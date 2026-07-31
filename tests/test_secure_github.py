"""GitHub repository lifecycle changes stay fixed, bounded, and approval-gated."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "src" / "watari_cli" / "pi" / "secure-github.mjs"
EXTENSION = ROOT / "src" / "watari_cli" / "pi" / "secure-github.ts"


def _node(expression: str, *args: str):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is required")
    script = f"import * as g from {json.dumps(CORE.as_uri())}; {expression}"
    result = subprocess.run(
        [node, "--input-type=module", "-e", script, *args],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class SecureGitHubPolicyTest(unittest.TestCase):
    def test_repository_names_logins_and_descriptions_are_bounded(self):
        result = _node(
            "const names=['safe-repo','owner/repo','../repo','repo.git','a'.repeat(101)];"
            "const login=['BINGE-japan','bad/name','-bad'];"
            "const check=(f,x)=>{try{return f(x)}catch{return false}};"
            "console.log(JSON.stringify({names:names.map(x=>check(g.normalizeRepoName,x)),"
            "login:login.map(x=>check(g.normalizeLogin,x)),"
            "description:check(g.normalizeDescription,'unsafe\\u001btext')}));"
        )
        self.assertEqual(result["names"], ["safe-repo", False, False, False, False])
        self.assertEqual(result["login"], ["BINGE-japan", False, False])
        self.assertFalse(result["description"])

    def test_create_and_delete_commands_have_fixed_host_and_endpoints(self):
        result = _node(
            "console.log(JSON.stringify({"
            "create:g.createRepositoryArgs('demo','public','safe'),"
            "delete:g.deleteRepositoryArgs('BINGE-japan','demo'),"
            "read:g.repositoryArgs('BINGE-japan','demo'),identity:g.identityArgs()}));"
        )
        self.assertEqual(result["identity"], ["api", "--hostname", "github.com", "user"])
        self.assertIn("user/repos", result["create"])
        self.assertIn("private=false", result["create"])
        self.assertEqual(result["delete"][-1], "repos/BINGE-japan/demo")
        self.assertEqual(result["read"][-1], "repos/BINGE-japan/demo")
        self.assertNotIn("--input", result["create"] + result["delete"])

    def test_repository_response_must_belong_to_authenticated_user(self):
        result = _node(
            "const check=x=>{try{return g.safeRepositoryResult(x,'BINGE-japan')}catch{return false}};"
            "console.log(JSON.stringify({good:check({full_name:'BINGE-japan/demo',visibility:'private',"
            "html_url:'https://github.com/BINGE-japan/demo',default_branch:'main'}),"
            "other:check({full_name:'attacker/demo',visibility:'private',"
            "html_url:'https://github.com/attacker/demo'}),"
            "spoof:check({full_name:'BINGE-japan/demo',visibility:'private',"
            "html_url:'https://attacker.invalid/BINGE-japan/demo'})}));"
        )
        self.assertEqual(result["good"]["fullName"], "BINGE-japan/demo")
        self.assertFalse(result["other"])
        self.assertFalse(result["spoof"])

    def test_executable_must_be_an_absolute_existing_binary(self):
        result = _node(
            "const values=['gh',process.execPath];"
            "console.log(JSON.stringify(values.map(x=>{try{return Boolean(g.assertGhExecutable(x))}catch{return false}})));"
        )
        self.assertEqual(result, [False, True])

    def test_extension_exposes_only_fixed_lifecycle_tools_with_ui_approval(self):
        source = EXTENSION.read_text(encoding="utf-8")
        self.assertIn('name: "watari_github_repo_create"', source)
        self.assertIn('name: "watari_github_repo_delete"', source)
        self.assertGreaterEqual(source.count("ctx.ui.confirm"), 2)
        self.assertGreaterEqual(source.count("if (!ctx.hasUI)"), 2)
        self.assertNotIn("params.endpoint", source)
        self.assertNotIn("params.owner", source)
        self.assertNotIn("params.args", source)
        self.assertNotIn("process.env.GH_TOKEN", source)
        self.assertNotIn("process.env.GITHUB_TOKEN", source)


if __name__ == "__main__":
    unittest.main()
