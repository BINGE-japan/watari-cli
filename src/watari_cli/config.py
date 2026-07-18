"""カセット差込口（cartridge slot）の解決。

ゲーム機(watari-cli)はカセット＝個人記憶を内蔵しない。実行時にここで解決した
パスを、エンジン(engine.watari_lib)が import 時に読む環境変数へ橋渡しする。
優先順: --home 引数 > 環境変数 WATARI_HOME > エンジン既定（現ライブ・カセット）。
既定値の正本はエンジン側(watari_lib)に一元化してあり、ここでは複製しない。
"""
from __future__ import annotations

import os


def apply(home: str | None = None) -> None:
    """CLI 引数のカセットパスを環境変数へ反映する。

    engine を import する前に呼ぶこと（watari_lib は import 時に env を読むため）。
    home が None のときは何もしない＝env かエンジン既定に委ねる。
    """
    if home:
        os.environ["WATARI_HOME"] = os.path.abspath(os.path.expanduser(home))
