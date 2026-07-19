"""watari コマンドの入口。

ワタリ本体は記憶を内蔵せず、--home / 環境変数 WATARI_HOME で指した記憶を読み書きする。
記憶は会話ログから育つ個人データ（log.jsonl が正本、state.json は派生）。
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
    from watari_cli import host
    from watari_cli.engine import watari_lib as wl

    home = wl.MEM
    if not os.path.isdir(home):
        sys.stderr.write(f"記憶が見つかりません: {home}\n")
        return 1
    print(f"記憶の場所: {home}")
    for genre in wl.GENRES:
        n = _count_lines(wl.log_path(genre))
        print(f"  {genre}/log.jsonl: {n if n is not None else '—'} 行")
    # カーソルはこのマシンの host 記録から（旧 cursors.json があれば初回に移行して読む）
    cursors = host.load_cursors(home)
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


def cmd_host(args) -> int:
    config.apply(args.home)
    from watari_cli import host
    from watari_cli.engine import watari_lib as wl

    home = wl.MEM
    if not os.path.isdir(home):
        sys.stderr.write(f"記憶が見つかりません: {home}\n")
        return 1
    for pair in args.set:
        if "=" not in pair:
            sys.stderr.write(f"--set は KEY=VALUE 形式で指定してください: {pair}\n")
            return 2
        key, value = pair.split("=", 1)
        host.set_fact(home, key, value)
    record = host.refresh(home)
    print(f"このマシン: {record['machine_id']}")
    print(f"  hostname: {record['hostname']}")
    print(f"  platform: {record['platform']} / python {record['python']}")
    print(f"  shell: {record['shell'] or '—'}")
    print(f"  ai_clis: {', '.join(record['ai_clis']) or '—'}")
    for key, value in record["facts"].items():
        print(f"  fact {key}: {value}")
    others = [r for r in host.all_hosts(home) if r.get("machine_id") != record["machine_id"]]
    if others:
        print("他のマシン:")
        for r in others:
            facts = " ".join(f"{k}={v}" for k, v in (r.get("facts") or {}).items())
            clis = ",".join(r.get("ai_clis") or []) or "—"
            line = f"  {r.get('machine_id')}: {r.get('platform')} clis={clis}"
            print(line + (f" [{facts}]" if facts else ""))
    return 0


def cmd_dream(args) -> int:
    config.apply(args.home)
    from watari_cli.engine import extract

    result = extract.run()
    if args.json:
        # 判定するワタリ(エージェント)が消費する生の候補。messages[] を渡す。
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    print("dream（会話ログを読むだけ・記憶への書き込みなし）")
    print(f"  generated: {result['generated']}")
    for store, s in result["stores"].items():
        print(
            f"  {store}: readable={s['readable']} 新規発話={s['count']} "
            f"max_ts={s['max_ts']} truncated={s['truncated']}"
        )
    print(f"  合計候補: {len(result['messages'])} 件")
    print("  → 判定はワタリ(エージェント)が SCHEMA に沿って行い、watari ingest で書き込む")
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


def _scaffold_empty_memory() -> str:
    """WATARI_HOME に空の記憶の骨格を作り、そのパスを返す（config.apply 済みで呼ぶ）。"""
    from watari_cli.engine import watari_lib as wl

    home = wl.MEM
    for sub in ("life", "learning"):
        os.makedirs(os.path.join(home, sub), exist_ok=True)
    for genre in ("life", "learning"):
        path = wl.log_path(genre)
        if not os.path.exists(path):
            open(path, "w", encoding="utf-8").close()
    # カーソルはマシンごとの host 記録に持つ（hosts/<machine_id>.json の "cursors"）。
    # 初回の advance / status で遅延生成されるので、ここでは作らない。
    # 記憶の git 設定（多マシン追記の union-merge / 派生 state は追跡しない）
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
    _scaffold_empty_memory()
    print(f"空の記憶を用意しました: {home}")
    print("  次: この場所を WATARI_HOME に。会話ログから育てるなら dream→(判定)→ingest。")
    print("  持ち運び: このフォルダを private git リポにして別マシンで clone すれば記憶ごと再現。")
    return 0


def _default_memory_dir() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "watari", "memory")


def _prepare_memory(mode: str, home: str, url: str | None) -> tuple[str, str]:
    """mode='clone'|'adopt'|'new'。home に記憶を用意し state を再生成。(絶対home, 説明) を返す。"""
    import subprocess

    home = os.path.abspath(os.path.expanduser(home))
    if mode == "clone":
        if os.path.exists(home) and os.listdir(home):
            raise RuntimeError(f"復元先が空ではありません: {home}")
        os.makedirs(os.path.dirname(home) or ".", exist_ok=True)
        clone = subprocess.run(["git", "clone", url, home], capture_output=True, text=True)
        if clone.returncode != 0:
            raise RuntimeError(f"git clone 失敗:\n{clone.stderr}")
        config.apply(home)
        _rebuild_state()
        return home, "バックアップから復元（記憶を継承）"
    config.apply(home)
    if mode == "adopt":
        if not (os.path.isdir(home) and os.listdir(home)):
            raise RuntimeError(f"記憶が見つかりません: {home}")
        _rebuild_state()
        return home, "既存の記憶を使う"
    if os.path.isdir(home) and os.listdir(home):
        raise RuntimeError(f"空ではありません: {home}")
    _scaffold_empty_memory()
    return home, "新しい記憶を作成"


def _install_wizard(args) -> dict:
    """インストール体験（UX）だけ。質問して選択を plan(dict) にして返す。副作用なし。

    ここが調整対象のコンポーネント。--dry-run はこれだけを回す。実行は _prepare_memory が担う。
    フラグを渡せばその質問は飛ばす。--yes で全部既定。prompts.Cancelled を送出しうる。
    """
    from watari_cli import prompts

    default_dir = _default_memory_dir()
    live = os.path.join(os.path.expanduser("~"), ".claude", "skills", "watari", "memory")

    # 1) 記憶の始め方
    if args.from_url:
        mode, home, url = "clone", (args.home or default_dir), args.from_url
    elif args.home:
        existing = os.path.isdir(args.home) and os.listdir(args.home)
        mode, home, url = ("adopt" if existing else "new"), args.home, None
    elif args.yes:
        mode, home, url = "new", default_dir, None
    else:
        print("\nワタリのセットアップ")
        print("会話からあなたを少しずつ覚えていく相棒「ワタリ」を用意します。\n")
        kind = prompts.select("ワタリの記憶を、どこから始めますか？", [
            ("新しく始める", "new"),
            ("このパソコンにある記憶を引き継ぐ", "adopt"),
            ("別の場所のバックアップから復元する", "clone"),
        ], default=0)
        if kind == "clone":
            url = prompts.text("バックアップの場所（git URL）")
            home = default_dir  # 保存先は既定で十分。こだわる人は --home で上書き
        elif kind == "adopt":
            home = prompts.text("記憶のあるフォルダ", default=(live if os.path.isdir(live) else default_dir))
            url = None
        else:  # new: 保存先は聞かず既定を使う
            home = default_dir
            url = None
        mode = kind

    # AI（プロバイダ/モデル）は Pi 側で選ぶもの。install はモデル非依存に徹する（尋ねない・保存しない）。
    return {"mode": mode, "home": home, "url": url, "runtime": args.runtime}


def _install_done_lines(home: str, desc: str) -> list[str]:
    return [f"✓ セットアップ完了（{desc}）", f"  記憶の場所: {home}", "  起動:  watari chat"]


def cmd_install(args) -> int:
    """初回セットアップ。UX(_install_wizard) と実行(_prepare_memory/保存) を分離。

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
        act = {"new": "新しい記憶を作成", "adopt": "既存の記憶を使う",
               "clone": f"バックアップから復元（{plan['url']}）"}[plan["mode"]]
        print("\n── プレビュー（--dry-run：実際には何も変更していません）──")
        print(f"  記憶: {act} → {target}")
        print("  実行時: 記憶を用意 → state 再生成 → 設定保存(config.json)")
        print("  完了時の表示 ↓")
        for line in _install_done_lines(target, act):
            print("    " + line)
        return 0

    try:
        home, desc = _prepare_memory(plan["mode"], plan["home"], plan["url"])
    except RuntimeError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    saved = config.save_home(home)
    config.save_config(runtime=plan["runtime"])
    print()
    for line in _install_done_lines(saved, desc):
        print(line)
    return 0


def _find_skill_dir() -> str | None:
    """同梱スキル(watari_cli/skill)の場所を返す。

    スキルはパッケージ本体(src/watari_cli/)の内側に同梱されているため、wheel から
    インストールされていても checkout を直接（editable / PYTHONPATH=src）実行していても、
    importlib.resources で一貫して見つかる（パスを当てずっぽうで探し回らない）。
    それでも解決できない特殊な配置向けに、checkout 相対のパスへ最後にフォールバックする。
    """
    try:
        from importlib import resources

        candidate = resources.files("watari_cli") / "skill"
        if (candidate / "SKILL.md").is_file():
            return str(candidate)
    except (ModuleNotFoundError, FileNotFoundError, NotADirectoryError, TypeError):
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "..", "skill"),
        os.path.join(os.getcwd(), "src", "watari_cli", "skill"),
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
    """ワタリを起動する。スキル・記憶を自動で渡すランチャー（モデルは Pi 側の関心事）。

    ユーザーは長い pi コマンドを覚えなくてよい: watari chat だけでワタリが立ち上がる。
    """
    import shlex
    import subprocess

    config.apply(args.home)
    from watari_cli.engine import watari_lib as wl

    home = wl.MEM
    if not os.path.isdir(home):
        sys.stderr.write(f"記憶が見つかりません: {home}\n  先に `watari install` を実行してください。\n")
        return 1
    skill = _find_skill_dir()
    if not skill:
        sys.stderr.write("同梱スキル(watari_cli/skill)が見つかりません（インストールが壊れている可能性があります）。\n")
        return 1

    settings = config.load_config()
    runtime = args.runtime or settings.get("runtime") or "pi"

    cmd = _runtime_base(runtime) + ["--skill", skill] + args.extra

    env = dict(os.environ)
    env["WATARI_HOME"] = home  # ランタイムの bash ツールが同じ記憶を読めるように

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
    try:
        gen = regen_state.regen(now)
    except FileNotFoundError:
        sys.stderr.write(f"記憶が見つかりません: {wl.MEM}（先に watari init / watari install）\n")
        return 1
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


def _write_validation_errors(error: ValueError) -> int:
    """ValueError(errors) 契約（args[0]=エラー文字列のリスト）を標準形式で stderr に書く。"""
    errors = error.args[0] if error.args else [str(error)]
    sys.stderr.write(f"検証エラー {len(errors)} 件（何も書き込んでいません）:\n")
    for e in errors:
        sys.stderr.write(f"  - {e}\n")
    return 2


def cmd_ingest(args) -> int:
    config.apply(args.home)
    from watari_cli.engine import ingest, watari_lib as wl

    try:
        rows = ingest.load_rows(args.rows)
    except FileNotFoundError as error:
        sys.stderr.write(f"rows ファイルが読めません: {error}\n")
        return 2
    except ValueError as error:
        return _write_validation_errors(error)

    try:
        summary = ingest.apply(
            rows,
            advance_pi=args.advance_pi,
            advance_ext=args.advance_ext or (), allow_new_domain=args.allow_new_domain,
            dry_run=args.dry_run,
        )
    except FileNotFoundError:
        # rows は読めている。記憶(WATARI_HOME)側の log.jsonl が無い＝未初期化のホーム。
        sys.stderr.write(f"記憶が見つかりません: {wl.MEM}（先に watari init / watari install）\n")
        return 1
    except ValueError as error:
        return _write_validation_errors(error)
    print(summary)
    return 0


def cmd_connector_list(args) -> int:
    """宣言済み connector（夢に流し込むソース）を一覧する。"""
    connectors = config.load_connectors()
    if not connectors:
        print("宣言済み connector: なし")
        print('  追加: watari connector add --name <slug> --scope cloud|local --read "..."')
        return 0
    print("宣言済み connector:")
    for c in connectors:
        print(f"  {c.get('name')} [{c.get('scope')}]: {c.get('read') or '—'}")
    return 0


def cmd_connector_add(args) -> int:
    """connector を宣言（同名は更新）。実際の読み取りはエージェントが行い、CLI は宣言だけ持つ。"""
    try:
        connectors = config.save_connector(
            {"name": args.name, "scope": args.scope, "read": args.read})
    except ValueError as error:
        sys.stderr.write(f"{error}\n")
        return 2
    print(f"connector を保存しました: {args.name} [{args.scope}]")
    print(f"  read: {args.read or '—'}")
    print(f"  宣言済み: {', '.join(c['name'] for c in connectors)}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="watari", description="ワタリ — 会話からあなたを覚えていく相棒")
    try:
        from importlib.metadata import version

        p.add_argument("--version", action="version", version=f"watari {version('watari-cli')}")
    except Exception:
        pass
    sub = p.add_subparsers(dest="command", required=True)

    ps = sub.add_parser("status", help="ワタリの記憶の現在地を読む")
    ps.add_argument("--home", help="記憶の場所（既定: WATARI_HOME か保存済み設定）")
    ps.set_defaults(func=cmd_status)

    ph = sub.add_parser("host", help="このマシンの環境を記録し、他マシンの記録も一覧")
    ph.add_argument("--home", help="記憶の場所（既定: WATARI_HOME か保存済み設定）")
    ph.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="自由記述の事実を記録（例 terminal=Ghostty）。繰り返し可")
    ph.set_defaults(func=cmd_host)

    pd = sub.add_parser("dream", help="会話ログから記憶の候補を抽出（読むだけ）")
    pd.add_argument("--home", help="記憶の場所")
    pd.add_argument("--json", action="store_true", help="判定用に生の候補(messages[])をJSON出力")
    pd.set_defaults(func=cmd_dream)

    pr = sub.add_parser("recall", help="記憶の現在地(life/learning state)をJSONで読む")
    pr.add_argument("--home", help="記憶の場所")
    pr.set_defaults(func=cmd_recall)

    pa = sub.add_parser("audit", help="記憶の健全性を監査（決定論・形式・乖離）")
    pa.add_argument("--home", help="記憶の場所")
    pa.add_argument("--coverage", action="store_true", help="log に現れないセッションも列挙")
    pa.set_defaults(func=cmd_audit)

    pn = sub.add_parser("init", help="空の記憶を新規作成")
    pn.add_argument("--home", help="作成先のパス（既定: WATARI_HOME）")
    pn.add_argument("--force", action="store_true", help="空でない場所でも続行")
    pn.set_defaults(func=cmd_init)

    pg = sub.add_parser("regen", help="log から state を再生成（clone 直後の復元・派生の作り直し）")
    pg.add_argument("--home", help="記憶の場所")
    pg.add_argument("--now", help="再生成時刻(UTC ISO)。省略時は現在時刻")
    pg.add_argument("--check", action="store_true", help="書き込まず現 state と比較")
    pg.set_defaults(func=cmd_regen)

    pinst = sub.add_parser("install", help="初回セットアップ（対話。記憶を用意して設定を保存）")
    pinst.add_argument("--home", help="記憶の場所（既定: XDG_DATA_HOME/watari/memory）")
    pinst.add_argument("--from", dest="from_url", metavar="GIT_URL",
                       help="バックアップ(git)から記憶を復元する")
    pinst.add_argument("--runtime", help="起動ランタイム（既定 pi）。watari chat が使う")
    pinst.add_argument("--yes", "-y", action="store_true", help="質問せず既定のまま（コマンド一発）")
    pinst.add_argument("--dry-run", action="store_true", help="UX だけ試す（何も変更しない・何度でも）")
    pinst.set_defaults(func=cmd_install)

    pc = sub.add_parser("chat", help="ワタリを起動（スキル/記憶/モデルを自動で渡す）")
    pc.add_argument("--home", help="記憶の場所")
    pc.add_argument("--runtime", help="起動ランタイム（既定: 保存値か pi）")
    pc.add_argument("--show", action="store_true", help="起動せず、実行するコマンドだけ表示")
    pc.add_argument("extra", nargs="*", help="ランタイムへ素通しする追加引数")
    pc.set_defaults(func=cmd_chat)

    pi = sub.add_parser("ingest", help="判定済みの記憶行(JSON)を記憶へ書き込む")
    pi.add_argument("--rows", required=True, help="log 行の JSON 配列ファイル(SCHEMA 準拠)")
    pi.add_argument("--home", help="記憶の場所")
    pi.add_argument("--advance-pi")
    pi.add_argument("--advance-ext", action="append", default=[], metavar="NAME=TS")
    pi.add_argument("--allow-new-domain", action="store_true")
    pi.add_argument("--dry-run", action="store_true", help="検証と件数だけ（書き込みなし）")
    pi.set_defaults(func=cmd_ingest)

    # connector は WATARI_HOME ではなく config.json に宣言する（記憶の場所に依らず全マシン共通の宣言）。
    pcon = sub.add_parser("connector", help="夢に流し込むソース(connector)を宣言/一覧")
    consub = pcon.add_subparsers(dest="connector_command", required=True)
    pcl = consub.add_parser("list", help="宣言済み connector を一覧")
    pcl.set_defaults(func=cmd_connector_list)
    pca = consub.add_parser("add", help="connector を宣言（追加/更新）")
    pca.add_argument("--name", required=True, help="小文字スラッグ（例 mail, tasks）")
    pca.add_argument("--scope", required=True, choices=["cloud", "local"],
                     help="cloud=担当1台だけが夢を見る / local=各マシンが自分で読む")
    pca.add_argument("--read", required=True,
                     help="このソースを cursor 以降どう読むかのエージェント向け自由指示")
    pca.set_defaults(func=cmd_connector_add)
    return p


def main() -> int:
    args = _build_parser().parse_args()
    return args.func(args)
