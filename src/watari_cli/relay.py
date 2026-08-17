"""watari chat の中継スレッド：ローカル Pi transcript → クラウド発話置き場。

watari chat は Pi の親プロセス。会話中、背景スレッドがローカル session ファイルをバイトオフセットで
tail し、user＋assistant の発話テキストだけ（tool 出力・thinking は除く）を JSONL 1 行に整形して
クラウドのマシン別ファイルへ追記する。＝別マシンの夢がこの会話を読めるようにする素材の中継。

- 発火は数秒ポーリング（zero-dep で移植性優先。実質ターン終了時に送信になる粒度）。
- 送信失敗（offline 等）はローカルキューに繰り越し、次の tick か次回 chat で再送。
- 終了時（正常/SIGINT は finally、SIGTERM はハンドラ）に最終 flush。
- Google連携が完全未設定なら start() は何もしない。設定済みなのに実接続できない場合は即時警告し、
  発話をローカルキューへ残して再認証後の次回chatで再送する。

抽出のバイトオフセット・再送キューはローカル状態（XDG_STATE_HOME/watari、非同期・マシン固有）。
"""
from __future__ import annotations

import glob
import json
import os
import sys
import threading

from watari_cli import cloud

# 送信キューがこの大きさを超えたら「同期が滞っている」として1行警告する
QUEUE_WARN_BYTES = 10 * 1024 * 1024


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


def _pi_cursor_epoch(home):
    """dream の transcripts_pi カーソルを epoch 秒で返す（無ければ None）。初見ファイルの取捨に使う。"""
    if not home:
        return None
    try:
        from watari_cli import host
        from watari_cli.engine.watari_lib import parse_ts
        cur = host.load_cursors(home).get("transcripts_pi")
        return parse_ts(cur).timestamp() if cur else None
    except Exception:
        return None


class Relay:
    """1 マシン分の中継。cmd_chat が start()→(Pi 実行)→stop_and_flush() で使う。"""

    def __init__(self, pi_store: str, machine_id: str, home: str | None = None,
                 poll_interval: float = 3.0):
        self.pi_store = pi_store
        self.machine_id = machine_id
        self.cloud_name = f"transcripts-{machine_id}.jsonl"
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._store: cloud.CloudStore | None = None
        self._enabled = False  # Google連携を設定した利用者だけローカルキューを使う
        self._warned_sync_failure = False
        self._offsets = _load_offsets()
        self._meta: dict[str, dict] = {}  # path -> {"cwd", "session"}
        self._pi_cursor = _pi_cursor_epoch(home)  # 初見ファイルの「夢見済み」判定用

    # --- ライフサイクル ---
    def start(self) -> None:
        if not cloud.is_configured():
            return  # 完全未設定（同期を使っていない）は無言で中継しない
        self._enabled = True
        if cloud.has_live_authorization():
            self._store = cloud.get_store()
        if self._store is None:
            # 保存値の存在だけでなくtoken実交換に失敗した場合も即時に知らせる。送れない間も
            # transcript抽出は続け、再認証後に送れるようローカルキューへ残す。
            self._warn_sync_failure()
        self._warn_if_queue_large()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _warn_sync_failure(self) -> None:
        if self._warned_sync_failure:
            return
        print("! Googleとの接続が切れたため、このパソコンの会話を"
              "ほかのパソコンのワタリへ共有できません。\n"
              "  会話はこのパソコンに保存されるため、内容は失われません。\n"
              "  直すには、ターミナルで `watari auth` を実行してください。", file=sys.stderr)
        self._warned_sync_failure = True

    def _warn_if_queue_large(self) -> None:
        """送信できていないキューが肥大していたら1行警告する（会話は止めない）。"""
        try:
            size = os.path.getsize(_queue_path())
        except OSError:
            return
        if size > QUEUE_WARN_BYTES:
            mb = size / (1024 * 1024)
            print(f"! 送信できていない会話データが {mb:.0f}MB たまっています。"
                  "続く場合は watari auth でログインし直してください。", file=sys.stderr)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                pass  # 中継は会話を止めない——次の tick で再試行
            self._stop.wait(self.poll_interval)

    def stop_and_flush(self) -> None:
        if not self._enabled:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        try:
            self._tick()  # 送信不能でもPi終了直後の残り分をローカルキューへ拾う
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
        meta = {"cwd": None, "session": None}
        try:
            with open(path, encoding="utf-8") as f:
                first = f.readline()
            d = json.loads(first)
            if d.get("type") == "session":
                meta["cwd"] = d.get("cwd")
                meta["session"] = d.get("id")  # dream の dedup uuid をローカル(scan_pi_store)と揃える
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
            "session": meta.get("session"), "cwd": meta.get("cwd"),
            "role": m["role"], "text": text,
        }, ensure_ascii=False) + "\n"

    def _extract_new(self) -> list[str]:
        out: list[str] = []
        for path in sorted(glob.glob(os.path.join(self.pi_store, "**", "*.jsonl"), recursive=True)):
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if path not in self._offsets and self._pi_cursor is not None:
                # 初見ファイルが dream カーソル以前にしか書かれていない＝既に夢見済み（共有 log に蒸留済み）。
                # 過去履歴を丸ごとアップロードして他マシンで再判定させないよう、末尾から始める。
                try:
                    mtime = os.path.getmtime(path)
                except OSError:
                    mtime = None
                if mtime is not None and mtime < self._pi_cursor:
                    self._offsets[path] = size
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
        if not content or self._store is None:
            return
        try:
            self._store.append(self.cloud_name, content)
        except cloud.CloudError:
            self._warn_sync_failure()
            return  # 繰り越し（キューはそのまま・次回再送）
        open(_queue_path(), "w", encoding="utf-8").close()  # 送信成功 → キューを空に


def prune_cloud(home: str, days: int = 90) -> None:
    """クラウドの共有発話から「全マシンが夢に見た分」＋「days 超の古い分」を削除する（容量の頭打ち）。

    各マシンの cloud_<machine> カーソルは host record（カセット git 共有）にあるので、あるファイル
    transcripts-<M>.jsonl については **M 以外の全マシン**の cloud_<M> カーソルの最小で「全員が読んだ
    位置」を求め、それ以前を削る。まだ読んでいないマシンがあれば days の保険だけが効く（取りこぼさない）。
    未認証/未接続や個々の失敗は握りつぶす（ベストエフォート）。
    """
    store = cloud.get_store()
    if store is None:
        return
    try:
        files = store.list()
    except cloud.CloudError:
        return
    from datetime import timedelta

    from watari_cli import host
    from watari_cli.engine.watari_lib import now_utc, parse_ts

    hosts = host.all_hosts(home)
    cutoff = now_utc() - timedelta(days=days)
    for f in files:
        name = f.get("name", "")
        if not (name.startswith("transcripts-") and name.endswith(".jsonl")):
            continue
        machine = name[len("transcripts-"):-len(".jsonl")]
        mt = f.get("modifiedTime")
        if mt:
            try:
                if parse_ts(mt) > now_utc() - timedelta(minutes=10):
                    continue  # 直近更新＝発話元が追記中かも。read-modify-write の競合で未消化分を消さない
            except (ValueError, TypeError):
                pass
        key = f"cloud_{machine}"
        curs = [(h.get("cursors") or {}).get(key) for h in hosts
                if h.get("machine_id") != machine]  # M 自身は自分の cloud を夢に見ない
        min_dreamed = None
        if curs and all(curs):
            try:
                min_dreamed = min(parse_ts(c) for c in curs)
            except (ValueError, TypeError):
                min_dreamed = None
        try:
            content = store.read(name)
        except cloud.CloudError:
            continue
        kept = []
        for raw in content.splitlines():
            try:
                tsp = parse_ts(json.loads(raw)["ts"])
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                kept.append(raw)  # 壊れ行は消さず残す
                continue
            if tsp < cutoff:
                continue  # days 超（保険）
            if min_dreamed and tsp <= min_dreamed:
                continue  # 全マシンが夢に見た
            kept.append(raw)
        new_content = ("\n".join(kept) + "\n") if kept else ""
        if new_content == content:
            continue
        try:
            if kept:
                store.write(name, new_content)
            else:
                store.delete(name)
        except cloud.CloudError:
            pass
