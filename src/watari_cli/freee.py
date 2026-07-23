"""freee（クラウド会計）connector（組み込み）。OAuth（loopback 優先・oob フォールバック）＋
取引(deals)の決定論リーダー。

linear/github/notion/slack/chatwork と違い、freee はユーザーが貼るのは Client ID/Secret だけで、
実際の認可は freee 側のブラウザ画面で行う。auth_kind は既存の "paste"（トークン1個の貼り付け）にも
"oauth"（cloud.py の共有 Google 認可）にもそのまま当てはまらないが、専用の3個目の auth_kind は
増やさない。代わりに `verify()` 自身が「Client ID/Secret の入力 → ブラウザ認可 → トークン交換 →
事業所選択 → config 保存」まで一通り行い、`ServiceAdapter(auth_kind="oauth")`（＝
`_connect_wizard` が引数無しで `service.verify()` を呼ぶだけの経路。貼り付けプロンプトを
CLI 側が挟まない）に乗せる。ただし gmail/calendar/gdrive と違い freee は cloud.py の Google OAuth
を共有しないので、`connectors.is_connected()` は `ServiceAdapter.connected`（この
モジュールの `is_connected`）を経由する（connectors.py 側は auth_kind の分岐のみで、
サービス名の分岐は増やさない）。

認可フロー（`_run_authorization`）:
- 127.0.0.1:8787（固定ポート）での loopback 待ち受けを第一候補にする。使用中なら空きポートへ
  フォールバックする。どちらも bind できない、またはコールバックが来ないまま失敗した場合は
  `urn:ietf:wg:oauth:2.0:oob`（画面に認可コードが表示される方式）にフォールバックする——
  貼り付けプロンプトが出るのはこの oob 経路のときだけ。
- 実際に使う redirect_uri は毎回 print で明示する（アプリのコールバックURL欄をその値に
  置き換えて保存してもらう必要があるため）。

トークン仕様（freee 公式・確認済み。再調査しないこと）:
- アクセストークンは 6 時間（21600秒）。リフレッシュトークンは 90 日で、**使い捨て**
  （同じ refresh_token では2度取得できない＝更新のたびにローテーションする）。
- そのため `access_token()` は更新のたびに応答の新しい refresh_token を必ず config へ
  上書き保存してから access_token を返す（保存前に返すと、保存に失敗した回だけ新しい
  refresh_token が失われ次回から認証不能になる）。保存は config.save_config の
  tmp+os.replace による原子的書き込みに委ねる。90日失効・invalid_grant は
  「再接続が必要です（`watari connect freee`）」と明示するエラーにする。

事業所(company_id): トークン取得直後に GET /api/1/companies を叩き、1件なら自動選択、複数なら
`prompts.select` で選ばせて company_id を保存する（read はこの company_id を使い回す）。

read の対象は `GET /api/1/deals`（取引一覧）の単発取得のみ（ページングは1ページ=100件で打ち切り。
超過分は次回以降の呼び出しに回る、他アダプタと同じ「1回で取り切らない」設計）。deals 一覧応答は
取引先・勘定科目を ID でしか返さない（名称解決には別エンドポイントが要り、単発取得のスコープ外）
ため、text には display 名があればそれを、無ければ ID / 摘要(details[0].description) を畳む
（明細の全文は書き写さない。正本は freee のまま）。

認証情報は config.json の `connectors_auth.freee` に保存する（カセット記憶には絶対に入れない）。
"""
from __future__ import annotations

import http.server
import json
import secrets
import time
import urllib.parse
import webbrowser

from watari_cli import config, connector_http, prompts
from watari_cli.connectors import ConnectorError

AUTHORIZE_URL = "https://accounts.secure.freee.co.jp/public_api/authorize"
TOKEN_URL = "https://accounts.secure.freee.co.jp/public_api/token"
COMPANIES_URL = "https://api.freee.co.jp/api/1/companies"
DEALS_URL = "https://api.freee.co.jp/api/1/deals"

OOB_REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"
LOOPBACK_PORT = 8787  # 第一候補の固定ポート（使用中なら空きポートへフォールバック）
_LOOPBACK_WAIT_SECONDS = 300  # 最長5分待つ（cloud.py の Google 認可と同じ長さ）


def _http(method: str, url: str, headers: dict | None = None, data: bytes | None = None):
    """(status, body_bytes) を返す。他アダプタと同じ薄いラッパー（テストが差し替える名前）。"""
    return connector_http.request("freee", method, url, headers, data)


# ---- config 永続化 ------------------------------------------------------------

def _auth_section() -> dict:
    section = config.load_config().get("connectors_auth")
    section = section if isinstance(section, dict) else {}
    freee = section.get("freee")
    return freee if isinstance(freee, dict) else {}


def _save_auth(**fields) -> None:
    """connectors_auth.freee へ read-modify-write でマージ保存する（None の値は書かない）。

    config.save_config は tmp ファイル＋os.replace で原子的に書く。書き込み自体が失敗したら
    ConnectorError にして明確に伝える（呼び出し側＝リフレッシュ直後はここで失敗すると
    ローテーション済みの新しい refresh_token を失うため、曖昧に握りつぶさない）。
    """
    root = config.load_config().get("connectors_auth")
    root = dict(root) if isinstance(root, dict) else {}
    section = dict(root.get("freee") or {})
    section.update({k: v for k, v in fields.items() if v is not None})
    root["freee"] = section
    try:
        config.save_config(connectors_auth=root)
    except OSError as error:
        raise ConnectorError(
            f"freee: 認証情報の保存に失敗しました: {error}。"
            f"次回エラーになる場合は、{connector_http.reconnect_hint('freee')}")


def is_connected() -> bool:
    """client_id/secret/refresh_token/company_id が全部揃っていれば接続済み扱い。"""
    section = _auth_section()
    return bool(section.get("client_id") and section.get("client_secret")
                and section.get("refresh_token") and section.get("company_id"))


# ---- 認可コード取得（loopback 優先・oob フォールバック） -----------------------------

class _CodeCaptureHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        self.server.captured = {  # type: ignore[attr-defined]
            "code": params.get("code", [None])[0],
            "state": params.get("state", [None])[0],
            "error": params.get("error", [None])[0],
        }
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("認証を受け取りました。ターミナルに戻ってください。".encode("utf-8"))

    def log_message(self, *a):  # 静かに
        pass


def _bind_loopback_server():
    """127.0.0.1 の固定ポート(8787)優先、使用中なら空きポート(0)へフォールバックして bind する。

    どちらも失敗したら None（呼び出し側は oob へフォールバックする）。
    """
    for port in (LOOPBACK_PORT, 0):
        try:
            return http.server.HTTPServer(("127.0.0.1", port), _CodeCaptureHandler)
        except OSError:
            continue
    return None


def _authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    return AUTHORIZE_URL + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri,
        "state": state, "prompt": "select_company",
    })


def _open_browser(auth_url: str) -> None:
    print("ブラウザで freee の承認画面を開きます。自動で開かない場合は、"
          "次の URL をブラウザのアドレス欄に貼り付けて開いてください:", flush=True)
    print(f"  {auth_url}", flush=True)
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass


def _run_authorization_loopback(client_id: str, server) -> tuple[str, str] | None:
    """bind 済みの loopback サーバでコールバックを待つ。成功時は (code, redirect_uri)、
    失敗（timeout / state 不一致 / error パラメータ）時は None（呼び出し側が oob へ回す）。
    """
    port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}"
    print(f"freee アプリの「コールバックURL」欄が {redirect_uri} になっているか確認してください"
          "（手順どおり設定済みならそのままで大丈夫です。違う値ならこの値に置き換えて"
          "保存してください）。", flush=True)
    prompts.text("確認できたら Enter を押してください", default="")
    state = secrets.token_urlsafe(16)
    _open_browser(_authorize_url(client_id, redirect_uri, state))
    server.timeout = 1
    deadline = time.monotonic() + _LOOPBACK_WAIT_SECONDS
    captured: dict = {}
    while time.monotonic() < deadline:
        server.handle_request()
        captured = getattr(server, "captured", None) or {}
        if captured:
            break
    server.server_close()
    if captured.get("code") and captured.get("state") == state:
        return captured["code"], redirect_uri
    return None


def _run_authorization_oob(client_id: str) -> tuple[str, str]:
    """loopback が使えない/失敗したときのフォールバック。画面に出る認可コードを貼ってもらう
    （貼り付けプロンプトが出るのはこの経路だけ）。"""
    redirect_uri = OOB_REDIRECT_URI
    print(f"freee アプリの「コールバックURL」欄をこの値に置き換えて保存してください: "
          f"{redirect_uri}", flush=True)
    state = secrets.token_urlsafe(16)
    _open_browser(_authorize_url(client_id, redirect_uri, state))
    code = prompts.text("承認後に画面に表示されたコードを貼り付けてください")
    if not code:
        raise ConnectorError(
            "freee: コードが入力されなかったため中止しました。"
            f"{connector_http.reconnect_hint('freee')}")
    return code, redirect_uri


def _run_authorization(client_id: str) -> tuple[str, str]:
    """(code, redirect_uri) を返す。loopback を第一候補にし、bind 失敗/コールバック失敗は
    oob にフォールバックする（テストはこの関数ごと差し替えて実ソケット/実ブラウザを通さない）。
    """
    server = _bind_loopback_server()
    if server is not None:
        result = _run_authorization_loopback(client_id, server)
        if result is not None:
            return result
    return _run_authorization_oob(client_id)


# ---- トークン交換・更新 ----------------------------------------------------------

def _token_request(data: dict, context: str) -> dict:
    payload = urllib.parse.urlencode(data).encode()
    status, body = _http("POST", TOKEN_URL,
                         {"Content-Type": "application/x-www-form-urlencoded"}, payload)
    if status != 200:
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {}
        if parsed.get("error") == "invalid_grant":
            raise ConnectorError("freee: 再接続が必要です（watari connect freee）")
        raise ConnectorError(
            f"freee: {context}に失敗しました({status}): {connector_http.body_text(body)}。"
            f"{connector_http.reconnect_hint('freee')}")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise ConnectorError(
            f"freee: 応答を読み取れませんでした: {connector_http.body_text(body)}。"
            f"時間をおいて再実行してください")


def _exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    return _token_request({
        "grant_type": "authorization_code", "client_id": client_id,
        "client_secret": client_secret, "code": code, "redirect_uri": redirect_uri,
    }, "認証情報の取得")


def _refresh(client_id: str, client_secret: str, refresh_token: str) -> dict:
    return _token_request({
        "grant_type": "refresh_token", "client_id": client_id,
        "client_secret": client_secret, "refresh_token": refresh_token,
    }, "認証情報の更新")


def access_token() -> str:
    """有効な access_token を返す（呼び出しのたびに refresh_token で更新する。cloud.py の
    access_token() と同じくキャッシュしない）。

    freee の refresh_token は使い捨て（ローテーション）なので、更新に成功したら**必ず**新しい
    refresh_token を保存してから access_token を返す（保存前に返すと事故る）。
    """
    section = _auth_section()
    client_id = section.get("client_id")
    client_secret = section.get("client_secret")
    refresh_token = section.get("refresh_token")
    if not (client_id and client_secret and refresh_token):
        raise ConnectorError("freee: 未接続です（接続するには: watari connect freee）")
    token = _refresh(client_id, client_secret, refresh_token)
    new_refresh_token = token.get("refresh_token")
    if not new_refresh_token:
        raise ConnectorError(
            "freee: 認証の更新情報を受け取れませんでした。再接続が必要です（watari connect freee）")
    _save_auth(refresh_token=new_refresh_token)  # ローテーション対応：必ず新しい値へ差し替える
    access = token.get("access_token")
    if not access:
        raise ConnectorError(
            "freee: 認証情報を取得できませんでした。"
            f"{connector_http.reconnect_hint('freee')}")
    return access


# ---- 事業所選択 ----------------------------------------------------------------

def _get_json(url: str, token: str) -> dict:
    status, body = _http("GET", url, {"Authorization": f"Bearer {token}"})
    if status == 401:
        raise ConnectorError("freee: 認証に失敗しました。再接続が必要です（watari connect freee）")
    if status != 200:
        raise ConnectorError(
            f"freee: API エラー({status}): {connector_http.body_text(body)}。"
            f"時間をおいて再実行してください（続くようなら、{connector_http.reconnect_hint('freee')}）")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise ConnectorError(
            f"freee: 応答を読み取れませんでした: {connector_http.body_text(body)}。"
            f"時間をおいて再実行してください")


def _company_label(company: dict) -> str:
    return company.get("display_name") or company.get("name") or str(company.get("id"))


def _resolve_company(access_token_: str) -> tuple[int, str]:
    """GET /api/1/companies。1件なら自動選択、複数なら prompts.select で選ばせる。"""
    data = _get_json(COMPANIES_URL, access_token_)
    companies = data.get("companies") or []
    if not companies:
        raise ConnectorError(
            "freee: 事業所が見つかりませんでした。承認した freee アカウントに事業所が"
            f"登録されているか確認してください（{connector_http.reconnect_hint('freee')}）")
    if len(companies) == 1:
        company = companies[0]
        return company["id"], _company_label(company)
    options = [(_company_label(c), c["id"]) for c in companies]
    company_id = prompts.select("事業所を選んでください", options, default=0)
    chosen = next(c for c in companies if c["id"] == company_id)
    return company_id, _company_label(chosen)


# ---- verify（Client ID/Secret 入力 → ブラウザ認可 → トークン保存 → 事業所選択まで一括） ------

def verify() -> tuple[bool, str]:
    """auth_kind="oauth" の「貼り付けプロンプトなし」経路に乗せるため、Client ID/Secret の入力
    自体はここで行う（貼り付けプロンプトが出るのは client_id/secret と、oob フォールバック時の
    認可コードだけ——linear 等の「トークン1個貼る」paste 経路とは別物）。

    成功時は (True, "<事業所名>（事業所ID=<id>）")、失敗時は (False, 理由)。
    """
    client_id = prompts.text("freee アプリの Client ID を貼り付けてください")
    client_secret = prompts.text("freee アプリの Client Secret を貼り付けてください")
    if not client_id or not client_secret:
        return False, ("Client ID / Client Secret が入力されなかったため中止しました。"
                       "watari connect freee でやり直せます")
    try:
        code, redirect_uri = _run_authorization(client_id)
        token = _exchange_code(client_id, client_secret, code, redirect_uri)
    except ConnectorError as error:
        return False, str(error)
    refresh_token = token.get("refresh_token")
    access = token.get("access_token")
    if not refresh_token or not access:
        return False, ("freee から認証情報を受け取れませんでした。"
                       f"{connector_http.reconnect_hint('freee')}")
    try:
        _save_auth(client_id=client_id, client_secret=client_secret, refresh_token=refresh_token)
        company_id, company_name = _resolve_company(access)
        _save_auth(company_id=company_id)
    except ConnectorError as error:
        return False, str(error)
    return True, f"{company_name}（事業所ID={company_id}）"


# ---- read（取引） --------------------------------------------------------------

def _format_row(deal: dict) -> dict:
    issue_date = deal.get("issue_date") or "1970-01-01"
    deal_id = deal["id"]
    details = deal.get("details") or []
    first_detail = details[0] if details else {}

    partner = deal.get("partner_name") or deal.get("partner_display_name")
    if not partner:
        partner = f"取引先ID={deal['partner_id']}" if deal.get("partner_id") else "取引先不明"

    amount = deal.get("amount")
    amount_text = f"{amount:,}円" if isinstance(amount, (int, float)) else "金額不明"

    account_item = first_detail.get("account_item_name")
    if not account_item and first_detail.get("account_item_id"):
        account_item = f"勘定科目ID={first_detail['account_item_id']}"
    account_item = account_item or first_detail.get("description") or "-"

    return {
        "ts": issue_date,
        "uuid": f"freee:deal:{deal_id}@{issue_date}",
        "text": f"[取引] {issue_date} / {partner} / {amount_text} / {account_item}",
        "meta": {"id": deal_id, "type": deal.get("type")},
    }


def read(since: str | None) -> list[dict]:
    """カーソル(since)以降の取引(deals)を統一形式 [{ts,uuid,text,meta}, ...] で発生日昇順に返す。

    GET /api/1/deals?company_id=<id>&start_issue_date=<sinceの日付YYYY-MM-DD>&limit=100 の
    単発取得（ページングは1ページで打ち切り。100件を超える同日分は次回以降の呼び出しに回る、
    他アダプタと同じ「1回で取り切らない」設計）。since 省略時は全件相当（1970-01-01 起点）。
    """
    section = _auth_section()
    company_id = section.get("company_id")
    if not company_id:
        raise ConnectorError("freee: 未接続です（接続するには: watari connect freee）")
    token = access_token()
    since_date = (since or "1970-01-01")[:10]
    params = urllib.parse.urlencode({
        "company_id": company_id, "start_issue_date": since_date, "limit": "100",
    })
    data = _get_json(f"{DEALS_URL}?{params}", token)
    rows = [_format_row(deal) for deal in data.get("deals") or []]
    rows.sort(key=lambda r: (r["ts"], r["uuid"]))
    return rows
