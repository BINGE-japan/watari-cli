#!/usr/bin/env python3
"""記憶の健全性監査。「正しく記録できているか不安」を一コマンドで検証する。

チェック内容:
1. log 行の形式（kind とジャンルの一致・ts・refs.uuid・(uuid,kind) 重複）。
   study の domain/topic/mastery/note 等の必須フィールド欠落は「参考情報」扱い
   （古い時期の行や手書きの行に混ざりうる。壊れではないので exit code に影響させない）。
2. state が log から再生成した結果と一致するか（決定論の検証。now は state.updated を使う）
3. related の参照先欠け / まもなく一覧から外れる話題・興味（参考情報）
4. --coverage: 直近の transcript で実発話が多いのに log に一度も現れないセッション一覧

exit 0 = 問題なし / 1 = 直したほうがよい問題あり

CLI(watari audit) からも使えるよう、集計を audit_report() に、表示整形を render_report() に
分けてある（表示文言の正本はここ。cli 側は render_report() を呼ぶだけにして二重整形を避ける）。
"""
import argparse
import glob
import json
import os
import sys

from .watari_lib import (
    GENRES, KIND_TO_GENRE, MSG_SETUP_REQUIRED, PI_STORE, SINK_DAYS,
    is_genuine_pi_user_message, load_log, now_utc, parse_ts, state_path,
)
from . import regen_state

# 必須フィールド欠落（参考情報）の表示上限。多い場合は先頭だけ見せて残りは件数で示す。
FIELD_INFO_LIMIT = 5


def check_logs():
    """(problems, field_infos) を返す。field_infos は必須フィールド欠落（参考情報扱い）。"""
    problems, field_infos, seen = [], [], {}
    for g in GENRES:
        for d in load_log(g):
            n = f"{g}#{d['_line']}"
            kind = d.get("kind")
            if KIND_TO_GENRE.get(kind) != g:
                problems.append(
                    f"{n}: kind={kind!r} の行はこのファイル({g}/log.jsonl)には保存できません"
                    "（study→learning、fact/interest/thread→life）")
            u = d.get("refs", {}).get("uuid")
            if not u:
                problems.append(f"{n}: refs.uuid がありません")
            else:
                key = (u, kind)
                if key in seen:
                    problems.append(f"{n}: 同じ (uuid, kind) の行が重複しています（先に出た行: {seen[key]}）")
                else:
                    seen[key] = n
            try:
                parse_ts(d["ts"])
            except Exception:
                problems.append(f"{n}: ts が時刻として読めません: {d.get('ts')!r}")
                continue
            # 必須フィールドの欠落は日付に関係なく検出し、「参考情報」として報告する
            if kind == "study" and not (d.get("domain") and d.get("topic") and d.get("mastery") and d.get("note")):
                field_infos.append(f"{n}: study 行に domain / topic / mastery / note のいずれかが欠落しています")
            if kind in ("interest", "thread") and not d.get("topic"):
                field_infos.append(f"{n}: {kind} 行に topic が欠落しています")
    return problems, field_infos


def check_state_derivation():
    problems = []
    # now には各 state 自身の updated を使う（減衰・クローズ計算を生成時点に合わせる）
    for g in GENRES:
        try:
            current = json.load(open(state_path(g), encoding="utf-8"))
        except FileNotFoundError:
            problems.append(f"{g}: 記憶のまとめが未生成です → watari regen で生成できます")
            continue
        gen = regen_state.regen(parse_ts(current["updated"]))[g]
        diffs = regen_state.semantic_diff({g: current}, {g: gen})
        problems += [
            f"記憶のまとめ({g})が記録と食い違っています → watari regen で作り直せます: {x}"
            for x in diffs]
    return problems


def check_references(now):
    infos = []
    try:
        st = json.load(open(state_path("learning"), encoding="utf-8"))
        life = json.load(open(state_path("life"), encoding="utf-8"))
    except FileNotFoundError:
        return infos  # まとめ未生成は check_state_derivation が報告する
    topics = {(dom, t) for dom, dv in st["domains"].items() for t in dv["topics"]}
    for dom, dv in st["domains"].items():
        for t, tv in dv["topics"].items():
            for r in tv.get("related", []):
                rd, _, rt = r.partition("/")
                if (rd, rt) not in topics:
                    infos.append(f"参照先が見つかりません: {dom}/{t} の関連トピック {r} は学習の記録にありません")
    for th in life["open_threads"]:
        if th.get("deadline") and parse_ts(th["deadline"]) > now:
            continue  # 期限が未来の thread は age によらず一覧に残る
        days = (now - parse_ts(th["last"])).days
        if days > SINK_DAYS - 10:
            infos.append(
                f"進行中の話題「{th['topic']}」は {days} 日更新がありません。まもなく一覧から外れます"
                "（記録は残ります。話題に出せば戻ります）")
    for topic, it in life["interests"].items():
        if it["heat"] == 1:
            infos.append(f"興味「{topic}」は最近話題に出ていません（このまま話題に出ないと一覧から外れます）")
    return infos


def check_coverage():
    ref_sessions = set()
    for g in GENRES:
        for d in load_log(g):
            s = d.get("refs", {}).get("session")
            if s:
                ref_sessions.add(s)
    lines = []
    if not os.path.isdir(PI_STORE):
        return ["[pi] まだ会話ログがありません（watari chat で話すと作られます）"]
    # session id はヘッダ行(type:"session")に入るので、まず1ファイル読んでから ref と突き合わせる
    # （Claude 版はファイル名で早期 skip できたが、Pi は id が中にあるため中身を見てから判定）。
    for path in glob.glob(os.path.join(PI_STORE, "**", "*.jsonl"), recursive=True):
        sid = os.path.basename(path)[:-6]
        cnt, last = 0, ""
        try:
            for line in open(path, encoding="utf-8"):
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("type") == "session":
                    sid = d.get("id") or sid
                    continue
                if is_genuine_pi_user_message(d):
                    cnt += 1
                    last = max(last, d["timestamp"])
        except OSError:
            continue
        if sid in ref_sessions:
            continue
        if cnt >= 5:
            lines.append(f"[pi] {os.path.basename(os.path.dirname(path))} {sid[:8]} 実発話{cnt} last={last[:10]}")
    return lines


def audit_report(coverage=False):
    """(problems, infos, coverage_lines|None) を返す。problems が非空なら直したほうがよい。

    必須フィールド欠落は infos（参考情報）側に、最大 FIELD_INFO_LIMIT 件＋残り件数で載る。
    log 自体が無い（未セットアップ）場合は FileNotFoundError を送出する
    （呼び出し側は MSG_SETUP_REQUIRED を案内して exit 1 にする）。
    """
    now = now_utc()
    problems, field_infos = check_logs()
    problems += check_state_derivation()
    infos = check_references(now)
    if len(field_infos) > FIELD_INFO_LIMIT:
        shown = field_infos[:FIELD_INFO_LIMIT]
        shown.append(f"（フィールド欠落は ほか {len(field_infos) - FIELD_INFO_LIMIT} 件）")
        field_infos = shown
    infos += field_infos
    cov = check_coverage() if coverage else None
    return problems, infos, cov


def render_report(problems, infos, cov=None):
    """監査結果の表示行を返す（文言の正本。engine main と cli の両方がこれを表示する）。"""
    lines = ["=== 直したほうがよい点 ===" if problems else "=== 直したほうがよい点: なし ==="]
    lines += [f" - {x}" for x in problems]
    if problems:
        lines.append(
            "→ 直し方: 「まとめが記録と食い違っています」は watari regen で解消できます。"
            "行の形式の問題は、記憶フォルダ内の life/ と learning/ の log.jsonl の該当行を修正してください。")
    if infos:
        lines.append("=== 参考情報（異常ではありません） ===")
        lines += [f" - {x}" for x in infos]
    if cov is not None:
        lines.append("=== 記憶に一度も取り込まれていない会話（実発話5件以上） ===")
        lines += [f" - {x}" for x in cov]
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", action="store_true", help="log に現れないセッションの一覧も出す")
    args = ap.parse_args()

    try:
        problems, infos, cov = audit_report(args.coverage)
    except FileNotFoundError:
        print(MSG_SETUP_REQUIRED, file=sys.stderr)
        sys.exit(1)
    for line in render_report(problems, infos, cov):
        print(line)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
