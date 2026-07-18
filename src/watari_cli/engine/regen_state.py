#!/usr/bin/env python3
"""state.json を log.jsonl から決定的に再生成する。state = f(log, aliases, now)。

畳み込み規則（SCHEMA.md の正本実装）:
- 行は ts 昇順・同時刻は refs.uuid 順で畳む。
- learning: (domain, topic) ごとに
    mastery  = max(行の mastery, 既定1)   # 定着は降格しない
    last     = 最大 ts
    freshness= 最大 (行の freshness or ts)
    note     = note を持つ最新行の note（無ければ最新行の summary）
    related  = 全行の related の和集合（初出順・自己参照除外）
- life.profile: kind=fact で profile:{key,value} を持つ行の key ごと最新値。
- life.interests: kind=interest で topic を持つ行を topic ごとに畳み、
    base heat = heat を持つ最新行の heat（無ければ1）
    effective = max(0, base - floor((now-last)/30日))、0 なら state から落ちる。
- life.open_threads: kind=thread で topic を持つ行。最新行 status:"closed" は即クローズ。
  それ以外は last からの経過日数 age で3層に分ける：
    active (age < DORMANT_DAYS)         … 通常どおり open_threads に載る（印なし）
    dormant (DORMANT_DAYS <= age < SINK_DAYS) … open_threads に残すが dormant:true / dormant_days:age を付ける（声かけ待ち）
    sunk (age >= SINK_DAYS)             … state から外す（log には残る）
  deadline（UTC ISO …Z）を持つ行はその最新の非 null 値を record に持ち越し、
  deadline が now より未来なら age によらず active 固定（dormant/sunk にしない）。
- topic の無い interest/thread 行・domain の無い study 行は state に畳まれない
  （log 上の文脈としては残る）。

usage: regen_state.py [--now ISO] [--check]
  --check: 書き込まず現 state と比較。差分があれば表示して exit 1。
"""
import argparse
import json
import sys

from .watari_lib import (
    DORMANT_DAYS, GENRES, HEAT_DECAY_DAYS, SINK_DAYS,
    atomic_write_json, fmt_ts, load_aliases, load_log, now_utc, parse_ts,
    sorted_rows, state_path,
)


def fold_learning(rows, aliases):
    domains = {}
    for d in sorted_rows(rows):
        if d.get("kind") != "study":
            continue
        dom = d.get("domain")
        topic = d.get("topic")
        if not dom or not topic:
            continue
        dom = aliases.get(dom, dom)
        t = domains.setdefault(dom, {"topics": {}})["topics"].setdefault(topic, {
            "mastery": 1, "freshness": None, "last": None, "note": "", "related": [],
        })
        t["mastery"] = max(t["mastery"], int(d.get("mastery", 1)))
        ts = parse_ts(d["ts"])
        t["last"] = max(t["last"], ts) if t["last"] else ts
        fresh = parse_ts(d["freshness"]) if d.get("freshness") else ts
        t["freshness"] = max(t["freshness"], fresh) if t["freshness"] else fresh
        if d.get("note"):
            t["note"] = d["note"]
        elif d.get("summary") and not t["note"]:
            t["note"] = d["summary"]
        self_ref = f"{dom}/{topic}"
        for r in d.get("related", []) or []:
            if r != self_ref and r not in t["related"]:
                t["related"].append(r)
    for dom in domains.values():
        for t in dom["topics"].values():
            t["last"] = fmt_ts(t["last"])
            t["freshness"] = fmt_ts(t["freshness"])
    return domains


def fold_life(rows, now):
    profile, interests, threads = {}, {}, {}
    for d in sorted_rows(rows):
        kind = d.get("kind")
        if kind == "fact":
            p = d.get("profile")
            if isinstance(p, dict) and p.get("key") and p.get("value"):
                profile[p["key"]] = p["value"]
        elif kind == "interest" and d.get("topic"):
            it = interests.setdefault(d["topic"], {"last": None, "heat": 1, "note": ""})
            it["last"] = max(it["last"], parse_ts(d["ts"])) if it["last"] else parse_ts(d["ts"])
            if d.get("heat") is not None:
                it["heat"] = int(d["heat"])
            if d.get("note"):
                it["note"] = d["note"]
            elif d.get("summary") and not it["note"]:
                it["note"] = d["summary"]
        elif kind == "thread" and d.get("topic"):
            th = threads.setdefault(d["topic"], {"last": None, "note": "", "closed": False, "deadline": None})
            th["last"] = max(th["last"], parse_ts(d["ts"])) if th["last"] else parse_ts(d["ts"])
            th["closed"] = d.get("status") == "closed"
            if d.get("deadline"):  # 最新の非 null deadline を持ち越す（後続の null では消さない）
                th["deadline"] = d["deadline"]
            if d.get("note"):
                th["note"] = d["note"]
            elif d.get("summary") and not th["note"]:
                th["note"] = d["summary"]
    out_interests = {}
    for topic, it in interests.items():
        decay = int((now - it["last"]).total_seconds() // 86400) // HEAT_DECAY_DAYS
        eff = max(0, it["heat"] - decay)
        if eff > 0:
            out_interests[topic] = {"last": fmt_ts(it["last"]), "heat": eff, "note": it["note"]}
    out_threads = []
    for topic, th in threads.items():
        if th["closed"]:
            continue  # status:"closed" は age によらず即クローズ（従来どおり）
        # deadline が now より未来なら、経過日数によらず active に固定する（項目ごとの寿命）
        deadline_future = bool(th["deadline"]) and parse_ts(th["deadline"]) > now
        age_days = (now - th["last"]).total_seconds() / 86400
        if not deadline_future and age_days >= SINK_DAYS:
            continue  # sunk: state から沈める（log には残り復元可能）
        out = {"topic": topic, "note": th["note"], "last": fmt_ts(th["last"])}
        if th["deadline"]:
            out["deadline"] = th["deadline"]
        if not deadline_future and age_days >= DORMANT_DAYS:
            out["dormant"] = True  # 声かけ待ち：state に残すが「最近どうなってる？」の印を付ける
            out["dormant_days"] = int(age_days)
        out_threads.append(out)
    return profile, out_interests, out_threads


def regen(now):
    aliases = load_aliases()
    learning = {"updated": fmt_ts(now), "domains": fold_learning(load_log("learning"), aliases)}
    profile, interests, threads = fold_life(load_log("life"), now)
    life = {"updated": fmt_ts(now), "profile": profile, "interests": interests, "open_threads": threads}
    return {"learning": learning, "life": life}


def semantic_diff(current, generated):
    """updated と並び順を無視した差分の要約行を返す。"""
    diffs = []

    def cmp(path, a, b):
        if isinstance(a, dict) and isinstance(b, dict):
            for k in a.keys() | b.keys():
                if k == "updated":
                    continue
                if k not in a:
                    diffs.append(f"+ {path}.{k} (生成側のみ)")
                elif k not in b:
                    diffs.append(f"- {path}.{k} (現stateのみ)")
                else:
                    cmp(f"{path}.{k}", a[k], b[k])
        elif isinstance(a, list) and isinstance(b, list):
            if path.endswith(".related"):
                if set(a) != set(b):
                    diffs.append(f"≠ {path}: {sorted(set(a) ^ set(b))}")
            else:  # open_threads: topic をキーに比較
                am = {x["topic"]: x for x in a}
                bm = {x["topic"]: x for x in b}
                for k in am.keys() | bm.keys():
                    if k not in am:
                        diffs.append(f"+ {path}[{k}] (生成側のみ)")
                    elif k not in bm:
                        diffs.append(f"- {path}[{k}] (現stateのみ)")
                    else:
                        cmp(f"{path}[{k}]", am[k], bm[k])
        elif a != b:
            diffs.append(f"≠ {path}: {json.dumps(a, ensure_ascii=False)[:60]} -> {json.dumps(b, ensure_ascii=False)[:60]}")
    for g in current.keys() & generated.keys():
        cmp(g, current[g], generated[g])
    return diffs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", help="再生成時刻 (UTC ISO)。省略時は現在時刻")
    ap.add_argument("--check", action="store_true", help="書き込まず現 state と比較")
    args = ap.parse_args()
    now = parse_ts(args.now) if args.now else now_utc()
    gen = regen(now)
    if args.check:
        current = {g: json.load(open(state_path(g), encoding="utf-8")) for g in GENRES}
        diffs = semantic_diff(current, gen)
        if diffs:
            print(f"state と log 再生成結果に差分 {len(diffs)} 件:")
            for x in diffs:
                print(" ", x)
            sys.exit(1)
        print("OK: state は log から再生成した結果と一致（決定論が保たれている）")
        return
    for g in GENRES:
        atomic_write_json(state_path(g), gen[g])
    print(f"state 再生成完了 (now={fmt_ts(now)})")


if __name__ == "__main__":
    main()
