"""AIへ秘密を渡さず、固定されたWatari操作だけを公開する補助機能の契約テスト。"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "src" / "watari_cli" / "pi" / "secure-memory.mjs"


class SecretRedactionTest(unittest.TestCase):
    def test_known_credential_shapes_and_secret_fields_are_redacted(self):
        node = shutil.which("node")
        if not node:
            raise unittest.SkipTest("node is required by the Pi runtime")
        synthetic = {
            "api_key": "synthetic-api-key-value",
            "nested": {
                "refresh_token": "synthetic-refresh-value",
                "token": "synthetic-unpatterned-token",
                "message": "token=" + "xoxp-" + "1234567890-abcdefghijklmnopqrstuv",
                "linear": "lin_api_" + "synthetic0123456789abcdefghijklmnop",
                "normal": "keep me",
            },
        }
        script = (
            f"import {{ redactSensitiveValue }} from {json.dumps(CORE.as_uri())};"
            "console.log(JSON.stringify(redactSensitiveValue(JSON.parse(process.argv[1]))));"
        )
        result = subprocess.run(
            [node, "--input-type=module", "-e", script, json.dumps(synthetic)],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr)
        redacted = json.loads(result.stdout)
        self.assertEqual(redacted["nested"]["normal"], "keep me")
        self.assertNotIn("synthetic-api-key-value", result.stdout)
        self.assertNotIn("synthetic-refresh-value", result.stdout)
        self.assertNotIn("synthetic-unpatterned-token", result.stdout)
        self.assertNotIn("xoxp-", result.stdout)
        self.assertNotIn("lin_api_", result.stdout)

    def test_linear_tools_are_fixed_and_confirmation_gated(self):
        source = (ROOT / "src" / "watari_cli" / "pi" / "secure-memory.ts").read_text()
        self.assertIn('name: "watari_linear_catalog"', source)
        self.assertIn('name: "watari_linear_action"', source)
        self.assertIn('ctx.ui.confirm(', source)
        self.assertIn('if (!ctx.hasUI)', source)
        self.assertIn('["linear", "action", "--request", file]', source)
        self.assertNotIn("params.query", source)
        self.assertNotIn('action: Type.Literal("graphql")', source)


if __name__ == "__main__":
    unittest.main()
