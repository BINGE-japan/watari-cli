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
    if args.execute:
        sys.stderr.write("live dream (--execute) はこのスライスでは未接続です。\n")
        return 2
    print("dream --dry-run（ソースを読むだけ・カセットへの書き込みなし）")
    print(f"  generated: {result['generated']}")
    for store, s in result["stores"].items():
        print(
            f"  {store}: readable={s['readable']} 新規発話={s['count']} "
            f"max_ts={s['max_ts']} truncated={s['truncated']}"
        )
    print(f"  合計候補: {len(result['messages'])} 件")
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

    pd = sub.add_parser("dream", help="ソース(会話ログ)から記憶候補を抽出（既定は書き込みなし）")
    pd.add_argument("--home", help="カセットのパス")
    pd.add_argument("--execute", action="store_true", help="(未接続) 実際に記憶へ取り込む")
    pd.set_defaults(func=cmd_dream)

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
