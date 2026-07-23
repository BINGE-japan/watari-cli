#!/usr/bin/env python3
"""カーソル以降の「本物のユーザー発話」を Pi ストアから決定的に抽出する。

出力(JSON, stdout):
{
  "generated": ts,
  "stores": {"pi": {"cursor":.., "readable":bool, "count":n, "max_ts":..|null, "truncated":bool}},
  "messages": [{"store","ts","session","uuid","cwd","file","text"}, ...]  # ts 昇順（store=pi）
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
    INGEST_MAX_MESSAGES, INGEST_MAX_WINDOW_DAYS, PI_STORE,
    fmt_ts, is_genuine_pi_user_message, load_cursors, now_utc, parse_ts,
)


def scan_pi_store(root, cursor_iso):
    """Pi のセッション（<root>/**/<session>.jsonl、cwd ごとに保存）を走査。(readable, messages) を返す。
    先頭行がヘッダ（type:"session"）で session id と cwd を持つ。以降の type:"message" のうち
    message.role=="user" が本物の発話。dedup 用 uuid は pi:<session>:<entry id>（各行の安定 id を使う。
    無い版では ts で代替）。入れ子の深さは Pi の版で変わりうるので **/*.jsonl で深さ非依存に拾う。
    I/O 失敗時 readable=False、窓・停滞対策は他ストアと同じ思想。"""
    if not os.path.isdir(root):
        return False, []
    cursor = parse_ts(cursor_iso) if cursor_iso else None
    out = []
    ok = True
    for path in sorted(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)):
        try:
            if cursor and os.path.getmtime(path) < cursor.timestamp() - 120:
                continue  # カーソル以前にしか書かれていないファイルは読まない
            f = open(path, encoding="utf-8")
        except OSError:
            ok = False  # stat/open に失敗したファイルがある→このストアは前進させない
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
                    if d.get("type") == "session":  # 先頭ヘッダ行：session id と cwd を確定
                        session_id = d.get("id") or session_id
                        cwd = d.get("cwd") or cwd
                        continue
                    if not is_genuine_pi_user_message(d):
                        continue
                    try:
                        ts = parse_ts(d["timestamp"])
                    except (ValueError, KeyError):
                        continue  # 不正な ts の1行はスキップ（ここで前進を止めると停滞するため）
                    if cursor and ts <= cursor:
                        continue
                    out.append({
                        "ts": d["timestamp"],
                        "session": session_id,
                        "uuid": f"pi:{session_id}:{d.get('id') or d['timestamp']}",
                        "cwd": cwd,
                        "file": path,
                        "text": d["message"]["content"],
                        "role": "user",
                    })
        except (OSError, UnicodeDecodeError):
            # ライブ追記中のファイルが多バイト文字の途中で切れていると for line in f が
            # UnicodeDecodeError を投げる。extract 全体を落とさず、このストアは前進させない
            # （＝一時的な切断は次回自己回復。カーソルは無傷）。
            ok = False
            continue
    return ok, out


def scan_cloud_stream(cursors, this_machine):
    """他マシンの共有発話（クラウドの transcripts-<machine>.jsonl）を machine ごとに走査する。
    [(store_key, cursor_key, readable, msgs), ...] を返す。自分のマシン分は local Pi で読むので
    スキップ（重複回避）。クラウド未認証/未接続は空リスト。各マシン分は readable=False で据え置ける。

    行形式は relay が書いた {ts, turn_id, machine, cwd, role, text}。role=user は候補、assistant は
    判定の文脈用。dedup 用 uuid は pi:<machine>:<turn_id>（別マシンでも安定・ingest 重複を防ぐ）。"""
    try:
        from watari_cli import cloud
        store = cloud.get_store()
    except Exception:
        return []
    if store is None:
        return []
    try:
        files = store.list()
    except Exception:
        return []  # クラウド全体が読めない → cloud ソース無し（全 cloud カーソル据え置き）
    sources = []
    for f in files:
        name = f.get("name", "")
        if not (name.startswith("transcripts-") and name.endswith(".jsonl")):
            continue
        machine = name[len("transcripts-"):-len(".jsonl")]
        if machine == this_machine:
            continue
        cursor_key = f"cloud_{machine}"
        cur_iso = cursors.get(cursor_key)
        cursor = None
        if cur_iso:
            try:
                cursor = parse_ts(cur_iso)
            except (ValueError, TypeError):
                cursor = None
        try:
            content = store.read(name)
        except Exception:
            sources.append((cursor_key, cursor_key, False, []))  # このマシン分は据え置き
            continue
        msgs = []
        for raw in content.splitlines():
            try:
                d = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if d.get("role") not in ("user", "assistant"):
                continue
            ts = d.get("ts")
            if not ts:
                continue
            try:
                tsp = parse_ts(ts)
            except (ValueError, TypeError):
                continue
            if cursor and tsp <= cursor:
                continue
            # dedup uuid はローカル scan_pi_store と完全一致させる（pi:<session>:<turn_id/id>）。
            # A がローカルで、B がクラウド経由で同じ発話を夢に見ても (uuid,kind) dedup が効く。
            session = d.get("session")
            msgs.append({
                "ts": ts, "session": session,
                "uuid": f"pi:{session or machine}:{d.get('turn_id') or ts}",
                "cwd": d.get("cwd"), "file": name, "text": d.get("text"),
                "role": d.get("role"),
            })
        sources.append((cursor_key, cursor_key, True, msgs))
    return sources


def run():
    """ローカル Pi ＋ 他マシンの共有発話を走査して結果 dict を返す（副作用なし・読むだけ）。"""
    cursors = load_cursors()
    result = {"generated": fmt_ts(now_utc()), "stores": {}, "messages": []}
    # ソース = (store_key, cursor_key, readable, msgs)。組み込みは Pi（自マシンのローカル）＋
    # クラウドの他マシン分。cursor 規律は共通（読めた分だけ前進・読めなければ据え置き）。
    pi_readable, pi_msgs = scan_pi_store(PI_STORE, cursors.get("transcripts_pi"))
    sources = [("pi", "transcripts_pi", pi_readable, pi_msgs)]
    from watari_cli import host
    sources.extend(scan_cloud_stream(cursors, host.machine_id()))

    for store, cursor_key, readable, msgs in sources:
        cursor_iso = cursors.get(cursor_key)
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


def render_store_summary(store, info):
    """人間向けの1行サマリ（cli の `watari scan`（--json なし）の表示用。文言の正本はここ）。

    JSON のフィールド（readable/truncated 等）はエージェント用にそのまま維持し、
    画面表示だけを平易な日本語にする。
    """
    reading = "OK" if info.get("readable") else "失敗（今回の分は次回に持ち越します）"
    cut = "あり（量が多いため30日分ずつ処理します）" if info.get("truncated") else "なし"
    return f"{store}: 読み取り={reading} 新しい発話={info.get('count', 0)}件 区切り={cut}"


def main():
    print(json.dumps(run(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
