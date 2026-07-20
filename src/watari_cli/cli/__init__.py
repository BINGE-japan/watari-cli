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
    from watari_cli import git_sync
    from watari_cli.engine import extract, watari_lib as wl

    git_sync.sync_before_read(wl.MEM)
    _ensure_state()
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


def _ensure_state() -> None:
    """state.json が無い/古い場合に log から再生成する（state は派生物＝いつでも作り直せる）。

    起きる状況: カセットを clone した直後（state は gitignore で運ばれない）、pull で log だけが
    進んだ直後。読む側(recall/chat/dream)が呼ぶことで「state 無し=null」や陳腐化を防ぐ。"""
    from watari_cli.engine import watari_lib as wl

    for genre in wl.GENRES:
        try:
            log_m = os.path.getmtime(wl.log_path(genre))
        except OSError:
            continue  # log が無い＝未初期化。ここでは扱わない（install/init の責務）
        try:
            state_m = os.path.getmtime(wl.state_path(genre))
        except OSError:
            state_m = None
        if state_m is None or state_m < log_m:
            try:
                _rebuild_state()  # regen して state.json へ書き出すところまで
            except Exception:
                pass  # 再生成失敗で読み全体を止めない（従来挙動＝あるものを読む）
            return


def cmd_recall(args) -> int:
    config.apply(args.home)
    from watari_cli import git_sync
    from watari_cli.engine import watari_lib as wl

    git_sync.sync_before_read(wl.MEM)
    _ensure_state()
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
            # 既定に ~/.claude の原本を出さない：adopt は state を書き戻すので、原本を指すと
            # ~/.claude を書き換えてオリジナルワタリを壊しうる。カセットの複製/クローンを指させる。
            home = prompts.text("記憶のあるフォルダ（カセットの場所）", default=default_dir)
            url = None
        else:  # new: 保存先は聞かず既定を使う
            home = default_dir
            url = None
        mode = kind

    # 2) マルチマシン同期（git remote）。clone は既に origin あり。それ以外は選ばせる／--remote で指定。
    interactive = not (args.from_url or args.home or args.yes)
    if mode == "clone":
        git_remote = None  # clone 先には既に origin が設定される
    elif args.remote:
        git_remote = args.remote
    elif not interactive:
        git_remote = None  # 非対話の既定はローカルのみ（--remote で上書き）
    else:
        choice = prompts.select(
            "記憶を別のマシンとも同期しますか？（git remote＝バックアップにもなる）", [
                ("同期する（git remote を設定）", "remote"),
                ("このマシンだけで使う（同期もバックアップも無し）", "local"),
            ], default=0)
        git_remote = (prompts.text("記憶リポの git URL") if choice == "remote" else None) or None

    return {"mode": mode, "home": home, "url": url, "runtime": args.runtime,
            "git_remote": git_remote}


def _install_done_lines(home: str, desc: str, git_remote: str | None = None,
                        mode: str | None = None) -> list[str]:
    lines = [f"✓ セットアップ完了（{desc}）", f"  記憶の場所: {home}"]
    if git_remote:
        lines.append(f"  同期: {git_remote}")
    elif mode != "clone":
        lines.append("  同期: このマシンのみ（別マシンと共有せず・バックアップも無し）")
    lines.append("  起動:  watari chat")
    return lines


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
        sync = (f"git remote と同期（{plan['git_remote']}）" if plan["git_remote"]
                else "clone 元と同期（origin 既設）" if plan["mode"] == "clone"
                else "このマシンのみ（同期なし）")
        print("\n── プレビュー（--dry-run：実際には何も変更していません）──")
        print(f"  記憶: {act} → {target}")
        print(f"  同期: {sync}")
        print("  実行時: 記憶を用意 → state 再生成 →(remote 指定時)git 設定+push → 設定保存(config.json)")
        print("  完了時の表示 ↓")
        for line in _install_done_lines(target, act, plan["git_remote"], plan["mode"]):
            print("    " + line)
        return 0

    try:
        home, desc = _prepare_memory(plan["mode"], plan["home"], plan["url"])
    except RuntimeError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    saved = config.save_home(home)
    config.save_config(runtime=plan["runtime"])
    if plan["git_remote"]:
        from watari_cli import git_sync
        ok, message = git_sync.setup_remote(saved, plan["git_remote"])
        print(("✓ " if ok else "! ") + message)
    # Google 認証（発話中継所）。client_id/secret が設定済みかつ未認証・対話時のみ承認を促す。
    # 実体は watari auth と同じ _google_auth_flow（creds は既にあるので追加入力は求めない）。
    from watari_cli import cloud
    if cloud.is_configured() and not cloud.is_authorized() and not args.yes:
        from watari_cli import prompts
        if prompts.confirm("Google Drive と会話を同期しますか？（別マシンのワタリが夢に見れる）", default=True):
            ok, message = _google_auth_flow(prompt_for_creds=False)
            print(("✓ " if ok else "! ") + message)
    print()
    for line in _install_done_lines(saved, desc, plan["git_remote"], plan["mode"]):
        print(line)
    return 0


def _google_auth_flow(prompt_for_creds: bool) -> tuple[bool, str]:
    """Google 認証の共通経路（install の承認プロンプトも watari auth もここを通る）。

    client_id/secret を env>config で解決し、無ければ（prompt_for_creds のとき）対話入力させて
    config.json に保存する。その後 loopback フローで承認し refresh token を保存。(ok, メッセージ)。
    """
    from watari_cli import cloud, prompts

    cid, csec = cloud.credentials()
    if not (cid and csec):
        if not prompt_for_creds:
            return False, "Google の client_id/secret 未設定（`watari auth` で設定できます）"
        print("Google OAuth の client_id / client_secret を入力してください")
        print("（未登録なら docs/google-oauth-setup.md の手順で発行）。")
        cid = cid or prompts.text("client_id")
        csec = csec or prompts.text("client_secret")
        if not (cid and csec):
            return False, "client_id/secret が空のため中止しました"
    cloud.save_credentials(cid, csec)  # env 由来でも config に保存し、以後の token 更新を無人化
    return cloud.authorize()


def cmd_auth(args) -> int:
    """Google 認証（発話中継所＝Drive appDataFolder）を単独で行う。

    初回は env か対話入力で client_id/secret を受け取り config.json に保存 → ブラウザ承認。
    以後は保存値で再承認/更新できる（token 失効時の再ログインもこれ一発）。
    """
    ok, message = _google_auth_flow(prompt_for_creds=True)
    print(("✓ " if ok else "! ") + message)
    return 0 if ok else 1


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


def _state_dir() -> str:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    d = os.path.join(base, "watari")
    os.makedirs(d, exist_ok=True)
    return d


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _dream_recently(lock_path: str, window: float = 300.0) -> bool:
    """直近 window 秒に夢が走った、または今も走っているなら True（二重起動ガード）。"""
    import time
    try:
        with open(lock_path, encoding="utf-8") as f:
            lock = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return False
    if lock.get("pid") and _pid_alive(lock["pid"]):
        return True
    return (time.time() - lock.get("ts", 0)) < window


def _spawn_background_dream(home: str, runtime: str, skill: str) -> None:
    """chat 起動時に裏で夢（「夢を見て」）を回す。起動をブロックしない。二重起動は lock でガードし、
    自分が dream worker（WATARI_SKIP_AUTO_DREAM）なら回さない＝再帰しない。夜間 cron の代替。"""
    import subprocess
    import time

    if os.environ.get("WATARI_SKIP_AUTO_DREAM"):
        return
    lock_path = os.path.join(_state_dir(), "dream.lock")
    if _dream_recently(lock_path):
        return
    cmd = _runtime_base(runtime) + [
        "--no-skills", "--append-system-prompt", os.path.join(skill, "SKILL.md"),
        "--no-session", "-p", "夢を見て"]
    env = dict(os.environ)
    env["WATARI_HOME"] = home
    env["WATARI_SKIP_AUTO_DREAM"] = "1"
    try:
        proc = subprocess.Popen(
            cmd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return
    try:
        with open(lock_path, "w", encoding="utf-8") as f:
            json.dump({"pid": proc.pid, "ts": time.time()}, f)
    except OSError:
        pass


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
    if not args.show:
        from watari_cli import git_sync
        git_sync.sync_before_read(home)  # 起動前に最新の記憶を取り込む
        _ensure_state()  # clone/pull 直後でも state を最新に（派生物の遅延再生成）
    skill = _find_skill_dir()
    if not skill:
        sys.stderr.write("同梱スキル(watari_cli/skill)が見つかりません（インストールが壊れている可能性があります）。\n")
        return 1

    settings = config.load_config()
    runtime = args.runtime or settings.get("runtime") or "pi"

    # ワタリは「オンデマンドで呼ぶスキル」でなく常時オンの人格。--skill 渡しだとモデルが自動発動せず
    # 素の助手のまま応答する（実測）。SKILL.md をシステムプロンプトに常時注入して人格を起動する。
    # --no-skills で他スキルの自動探索（~/.agents/skills 等の同名 "watari" 衝突含む）も切る。
    skill_md = os.path.join(skill, "SKILL.md")
    cmd = _runtime_base(runtime) + ["--no-skills", "--append-system-prompt", skill_md] + args.extra

    env = dict(os.environ)
    env["WATARI_HOME"] = home  # ランタイムの bash ツールが同じ記憶を読めるように

    if args.show:
        print(f"WATARI_HOME={home}")
        print(" ".join(shlex.quote(c) for c in cmd))
        return 0

    import signal
    from watari_cli import host, relay

    relayer = relay.Relay(wl.PI_STORE, host.machine_id(), home=home)
    relayer.start()  # 会話を別マシンへ中継（クラウド未認証なら内部で no-op）
    _spawn_background_dream(home, runtime, skill)  # 裏で夢を回す（非ブロッキング・二重起動ガード）

    def _on_term(signum, frame):  # SIGTERM でも最終 flush してから抜ける
        relayer.stop_and_flush()
        os._exit(128 + signum)

    prev_term = signal.signal(signal.SIGTERM, _on_term)
    try:
        return subprocess.run(cmd, env=env).returncode
    except FileNotFoundError:
        sys.stderr.write(
            f"ランタイム '{runtime}' が起動できません（{cmd[0]} が見つからない）。\n"
            "  Pi を使うなら `npx -y @earendil-works/pi-coding-agent` が通るか確認してください。\n"
        )
        return 127
    except KeyboardInterrupt:
        return 130
    finally:
        signal.signal(signal.SIGTERM, prev_term)
        relayer.stop_and_flush()  # 正常/SIGINT/例外いずれも最終 flush


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
            advance_pi=args.advance_pi, advance_cloud=args.advance_cloud or (),
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
    if not args.dry_run:
        from watari_cli import git_sync, relay
        git_sync.sync_after_write(wl.MEM)  # 書いた記憶を commit→pull→push（offline は繰り越し）
        relay.prune_cloud(wl.MEM)          # 全マシンが夢に見た分＋90日超の共有発話を削除
    return 0


def cmd_connector_list(args) -> int:
    """宣言済み connector（夢に流し込むソース）を一覧する。組み込み/カスタムを区別して表示。"""
    from watari_cli import connectors as connectors_mod

    decls = config.load_connectors()
    if not decls:
        print("宣言済み connector: なし")
        print("  追加: watari connect <service>（組み込み） / "
              'watari connector add --name <slug> --scope cloud|local --read "..."（カスタム）')
        return 0
    print("宣言済み connector:")
    for c in decls:
        name = c.get("name")
        if connectors_mod.is_builtin_name(name):
            mark = "✅" if connectors_status(name) else "⬜"
            kind = "組み込み"
        else:
            mark = "🔧"
            kind = "カスタム"
        print(f"  {mark} {name} [{c.get('scope')}] ({kind}): {c.get('read') or '—'}")
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


def cmd_connector_read(args) -> int:
    """組み込みコネクタをカーソル(--since、省略時はこのマシンの host カーソル)以降で読む。

    決定論リーダー: 実 API を叩いて統一形式 {ts,uuid,text,meta} の配列を返すだけで、
    カーソルの前進はしない（前進は従来どおり `watari ingest --advance-ext` のみが行う）。
    認証エラー・ネットワーク断は明確な非ゼロ終了で返す（呼び出し側はカーソル据え置きで扱える）。
    """
    config.apply(args.home)
    from watari_cli import connectors as connectors_mod, host
    from watari_cli.engine import watari_lib as wl

    since = args.since or host.load_cursors(wl.MEM).get(args.name)
    try:
        rows = connectors_mod.read(args.name, since)
    except connectors_mod.ConnectorError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0
    print(f"connector: {args.name}")
    print(f"  since: {since or '—'}")
    print(f"  件数: {len(rows)}")
    if rows:
        print(f"  max_ts: {rows[-1]['ts']}")
    return 0


def _declare_builtin_connector(name: str, message: str) -> int:
    """成功時の共通の締め（connector 宣言 → 完了表示）。paste/oauth 両経路から呼ぶ。"""
    config.save_connector({
        "name": name, "scope": "cloud",
        "read": f"組み込み: `watari connector read {name}` で読む",
    })
    print(f"✓ 接続しました（{message} として認証）")
    return 0


def _connect_wizard(name: str) -> int:
    """1サービス分の接続体験: 案内 → 認証 → config 保存 → connector 宣言。

    サービスごとの分岐はここに書かない——レジストリ(connectors.REGISTRY)から引いた
    ServiceAdapter を汎用に駆動するだけ。新サービスはレジストリに1件足せばここを触らず動く。
    分岐は auth_kind の2種類だけ（paste=トークン貼り付け / oauth=cloud.py の共有 Google 認可）。
    """
    from watari_cli import connectors as connectors_mod, prompts

    service = connectors_mod.get_service(name)
    if service is None:
        sys.stderr.write(f"不明なサービスです: {name}\n")
        return 2
    if not service.implemented:
        print(f"{service.label}: 未対応です。対応予定。")
        return 0
    if connectors_status(name):
        print(f"{service.label} は接続済みです（続けると再接続します）。")
    print(f"{service.label} と接続します。")
    for line in service.guide:
        print(f"  {line}")

    if service.auth_kind == "oauth":
        ok, message = service.verify()
        if not ok:
            sys.stderr.write(f"! 接続に失敗しました: {message}\n")
            return 1
        return _declare_builtin_connector(name, message)

    try:
        api_key = prompts.text("貼り付けてください")
    except prompts.Cancelled:
        sys.stderr.write("\n中止しました。\n")
        return 130
    if not api_key:
        sys.stderr.write("キーが空のため中止しました。\n")
        return 1
    ok, message = service.verify(api_key)
    if not ok:
        sys.stderr.write(f"! 接続に失敗しました: {message}\n")
        return 1
    connectors_mod.save_auth(name, api_key)
    return _declare_builtin_connector(name, message)


def _menu_label(name: str, service) -> str:
    """メニュー1行の表示。状態は行頭の記号で示す（縦に並んだとき目が拾いやすい）。

    ✅ 接続済み / ⬜ 未接続 / 🚧 未対応。記号だけに頼らず語も添える（記号が化ける端末・
    読み上げ環境でも意味が落ちないように）。"""
    if not service.implemented:
        return f"🚧 {service.label}（対応予定）"
    if connectors_status(name):
        return f"✅ {service.label}（接続済み）"
    return f"⬜ {service.label}"


def connectors_status(name: str) -> bool:
    """そのサービスが接続済みか（表示用の薄いラッパー）。"""
    from watari_cli import connectors as connectors_mod

    try:
        return connectors_mod.is_connected(name)
    except Exception:
        return False  # 判定できない回は未接続扱い（表示のために失敗させない）


def cmd_connect(args) -> int:
    """`watari connect [service]`。引数なしは選択メニュー（レジストリを列挙するだけ）。

    対話ウィザードなので、非対話シェル（エージェントのツール実行・パイプ）から呼ばれたら
    黙って既定値で進まず、ユーザー本人のターミナルで打つよう即座に案内して終了する。"""
    from watari_cli import connectors as connectors_mod, prompts

    if not sys.stdin.isatty() and not os.environ.get("WATARI_CONNECT_ALLOW_NO_TTY"):
        sys.stderr.write(
            "watari connect は対話コマンドです。ユーザー本人のターミナルで実行してください\n"
            "（エージェントは代行せず、打つコマンドを案内すること）。\n")
        return 2

    name = args.service
    if not name:
        options = [(_menu_label(key, s), key) for key, s in connectors_mod.list_services()]
        try:
            name = prompts.select("接続するサービスを選んでください", options, default=0)
        except prompts.Cancelled:
            sys.stderr.write("\n中止しました。\n")
            return 130
    return _connect_wizard(name)


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
    pinst.add_argument("--remote", metavar="GIT_URL",
                       help="記憶を同期する git remote（新規/引き継ぎ時）。省略かつ対話なら menu で選べる")
    pinst.add_argument("--yes", "-y", action="store_true", help="質問せず既定のまま（コマンド一発）")
    pinst.add_argument("--dry-run", action="store_true", help="UX だけ試す（何も変更しない・何度でも）")
    pinst.set_defaults(func=cmd_install)

    pauth = sub.add_parser("auth", help="Google 認証（会話をマシン間で同期する中継所にログイン）")
    pauth.set_defaults(func=cmd_auth)

    pconn = sub.add_parser("connect", help="組み込みコネクタと接続（案内→貼り付け→疎通確認→保存）")
    pconn.add_argument("service", nargs="?", help="接続するサービス（例 linear）。省略時は選択メニュー")
    pconn.set_defaults(func=cmd_connect)

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
    pi.add_argument("--advance-cloud", action="append", default=[], metavar="MACHINE=TS")
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
    pcr = consub.add_parser("read", help="組み込みコネクタをカーソル以降で決定論的に読む")
    pcr.add_argument("name", help="組み込みコネクタ名（例 linear）")
    pcr.add_argument("--home", help="記憶の場所（host カーソルの既定値解決に使う）")
    pcr.add_argument("--since", help="この ts 以降を読む（省略時: このマシンの host カーソル）")
    pcr.add_argument("--json", action="store_true", help="統一形式 {ts,uuid,text,meta} をJSON配列で出力")
    pcr.set_defaults(func=cmd_connector_read)
    return p


def main() -> int:
    args = _build_parser().parse_args()
    return args.func(args)
