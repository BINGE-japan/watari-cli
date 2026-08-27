"""同梱スラッシュコマンド（skill/prompts/*.md）と SKILL.md の語彙契約テスト。

- prompts/ に 6 コマンドが揃い、各ファイルの frontmatter に description があること
  （Pi の /help 一覧に説明が出るための必須メタデータ）。
- SKILL.md がユーザー可視の内輪語（カセット・後で効く）を含まないこと。
- 「夢」は旧い合図の受理を規定する 1 箇所だけに現れること（表示語彙は「記憶の整理」）。
"""
from __future__ import annotations

import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1] / "src" / "watari_cli" / "skill"
PROMPTS_DIR = SKILL_DIR / "prompts"
SKILL_MD = SKILL_DIR / "SKILL.md"

EXPECTED_PROMPTS = ("remember", "organize", "profile", "forget", "goal", "watari-help")


def _frontmatter_lines(text: str) -> list[str]:
    """先頭の frontmatter（--- ... ---）の中身を行のリストで返す。無ければ空。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return lines[1:index]
    return []


class BundledPromptsTest(unittest.TestCase):
    def test_six_prompts_exist_with_description(self):
        for name in EXPECTED_PROMPTS:
            path = PROMPTS_DIR / f"{name}.md"
            with self.subTest(prompt=name):
                self.assertTrue(path.is_file(), f"同梱プロンプトが無い: {path}")
                text = path.read_text(encoding="utf-8")
                frontmatter = _frontmatter_lines(text)
                self.assertTrue(frontmatter, f"frontmatter（---）が無い: {name}.md")
                self.assertTrue(
                    any(line.startswith("description:") for line in frontmatter),
                    f"frontmatter に description が無い: {name}.md",
                )
                body = text.split("---", 2)[-1].strip()
                self.assertTrue(body, f"本文が空: {name}.md")

    def test_tool_work_does_not_force_a_template_progress_message(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        self.assertIn("必要がある場合", text)
        self.assertIn("定型の進捗報告を毎回強制しない", text)
        self.assertIn("内部推論やコマンド内容は書かない", text)
        self.assertNotIn("実行前に「今から何を確認・変更するか」", text)

    def test_skill_has_no_insider_jargon(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        for banned in ("カセット", "後で効く", "あとで効く"):
            self.assertNotIn(banned, text, f"SKILL.md に内輪語が残っている: {banned}")

    def test_skill_dream_appears_only_as_accepted_alias(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        self.assertEqual(
            text.count("夢"), 1,
            "SKILL.md の「夢」は旧い合図の受理を規定する 1 箇所だけであること",
        )
        self.assertIn("夢を見て", text)  # その 1 箇所は「夢を見て」の受理規定

    def test_skill_uses_organize_trigger(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        self.assertIn("記憶を整理して", text)


if __name__ == "__main__":
    unittest.main()
