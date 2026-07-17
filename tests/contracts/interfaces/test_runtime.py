import copy
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[3]
DOC = ROOT / "docs" / "runtime-contract.md"
ROUTES = ROOT / "docs" / "adr" / "005-data-routes.md"
CLI = ROOT / "docs" / "cli-contract.md"
OPS = [
    "detect", "qualify", "launch_interactive", "run_structured",
    "session_source", "memory_tools", "explain",
]
SCHEMAS = {
    "adapter": "watari.runtime-adapter.v1",
    "request": "watari.runtime-request.v1",
    "capability": "watari.runtime-capability.v1",
    "qualification": "watari.runtime-qualification.v1",
    "launch_receipt": "watari.runtime-launch-receipt.v1",
    "explain": "watari.runtime-explain.v1",
}
CAPABILITIES = [
    "mount", "retrieval", "shell", "file", "project", "external_write",
    "process", "network",
]
CLOSED = {
    "schemas": set(SCHEMAS),
    "route_binding": {"registry_schema", "policy_revision", "policy_digest", "identity_fields", "identity_source", "fallback"},
    "auth": {"fields", "transport", "forbidden"},
    "context": {"schema", "fields", "transports", "argv", "visibility"},
    "project_layer": {"modes", "approved_fields", "changed", "auto_discovery", "model_override", "runtime_system_digest"},
    "capabilities": {"fields", "source", "model_escalation", "sandbox_evidence"},
    "qualification": {"support_status", "supported_requires", "declaration_only"},
    "operation_semantics": {"interactive", "structured", "session_source", "memory_tools"},
    "receipt": {"required_bindings", "verification_status", "structural_tests_do_not_qualify_runtime"},
    "explain": {"fields", "forbidden", "redaction"},
}


def json_block(path):
    blocks = re.findall(r"```json\n(.*?)\n```", path.read_text(encoding="utf-8"), re.S)
    if len(blocks) != 1:
        raise AssertionError(f"expected one JSON block in {path}, got {len(blocks)}")

    def closed(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate key: {key}")
            value[key] = item
        return value

    return json.loads(blocks[0], object_pairs_hook=closed)


class RuntimeContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json_block(DOC)
        cls.matrix = json_block(ROUTES)
        cls.route = next(
            r for r in cls.matrix["routes"]
            if r["route_id"] == "route.codex.full-watari.v1"
        )

    def fake(self):
        c, r = self.contract, self.route
        fields = c["route_binding"]["identity_fields"]
        return {
            "schemas": copy.deepcopy(c["schemas"]),
            "operations": list(c["operations"]),
            "route": {key: r[key] for key in fields},
            "auth": {
                "provider_id": r["provider_id"], "reference_id": "secret-ref.synthetic",
                "scope": r["credential_scope"], "state": "available",
                "transport": "bounded-fd-or-pipe",
            },
            "context": {
                "schema": "watari.context/v1", "route_policy_digest": r["route_policy_digest"],
                "visibility": "trusted-model", "canonical_fingerprint": "watari-context-canonical-v1:" + "1" * 64,
                "effective_fingerprint": "watari-context-effective-v1:" + "2" * 64, "transport": "stdin",
            },
            "project": {
                "mode": "approved", "digest": "watari-project-v1:" + "3" * 64,
                "root_scope_digest": "watari-project-root-v1:" + "4" * 64,
                "auto_discovery": "deny", "model_override": "deny",
                "runtime_system_digest": "watari-runtime-system-v1:" + "5" * 64,
            },
            "capabilities": copy.deepcopy(r["capability_set"]),
            "semantics": copy.deepcopy(c["operation_semantics"]),
            "receipt_bindings": list(c["receipt"]["required_bindings"]),
            "receipt_status": "structural-binding-only",
            "explain_fields": list(c["explain"]["fields"]),
            "support": {"status": "unsupported", "runtime_evidence": "none", "sandbox_evidence": "none"},
        }

    def violations(self, fake):
        expected = self.fake()
        return sorted(
            {f"unknown:{key}" for key in set(fake) - set(expected)}
            | {f"missing:{key}" for key in set(expected) - set(fake)}
            | {key for key in set(fake) & set(expected) if fake[key] != expected[key]}
        )

    def reject(self, section, member, value):
        fake = self.fake()
        if member is None:
            fake[section] = value
        else:
            fake[section][member] = value
        self.assertTrue(self.violations(fake))

    def test_t_runtime_reference_fake_and_closed_schema(self):
        top = {"schema_version", "unknown_policy", "operations", "failure_codes", "open_decisions"} | set(CLOSED)
        self.assertEqual(set(self.contract), top)
        for section, fields in CLOSED.items():
            self.assertEqual(set(self.contract[section]), fields, section)
        self.assertEqual(self.contract["schema_version"], "watari.runtime-contract.v1")
        self.assertEqual(self.contract["unknown_policy"], "fail-closed")
        self.assertEqual(self.contract["schemas"], SCHEMAS)
        self.assertEqual(self.contract["operations"], OPS)
        self.assertEqual(self.violations(self.fake()), [])

    def test_t_runtime_missing_unknown_operation_or_revision_fails(self):
        self.reject("operations", None, OPS[:-1])
        self.reject("schemas", "request", "watari.runtime-request.v2")
        fake = self.fake(); fake["unexpected"] = True
        self.assertTrue(self.violations(fake))

    def test_t_runtime_route_model_endpoint_auth_binding_and_secret_boundary(self):
        rb = self.contract["route_binding"]
        self.assertEqual(rb["policy_digest"], self.matrix["route_policy_digest"])
        self.assertEqual(rb["fallback"], "disabled")
        self.assertEqual(rb["identity_fields"], ["route_id", "caller_runtime", "provider_model_class", "provider_id", "model_id", "endpoint_id", "network_endpoint_class", "credential_scope", "fallback_policy", "retention_zdr", "route_policy_digest"])
        self.assertEqual(self.contract["auth"]["fields"], ["provider_id", "reference_id", "scope", "state", "transport"])
        self.assertEqual(self.contract["auth"]["forbidden"], ["value", "argv", "environment", "global-copy", "log"])
        for key in ("provider_model_class", "model_id", "endpoint_id", "fallback_policy"):
            self.reject("route", key, "forged")
        self.reject("auth", "scope", "wrong-scope")
        self.reject("auth", "value", "synthetic-secret")

    def test_t_runtime_context_visibility_and_fingerprint_mismatch_fails(self):
        ctx = self.contract["context"]
        self.assertEqual(ctx["schema"], "watari.context/v1")
        self.assertEqual(ctx["fields"], ["route_policy_digest", "visibility", "canonical_fingerprint", "effective_fingerprint", "transport"])
        self.assertEqual(ctx["transports"], ["stdin", "owner-private-file"])
        self.assertEqual((ctx["argv"], ctx["visibility"]), ("deny", "route-bound"))
        for key, value in (("visibility", "local-only"), ("effective_fingerprint", "forged"), ("transport", "argv")):
            self.reject("context", key, value)

    def test_t_runtime_project_layer_approval_change_and_autodiscovery_fails(self):
        project = self.contract["project_layer"]
        self.assertEqual(project["modes"], ["none", "approved"])
        self.assertEqual(project["approved_fields"], ["digest", "root_scope_digest"])
        self.assertEqual((project["changed"], project["auto_discovery"], project["model_override"]),
                         ("reapproval-required", "deny", "deny"))
        self.reject("project", "mode", "changed")
        self.reject("project", "auto_discovery", "allow")

    def test_t_runtime_capability_escalation_or_unqualified_sandbox_is_unsupported(self):
        caps = self.contract["capabilities"]
        self.assertEqual(caps["fields"], CAPABILITIES)
        self.assertEqual(caps["model_escalation"], "deny")
        self.assertEqual(caps["sandbox_evidence"], "required-for-supported")
        self.assertEqual(self.contract["qualification"], {"support_status": ["unsupported", "supported"], "supported_requires": ["observed-runtime-evidence", "qualified-sandbox-evidence"], "declaration_only": "unsupported"})
        self.reject("capabilities", "mount", "allow")
        self.reject("support", "status", "supported")

    def test_t_runtime_interactive_structured_session_and_memory_tool_contract(self):
        semantics = self.contract["operation_semantics"]
        self.assertEqual(semantics["interactive"], ["pty", "cwd", "ctrl-c", "exit-code", "child-cleanup"])
        self.assertEqual(semantics["structured"], ["bounded-input", "bounded-output", "timeout", "strict-schema", "unverified-output"])
        self.assertEqual(semantics["session_source"], ["watari-owned-root", "lineage", "receipt"])
        self.assertEqual(semantics["memory_tools"], ["memory.search", "memory.get", "memory.explain", "read-only", "session-scoped", "route-bound"])
        self.reject("semantics", "memory_tools", semantics["memory_tools"] + ["memory.write"])

    def test_t_runtime_launch_explain_receipt_exit_mapping_and_open_support(self):
        self.assertTrue(self.contract["receipt"]["structural_tests_do_not_qualify_runtime"])
        self.assertEqual(self.contract["receipt"]["verification_status"], "structural-binding-only")
        self.assertEqual(self.contract["receipt"]["required_bindings"], ["runtime_id", "adapter_version", "route_id", "provider_id", "model_id", "endpoint_id", "route_policy_digest", "auth_reference_digest", "canonical_fingerprint", "effective_fingerprint", "project_digest", "runtime_system_digest", "capability_digest", "session_lineage_digest", "launch_attestation_digest"])
        self.assertEqual(self.contract["failure_codes"], {"INVALID_SCHEMA": 11, "UNSUPPORTED": 12, "AUTH": 20, "POLICY": 50})
        self.assertEqual(self.contract["open_decisions"], ["DEC-OPEN-003", "DEC-OPEN-004"])
        cli = CLI.read_text(encoding="utf-8")
        for token, code in self.contract["failure_codes"].items():
            self.assertRegex(cli, rf"(?m)^\| {code} \| {token} \|", token)
        self.assertEqual(self.contract["explain"]["fields"], ["runtime_id", "adapter_version", "redacted_argv", "environment_keys", "route_id", "canonical_fingerprint", "effective_fingerprint", "project_digest", "runtime_system_digest", "capability_status"])
        self.assertEqual(self.contract["explain"]["forbidden"], ["secret-value", "context-bytes", "absolute-host-path"])
        self.reject("receipt_bindings", None, self.fake()["receipt_bindings"][:-1])
        self.reject("explain_fields", None, self.fake()["explain_fields"] + ["secret-value"])


if __name__ == "__main__":
    unittest.main()
