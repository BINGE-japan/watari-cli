"""transcript 系 connector（auth_kind="local"）が共有する薄い土台。

- config.json への置き場パスの保存/読み出し（connectors_auth.<name>.path）。
- 「既定の置き場を自動検出 → 見つかれば保存して完了 / 見つからなければパスの直接入力を
  促して検証・保存」という共通フロー（claude_code.py / codex.py の verify() が使う）。
- 統一形式への整形（since フィルタ・ts 昇順ソート・件数上限での打ち切り）。

サービス固有の検出規則・行のパース・（Codex の）リプレイ除去は各アダプタ側に閉じる。
"""
from __future__ import annotations

import os

from watari_cli import config, prompts

# 1回の read で返す行数の上限（他の組み込みコネクタと同じ「1回で取り切らない」設計）。
MAX_ROWS = 500


def _auth_root() -> dict:
    section = config.load_config().get("connectors_auth")
    return dict(section) if isinstance(section, dict) else {}


def auth_section(name: str) -> dict:
    """connectors_auth.<name> を返す（無ければ空 dict）。"""
    sub = _auth_root().get(name)
    return dict(sub) if isinstance(sub, dict) else {}


def save_path(name: str, path: str) -> None:
    """検出/入力されたログ置き場パスを connectors_auth.<name>.path へ保存する。"""
    root = _auth_root()
    section = dict(root.get(name) or {})
    section["path"] = path
    root[name] = section
    config.save_config(connectors_auth=root)


def configured_path(name: str) -> str | None:
    """保存済みのログ置き場パス（未接続なら None）。read() はこれを既定の探索先として使う。"""
    return auth_section(name).get("path")


def is_connected(name: str) -> bool:
    return bool(configured_path(name))


def detect_or_prompt(name: str, label: str, default_root, count_sessions) -> tuple[bool, str]:
    """「既定の置き場を自動検出 → 保存」または「見つからなければパスを聞いて検証 → 保存」。

    default_root: () -> str（既定のログ置き場）。count_sessions: (root: str) -> int
    （そのディレクトリ配下のセッション数。0 なら「ログが無い」扱い）。
    成功時は (True, "<label> の会話ログを見つけました（<path> / セッション <n> 件）") 等の
    ユーザー向け完了メッセージ、失敗時は (False, 理由)。
    """
    root = default_root()
    if os.path.isdir(root):
        count = count_sessions(root)
        if count > 0:
            save_path(name, root)
            return True, f"{label} の会話ログを見つけました（{root} / セッション {count} 件）"

    print(f"{label} の会話ログが既定の場所（{root}）に見つかりませんでした。")
    entered = prompts.text("会話ログが入っているディレクトリのパスを直接入力しますか？（空で中止）")
    if not entered:
        return False, f"{label}: パスが入力されなかったため中止しました"
    entered = os.path.abspath(os.path.expanduser(entered))
    if not os.path.isdir(entered):
        return False, f"{entered} はディレクトリではありません"
    count = count_sessions(entered)
    if count == 0:
        return False, f"{entered} にセッションが見つかりませんでした"
    save_path(name, entered)
    return True, f"{label} の会話ログ（{entered} / セッション {count} 件）"


def unify(rows: list[dict], since: str | None, max_rows: int = MAX_ROWS) -> list[dict]:
    """since より新しい行だけを ts 昇順（同時刻は uuid）に揃え、上限で打ち切る。

    row は {ts, uuid, text, meta, role} の統一形式（role は "user"|"assistant"）。
    """
    if since:
        rows = [r for r in rows if r["ts"] > since]
    rows = sorted(rows, key=lambda r: (r["ts"], r["uuid"]))
    return rows[:max_rows]
