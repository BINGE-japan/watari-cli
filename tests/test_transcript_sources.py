"""transcript 系 connector（Claude Code / Codex, auth_kind="local", scope="local"）の契約テスト。

実データ（~/.claude, ~/.codex）は絶対に読まない——各テストは一時ディレクトリに偽のログを作り、
`claude_code.default_root` / `codex.default_root` をその一時ディレクトリへ差し替えて検証する
（test_connect.py が `linear._http` を差し替えるのと同じやり方）。固めること:
- 本物のユーザー発話だけが拾われる（tool_result・meta 行・合成行は除外される）。
- assistant 行が role 付きで拾われる（文脈用。記憶の根拠にはしない）。
- Codex のリプレイ（セッション再開時に過去発話が丸ごと新 ID・新 ts で再記録される実バグ）が
  除外される。novel な発話以降は同文が再登場しても残る。
- カーソル(since)以降だけが ts 昇順で返る。
- `watari connect claude-code`/`codex` が検出パスを保存し connector 宣言(scope="local")を作る。
- 検出できない場合はパス入力へ落ち、入力されたパスを検証して保存する。
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest

from watari_cli import config
from watari_cli.cli import _build_parser
from watari_cli.transcripts import claude_code, codex, common


def _run(argv):
    os.environ["WATARI_CONNECT_ALLOW_NO_TTY"] = "1"  # テストは非TTY実行のため許可
    args = _build_parser().parse_args(argv)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = args.func(args)
    return rc, out.getvalue(), err.getvalue()


def _write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


class _XdgIsolated(unittest.TestCase):
    """XDG_CONFIG_HOME を隔離し、connectors_auth.<name>.path を config.json に閉じ込める。"""

    def setUp(self):
        self._cfg = tempfile.TemporaryDirectory(prefix="watari-transcripts-cfg-")
        self._saved_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._cfg.name
        from watari_cli import prompts
        self._saved_prompts = {"text": prompts.text, "select": prompts.select}

    def tearDown(self):
        from watari_cli import prompts
        prompts.text = self._saved_prompts["text"]
        prompts.select = self._saved_prompts["select"]
        if self._saved_xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._saved_xdg
        self._cfg.cleanup()


# ---- (a)/(b)/(d) Claude Code: 選別・role・カーソル ------------------------------------

class ClaudeCodeReadTest(_XdgIsolated):
    def setUp(self):
        super().setUp()
        self._home = tempfile.TemporaryDirectory(prefix="watari-cc-logs-")
        common.save_path(claude_code.NAME, self._home.name)

    def tearDown(self):
        self._home.cleanup()
        super().tearDown()

    def _session_path(self, project="proj", session="sess-1"):
        return os.path.join(self._home.name, project, f"{session}.jsonl")

    def test_only_genuine_user_rows_are_kept(self):
        path = self._session_path()
        rows = [
            {"type": "user", "uuid": "u1", "timestamp": "2026-07-01T00:00:00.000Z",
             "cwd": "/repo", "message": {"role": "user", "content": "本物の発話1"}},
            # tool_result: content が配列（除外）
            {"type": "user", "uuid": "u2", "timestamp": "2026-07-01T00:01:00.000Z",
             "cwd": "/repo", "message": {"role": "user", "content": [{"type": "tool_result"}]}},
            # toolUseResult キーを持つ行は除外
            {"type": "user", "uuid": "u3", "timestamp": "2026-07-01T00:02:00.000Z",
             "cwd": "/repo", "message": {"role": "user", "content": "misleading"},
             "toolUseResult": {"x": 1}},
            # isMeta
            {"type": "user", "uuid": "u4", "timestamp": "2026-07-01T00:03:00.000Z",
             "cwd": "/repo", "message": {"role": "user", "content": "meta"}, "isMeta": True},
            # isCompactSummary
            {"type": "user", "uuid": "u5", "timestamp": "2026-07-01T00:04:00.000Z",
             "cwd": "/repo", "message": {"role": "user", "content": "compact"},
             "isCompactSummary": True},
            # isSidechain
            {"type": "user", "uuid": "u6", "timestamp": "2026-07-01T00:05:00.000Z",
             "cwd": "/repo", "message": {"role": "user", "content": "side"}, "isSidechain": True},
            # timestamp なし
            {"type": "user", "uuid": "u7",
             "cwd": "/repo", "message": {"role": "user", "content": "no ts"}},
            # 合成行（system-reminder 混入）
            {"type": "user", "uuid": "u8", "timestamp": "2026-07-01T00:06:00.000Z",
             "cwd": "/repo", "message": {"role": "user",
             "content": "<system-reminder>hi</system-reminder>本文"}},
            # 合成行（スラッシュコマンド実行結果）
            {"type": "user", "uuid": "u9", "timestamp": "2026-07-01T00:07:00.000Z",
             "cwd": "/repo", "message": {"role": "user",
             "content": "<command-name>/foo</command-name><local-command-stdout>ok</local-command-stdout>"}},
        ]
        _write_jsonl(path, rows)
        result = claude_code.read(None)
        self.assertEqual([r["uuid"] for r in result], ["claude-code:u1"])
        self.assertEqual(result[0]["role"], "user")
        self.assertEqual(result[0]["text"], "本物の発話1")
        self.assertEqual(result[0]["meta"], {"cwd": "/repo", "session": "sess-1"})
        self.assertEqual(set(result[0].keys()), {"ts", "uuid", "text", "meta", "role"})

    def test_assistant_rows_are_kept_with_role_and_text_blocks_only(self):
        path = self._session_path()
        rows = [
            {"type": "assistant", "uuid": "a1", "timestamp": "2026-07-01T00:00:00.000Z",
             "cwd": "/repo", "message": {"role": "assistant", "content": [
                 {"type": "thinking", "thinking": "内部思考"},
                 {"type": "text", "text": "本文だけ拾う"},
                 {"type": "tool_use", "name": "Bash", "input": {}},
             ]}},
            # サブエージェント(isSidechain)はユーザー本人ではないため除外
            {"type": "assistant", "uuid": "a2", "timestamp": "2026-07-01T00:01:00.000Z",
             "cwd": "/repo", "isSidechain": True,
             "message": {"role": "assistant", "content": [{"type": "text", "text": "サブエージェント"}]}},
        ]
        _write_jsonl(path, rows)
        result = claude_code.read(None)
        self.assertEqual([r["uuid"] for r in result], ["claude-code:a1"])
        self.assertEqual(result[0]["role"], "assistant")
        self.assertEqual(result[0]["text"], "本文だけ拾う")

    def test_cursor_and_ascending_order(self):
        path = self._session_path()
        rows = [
            {"type": "user", "uuid": "u-late", "timestamp": "2026-07-03T00:00:00.000Z",
             "cwd": "/repo", "message": {"role": "user", "content": "遅い"}},
            {"type": "user", "uuid": "u-mid", "timestamp": "2026-07-02T00:00:00.000Z",
             "cwd": "/repo", "message": {"role": "user", "content": "中間"}},
            {"type": "user", "uuid": "u-early", "timestamp": "2026-07-01T00:00:00.000Z",
             "cwd": "/repo", "message": {"role": "user", "content": "早い"}},
        ]
        _write_jsonl(path, rows)
        result = claude_code.read("2026-07-01T12:00:00.000Z")
        self.assertEqual([r["uuid"] for r in result], ["claude-code:u-mid", "claude-code:u-late"])
        self.assertEqual([r["ts"] for r in result], sorted(r["ts"] for r in result))


# ---- (c)/(d) Codex: リプレイ除去・カーソル -----------------------------------------------

def _session_meta(session_id, cwd):
    return {"type": "session_meta", "payload": {"id": session_id, "cwd": cwd}}


def _user_msg(ts, text):
    return {"type": "event_msg", "timestamp": ts,
           "payload": {"type": "user_message", "message": text}}


def _agent_msg(ts, text):
    return {"type": "event_msg", "timestamp": ts,
           "payload": {"type": "agent_message", "message": text}}


class CodexReplayTest(_XdgIsolated):
    def setUp(self):
        super().setUp()
        self._home = tempfile.TemporaryDirectory(prefix="watari-codex-logs-")
        common.save_path(codex.NAME, self._home.name)

    def tearDown(self):
        self._home.cleanup()
        super().tearDown()

    def _path(self, y, m, d, name):
        return os.path.join(self._home.name, y, m, d, name)

    def test_replayed_prefix_is_dropped_novel_tail_is_kept(self):
        # セッション A（最初の発話）。
        file_a = self._path("2026", "07", "01", "rollout-sess-a.jsonl")
        _write_jsonl(file_a, [
            _session_meta("sess-A", "/proj"),
            _user_msg("2026-07-01T00:00:00.000Z", "hello"),
            _agent_msg("2026-07-01T00:01:00.000Z", "hi there"),
            _user_msg("2026-07-01T00:02:00.000Z", "continue"),
        ])
        # セッション B は A を再開: Codex の実バグにより A の全発話が新 ID・新 ts で
        # 丸ごと再記録され（先頭3件）、そのあとに本当に新しい発話が続く。
        file_b = self._path("2026", "07", "02", "rollout-sess-b.jsonl")
        _write_jsonl(file_b, [
            _session_meta("sess-B", "/proj"),
            _user_msg("2026-07-02T00:00:00.000Z", "hello"),        # リプレイ（捨てる）
            _agent_msg("2026-07-02T00:01:00.000Z", "hi there"),    # リプレイ（捨てる）
            _user_msg("2026-07-02T00:02:00.000Z", "continue"),     # リプレイ（捨てる）
            _user_msg("2026-07-02T00:03:00.000Z", "what's next"),  # novel（残す）
            _user_msg("2026-07-02T00:04:00.000Z", "continue"),     # novel 以降なので同文でも残す
        ])
        rows = codex.read(None)
        texts = [r["text"] for r in rows]
        self.assertEqual(texts, ["hello", "hi there", "continue", "what's next", "continue"])
        self.assertEqual([r["role"] for r in rows],
                         ["user", "assistant", "user", "user", "user"])
        # 元発話(A)はそのまま残り、B は再記録された3件が出てこない(novel の2件だけ)。
        self.assertEqual(sum(1 for r in rows if r["meta"]["session"] == "sess-A"), 3)
        self.assertEqual(sum(1 for r in rows if r["meta"]["session"] == "sess-B"), 2)
        self.assertEqual(set(rows[0].keys()), {"ts", "uuid", "text", "meta", "role"})

    def test_entirely_replayed_session_is_dropped(self):
        # セッション再開が続きの発話を生まないまま終わる（全件リプレイ）ケース。
        file_a = self._path("2026", "07", "01", "rollout-sess-a.jsonl")
        _write_jsonl(file_a, [
            _session_meta("sess-A", "/proj"),
            _user_msg("2026-07-01T00:00:00.000Z", "hello"),
        ])
        file_b = self._path("2026", "07", "02", "rollout-sess-b.jsonl")
        _write_jsonl(file_b, [
            _session_meta("sess-B", "/proj"),
            _user_msg("2026-07-02T00:00:00.000Z", "hello"),  # 丸ごとリプレイ
        ])
        rows = codex.read(None)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["meta"]["session"], "sess-A")

    def test_cursor_applies_after_replay_filter(self):
        file_a = self._path("2026", "07", "01", "rollout-sess-a.jsonl")
        _write_jsonl(file_a, [
            _session_meta("sess-A", "/proj"),
            _user_msg("2026-07-01T00:00:00.000Z", "hello"),
            _user_msg("2026-07-01T00:01:00.000Z", "continue"),
        ])
        file_b = self._path("2026", "07", "02", "rollout-sess-b.jsonl")
        _write_jsonl(file_b, [
            _session_meta("sess-B", "/proj"),
            _user_msg("2026-07-02T00:00:00.000Z", "hello"),        # リプレイ（ts は新しいが捨てる）
            _user_msg("2026-07-02T00:01:00.000Z", "continue"),     # リプレイ
            _user_msg("2026-07-02T00:02:00.000Z", "what's next"),  # novel
        ])
        # since を A のカーソル直後にしても、B のリプレイ(ts は since より新しい)は出てこない。
        rows = codex.read("2026-07-01T00:01:30.000Z")
        self.assertEqual([r["text"] for r in rows], ["what's next"])


# ---- (e)/(f) connect: 検出→宣言 / 未検出→手入力 -------------------------------------

class ConnectTranscriptSourceTest(_XdgIsolated):
    def setUp(self):
        super().setUp()
        self._saved_cc_root = claude_code.default_root
        self._saved_codex_root = codex.default_root
        self._logs = tempfile.TemporaryDirectory(prefix="watari-cc-detect-")
        self._empty = tempfile.TemporaryDirectory(prefix="watari-cc-empty-")
        _write_jsonl(os.path.join(self._logs.name, "proj", "s1.jsonl"), [
            {"type": "user", "uuid": "u1", "timestamp": "2026-07-01T00:00:00.000Z",
             "cwd": "/proj", "message": {"role": "user", "content": "hi"}},
        ])
        _write_jsonl(os.path.join(self._logs.name, "proj", "s2.jsonl"), [
            {"type": "user", "uuid": "u2", "timestamp": "2026-07-01T00:00:00.000Z",
             "cwd": "/proj", "message": {"role": "user", "content": "hi2"}},
        ])
        self._codex_logs = tempfile.TemporaryDirectory(prefix="watari-codex-detect-")
        _write_jsonl(
            os.path.join(self._codex_logs.name, "2026", "07", "01", "rollout-sess-a.jsonl"),
            [_session_meta("sess-A", "/proj"), _user_msg("2026-07-01T00:00:00.000Z", "hi")])

    def tearDown(self):
        claude_code.default_root = self._saved_cc_root
        codex.default_root = self._saved_codex_root
        self._logs.cleanup()
        self._empty.cleanup()
        self._codex_logs.cleanup()
        super().tearDown()

    def test_detects_default_path_and_declares_local_connector(self):
        claude_code.default_root = lambda: self._logs.name
        rc, out, err = _run(["connect", "claude-code"])
        self.assertEqual(rc, 0, err)
        self.assertIn("見つけました", out)
        self.assertIn(self._logs.name, out)
        self.assertIn("セッション 2 件", out)
        self.assertEqual(common.configured_path(claude_code.NAME), self._logs.name)
        decl = config.load_connectors()
        self.assertEqual(len(decl), 1)
        self.assertEqual((decl[0]["name"], decl[0]["scope"]), ("claude-code", "local"))

    def test_falls_back_to_manual_path_when_not_found(self):
        claude_code.default_root = lambda: self._empty.name  # 空ディレクトリ＝セッション0件
        from watari_cli import prompts
        prompts.text = lambda *a, **k: self._logs.name
        rc, out, err = _run(["connect", "claude-code"])
        self.assertEqual(rc, 0, err)
        self.assertIn(self._logs.name, out)
        self.assertEqual(common.configured_path(claude_code.NAME), self._logs.name)
        decl = config.load_connectors()
        self.assertEqual((decl[0]["name"], decl[0]["scope"]), ("claude-code", "local"))

    def test_empty_manual_path_aborts_without_saving(self):
        claude_code.default_root = lambda: self._empty.name
        from watari_cli import prompts
        prompts.text = lambda *a, **k: ""
        rc, _out, _err = _run(["connect", "claude-code"])
        self.assertEqual(rc, 1)
        self.assertIsNone(common.configured_path(claude_code.NAME))
        self.assertEqual(config.load_connectors(), [])

    def test_codex_detects_default_path_and_declares_local_connector(self):
        codex.default_root = lambda: self._codex_logs.name
        rc, out, err = _run(["connect", "codex"])
        self.assertEqual(rc, 0, err)
        self.assertIn("見つけました", out)
        self.assertIn(self._codex_logs.name, out)
        self.assertIn("セッション 1 件", out)
        self.assertEqual(common.configured_path(codex.NAME), self._codex_logs.name)
        decl = config.load_connectors()
        self.assertEqual((decl[0]["name"], decl[0]["scope"]), ("codex", "local"))

    def test_codex_falls_back_to_manual_path_when_not_found(self):
        codex.default_root = lambda: self._empty.name  # 空ディレクトリ＝セッション0件
        from watari_cli import prompts
        prompts.text = lambda *a, **k: self._codex_logs.name
        rc, out, err = _run(["connect", "codex"])
        self.assertEqual(rc, 0, err)
        self.assertIn(self._codex_logs.name, out)
        self.assertEqual(common.configured_path(codex.NAME), self._codex_logs.name)
        decl = config.load_connectors()
        self.assertEqual((decl[0]["name"], decl[0]["scope"]), ("codex", "local"))


if __name__ == "__main__":
    unittest.main()
