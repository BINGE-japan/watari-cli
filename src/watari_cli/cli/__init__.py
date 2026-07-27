"""watari コマンドの入口。

ワタリ本体は記憶を内蔵せず、--home / 環境変数 WATARI_HOME で指した記憶フォルダを読み書きする。
記憶は会話ログから育つ個人データ（log.jsonl が記録の原本、state.json は自動生成のまとめ）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from watari_cli import config

# トップの --help は argparse の自動整形を使わず、この見本どおりに出す
# （一般ユーザー向けと内部コマンドを分け、最初の一歩から迷わないように）。
_TOP_HELP = """\
ワタリ — 会話からあなたを覚えていく相棒

はじめかた:
  watari install   初回セットアップ（記憶フォルダを用意します）
  watari chat      ワタリと話す

よく使うコマンド:
  install   初回セットアップ（記憶フォルダの用意と設定の保存）
  chat      ワタリと話す（Pi を起動します）
  performance  返信速度と記憶の詳しさを選ぶ
  connect   外部サービスと接続（Gmail・カレンダー・Slack など）
  brief     期限・予定・未返信・未読をまとめて確認
  status    記憶の様子を確認
  auth      Google にログイン（複数のパソコンで会話を同期する場合）

内部コマンド（ワタリが自動で使います。手で打つ必要はありません）:
  scan / recall / ingest / audit / regen / init / host / connector

詳しくは: watari <コマンド> --help
"""

# --home の説明は全コマンドで統一する（install だけ「保存先」の意味になるので別文言）。
_HOME_HELP = "記憶フォルダの場所（普段は指定不要。install で保存済みの場所を使います）"


def _translate_parser_error(message: str) -> str:
    """argparse の英語エラーを日本語にする。打ち間違いは difflib で候補を出す。"""
    import difflib
    import re

    m = re.search(r"argument (\S+): invalid choice: '([^']*)' \(choose from (.*)\)", message)
    if m:
        dest, value, raw = m.group(1), m.group(2), m.group(3)
        choices = [c.strip().strip("'\"") for c in raw.split(",")]
        visible = [c for c in choices if c != "dream"]  # 隠し alias は候補に出さない
        # サブコマンド位置のエラーか（dest 名のほか、metavar "{install,...}" 表記でも判定）
        if dest in ("command", "connector_command") or dest.startswith("{"):
            hints = difflib.get_close_matches(value, visible, n=2)
            lines = [f"'{value}' は不明なコマンドです。"]
            if hints:
                lines.append(f"もしかして: {' / '.join(hints)} ?")
            lines.append("一覧は watari --help で確認できます。")
            return "\n".join(lines)
        return f"'{value}' は使えない値です（使える値: {', '.join(visible)}）"
    m = re.search(r"the following arguments are required: (.+)", message)
    if m:
        needed = m.group(1).strip()
        if needed == "connector_command":
            return "サブコマンドを指定してください（list / add / read）"
        if needed == "command":
            return ("コマンドを指定してください。\n"
                    "はじめて使う場合: watari install → watari chat（一覧: watari --help）")
        return f"必要な引数が指定されていません: {needed}"
    m = re.search(r"unrecognized arguments: (.+)", message)
    if m:
        return f"不明な引数です: {m.group(1)}"
    m = re.search(r"argument (\S+): expected one argument", message)
    if m:
        return f"{m.group(1)} には値が必要です"
    return message


class _ArgumentParser(argparse.ArgumentParser):
    """エラーを日本語で出す ArgumentParser（全サブコマンド共通）。"""

    def error(self, message):  # noqa: D102 - argparse の上書き
        self.print_usage(sys.stderr)
        self.exit(2, "エラー: " + _translate_parser_error(message) + "\n")


class _TopParser(_ArgumentParser):
    """トップレベル専用: --help を自前整形（_TOP_HELP の見本どおり）で出す。"""

    def format_help(self):  # noqa: D102
        return _TOP_HELP


def _next_steps(*lines: str) -> None:
    """コマンド終端の「次の一歩」表示（全コマンド共通の形）。"""
    print()
    print("次の一歩:")
    for line in lines:
        print(f"  ・{line}")


def _setup_required() -> int:
    """未セットアップ（記憶フォルダ不在）の統一案内。traceback を出さず exit 1。"""
    from watari_cli.engine import watari_lib as wl

    sys.stderr.write(wl.MSG_SETUP_REQUIRED + "\n")
    return 1


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


def _cursor_label(key: str) -> str:
    """読み取り位置キーの表示名（内部キーの生値をそのまま並べない）。"""
    if key == "transcripts_pi":
        return "このパソコンの会話ログ"
    if key == "last_run":
        return "最後に整理した時刻"
    if key.startswith("cloud_"):
        return f"共有された会話（{key[len('cloud_'):]}）"
    return key  # connector 宣言名はユーザーが付けた名前なのでそのまま


def cmd_status(args) -> int:
    config.apply(args.home)
    from watari_cli import host
    from watari_cli.engine import watari_lib as wl

    home = wl.MEM
    if not os.path.isdir(home):
        return _setup_required()
    print(f"記憶の場所: {home}")
    counts = {g: _count_lines(wl.log_path(g)) or 0 for g in wl.GENRES}
    life = _load_json(wl.state_path("life")) or {}
    learning = _load_json(wl.state_path("learning")) or {}
    domains = learning.get("domains", {})
    topics = sum(len(d.get("topics", {})) for d in domains.values())
    print(f"  生活の記憶: {counts['life']} 件"
          f"（進行中の話題 {len(life.get('open_threads', []))}・"
          f"関心 {len(life.get('interests', {}))}・"
          f"プロフィール {len(life.get('profile', {}))} 項目）")
    print(f"  学習の記憶: {counts['learning']} 件（分野 {len(domains)}・トピック {topics}）")
    # 読み取り位置はこのパソコンの host 記録から（旧 cursors.json があれば初回に移行して読む）
    cursors = {k: v for k, v in host.load_cursors(home).items() if v}
    if cursors:
        print("  どこまで読んだかの記録:")
        for key, value in cursors.items():
            print(f"    {_cursor_label(key)}: {value}")
    _next_steps("話す: watari chat", "サービスを繋ぐ: watari connect")
    return 0


def cmd_host(args) -> int:
    config.apply(args.home)
    from watari_cli import host
    from watari_cli.engine import watari_lib as wl

    home = wl.MEM
    if not os.path.isdir(home):
        return _setup_required()
    for pair in args.set:
        if "=" not in pair:
            sys.stderr.write(f"--set は KEY=VALUE 形式で指定してください: {pair}\n")
            return 2
        key, value = pair.split("=", 1)
        host.set_fact(home, key, value)
    record = host.refresh(home)
    print(f"このパソコンの識別子: {record['machine_id']}")
    print(f"  ホスト名: {record['hostname']}")
    print(f"  環境: {record['platform']} / Python {record['python']}")
    print(f"  シェル: {record['shell'] or '—'}")
    print(f"  検出した AI ツール: {', '.join(record['ai_clis']) or '—'}")
    for key, value in record["facts"].items():
        print(f"  記録 {key}: {value}")
    others = [r for r in host.all_hosts(home) if r.get("machine_id") != record["machine_id"]]
    if others:
        print("他のパソコン:")
        for r in others:
            facts = " ".join(f"{k}={v}" for k, v in (r.get("facts") or {}).items())
            clis = ",".join(r.get("ai_clis") or []) or "—"
            line = f"  {r.get('machine_id')}: {r.get('platform')} AIツール={clis}"
            print(line + (f" [{facts}]" if facts else ""))
    return 0


def cmd_scan(args) -> int:
    config.apply(args.home)
    from watari_cli import git_sync
    from watari_cli.engine import extract, watari_lib as wl

    if not os.path.isdir(wl.MEM):
        return _setup_required()
    git_sync.sync_before_read(wl.MEM)
    _ensure_state()
    result = extract.run()
    if args.json:
        # 選別するワタリ(エージェント)が消費する生の候補。messages[] を渡す。
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    print("会話ログから記憶の候補を集めました（まだ何も書き込んでいません。"
          "通常はワタリが自動で実行します）")
    for store, info in result["stores"].items():
        print("  " + extract.render_store_summary(store, info))
    print(f"  合計候補: {len(result['messages'])} 件")
    print("  → この後の選別と書き込みはワタリが自動で行います")
    return 0


def _ensure_state() -> None:
    """state.json（自動生成のまとめ）が無い/古い場合に log から作り直す。

    起きる状況: 記憶フォルダを clone した直後（state は gitignore で運ばれない）、pull で log
    だけが進んだ直後。読む側(recall/chat/scan)が呼ぶことで「state 無し=null」や陳腐化を防ぐ。"""
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

    if not os.path.isdir(wl.MEM):
        return _setup_required()  # null だけの JSON を出さない（JSON 契約は正常系のみ）
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

    try:
        problems, infos, cov = audit.audit_report(args.coverage)
    except FileNotFoundError:
        return _setup_required()
    # 表示文言の正本は engine 側（render_report）。cli は書き出すだけで二重整形しない。
    for line in audit.render_report(problems, infos, cov):
        print(line)
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
    # 読み取り位置はパソコンごとの host 記録に持つ（hosts/<machine_id>.json の "cursors"）。
    # 初回の advance / status で遅延生成されるので、ここでは作らない。
    # 記憶の git 設定（複数パソコンからの追記の union-merge / 自動生成の state は追跡しない）
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
        sys.stderr.write(
            f"この場所には既にファイルがあります: {home}\n"
            "  既存の記憶を使うなら `watari install`（「このパソコンにある記憶フォルダを使う」を選択）、\n"
            "  上書き覚悟で新規作成するなら `watari init --force` を実行してください。\n")
        return 1
    _scaffold_empty_memory()
    print(f"空の記憶を用意しました: {home}")
    _next_steps(
        f"watari install --home {home} で設定に登録すると、watari chat から使えます",
        "持ち運び: このフォルダを非公開の git リポジトリに置けば、"
        "別のパソコンで watari install --from <URL> で記憶ごと復元できます",
    )
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
            raise RuntimeError(
                f"復元先のフォルダが空ではありません: {home}\n"
                "  別の場所を --home で指定するか、フォルダを空にしてからやり直してください。")
        os.makedirs(os.path.dirname(home) or ".", exist_ok=True)
        clone = subprocess.run(["git", "clone", url, home], capture_output=True, text=True)
        if clone.returncode != 0:
            raise RuntimeError(
                "バックアップの取得に失敗しました。URL の綴りと、そのリポジトリへの"
                "アクセス権（SSH 鍵の設定）を確認して、もう一度 watari install を実行してください。\n"
                f"--- git の出力 ---\n{clone.stderr}")
        config.apply(home)
        _rebuild_state()
        return home, "バックアップから復元（記憶を引き継ぎ）"
    config.apply(home)
    if mode == "adopt":
        if not (os.path.isdir(home) and os.listdir(home)):
            raise RuntimeError(
                f"指定のフォルダに記憶が見つかりません: {home}\n"
                "  場所を確認するか、`watari install` で「新しく始める」を選んでください。")
        _rebuild_state()
        return home, "今ある記憶をそのまま使う"
    if os.path.isdir(home) and os.listdir(home):
        raise RuntimeError(
            f"この場所には既にワタリの記憶があります: {home}\n"
            "  そのまま使う場合は、`watari install` で"
            "「このパソコンにある記憶フォルダを使う」を選んでください。")
    _scaffold_empty_memory()
    return home, "新しい記憶を作成"


def _has_existing_memory(path: str) -> bool:
    """そのフォルダにワタリの記憶（life/ か learning/）があるか。"""
    return any(os.path.isdir(os.path.join(path, sub)) for sub in ("life", "learning"))


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
        options = []
        if _has_existing_memory(default_dir):
            # 再実行の行き止まり解消: 既定保存先に記憶があるなら「そのまま使う」を先頭・既定に
            options.append((f"今ある記憶をそのまま使う（{default_dir}）", "adopt-default"))
        options += [
            ("新しく始める", "new"),
            ("このパソコンにある記憶フォルダを使う", "adopt"),
            ("バックアップ（git リポジトリ）から復元する", "clone"),
        ]
        kind = prompts.select("ワタリの記憶を、どこから始めますか？", options, default=0)
        if kind == "adopt-default":
            kind, home, url = "adopt", default_dir, None
        elif kind == "clone":
            url = prompts.text(
                "バックアップの場所（git の URL。"
                "例: git@github.com:あなたの名前/watari-memory.git）")
            home = default_dir  # 保存先は既定で十分。こだわる人は --home で上書き
        elif kind == "adopt":
            # 既定で「他ツールが管理している記憶フォルダの原本」を指させない：adopt は state を
            # 書き戻すため、原本を直接指すとそちらを書き換えてしまう。複製したフォルダを指定させる。
            home = prompts.text(
                "記憶のあるフォルダ（以前ワタリが使っていた記憶フォルダの場所）",
                default=default_dir)
            url = None
        else:  # new: 保存先は聞かず既定を使う
            home = default_dir
            url = None
        mode = kind

    # 2) 複数パソコンの同期（git リポジトリ）。clone は既に origin あり。それ以外は選ばせる。
    interactive = not (args.from_url or args.home or args.yes)
    if mode == "clone":
        git_remote = None  # clone 先には既に origin が設定される
    elif args.remote:
        git_remote = args.remote
    elif not interactive:
        git_remote = None  # 非対話の既定はローカルのみ（--remote で上書き）
    else:
        choice = prompts.select(
            "記憶を他のパソコンと共有・バックアップしますか？（git リポジトリの URL が必要です）", [
                ("このパソコンだけで使う（あとから設定できます）", "local"),
                ("git リポジトリと同期する", "remote"),
            ], default=0)
        git_remote = None
        if choice == "remote":
            print("GitHub などに空のプライベートリポジトリを先に作り、その URL を貼ってください。")
            git_remote = prompts.text(
                "git リポジトリの URL（例: git@github.com:あなたの名前/watari-memory.git）") or None
            if not git_remote:
                # 空 Enter を黙って「同期なし」に落とさない（結果が反転したことを必ず伝える）
                print("URL が入力されなかったため、同期なしで続けます。"
                      "あとから watari install --remote <URL> で設定できます。")

    return {"mode": mode, "home": home, "url": url, "runtime": args.runtime,
            "git_remote": git_remote}


def _install_done_lines(home: str, desc: str, git_remote: str | None = None,
                        mode: str | None = None) -> list[str]:
    lines = [f"✓ セットアップ完了（{desc}）",
             f"  記憶の保存場所: {home}",
             "    （記憶はこのフォルダの中だけに保存されます。中身はいつでも見られます）"]
    if git_remote:
        lines.append(f"  同期: {git_remote}")
    elif mode == "clone":
        lines.append("  同期: 復元元の git リポジトリと同期します")
    else:
        lines.append("  同期: このパソコンのみ（バックアップなし）。あとで同期するには"
                     " `watari install --remote <git URL>` を実行し、"
                     "「今ある記憶をそのまま使う」を選んでください")
    lines += [
        "",
        "次の一歩:",
        "  ・話す: watari chat",
        "  ・サービスを繋ぐ: watari connect（Gmail・カレンダー・Slack など。あとからでも構いません）",
    ]
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
        act = {"new": "新しい記憶を作成", "adopt": "今ある記憶をそのまま使う",
               "clone": f"バックアップから復元（{plan['url']}）"}[plan["mode"]]
        sync = (f"git リポジトリと同期（{plan['git_remote']}）" if plan["git_remote"]
                else "復元元と同期（設定済み）" if plan["mode"] == "clone"
                else "このパソコンのみ（同期なし）")
        print("\n── プレビュー（--dry-run: 実際には何も変更していません）──")
        print(f"  記憶: {act} → {target}")
        print(f"  同期: {sync}")
        print("  実行時にすること: 記憶フォルダを用意 → 設定を保存"
              + ("（→ 同期の設定）" if plan["git_remote"] else ""))
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
    # Google 認証（会話の同期）。client_id/secret が設定済みかつ未認証・対話時のみ承認を促す。
    # 実体は watari auth と同じ _google_auth_flow（creds は既にあるので追加入力は求めない）。
    from watari_cli import cloud
    if cloud.is_configured() and not cloud.is_authorized() and not args.yes:
        if prompts.confirm(
                "会話を Google Drive 経由で同期しますか？"
                "（複数のパソコンで同じワタリを使うための機能です。1台だけなら不要です）",
                default=True):
            ok, message = _google_auth_flow(prompt_for_creds=False)
            print(("✓ " if ok else "! ") + message)
    print()
    for line in _install_done_lines(saved, desc, plan["git_remote"], plan["mode"]):
        print(line)
    return 0


# creds 未設定時に表示するインライン手順。docs のリポジトリ相対パスへは誘導しない
# （pip で入れたユーザーの手元に docs/ は無い。要点はこの場で完結させる）。
_GOOGLE_SETUP_GUIDE = """\
Google 連携には、あなた自身の Google Cloud プロジェクトの OAuth クライアント（無料）が必要です。
  1. https://console.cloud.google.com/ を開き、プロジェクトを作成する（既存のものでも可）
  2. 「API とサービス」→「ライブラリ」で「Google Drive API」を有効にする
  3. 「OAuth 同意画面」を設定し、公開ステータスを「本番環境」（In production）にする
  4. 「認証情報」→「認証情報を作成」→「OAuth クライアント ID」を選ぶ
  5. アプリケーションの種類は「デスクトップアプリ」を選んで作成する
  6. 発行された client_id と client_secret を、この下に貼り付けてください
詳しい手順は README の「複数のパソコンで使う」の節にあります。"""


def _google_auth_flow(prompt_for_creds: bool) -> tuple[bool, str]:
    """Google 認証の共通経路（install の承認プロンプトも watari auth もここを通る）。

    client_id/secret を env>config で解決し、無ければ（prompt_for_creds のとき）対話入力させて
    config.json に保存する。その後 loopback フローで承認し refresh token を保存。(ok, メッセージ)。
    """
    from watari_cli import cloud, prompts

    cid, csec = cloud.credentials()
    if not (cid and csec):
        if not prompt_for_creds:
            return False, ("Google 連携は未設定です（任意機能。使う場合は `watari auth` で"
                           "設定できます）")
        print(_GOOGLE_SETUP_GUIDE, flush=True)
        cid = cid or prompts.text("client_id")
        csec = csec or prompts.text("client_secret")
        if not (cid and csec):
            return False, ("client_id / client_secret が空のため中止しました。"
                           "もう一度 `watari auth` を実行して入力してください")
    cloud.save_credentials(cid, csec)  # env 由来でも config に保存し、以後の token 更新を無人化
    if sys.stdin.isatty():
        # ブラウザを突然開かない（何が起きるかを言ってから開く）。既定は Yes。
        if not prompts.confirm("ブラウザで Google の承認画面を開きます。よろしいですか？",
                               default=True):
            return False, "中止しました。もう一度実行するには: watari auth"
    return cloud.authorize()


def cmd_auth(args) -> int:
    """Google 認証（会話の同期に使う Google Drive のアプリ専用領域へのログイン）を単独で行う。

    初回は env か対話入力で client_id/secret を受け取り config.json に保存 → ブラウザ承認。
    以後は保存値で再承認/更新できる（token 失効時の再ログインもこれ一発）。
    """
    ok, message = _google_auth_flow(prompt_for_creds=True)
    print(("✓ " if ok else "! ") + message, flush=True)
    if ok:
        _next_steps("これで会話が同期されます。Gmail などのサービスを繋ぐ場合: watari connect")
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


def _find_pi_runtime_file(name: str) -> str | None:
    """wheel / checkout のどちらでも同梱 Pi runtime file を解決する。"""
    try:
        from importlib import resources

        candidate = resources.files("watari_cli") / "pi" / name
        if candidate.is_file():
            return str(candidate)
    except (ModuleNotFoundError, FileNotFoundError, NotADirectoryError, TypeError):
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "..", "pi", name),
        os.path.join(os.getcwd(), "src", "watari_cli", "pi", name),
    ]
    for path in candidates:
        resolved = os.path.abspath(path)
        if os.path.isfile(resolved):
            return resolved
    return None


def _bundled_prompt_templates(skill: str) -> list[str]:
    """同梱スラッシュコマンド（skill/prompts/*.md）の絶対パス一覧（名前順で安定）。"""
    import glob

    return sorted(glob.glob(os.path.join(skill, "prompts", "*.md")))


def _runtime_base(runtime: str) -> list[str]:
    """AI ランタイムの起動コマンド基底を返す。今は Pi。pi が無ければ npx 経由で取りに行く。"""
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
    """直近 window 秒に自動の記憶整理が走った、または今も走っているなら True（二重起動ガード）。"""
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
    """chat 起動時に裏で記憶の整理（プロンプト「記憶を整理して」）を回す。起動をブロックしない。
    二重起動は lock でガードし、自分が整理 worker（WATARI_SKIP_AUTO_DREAM）なら回さない
    ＝再帰しない。夜間 cron の代替。"""
    import subprocess
    import time

    if os.environ.get("WATARI_SKIP_AUTO_DREAM"):
        return
    lock_path = os.path.join(_state_dir(), "dream.lock")
    if _dream_recently(lock_path):
        return
    cmd = _runtime_base(runtime) + [
        "--no-skills", "--append-system-prompt", os.path.join(skill, "SKILL.md"),
        "--no-session", "-p", "記憶を整理して"]
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


def _auto_update_before_chat() -> bool:
    """Apply a safe main update before loading the rest of the installed package."""
    from watari_cli import updater

    notice = updater.consume_notice()
    if notice is not None:
        for line in updater.notice_lines(notice):
            print(line)
        return False

    result = updater.update_installed_tool()
    if result.status in {"updated", "repaired"}:
        try:
            if updater.restart_with_notice(result):
                return True
        except OSError:
            pass
        # If process replacement is unavailable, the package files are already
        # updated; report completion and continue with the code currently loaded.
        for line in updater.notice_lines(result):
            print(line)
    elif result.status == "failed":
        sys.stderr.write("ワタリの自動更新に失敗したため、現在の版で起動します。\n")
    elif result.reason == "dirty":
        sys.stderr.write(
            "watari-cliの取得フォルダに未コミットの変更があるため、自動更新を見送りました。\n")
    elif result.reason == "diverged":
        sys.stderr.write(
            "watari-cliのmainとorigin/mainの履歴が分かれているため、自動更新を見送りました。\n")
    return False


_PERFORMANCE_LABELS = {
    "fast": "爆速",
    "balanced": "標準",
    "butler": "スーパー執事",
}


def cmd_performance(args) -> int:
    """返信速度と、毎回モデルへ渡す記憶量の設定を表示・保存する。"""
    if args.set_mode:
        mode = config.save_performance_mode(args.set_mode)
        print(f"性能モードを「{_PERFORMANCE_LABELS[mode]}」に変更しました。")
        print("次回の watari chat からもこの設定を使います。")
        return 0

    mode = config.load_performance_mode()
    print(f"現在の性能モード: {_PERFORMANCE_LABELS[mode]} ({mode})")
    print("  fast     爆速 — 記憶を4KBに絞り、確認処理の余分な1往復を省略")
    print("  balanced 標準 — 関連する記憶を16KB以内で確認（既定）")
    print("  butler   スーパー執事 — 現在の記憶全体を理解してから回答")
    print("変更: watari performance --set fast|balanced|butler")
    return 0


def cmd_chat(args) -> int:
    """ワタリを起動する。スキル・記憶を自動で渡すランチャー（モデルは Pi 側の関心事）。

    ユーザーは長い pi コマンドを覚えなくてよい: watari chat だけでワタリが立ち上がる。
    """
    import shlex
    import subprocess

    if not args.show and not args.no_update and _auto_update_before_chat():
        return 0

    config.apply(args.home)
    from watari_cli.engine import watari_lib as wl

    home = wl.MEM
    if not os.path.isdir(home):
        return _setup_required()
    if not args.show:
        from watari_cli import git_sync
        git_sync.sync_before_read(home)  # 起動前に最新の記憶を取り込む
        _ensure_state()  # clone/pull 直後でも state を最新に（まとめの遅延再生成）
    skill = _find_skill_dir()
    if not skill:
        sys.stderr.write(
            "ワタリの本体データ（同梱スキル）が見つかりません"
            "（インストールが壊れている可能性があります）。\n"
            "  watari-cli を入れ直してください（例: pip install --force-reinstall watari-cli）。\n")
        return 1

    settings = config.load_config()
    runtime = args.runtime or settings.get("runtime") or "pi"

    # ワタリは「オンデマンドで呼ぶスキル」でなく常時オンの人格。--skill 渡しだとモデルが自動発動せず
    # 素の助手のまま応答する（実測）。SKILL.md をシステムプロンプトに常時注入して人格を起動する。
    # --no-skills で他スキルの自動探索（~/.agents/skills 等の同名 "watari" 衝突含む）も切る。
    skill_md = os.path.join(skill, "SKILL.md")
    quiet_ui = _find_pi_runtime_file("quiet-ui.mjs")
    politeness_guard = _find_pi_runtime_file("politeness-guard.ts")
    performance_extension = _find_pi_runtime_file("performance.ts")
    memory_context = _find_pi_runtime_file("memory-context.ts")
    verification_guard = _find_pi_runtime_file("verification-guard.ts")
    briefing_extension = _find_pi_runtime_file("briefing.ts")
    if not all((quiet_ui, politeness_guard, performance_extension, memory_context,
                verification_guard, briefing_extension)):
        sys.stderr.write(
            "ワタリの本体データ（同梱 Pi runtime file）が見つかりません"
            "（インストールが壊れている可能性があります）。\n"
            "  watari-cli を入れ直してください（例: pip install --force-reinstall watari-cli）。\n")
        return 1
    cmd = _runtime_base(runtime) + ["--no-skills"]
    for template in _bundled_prompt_templates(skill):
        cmd += ["--prompt-template", template]  # /remember /organize 等の同梱スラッシュコマンド
    cmd += [
        "--append-system-prompt", skill_md,
        "--extension", politeness_guard,
        "--extension", performance_extension,
        "--extension", memory_context,
        "--extension", verification_guard,
        "--extension", briefing_extension,
    ] + args.extra

    env = dict(os.environ)
    env["WATARI_HOME"] = home  # ランタイムの bash ツールが同じ記憶を読めるように
    env["WATARI_PERFORMANCE_MODE"] = config.load_performance_mode()
    # Pi が TUI を組み立てる前に process-local の表示設定を当てる。reasoning/effort と会話ログは
    # 変えず、途中の思考文を隠し、tool 実行は通常1行・Ctrl+Oで詳細表示にする。
    # Pi のグローバル settings.json は触らない。
    from pathlib import Path
    preload = f"--import={Path(quiet_ui).resolve().as_uri()}"
    env["NODE_OPTIONS"] = " ".join(x for x in (env.get("NODE_OPTIONS", "").strip(), preload) if x)

    if args.show:
        print(f"chat が実行するコマンド（実行環境: {runtime}。"
              "未導入でも初回に npx が自動で取得します）:")
        print(f"WATARI_HOME={home}")
        print(f"WATARI_PERFORMANCE_MODE={env['WATARI_PERFORMANCE_MODE']}")
        print(f"NODE_OPTIONS={shlex.quote(env['NODE_OPTIONS'])}")
        print(" ".join(shlex.quote(c) for c in cmd))
        return 0

    import signal
    from watari_cli import host, relay

    relayer = relay.Relay(wl.PI_STORE, host.machine_id(), home=home)
    relayer.start()  # 会話を別のパソコンへ中継（クラウド未認証なら内部で no-op）
    _spawn_background_dream(home, runtime, skill)  # 裏で記憶の整理（非ブロッキング・二重起動ガード）

    print("/watari-help で使い方、/organize で記憶の整理ができます。", flush=True)

    def _on_term(signum, frame):  # SIGTERM でも最終 flush してから抜ける
        relayer.stop_and_flush()
        os._exit(128 + signum)

    prev_term = signal.signal(signal.SIGTERM, _on_term)
    try:
        return subprocess.run(cmd, env=env).returncode
    except FileNotFoundError:
        sys.stderr.write(
            "ワタリの実行環境（Pi）を起動できませんでした。\n"
            "  Node.js が入っているか確認してください（https://nodejs.org からインストールできます）。\n"
            "  確認方法: ターミナルで `npx -y @earendil-works/pi-coding-agent` が動けば準備完了です。\n"
        )
        return 127
    except KeyboardInterrupt:
        return 130
    finally:
        signal.signal(signal.SIGTERM, prev_term)
        relayer.stop_and_flush()  # 正常/SIGINT/例外いずれも最終 flush


def cmd_brief(args) -> int:
    """期限・予定・未返信・未読を実状態から read-only でまとめる。"""
    from datetime import datetime, timezone

    config.apply(args.home)
    from watari_cli import briefing, git_sync
    from watari_cli.engine import watari_lib as wl

    git_sync.sync_before_read(wl.MEM)
    _ensure_state()
    try:
        with open(wl.state_path("life"), encoding="utf-8") as stream:
            life = json.load(stream)
    except FileNotFoundError:
        life = {}
    if args.now:
        now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
    else:
        now = datetime.now(timezone.utc)
    result = briefing.collect(life, now)
    result["signals"] = briefing.select_for_delivery(
        result["signals"], now, limit=None if args.all else 3, mark=args.mark_shown,
        suppress_recent=args.mark_shown)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    if not result["signals"]:
        print("今すぐ伝える確認事項はありません。")
    else:
        print("確認事項:")
        for signal in result["signals"]:
            print(f"  - {signal['title']}: {signal['reason']}")
    if result["errors"]:
        print(f"  ※確認できなかったサービス: {', '.join(x['source'] for x in result['errors'])}")
    return 0


def cmd_regen(args) -> int:
    config.apply(args.home)
    from watari_cli.engine import regen_state, watari_lib as wl

    now = regen_state.parse_ts(args.now) if args.now else regen_state.now_utc()
    try:
        gen = regen_state.regen(now)
    except FileNotFoundError:
        return _setup_required()
    if args.check:
        current = {}
        try:
            for g in wl.GENRES:
                with open(wl.state_path(g), encoding="utf-8") as f:
                    current[g] = json.load(f)
        except FileNotFoundError:
            sys.stderr.write(regen_state.MSG_STATE_MISSING + "\n")
            return 1
        diffs = regen_state.semantic_diff(current, gen)
        if diffs:
            print(f"まとめと記録の食い違い {len(diffs)} 件 → watari regen で作り直せます:")
            for x in diffs:
                print(" ", x)
            return 1
        print(regen_state.MSG_CHECK_OK)
        return 0
    for genre in wl.GENRES:
        wl.atomic_write_json(wl.state_path(genre), gen[genre])
    print(f"まとめを作り直しました（基準時刻: {regen_state.fmt_ts(now)}）")
    return 0


def _write_validation_errors(error: ValueError) -> int:
    """ValueError(errors) 契約（args[0]=エラー文字列のリスト）を標準形式で stderr に書く。

    整形は engine(ingest.format_error_lines) に一元化されている——ここは書き出すだけ
    （engine main と cli で文言をズラさない）。
    """
    from watari_cli.engine import ingest

    errors = error.args[0] if error.args else [str(error)]
    for line in ingest.format_error_lines(errors):
        sys.stderr.write(line + "\n")
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
        # rows は読めている。記憶(WATARI_HOME)側の log.jsonl が無い＝未セットアップ。
        return _setup_required()
    except ValueError as error:
        return _write_validation_errors(error)
    print(summary)
    if not args.dry_run:
        from watari_cli import git_sync, relay
        git_sync.sync_after_write(wl.MEM)  # 書いた記憶を commit→pull→push（offline は繰り越し）
        relay.prune_cloud(wl.MEM)          # 全パソコンが取り込み済み＋90日超の共有発話を削除
    return 0


def cmd_connector_list(args) -> int:
    """宣言済みの読み取りソース(connector)を一覧する。対応サービス/カスタムを区別して表示。"""
    from watari_cli import connectors as connectors_mod

    decls = config.load_connectors()
    if not decls:
        print("宣言済みの読み取りソース: なし")
        print("  追加: `watari connect` を実行すると一覧から選べます")
        print('  上級者向け: watari connector add --name <名前> --scope cloud|local'
              ' --read "読み方の指示"')
        return 0
    print("宣言済みの読み取りソース:")
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


def cmd_connector_watch(args) -> int:
    """Slack の監視チャンネル（メンションなしでも全件読むチャンネル）を設定/表示/解除する。"""
    if args.service != "slack":
        print(
            f"監視チャンネルの設定は現在 slack のみ対応しています: {args.service}",
            file=sys.stderr)
        return 1
    if args.clear:
        config.save_slack_watch_channels([])
        print("Slack の監視チャンネルをすべて解除しました")
        return 0
    if args.channels:
        saved = config.save_slack_watch_channels(args.channels)
        if not saved:
            print("チャンネル名を指定してください（全部解除する場合は --clear）", file=sys.stderr)
            return 1
        print("Slack の監視チャンネルを更新しました:")
        for ch in saved:
            print(f"  #{ch}")
        print("  以降、これらのチャンネルはメンションなしの投稿も記憶の整理で読みます")
        return 0
    current = config.load_slack_watch_channels()
    if not current:
        print("Slack の監視チャンネル: なし")
        print("  設定: watari connector watch slack <チャンネル名...>")
    else:
        print("Slack の監視チャンネル:")
        for ch in current:
            print(f"  #{ch}")
    return 0


def cmd_connector_add(args) -> int:
    """connector を宣言（同名は更新）。実際の読み取りはエージェントが行い、CLI は宣言だけ持つ。"""
    try:
        connectors = config.save_connector(
            {"name": args.name, "scope": args.scope, "read": args.read})
    except ValueError as error:
        sys.stderr.write(f"{error}\n")
        return 2
    print(f"読み取りソースを保存しました: {args.name} [{args.scope}]")
    print(f"  読み方: {args.read or '—'}")
    print(f"  宣言済み: {', '.join(c['name'] for c in connectors)}")
    return 0


def cmd_connector_read(args) -> int:
    """対応サービスを読み取り位置(--since、省略時はこのパソコンの記録)以降で読む。

    実 API を叩いて統一形式 {ts,uuid,text,meta} の配列を返すだけで、読み取り位置は進めない
    （前進は従来どおり `watari ingest --advance-ext` のみが行う）。
    認証エラー・ネットワーク断は明確な非ゼロ終了で返す（呼び出し側は位置据え置きで扱える）。
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
    print(f"読み取りソース: {args.name}")
    print(f"  読み始めの位置: {since or 'はじめから'}")
    print(f"  件数: {len(rows)}")
    if rows:
        print(f"  最後の時刻: {rows[-1]['ts']}")
    return 0


def _declare_builtin_connector(name: str, message: str, scope: str = "cloud",
                                auth_kind: str = "paste") -> int:
    """成功時の共通の締め（connector 宣言 → 完了表示 → 次に起きること）。全経路から呼ぶ。

    scope はサービスの ServiceAdapter.scope（transcript 系は "local"、他は既定 "cloud"）。
    local は「認証した」わけではなくログ置き場を見つけただけなので文言を変える（サービス名の
    分岐ではなく auth_kind の分岐——他の場所と同じ形）。
    """
    config.save_connector({
        "name": name, "scope": scope,
        "read": f"組み込み: `watari connector read {name}` で読む",
    })
    if auth_kind == "local":
        print(f"✓ {message}")
    else:
        print(f"✓ 接続しました（{message} として認証）")
    print("  次の記憶の整理から読み込まれます"
          "（watari chat で話しかけたときに自動で反映されます）。")
    if scope == "cloud":
        print("  ※ このサービスはこのパソコンが読み取り担当になります。"
              "他のパソコンでは同じサービスを接続しないでください。")
    return 0


def _print_guide(lines) -> None:
    """接続案内の表示。複数行の要素（マニフェスト等）も1行ずつ崩れずにインデントする。"""
    for line in lines:
        for part in (str(line).splitlines() or [""]):
            print(f"  {part}")


def _connect_wizard(name: str) -> int:
    """1サービス分の接続体験: 案内 → 認証 → config 保存 → connector 宣言。

    サービスごとの分岐はここに書かない——レジストリ(connectors.REGISTRY)から引いた
    ServiceAdapter を汎用に駆動するだけ。新サービスはレジストリに1件足せばここを触らず動く。
    分岐は auth_kind の3種類だけ（paste=トークン貼り付け / oauth=cloud.py の共有 Google 認可 /
    local=認証不要・ログ置き場の自動検出——例: 他 AI CLI の transcript）。
    """
    from watari_cli import connectors as connectors_mod, prompts

    service = connectors_mod.get_service(name)
    if service is None:
        names = ", ".join(key for key, _ in connectors_mod.list_services())
        sys.stderr.write(
            f"不明なサービスです: {name}\n"
            f"  対応サービス: {names}\n"
            "  引数なしの `watari connect` を実行すると一覧から選べます。\n")
        return 2
    if not service.implemented:
        print(f"{service.label} はまだ接続できません（今後対応予定です）。")
        return 0
    if connectors_status(name):
        print(f"{service.label} は接続済みです（続けると再接続します）。")
    print(f"{service.label} と接続します。")
    _print_guide(service.guide)

    if service.auth_kind in ("oauth", "local"):
        ok, message = service.verify()
        if not ok:
            sys.stderr.write(f"! 接続に失敗しました: {message}\n"
                             f"  もう一度やり直すには: watari connect {name}\n")
            return 1
        return _declare_builtin_connector(name, message, scope=service.scope,
                                          auth_kind=service.auth_kind)

    try:
        api_key = prompts.text("トークンを貼り付けてください")
    except prompts.Cancelled:
        sys.stderr.write("\n中止しました。\n")
        return 130
    if not api_key:
        sys.stderr.write("トークンが空のため中止しました。"
                         f"もう一度やり直すには: watari connect {name}\n")
        return 1
    ok, message = service.verify(api_key)
    if not ok:
        sys.stderr.write(f"! 接続に失敗しました: {message}\n"
                         f"  もう一度やり直すには: watari connect {name}\n")
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

    対話ウィザードなので、非対話シェル（パイプ・スクリプト経由）から呼ばれたら
    黙って既定値で進まず、ターミナルで直接打つよう即座に案内して終了する。"""
    from watari_cli import connectors as connectors_mod, prompts

    if not sys.stdin.isatty() and not os.environ.get("WATARI_CONNECT_ALLOW_NO_TTY"):
        sys.stderr.write(
            "watari connect は対話コマンドです。お使いのターミナルで直接実行してください。\n")
        return 2

    if args.service:
        return _connect_wizard(args.service)  # サービス指名は1回だけ実行して終わる

    # 引数なしは「メニュー → 接続 → メニューへ戻る」を繰り返す（複数サービスを続けて繋げる）。
    # 状態アイコンは毎回組み立て直すので、今つないだものは次の表示で ✅ になる。
    while True:
        options = [(_menu_label(key, s), key) for key, s in connectors_mod.list_services()]
        options.append(("終了", None))
        try:
            name = prompts.select("接続するサービスを選んでください", options, default=0)
        except prompts.Cancelled:
            print("\n終了しました。")
            return 0
        if name is None:
            return 0
        _connect_wizard(name)  # 個々の失敗はメッセージを出すだけ。メニューには戻る
        print()


def _build_parser() -> argparse.ArgumentParser:
    p = _TopParser(prog="watari", usage="watari <コマンド> [オプション]",
                   description="ワタリ — 会話からあなたを覚えていく相棒")
    try:
        from importlib.metadata import version

        p.add_argument("--version", action="version", version=f"watari {version('watari-cli')}")
    except Exception:
        pass
    # サブコマンドは _ArgumentParser（トップ専用の自前 help を継がせない）。
    # prog を明示しないとトップの usage 文字列（watari <コマンド> [オプション]）が
    # サブコマンドの usage 行にそのまま連結されてしまう。
    sub = p.add_subparsers(dest="command", required=True, parser_class=_ArgumentParser,
                           prog="watari",
                           metavar="{install,chat,performance,connect,status,auth}")

    ps = sub.add_parser(
        "status", help="記憶の様子を確認",
        description="ワタリの記憶の様子を確認します"
                    "（件数・進行中の話題・どこまで読んだか。読み取り専用です）。")
    ps.add_argument("--home", help=_HOME_HELP)
    ps.set_defaults(func=cmd_status)

    ph = sub.add_parser(
        "host", help="（内部用）このパソコンの環境を記録し、他のパソコンの記録も一覧",
        description="（内部用）このパソコンの環境（ホスト名・AI ツールなど）を記憶フォルダに記録し、"
                    "他のパソコンの記録も一覧します。通常はワタリが自動で使います。")
    ph.add_argument("--home", help=_HOME_HELP)
    ph.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="自由記述の事実を記録します（例 terminal=Ghostty）。繰り返し指定できます")
    ph.set_defaults(func=cmd_host)

    # 旧名 dream は隠し alias として受け付ける（表示は scan のみ。help/候補には出さない）
    pd = sub.add_parser(
        "scan", aliases=["dream"],
        help="（内部用）会話ログから記憶の候補を集める（読むだけ）",
        description="（内部用）会話ログから記憶の候補を集めます（読むだけで、何も書き込みません）。"
                    "通常はワタリが自動で実行します。")
    pd.add_argument("--home", help=_HOME_HELP)
    pd.add_argument("--json", action="store_true", help="（内部用）候補を JSON 形式で出力する")
    pd.set_defaults(func=cmd_scan)

    pr = sub.add_parser(
        "recall", help="（内部用）記憶の中身全体を JSON で出力する",
        description="（内部用）記憶の中身全体（生活・学習のまとめ）を JSON で出力します。"
                    "人が読む場合は watari status を使ってください。")
    pr.add_argument("--home", help=_HOME_HELP)
    pr.set_defaults(func=cmd_recall)

    pa = sub.add_parser(
        "audit", help="（内部用）記憶データに壊れや矛盾がないか点検する",
        description="（内部用）記憶データに壊れや矛盾がないか点検します。"
                    "直したほうがよい点があれば、直し方も表示します。")
    pa.add_argument("--home", help=_HOME_HELP)
    pa.add_argument("--coverage", action="store_true",
                    help="まだ記憶に取り込まれていない会話も一覧する")
    pa.set_defaults(func=cmd_audit)

    pn = sub.add_parser(
        "init", help="（内部用）空の記憶フォルダを新規作成",
        description="（内部用）空の記憶フォルダを作ります。"
                    "通常は watari install（設定の保存まで行う）を使ってください。")
    pn.add_argument("--home", help=_HOME_HELP)
    pn.add_argument("--force", action="store_true", help="空でない場所でも続行する")
    pn.set_defaults(func=cmd_init)

    pg = sub.add_parser(
        "regen", help="（内部用）記憶のまとめを記録から作り直す",
        description="（内部用）記憶のまとめを記録から作り直します。"
                    "復元直後や、点検で食い違いが出たときに使います。通常は自動で実行されます。")
    pg.add_argument("--home", help=_HOME_HELP)
    pg.add_argument("--now", help="作り直しの基準時刻（UTC の ISO 形式。"
                                  "例 2026-01-01T00:00:00.000Z）。省略時は現在時刻")
    pg.add_argument("--check", action="store_true", help="書き込まず、今のまとめと比較だけする")
    pg.set_defaults(func=cmd_regen)

    pinst = sub.add_parser(
        "install", help="初回セットアップ（記憶フォルダの用意と設定の保存）",
        description="初回セットアップを対話形式で行います（記憶フォルダの用意と設定の保存）。"
                    "再実行しても記憶は消えません（「今ある記憶をそのまま使う」を選べます）。")
    pinst.add_argument("--home", help="記憶の保存先（既定: ~/.local/share/watari/memory）")
    pinst.add_argument("--from", dest="from_url", metavar="GIT_URL",
                       help="バックアップ（git リポジトリ）から記憶を復元する")
    pinst.add_argument("--runtime", help="ワタリを動かす AI 実行環境（既定: pi）。通常は変更不要")
    pinst.add_argument("--remote", metavar="GIT_URL",
                       help="記憶を同期する git リポジトリの URL。省略時は対話中に選択できます")
    pinst.add_argument("--yes", "-y", action="store_true", help="質問せず既定のまま進める")
    pinst.add_argument("--dry-run", action="store_true",
                       help="質問の流れだけ試す（何も変更しません。何度でも実行できます）")
    pinst.set_defaults(func=cmd_install)

    pauth = sub.add_parser(
        "auth", help="Google にログイン（複数のパソコンで会話を同期する場合）",
        description="Google にログインし、会話を複数のパソコンの間で同期できるようにします（任意）。"
                    "1台だけで使う場合は不要です。")
    pauth.set_defaults(func=cmd_auth)

    pconn = sub.add_parser(
        "connect", help="外部サービスと接続（Gmail・カレンダー・Slack など）",
        description="外部サービス（Gmail・カレンダー・Slack など）をワタリに繋ぎます。"
                    "画面の案内に従うだけで完了します。引数なしで実行すると一覧から選べます。")
    pconn.add_argument("service", nargs="?",
                       help="接続するサービス名（例 gmail）。省略時は選択メニュー")
    pconn.set_defaults(func=cmd_connect)

    pc = sub.add_parser(
        "chat", help="ワタリと話す",
        description="ワタリと話します（記憶を読み込んで会話を始めます）。"
                    "会話の内容は、あとで役に立つものだけが記憶に取り込まれます。")
    pc.add_argument("--home", help=_HOME_HELP)
    pc.add_argument("--runtime",
                    help="ワタリを動かす AI 実行環境（既定: 保存値か pi）。通常は変更不要")
    pc.add_argument("--show", action="store_true", help="起動せず、実行するコマンドだけ表示する")
    pc.add_argument("--no-update", action="store_true", help="今回だけ本体の自動更新を確認しない")
    pc.add_argument("extra", nargs="*", help="実行環境（Pi）へそのまま渡す追加引数（上級者向け）")
    pc.set_defaults(func=cmd_chat)

    pperf = sub.add_parser(
        "performance", help="返信速度と記憶の詳しさを選ぶ",
        description="返信速度と、回答前に確認する記憶の詳しさを選びます。"
                    "watari chat 内では /performance から選べます。")
    pperf.add_argument("--set", dest="set_mode", choices=config.PERFORMANCE_MODES,
                       help="fast=爆速 / balanced=標準 / butler=スーパー執事")
    pperf.set_defaults(func=cmd_performance)

    pb = sub.add_parser(
        "brief", help="期限・予定・未返信・未読をまとめて確認",
        description="記憶と接続サービスの実状態から、今伝える確認事項を最大3件に絞ります。")
    pb.add_argument("--home", help="記憶フォルダの場所")
    pb.add_argument("--json", action="store_true", help="JSONで表示")
    pb.add_argument("--all", action="store_true", help="3件に絞らずすべて表示")
    pb.add_argument("--mark-shown", action="store_true", help=argparse.SUPPRESS)
    pb.add_argument("--now", help=argparse.SUPPRESS)
    pb.set_defaults(func=cmd_brief)

    pi = sub.add_parser(
        "ingest", help="（内部用）選別済みの記憶データを書き込む",
        description="（内部用）選別済みの記憶データ（JSON）を記憶に書き込みます。"
                    "通常はワタリが自動で実行します。")
    pi.add_argument("--rows", required=True, help="（内部用）書き込む記憶行の JSON 配列ファイル")
    pi.add_argument("--home", help=_HOME_HELP)
    pi.add_argument("--advance-pi", metavar="TS",
                    help="（内部用）このパソコンの会話ログの読み取り位置をこの時刻まで進める"
                         "（UTC の ISO 形式。例 2026-01-01T00:00:00.000Z）")
    pi.add_argument("--advance-cloud", action="append", default=[], metavar="MACHINE=TS",
                    help="（内部用）共有された会話の読み取り位置を進める"
                         "（形式: パソコン名=UTC時刻。例 my-pc=2026-01-01T00:00:00.000Z）")
    pi.add_argument("--advance-ext", action="append", default=[], metavar="NAME=TS",
                    help="（内部用）外部サービスの読み取り位置を進める"
                         "（形式: 名前=UTC時刻。例 mail=2026-01-01T00:00:00.000Z）")
    pi.add_argument("--allow-new-domain", action="store_true",
                    help="（内部用）新しい分野の作成を許可する")
    pi.add_argument("--dry-run", action="store_true", help="検証と件数の表示だけ（書き込みません）")
    pi.set_defaults(func=cmd_ingest)

    # connector は WATARI_HOME ではなく config.json に宣言する（記憶の場所に依らず全パソコン共通の宣言）。
    pcon = sub.add_parser(
        "connector", help="（上級者向け）ワタリが読む外部ソースの一覧・追加設定",
        description="（上級者向け）ワタリが記憶の整理のときに読む外部ソースの一覧・追加設定です。"
                    "通常は watari connect で十分です。")
    consub = pcon.add_subparsers(dest="connector_command", required=True)
    pcl = consub.add_parser("list", help="宣言済みの読み取りソースを一覧する",
                            description="宣言済みの読み取りソースを一覧します。")
    pcl.set_defaults(func=cmd_connector_list)
    pca = consub.add_parser("add", help="読み取りソースを宣言する（追加/更新）",
                            description="読み取りソースを宣言します（同じ名前は更新されます）。")
    pca.add_argument("--name", required=True,
                     help="名前（小文字の英数字とハイフン。例: mail, my-tasks）")
    pca.add_argument("--scope", required=True, choices=["cloud", "local"],
                     help="cloud=接続したパソコンが代表して読み取る / "
                          "local=それぞれのパソコンが自分のデータを読む")
    pca.add_argument("--read", required=True,
                     help="このソースを前回の続きからどう読むか、ワタリへ渡す指示文")
    pca.set_defaults(func=cmd_connector_add)
    pcr = consub.add_parser("read", help="（内部用）対応サービスの新着を前回の続きから読み出す",
                            description="（内部用）対応サービスの新着を前回の続きから読み出します。"
                                        "読み取り位置は進めません。")
    pcr.add_argument("name", help="対応サービス名（例 gmail）")
    pcr.add_argument("--home", help=_HOME_HELP)
    pcr.add_argument("--since", help="この時刻以降を読む（省略時: 前回読んだ続きから）")
    pcr.add_argument("--json", action="store_true",
                     help="（内部用）読み取り結果を JSON 配列で出力する")
    pcr.set_defaults(func=cmd_connector_read)
    pcw = consub.add_parser(
        "watch", help="Slack で監視するチャンネル（メンションなしも全件読む）を設定/表示する",
        description="Slack コネクタが自分の発言とメンションに加えて全件読むチャンネルを"
                    "設定します。引数なしで現在の一覧を表示します。")
    pcw.add_argument("service", help="対応サービス名（現在は slack のみ）")
    pcw.add_argument("channels", nargs="*",
                     help="監視するチャンネル名（# は付けても付けなくてもよい）")
    pcw.add_argument("--clear", action="store_true",
                     help="監視チャンネルをすべて解除する")
    pcw.set_defaults(func=cmd_connector_watch)
    return p


def main() -> int:
    parser = _build_parser()
    if len(sys.argv) <= 1:
        # 裸の watari はエラーにせず、最初の一歩（install → chat）が分かる help を出す
        parser.print_help()
        return 0
    args = parser.parse_args()
    return args.func(args)
