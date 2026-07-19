"""watari chat の中継スレッド：ローカル Pi transcript → クラウド発話置き場。

watari chat は Pi の親プロセス。会話中、背景スレッドがローカル session ファイルをバイトオフセットで
tail し、user＋assistant の発話テキストだけ（tool 出力・thinking は除く）を JSONL 1 行に整形して
クラウドのマシン別ファイルへ追記する。＝別マシンの夢がこの会話を読めるようにする素材の中継。

- 発火は数秒ポーリング（zero-dep で移植性優先。実質ターン終了時に送信になる粒度）。
- 送信失敗（offline 等）はローカルキューに繰り越し、次の tick か次回 chat で再送。
- 終了時（正常/SIGINT は finally、SIGTERM はハンドラ）に最終 flush。
- クラウド未認証なら start() は何もしない＝ローカルのみで普通に動く。

抽出のバイトオフセット・再送キューはローカル状態（XDG_STATE_HOME/watari、非同期・マシン固有）。
"""
from __future__ import annotations

import glob
import json
import os
import threading

from watari_cli import cloud


def _state_dir() -> str:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    d = os.path.join(base, "watari")
    os.makedirs(d, exist_ok=True)
    return d


def _offsets_path() -> str:
    return os.path.join(_state_dir(), "relay-offsets.json")


def _queue_path() -> str:
    return os.path.join(_state_dir(), "relay-queue.jsonl")


def _load_offsets() -> dict:
    try:
        with open(_offsets_path(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_offsets(offsets: dict) -> None:
    tmp = _offsets_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(offsets, f)
    os.replace(tmp, _offsets_path())


def _message_text(message: dict) -> str:
    """user/assistant メッセージの本文テキストだけを取り出す（thinking・toolcall・image は除外）。"""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content
                       if isinstance(b, dict) and b.get("type") == "text")
    return ""


class Relay:
    """1 マシン分の中継。cmd_chat が start()→(Pi 実行)→stop_and_flush() で使う。"""

    def __init__(self, pi_store: str, machine_id: str, poll_interval: float = 3.0):
        self.pi_store = pi_store
        self.machine_id = machine_id
        self.cloud_name = f"transcripts-{machine_id}.jsonl"
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._store: cloud.CloudStore | None = None
        self._offsets = _load_offsets()
        self._meta: dict[str, dict] = {}  # path -> {"cwd": ...}

    # --- ライフサイクル ---
    def start(self) -> None:
        self._store = cloud.get_store()
        if self._store is None:
            return  # 未認証 → 中継しない
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                pass  # 中継は会話を止めない——次の tick で再試行
            self._stop.wait(self.poll_interval)

    def stop_and_flush(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        if self._store is not None:
            try:
                self._tick()  # Pi 終了直後の残り分を拾って送る
            except Exception:
                pass

    # --- 1 tick: 抽出 → キュー → 送信 ---
    def _tick(self) -> None:
        new = self._extract_new()
        if new:
            with open(_queue_path(), "a", encoding="utf-8") as f:
                f.write("".join(new))
        self._flush()

    def _header_meta(self, path: str) -> dict:
        if path in self._meta:
            return self._meta[path]
        meta = {"cwd": None}
        try:
            with open(path, encoding="utf-8") as f:
                first = f.readline()
            d = json.loads(first)
            if d.get("type") == "session":
                meta["cwd"] = d.get("cwd")
        except (OSError, json.JSONDecodeError):
            pass
        self._meta[path] = meta
        return meta

    def _to_line(self, raw: str, meta: dict) -> str | None:
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if d.get("type") != "message":
            return None
        m = d.get("message")
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            return None
        text = _message_text(m)
        if not text.strip():
            return None
        return json.dumps({
            "ts": d.get("timestamp"), "turn_id": d.get("id"), "machine": self.machine_id,
            "cwd": meta.get("cwd"), "role": m["role"], "text": text,
        }, ensure_ascii=False) + "\n"

    def _extract_new(self) -> list[str]:
        out: list[str] = []
        for path in sorted(glob.glob(os.path.join(self.pi_store, "**", "*.jsonl"), recursive=True)):
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            offset = self._offsets.get(path, 0)
            if size <= offset:
                continue
            meta = self._header_meta(path)
            try:
                with open(path, "rb") as f:
                    f.seek(offset)
                    chunk = f.read()
            except OSError:
                continue
            nl = chunk.rfind(b"\n")
            if nl < 0:
                continue  # まだ完全な行が無い（ライブ追記の途中）
            self._offsets[path] = offset + nl + 1
            for raw in chunk[:nl + 1].decode("utf-8", "replace").splitlines():
                line = self._to_line(raw, meta)
                if line:
                    out.append(line)
        _save_offsets(self._offsets)
        return out

    def _flush(self) -> None:
        try:
            with open(_queue_path(), encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            return
        if not content:
            return
        try:
            self._store.append(self.cloud_name, content)
        except cloud.CloudError:
            return  # 繰り越し（キューはそのまま・次回再送）
        open(_queue_path(), "w", encoding="utf-8").close()  # 送信成功 → キューを空に
