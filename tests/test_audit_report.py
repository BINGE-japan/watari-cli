"""audit / regen の公開品質文言の契約テスト。

- STRICT_SINCE（開発者個人の移行日）の廃止: 必須フィールド欠落は日付に関係なく検出し、
  「参考情報」（exit code に影響しない）として最大5件＋残り件数で報告する。
- render_report の見出し（直したほうがよい点 / 参考情報 / 取り込まれていない会話）と直し方の提示。
- まとめ(state)未生成・記憶フォルダ不在のとき traceback を出さない契約。
- regen --check の表示ヘルパー（文言の正本は engine 側）。
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from watari_cli.engine import audit, regen_state, watari_lib as wl


def _thread(topic, ts, uuid, **kw):
    d = {"ts": ts, "kind": "thread", "topic": topic, "summary": "s", "note": "n",
         "refs": {"uuid": uuid}}
    d.update(kw)
    return d


class _Home(unittest.TestCase):
    """一時 WATARI_HOME に log を置く共通土台。"""

    def setUp(self):
        self._saved_mem = wl.MEM
        self._tmp = tempfile.TemporaryDirectory(prefix="watari-audit-")
        wl.MEM = self._tmp.name
        for sub in ("life", "learning"):
            os.makedirs(os.path.join(wl.MEM, sub), exist_ok=True)
            open(wl.log_path(sub), "w", encoding="utf-8").close()

    def tearDown(self):
        wl.MEM = self._saved_mem
        self._tmp.cleanup()

    def _write_rows(self, genre, rows):
        with open(wl.log_path(genre), "w", encoding="utf-8") as f:
            for d in rows:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")

    def _build_state(self, now="2026-07-18T00:00:00.000Z"):
        for genre, out in regen_state.regen(wl.parse_ts(now)).items():
            wl.atomic_write_json(wl.state_path(genre), out)


class StrictSinceRemovedTest(_Home):
    def test_constant_is_gone(self):
        self.assertFalse(hasattr(audit, "STRICT_SINCE"))

    def test_old_dated_missing_fields_are_reported_as_info(self):
        # 旧 STRICT_SINCE(2026-07-02) より前の ts でも欠落を検出する（日付ゲート廃止）
        rows = [{"ts": "2026-01-01T00:00:00.000Z", "kind": "study", "summary": "s",
                 "refs": {"uuid": "u-old"}}]
        self._write_rows("learning", rows)
        self._build_state()
        problems, field_infos = audit.check_logs()
        self.assertEqual(problems, [])  # 欠落は「直したほうがよい点」ではない
        self.assertEqual(len(field_infos), 1)
        self.assertIn("study 行に domain / topic / mastery / note のいずれかが欠落", field_infos[0])
        self.assertNotIn("新仕様", field_infos[0])  # 開発者史の言い回しを出さない

    def test_field_infos_capped_at_five_with_remainder(self):
        rows = [{"ts": f"2026-01-0{i}T00:00:00.000Z", "kind": "study", "summary": "s",
                 "refs": {"uuid": f"u{i}"}} for i in range(1, 9)]  # 8 件の欠落
        self._write_rows("learning", rows)
        self._build_state()
        problems, infos, _cov = audit.audit_report()
        self.assertEqual(problems, [])
        field_lines = [x for x in infos if "欠落" in x]
        self.assertEqual(len(field_lines), 6)          # 5 件 + 「ほか N 件」
        self.assertIn("ほか 3 件", field_lines[-1])

    def test_missing_fields_do_not_flip_exit_semantics(self):
        rows = [{"ts": "2026-01-01T00:00:00.000Z", "kind": "interest", "summary": "s",
                 "refs": {"uuid": "u1"}}]  # topic 欠落
        self._write_rows("life", rows)
        self._build_state()
        problems, infos, _cov = audit.audit_report()
        self.assertEqual(problems, [])  # exit 0 相当
        self.assertTrue(any("topic が欠落" in x for x in infos))


class RenderReportTest(_Home):
    def test_headers_and_fix_hint(self):
        lines = audit.render_report(["こわれた行"], ["参考"], ["[pi] x"])
        self.assertEqual(lines[0], "=== 直したほうがよい点 ===")
        self.assertTrue(any("→ 直し方" in x for x in lines))
        self.assertTrue(any("watari regen" in x for x in lines))
        self.assertIn("=== 参考情報（異常ではありません） ===", lines)
        self.assertIn("=== 記憶に一度も取り込まれていない会話（実発話5件以上） ===", lines)

    def test_no_problems_header(self):
        lines = audit.render_report([], [], None)
        self.assertEqual(lines, ["=== 直したほうがよい点: なし ==="])

    def test_state_divergence_message_mentions_regen(self):
        self._write_rows("life", [_thread("t", "2026-07-01T00:00:00.000Z", "u1")])
        self._build_state()
        # まとめを手で書き換えて食い違いを作る
        st = json.load(open(wl.state_path("life"), encoding="utf-8"))
        st["open_threads"] = []
        wl.atomic_write_json(wl.state_path("life"), st)
        problems = audit.check_state_derivation()
        self.assertTrue(problems)
        self.assertTrue(all("watari regen" in x for x in problems))
        self.assertTrue(all("乖離" not in x for x in problems))

    def test_missing_state_is_problem_with_regen_hint_not_traceback(self):
        self._write_rows("life", [_thread("t", "2026-07-01T00:00:00.000Z", "u1")])
        # state.json を作らない（clone 直後相当）
        problems = audit.check_state_derivation()
        self.assertTrue(any("まとめが未生成" in x and "watari regen" in x for x in problems))

    def test_missing_pi_store_coverage_is_friendly(self):
        self._build_state()
        saved = audit.PI_STORE
        audit.PI_STORE = os.path.join(self._tmp.name, "no-such-store")
        try:
            lines = audit.check_coverage()
        finally:
            audit.PI_STORE = saved
        self.assertEqual(len(lines), 1)
        self.assertIn("まだ会話ログがありません", lines[0])
        self.assertIn("watari chat", lines[0])
        self.assertNotIn("ストア", lines[0])

    def test_unset_up_home_raises_filenotfound_for_caller(self):
        # 記憶フォルダ不在は FileNotFoundError（呼び出し側が MSG_SETUP_REQUIRED を案内する契約）
        saved = wl.MEM
        wl.MEM = os.path.join(self._tmp.name, "nowhere")
        try:
            with self.assertRaises(FileNotFoundError):
                audit.audit_report()
        finally:
            wl.MEM = saved

    def test_setup_required_message_is_unified(self):
        self.assertTrue(wl.MSG_SETUP_REQUIRED.startswith("まだセットアップされていません"))
        self.assertIn("watari install", wl.MSG_SETUP_REQUIRED)


class ReferenceInfoWordingTest(_Home):
    def test_sinking_thread_wording_is_plain(self):
        self._write_rows("life", [_thread("古い話題", "2026-04-25T00:00:00.000Z", "u1")])
        self._build_state(now="2026-07-18T00:00:00.000Z")  # 約84日経過 → まもなく外れる帯
        infos = audit.check_references(wl.parse_ts("2026-07-18T00:00:00.000Z"))
        line = next(x for x in infos if "古い話題" in x)
        self.assertIn("まもなく一覧から外れます", line)
        self.assertIn("記録は残ります", line)
        self.assertNotIn("沈む", line)

    def test_cooling_interest_wording_is_plain(self):
        rows = [{"ts": "2026-07-01T00:00:00.000Z", "kind": "interest", "topic": "jazz",
                 "summary": "s", "note": "n", "heat": 1, "refs": {"uuid": "u1"}}]
        self._write_rows("life", rows)
        self._build_state()
        infos = audit.check_references(wl.parse_ts("2026-07-18T00:00:00.000Z"))
        line = next(x for x in infos if "jazz" in x)
        self.assertIn("最近話題に出ていません", line)
        self.assertNotIn("冷却", line)
        self.assertNotIn("heat", line)

    def test_dangling_related_wording_is_plain(self):
        rows = [{"ts": "2026-07-01T00:00:00.000Z", "kind": "study", "domain": "python",
                 "topic": "t", "mastery": 1, "note": "n", "summary": "s",
                 "related": ["go/x"], "refs": {"uuid": "u1"}}]
        self._write_rows("learning", rows)
        self._build_state()
        infos = audit.check_references(wl.parse_ts("2026-07-18T00:00:00.000Z"))
        line = next(x for x in infos if "go/x" in x)
        self.assertIn("参照先が見つかりません", line)
        self.assertNotIn("宙に浮", line)


class RegenWordingTest(_Home):
    def test_check_helpers_and_messages(self):
        self.assertEqual(regen_state.MSG_CHECK_OK, "まとめは記録と一致しています")
        self.assertIn("watari regen", regen_state.MSG_STATE_MISSING)
        lines = regen_state.render_check_diffs(["≠ life.profile.x: 1 -> 2"])
        self.assertIn("食い違い 1 件", lines[0])
        self.assertIn("watari regen", lines[-1])
        self.assertNotIn("state", lines[0])

    def test_done_message_is_plain(self):
        message = regen_state.done_message(wl.parse_ts("2026-07-18T00:00:00.000Z"))
        self.assertIn("まとめを作り直しました", message)
        self.assertNotIn("state", message)

    def test_load_current_states_raises_when_missing(self):
        with self.assertRaises(FileNotFoundError):
            regen_state.load_current_states()

    def test_semantic_diff_labels_name_sides_plainly(self):
        current = {"life": {"updated": "x", "profile": {"a": 1}, "interests": {},
                            "open_threads": []}}
        generated = {"life": {"updated": "x", "profile": {"b": 2}, "interests": {},
                              "open_threads": []}}
        diffs = regen_state.semantic_diff(current, generated)
        joined = "\n".join(diffs)
        self.assertIn("記録から作り直した側にのみ存在", joined)
        self.assertIn("現在のまとめにのみ存在", joined)
        self.assertNotIn("現state", joined)
        self.assertNotIn("生成側", joined)


if __name__ == "__main__":
    unittest.main()
