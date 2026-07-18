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

    自動検出の基本情報だけを更新し、自由記述の facts は消さずに引き継ぐ。
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
