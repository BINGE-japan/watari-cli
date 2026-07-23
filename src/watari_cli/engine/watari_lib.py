#!/usr/bin/env python3
"""ワタリ記憶の共有ライブラリ（パス・時刻・log IO・発話選別）。

決定論部分の正本実装。仕様の「なぜ」は SCHEMA.md、ここは「どう」。

パス定数（記憶＝MEM、ソース＝PI_STORE）は環境変数(config)から注入する。未設定時の既定は
どのマシンでも動く標準の場所に解決する（記憶は XDG_DATA_HOME 配下、transcript ストアは Pi の
セッション ~/.pi/agent/sessions）。watari-cli の runtime は Pi なので、夢が読む唯一の組み込み
transcript は Pi。他の AI CLI・ツールは connector（ユーザー宣言）として渡す。通常は install が
保存した WATARI_HOME（config 経由）がこれらを上書きするので、既定はあくまで無設定時の受け皿。
"""
import json
import os
import re
from datetime import datetime, timezone

# 環境変数で上書き可。既定は標準の場所に一元化（通常は config 経由の WATARI_HOME が上書きする）。
MEM = os.environ.get("WATARI_HOME", os.path.join(
    os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "watari", "memory"))
# Pi のセッション（~/.pi/agent/sessions/<作業ディレクトリ>/*.jsonl）。watari chat は Pi を
# 起動するので、ワタリと話した内容はすべてここに残る＝夢が読む唯一の組み込み transcript ストア。
# 形式は Pi 独自 JSONL（下の is_genuine_pi_user_message 参照）。カーソルは transcripts_pi。
PI_STORE = os.environ.get("WATARI_STORE_PI", os.path.expanduser("~/.pi/agent/sessions"))
# transcript 以外のソース（他 AI CLI・メール・タスク・チャット等）は connector として扱う。
# カーソルキーは固定リストでなく、ユーザーが config に宣言した connector 名
# （config.load_connectors）が --advance-ext の許可名になる（ingest.py で検証）。
GENRES = ("life", "learning")
KIND_TO_GENRE = {"study": "learning", "fact": "life", "interest": "life", "thread": "life"}
DOMAIN_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# 未セットアップ（記憶フォルダ不在）のときの統一案内。engine の main と cli が共用する
# （どのコマンドから入っても同じ文言・traceback なし・exit 1 で案内する）。
MSG_SETUP_REQUIRED = "まだセットアップされていません。まず次を実行してください:\n  watari install"

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


def is_genuine_pi_user_message(d):
    """Pi セッションの1行が「本物のユーザー発話」か（SCHEMA『本物の発話の選別』の実装）。

    Pi は実ユーザー入力を type:"message" & message.role:"user" として残す。tool 結果は
    role:"toolResult"、bash 実行や注入は別 type（bashExecution / custom / custom_message / label
    等）に出るため、role だけで自然に選別できる（Claude のような type:"user" への tool 結果混入がない）。
    content は文字列でも、テキスト/画像ブロックの配列でもよい（判定側がそのまま読む）。"""
    if d.get("type") != "message":
        return False
    if not d.get("timestamp"):
        return False
    m = d.get("message")
    if not isinstance(m, dict) or m.get("role") != "user":
        return False
    return m.get("content") is not None
