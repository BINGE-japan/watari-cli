"""ゼロ依存の対話プロンプト（create-vite / @clack 風）。

方針（create-vite に倣う）:
- 未指定の項目だけを尋ねる。各質問に既定値、Enter で採用。
- TTY なら矢印キー選択、非TTY（パイプ/CI）は番号入力に自動フォールバック。
- Ctrl+C で中止（Cancelled 送出）。EOF は既定値を採用（スクリプトで固まらない）。
外部依存を持たない（watari-cli の「素の Python だけで入る」を保つため）。
"""
from __future__ import annotations

import sys


class Cancelled(Exception):
    """ユーザーが Ctrl+C 等で中止した。"""


def _stdin_is_tty() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def text(message: str, default: str | None = None) -> str:
    suffix = f" ({default})" if default else ""
    try:
        line = input(f"◆ {message}{suffix}: ").strip()
    except EOFError:
        return default or ""
    except KeyboardInterrupt:
        raise Cancelled()
    return line or (default or "")


def confirm(message: str, default: bool = True) -> bool:
    """はい/いいえの確認。認識できない入力は既定に落とさず、聞き直す。"""
    hint = "Y/n" if default else "y/N"
    yes = ("y", "yes", "ｙ", "はい")
    no = ("n", "no", "ｎ", "いいえ")
    while True:
        try:
            line = input(f"◆ {message} [{hint}]: ").strip().lower()
        except EOFError:
            return default  # 入力が尽きた（スクリプト実行）ときだけ既定を採用
        except KeyboardInterrupt:
            raise Cancelled()
        if not line:
            return default
        if line in yes:
            return True
        if line in no:
            return False
        print("  y（はい）か n（いいえ）で答えてください")


def select(message: str, options: list[tuple[str, object]], default: int = 0) -> object:
    """options=[(label, value), ...] から1つ選ぶ。選ばれた value を返す。"""
    if _stdin_is_tty():
        try:
            return _select_tty(message, options, default)
        except Cancelled:
            raise
        except Exception:
            pass  # 端末制御に失敗したら番号入力へ
    return _select_lines(message, options, default)


def _select_lines(message: str, options, default: int) -> object:
    print(f"◆ {message}")
    for i, (label, _) in enumerate(options):
        mark = "❯" if i == default else " "
        print(f"  {mark} {i + 1}) {label}")
    while True:
        try:
            line = input(f"  番号を選択 [{default + 1}]: ").strip()
        except EOFError:
            return options[default][1]  # 入力が尽きたときだけ既定を採用
        except KeyboardInterrupt:
            raise Cancelled()
        if not line:
            return options[default][1]
        try:
            idx = int(line) - 1
        except ValueError:
            # 解析できない入力を黙って既定にしない（何が選ばれたか分からなくなる）
            print(f"  1〜{len(options)} の番号を入力してください")
            continue
        if 0 <= idx < len(options):
            return options[idx][1]
        print(f"  1〜{len(options)} の番号を入力してください")


def _select_tty(message: str, options, default: int) -> object:
    import termios
    import tty

    idx = max(0, min(default, len(options) - 1))
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)

    def draw(first: bool) -> None:
        if not first:
            sys.stdout.write(f"\x1b[{len(options)}A")  # カーソルを選択肢の先頭へ戻す
        for i, (label, _) in enumerate(options):
            pointer = "❯" if i == idx else " "
            body = f" {pointer} {label}"
            if i == idx:
                body = f"\x1b[36m{body}\x1b[0m"  # cyan
            sys.stdout.write("\r\x1b[2K" + body + "\r\n")
        sys.stdout.flush()

    sys.stdout.write(f"◆ {message}  (↑↓ で選択、Enter で決定)\r\n")
    sys.stdout.flush()
    try:
        tty.setraw(fd)
        draw(first=True)
        while True:
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):
                break
            if ch == "\x03":  # Ctrl+C
                raise Cancelled()
            if ch == "\x1b":  # 矢印などのエスケープシーケンス
                seq = sys.stdin.read(2)
                if seq == "[A":
                    idx = (idx - 1) % len(options)
                elif seq == "[B":
                    idx = (idx + 1) % len(options)
                draw(first=False)
            elif ch == "k":
                idx = (idx - 1) % len(options)
                draw(first=False)
            elif ch == "j":
                idx = (idx + 1) % len(options)
                draw(first=False)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\r\n")
        sys.stdout.flush()
    return options[idx][1]
