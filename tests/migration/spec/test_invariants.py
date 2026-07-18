import copy
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[3]
MIGRATION = ROOT / "docs" / "migration.md"
ACCEPTANCE = ROOT / "docs" / "acceptance.md"
HASHES = {
    "docs/requirements.md": "86f252c92b57f738b612fe620e2f205d3961ad30446a472c0df3c0b9da0eecb0",
    "docs/data-contract.md": "613a33b886e9d01ee1f591c4a0d5e09c9968943202fbbe3f9ae27866f9d1de17",
    "docs/adr/004-transaction.md": "7c06f1b2637cd10a5184112c7e1e6c71d31af5087386451cd708a90106ec37f8",
    "docs/threat-model.md": "8a538f78b044afccb2f011954d05e05c50bbcdbb5e5bb20b2caa919afc92402a",
    "docs/adr/005-data-routes.md": "038ee36bf2e532db80b3a74605d9619529794e0743c38d114e61c3635f7dde18",
    "docs/baseline/implementation-plan.md": "3cc65da6a333271d6efed00cdf13f419249d40692126c87ae02096f6bfb6d4de",
    "docs/baseline/issue-dag.md": "b12d22906422da41a69e98b16e93f81c86fe570dc81fb5c8e17b5999920d4be4",
}
TRACE = ["RQ-015", "AC-015", "RQ-016", "AC-016"]
MIGRATION_KEYS = {
    "schema", "status", "trace", "scope", "capsule", "plan", "review",
    "import", "verify", "final_delta", "stop_attestation", "source_invariant",
}
ACCEPTANCE_KEYS = {
    "schema", "status", "trace", "feature_parity", "clean_room_restore",
    "rollback_boundary", "owner_decisions", "qualification_boundary",
}
CAPSULE_CATEGORIES = {
    "global-persona-rules", "watari-policy-design-schema", "knowledge",
    "memory-log", "derived-state", "connector-checkpoint", "writer-definition",
    "scheduler-definition", "legacy-comparison-evidence", "project-local-instruction",
}
EXCLUDED_CATEGORIES = {"credential-store", "runtime-session", "cache"}
MAPPING_FIELDS = {
    "legacy_row_digest", "active_derived_contribution", "outcome",
    "canonical_event_id", "quarantine_reason", "visibility",
}
D004_BINDING = {
    "binding_schema", "binding_kind", "transaction_id", "source_key",
    "checkpoint_before_digest", "checkpoint_after_digest",
    "migration_snapshot_digest", "review_artifact_digest",
    "imported_event_variant_set_digest", "imported_event_count", "status",
}
ATTESTATION_FIELDS = {
    "attestation_schema", "approval_id", "owner_id", "final_capsule_digest",
    "final_source_digest", "target_state_id", "target_revision",
    "legacy_writer_stop_digest", "issued_at", "expires_at", "nonce", "signature",
}
FEATURE_FIELDS = {
    "feature_id", "source_snapshot_digest", "disposition", "evidence_digest",
    "waiver_id", "waiver_owner", "waiver_signature",
}
OWNER_DECISIONS = {
    "writer_stop_time", "migration_profile_diff", "feature_parity_dispositions",
    "canary_batch", "recovery_authority_and_retention", "claude_cancellation_time",
}


def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate member: {key}")
        result[key] = value
    return result


def load_model(path, marker):
    if not path.is_file():
        raise AssertionError(f"missing contract document: {path.relative_to(ROOT)}")
    text = path.read_text(encoding="utf-8")
    start, end = f"<!-- {marker}:start -->", f"<!-- {marker}:end -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise AssertionError(f"bad marker count: {marker}")
    payload = text.split(start, 1)[1].split(end, 1)[0].strip()
    if not payload.startswith("```json\n") or not payload.endswith("\n```"):
        raise AssertionError(f"{marker} must contain one JSON fence")
    return json.loads(payload[8:-4], object_pairs_hook=reject_duplicates)


def migration():
    return load_model(MIGRATION, "migration-contract")


def acceptance():
    return load_model(ACCEPTANCE, "migration-acceptance")


def exact_root(model, keys, schema):
    return set(model) == keys and model.get("schema") == schema and model.get("status") == "structural-only-unqualified" and model.get("trace") == TRACE


def exact_unique_list(value, expected):
    return type(value) is list and len(value) == len(expected) == len(set(value)) and set(value) == set(expected)


def exact_qualification_boundary(value):
    flags = ("claims_qualification", "creates_evidence", "performs_cutover")
    return set(value) == {"authority", *flags} and type(value["authority"]) is str and value["authority"] == "none" and all(value[key] is False for key in flags)


def exact_unqualified_signature(value):
    return type(value) is str and value == "opaque-until-qualified"


class MigrationInvariantTests(unittest.TestCase):
    def assert_unique_list(self, value, expected):
        self.assertTrue(exact_unique_list(value, expected))
        self.assertFalse(exact_unique_list(value + [value[0]], expected))

    def test_t_migration_001_schema_trace_and_dependency_hashes(self):
        m, a = migration(), acceptance()
        self.assertTrue(exact_root(m, MIGRATION_KEYS, "watari.migration-contract/v1"))
        self.assertTrue(exact_root(a, ACCEPTANCE_KEYS, "watari.migration-acceptance/v1"))
        for path, digest in HASHES.items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)
        with self.assertRaises(ValueError):
            json.loads('{"a":1,"a":2}', object_pairs_hook=reject_duplicates)
        mutant = copy.deepcopy(m); mutant["unknown"] = True
        self.assertFalse(exact_root(mutant, MIGRATION_KEYS, "watari.migration-contract/v1"))
        mutant = copy.deepcopy(m); mutant["trace"].pop()
        self.assertFalse(exact_root(mutant, MIGRATION_KEYS, "watari.migration-contract/v1"))

    def test_t_migration_002_scope_capsule_lossless_and_source_immutable(self):
        m = migration(); scope, capsule = m["scope"], m["capsule"]
        self.assertEqual(set(scope), {"capsule_categories", "excluded_categories", "coverage", "unknown", "project_local"})
        self.assertEqual(set(capsule), {"invariants"})
        self.assert_unique_list(scope["capsule_categories"], CAPSULE_CATEGORIES)
        self.assert_unique_list(scope["excluded_categories"], EXCLUDED_CATEGORIES)
        self.assertTrue(CAPSULE_CATEGORIES.isdisjoint(EXCLUDED_CATEGORIES))
        self.assertEqual(scope["coverage"], "every-discovered-item-exactly-one-category-and-disposition")
        self.assertEqual(scope["unknown"], "reject")
        self.assertEqual(scope["project_local"], "capsule-not-global-profile")
        required = {"exact-path-kind-mode-content-bytes", "scope-equals-capsule-union-exclusions", "counts-and-set-digests-recomputed", "source-before-equals-source-after", "shadow-non-authoritative"}
        self.assert_unique_list(capsule["invariants"], required)
        for removed in CAPSULE_CATEGORIES:
            mutant = set(scope["capsule_categories"]); mutant.remove(removed)
            self.assertNotEqual(mutant, CAPSULE_CATEGORIES)
        self.assertEqual(m["source_invariant"], "legacy-source-always-unchanged-by-watari-migration")

    def test_t_migration_003_mapping_exclusion_and_review_defaults(self):
        m = migration(); plan, review = m["plan"], m["review"]
        self.assertEqual(set(plan), {"mapping_fields", "outcomes", "mapping_rule", "credential_candidate", "canonical_exclusions", "default_visibility"})
        self.assertEqual(set(review), {"bindings", "profile", "visibility_promotion", "low_risk_promotion", "stale_binding"})
        self.assert_unique_list(plan["mapping_fields"], MAPPING_FIELDS)
        self.assertEqual(plan["outcomes"], ["canonical-event", "quarantine"])
        self.assertEqual(plan["mapping_rule"], "every-row-exactly-once-and-event-xor-quarantine")
        self.assertEqual(plan["credential_candidate"], "quarantine")
        self.assertEqual(plan["canonical_exclusions"], ["absolute-host-path", "raw-provider-id"])
        self.assertEqual(plan["default_visibility"], "local-only")
        self.assert_unique_list(review["bindings"], {"snapshot_digest", "event_set_digest", "evaluation_time", "profile_diff_digest", "visibility_decision_set_digest", "quarantine_decision_set_digest", "approver_id", "approved_at", "signature"})
        self.assertEqual(review["profile"], "review-only-never-auto-apply")
        self.assertEqual(review["visibility_promotion"], "explicit-trusted-model-only")
        self.assertEqual(review["low_risk_promotion"], "forbidden")
        self.assertEqual(review["stale_binding"], "reject")
        for key, bad in [("mapping_rule", "last-wins"), ("credential_candidate", "canonical-event"), ("default_visibility", "trusted-model")]:
            mutant = copy.deepcopy(plan); mutant[key] = bad
            self.assertNotEqual(mutant, plan)

    def test_t_migration_004_import_parity_quarantine_and_checkpoint_binding(self):
        m = migration(); imp, verify = m["import"], m["verify"]
        self.assertEqual(set(imp), {"invariants"})
        self.assertEqual(set(verify), {"evaluation_time", "parity", "checkpoint", "d004_migration_binding_fields", "checkpoint_result_equation"})
        self.assert_unique_list(imp["invariants"], {"default-dry-run", "explicit-canonically-empty-target", "private-copy-on-write-generation", "pointer-after-verify-and-D004-complete", "idempotency-key-migration-snapshot-review", "replay-same-result-no-second-change", "unresolved-active-quarantine-blocks", "legacy-source-never-output"})
        self.assertEqual(verify["evaluation_time"], "fixed-canonical-UTC-no-wall-clock")
        self.assertEqual(verify["parity"], "same-time-semantic-and-hash-including-approved-quarantine")
        self.assertEqual(verify["checkpoint"], "nonregressing-reviewed-proposal-no-max-merge-preserve-unbound")
        self.assert_unique_list(verify["d004_migration_binding_fields"], D004_BINDING)
        self.assertEqual(verify["checkpoint_result_equation"], "old-map-overlaid-by-exact-bound-writes")
        for bad in ["in-place-generation", "nonempty-target", "wall-clock", "ignore-active-quarantine", "checkpoint-max-merge"]:
            mutant = copy.deepcopy(m); mutant["verify"]["counterexample"] = bad
            self.assertNotEqual(set(mutant["verify"]), set(verify))

    def test_t_migration_005_final_delta_and_one_shot_stop_attestation(self):
        m = migration(); final, attestation = m["final_delta"], m["stop_attestation"]
        self.assertEqual(set(final), {"bindings", "source", "order"})
        self.assertEqual(set(attestation), {"fields", "signature", "consumption", "reject"})
        self.assert_unique_list(final["bindings"], {"stable_capsule_digest", "delta_capsule_digest", "final_scope_digest", "writer_stop_evidence_digest"})
        self.assertEqual(final["source"], "before-equals-after")
        self.assertEqual(final["order"], "final-import-then-strict-verify-then-attest")
        self.assert_unique_list(attestation["fields"], ATTESTATION_FIELDS)
        self.assertTrue(exact_unqualified_signature(attestation["signature"]))
        for bad_signature in ("arbitrary", True):
            self.assertFalse(exact_unqualified_signature(bad_signature))
        self.assertEqual(attestation["consumption"], "exactly-once-first-production-transaction")
        self.assert_unique_list(attestation["reject"], {"expired", "replayed", "source-mutated", "target-mutated", "capsule-mismatch", "writer-restarted"})
        mutant = copy.deepcopy(attestation); mutant["reject"].remove("replayed")
        self.assertNotEqual(set(mutant["reject"]), set(attestation["reject"]))

    def test_t_migration_006_feature_parity_evidence_or_snapshot_waiver(self):
        feature = acceptance()["feature_parity"]
        self.assertEqual(set(feature), {"required_families", "row_fields", "coverage", "disposition", "staleness", "reject"})
        self.assert_unique_list(feature["required_families"], {"journal", "external-completion"})
        self.assert_unique_list(feature["row_fields"], FEATURE_FIELDS)
        self.assertEqual(feature["coverage"], "inventory-to-manifest-exact-bijection")
        self.assertEqual(feature["disposition"], "qualified-evidence-xor-owner-signed-snapshot-waiver")
        self.assertEqual(feature["staleness"], "feature-source-change-blocks-cutover")
        self.assert_unique_list(feature["reject"], {"unclassified", "duplicate", "missing", "stale", "both", "neither", "waiver-snapshot-mismatch"})

    def test_t_migration_007_clean_room_restore_and_rollback_boundary(self):
        a = acceptance(); clean, rollback = a["clean_room_restore"], a["rollback_boundary"]
        self.assertEqual(set(clean), {"evidence_fields", "invariants"})
        self.assertEqual(set(rollback), {"pre_canary", "after_first_target_write"})
        self.assert_unique_list(clean["evidence_fields"], {"artifact_digest", "signature_verification_digest", "provenance_digest", "clean_home_before_digest", "allowed_home_diff_digest", "disposable_state_cleanup_digest", "restored_state_revision", "profile_digest", "memory_event_set_digest", "derived_view_digest", "checkpoint_digest", "fixed_evaluation_time", "credential_scan_digest", "canonical_before_digest", "canonical_after_digest", "naked_cli_context_count", "uninstall_reinstall_digest"})
        self.assert_unique_list(clean["invariants"], {"destructive-tests-use-disposable-state", "personal-restore-read-only", "canonical-before-equals-after", "profile-memory-derived-checkpoint-match", "naked-cli-context-zero", "human-injected-credentials-not-artifacts", "uninstall-preserves-state-and-reinstall-restores"})
        self.assert_unique_list(rollback["pre_canary"], {"zero-canary-events-and-checkpoints", "attestation-unconsumed", "target-at-final-imported-revision", "legacy-at-final-source-digest", "abandon-target-generation-remote-anchor", "legacy-restart-human-decision-only"})
        self.assert_unique_list(rollback["after_first_target_write"], {"automatic-rollback-forbidden", "legacy-cursor-rewind-forbidden", "legacy-writer-restart-forbidden", "stop-all-writers-and-recover-target"})

    def test_t_migration_008_authority_owner_decisions_and_no_qualification_claim(self):
        m, a = migration(), acceptance(); decisions, boundary = a["owner_decisions"], a["qualification_boundary"]
        self.assertEqual(set(decisions), OWNER_DECISIONS)
        self.assertEqual(set(decisions.values()), {"owner-supplied-later"})
        self.assertTrue(exact_qualification_boundary(boundary))
        self.assertEqual(m["status"], "structural-only-unqualified")
        mutant = copy.deepcopy(a); mutant["owner_decisions"]["canary_batch"] = "default"
        self.assertNotEqual(set(mutant["owner_decisions"].values()), {"owner-supplied-later"})
        for key in ("claims_qualification", "creates_evidence", "performs_cutover"):
            for bad in (0, 0.0, None, True):
                mutant = copy.deepcopy(boundary); mutant[key] = bad
                self.assertFalse(exact_qualification_boundary(mutant))
        for bad in (0, 0.0, None, True, "other"):
            mutant = copy.deepcopy(boundary); mutant["authority"] = bad
            self.assertFalse(exact_qualification_boundary(mutant))


if __name__ == "__main__":
    unittest.main()
