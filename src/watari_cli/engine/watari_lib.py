#!/usr/bin/env python3
"""ワタリ記憶の共有ライブラリ（パス・時刻・log IO・発話選別）。

決定論部分の正本実装。仕様の「なぜ」は SCHEMA.md、ここは「どう」。

パス定数（記憶＝MEM、ソース＝STORES/CODEX_STORE）は環境変数(config)から注入する。
未設定時の既定はどのマシンでも動く標準の場所に解決する（記憶は XDG_DATA_HOME 配下、
transcript ストアは ~/.claude/projects と ~/.codex/sessions）。通常は install が保存した
WATARI_HOME（config 経由）がこれらを上書きするので、既定はあくまで無設定時の受け皿。
"""
import json
import os
import re
from datetime import datetime, timezone

# 環境変数で上書き可。既定は標準の場所に一元化（通常は config 経由の WATARI_HOME が上書きする）。
MEM = os.environ.get("WATARI_HOME", os.path.join(
    os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "watari", "memory"))
STORES = {
    # win は Windows/WSL 併用者向けのオプトイン。既定は空文字＝この store は無し
    # （scan_store は存在しないパスを readable=False で扱うので空既定でも安全）。
    "win": os.environ.get("WATARI_STORE_WIN", ""),
    "wsl": os.environ.get("WATARI_STORE_WSL", os.path.expanduser("~/.claude/projects")),
}
# Codex CLI のセッション（~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl）。
# Codex 側でワタリと話した内容も consolidate が拾えるようにする第3の transcript ストア。
# 形式は Claude Code と異なる（下の is_genuine_codex_user_message 参照）。カーソルは transcripts_codex。
CODEX_STORE = os.environ.get("WATARI_STORE_CODEX", os.path.expanduser("~/.codex/sessions"))
# 外部ソース(connector)のカーソルキーは固定リストではない。ユーザーが config に宣言した
# connector 名（config.load_connectors）が --advance-ext の許可名になる（ingest.py で検証）。
GENRES = ("life", "learning")
KIND_TO_GENRE = {"study": "learning", "fact": "life", "interest": "life", "thread": "life"}
DOMAIN_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# state 算出の定数（SCHEMA.md と一致させる）
HEAT_DECAY_DAYS = 30      # 30日ごとに heat が1下がる
DORMANT_DAYS = 45         # 45日更新が無い thread は dormant（声かけ待ち。印を付けて state に残す）
SINK_DAYS = 90            # 90日更新が無い thread は state から沈める（log には残り復元可能）
INGEST_MAX_MESSAGES = 300000
INGEST_MAX_WINDOW_DAYS = 30


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def fmt_ts(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def now_utc():
    return datetime.now(timezone.utc)


def log_path(genre):
    return os.path.join(MEM, genre, "log.jsonl")


def state_path(genre):
    return os.path.join(MEM, genre, "state.json")


def load_log(genre):
    rows = []
    with open(log_path(genre), encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            d["_line"] = n
            rows.append(d)
    return rows


def sorted_rows(rows):
    """ts 昇順・同時刻は uuid で安定順（決定論の要）。"""
    return sorted(rows, key=lambda d: (d["ts"], d.get("refs", {}).get("uuid") or ""))


def load_aliases():
    p = os.path.join(MEM, "learning", "aliases.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return {}


def load_cursors():
    # カーソルはマシンごとの host 記録に持つ（host.py が正本）。host は watari_lib を
    # import するため、循環を避けて遅延 import する。
    from watari_cli import host
    return host.load_cursors(MEM)


def atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def append_log(genre, rows):
    with open(log_path(genre), "a", encoding="utf-8") as f:
        for d in rows:
            d = {k: v for k, v in d.items() if not k.startswith("_")}
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


def existing_dedup_keys():
    """既存 log の (uuid, kind) 集合。"""
    keys = set()
    for g in GENRES:
        for d in load_log(g):
            u = d.get("refs", {}).get("uuid")
            if u:
                keys.add((u, d.get("kind")))
    return keys


def is_genuine_user_message(d):
    """transcript の1行が「本物のユーザー発話」か（SCHEMA『本物の発話の選別』の実装）。"""
    if d.get("type") != "user":
        return False
    if d.get("isSidechain") or d.get("isMeta") or d.get("isCompactSummary"):
        return False
    if "toolUseResult" in d:
        return False
    if not d.get("timestamp"):
        return False
    content = d.get("message", {}).get("content")
    if not isinstance(content, str):
        return False
    # ハーネス合成行（スラッシュコマンド・ローカル実行・タスク通知・スケジュール起動）を除外
    for marker in ("<command-name>", "<local-command-stdout>", "<task-notification>",
                   "<system-reminder>", "<scheduled-task"):
        if marker in content:
            return False
    return True


def is_genuine_codex_user_message(d):
    """Codex セッションの1行が「本物のユーザー発話」か。
    Codex はユーザーが実際に打った入力だけを event_msg / payload.type=user_message として残す
    （AGENTS.md 注入・<skill> 注入・環境コンテキストは response_item 側に出るため自然に除外される）。
    payload.message が発話本文。"""
    if d.get("type") != "event_msg":
        return False
    if not d.get("timestamp"):
        return False
    p = d.get("payload")
    if not isinstance(p, dict) or p.get("type") != "user_message":
        return False
    msg = p.get("message")
    return isinstance(msg, str) and bool(msg.strip())
