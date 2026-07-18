"""マシンごとの環境記録（host record）。

ワタリはどのマシンからでも「各マシンの環境」を読めるべき。マシン名で名前空間を
切ったファイルを記憶ディレクトリ内（<home>/hosts/<machine_id>.json）に置く。git で
同期され、各マシンは自分のファイルだけを書くので衝突しない。自動検出の基本情報と、
自由記述の facts（例 {"terminal": "Ghostty"}）を1レコードに持たせる。
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket

from watari_cli.engine import watari_lib as wl

# 存在すれば ai_clis に載せる AI CLI（自動検出のみ・これ以上は増やさない）
AI_CLIS = ("claude", "codex", "pi")

# 取り込みカーソルのキー（このマシンの host 記録の "cursors" に格納。空の既定は全て None）。
# 記憶（WATARI_HOME）は git で全マシン共有されるため、カーソルは共有 cursors.json ではなく
# マシンごとの host 記録に持つ（各マシンは自分のファイルだけ書くので衝突しない）。
CURSOR_KEYS = (
    "transcripts_win", "transcripts_wsl", "transcripts_codex",
    "slack", "gmail", "calendar", "linear", "obsidian", "last_run",
)


def machine_id() -> str:
    """このマシンの安定した（乱数を使わない）ファイル名安全なスラッグ。"""
    raw = f"{platform.system().lower()}-{socket.gethostname()}"
    slug = re.sub(r"[^a-z0-9-]+", "-", raw.lower()).strip("-")
    return slug or "unknown"


def host_path(home: str) -> str:
    """このマシンの host ファイルのパス（<home>/hosts/<machine_id>.json）。"""
    return os.path.join(home, "hosts", f"{machine_id()}.json")


def _read(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def refresh(home: str) -> dict:
    """このマシンの host ファイルを最新化して返す。

    自動検出の基本情報だけを更新し、自由記述の facts と取り込みカーソル(cursors)は
    消さずに引き継ぐ（cmd_host のような読み取り専用ビューがこれを呼ぶだけで
    save_cursors 済みのカーソルを消してしまわないよう、facts と全く同じ扱いにする）。
    """
    existing = _read(host_path(home)) or {}
    facts = existing.get("facts")
    if not isinstance(facts, dict):
        facts = {}
    record = {
        "machine_id": machine_id(),
        "hostname": socket.gethostname(),
        "platform": platform.system(),
        "python": platform.python_version(),
        "ai_clis": [name for name in AI_CLIS if shutil.which(name)],
        "shell": os.path.basename(os.environ.get("SHELL") or ""),
        "facts": facts,
        "updated": wl.fmt_ts(wl.now_utc()),
    }
    cursors = existing.get("cursors")
    if isinstance(cursors, dict):
        record["cursors"] = cursors
    path = host_path(home)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wl.atomic_write_json(path, record)
    return record


def set_fact(home: str, key: str, value) -> dict:
    """自由記述の事実を1つ記録する（自動情報も最新化して書き戻す）。"""
    record = refresh(home)
    record["facts"][key] = value
    wl.atomic_write_json(host_path(home), record)
    return record


def save_cursors(home: str, cursors: dict) -> dict:
    """このマシンの host 記録に取り込みカーソルを書き込む（自動情報を最新化し facts は保つ）。"""
    record = refresh(home)
    record["cursors"] = cursors
    wl.atomic_write_json(host_path(home), record)
    return record


def load_cursors(home: str) -> dict:
    """このマシンの取り込みカーソルを返す（host 記録の "cursors"）。読むだけで書かない。

    host 記録に "cursors" があればそれを返す。無く旧 <home>/cursors.json があれば、その
    位置を**メモリ上で**引き継いで返すだけで、ここでは host 記録へ書き込まない。永続化は
    実際に前進が起きたとき（save_cursors）に行う——status / dream / ingest --dry-run のような
    読み取り専用パスが副作用を持たない契約を守るため。既存のカーソル位置（checkpoint）は、
    次の save_cursors がこの戻り値を丸ごと書き戻すので失われない。cursors.json はリポ外の旧
    ルーティンがまだ読むので消さずに残す。どちらも無ければ全キー None の既定を返す。
    """
    record = _read(host_path(home))
    if record and isinstance(record.get("cursors"), dict):
        return record["cursors"]
    legacy = _read(os.path.join(home, "cursors.json"))
    if isinstance(legacy, dict):
        return legacy  # メモリ上で引き継ぐだけ（永続化は最初の save_cursors が担う）
    return {key: None for key in CURSOR_KEYS}


def all_hosts(home: str) -> list:
    """<home>/hosts/*.json を全て読み、各マシンの記録を返す。"""
    out = []
    directory = os.path.join(home, "hosts")
    if not os.path.isdir(directory):
        return out
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"):
            continue
        record = _read(os.path.join(directory, name))
        if record is not None:
            out.append(record)
    return out
