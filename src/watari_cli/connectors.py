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
    （cloud.authorize(scopes)）を使い、`available` で各サービスのプロフィール用 API が現在読める
    ことまで確認する。freee のように Google を共有しない独立した OAuth（Client ID/Secret
    貼り付け→ブラウザ認可→自前のトークン保存）を持つサービスは、`connected` にそのサービス
    自身の保存済み設定判定関数を渡す。auth_kind="local" も常に `connected` を渡す（Google の
    既定判定は当てはまらないため）。

    `scope` は接続成功時に登録する connector 宣言の scope（既定 "cloud"）。transcript 系は
    各マシンが自分のログを自分で夢に見るため "local" を渡す（cloud の「担当1台」ルールとは別）。
    """

    def __init__(self, label: str, implemented: bool = True,
                guide: list[str] | None = None, verify=None, read=None, brief=None,
                auth_kind: str = "paste", scopes: list[str] | None = None, connected=None,
                available=None, scope: str = "cloud"):
        self.label = label
        self.implemented = implemented
        self.guide = guide or []  # 案内行（`watari connect <name>` がそのまま表示する短い日本語）
        self.verify = verify
        self.read = read
        self.brief = brief  # current actionable state reader; independent of memory cursors
        self.auth_kind = auth_kind
        self.scopes = scopes or []  # auth_kind="oauth" のとき、このサービスに必要な追加スコープ
        # 保存済み設定の存在判定を自前で持つサービス用（例: freee, transcript 系）。
        # 無ければ Google 系の既定（cloud.is_authorized + granted_scopes）を使う（oauth のみ）。
        self.connected = connected
        # 表示用の実接続テスト。Google 系はプロフィール用 API まで読める場合だけ True にする。
        self.available = available
        self.scope = scope  # 接続成功時に登録する connector 宣言の scope


def _linear_adapter() -> ServiceAdapter:
    from watari_cli import linear

    return ServiceAdapter(
        label="Linear", implemented=True,
        guide=[
            "1. Open https://linear.app/settings/account/security",
            "2. Under 'Personal API keys', create a new key",
            "3. Paste the generated key here",
        ],
        verify=linear.verify, read=linear.read, brief=linear.brief,
    )


def _github_adapter() -> ServiceAdapter:
    from watari_cli import github

    return ServiceAdapter(
        label="GitHub", implemented=True,
        guide=[
            "1. Sign in to GitHub, then open "
            "https://github.com/settings/personal-access-tokens/new",
            "2. Set a token name and expiration, then choose repositories under 'Repository access'",
            "3. Under 'Permissions' > 'Repository permissions', set Issues and Pull requests to "
            "Read-only, then click 'Generate token'",
            "4. Paste the generated token here",
            "Note: when the token expires, run `watari connect github` to replace it",
        ],
        verify=github.verify, read=github.read,
    )


def _notion_adapter() -> ServiceAdapter:
    from watari_cli import notion

    return ServiceAdapter(
        label="Notion", implemented=True,
        guide=[
            "1. Open https://www.notion.so/my-integrations",
            "2. Click 'New integration', create an internal integration, and copy its "
            "'Internal Integration Secret'",
            "3. Open each page Watari should read, then use the top-right '...' > 'Connections' "
            "menu to add the integration",
            "4. Paste the copied secret here",
            "Note: without step 3, the connection succeeds but Watari cannot see any pages",
        ],
        verify=notion.verify, read=notion.read,
    )


def _gmail_adapter() -> ServiceAdapter:
    from watari_cli import google_connectors as g

    return ServiceAdapter(
        label="Gmail", implemented=True, auth_kind="oauth", scopes=[g.GMAIL_SCOPE],
        guide=[
            "A browser will open the Google consent screen for read-only Gmail access",
            "Use the same Google account used for `watari auth`; choosing another account "
            "prevents access to existing synced data",
            "The first read starts with the most recent 14 days",
        ],
        verify=g.gmail_verify, read=g.gmail_read, brief=g.gmail_brief,
        available=g.gmail_is_connected,
    )


def _calendar_adapter() -> ServiceAdapter:
    from watari_cli import google_connectors as g

    return ServiceAdapter(
        label="Google カレンダー", implemented=True, auth_kind="oauth", scopes=[g.CALENDAR_SCOPE],
        guide=[
            "A browser will open the Google consent screen for read-only Calendar access",
            "Use the same Google account used for `watari auth`; choosing another account "
            "prevents access to existing synced data",
            "The first read starts with the most recent 14 days",
        ],
        verify=g.calendar_verify, read=g.calendar_read, brief=g.calendar_brief,
        available=g.calendar_is_connected,
    )


def _gdrive_adapter() -> ServiceAdapter:
    from watari_cli import google_connectors as g

    return ServiceAdapter(
        label="Google ドライブ", implemented=True, auth_kind="oauth", scopes=[g.GDRIVE_SCOPE],
        guide=[
            "A browser will open the Google consent screen for read-only Drive metadata access; "
            "file contents are not read",
            "Use the same Google account used for `watari auth`; choosing another account "
            "prevents access to existing synced data",
            "The first read starts with the most recent 14 days",
        ],
        verify=g.gdrive_verify, read=g.gdrive_read, available=g.gdrive_is_connected,
    )


def _slack_adapter() -> ServiceAdapter:
    from watari_cli import slack

    # マニフェストは複数行の JSON。guide は「1要素=1行」の契約（表示側は各行に一律の
    # プレフィックスを付けるだけ）なので、ここで行ごとに分割して崩れない形で渡す。
    manifest_lines = ["   " + line for line in slack.SLACK_MANIFEST.splitlines()]
    return ServiceAdapter(
        label="Slack", implemented=True,
        guide=[
            "1. Open https://api.slack.com/apps, then choose 'Create New App' > "
            "'From an app manifest'",
            "2. Choose the workspace, then click 'Next'",
            "3. On the 'JSON' tab, select all (Ctrl+A / Cmd+A), replace the demo manifest with "
            "the manifest below, then click 'Next' > 'Create':",
            *manifest_lines,
            "4. Click 'Install to Workspace' (also available under 'OAuth & Permissions'), "
            "then click 'Allow'",
            "5. Under 'OAuth & Permissions', copy the 'User OAuth Token' beginning with xoxp- "
            "(not the xoxb- bot token), then paste it here",
            "Note: a workspace administrator may need to approve app creation or installation",
        ],
        verify=slack.verify, read=slack.read,
    )


def _freee_adapter() -> ServiceAdapter:
    from watari_cli import freee

    return ServiceAdapter(
        label="freee（会計）", implemented=True, auth_kind="oauth", connected=freee.is_connected,
        guide=[
            "1. Open https://app.secure.freee.co.jp/developers/applications",
            "2. Sign in and choose the company that will own the app",
            "3. Open 'App Management', choose 'Add New', enter the app name and description, "
            "then click 'Create'",
            "4. Copy the displayed 'Client ID' and 'Client Secret'",
            "5. Set 'Callback URL' to http://127.0.0.1:8787 and save; if that port is unavailable, "
            "Watari will show the actual URL to use",
            "6. Paste the Client ID and Client Secret when prompted; the authorization page "
            "will then open in your browser",
        ],
        verify=freee.verify, read=freee.read,
    )


def _chatwork_adapter() -> ServiceAdapter:
    from watari_cli import chatwork

    return ServiceAdapter(
        label="Chatwork", implemented=True,
        guide=[
            "1. Sign in to Chatwork, then open:",
            "   https://www.chatwork.com/service/packages/chatwork/subpackages/api/token.php",
            "   Menu path: account menu > 'Service integration' > 'API' > 'API Token'",
            "2. Enter your login password to display the API token",
            "3. Click 'Copy', then paste the token here",
            "Note: on organization plans, an administrator may need to enable API access",
        ],
        verify=chatwork.verify, read=chatwork.read,
    )


def _obsidian_adapter() -> ServiceAdapter:
    from watari_cli import obsidian

    return ServiceAdapter(
        label=obsidian.LABEL, implemented=True, auth_kind="local", scope="local",
        connected=obsidian.is_connected,
        guide=[
            "Watari imports Markdown notes using read-only access limited to the selected vault",
            "No authentication is required; existing Obsidian settings are migrated automatically",
            "If no vault is found, Watari will ask for the vault folder path",
            "Watari excludes .obsidian, hidden folders, Journal/Watari, and symbolic links",
        ],
        verify=obsidian.verify, read=obsidian.read,
    )


def _claude_code_adapter() -> ServiceAdapter:
    from watari_cli.transcripts import claude_code as cc

    return ServiceAdapter(
        label=cc.LABEL, implemented=True, auth_kind="local", scope="local",
        connected=cc.is_connected,
        guide=[
            "Connect Claude Code to let Watari use those conversations as memory context; "
            "if you do not use Claude Code, this connection is not needed",
            "No authentication is required; Watari looks for logs in ~/.claude/projects",
            "If no logs are found, Watari will ask for the log folder path",
        ],
        verify=cc.verify, read=cc.read,
    )


def _codex_adapter() -> ServiceAdapter:
    from watari_cli.transcripts import codex

    return ServiceAdapter(
        label=codex.LABEL, implemented=True, auth_kind="local", scope="local",
        connected=codex.is_connected,
        guide=[
            "Connect Codex to let Watari use those conversations as memory context; "
            "if you do not use Codex, this connection is not needed",
            "No authentication is required; Watari looks for logs in ~/.codex/sessions",
            "If no logs are found, Watari will ask for the log folder path",
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


def is_configured(name: str) -> bool:
    """読み取りを試せるだけの認証設定が保存されているか。外部サービスへは接続しない。"""
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


def is_connected(name: str) -> bool:
    """現在利用できる接続か。表示用なので、対応サービスでは実 API まで確認する。"""
    service = get_service(name)
    if service is None or not is_configured(name):
        return False
    if service.available is not None:
        return service.available()
    if service.auth_kind == "oauth" and service.connected is None:
        from watari_cli import cloud

        return cloud.has_live_authorization()
    return True


def brief(name: str, now) -> list[dict]:
    """Read current actionable state without touching connector/memory cursors."""
    service = get_service(name)
    if service is None or service.brief is None:
        return []
    if not is_configured(name):
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
        if not is_configured(name):
            raise ConnectorError(f"{name} は未接続です（接続するには: watari connect {name}）")
        return service.read(since)
    api_key = auth_key(name)
    if not api_key:
        raise ConnectorError(f"{name} は未接続です（接続するには: watari connect {name}）")
    return service.read(api_key, since)
