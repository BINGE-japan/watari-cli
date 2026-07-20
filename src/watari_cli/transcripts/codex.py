"""Codex CLI の会話ログ connector（組み込み・scope="local"・認証不要）。

置き場: `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`。1ファイル(=1セッション)は JSONL で、
`session_meta` 行（session id・cwd を持つ）を挟みながら `event_msg` 行が並ぶ。**`session_meta` は
1ファイルに複数回現れうる**（セッションが分岐・再開されると cwd/session が切り替わる）ため、
ファイルを先頭から順に読みながら都度更新する（最初の1回だけ拾って固定しない）。

本物のユーザー発話は `type == "event_msg"` かつ `payload.type == "user_message"`（本文は
`payload.message`）。assistant は `payload.type == "agent_message"`（本文は同じく `payload.message`）。

## 最重要（検証済みの実バグ。変えないこと）
Codex はセッションを再開・分岐するたびに、**過去の全発話を新しい session id と新しい
timestamp で丸ごと書き直す**。素直に読むと同じ会話が何度も取り込まれる（実測で総発話 3565 件中
2433 件が再記録だった）。対策：
1. セッション（＝ファイル）を **(そのファイル内で最初に現れる発話の ts, ファイルパス)** で
   決定的に順序付ける。
2. 古い順に処理しながら、**(cwd, role, text) の組**をグローバルな「既出集合」に積み上げる。
3. 各ファイルは**先頭から連続して**既出集合に一致する発話が続く限り「リプレイ（再記録）」と
   判定して捨てる。**一致しない発話（novel）が現れた時点でそのファイルの以降は全て残す**
   （novel 以降に同文が再登場しても捨てない＝「続けて」等の言い直しを守るため）。

この「先頭からの連続一致だけを捨てる」プレフィックス判定が肝で、ファイル全体を既出集合と
突き合わせて間引くわけではない（それだと言い直しまで消えてしまう）。
"""
from __future__ import annotations

import glob
import json
import os

from watari_cli.transcripts import common

NAME = "codex"
LABEL = "Codex"

# 未処理時点の「最初の発話 ts」ソート用の番兵（発話0件のファイルは並び替えで最後方に置く。
# 実データ中には現れない形式にしてあるだけで、それ自体が意味を持つ日時ではない）。
_NO_MESSAGE_SENTINEL = "9999-12-31T23:59:59.999Z"


def default_root() -> str:
    return os.path.expanduser("~/.codex/sessions")


def _iter_session_files(root: str) -> list[str]:
    return sorted(glob.glob(os.path.join(root, "*", "*", "*", "rollout-*.jsonl")))


def count_sessions(root: str) -> int:
    return len(_iter_session_files(root))


def _session_meta_fields(d: dict) -> tuple[str | None, str | None]:
    payload = d.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    session_id = payload.get("id") or payload.get("session_id") or d.get("id")
    cwd = payload.get("cwd") or d.get("cwd")
    return session_id, cwd


def _event_role_text(d: dict) -> tuple[str | None, str | None]:
    payload = d.get("payload")
    if not isinstance(payload, dict):
        return None, None
    ptype = payload.get("type")
    if ptype == "user_message":
        role = "user"
    elif ptype == "agent_message":
        role = "assistant"
    else:
        return None, None
    text = payload.get("message")
    if not isinstance(text, str) or not text.strip():
        return None, None
    return role, text.strip()


def _parse_file(path: str) -> list[dict]:
    """1ファイルを先頭から読み、event_msg 行を記録として返す（session_meta は逐次反映）。

    各記録: {"ts","role","text","cwd","session","index"}（index はファイル内の行番号・dedup 鍵用）。
    """
    records: list[dict] = []
    session_id: str | None = None
    cwd: str | None = None
    try:
        with open(path, encoding="utf-8") as f:
            for index, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("type") == "session_meta":
                    sid, c = _session_meta_fields(d)
                    if sid:
                        session_id = sid
                    if c:
                        cwd = c
                    continue
                if d.get("type") != "event_msg":
                    continue
                ts = d.get("timestamp")
                if not ts:
                    continue
                role, text = _event_role_text(d)
                if role is None:
                    continue
                records.append({
                    "ts": ts, "role": role, "text": text, "cwd": cwd,
                    "session": session_id, "index": index,
                })
    except OSError:
        return []
    return records


def _sorted_sessions(root: str) -> list[tuple[str, list[dict]]]:
    """(path, records) を (最初の発話 ts, path) 昇順に並べる（リプレイ除去の処理順）。"""
    sessions = [(path, _parse_file(path)) for path in _iter_session_files(root)]

    def sort_key(item: tuple[str, list[dict]]):
        path, records = item
        first_ts = records[0]["ts"] if records else _NO_MESSAGE_SENTINEL
        return (first_ts, path)

    sessions.sort(key=sort_key)
    return sessions


def _drop_replays(sessions: list[tuple[str, list[dict]]]) -> list[dict]:
    """古い順のセッション群から、各ファイル先頭の「既出プレフィックス」を間引いて残りを返す。

    「既出」はグローバルな (cwd, role, text) 集合で判定する。ファイル内で一致しない発話
    （novel）に達したら、そのファイルの残りは既出であっても全て残す（言い直しを守るため）。
    """
    seen: set[tuple[str | None, str, str]] = set()
    kept: list[dict] = []
    for _path, records in sessions:
        consuming_replay = True
        for rec in records:
            key = (rec["cwd"], rec["role"], rec["text"])
            if consuming_replay and key in seen:
                continue  # 既出セッションのプレフィックスの再記録＝リプレイとして捨てる
            consuming_replay = False
            seen.add(key)
            kept.append(rec)
    return kept


def is_connected() -> bool:
    return common.is_connected(NAME)


def verify() -> tuple[bool, str]:
    """既定の置き場を自動検出→保存、無ければパス入力を促して検証→保存（`common.detect_or_prompt`）。"""
    return common.detect_or_prompt(NAME, LABEL, default_root, count_sessions)


def read(since: str | None) -> list[dict]:
    """カーソル(since)以降の本物の発話を統一形式 [{ts,uuid,text,meta,role}, ...] で ts 昇順に返す。

    role は "user"（記憶の根拠にしてよい）/ "assistant"（文脈用。根拠にはしない）。リプレイ
    （セッション再開時の過去発話の丸ごと再記録）は `_drop_replays` で除去してから since で絞る
    （since だけでは、リプレイが新しい timestamp を持つため取り除けない）。1回の呼び出しで
    最大 `common.MAX_ROWS`（500）行までで打ち切る（超過分は次回以降に回る）。
    """
    root = common.configured_path(NAME) or default_root()
    sessions = _sorted_sessions(root)
    kept = _drop_replays(sessions)
    rows = [{
        "ts": rec["ts"],
        "uuid": f"{NAME}:{rec['session'] or 'unknown'}:{rec['index']}",
        "text": rec["text"],
        "meta": {"cwd": rec["cwd"], "session": rec["session"]},
        "role": rec["role"],
    } for rec in kept]
    return common.unify(rows, since)
