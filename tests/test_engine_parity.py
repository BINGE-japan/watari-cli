"""エンジンの決定論コアの移植パリティ + 意図的変更の契約テスト。

既存の test_regen_threads.py（open_threads の3層フェード）と test_host.py（カーソルの
host 記録化）を補い、決定論コアで直接の被覆が無かった箇所を固める:
- extract: 本物発話の選別（Pi）/ Pi 合成 uuid・ヘッダ読取 / カーソル絞り込み / 窓トランケート
- ingest : (uuid,kind) 重複スキップ / 検証の原子性 / カーソル後退拒否 / deadline 検証 / 不正JSON
- regen  : learning 畳み込み（mastery 非降格・freshness・related 和集合・alias）/ interests 減衰

注: watari_lib.MEM はモジュール定数（import 時に env から一度だけ解決）。ingest は MEM を
「値で」import するため、一時 home へ向けるには wl.MEM と ingest.MEM の両方を差し替える。
extract は PI_STORE を値で持つので、そちらを差し替える。
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import timedelta

from watari_cli import host
from watari_cli.engine import extract, ingest, regen_state, watari_lib as wl
from watari_cli.engine.watari_lib import fmt_ts, parse_ts


def _write_jsonl(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class ExtractSelectionTest(unittest.TestCase):
    """本物のユーザー発話の選別・カーソル絞り込み・Pi 合成 uuid・ヘッダ読取の契約。"""

    def test_scan_pi_selects_only_genuine_user_messages(self):
        with tempfile.TemporaryDirectory(prefix="watari-ex-") as root:
            _write_jsonl(os.path.join(root, "proj", "sess.jsonl"), [
                # 先頭ヘッダ行：session id と cwd を持つ
                {"type": "session", "id": "S1", "cwd": "/home/example/proj",
                 "timestamp": "2026-07-10T00:00:00.000Z"},
                {"type": "message", "id": "m1", "timestamp": "2026-07-10T00:00:01.000Z",
                 "message": {"role": "user", "content": "本物の発話"}},
                # tool 結果は role:"toolResult" で除外（混入しない）
                {"type": "message", "id": "m2", "timestamp": "2026-07-10T00:00:02.000Z",
                 "message": {"role": "toolResult", "content": [{"type": "text", "text": "x"}]}},
                # assistant は除外
                {"type": "message", "id": "m3", "timestamp": "2026-07-10T00:00:03.000Z",
                 "message": {"role": "assistant", "content": [{"type": "text", "text": "返答"}]}},
                # message 以外の type（bash 実行・注入等）は除外
                {"type": "bashExecution", "id": "m4", "timestamp": "2026-07-10T00:00:04.000Z"},
            ])
            ok, msgs = extract.scan_pi_store(root, None)
            self.assertTrue(ok)
            self.assertEqual([m["uuid"] for m in msgs], ["pi:S1:m1"])
            self.assertEqual(msgs[0]["text"], "本物の発話")
            self.assertEqual(msgs[0]["session"], "S1")
            self.assertEqual(msgs[0]["cwd"], "/home/example/proj")

    def test_scan_pi_excludes_at_or_before_cursor(self):
        with tempfile.TemporaryDirectory(prefix="watari-ex-") as root:
            _write_jsonl(os.path.join(root, "proj", "sess.jsonl"), [
                {"type": "session", "id": "S1", "cwd": "/w",
                 "timestamp": "2026-07-10T00:00:00.000Z"},
                {"type": "message", "id": "old", "timestamp": "2026-07-10T00:00:00.000Z",
                 "message": {"role": "user", "content": "old"}},
                {"type": "message", "id": "new", "timestamp": "2026-07-10T00:05:00.000Z",
                 "message": {"role": "user", "content": "new"}},
            ])
            # ts == cursor は除外・以降のみ（カーソルは「処理済みの最後」の意味）
            ok, msgs = extract.scan_pi_store(root, "2026-07-10T00:00:00.000Z")
            self.assertTrue(ok)
            self.assertEqual([m["uuid"] for m in msgs], ["pi:S1:new"])

    def test_scan_pi_missing_root_is_unreadable(self):
        ok, msgs = extract.scan_pi_store("/no/such/dir", None)
        self.assertFalse(ok)
        self.assertEqual(msgs, [])

    def test_scan_pi_synthesizes_uuid_and_reads_header_at_any_depth(self):
        # dedup 鍵は pi:<session id>:<行の安定 id>。入れ子の深さに依らず拾える（**/*.jsonl）。
        with tempfile.TemporaryDirectory(prefix="watari-pi-") as root:
            _write_jsonl(os.path.join(root, "deep", "nest", "s.jsonl"), [
                {"type": "session", "id": "CX1", "cwd": "/work",
                 "timestamp": "2026-07-10T00:00:00.000Z"},
                {"type": "message", "id": "e9", "timestamp": "2026-07-10T00:00:01.000Z",
                 "message": {"role": "user", "content": "深いネストの発話"}},
            ])
            ok, msgs = extract.scan_pi_store(root, None)
            self.assertTrue(ok)
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs[0]["uuid"], "pi:CX1:e9")
            self.assertEqual(msgs[0]["session"], "CX1")
            self.assertEqual(msgs[0]["cwd"], "/work")
            self.assertEqual(msgs[0]["text"], "深いネストの発話")

    def test_run_truncates_window_from_oldest_message(self):
        # 窓の起点は「最古の未処理メッセージ」。起点 +30日を超える発話は落とし truncated:true。
        with tempfile.TemporaryDirectory(prefix="watari-pi-") as pi, \
                tempfile.TemporaryDirectory(prefix="watari-home-") as home:
            _write_jsonl(os.path.join(pi, "proj", "s.jsonl"), [
                {"type": "session", "id": "S1", "cwd": "/p",
                 "timestamp": "2026-01-01T00:00:00.000Z"},
                {"type": "message", "id": "a", "timestamp": "2026-01-01T00:00:00.000Z",
                 "message": {"role": "user", "content": "oldest"}},
                {"type": "message", "id": "b", "timestamp": "2026-01-16T00:00:00.000Z",
                 "message": {"role": "user", "content": "within"}},
                {"type": "message", "id": "c", "timestamp": "2026-02-20T00:00:00.000Z",
                 "message": {"role": "user", "content": "beyond-window"}},
            ])
            saved = (extract.PI_STORE, wl.MEM)
            extract.PI_STORE = pi
            wl.MEM = home  # 空 home → カーソルは全 None（絞り込み無し・書き込み無し）
            try:
                result = extract.run()
            finally:
                extract.PI_STORE, wl.MEM = saved
            pi_stats = result["stores"]["pi"]
            self.assertTrue(pi_stats["truncated"])
            self.assertEqual(pi_stats["count"], 2)
            self.assertEqual(pi_stats["max_ts"], "2026-01-16T00:00:00.000Z")
            self.assertEqual([m["uuid"] for m in result["messages"]], ["pi:S1:a", "pi:S1:b"])


class IngestApplyTest(unittest.TestCase):
    """検証→dedup→追記→カーソル前進→state 再生成 の契約。カーソルは host 記録に載る。"""

    def setUp(self):
        self._saved = (wl.MEM, ingest.MEM)
        self._tmp = tempfile.TemporaryDirectory(prefix="watari-ing-")
        home = self._tmp.name
        wl.MEM = home
        ingest.MEM = home  # ingest は MEM を値で import するため差し替える
        for sub in ("life", "learning"):
            os.makedirs(os.path.join(home, sub), exist_ok=True)
            open(wl.log_path(sub), "w", encoding="utf-8").close()
        self.home = home

    def tearDown(self):
        wl.MEM, ingest.MEM = self._saved
        self._tmp.cleanup()

    def _row(self, uuid="u1", **kw):
        d = {"kind": "thread", "topic": "t", "summary": "s", "note": "n",
             "ts": "2026-07-10T00:00:00.000Z", "refs": {"uuid": uuid}}
        d.update(kw)
        return d

    def test_dedup_by_uuid_and_kind(self):
        s1 = ingest.apply([self._row()])
        self.assertIn("生活 1 件", s1)
        s2 = ingest.apply([self._row()])  # 同 (uuid,kind) は黙ってスキップ
        self.assertIn("重複スキップ 1 件", s2)
        self.assertIn("生活 0 件", s2)
        self.assertEqual(len(wl.load_log("life")), 1)

    def test_validation_error_writes_nothing(self):
        with self.assertRaises(ValueError):
            ingest.apply([self._row(uuid="")])  # refs.uuid 欠落 → 検証失敗
        self.assertEqual(wl.load_log("life"), [])            # log は無傷
        self.assertFalse(os.path.exists(host.host_path(self.home)))  # host 記録も書かない

    def test_new_profile_row_requires_explicit_mode(self):
        row = self._row(
            uuid="profile-no-mode",
            kind="fact",
            profile={"key": "response_style", "value": "brief"},
        )
        with self.assertRaises(ValueError) as cm:
            ingest.apply([row])
        self.assertTrue(any("profile.mode" in error for error in cm.exception.args[0]))
        self.assertEqual(wl.load_log("life"), [])

    def test_profile_mode_rejects_unknown_value(self):
        row = self._row(
            uuid="profile-mode",
            kind="fact",
            profile={"key": "response_style", "value": "brief", "mode": "sometimes"},
        )
        with self.assertRaises(ValueError) as cm:
            ingest.apply([row])
        self.assertTrue(any("profile.mode" in error for error in cm.exception.args[0]))
        self.assertEqual(wl.load_log("life"), [])

    def test_new_profile_row_migrates_legacy_value_to_relevant_facts(self):
        legacy = self._row(
            uuid="profile-old",
            kind="fact",
            ts="2026-07-10T00:00:00.000Z",
            profile={"key": "render_backend", "value": "Aurora"},
        )
        migrated = self._row(
            uuid="profile-new",
            kind="fact",
            ts="2026-07-11T00:00:00.000Z",
            profile={"key": "render_backend", "value": "Aurora", "mode": "relevant"},
            note=None,
        )
        _write_jsonl(wl.log_path("life"), [legacy])  # 旧記録は読み取り互換
        ingest.apply([migrated])
        with open(wl.state_path("life"), encoding="utf-8") as stream:
            life = json.load(stream)
        self.assertNotIn("render_backend", life["profile"])
        self.assertEqual(life["facts"]["render_backend"]["note"], "Aurora")

    def test_cursor_backward_rejected_and_atomic(self):
        ingest.apply([self._row(uuid="u1")], advance_pi="2026-07-10T00:00:00.000Z")
        with self.assertRaises(ValueError) as cm:
            ingest.apply([self._row(uuid="u2")], advance_pi="2026-07-01T00:00:00.000Z")
        self.assertTrue(any("巻き戻せません" in e for e in cm.exception.args[0]))
        # エラー文は実際に打たれたフラグ構文で示す（存在しないフラグ表記を出さない）
        self.assertTrue(any(e.startswith("--advance-pi 2026-07-01") for e in cm.exception.args[0]))
        # 後退拒否で u2 は書かれない（原子性）
        self.assertEqual([d["refs"]["uuid"] for d in wl.load_log("life")], ["u1"])

    def test_cursor_advance_lands_in_host_record_not_shared_json(self):
        ingest.apply([self._row(uuid="u1")], advance_pi="2026-07-10T00:00:00.000Z")
        record = json.load(open(host.host_path(self.home), encoding="utf-8"))
        self.assertEqual(record["cursors"]["transcripts_pi"], "2026-07-10T00:00:00.000Z")
        self.assertIn("last_run", record["cursors"])
        # 共有 cursors.json は（このマシンからは）作らない
        self.assertFalse(os.path.exists(os.path.join(self.home, "cursors.json")))

    def test_dry_run_does_not_append(self):
        summary = ingest.apply([self._row(uuid="u1")], dry_run=True)
        self.assertIn("お試し実行", summary)
        self.assertIn("何も書き込んでいません", summary)
        self.assertEqual(wl.load_log("life"), [])

    def test_summary_mentions_cursor_update_and_state_rebuild(self):
        # 成功サマリは平易語（読み取り位置・まとめ）で構成し、内部語(dedup/カーソル/state)を出さない
        summary = ingest.apply([self._row(uuid="u1")], advance_pi="2026-07-10T00:00:00.000Z")
        self.assertIn("記憶に追記", summary)
        self.assertIn("読み取り位置を更新", summary)
        self.assertIn("transcripts_pi=2026-07-10T00:00:00.000Z", summary)
        self.assertIn("まとめを再生成しました", summary)
        for jargon in ("dedup", "カーソル", "state 再生成"):
            self.assertNotIn(jargon, summary)

    def test_naive_ts_error_shows_iso_example_without_jargon(self):
        with self.assertRaises(ValueError) as cm:
            ingest.apply([self._row(uuid="u1", ts="2026-07-10T00:00:00")])  # naive
        joined = "\n".join(cm.exception.args[0])
        self.assertIn("UTC の ISO 形式", joined)
        self.assertIn("2026-01-01T00:00:00.000Z", joined)  # 実際に使える例を見せる
        for jargon in ("naive", "aware", "regen", "クラッシュ"):
            self.assertNotIn(jargon, joined)

    def test_invalid_kind_lists_valid_values(self):
        with self.assertRaises(ValueError) as cm:
            ingest.apply([self._row(uuid="u1", kind="memo")])
        joined = "\n".join(cm.exception.args[0])
        self.assertIn("study", joined)
        self.assertIn("thread", joined)

    def test_domain_kebab_error_is_plain_language(self):
        row = self._row(uuid="u1", kind="study", domain="Bad_Domain",
                        topic="t", mastery=1, note="n")
        with self.assertRaises(ValueError) as cm:
            ingest.apply([row])
        joined = "\n".join(cm.exception.args[0])
        self.assertIn("小文字の英数字とハイフン", joined)
        self.assertNotIn("ケバブ", joined)

    def test_new_domain_error_points_to_recall_and_flag(self):
        row = self._row(uuid="u1", kind="study", domain="new-dom",
                        topic="t", mastery=1, note="n")
        with self.assertRaises(ValueError) as cm:
            ingest.apply([row])
        joined = "\n".join(cm.exception.args[0])
        self.assertIn("watari recall", joined)
        self.assertIn("--allow-new-domain", joined)
        self.assertNotIn("既存に寄せる", joined)

    def test_deadline_must_be_tz_aware(self):
        with self.assertRaises(ValueError) as cm:
            ingest.apply([self._row(uuid="u1", deadline="2026-09-01T00:00:00")])  # naive
        self.assertTrue(any("deadline" in e for e in cm.exception.args[0]))

    def test_valid_deadline_accepted_and_stored_in_log(self):
        ingest.apply([self._row(uuid="u1", deadline="2026-12-01T00:00:00.000Z")])
        self.assertEqual(wl.load_log("life")[0]["deadline"], "2026-12-01T00:00:00.000Z")


class AdvanceExtErrorTest(IngestApplyTest):
    """--advance-ext のエラーは実際に打てる構文例で示す（config は一時ディレクトリに隔離）。"""

    def setUp(self):
        super().setUp()
        self._cfg = tempfile.TemporaryDirectory(prefix="watari-cfg-")
        self._saved_cfg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._cfg.name

    def tearDown(self):
        if self._saved_cfg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._saved_cfg
        self._cfg.cleanup()
        super().tearDown()

    def test_undeclared_connectors_get_add_command_not_placeholder(self):
        with self.assertRaises(ValueError) as cm:
            ingest.apply([self._row(uuid="u1")], advance_ext=["mail=2026-07-10T00:00:00.000Z"])
        joined = "\n".join(cm.exception.args[0])
        self.assertIn("watari connector add", joined)
        self.assertNotIn("宣言なし", joined)  # 「<宣言なし>=<UTC ts>」を出さない（回帰防止）

    def test_malformed_spec_shows_typable_example(self):
        with self.assertRaises(ValueError) as cm:
            ingest.apply([self._row(uuid="u1")], advance_ext=["mail"])
        joined = "\n".join(cm.exception.args[0])
        self.assertIn("--advance-ext mail=2026-01-01T00:00:00.000Z", joined)

    def test_unknown_name_lists_declared_names(self):
        from watari_cli import config
        config.save_connector({"name": "mail", "scope": "cloud", "read": "r"})
        with self.assertRaises(ValueError) as cm:
            ingest.apply([self._row(uuid="u1")], advance_ext=["typo=2026-07-10T00:00:00.000Z"])
        joined = "\n".join(cm.exception.args[0])
        self.assertIn("宣言されていない名前", joined)
        self.assertIn("mail", joined)

    def test_non_iso_ts_shows_real_flag_syntax(self):
        from watari_cli import config
        config.save_connector({"name": "mail", "scope": "cloud", "read": "r"})
        with self.assertRaises(ValueError) as cm:
            ingest.apply([self._row(uuid="u1")], advance_ext=["mail=notatime"])
        joined = "\n".join(cm.exception.args[0])
        self.assertIn("--advance-ext mail=notatime", joined)     # 打たれた形
        self.assertIn("--advance-ext mail=2026-01-01", joined)   # 正しく打てる例
        self.assertNotIn("--advance-ext mail が", joined)        # 存在しないフラグ表記を出さない


class FormatErrorLinesTest(unittest.TestCase):
    """検証エラー表示の整形は ingest.format_error_lines に一元化（engine main と cli が共用）。"""

    def test_header_and_indent(self):
        lines = ingest.format_error_lines(["a", "b"])
        self.assertIn("検証エラー 2 件", lines[0])
        self.assertIn("何も書き込んでいません", lines[0])
        self.assertIn("修正して再実行", lines[0])
        self.assertEqual(lines[1], "  - a")
        self.assertEqual(lines[2], "  - b")


class RenderStoreSummaryTest(unittest.TestCase):
    """scan（旧 dream）の人間向け1行サマリ。英語フィールド名(readable/truncated)を出さない。"""

    def test_ok_line(self):
        line = extract.render_store_summary("pi", {"readable": True, "count": 3, "truncated": False})
        self.assertIn("読み取り=OK", line)
        self.assertIn("新しい発話=3件", line)
        self.assertIn("区切り=なし", line)
        self.assertNotIn("readable", line)
        self.assertNotIn("truncated", line)

    def test_unreadable_and_truncated(self):
        line = extract.render_store_summary("pi", {"readable": False, "count": 0, "truncated": True})
        self.assertIn("次回に持ち越します", line)
        self.assertIn("30日分", line)


class LoadRowsTest(unittest.TestCase):
    """rows ファイルの読み込みは、常に「エラー文字列のリスト」を持つ ValueError で失敗する。"""

    def test_malformed_json_raises_list_valueerror(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("not json{{{")
            path = f.name
        try:
            with self.assertRaises(ValueError) as cm:
                ingest.load_rows(path)
        finally:
            os.unlink(path)
        errors = cm.exception.args[0]
        self.assertIsInstance(errors, list)   # 1文字ずつ列挙されない（回帰防止）
        self.assertEqual(len(errors), 1)
        self.assertIn("不正な JSON", errors[0])

    def test_non_list_json_raises(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write('{"kind": "thread"}')
            path = f.name
        try:
            with self.assertRaises(ValueError) as cm:
                ingest.load_rows(path)
        finally:
            os.unlink(path)
        self.assertEqual(cm.exception.args[0], ["rows は JSON 配列"])


class FoldLearningTest(unittest.TestCase):
    """learning 畳み込み（純関数）の規則。"""

    def _study(self, topic, ts, uuid, **kw):
        d = {"kind": "study", "domain": "python", "topic": topic, "summary": "s",
             "note": "n", "mastery": 1, "ts": ts, "refs": {"uuid": uuid}}
        d.update(kw)
        return d

    def test_mastery_takes_max_never_downgrades(self):
        rows = [self._study("t", "2026-07-01T00:00:00.000Z", "u1", mastery=3),
                self._study("t", "2026-07-02T00:00:00.000Z", "u2", mastery=1)]
        t = regen_state.fold_learning(rows, {})["python"]["topics"]["t"]
        self.assertEqual(t["mastery"], 3)

    def test_freshness_takes_max_of_freshness_or_ts(self):
        rows = [self._study("t", "2026-07-01T00:00:00.000Z", "u1",
                             freshness="2026-08-01T00:00:00.000Z"),
                self._study("t", "2026-07-05T00:00:00.000Z", "u2")]
        t = regen_state.fold_learning(rows, {})["python"]["topics"]["t"]
        self.assertEqual(t["freshness"], "2026-08-01T00:00:00.000Z")
        self.assertEqual(t["last"], "2026-07-05T00:00:00.000Z")

    def test_related_is_union_in_first_seen_order_without_self_ref(self):
        rows = [self._study("t", "2026-07-01T00:00:00.000Z", "u1",
                             related=["python/t", "python/other", "go/x"]),
                self._study("t", "2026-07-02T00:00:00.000Z", "u2",
                             related=["go/x", "rust/y"])]
        t = regen_state.fold_learning(rows, {})["python"]["topics"]["t"]
        self.assertEqual(t["related"], ["python/other", "go/x", "rust/y"])

    def test_alias_folds_domain(self):
        rows = [self._study("t", "2026-07-01T00:00:00.000Z", "u1")]
        domains = regen_state.fold_learning(rows, {"python": "py3"})
        self.assertIn("py3", domains)
        self.assertNotIn("python", domains)

    def test_note_falls_back_to_summary(self):
        row = self._study("t", "2026-07-01T00:00:00.000Z", "u1")
        row.pop("note")
        row["summary"] = "サマリ"
        t = regen_state.fold_learning([row], {})["python"]["topics"]["t"]
        self.assertEqual(t["note"], "サマリ")


class FoldProfileModesTest(unittest.TestCase):
    """profile.mode で常時注入と関連時検索を分離する。"""

    def _fact(self, ts, uuid, key, value, mode=None):
        profile = {"key": key, "value": value}
        if mode is not None:
            profile["mode"] = mode
        return {
            "kind": "fact", "summary": "s", "ts": ts,
            "profile": profile, "refs": {"uuid": uuid},
        }

    def test_relevant_profile_fact_moves_out_of_always_profile(self):
        now = parse_ts("2026-07-03T00:00:00.000Z")
        rows = [
            self._fact("2026-07-01T00:00:00.000Z", "u1", "render_backend", "Legacy", "always"),
            self._fact("2026-07-02T00:00:00.000Z", "u2", "render_backend", "Aurora", "relevant"),
        ]
        profile, facts, _interests, _threads = regen_state.fold_life(rows, now)
        self.assertNotIn("render_backend", profile)
        self.assertEqual(facts["render_backend"]["note"], "Aurora")

    def test_legacy_profile_rows_remain_always_for_backward_compatibility(self):
        now = parse_ts("2026-07-03T00:00:00.000Z")
        row = self._fact("2026-07-01T00:00:00.000Z", "u1", "response_style", "brief")
        profile, facts, _interests, _threads = regen_state.fold_life([row], now)
        self.assertEqual(profile["response_style"], "brief")
        self.assertEqual(facts, {})


class FoldInterestsTest(unittest.TestCase):
    """interests の heat 減衰（30日で1下がり・0で state から落ちる）。"""

    def _interest(self, ts, uuid, **kw):
        d = {"kind": "interest", "topic": "jazz", "summary": "s", "note": "n",
             "ts": ts, "refs": {"uuid": uuid}}
        d.update(kw)
        return d

    def test_heat_decays_one_per_30_days(self):
        now = parse_ts("2026-07-01T00:00:00.000Z")
        row = self._interest(fmt_ts(now - timedelta(days=60)), "u1", heat=3)  # decay 2 → eff 1
        _profile, _facts, interests, _threads = regen_state.fold_life([row], now)
        self.assertEqual(interests["jazz"]["heat"], 1)

    def test_interest_drops_when_effective_heat_zero(self):
        now = parse_ts("2026-07-01T00:00:00.000Z")
        row = self._interest(fmt_ts(now - timedelta(days=60)), "u1", heat=1)  # decay 2 → eff 0
        _profile, _facts, interests, _threads = regen_state.fold_life([row], now)
        self.assertNotIn("jazz", interests)


if __name__ == "__main__":
    unittest.main()
