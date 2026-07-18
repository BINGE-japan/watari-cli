"""カセット差込口（cartridge slot）の解決と永続化。

ゲーム機(watari-cli)はカセット＝個人記憶を内蔵しない。実行時にここで解決した
パスを、エンジン(engine.watari_lib)が import 時に読む環境変数へ橋渡しする。
優先順: --home 引数 > 環境変数 WATARI_HOME > 保存済み設定 > エンジン既定(現ライブ・カセット)。
既定値の正本はエンジン側(watari_lib)に一元化してあり、ここでは複製しない。
"""
from __future__ import annotations

import os


def _config_home_file() -> str:
    """カセット位置を保存するファイル(XDG準拠)。watari install が書き、apply が読む。"""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "watari", "home")


def apply(home: str | None = None) -> None:
    """使用するカセットパスを環境変数 WATARI_HOME に確定する。

    engine を import する前に呼ぶこと（watari_lib は import 時に env を読むため）。
    優先順: 明示引数 > 既存の環境変数 > 保存済み設定。どれも無ければ何もしない
    （＝engine 既定の現ライブ・カセットに委ねる）。
    """
    if home:
        os.environ["WATARI_HOME"] = os.path.abspath(os.path.expanduser(home))
        return
    if "WATARI_HOME" in os.environ:
        return
    saved_file = _config_home_file()
    if os.path.exists(saved_file):
        with open(saved_file, encoding="utf-8") as f:
            saved = f.read().strip()
        if saved:
            os.environ["WATARI_HOME"] = saved


def save_home(home: str) -> str:
    """カセットパスを設定に永続化し、確定した絶対パスを返す（watari install 用）。"""
    resolved = os.path.abspath(os.path.expanduser(home))
    saved_file = _config_home_file()
    os.makedirs(os.path.dirname(saved_file), exist_ok=True)
    with open(saved_file, "w", encoding="utf-8") as f:
        f.write(resolved + "\n")
    return resolved
