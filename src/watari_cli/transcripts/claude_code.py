"""Claude Code の会話ログ connector（組み込み・scope="local"・認証不要）。

置き場: `~/.claude/projects/<project-slug>/<session-uuid>.jsonl`（Windows/WSL 混在環境では
複数あり得るが、まずは `~/.claude/projects` を既定にする。見つからない/別マシンに移した場合は
`watari connect claude-code` がパスの直接入力を促す）。

**本物のユーザー発話の条件（検証済みの事実。変えないこと）**：次を全て満たす行だけを拾う。
- `type == "user"`
- `message.content` が**文字列**（配列は tool_result なので除外）
- `toolUseResult` キーを持たない
- `isMeta` / `isCompactSummary` / `isSidechain` のいずれも真でない
- `timestamp` を持つ
- 内容に `<command-name>` `<local-command-stdout>` `<task-notification>` `<system-reminder>`
  `<scheduled-task` のいずれも含まない（スラッシュコマンド実行結果・システム通知等の合成行）

assistant 行も文脈用に拾う（`type == "assistant"`、`message.content` 配列の `type=="text"`
ブロックのテキストのみ。thinking/tool_use は除外）。サブエージェント(`isSidechain`)は
ユーザー本人の発話ではないため user/assistant どちらでも除外する
（SCHEMA.md「サブエージェント(isSidechain)・ツール出力・メタ行は無視する」と同じ原則）。

行の `uuid` は各行の `uuid` フィールド、`ts` は `timestamp`、`cwd` は `cwd`。dedup 鍵は
`claude-code:<uuid>`（他コネクタの `<source>:<id>` 慣例と同じ）。
"""
from __future__ import annotations

import glob
import json
import os

from watari_cli.transcripts import common

NAME = "claude-code"
LABEL = "Claude Code"

SYNTHETIC_MARKERS = (
    "<command-name>", "<local-command-stdout>", "<task-notification>",
    "<system-reminder>", "<scheduled-task",
)


def default_root() -> str:
    return os.path.expanduser("~/.claude/projects")


def _iter_session_files(root: str) -> list[str]:
    return sorted(glob.glob(os.path.join(root, "*", "*.jsonl")))


def count_sessions(root: str) -> int:
    return len(_iter_session_files(root))


def _user_text(d: dict) -> str | None:
    if d.get("type") != "user":
        return None
    if "toolUseResult" in d:
        return None
    if d.get("isMeta") or d.get("isCompactSummary") or d.get("isSidechain"):
        return None
    message = d.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, str):
        return None
    if any(marker in content for marker in SYNTHETIC_MARKERS):
        return None
    text = content.strip()
    return text or None


def _assistant_text(d: dict) -> str | None:
    if d.get("type") != "assistant":
        return None
    if d.get("isSidechain"):
        return None
    message = d.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, list):
        return None
    parts = [block.get("text") for block in content
             if isinstance(block, dict) and block.get("type") == "text" and block.get("text")]
    text = "\n".join(p for p in parts if p).strip()
    return text or None


def _row_from_line(d: dict, session: str) -> dict | None:
    ts = d.get("timestamp")
    if not ts:
        return None
    uuid = d.get("uuid")
    if not uuid:
        return None
    text = _user_text(d)
    role = "user"
    if text is None:
        text = _assistant_text(d)
        role = "assistant"
    if not text:
        return None
    return {
        "ts": ts,
        "uuid": f"{NAME}:{uuid}",
        "text": text,
        "meta": {"cwd": d.get("cwd"), "session": session},
        "role": role,
    }


def _rows_from_file(path: str) -> list[dict]:
    session = os.path.splitext(os.path.basename(path))[0]
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                row = _row_from_line(d, session)
                if row is not None:
                    rows.append(row)
    except OSError:
        return []
    return rows


def is_connected() -> bool:
    return common.is_connected(NAME)


def verify() -> tuple[bool, str]:
    """既定の置き場を自動検出→保存、無ければパス入力を促して検証→保存（`common.detect_or_prompt`）。"""
    return common.detect_or_prompt(NAME, LABEL, default_root, count_sessions)


def read(since: str | None) -> list[dict]:
    """カーソル(since)以降の本物の発話を統一形式 [{ts,uuid,text,meta,role}, ...] で ts 昇順に返す。

    role は "user"（記憶の根拠にしてよい）/ "assistant"（文脈用。根拠にはしない）。
    1回の呼び出しで最大 `common.MAX_ROWS`（500）行までで打ち切る（超過分は次回以降に回る）。
    """
    root = common.configured_path(NAME) or default_root()
    rows: list[dict] = []
    for path in _iter_session_files(root):
        rows.extend(_rows_from_file(path))
    return common.unify(rows, since)
