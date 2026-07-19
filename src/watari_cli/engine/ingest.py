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
    DOMAIN_RE, KIND_TO_GENRE, MEM,
    append_log, atomic_write_json, existing_dedup_keys, fmt_ts,
    load_log, now_utc, parse_ts,
)
from . import regen_state


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
            errors.append(f"{where}: kind 不正: {kind!r}")
            continue
        try:
            if parse_ts(d["ts"]).tzinfo is None:
                errors.append(f"{where}: ts はタイムゾーン必須（UTC …Z）。naive 値は regen で aware と比較できず毎回クラッシュする: {d['ts']!r}")
        except Exception:
            errors.append(f"{where}: ts 不正: {d.get('ts')!r}")
        if not d.get("refs", {}).get("uuid"):
            errors.append(f"{where}: refs.uuid 欠落")
        if not d.get("summary"):
            errors.append(f"{where}: summary 欠落")
        if kind == "study":
            if not d.get("domain"):
                errors.append(f"{where}: study に domain 欠落")
            elif not DOMAIN_RE.match(d["domain"]):
                errors.append(f"{where}: domain は小文字ケバブ: {d['domain']!r}")
            elif d["domain"] not in doms and not allow_new_domain:
                errors.append(f"{where}: 新規 domain {d['domain']!r}。既存に寄せるか --allow-new-domain を明示")
            if not d.get("topic"):
                errors.append(f"{where}: study に topic 欠落")
            if d.get("mastery") not in (1, 2, 3):
                errors.append(f"{where}: mastery は 1..3 必須: {d.get('mastery')!r}")
            if not d.get("note"):
                errors.append(f"{where}: study に note（state 用・現在形1〜2文）欠落")
        elif kind in ("interest", "thread"):
            if not d.get("topic"):
                errors.append(f"{where}: {kind} に topic 欠落")
            if kind == "interest" and d.get("heat") is not None and d["heat"] not in (0, 1, 2, 3):
                errors.append(f"{where}: heat は 0..3: {d.get('heat')!r}")
        elif kind == "fact":
            p = d.get("profile")
            if p is not None and (not isinstance(p, dict) or not p.get("key") or not p.get("value")):
                errors.append(f"{where}: profile は {{key, value}} 形式")
        # regen が消費するフィールドの形も検証する（不正値は log に入ると regen/audit を毎回
        # クラッシュさせる「毒行」になり、追記専用 log では手編集でしか除けなくなる）。
        if d.get("freshness") is not None:
            try:
                if parse_ts(d["freshness"]).tzinfo is None:
                    errors.append(f"{where}: freshness はタイムゾーン必須（UTC …Z）。naive 値は regen で aware と比較できず毎回クラッシュする: {d['freshness']!r}")
            except Exception:
                errors.append(f"{where}: freshness 不正（UTC …Z）: {d.get('freshness')!r}")
        if d.get("deadline") is not None:
            try:
                if parse_ts(d["deadline"]).tzinfo is None:
                    errors.append(f"{where}: deadline はタイムゾーン必須（UTC …Z）。naive 値は regen で aware と比較できず毎回クラッシュする: {d['deadline']!r}")
            except Exception:
                errors.append(f"{where}: deadline 不正（UTC …Z）: {d.get('deadline')!r}")
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


def apply(rows, *, advance_pi=None, advance_ext=(), allow_new_domain=False, dry_run=False):
    """検証→dedup→追記→カーソル前進→state 再生成。サマリ文字列を返す。

    検証（行・カーソル後退）に1件でも失敗したら ValueError(errors) を送出し、何も書かない。
    """
    errors = validate(rows, allow_new_domain)
    # カーソルはマシンごとの host 記録に持つ（遅延 import で循環を回避）。
    from watari_cli import host
    cursors = host.load_cursors(MEM)
    advances = [("pi", "transcripts_pi", advance_pi)]
    # 外部ソース(connector)の許可名はユーザー宣言（config の connectors）。transcript(Pi) は
    # 上の専用フラグが担当し、ここは通らない。advance_ext が無ければ config を読まない（副作用最小）。
    if advance_ext:
        from watari_cli import config
        declared = {c.get("name") for c in config.load_connectors() if c.get("name")}
        for spec in advance_ext:
            name, sep, ts = spec.partition("=")
            if not sep or not ts or name not in declared:
                allowed = "|".join(sorted(declared)) or "宣言なし"
                errors.append(
                    f"--advance-ext は宣言済み connector のみ <{allowed}>=<UTC ts>（watari connector add で宣言）: {spec!r}")
            else:
                advances.append((f"ext {name}", name, ts))
    for name, key, adv in advances:
        if adv:
            try:
                adv_ts = parse_ts(adv)
            except Exception:
                errors.append(f"--advance-{name} が ISO 時刻でない: {adv!r}")
                continue
            cur = cursors.get(key)
            if cur and adv_ts < parse_ts(cur):
                errors.append(f"--advance-{name} {adv} はカーソル {cur} より過去（後退禁止）")
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

    if dry_run:
        return f"dry-run OK: 追記予定 life={len(to_write['life'])} learning={len(to_write['learning'])} dedupスキップ={skipped}"

    for genre, rs in to_write.items():
        if rs:
            append_log(genre, rs)
    now = now_utc()
    for name, key, adv in advances:
        if adv:
            cursors[key] = adv
    cursors["last_run"] = fmt_ts(now)
    host.save_cursors(MEM, cursors)
    for g, out in regen_state.regen(now).items():
        atomic_write_json(os.path.join(MEM, g, "state.json"), out)
    advanced = " ".join(f"{key}={adv}" for _, key, adv in advances if adv) or "なし"
    return (f"追記 life={len(to_write['life'])} learning={len(to_write['learning'])} dedupスキップ={skipped}、"
            f"カーソル前進 {advanced}、state 再生成済み")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--advance-pi")
    ap.add_argument("--advance-ext", action="append", default=[], metavar="NAME=TS")
    ap.add_argument("--allow-new-domain", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        rows = load_rows(args.rows)
        summary = apply(
            rows,
            advance_pi=args.advance_pi,
            advance_ext=args.advance_ext, allow_new_domain=args.allow_new_domain,
            dry_run=args.dry_run,
        )
    except ValueError as error:
        errors = error.args[0] if error.args else [str(error)]
        print(f"検証エラー {len(errors)} 件（何も書き込んでいません）:", file=sys.stderr)
        for e in errors:
            print(" -", e, file=sys.stderr)
        sys.exit(2)
    print(summary)


if __name__ == "__main__":
    main()
