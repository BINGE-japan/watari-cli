"""設定（記憶の場所＋起動設定）の解決と永続化。

ワタリ本体は記憶を内蔵しない。実行時にここで解決した記憶パスを、エンジン
(engine.watari_lib)が import 時に読む環境変数 WATARI_HOME へ橋渡しする。
起動設定(runtime)も同じ設定ファイルに永続化し、watari chat が使う（AI のプロバイダ/
モデル選びは watari の関心事ではなく Pi 側に委ねる）。

記憶パスの優先順: --home 引数 > 環境変数 WATARI_HOME > 保存済み設定 > エンジン既定。
設定ファイルは XDG 準拠: $XDG_CONFIG_HOME/watari/config.json（既定 ~/.config/watari/config.json）。
"""
from __future__ import annotations

import json
import os
import re

# connector 名は小文字スラッグ（domain と同じ形）。engine を import すると watari_lib が
# env から MEM を確定してしまい config.apply の上書き機会を奪うため、ここは engine に依存せず
# 自前で持つ（config は engine より前に読まれる層）。
_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
CONNECTOR_SCOPES = ("local", "cloud")


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


def load_connectors() -> list:
    """宣言済み connector の一覧（config の "connectors"）。無ければ空リスト。

    connector＝「夢に流し込むソース」の宣言。watari-cli は特定ツールのアダプタを内蔵せず、
    ユーザーがどのソースを・どう読むかを宣言するだけ（実際の読み取りはエージェントが自分の
    ツールで行う）。各エントリは {"name":<slug>, "scope":"local"|"cloud", "read":<自由記述>}。
    """
    connectors = load_config().get("connectors")
    return connectors if isinstance(connectors, list) else []


def save_connector(entry: dict) -> list:
    """connector 宣言を1件、name をキーに追加/更新して保存し、更新後の一覧を返す。

    name は小文字スラッグ必須、scope は local|cloud。read はエージェントへの自由記述の読み方指示。
    同名は位置を保って上書き（二重管理を避ける）。不正な name/scope は ValueError。
    """
    name = entry.get("name")
    scope = entry.get("scope")
    if not isinstance(name, str) or not _SLUG_RE.match(name):
        raise ValueError(f"connector name は小文字スラッグ必須: {name!r}")
    if scope not in CONNECTOR_SCOPES:
        raise ValueError(f"connector scope は {'|'.join(CONNECTOR_SCOPES)}: {scope!r}")
    record = {"name": name, "scope": scope, "read": entry.get("read") or ""}
    connectors = load_connectors()
    for i, c in enumerate(connectors):
        if c.get("name") == name:
            connectors[i] = record
            break
    else:
        connectors.append(record)
    save_config(connectors=connectors)
    return connectors
