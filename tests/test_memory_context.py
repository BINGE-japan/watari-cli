"""Each user turn gets small, relevant memory without loading the whole summary."""
from __future__ import annotations

import json
import shutil
import subprocess
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "src" / "watari_cli" / "pi" / "memory-context.mjs"
EXTENSION = ROOT / "src" / "watari_cli" / "pi" / "memory-context.ts"
SKILL = ROOT / "src" / "watari_cli" / "skill" / "SKILL.md"


def _build(life: dict, learning: dict, query: str, max_bytes: int = 16_000) -> dict:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is required by the Pi runtime")
    script = (
        f"import {{ buildMemoryContext }} from {json.dumps(HELPER.as_uri())};"
        "import { readFileSync } from 'node:fs';"
        "const [life,learning,query,maxBytes]=JSON.parse(readFileSync(0,'utf8'));"
        "console.log(JSON.stringify(buildMemoryContext(life,learning,query,{maxBytes})));"
    )
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        input=json.dumps([life, learning, query, max_bytes], ensure_ascii=False),
        capture_output=True, text=True, timeout=15, check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def _states(topic_count: int = 0) -> tuple[dict, dict]:
    life = {
        "updated": "2026-01-01T00:00:00.000Z",
        "profile": {
            "name": "sample-user",
            "teaching_style": "答えを与えず一工程ずつ進める",
        },
        "facts": {},
        "interests": {
            "音楽制作": {"last": "2026-01-01T00:00:00.000Z", "heat": 2,
                     "note": "ライブ用の音源を制作する。"},
        },
        "open_threads": [
            {"topic": "Watariの応答高速化", "last": "2026-01-03T00:00:00.000Z",
             "note": "毎回の入力を軽くしつつ関連する記憶は必ず確認する。"},
            {"topic": "確定申告", "last": "2026-01-02T00:00:00.000Z",
             "note": "領収書の整理が残る。", "deadline": "2026-03-01T00:00:00.000Z"},
        ],
    }
    topics = {
        "TypeScript": {
            "mastery": 2,
            "freshness": "2026-01-04T00:00:00.000Z",
            "last": "2026-01-04T00:00:00.000Z",
            "note": "strictNullChecksとSymbol型を学習済み。",
            "related": ["web/Vue"],
        },
        "Vue": {
            "mastery": 1,
            "freshness": "2026-01-02T00:00:00.000Z",
            "last": "2026-01-02T00:00:00.000Z",
            "note": "コンポーネントの入口まで学習。",
            "related": ["web/TypeScript"],
        },
    }
    for index in range(topic_count):
        topics[f"合成トピック{index:04d}"] = {
            "mastery": 1,
            "freshness": "2026-01-01T00:00:00.000Z",
            "last": "2026-01-01T00:00:00.000Z",
            "note": f"検索性能確認用の長い説明 {index} " + "あ" * 120,
            "related": [],
        }
    learning = {
        "updated": "2026-01-04T00:00:00.000Z",
        "domains": {"web": {"topics": topics}},
    }
    return life, learning


class MemoryContextTest(unittest.TestCase):
    def test_relevant_detail_is_selected_while_profile_is_always_present(self):
        life, learning = _states()
        result = _build(life, learning, "strictNullChecksはどこまで理解してた？")
        self.assertEqual(result["profile"]["name"], "sample-user")
        matches = {(item["kind"], item["topic"]) for item in result["matches"]}
        self.assertIn(("study", "TypeScript"), matches)
        self.assertNotIn(("interest", "音楽制作"), matches)

    def test_relevant_fact_is_searchable_without_being_always_present(self):
        life, learning = _states()
        life["facts"] = {
            "render_backend": {
                "last": "2026-01-05T00:00:00.000Z",
                "note": "描画基盤にはAurora Engineを使う。",
            },
        }
        result = _build(life, learning, "Aurora Engineの描画基盤は？")
        self.assertNotIn("render_backend", result["profile"])
        self.assertIn(
            ("fact", "render_backend"),
            {(item["kind"], item["topic"]) for item in result["matches"]},
        )
        self.assertIn("render_backend", result["catalog"]["facts"])

    def test_catalog_keeps_topic_names_without_all_notes(self):
        life, learning = _states()
        result = _build(life, learning, "こんにちは")
        self.assertIn("Watariの応答高速化", result["catalog"]["threads"])
        self.assertIn("音楽制作", result["catalog"]["interests"])
        self.assertIn("TypeScript", result["catalog"]["learning"]["web"])
        rendered = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("strictNullChecksとSymbol型を学習済み", rendered)

    def test_oversized_profile_cannot_evict_attention_matches_and_catalog(self):
        life, learning = _states()
        life["profile"] = {f"account_fact_{index:03d}": "x" * 500 for index in range(40)}
        life["profile"]["z_response_style"] = "回答は必ず簡潔にする。" + "y" * 900
        life["facts"] = {
            "aurora_renderer": {
                "last": "2026-01-05T00:00:00.000Z",
                "note": "Aurora Rendererの移行判断を記録している。",
            },
        }
        result = _build(life, learning, "Aurora Renderer")
        self.assertTrue(result["profile_truncated"])
        self.assertIn("z_response_style", result["profile"])
        self.assertEqual(len(result["attention"]), 2)
        self.assertIn("aurora_renderer", {item["topic"] for item in result["matches"]})
        self.assertIn("Watariの応答高速化", result["catalog"]["threads"])
        self.assertIn("TypeScript", result["catalog"]["learning"]["web"])

    def test_common_negative_phrase_does_not_create_false_match(self):
        life, learning = _states()
        life["open_threads"] = [{
            "topic": "自動更新の修復",
            "last": "2026-01-03T00:00:00.000Z",
            "note": "自動更新されない問題を修復する。",
        }]
        result = _build(life, learning, "具体的に何が正常じゃないの？")
        self.assertEqual(result["matches"], [])

    def test_rendered_context_has_a_hard_byte_cap(self):
        life, learning = _states(topic_count=500)
        result = _build(life, learning, "合成トピック0499", max_bytes=16_000)
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
        self.assertLessEqual(len(encoded), 16_000)
        self.assertTrue(result["catalog_truncated"])
        self.assertIn("合成トピック0499", {item["topic"] for item in result["matches"]})

    def test_local_search_is_fast_enough_for_every_turn(self):
        life, learning = _states(topic_count=500)
        started = time.perf_counter()
        for _ in range(10):
            result = _build(life, learning, "合成トピック0499")
            self.assertTrue(result["memory_checked"])
        elapsed = time.perf_counter() - started
        # Includes starting Node ten times; local lookup itself is much faster.
        self.assertLess(elapsed, 3.0)

    def test_pi_injects_memory_before_model_without_persisting_a_message(self):
        text = EXTENSION.read_text(encoding="utf-8")
        self.assertIn('pi.on("before_agent_start"', text)
        self.assertIn("loadMemoryContext", text)
        self.assertNotIn("pi.sendMessage", text)

    def test_session_opening_no_longer_loads_the_whole_memory_summary(self):
        text = SKILL.read_text(encoding="utf-8")
        opening = text.split("## セッションの開き方", 1)[1].split("## 会話中にやること", 1)[0]
        self.assertNotIn("watari recall", opening)
        self.assertIn("入力前に自動で確認", opening)


if __name__ == "__main__":
    unittest.main()
