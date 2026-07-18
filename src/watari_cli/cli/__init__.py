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


def _scaffold_empty_cartridge() -> str:
    """WATARI_HOME に空カセットの骨格を作り、そのパスを返す（config.apply 済みで呼ぶ）。"""
    from watari_cli.engine import watari_lib as wl

    home = wl.MEM
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
    _rebuild_state()
    return home


def _rebuild_state() -> None:
    """log から state.json を再生成する（config.apply 済みで呼ぶ）。"""
    from watari_cli.engine import regen_state, watari_lib as wl

    for genre, out in regen_state.regen(wl.now_utc()).items():
        wl.atomic_write_json(wl.state_path(genre), out)


def cmd_init(args) -> int:
    config.apply(args.home)
    from watari_cli.engine import watari_lib as wl

    home = wl.MEM
    if os.path.isdir(home) and os.listdir(home) and not args.force:
        sys.stderr.write(f"既にファイルがあります: {home}（空でない）。--force で続行。\n")
        return 1
    _scaffold_empty_cartridge()
    print(f"空のカセットを用意しました: {home}")
    print("  次: この場所を WATARI_HOME に。会話ログから育てるなら dream→(判定)→ingest。")
    print("  可搬化: このディレクトリを private git リポにして別マシンで clone すれば記憶ごと再現。")
    return 0


def _default_cartridge_dir() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "watari", "cartridge")


PROVIDER_MODELS = {
    "openrouter": "deepseek/deepseek-chat",
    "anthropic": "anthropic/claude-sonnet-5",
    "google": "",
    "openai": "openai/gpt-5",
}
PROVIDER_KEY_ENV = {
    "openrouter": "OPENROUTER_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
    "google": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY",
}


def _setup_cartridge(mode: str, home: str, url: str | None) -> tuple[str, str]:
    """mode='clone'|'adopt'|'new'。home にカセットを用意し state を再生成。(絶対home, 説明) を返す。"""
    import subprocess

    home = os.path.abspath(os.path.expanduser(home))
    if mode == "clone":
        if os.path.exists(home) and os.listdir(home):
            raise RuntimeError(f"クローン先が空ではありません: {home}")
        os.makedirs(os.path.dirname(home) or ".", exist_ok=True)
        clone = subprocess.run(["git", "clone", url, home], capture_output=True, text=True)
        if clone.returncode != 0:
            raise RuntimeError(f"git clone 失敗:\n{clone.stderr}")
        config.apply(home)
        _rebuild_state()
        return home, "クローン＋state再生成（記憶を継承）"
    config.apply(home)
    if mode == "adopt":
        if not (os.path.isdir(home) and os.listdir(home)):
            raise RuntimeError(f"既存カセットが見つかりません: {home}")
        _rebuild_state()
        return home, "既存カセットを採用＋state再生成"
    if os.path.isdir(home) and os.listdir(home):
        raise RuntimeError(f"空ではありません: {home}")
    _scaffold_empty_cartridge()
    return home, "空カセットを新規作成"


def _install_wizard(args) -> dict:
    """インストール体験（UX）だけ。質問して選択を plan(dict) にして返す。副作用なし。

    ここが「コンポーネント」。--dry-run はこれだけを回す。実行は _setup_cartridge が担う。
    フラグを渡せばその質問は飛ばす。--yes で全部既定。prompts.Cancelled を送出しうる。
    """
    from watari_cli import prompts

    default_dir = _default_cartridge_dir()
    live = os.path.join(os.path.expanduser("~"), ".claude", "skills", "watari", "memory")

    # 1) カセット
    if args.from_url:
        mode, home, url = "clone", (args.home or default_dir), args.from_url
    elif args.home:
        existing = os.path.isdir(args.home) and os.listdir(args.home)
        mode, home, url = ("adopt" if existing else "new"), args.home, None
    elif args.yes:
        mode, home, url = "new", default_dir, None
    else:
        kind = prompts.select("記憶（カセット）をどうしますか？", [
            ("まっさら新規作成（自分のワタリを一から育てる）", "new"),
            ("このマシンにある既存カセットを使う", "adopt"),
            ("既存のワタリ記憶を git から引き継ぐ（別マシン再現・共有）", "clone"),
        ], default=0)
        if kind == "clone":
            url = prompts.text("カセットの git URL")
            home = prompts.text("取り込み先", default=default_dir)
        elif kind == "adopt":
            home = prompts.text("カセットのパス", default=(live if os.path.isdir(live) else default_dir))
            url = None
        else:
            home = prompts.text("作成先", default=default_dir)
            url = None
        mode = kind

    # 2) プロバイダ / モデル（ウィザード時のみ尋ねる）
    provider = args.provider
    wizard = not (args.from_url or args.home or args.yes)
    if provider is None and wizard:
        provider = prompts.select("モデルプロバイダは？（Pi で使う。後で変更可）", [
            ("OpenRouter（安価モデルを横断）", "openrouter"),
            ("Anthropic（Claude）", "anthropic"),
            ("Google（Pi 既定）", "google"),
            ("OpenAI", "openai"),
        ], default=0)
    model = args.model
    if model is None and wizard and provider is not None:
        model = prompts.text("モデル（空Enterで既定）", default=PROVIDER_MODELS.get(provider, "")) or None

    return {"mode": mode, "home": home, "url": url,
            "provider": provider, "model": model, "runtime": args.runtime}


def _install_done_lines(home: str, desc: str, plan: dict) -> list[str]:
    lines = [f"✓ インストール完了（{desc}）", f"  カセット: {home}"]
    if plan["provider"] or plan["model"]:
        lines.append(f"  ランタイム: provider={plan['provider'] or '既定'} model={plan['model'] or '既定'}")
    lines.append("  起動:  watari chat")
    key_env = PROVIDER_KEY_ENV.get(plan["provider"] or "")
    if key_env and not os.environ.get(key_env):
        lines.append(f"  ※ モデルのキー未設定。一度だけ: export {key_env}=...")
    return lines


def cmd_install(args) -> int:
    """初回セットアップ。UX(_install_wizard) と実行(_setup_cartridge/保存) を分離。

    --dry-run で UX だけを何度でも試せる（副作用ゼロ）。フラグ全指定/--yes で非対話。
    """
    from watari_cli import prompts

    try:
        plan = _install_wizard(args)
    except prompts.Cancelled:
        sys.stderr.write("\n中止しました。\n")
        return 130

    if args.dry_run:
        target = os.path.abspath(os.path.expanduser(plan["home"]))
        act = {"new": "空カセットを新規作成", "adopt": "既存カセットを採用",
               "clone": f"git clone {plan['url']}"}[plan["mode"]]
        print("\n── プレビュー（--dry-run：実際には何も変更していません）──")
        print(f"  カセット: {act} → {target}")
        print("  実行時: カセット用意 → state 再生成 → 設定保存(config.json)")
        print("  完了時の表示 ↓")
        for line in _install_done_lines(target, act, plan):
            print("    " + line)
        return 0

    try:
        home, desc = _setup_cartridge(plan["mode"], plan["home"], plan["url"])
    except RuntimeError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    saved = config.save_home(home)
    config.save_config(runtime=plan["runtime"], provider=plan["provider"], model=plan["model"])
    print()
    for line in _install_done_lines(saved, desc, plan):
        print(line)
    return 0


def _find_skill_dir() -> str | None:
    """同梱スキル skills/watari の場所を最善努力で探す（リポ実行時に見つかる）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(os.getcwd(), "skills", "watari"),
        os.path.join(here, "..", "..", "..", "skills", "watari"),
        os.path.join(here, "..", "skills", "watari"),
    ]
    for path in candidates:
        resolved = os.path.abspath(path)
        if os.path.isfile(os.path.join(resolved, "SKILL.md")):
            return resolved
    return None


def _runtime_base(runtime: str) -> list[str]:
    """ランタイムの起動コマンド基底を返す。今は Pi。pi が無ければ npx 経由で取りに行く。"""
    import shutil

    if runtime in ("pi", None, ""):
        if shutil.which("pi"):
            return ["pi"]
        npx = shutil.which("npx")
        if npx:
            return [npx, "-y", "@earendil-works/pi-coding-agent"]
        return ["pi"]  # 見つからなければ実行時に分かりやすく失敗させる
    # 他ランタイムは runtime 文字列をそのままコマンドとして扱う（拡張余地）
    return runtime.split()


def cmd_chat(args) -> int:
    """ワタリを起動する。スキル・カセット・モデルを自動で渡すランチャー。

    ユーザーは長い pi コマンドを覚えなくてよい: watari chat だけでワタリが立ち上がる。
    """
    import shlex
    import subprocess

    config.apply(args.home)
    from watari_cli.engine import watari_lib as wl

    home = wl.MEM
    if not os.path.isdir(home):
        sys.stderr.write(f"カセットが見つかりません: {home}\n  先に `watari install` を実行してください。\n")
        return 1
    skill = _find_skill_dir()
    if not skill:
        sys.stderr.write("同梱スキル skills/watari が見つかりません（リポから実行してください）。\n")
        return 1

    settings = config.load_config()
    runtime = args.runtime or settings.get("runtime") or "pi"
    provider = args.provider or settings.get("provider")
    model = args.model or settings.get("model")

    cmd = _runtime_base(runtime) + ["--skill", skill]
    if provider:
        cmd += ["--provider", provider]
    if model:
        cmd += ["--model", model]
    cmd += args.extra

    env = dict(os.environ)
    env["WATARI_HOME"] = home  # ランタイムの bash ツールが watari CLI で同じカセットを読めるように

    if args.show:
        print(f"WATARI_HOME={home}")
        print(" ".join(shlex.quote(c) for c in cmd))
        return 0
    try:
        return subprocess.run(cmd, env=env).returncode
    except FileNotFoundError:
        sys.stderr.write(
            f"ランタイム '{runtime}' が起動できません（{cmd[0]} が見つからない）。\n"
            "  Pi を使うなら `npx -y @earendil-works/pi-coding-agent` が通るか確認してください。\n"
        )
        return 127


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

    pinst = sub.add_parser("install", help="初回セットアップ（カセット用意＋設定保存。--from でgit継承）")
    pinst.add_argument("--home", help="カセットの場所（既定: XDG_DATA_HOME/watari/cartridge）")
    pinst.add_argument("--from", dest="from_url", metavar="GIT_URL",
                       help="既存カセットの git リポをクローンして記憶を継承する")
    pinst.add_argument("--runtime", help="起動ランタイム（既定 pi）。watari chat が使う")
    pinst.add_argument("--provider", help="モデルプロバイダ（例 openrouter, google, anthropic）")
    pinst.add_argument("--model", help="モデル（例 anthropic/claude-... や provider 既定）")
    pinst.add_argument("--yes", "-y", action="store_true", help="質問せず既定のまま（コマンド一発）")
    pinst.add_argument("--dry-run", action="store_true", help="UX だけ試す（何も変更しない・何度でも）")
    pinst.set_defaults(func=cmd_install)

    pc = sub.add_parser("chat", help="ワタリを起動（スキル/カセット/モデルを自動で渡す）")
    pc.add_argument("--home", help="カセットのパス")
    pc.add_argument("--runtime", help="起動ランタイム（既定: 保存値か pi）")
    pc.add_argument("--provider", help="モデルプロバイダ（保存値を上書き）")
    pc.add_argument("--model", help="モデル（保存値を上書き）")
    pc.add_argument("--show", action="store_true", help="起動せず、実行するコマンドだけ表示")
    pc.add_argument("extra", nargs="*", help="ランタイムへ素通しする追加引数")
    pc.set_defaults(func=cmd_chat)

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
