#!/usr/bin/env python3
"""判定済みの記憶行を検証つきで log に追記し、カーソルを前進させ、state を再生成する。

usage: ingest.py --rows FILE [--advance-pi TS]
                 [--advance-ext NAME=TS ...] [--allow-new-domain] [--dry-run]

--rows FILE: 追記したい log 行の JSON 配列。各行は SCHEMA の log 行仕様
  （kind で行き先ジャンルが決まる。study は domain/topic/mastery/note 必須、
    interest/thread は topic 必須、refs.uuid 必須）。
--advance-pi: Pi transcript ストアの「実際に処理した最後の timestamp」。後退は拒否。
  ストアが読めなかった回は渡さない（カーソル据え置き）。
--advance-ext NAME=TS: 外部ソース(connector)のカーソル前進。繰り返し指定可。許可名はユーザーが
  宣言した connector 名（config の connectors。`watari connector add`）。規則は --advance-pi と同じ
  （後退拒否・読めなかった回は渡さない）。未宣言の名前はエラー。obsidian 等もここで宣言して渡す。

検証に1件でも失敗したら何も書かずに exit 2（原子性）。
dedup: 既存 log に同 (refs.uuid, kind) があれば黙ってスキップ（正常系）。

CLI(watari ingest) からも使えるよう、arg 解析後の本体を apply()、rows 読み込みを
load_rows() に分けてある。検証失敗は ValueError(errors) を送出（挙動・出力文言は据え置き）。
"""
import argparse
import json
import os
import sys

from .watari_lib import (
    DOMAIN_RE, KIND_TO_GENRE, MEM, MSG_SETUP_REQUIRED,
    append_log, atomic_write_json, existing_dedup_keys, fmt_ts,
    load_log, now_utc, parse_ts,
)
from . import regen_state

# エラー文中で示す ISO 時刻の見本（実際に打てる形をそのまま見せる）
_TS_EXAMPLE = "2026-01-01T00:00:00.000Z"


def known_domains():
    doms = set()
    for d in load_log("learning"):
        if d.get("domain"):
            doms.add(d["domain"])
    return doms


def validate(rows, allow_new_domain):
    errors = []
    doms = known_domains()
    for i, d in enumerate(rows, 1):
        where = f"rows[{i}]"
        kind = d.get("kind")
        if kind not in KIND_TO_GENRE:
            valid = " / ".join(KIND_TO_GENRE)
            errors.append(f"{where}: kind が不正です: {kind!r}（有効な値: {valid}）")
            continue
        # naive（タイムゾーン無し）の時刻は log に入ると再生成のたびに比較不能になる「毒行」
        # なので、ts/freshness/deadline とも入口で必ず弾く（理由の説明はユーザーに見せない）。
        try:
            if parse_ts(d["ts"]).tzinfo is None:
                errors.append(f"{where}: ts は UTC の ISO 形式（例 {_TS_EXAMPLE}）で指定してください: {d['ts']!r}")
        except Exception:
            errors.append(f"{where}: ts が時刻として読めません（UTC の ISO 形式、例 {_TS_EXAMPLE}）: {d.get('ts')!r}")
        if not d.get("refs", {}).get("uuid"):
            errors.append(f"{where}: refs.uuid 欠落")
        if not d.get("summary"):
            errors.append(f"{where}: summary 欠落")
        if kind == "study":
            if not d.get("domain"):
                errors.append(f"{where}: study に domain 欠落")
            elif not DOMAIN_RE.match(d["domain"]):
                errors.append(f"{where}: domain は小文字の英数字とハイフンで指定してください（例 machine-learning）: {d['domain']!r}")
            elif d["domain"] not in doms and not allow_new_domain:
                errors.append(
                    f"{where}: 新しい分野名です: {d['domain']!r}。既存の分野名（watari recall で確認できます）に"
                    "合わせるか、新しく作る場合は --allow-new-domain を付けて再実行してください")
            if not d.get("topic"):
                errors.append(f"{where}: study に topic 欠落")
            if d.get("mastery") not in (1, 2, 3):
                errors.append(f"{where}: mastery は 1..3 必須: {d.get('mastery')!r}")
            if not d.get("note"):
                errors.append(f"{where}: study に note（まとめに載せる現在形の説明 1〜2 文）が欠落")
        elif kind in ("interest", "thread"):
            if not d.get("topic"):
                errors.append(f"{where}: {kind} に topic 欠落")
            if kind == "interest" and d.get("heat") is not None and d["heat"] not in (0, 1, 2, 3):
                errors.append(f"{where}: heat は 0..3: {d.get('heat')!r}")
        elif kind == "fact":
            p = d.get("profile")
            if p is not None and (not isinstance(p, dict) or not p.get("key") or not p.get("value")):
                errors.append(f"{where}: profile は {{key, value, mode?}} 形式")
            elif isinstance(p, dict) and "mode" not in p:
                errors.append(f"{where}: 新しい profile 行には profile.mode（'always' または 'relevant'）が必須です")
            elif isinstance(p, dict) and p.get("mode") not in ("always", "relevant"):
                errors.append(
                    f"{where}: profile.mode は 'always' または 'relevant': {p.get('mode')!r}")
        # regen が消費するフィールドの形も検証する（不正値は log に入ると regen/audit を毎回
        # クラッシュさせる「毒行」になり、追記専用 log では手編集でしか除けなくなる）。
        if d.get("freshness") is not None:
            try:
                if parse_ts(d["freshness"]).tzinfo is None:
                    errors.append(f"{where}: freshness は UTC の ISO 形式（例 {_TS_EXAMPLE}）で指定してください: {d['freshness']!r}")
            except Exception:
                errors.append(f"{where}: freshness が時刻として読めません（UTC の ISO 形式、例 {_TS_EXAMPLE}）: {d.get('freshness')!r}")
        if d.get("deadline") is not None:
            try:
                if parse_ts(d["deadline"]).tzinfo is None:
                    errors.append(f"{where}: deadline は UTC の ISO 形式（例 {_TS_EXAMPLE}）で指定してください: {d['deadline']!r}")
            except Exception:
                errors.append(f"{where}: deadline が時刻として読めません（UTC の ISO 形式、例 {_TS_EXAMPLE}）: {d.get('deadline')!r}")
        rel = d.get("related")
        if rel is not None and (not isinstance(rel, list)
                                or not all(isinstance(r, str) and "/" in r for r in rel)):
            errors.append(f"{where}: related は ['domain/topic', ...] 形式の配列: {rel!r}")
    return errors


def load_rows(path):
    try:
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
    except json.JSONDecodeError as error:
        # ValueError の args[0] は「エラー文字列のリスト」という取り決め（呼び出し側が len()/反復する）。
        # JSONDecodeError も ValueError だが args[0] は文字列なので、そのまま流すと1文字ずつ列挙される。
        raise ValueError([f"rows が不正な JSON: {error}"])
    if not isinstance(rows, list):
        raise ValueError(["rows は JSON 配列"])
    return rows


def apply(rows, *, advance_pi=None, advance_cloud=(), advance_ext=(),
          allow_new_domain=False, dry_run=False):
    """検証→dedup→追記→カーソル前進→state 再生成。サマリ文字列を返す。

    検証（行・カーソル後退）に1件でも失敗したら ValueError(errors) を送出し、何も書かない。
    """
    errors = validate(rows, allow_new_domain)
    # カーソルはマシンごとの host 記録に持つ（遅延 import で循環を回避）。
    from watari_cli import host
    cursors = host.load_cursors(MEM)
    # advances: (key, adv, disp, example)。disp は「実際に打たれた形」、example は「正しく打てる形」
    # ——エラー文で存在しないフラグ表記（--advance-ext mail 等）を出さないため。
    advances = [("transcripts_pi", advance_pi,
                 f"--advance-pi {advance_pi}", f"--advance-pi {_TS_EXAMPLE}")]
    for spec in advance_cloud:  # 他のパソコンの共有発話のカーソル（cloud_<machine>）
        name, sep, ts = spec.partition("=")
        if sep and ts:
            advances.append((f"cloud_{name}", ts,
                             f"--advance-cloud {spec}", f"--advance-cloud {name}={_TS_EXAMPLE}"))
        else:
            errors.append(
                f"--advance-cloud は <パソコン名>=<UTC時刻> の形式で指定してください"
                f"（例: --advance-cloud my-pc={_TS_EXAMPLE}）: {spec!r}")
    # 外部ソース(connector)の許可名はユーザー宣言（config の connectors）。transcript(Pi) は
    # 上の専用フラグが担当し、ここは通らない。advance_ext が無ければ config を読まない（副作用最小）。
    if advance_ext:
        from watari_cli import config
        declared = {c.get("name") for c in config.load_connectors() if c.get("name")}
        for spec in advance_ext:
            name, sep, ts = spec.partition("=")
            if not sep or not ts:
                example = name or "mail"
                errors.append(
                    f"--advance-ext は <名前>=<UTC時刻> の形式で指定してください"
                    f"（例: --advance-ext {example}={_TS_EXAMPLE}）: {spec!r}")
            elif not declared:
                errors.append(
                    f"--advance-ext {spec!r}: 読み取りソース(connector)が1つも宣言されていません。"
                    '先に watari connector add --name <名前> --scope cloud|local --read "読み方" で宣言してください')
            elif name not in declared:
                allowed = " / ".join(sorted(declared))
                errors.append(
                    f"--advance-ext {spec!r}: {name!r} は宣言されていない名前です"
                    f"（使える名前: {allowed}。watari connector add で追加できます）")
            else:
                advances.append((name, ts,
                                 f"--advance-ext {spec}", f"--advance-ext {name}={_TS_EXAMPLE}"))
    for key, adv, disp, example in advances:
        if adv:
            try:
                adv_ts = parse_ts(adv)
            except Exception:
                errors.append(f"{disp}: 時刻が ISO 形式ではありません（例: {example}）")
                continue
            cur = cursors.get(key)
            if cur and adv_ts < parse_ts(cur):
                errors.append(
                    f"{disp}: 前回の読み取り位置 {cur} より過去です。読み取り位置は巻き戻せません"
                    "（時刻の指定ミスがないか確認してください）")
    if errors:
        raise ValueError(errors)

    seen = existing_dedup_keys()
    to_write = {"life": [], "learning": []}
    skipped = 0
    for d in rows:
        key = (d["refs"]["uuid"], d["kind"])
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        to_write[KIND_TO_GENRE[d["kind"]]].append(d)

    counts = f"生活 {len(to_write['life'])} 件・学習 {len(to_write['learning'])} 件（重複スキップ {skipped} 件）"
    if dry_run:
        return f"追記の予定: {counts}（お試し実行: 何も書き込んでいません）"

    for genre, rs in to_write.items():
        if rs:
            append_log(genre, rs)
    now = now_utc()
    for key, adv, _disp, _example in advances:
        if adv:
            cursors[key] = adv
    cursors["last_run"] = fmt_ts(now)
    host.save_cursors(MEM, cursors)
    for g, out in regen_state.regen(now).items():
        atomic_write_json(os.path.join(MEM, g, "state.json"), out)
    advanced = " ".join(f"{key}={adv}" for key, adv, _d, _e in advances if adv) or "なし"
    return f"記憶に追記: {counts}／読み取り位置を更新: {advanced}／まとめを再生成しました"


def format_error_lines(errors):
    """検証エラーの表示行（ヘッダ＋各行）。engine main と cli(watari ingest) が同じ整形を使う。

    ValueError(errors) 契約（args[0]=エラー文字列のリスト）の表示側。二重実装で文言が
    ズレないよう、整形はここに一元化する。
    """
    lines = [f"検証エラー {len(errors)} 件（記憶には何も書き込んでいません）。以下を修正して再実行してください:"]
    lines += [f"  - {e}" for e in errors]
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--advance-pi")
    ap.add_argument("--advance-cloud", action="append", default=[], metavar="MACHINE=TS")
    ap.add_argument("--advance-ext", action="append", default=[], metavar="NAME=TS")
    ap.add_argument("--allow-new-domain", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        rows = load_rows(args.rows)
    except FileNotFoundError as error:
        print(f"rows ファイルが読めません: {error}", file=sys.stderr)
        sys.exit(2)
    except ValueError as error:
        errors = error.args[0] if error.args else [str(error)]
        for line in format_error_lines(errors):
            print(line, file=sys.stderr)
        sys.exit(2)
    try:
        summary = apply(
            rows,
            advance_pi=args.advance_pi, advance_cloud=args.advance_cloud,
            advance_ext=args.advance_ext, allow_new_domain=args.allow_new_domain,
            dry_run=args.dry_run,
        )
    except FileNotFoundError:
        # rows は読めている。記憶（WATARI_HOME）側の log.jsonl が無い＝未セットアップ。
        print(MSG_SETUP_REQUIRED, file=sys.stderr)
        sys.exit(1)
    except ValueError as error:
        errors = error.args[0] if error.args else [str(error)]
        for line in format_error_lines(errors):
            print(line, file=sys.stderr)
        sys.exit(2)
    print(summary)


if __name__ == "__main__":
    main()
