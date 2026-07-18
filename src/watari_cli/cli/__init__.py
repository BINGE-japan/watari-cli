"""Watari command-line entrypoint（ゲーム機の入口）。

カセット＝個人記憶は内蔵せず、--home / WATARI_HOME（差込口）で差し込む。
現在の一本:
  watari status          カセットの現在地を読む（読むだけ）
  watari dream           ソース(会話ログ)から記憶候補を抽出（既定は --dry-run 相当・書き込みなし）
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from watari_cli import config


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def _count_lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except FileNotFoundError:
        return None


def cmd_status(args) -> int:
    config.apply(args.home)
    from watari_cli.engine import watari_lib as wl

    home = wl.MEM
    if not os.path.isdir(home):
        sys.stderr.write(f"カセットが見つかりません: {home}\n")
        return 1
    print(f"cartridge（カセット）: {home}")
    for genre in wl.GENRES:
        n = _count_lines(wl.log_path(genre))
        print(f"  {genre}/log.jsonl: {n if n is not None else '—'} 行")
    cursors = _load_json(os.path.join(home, "cursors.json")) or {}
    if cursors:
        print("  cursors:")
        for k, v in cursors.items():
            print(f"    {k}: {v}")
    life = _load_json(wl.state_path("life")) or {}
    print(
        "  life.state: "
        f"open_threads={len(life.get('open_threads', []))} "
        f"interests={len(life.get('interests', {}))} "
        f"profile_keys={len(life.get('profile', {}))}"
    )
    learning = _load_json(wl.state_path("learning")) or {}
    domains = learning.get("domains", {})
    topics = sum(len(d.get("topics", {})) for d in domains.values())
    print(f"  learning.state: domains={len(domains)} topics={topics}")
    return 0


def cmd_dream(args) -> int:
    config.apply(args.home)
    from watari_cli.engine import extract

    result = extract.run()
    if args.json:
        # 判定するエージェント(Piで動くワタリ)が消費する生の候補。messages[] を渡す。
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    print("dream（ソースを読むだけ・カセットへの書き込みなし）")
    print(f"  generated: {result['generated']}")
    for store, s in result["stores"].items():
        print(
            f"  {store}: readable={s['readable']} 新規発話={s['count']} "
            f"max_ts={s['max_ts']} truncated={s['truncated']}"
        )
    print(f"  合計候補: {len(result['messages'])} 件")
    print("  → 判定は Watari(エージェント)が SCHEMA に沿って行い、watari ingest で書き込む")
    return 0


def cmd_recall(args) -> int:
    config.apply(args.home)
    from watari_cli.engine import watari_lib as wl

    out = {}
    for genre in wl.GENRES:
        try:
            with open(wl.state_path(genre), encoding="utf-8") as f:
                out[genre] = json.load(f)
        except FileNotFoundError:
            out[genre] = None
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def cmd_audit(args) -> int:
    config.apply(args.home)
    from watari_cli.engine import audit

    problems, infos, cov = audit.audit_report(args.coverage)
    print("=== 要修正 ===" if problems else "=== 要修正: なし ===")
    for x in problems:
        print(" -", x)
    if infos:
        print("=== 情報（異常ではない） ===")
        for x in infos:
            print(" -", x)
    if cov is not None:
        print("=== log に一度も現れないセッション（実発話5件以上） ===")
        for x in cov:
            print(" -", x)
    return 1 if problems else 0


def cmd_init(args) -> int:
    config.apply(args.home)
    from watari_cli.engine import regen_state, watari_lib as wl

    home = wl.MEM
    if os.path.isdir(home) and os.listdir(home) and not args.force:
        sys.stderr.write(f"既にファイルがあります: {home}（空でない）。--force で続行。\n")
        return 1
    for sub in ("life", "learning"):
        os.makedirs(os.path.join(home, sub), exist_ok=True)
    for genre in ("life", "learning"):
        path = wl.log_path(genre)
        if not os.path.exists(path):
            open(path, "w", encoding="utf-8").close()
    cursors = {k: None for k in (
        "transcripts_win", "transcripts_wsl", "transcripts_codex",
        "slack", "gmail", "calendar", "linear", "obsidian", "last_run",
    )}
    wl.atomic_write_json(os.path.join(home, "cursors.json"), cursors)
    # カセットの git 設定（多マシン追記の union-merge / 派生 state は追跡しない）
    with open(os.path.join(home, ".gitattributes"), "w", encoding="utf-8") as f:
        f.write("*.jsonl merge=union\n")
    with open(os.path.join(home, ".gitignore"), "w", encoding="utf-8") as f:
        f.write("*/state.json\n")
    for genre, out in regen_state.regen(wl.now_utc()).items():
        wl.atomic_write_json(wl.state_path(genre), out)
    print(f"空のカセットを用意しました: {home}")
    print("  次: この場所を WATARI_HOME に。会話ログから育てるなら dream→(判定)→ingest。")
    print("  可搬化: このディレクトリを private git リポにして別マシンで clone すれば記憶ごと再現。")
    return 0


def cmd_regen(args) -> int:
    config.apply(args.home)
    from watari_cli.engine import regen_state, watari_lib as wl

    now = regen_state.parse_ts(args.now) if args.now else regen_state.now_utc()
    gen = regen_state.regen(now)
    if args.check:
        current = {g: json.load(open(wl.state_path(g), encoding="utf-8")) for g in wl.GENRES}
        diffs = regen_state.semantic_diff(current, gen)
        if diffs:
            print(f"state と log 再生成結果に差分 {len(diffs)} 件:")
            for x in diffs:
                print(" ", x)
            return 1
        print("OK: state は log から再生成した結果と一致（決定論が保たれている）")
        return 0
    for genre in wl.GENRES:
        wl.atomic_write_json(wl.state_path(genre), gen[genre])
    print(f"state 再生成完了 (now={regen_state.fmt_ts(now)})")
    return 0


def cmd_ingest(args) -> int:
    config.apply(args.home)
    from watari_cli.engine import ingest

    try:
        rows = ingest.load_rows(args.rows)
        summary = ingest.apply(
            rows,
            advance_wsl=args.advance_wsl, advance_win=args.advance_win,
            advance_codex=args.advance_codex, advance_obsidian=args.advance_obsidian,
            advance_ext=args.advance_ext or (), allow_new_domain=args.allow_new_domain,
            dry_run=args.dry_run,
        )
    except FileNotFoundError as error:
        sys.stderr.write(f"rows ファイルが読めません: {error}\n")
        return 2
    except ValueError as error:
        errors = error.args[0] if error.args else [str(error)]
        sys.stderr.write(f"検証エラー {len(errors)} 件（何も書き込んでいません）:\n")
        for e in errors:
            sys.stderr.write(f"  - {e}\n")
        return 2
    print(summary)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="watari", description="Watari CLI — ゲーム機")
    try:
        from importlib.metadata import version

        p.add_argument("--version", action="version", version=f"watari {version('watari-cli')}")
    except Exception:
        pass
    sub = p.add_subparsers(dest="command", required=True)

    ps = sub.add_parser("status", help="カセット(個人記憶)の現在地を読む")
    ps.add_argument("--home", help="カセットのパス（既定: WATARI_HOME か現ライブ・カセット）")
    ps.set_defaults(func=cmd_status)

    pd = sub.add_parser("dream", help="ソース(会話ログ)から記憶候補を抽出（読むだけ）")
    pd.add_argument("--home", help="カセットのパス")
    pd.add_argument("--json", action="store_true", help="判定用に生の候補(messages[])をJSON出力")
    pd.set_defaults(func=cmd_dream)

    pr = sub.add_parser("recall", help="カセットの現在地(life/learning state)をJSONで読む")
    pr.add_argument("--home", help="カセットのパス")
    pr.set_defaults(func=cmd_recall)

    pa = sub.add_parser("audit", help="記憶の健全性を監査（決定論・形式・乖離）")
    pa.add_argument("--home", help="カセットのパス")
    pa.add_argument("--coverage", action="store_true", help="log に現れないセッションも列挙")
    pa.set_defaults(func=cmd_audit)

    pn = sub.add_parser("init", help="空のカセットを新規作成（他人が自分のワタリを始める口）")
    pn.add_argument("--home", help="作成先のパス（既定: WATARI_HOME）")
    pn.add_argument("--force", action="store_true", help="空でない場所でも続行")
    pn.set_defaults(func=cmd_init)

    pg = sub.add_parser("regen", help="log から state を再生成（clone 直後の復元・派生の作り直し）")
    pg.add_argument("--home", help="カセットのパス")
    pg.add_argument("--now", help="再生成時刻(UTC ISO)。省略時は現在時刻")
    pg.add_argument("--check", action="store_true", help="書き込まず現 state と比較")
    pg.set_defaults(func=cmd_regen)

    pi = sub.add_parser("ingest", help="判定済みの記憶行(JSON)をカセットへ書き込む")
    pi.add_argument("--rows", required=True, help="log 行の JSON 配列ファイル(SCHEMA 準拠)")
    pi.add_argument("--home", help="カセットのパス")
    pi.add_argument("--advance-wsl")
    pi.add_argument("--advance-win")
    pi.add_argument("--advance-codex")
    pi.add_argument("--advance-obsidian")
    pi.add_argument("--advance-ext", action="append", default=[], metavar="NAME=TS")
    pi.add_argument("--allow-new-domain", action="store_true")
    pi.add_argument("--dry-run", action="store_true", help="検証と件数だけ（書き込みなし）")
    pi.set_defaults(func=cmd_ingest)
    return p


def main() -> int:
    args = _build_parser().parse_args()
    return args.func(args)
