"""記憶フォルダ（git リポジトリ）の同期層。

読む前（chat/scan/recall の頭）に「未追記を commit → pull」、書いた後（ingest）に
「commit → pull → push」する。offline は commit だけ済ませて次回に繰り越す。記憶が git repo
でない／remote が無い場合は該当操作を静かに no-op（ローカルのみ運用を壊さない）。

log.jsonl は union-merge（.gitattributes）で複数マシンの追記が自動マージされ、host record は
マシンごとに別ファイルなので衝突しない。state は派生(.gitignore)で追跡せず競合もしない。
git 失敗（offline 等）でもローカル継続する——同期はベストエフォート。ただし黙りはしない：
pull/push の失敗は stderr へ1行だけ知らせる（変更は commit 済みなので事実として安全）。
表示の一元化のため、警告文言はこのモジュールに置き cli 側では整形しない。
"""
from __future__ import annotations

import os
import subprocess
import sys


def _git(home: str, *args: str) -> subprocess.CompletedProcess:
    """記憶リポで git を実行（失敗しても例外を投げない＝呼び出し側がベストエフォートで扱う）。"""
    try:
        return subprocess.run(["git", "-C", home, *args], capture_output=True, text=True)
    except OSError:
        return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="git unavailable")


def _warn(message: str) -> None:
    """同期の1行警告。stdout を汚さない（recall 等は stdout に JSON を出す）ため stderr へ。"""
    print("! " + message, file=sys.stderr)


def is_repo(home: str) -> bool:
    return _git(home, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true"


def has_remote(home: str) -> bool:
    r = _git(home, "remote")
    return r.returncode == 0 and bool(r.stdout.strip())


def _ensure_identity(home: str) -> None:
    """commit に必要な identity が全く無いホスト向けの保険（設定済みなら触らない＝本人名を尊重）。"""
    if not _git(home, "config", "user.email").stdout.strip():
        _git(home, "config", "user.email", "watari@localhost")
        _git(home, "config", "user.name", "watari")


def _commit_if_changed(home: str, message: str) -> bool:
    """追跡下の変更（log 追記・host record 等）があれば commit。派生 state は gitignore 済み。"""
    _git(home, "add", "-A")
    if not _git(home, "status", "--porcelain").stdout.strip():
        return False
    _ensure_identity(home)
    _git(home, "commit", "-m", message)
    return True


def _merge_in_progress(home: str) -> bool:
    return os.path.exists(os.path.join(home, ".git", "MERGE_HEAD"))


def _pull(home: str) -> bool:
    """pull を1回試みる。失敗は stderr へ1行警告し False を返す（処理自体は継続してよい）。

    union-merge 対象外のファイルで衝突するとマージ途中（MERGE_HEAD 残り）のまま止まり、
    以後の同期が全て失敗し続けるため、衝突を検出したら merge --abort で作業ツリーを
    健全な状態に戻して次回に再試行させる。
    """
    pull = _git(home, "pull", "--no-edit", "--no-rebase")
    if pull.returncode == 0:
        return True
    if _merge_in_progress(home):
        _git(home, "merge", "--abort")
        if _merge_in_progress(home):
            _warn(f"記憶の同期が衝突で止まっています。{home} で git status を確認してください。")
        else:
            _warn("記憶の同期で衝突があったため、今回の取り込みは見送りました"
                  "（記憶は壊れていません。次回に自動で再試行します）。")
    else:
        _warn("記憶の同期に失敗しました（オフライン？）。変更は保存済みで、次回に自動で再試行します。")
    return False


def sync_before_read(home: str) -> None:
    """読む前：未追記を commit し、remote があれば pull（union-merge で自動マージ）。
    repo でない／remote が無い場合は静かに継続。pull 失敗は1行警告して継続する。"""
    if not is_repo(home):
        return
    _commit_if_changed(home, "memory: sync before read")
    if has_remote(home):
        _pull(home)


def sync_after_write(home: str) -> None:
    """書いた後：commit → pull → push。offline は commit だけ済ませ次回に繰り越す。
    pull/push の失敗は stderr へ1行警告する（警告は1回の呼び出しにつき最大1行）。"""
    if not is_repo(home):
        return
    _commit_if_changed(home, "memory: update")
    if not has_remote(home):
        return
    if not _pull(home):
        return  # pull できない状況（offline/衝突）では push も失敗する。警告の重複を避ける
    push = _git(home, "push")
    if push.returncode != 0:
        _warn("記憶の同期に失敗しました（オフライン？）。変更は保存済みで、次回に自動で再試行します。")


def setup_remote(home: str, url: str) -> tuple[bool, str]:
    """install 時：記憶を git repo 化し origin を設定して初回 push する。(ok, メッセージ)。
    既に repo/remote でも冪等。push 失敗（offline 等）は remote 設定だけ残し False を返す
    （install は止めない——次回の sync で追いつく）。"""
    if not is_repo(home):
        init = _git(home, "init")
        if init.returncode != 0:
            detail = (init.stderr or init.stdout).strip()[:160]
            return False, ("記憶フォルダを同期用（git）に初期化できませんでした"
                           f"{'：' + detail if detail else ''}。"
                           "git がインストールされているか `git --version` で確認してください")
    if _git(home, "remote", "get-url", "origin").returncode == 0:
        _git(home, "remote", "set-url", "origin", url)
    else:
        _git(home, "remote", "add", "origin", url)
    _commit_if_changed(home, "memory: initial")
    push = _git(home, "push", "-u", "origin", "HEAD")
    if push.returncode != 0:
        return False, ("同期先は設定できましたが、初回のアップロードに失敗しました"
                       "（次回に自動で再試行します）。URL とアクセス権（SSH 鍵・トークン）を"
                       f"確認してください。詳細: {push.stderr.strip()[:160]}")
    return True, "同期を設定しました"
