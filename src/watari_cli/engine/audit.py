#!/usr/bin/env python3
"""記憶の健全性監査。「正しく記録できているか不安」を一コマンドで検証する。

チェック内容:
1. log 行の形式（kind とジャンルの一致・study の domain/topic・ts・refs.uuid・(uuid,kind) 重複）
2. state が log から再生成した結果と一致するか（決定論の検証。now は state.updated を使う）
3. related の宙に浮いた参照 / まもなく沈む・冷却する項目（情報表示）
4. --coverage: 直近の transcript で実発話が多いのに log に一度も現れないセッション一覧

exit 0 = 問題なし / 1 = 要修正の問題あり

CLI(watari audit) からも使えるよう、集計を audit_report() に分けてある。
"""
import argparse
import glob
import json
import os
import sys

from .watari_lib import (
    GENRES, KIND_TO_GENRE, SINK_DAYS, STORES,
    is_genuine_user_message, load_log, now_utc, parse_ts, state_path,
)
from . import regen_state

# 旧仕様時代（スクリプト化以前）の行は形式警告の対象外にする
STRICT_SINCE = "2026-07-02T12:00:00.000Z"


def check_logs():
    problems, seen = [], {}
    for g in GENRES:
        for d in load_log(g):
            n = f"{g}#{d['_line']}"
            kind = d.get("kind")
            if KIND_TO_GENRE.get(kind) != g:
                problems.append(f"{n}: kind={kind!r} は {g} に置けない")
            u = d.get("refs", {}).get("uuid")
            if not u:
                problems.append(f"{n}: refs.uuid 欠落")
            else:
                key = (u, kind)
                if key in seen:
                    problems.append(f"{n}: (uuid,kind) 重複（先出 {seen[key]}）")
                else:
                    seen[key] = n
            try:
                parse_ts(d["ts"])
            except Exception:
                problems.append(f"{n}: ts 不正 {d.get('ts')!r}")
                continue
            if d["ts"] >= STRICT_SINCE:
                if kind == "study" and not (d.get("domain") and d.get("topic") and d.get("mastery") and d.get("note")):
                    problems.append(f"{n}: 新仕様の study に domain/topic/mastery/note のどれかが欠落")
                if kind in ("interest", "thread") and not d.get("topic"):
                    problems.append(f"{n}: 新仕様の {kind} に topic 欠落")
    return problems


def check_state_derivation():
    problems = []
    # now には各 state 自身の updated を使う（減衰・クローズ計算を生成時点に合わせる）
    for g in GENRES:
        current = json.load(open(state_path(g), encoding="utf-8"))
        gen = regen_state.regen(parse_ts(current["updated"]))[g]
        diffs = regen_state.semantic_diff({g: current}, {g: gen})
        problems += [f"state[{g}] が log と乖離: {x}" for x in diffs]
    return problems


def check_references(now):
    infos = []
    st = json.load(open(state_path("learning"), encoding="utf-8"))
    topics = {(dom, t) for dom, dv in st["domains"].items() for t in dv["topics"]}
    for dom, dv in st["domains"].items():
        for t, tv in dv["topics"].items():
            for r in tv.get("related", []):
                rd, _, rt = r.partition("/")
                if (rd, rt) not in topics:
                    infos.append(f"related が宙に浮いている: {dom}/{t} -> {r}")
    life = json.load(open(state_path("life"), encoding="utf-8"))
    for th in life["open_threads"]:
        if th.get("deadline") and parse_ts(th["deadline"]) > now:
            continue  # 期限が未来の thread は age によらず沈まない
        days = (now - parse_ts(th["last"])).days
        if days > SINK_DAYS - 10:
            infos.append(f"thread まもなく沈む({days}日): {th['topic']}")
    for topic, it in life["interests"].items():
        if it["heat"] == 1:
            infos.append(f"interest 冷却間近(heat=1): {topic}")
    return infos


def check_coverage():
    ref_sessions = set()
    for g in GENRES:
        for d in load_log(g):
            s = d.get("refs", {}).get("session")
            if s:
                ref_sessions.add(s)
    lines = []
    for store, root in STORES.items():
        if not os.path.isdir(root):
            lines.append(f"[{store}] ストアが読めない")
            continue
        for path in glob.glob(os.path.join(root, "*", "*.jsonl")):
            sid = os.path.basename(path)[:-6]
            if sid in ref_sessions:
                continue
            cnt, last = 0, ""
            try:
                for line in open(path, encoding="utf-8"):
                    if '"type":"user"' not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if is_genuine_user_message(d):
                        cnt += 1
                        last = max(last, d["timestamp"])
            except OSError:
                continue
            if cnt >= 5:
                lines.append(f"[{store}] {os.path.basename(os.path.dirname(path))} {sid[:8]} 実発話{cnt} last={last[:10]}")
    return lines


def audit_report(coverage=False):
    """(problems, infos, coverage_lines|None) を返す。problems が非空なら要修正。"""
    now = now_utc()
    problems = check_logs() + check_state_derivation()
    infos = check_references(now)
    cov = check_coverage() if coverage else None
    return problems, infos, cov


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", action="store_true", help="log に現れないセッションの一覧も出す")
    args = ap.parse_args()

    problems, infos, cov = audit_report(args.coverage)
    print("=== 要修正 ===" if problems else "=== 要修正: なし ===")
    for x in problems:
        print(" -", x)
    if infos:
        print("=== 情報（異常ではない） ===")
        for x in infos:
            print(" -", x)
    if cov is not None:
        print("=== log に一度も現れないセッション（実発話5件以上。取り込み判断の見直し用） ===")
        for x in cov:
            print(" -", x)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
