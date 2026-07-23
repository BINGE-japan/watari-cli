"""prompts（ゼロ依存の対話部品）の入力契約テスト。

- confirm: 認識できない入力は既定に落とさず聞き直す。全角 ｙ/ｎ・はい/いいえも受ける。
- 番号選択（非TTYフォールバック）: 範囲外・解析不能は既定に落とさず聞き直す。
- 空 Enter / EOF は従来どおり既定を採用（スクリプト実行で固まらない）。
"""
from __future__ import annotations

import builtins
import contextlib
import io
import unittest

from watari_cli import prompts


def _feed(monkey_inputs):
    """input() をモックし、尽きたら EOFError を出す。"""
    answers = iter(monkey_inputs)

    def fake_input(prompt_text=""):
        try:
            return next(answers)
        except StopIteration:
            raise EOFError

    return fake_input


class ConfirmTest(unittest.TestCase):
    def _confirm(self, inputs, default=True):
        saved = builtins.input
        builtins.input = _feed(inputs)
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                result = prompts.confirm("続けますか？", default=default)
        finally:
            builtins.input = saved
        return result, out.getvalue()

    def test_unrecognized_input_reasks_instead_of_defaulting(self):
        result, out = self._confirm(["ok", "n"], default=True)
        self.assertFalse(result)  # 「ok」を無言で Yes/No 扱いしない
        self.assertIn("y（はい）か n（いいえ）で答えてください", out)

    def test_fullwidth_and_japanese_answers_accepted(self):
        self.assertTrue(self._confirm(["ｙ"], default=False)[0])
        self.assertFalse(self._confirm(["ｎ"], default=True)[0])
        self.assertTrue(self._confirm(["はい"], default=False)[0])
        self.assertFalse(self._confirm(["いいえ"], default=True)[0])

    def test_empty_and_eof_take_default(self):
        self.assertTrue(self._confirm([""], default=True)[0])
        self.assertFalse(self._confirm([], default=False)[0])  # 即 EOF → 既定


class SelectLinesTest(unittest.TestCase):
    OPTIONS = [("一つ目", "a"), ("二つ目", "b"), ("三つ目", "c")]

    def _select(self, inputs, default=0):
        saved = builtins.input
        builtins.input = _feed(inputs)
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                result = prompts._select_lines("選んでください", self.OPTIONS, default)
        finally:
            builtins.input = saved
        return result, out.getvalue()

    def test_out_of_range_number_reasks(self):
        result, out = self._select(["9", "2"])
        self.assertEqual(result, "b")  # 範囲外を黙って既定にしない
        self.assertIn("1〜3 の番号を入力してください", out)

    def test_non_numeric_input_reasks(self):
        result, out = self._select(["abc", "3"])
        self.assertEqual(result, "c")
        self.assertIn("1〜3 の番号を入力してください", out)

    def test_empty_and_eof_take_default(self):
        self.assertEqual(self._select([""], default=1)[0], "b")
        self.assertEqual(self._select([], default=2)[0], "c")  # 即 EOF → 既定


if __name__ == "__main__":
    unittest.main()
