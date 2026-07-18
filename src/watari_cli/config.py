"""設定（記憶の場所＋起動設定）の解決と永続化。

ワタリ本体は記憶を内蔵しない。実行時にここで解決した記憶パスを、エンジン
(engine.watari_lib)が import 時に読む環境変数 WATARI_HOME へ橋渡しする。
起動設定(runtime/provider/model)も同じ設定ファイルに永続化し、watari chat が使う。

記憶パスの優先順: --home 引数 > 環境変数 WATARI_HOME > 保存済み設定 > エンジン既定。
設定ファイルは XDG 準拠: $XDG_CONFIG_HOME/watari/config.json（既定 ~/.config/watari/config.json）。
"""
from __future__ import annotations

import json
import os


def _config_dir() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "watari")


def _config_file() -> str:
    return os.path.join(_config_dir(), "config.json")


def load_config() -> dict:
    try:
        with open(_config_file(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_config(**kwargs) -> dict:
    """None でない値だけを既存設定にマージして保存する。"""
    cfg = load_config()
    cfg.update({k: v for k, v in kwargs.items() if v is not None})
    os.makedirs(_config_dir(), exist_ok=True)
    tmp = _config_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, _config_file())
    return cfg


def apply(home: str | None = None) -> None:
    """使う記憶の場所を環境変数 WATARI_HOME に確定する。

    engine を import する前に呼ぶこと（watari_lib は import 時に env を読むため）。
    優先順: 明示引数 > 既存の環境変数 > 保存済み設定。どれも無ければ何もしない
    （＝engine 既定に委ねる）。
    """
    if home:
        os.environ["WATARI_HOME"] = os.path.abspath(os.path.expanduser(home))
        return
    if "WATARI_HOME" in os.environ:
        return
    saved = load_config().get("home")
    if saved:
        os.environ["WATARI_HOME"] = saved


def save_home(home: str) -> str:
    """記憶の場所を設定に永続化し、確定した絶対パスを返す。"""
    resolved = os.path.abspath(os.path.expanduser(home))
    save_config(home=resolved)
    return resolved
