"""カセット記憶リポの git 同期層。

読む前（chat/dream/recall の頭）に「未追記を commit → pull」、書いた後（ingest）に
「commit → pull → push」する。offline は commit だけ済ませて次回に繰り越す。記憶が git repo
でない／remote が無い場合は該当操作を静かに no-op（ローカルのみ運用を壊さない）。

log.jsonl は union-merge（.gitattributes）で複数マシンの追記が自動マージされ、host record は
マシンごとに別ファイルなので衝突しない。state は派生(.gitignore)で追跡せず競合もしない。
すべての git 失敗（offline 等）は握りつぶしてローカル継続する——同期はベストエフォート。
"""
from __future__ import annotations

import os
import subprocess


def _git(home: str, *args: str) -> subprocess.CompletedProcess:
    """記憶リポで git を実行（失敗しても例外を投げない＝呼び出し側がベストエフォートで扱う）。"""
    try:
        return subprocess.run(["git", "-C", home, *args], capture_output=True, text=True)
    except OSError:
        return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="git unavailable")


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


def sync_before_read(home: str) -> None:
    """読む前：未追記を commit し、remote があれば pull（union-merge で自動マージ）。
    repo でない／remote が無い／offline は静かに継続する。"""
    if not is_repo(home):
        return
    _commit_if_changed(home, "memory: sync before read")
    if has_remote(home):
        _git(home, "pull", "--no-edit", "--no-rebase")


def sync_after_write(home: str) -> None:
    """書いた後：commit → pull → push。offline は commit だけ済ませ次回に繰り越す。"""
    if not is_repo(home):
        return
    _commit_if_changed(home, "memory: update")
    if not has_remote(home):
        return
    _git(home, "pull", "--no-edit", "--no-rebase")
    _git(home, "push")


def setup_remote(home: str, url: str) -> tuple[bool, str]:
    """install 時：記憶を git repo 化し origin を設定して初回 push する。(ok, メッセージ)。
    既に repo/remote でも冪等。push 失敗（offline 等）は remote 設定だけ残し False を返す
    （install は止めない——次回の sync で追いつく）。"""
    if not is_repo(home):
        if _git(home, "init").returncode != 0:
            return False, "git init 失敗"
    if _git(home, "remote", "get-url", "origin").returncode == 0:
        _git(home, "remote", "set-url", "origin", url)
    else:
        _git(home, "remote", "add", "origin", url)
    _commit_if_changed(home, "memory: initial")
    push = _git(home, "push", "-u", "origin", "HEAD")
    if push.returncode != 0:
        return False, f"remote は設定済み・初回 push は次回同期で再試行: {push.stderr.strip()[:160]}"
    return True, "remote と同期を設定しました"
