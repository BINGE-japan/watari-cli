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
    auth_kind="oauth" は Google 系（gmail/calendar/gdrive）のように cloud.py の共有 OAuth を使う
    形で、貼り付けは発生しない。verify/read の呼び出し方が違う（cli._connect_wizard /
    connectors.read が auth_kind で分岐する。サービス名の if/elif はどこにも書かない）:
      - paste: verify(api_key) -> (ok, message) / read(api_key, since) -> rows
      - oauth: verify() -> (ok, message)（内部で cloud.authorize(scopes) を必要時に起動）/
               read(since) -> rows
    """

    def __init__(self, label: str, implemented: bool = True,
                guide: list[str] | None = None, verify=None, read=None,
                auth_kind: str = "paste", scopes: list[str] | None = None):
        self.label = label
        self.implemented = implemented
        self.guide = guide or []  # 案内行（`watari connect <name>` がそのまま表示する短い日本語）
        self.verify = verify
        self.read = read
        self.auth_kind = auth_kind
        self.scopes = scopes or []  # auth_kind="oauth" のとき、このサービスに必要な追加スコープ


def _linear_adapter() -> ServiceAdapter:
    from watari_cli import linear

    return ServiceAdapter(
        label="Linear", implemented=True,
        guide=[
            "1. https://linear.app/settings/account/security を開く",
            "2. 'Personal API keys' で新しいキーを作る",
            "3. 発行されたキーをここに貼り付ける",
        ],
        verify=linear.verify, read=linear.read,
    )


def _github_adapter() -> ServiceAdapter:
    from watari_cli import github

    return ServiceAdapter(
        label="GitHub", implemented=True,
        guide=[
            "1. https://github.com/settings/tokens を開く",
            "2. 'Generate new token' → 'Fine-grained tokens' を選ぶ",
            "3. 対象リポジトリに Issues / Pull requests の Read 権限を付けて発行する",
            "4. 発行されたトークンをここに貼り付ける",
        ],
        verify=github.verify, read=github.read,
    )


def _notion_adapter() -> ServiceAdapter:
    from watari_cli import notion

    return ServiceAdapter(
        label="Notion", implemented=True,
        guide=[
            "1. https://www.notion.so/my-integrations を開く",
            "2. 'New integration' で Internal Integration を作成し、トークンを発行する",
            "3. 読ませたいページ/データベースを開き、右上の Connections から今作った"
            " integration を接続する",
            "4. 発行されたトークンをここに貼り付ける",
        ],
        verify=notion.verify, read=notion.read,
    )


def _gmail_adapter() -> ServiceAdapter:
    from watari_cli import google_connectors as g

    return ServiceAdapter(
        label="Gmail", implemented=True, auth_kind="oauth", scopes=[g.GMAIL_SCOPE],
        guide=[
            "ブラウザで Google の承認画面が開きます（Gmail の読み取り専用アクセス）。",
            "サインイン中の Google アカウントで許可してください。",
        ],
        verify=g.gmail_verify, read=g.gmail_read,
    )


def _calendar_adapter() -> ServiceAdapter:
    from watari_cli import google_connectors as g

    return ServiceAdapter(
        label="Google カレンダー", implemented=True, auth_kind="oauth", scopes=[g.CALENDAR_SCOPE],
        guide=[
            "ブラウザで Google の承認画面が開きます（カレンダーの読み取り専用アクセス）。",
            "サインイン中の Google アカウントで許可してください。",
        ],
        verify=g.calendar_verify, read=g.calendar_read,
    )


def _gdrive_adapter() -> ServiceAdapter:
    from watari_cli import google_connectors as g

    return ServiceAdapter(
        label="Google ドライブ", implemented=True, auth_kind="oauth", scopes=[g.GDRIVE_SCOPE],
        guide=[
            "ブラウザで Google の承認画面が開きます（ドライブのメタデータ読み取り専用アクセス）。",
            "サインイン中の Google アカウントで許可してください。",
        ],
        verify=g.gdrive_verify, read=g.gdrive_read,
    )


def _slack_adapter() -> ServiceAdapter:
    from watari_cli import slack

    return ServiceAdapter(
        label="Slack", implemented=True,
        guide=[
            "1. https://api.slack.com/apps を開き 'Create New App' → 'From an app manifest' を"
            "選ぶ",
            "2. 対象ワークスペースを選び、次のマニフェストを貼り付ける:\n" + slack.SLACK_MANIFEST,
            "3. 自分のワークスペースにインストールし、発行された User OAuth Token（xoxp-）を"
            "ここに貼り付ける",
        ],
        verify=slack.verify, read=slack.read,
    )


def _chatwork_adapter() -> ServiceAdapter:
    from watari_cli import chatwork

    return ServiceAdapter(
        label="Chatwork", implemented=True,
        guide=[
            "1. Chatwork 右上のプロフィールアイコン → 'サービス連携' を開く",
            "2. 'API Token' で発行する",
            "3. 発行されたトークンをここに貼り付ける",
        ],
        verify=chatwork.verify, read=chatwork.read,
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
    "gmail": _gmail_adapter,
    "calendar": _calendar_adapter,
    "gdrive": _gdrive_adapter,
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
    if service.auth_kind == "oauth":
        from watari_cli import cloud

        granted = set(cloud.granted_scopes())
        return cloud.is_authorized() and all(scope in granted for scope in service.scopes)
    return bool(auth_key(name))


def read(name: str, since: str | None) -> list[dict]:
    """組み込みコネクタ name をカーソル(since)以降で読む。未知/未対応/未接続は ConnectorError。"""
    service = get_service(name)
    if service is None:
        raise ConnectorError(f"組み込みコネクタではありません: {name}")
    if not service.implemented:
        raise ConnectorError(f"{service.label} は未対応です（対応予定）")
    if service.auth_kind == "oauth":
        if not is_connected(name):
            raise ConnectorError(f"{name} は未接続です（先に `watari connect {name}`）")
        return service.read(since)
    api_key = auth_key(name)
    if not api_key:
        raise ConnectorError(f"{name} は未接続です（先に `watari connect {name}`）")
    return service.read(api_key, since)
