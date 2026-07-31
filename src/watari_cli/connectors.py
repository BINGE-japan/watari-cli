"""組み込みコネクタのレジストリ（`watari connect` / `watari connector read` が使う）。

「案内→貼り付け→疎通確認→config 保存」は cloud.py の Google 認証と同じ形をサービスごとに
繰り返さないよう、ここに一枚で揃える。サービス固有の分岐（if name == "linear": ... elif ...）は
どこにも書かない。REGISTRY に ServiceAdapter を1件足すだけで `watari connect`（メニュー含む）と
`watari connector read` の両方に現れる（cli/__init__.py はレジストリを走査するだけで、サービス名を
知らない）。未対応サービスも同じ REGISTRY に `implemented=False` のプレースホルダとして載る
（選ぶと「未対応です。対応予定」と案内するだけ）。

認証情報は config.json の "connectors_auth" セクションへ {name: {"api_key": ...}} の形で保存する
（auth_kind="paste" のサービス）。gmail/calendar/gdrive は auth_kind="oauth" で、認証情報を
ここに置かず cloud.py の "google" セクション（drive.appdata 用に既に確立済みの OAuth を
incremental scope で拡張したもの）をそのまま使う。

connector の**宣言**（config.json の "connectors" リスト）は既存の config.save_connector を
そのまま使う（`watari connect` 成功時に自動登録し、`connector add` の手動宣言と二重管理しない）。
"""
from __future__ import annotations

from watari_cli import config


class ConnectorError(Exception):
    """接続/読み取りの失敗。呼び出し側（`watari connector read` の CLI 層）はカーソル据え置きで扱う。"""


class ServiceAdapter:
    """レジストリの1エントリ。実装済みサービスは guide/verify/read を持つ。未対応はラベルだけ。

    auth_kind="paste"（既定）は Linear/GitHub/Notion のようにユーザーがトークンを貼り付ける形。
    auth_kind="oauth" は「貼り付けプロンプトを CLI 側が挟まず、verify() 自身が認可まで完結させる」
    形（貼り付けは発生しない）。auth_kind="local" は他 AI CLI の会話ログ（transcript）のように
    認証そのものが不要なソース用——verify() は「ログ置き場を自動検出→保存、無ければパス入力を
    促して検証→保存」まで自己完結させる（例: transcripts/claude_code.py, transcripts/codex.py）。
    verify/read の呼び出し方が違う（cli._connect_wizard / connectors.read が auth_kind で
    分岐する。サービス名の if/elif はどこにも書かない）:
      - paste: verify(api_key) -> (ok, message) / read(api_key, since) -> rows
      - oauth / local: verify() -> (ok, message) / read(since) -> rows
    oauth の内部実装は一様ではない: Google 系（gmail/calendar/gdrive）は cloud.py の共有 OAuth
    （cloud.authorize(scopes)）を使い、接続判定も cloud.granted_scopes() で行う。freee のように
    Google を共有しない独立した OAuth（Client ID/Secret 貼り付け→ブラウザ認可→自前のトークン
    保存）を持つサービスは、`connected` にそのサービス自身の接続判定関数を渡す——
    connectors.is_connected() はこれを優先し、無ければ Google 系の既定判定にフォールバックする。
    auth_kind="local" は常に `connected` を渡す（Google の既定判定は当てはまらないため）。

    `scope` は接続成功時に登録する connector 宣言の scope（既定 "cloud"）。transcript 系は
    各マシンが自分のログを自分で夢に見るため "local" を渡す（cloud の「担当1台」ルールとは別）。
    """

    def __init__(self, label: str, implemented: bool = True,
                guide: list[str] | None = None, verify=None, read=None, brief=None,
                auth_kind: str = "paste", scopes: list[str] | None = None, connected=None,
                scope: str = "cloud"):
        self.label = label
        self.implemented = implemented
        self.guide = guide or []  # 案内行（`watari connect <name>` がそのまま表示する短い日本語）
        self.verify = verify
        self.read = read
        self.brief = brief  # current actionable state reader; independent of memory cursors
        self.auth_kind = auth_kind
        self.scopes = scopes or []  # auth_kind="oauth" のとき、このサービスに必要な追加スコープ
        # auth_kind="oauth"/"local" のとき接続判定を自前で持つサービス用（例: freee, transcript 系）。
        # 無ければ Google 系の既定（cloud.granted_scopes()）にフォールバックする（oauth のみ）。
        self.connected = connected
        self.scope = scope  # 接続成功時に登録する connector 宣言の scope


def _linear_adapter() -> ServiceAdapter:
    from watari_cli import linear

    return ServiceAdapter(
        label="Linear", implemented=True,
        guide=[
            "1. https://linear.app/settings/account/security を開く",
            "2. 'Personal API keys' で新しいキーを作る",
            "3. 発行されたキーをここに貼り付ける",
        ],
        verify=linear.verify, read=linear.read, brief=linear.brief,
    )


def _github_adapter() -> ServiceAdapter:
    from watari_cli import github

    return ServiceAdapter(
        label="GitHub", implemented=True,
        guide=[
            "1. https://github.com/settings/personal-access-tokens/new を開く"
            "（GitHub にログインしておいてください）",
            "2. トークン名と有効期限を決め、『Repository access』で読ませたいリポジトリを選ぶ",
            "3. 『Permissions』→『Repository permissions』で Issues と Pull requests を"
            " Read-only にして『Generate token』を押す",
            "4. 発行されたトークンをここに貼り付ける",
            "※ トークンには有効期限があります。期限が切れたら watari connect github で"
            "もう一度発行・登録してください",
        ],
        verify=github.verify, read=github.read,
    )


def _notion_adapter() -> ServiceAdapter:
    from watari_cli import notion

    return ServiceAdapter(
        label="Notion", implemented=True,
        guide=[
            "1. https://www.notion.so/my-integrations を開く",
            "2. 『New integration』で内部インテグレーションを作成し、表示される"
            "『内部インテグレーションシークレット』（貼り付け用の文字列）をコピーする",
            "3. 読ませたいページを開き、右上の『…』メニュー →『接続』（Connections）から、"
            "今作った integration を追加する"
            "（※この手順を飛ばすと、接続は成功してもページを一切読めません）",
            "4. コピーしたシークレットをここに貼り付ける",
        ],
        verify=notion.verify, read=notion.read,
    )


def _gmail_adapter() -> ServiceAdapter:
    from watari_cli import google_connectors as g

    return ServiceAdapter(
        label="Gmail", implemented=True, auth_kind="oauth", scopes=[g.GMAIL_SCOPE],
        guide=[
            "ブラウザで Google の承認画面が開きます（Gmail の読み取り専用アクセス）。",
            "※ watari auth と同じ Google アカウントで承認してください"
            "（別のアカウントを選ぶと、これまでの同期データが読めなくなります）。",
            "※ 初回は直近 14 日分から読み始めます（それより古い分はさかのぼりません）。",
        ],
        verify=g.gmail_verify, read=g.gmail_read, brief=g.gmail_brief,
    )


def _calendar_adapter() -> ServiceAdapter:
    from watari_cli import google_connectors as g

    return ServiceAdapter(
        label="Google カレンダー", implemented=True, auth_kind="oauth", scopes=[g.CALENDAR_SCOPE],
        guide=[
            "ブラウザで Google の承認画面が開きます（カレンダーの読み取り専用アクセス）。",
            "※ watari auth と同じ Google アカウントで承認してください"
            "（別のアカウントを選ぶと、これまでの同期データが読めなくなります）。",
            "※ 初回は直近 14 日分から読み始めます（それより古い分はさかのぼりません）。",
        ],
        verify=g.calendar_verify, read=g.calendar_read, brief=g.calendar_brief,
    )


def _gdrive_adapter() -> ServiceAdapter:
    from watari_cli import google_connectors as g

    return ServiceAdapter(
        label="Google ドライブ", implemented=True, auth_kind="oauth", scopes=[g.GDRIVE_SCOPE],
        guide=[
            "ブラウザで Google の承認画面が開きます（ドライブのファイル情報の読み取り専用アクセス。"
            "ファイルの中身は読みません）。",
            "※ watari auth と同じ Google アカウントで承認してください"
            "（別のアカウントを選ぶと、これまでの同期データが読めなくなります）。",
            "※ 初回は直近 14 日分から読み始めます（それより古い分はさかのぼりません）。",
        ],
        verify=g.gdrive_verify, read=g.gdrive_read,
    )


def _slack_adapter() -> ServiceAdapter:
    from watari_cli import slack

    # マニフェストは複数行の JSON。guide は「1要素=1行」の契約（表示側は各行に一律の
    # プレフィックスを付けるだけ）なので、ここで行ごとに分割して崩れない形で渡す。
    manifest_lines = ["   " + line for line in slack.SLACK_MANIFEST.splitlines()]
    return ServiceAdapter(
        label="Slack", implemented=True,
        guide=[
            "1. https://api.slack.com/apps を開き 'Create New App' → 'From an app manifest'",
            "2. 使うワークスペースを選んで Next",
            "3. JSON タブの中身（Demo App の雛形）を全選択（Ctrl+A / Cmd+A）して消し、"
            "下のマニフェストで置き換えて Next → Create:",
            *manifest_lines,
            "4. 作成後の画面で 'Install to Workspace'（左メニュー OAuth & Permissions からでも可）"
            "を押し、Allow で許可する",
            "5. OAuth & Permissions の 'User OAuth Token'（xoxp- で始まる方。bot の xoxb- ではない）"
            "をコピーしてここに貼り付ける",
            "※ 会社のワークスペースでは、アプリの作成やインストールに管理者の承認が必要な"
            "場合があります（進めない場合は管理者に依頼してください）",
        ],
        verify=slack.verify, read=slack.read,
    )


def _freee_adapter() -> ServiceAdapter:
    from watari_cli import freee

    return ServiceAdapter(
        label="freee（会計）", implemented=True, auth_kind="oauth", connected=freee.is_connected,
        guide=[
            "1. https://app.secure.freee.co.jp/developers/applications を開く",
            "2. ログインし、アプリを作成する事業所を選ぶ（顧問先の事業所では作成できません）",
            "3. 「アプリ管理」→「新規追加」でアプリ名・概要を入力して「作成」を押す",
            "4. 表示された Client ID と Client Secret を控える（このあとの入力で使います）",
            "5. コールバックURL欄に http://127.0.0.1:8787 を設定して保存する"
            "（8787番が使用中の場合は空きポートに切り替わり、実際に使う値を改めて表示します。"
            "ブラウザを開けない環境では、コールバックURL欄に特別な値 urn:ietf:wg:oauth:2.0:oob を"
            "設定します——その場合は承認後に画面へ表示されるコードをターミナルに貼り付けます。"
            "必要になったら改めて案内します）",
            "6. 続けて Client ID → Client Secret の順に貼り付けてください（ブラウザで承認画面が"
            "開きます）",
        ],
        verify=freee.verify, read=freee.read,
    )


def _chatwork_adapter() -> ServiceAdapter:
    from watari_cli import chatwork

    return ServiceAdapter(
        label="Chatwork", implemented=True,
        guide=[
            "1. 次のページを開く（Chatwork にログインした状態で）:",
            "   https://www.chatwork.com/service/packages/chatwork/subpackages/api/token.php",
            "   ※画面から辿る場合: 右上のアカウント（利用者名）→『サービス連携』→ 左メニューの"
            "『API』→『APIトークン』",
            "2. ログインパスワードを入力すると API トークンが表示される",
            "3. 『コピー』を押して、そのトークンをここに貼り付ける",
            "※ 法人向けプランでは、組織の管理者が API 利用を有効にしていないとトークンを発行"
            "できない（表示されない場合は管理者に有効化を依頼する）",
        ],
        verify=chatwork.verify, read=chatwork.read,
    )


def _obsidian_adapter() -> ServiceAdapter:
    from watari_cli import obsidian

    return ServiceAdapter(
        label=obsidian.LABEL, implemented=True, auth_kind="local", scope="local",
        connected=obsidian.is_connected,
        guide=[
            "ObsidianのMarkdownノートを、vault内だけに限定した読み取り専用処理で取り込みます。",
            "認証は不要です。既存のObsidian設定があれば安全な形式へ自動移行します。",
            "見つからない場合だけ、vaultフォルダのパスを聞きます。",
            "※ .obsidian、隠しフォルダ、Journal/Watari、シンボリックリンクは読みません。",
        ],
        verify=obsidian.verify, read=obsidian.read,
    )


def _claude_code_adapter() -> ServiceAdapter:
    from watari_cli.transcripts import claude_code as cc

    return ServiceAdapter(
        label=cc.LABEL, implemented=True, auth_kind="local", scope="local",
        connected=cc.is_connected,
        guide=[
            "Claude Code（Anthropic の AI コーディングツール）を使っている場合、"
            "その会話もワタリの記憶の材料になります。使っていなければこの接続は不要です。",
            "認証は不要です。Claude Code の会話ログ（~/.claude/projects）を探します。",
            "見つからない場合は、会話ログが入っているフォルダのパスを聞きます。",
        ],
        verify=cc.verify, read=cc.read,
    )


def _codex_adapter() -> ServiceAdapter:
    from watari_cli.transcripts import codex

    return ServiceAdapter(
        label=codex.LABEL, implemented=True, auth_kind="local", scope="local",
        connected=codex.is_connected,
        guide=[
            "Codex（OpenAI の AI コーディングツール）を使っている場合、"
            "その会話もワタリの記憶の材料になります。使っていなければこの接続は不要です。",
            "認証は不要です。Codex の会話ログ（~/.codex/sessions）を探します。",
            "見つからない場合は、会話ログが入っているフォルダのパスを聞きます。",
        ],
        verify=codex.verify, read=codex.read,
    )


def _placeholder(label: str):
    """未対応サービスのアダプタ工場（実装が付くまでの枠）。"""
    def factory() -> ServiceAdapter:
        return ServiceAdapter(label=label, implemented=False)
    return factory


# name -> ServiceAdapter を作る工場（遅延 import：使わないサービスの依存を読み込まない）。
# ここに1行足すだけでメニュー・connect・connector read の全部に現れる（他の場所に分岐を書かない）。
REGISTRY = {
    "linear": _linear_adapter,
    "github": _github_adapter,
    "notion": _notion_adapter,
    "slack": _slack_adapter,
    "chatwork": _chatwork_adapter,
    "freee": _freee_adapter,
    "gmail": _gmail_adapter,
    "calendar": _calendar_adapter,
    "gdrive": _gdrive_adapter,
    "obsidian": _obsidian_adapter,
    "claude-code": _claude_code_adapter,
    "codex": _codex_adapter,
    # 未実装のサービスはここに載せない——選べるのに使えない行はメニューのノイズになる。
    # 実装できるだけの一次情報（ログ置き場・形式、または API 仕様）が取れた時点で
    # _placeholder ではなく本実装のアダプタとして追加する。
}


def get_service(name: str) -> ServiceAdapter | None:
    factory = REGISTRY.get(name)
    return factory() if factory else None


def list_services() -> list[tuple[str, ServiceAdapter]]:
    """レジストリ登録順の (name, ServiceAdapter) 一覧（`watari connect` のメニューが使う）。"""
    return [(name, get_service(name)) for name in REGISTRY]


def is_builtin_name(name: str) -> bool:
    return name in REGISTRY


def _auth_section() -> dict:
    section = config.load_config().get("connectors_auth")
    return section if isinstance(section, dict) else {}


def auth_key(name: str) -> str | None:
    """保存済み API キー（未接続なら None）。"""
    return (_auth_section().get(name) or {}).get("api_key")


def save_auth(name: str, api_key: str) -> None:
    """API キーを config.json の connectors_auth.<name> に保存する（キー自体は出力しない）。"""
    auth = _auth_section()
    auth[name] = {"api_key": api_key}
    config.save_config(connectors_auth=auth)


def is_connected(name: str) -> bool:
    service = get_service(name)
    if service is None:
        return False
    if service.auth_kind == "local":
        # 認証不要のソース（transcript 系）。自前の判定関数（configured_path の有無）が必須。
        return service.connected() if service.connected is not None else False
    if service.auth_kind == "oauth":
        if service.connected is not None:
            return service.connected()
        from watari_cli import cloud

        granted = set(cloud.granted_scopes())
        return cloud.is_authorized() and all(scope in granted for scope in service.scopes)
    return bool(auth_key(name))


def brief(name: str, now) -> list[dict]:
    """Read current actionable state without touching connector/memory cursors."""
    service = get_service(name)
    if service is None or service.brief is None:
        return []
    if not is_connected(name):
        raise ConnectorError(f"{name} は未接続です（接続するには: watari connect {name}）")
    if service.auth_kind in ("oauth", "local"):
        return service.brief(now)
    api_key = auth_key(name)
    if not api_key:
        raise ConnectorError(f"{name} は未接続です（接続するには: watari connect {name}）")
    return service.brief(api_key, now)


def read(name: str, since: str | None) -> list[dict]:
    """組み込みコネクタ name をカーソル(since)以降で読む。未知/未対応/未接続は ConnectorError。"""
    service = get_service(name)
    if service is None:
        raise ConnectorError(
            f"対応サービスにありません: {name}（一覧は watari connect で確認できます）")
    if not service.implemented:
        raise ConnectorError(f"{service.label} は未対応です（対応予定）")
    if service.auth_kind in ("oauth", "local"):
        if not is_connected(name):
            raise ConnectorError(f"{name} は未接続です（接続するには: watari connect {name}）")
        return service.read(since)
    api_key = auth_key(name)
    if not api_key:
        raise ConnectorError(f"{name} は未接続です（接続するには: watari connect {name}）")
    return service.read(api_key, since)
