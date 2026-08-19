"""Watari botのSlack送信は、Pi画面の本人確認を通した専用toolだけが担う。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "src" / "watari_cli" / "pi" / "slack-send.mjs"
EXTENSION = ROOT / "src" / "watari_cli" / "pi" / "slack-send.ts"
SKILL = ROOT / "src" / "watari_cli" / "skill" / "SKILL.md"


def _node(script: str, argument=None, env=None):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is required by the Pi runtime")
    command = [node, "--input-type=module", "-e", script]
    if argument is not None:
        command.append(json.dumps(argument, ensure_ascii=False))
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=10, check=False,
        env=(os.environ | (env or {})),
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class SlackSendHelperTest(unittest.TestCase):
    def test_bot_token_is_loaded_separately_from_read_token(self):
        with tempfile.TemporaryDirectory(prefix="watari-slack-send-") as root:
            config_dir = Path(root) / "watari"
            config_dir.mkdir()
            (config_dir / "config.json").write_text(json.dumps({
                "connectors_auth": {
                    "slack": {"api_key": "xoxp-read", "bot_token": "xoxb-write"},
                },
            }), encoding="utf-8")
            script = (
                f'import {{ loadSlackBotToken }} from {json.dumps(HELPER.as_uri())};'
                'console.log(JSON.stringify(loadSlackBotToken()));'
            )
            self.assertEqual(_node(script, env={"XDG_CONFIG_HOME": root}), "xoxb-write")

    def test_missing_bot_token_fails_with_reconnect_instruction(self):
        with tempfile.TemporaryDirectory(prefix="watari-slack-send-") as root:
            config_dir = Path(root) / "watari"
            config_dir.mkdir()
            (config_dir / "config.json").write_text(json.dumps({
                "connectors_auth": {"slack": {"api_key": "xoxp-read"}},
            }), encoding="utf-8")
            script = (
                f'import {{ loadSlackBotToken }} from {json.dumps(HELPER.as_uri())};'
                'try { loadSlackBotToken(); } catch (error) {'
                ' console.log(JSON.stringify(String(error.message))); }'
            )
            message = _node(script, env={"XDG_CONFIG_HOME": root})
            self.assertIn("watari connect slack", message)
            self.assertNotIn("xoxp-read", message)

    def test_approval_preview_contains_sender_destination_recipient_and_full_text(self):
        params = {
            "destination": "#general の書き込みスレッド",
            "recipient": "Example Recipient",
            "channel": "C123",
            "thread_ts": "1787000000.123456",
            "text": "一行目\n\n二行目",
        }
        script = (
            f'import {{ approvalPreview }} from {json.dumps(HELPER.as_uri())};'
            'console.log(JSON.stringify(approvalPreview(JSON.parse(process.argv[1]))));'
        )
        preview = _node(script, params)
        self.assertIn("送信元: Watari (Slack app)", preview)
        self.assertIn("送信先: #general の書き込みスレッド", preview)
        self.assertIn("宛先: Example Recipient", preview)
        self.assertIn("一行目\n\n二行目", preview)
        self.assertIn("C123", preview)

    def test_post_uses_bot_token_and_exact_thread_payload(self):
        params = {
            "token": "xoxb-write",
            "channel": "C123",
            "threadTs": "1787000000.123456",
            "text": " 承認済みの全文\n",
            "clientMsgId": "11111111-1111-4111-8111-111111111111",
        }
        script = f'''
import {{ postSlackMessage }} from {json.dumps(HELPER.as_uri())};
const calls=[];
const response=await postSlackMessage(JSON.parse(process.argv[1]), async (url, options) => {{
  calls.push({{url, options}});
  return {{json: async () => ({{ok:true, channel:"C123", ts:"1787000001.000001", message:{{thread_ts:"1787000000.123456", text:" 承認済みの全文\\n"}}}})}};
}});
const call=calls[0];
console.log(JSON.stringify({{response, url:call.url, authorization:call.options.headers.Authorization, body:JSON.parse(call.options.body)}}));
'''
        result = _node(script, params)
        self.assertEqual(result["url"], "https://slack.com/api/chat.postMessage")
        self.assertEqual(result["authorization"], "Bearer xoxb-write")
        self.assertEqual(result["body"], {
            "channel": "C123",
            "text": " 承認済みの全文\n",
            "client_msg_id": "11111111-1111-4111-8111-111111111111",
            "thread_ts": "1787000000.123456",
        })
        self.assertTrue(result["response"]["ok"])

    def test_not_in_channel_has_actionable_error_without_secret(self):
        params = {"token": "xoxb-secret", "channel": "C123", "text": "x"}
        script = f'''
import {{ postSlackMessage }} from {json.dumps(HELPER.as_uri())};
try {{
  await postSlackMessage(JSON.parse(process.argv[1]), async () => ({{json: async () => ({{ok:false,error:"not_in_channel"}})}}));
}} catch (error) {{ console.log(JSON.stringify(String(error.message))); }}
'''
        message = _node(script, params)
        self.assertIn("Watari", message)
        self.assertIn("招待", message)
        self.assertNotIn("xoxb-secret", message)

    def test_extension_fails_closed_and_confirms_before_posting(self):
        source = EXTENSION.read_text(encoding="utf-8")
        self.assertIn("ctx.hasUI", source)
        self.assertIn("ctx.ui.confirm", source)
        self.assertIn("approvalPreview", source)
        self.assertIn("Watari (Slack app)", (ROOT / "src" / "watari_cli" / "pi" / "slack-send.mjs").read_text(encoding="utf-8"))
        self.assertLess(source.index("ctx.ui.confirm"), source.index("await postSlackMessage"))
        self.assertIn("明示的に承認", source)

    def test_persona_requires_exact_human_approval_and_forbids_bot_substitution(self):
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn("相手だけで意味が分かる完全な文面", skill)
        self.assertIn("送信先・送信元", skill)
        self.assertIn("その提示後に同じ内容への明示承認", skill)
        self.assertIn("別bot・代理アカウントを黙って使わず", skill)
        self.assertIn("watari_slack_send", skill)


if __name__ == "__main__":
    unittest.main()
