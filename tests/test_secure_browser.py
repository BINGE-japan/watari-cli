"""Authenticated browser access is host-mediated and restricted to explicit sites."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "src" / "watari_cli" / "pi" / "secure-browser.mjs"
EXTENSION = ROOT / "src" / "watari_cli" / "pi" / "secure-browser.ts"


def _node(expression: str, *args: str):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is required")
    script = f"import * as b from {json.dumps(CORE.as_uri())}; {expression}"
    result = subprocess.run(
        [node, "--input-type=module", "-e", script, *args],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class SecureBrowserPolicyTest(unittest.TestCase):
    def test_allowed_hosts_are_explicit_and_suffix_spoofing_is_rejected(self):
        result = _node(
            "const h=b.parseAllowedHosts('mail.google.com, linear.app, https://bad.example,');"
            "console.log(JSON.stringify({hosts:[...h],good:b.isAllowedPageUrl('https://mail.google.com/mail/u/0/#inbox',h),"
            "spoof:b.isAllowedPageUrl('https://mail.google.com.attacker.invalid/',h),"
            "other:b.isAllowedPageUrl('https://example.com/',h)}));"
        )
        self.assertEqual(result["hosts"], ["mail.google.com", "linear.app"])
        self.assertTrue(result["good"])
        self.assertFalse(result["spoof"])
        self.assertFalse(result["other"])

    def test_debugging_endpoint_cannot_redirect_the_bridge_off_loopback(self):
        result = _node(
            "const urls=['ws://127.0.0.1:9223/devtools/page/abc',"
            "'ws://attacker.invalid/devtools/page/abc','wss://localhost/devtools/page/abc'];"
            "console.log(JSON.stringify(urls.map(u=>{try{return b.assertLoopbackWebSocket(u)}catch{return false}})));"
        )
        self.assertEqual(result, ["ws://127.0.0.1:9223/devtools/page/abc", False,
                                  "wss://localhost/devtools/page/abc"])

    def test_navigation_blocks_queries_fragments_credentials_and_non_https(self):
        result = _node(
            "const h=b.parseAllowedHosts('console.cloud.google.com');"
            "const urls=['https://console.cloud.google.com/apis/credentials',"
            "'https://console.cloud.google.com/path?private=data',"
            "'https://console.cloud.google.com/path#secret',"
            "'https://user:pass@console.cloud.google.com/path',"
            "'http://console.cloud.google.com/path'];"
            "console.log(JSON.stringify(urls.map(u=>{try{return b.assertAllowedNavigation(u,h)}catch{return false}})));"
        )
        self.assertEqual(result, ["https://console.cloud.google.com/apis/credentials", False,
                                  False, False, False])

    def test_page_urls_returned_to_model_drop_query_and_fragment(self):
        result = _node(
            "console.log(JSON.stringify(b.sanitizePageUrl(" 
            "'https://mail.google.com/mail/u/0/?token=synthetic#inbox')));"
        )
        self.assertEqual(result, "https://mail.google.com/mail/u/0/")

    def test_extension_exposes_no_arbitrary_javascript_tool(self):
        text = EXTENSION.read_text(encoding="utf-8")
        self.assertIn('name: "watari_browser_tabs"', text)
        self.assertIn('name: "watari_browser_snapshot"', text)
        self.assertIn('name: "watari_browser_open"', text)
        self.assertNotIn('name: "watari_browser_evaluate"', text)
        self.assertNotIn("params.expression", text)


if __name__ == "__main__":
    unittest.main()
