#!/usr/bin/env python3
"""カーソル以降の「本物のユーザー発話」を両ストアから決定的に抽出する。

出力(JSON, stdout):
{
  "generated": ts,
  "stores": {"win": {"cursor":.., "readable":bool, "count":n, "max_ts":..|null, "truncated":bool}, "wsl": {...}, "codex": {...}},
  "messages": [{"store","ts","session","uuid","cwd","file","text"}, ...]  # ts 昇順（win/wsl=Claude, codex=Codex）
}

- ストアが読めない回はそのストアを readable:false とし、カーソルは前進させない
  （呼び出し側は max_ts が null のストアのカーソルを触らないこと）。
- 上限は SCHEMA どおり: 件数 300000 または「最古の未処理メッセージから30日ぶん」の小さい方。
  超過分は truncated:true とし、max_ts は「実際に出力した最後の ts」。
"""
import glob
import json
import os
from datetime import timedelta

from .watari_lib import (
    CODEX_STORE, INGEST_MAX_MESSAGES, INGEST_MAX_WINDOW_DAYS, STORES,
    fmt_ts, is_genuine_codex_user_message, is_genuine_user_message,
    load_cursors, now_utc, parse_ts,
)


def scan_store(root, cursor_iso):
    """1ストアを走査。(readable, messages) を返す。
    ファイル1件でも読めなかった回は readable=False を返す（呼び出し側はそのストアの
    カーソルを前進させない＝未読ファイルを飛び越えて取りこぼす事故を防ぐ。SCHEMA『WSL が
    読めない回は前進させずスキップ』をファイル粒度で満たす）。"""
    if not os.path.isdir(root):
        return False, []
    cursor = parse_ts(cursor_iso) if cursor_iso else None
    out = []
    ok = True
    for path in sorted(glob.glob(os.path.join(root, "*", "*.jsonl"))):
        # サブエージェント等の入れ子は対象外（projects/<proj>/<session>.jsonl 直下のみ）
        try:
            if cursor and os.path.getmtime(path) < cursor.timestamp() - 120:
                continue  # カーソル以前にしか書かれていないファイルは読まない
            f = open(path, encoding="utf-8")
        except OSError:
            ok = False  # stat/open に失敗したファイルがある→このストアは前進させない
            continue
        try:
            with f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not is_genuine_user_message(d):
                        continue
                    try:
                        ts = parse_ts(d["timestamp"])
                    except (ValueError, KeyError):
                        continue  # 不正な ts の1行はスキップ（ここで前進を止めると停滞するため）
                    if cursor and ts <= cursor:
                        continue
                    out.append({
                        "ts": d["timestamp"],
                        "session": d.get("sessionId") or os.path.basename(path)[:-6],
                        "uuid": d.get("uuid"),
                        "cwd": d.get("cwd"),
                        "file": path,
                        "text": d["message"]["content"],
                    })
        except (OSError, UnicodeDecodeError):
            # ライブ追記中のファイルが多バイト文字の途中で切れていると for line in f が
            # UnicodeDecodeError を投げる。extract 全体を落とさず、このストアは前進させない
            # （＝一時的な切断は次回自己回復。カーソルは無傷）。
            ok = False
            continue
    return ok, out


def scan_codex_store(root, cursor_iso):
    """Codex のセッション（<root>/YYYY/MM/DD/rollout-*.jsonl）を走査。(readable, messages) を返す。
    形式は Claude Code と違うが、出力の形は同じ（LLM 判定は source を問わず一様に扱える）。
    dedup 用の合成 uuid は codex:<session>:<ts>（Codex は per-message uuid を持たないため）。
    I/O 失敗時 readable=False、窓・停滞対策は scan_store と同じ思想。"""
    if not os.path.isdir(root):
        return False, []
    cursor = parse_ts(cursor_iso) if cursor_iso else None
    out = []
    ok = True
    for path in sorted(glob.glob(os.path.join(root, "*", "*", "*", "*.jsonl"))):
        try:
            if cursor and os.path.getmtime(path) < cursor.timestamp() - 120:
                continue
            f = open(path, encoding="utf-8")
        except OSError:
            ok = False
            continue
        try:
            session_id = os.path.basename(path)[:-6]
            cwd = None
            with f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if d.get("type") == "session_meta":
                        p = d.get("payload") or {}
                        session_id = p.get("id") or p.get("session_id") or session_id
                        cwd = p.get("cwd") or cwd
                        continue
                    if not is_genuine_codex_user_message(d):
                        continue
                    try:
                        ts = parse_ts(d["timestamp"])
                    except (ValueError, KeyError):
                        continue
                    if cursor and ts <= cursor:
                        continue
                    out.append({
                        "ts": d["timestamp"],
                        "session": session_id,
                        "uuid": f"codex:{session_id}:{d['timestamp']}",
                        "cwd": cwd,
                        "file": path,
                        "text": d["payload"]["message"],
                    })
        except (OSError, UnicodeDecodeError):
            ok = False
            continue
    return ok, out


def run():
    """両ストアを走査して結果 dict を返す（副作用なし・読むだけ）。"""
    cursors = load_cursors()
    result = {"generated": fmt_ts(now_utc()), "stores": {}, "messages": []}
    # win/wsl は Claude Code 形式（scan_store）、codex は Codex 形式（scan_codex_store）。
    jobs = [
        ("win", "transcripts_win", scan_store, STORES["win"]),
        ("wsl", "transcripts_wsl", scan_store, STORES["wsl"]),
        ("codex", "transcripts_codex", scan_codex_store, CODEX_STORE),
    ]
    for store, cursor_key, scanner, root in jobs:
        cursor_iso = cursors.get(cursor_key)
        readable, msgs = scanner(root, cursor_iso)
        msgs.sort(key=lambda m: (m["ts"], m["uuid"] or ""))
        truncated = False
        if msgs:
            # 窓の起点は必ず「最古の未処理メッセージ」。カーソル固定にすると、カーソル以降30日超の
            # 空白後に発話が再開したとき窓が全件より手前に落ち、kept=[]・max_ts=null でカーソルが
            # 永久停滞し、90日で消える発話を取りこぼす。起点を msgs[0] にすれば必ず1件は残る。
            window_end = parse_ts(msgs[0]["ts"]) + timedelta(days=INGEST_MAX_WINDOW_DAYS)
            kept = [m for m in msgs if parse_ts(m["ts"]) <= window_end][:INGEST_MAX_MESSAGES]
            truncated = len(kept) < len(msgs)
            msgs = kept
        for m in msgs:
            m["store"] = store
        result["stores"][store] = {
            "cursor": cursor_iso,
            "readable": readable,
            "count": len(msgs),
            "max_ts": msgs[-1]["ts"] if msgs else None,
            "truncated": truncated,
        }
        result["messages"].extend(msgs)
    result["messages"].sort(key=lambda m: (m["ts"], m["uuid"] or ""))
    return result


def main():
    print(json.dumps(run(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
