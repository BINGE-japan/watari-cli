"""D010 structural crypto-qualification contract; no cryptography is executed."""

from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / "docs" / "adr" / "010-crypto-qualification.md"
MODEL_RE = re.compile(
    r"<!-- crypto-qualification-model:start -->\s*```json\s*(.*?)\s*```\s*"
    r"<!-- crypto-qualification-model:end -->",
    re.DOTALL,
)
TOP_FIELDS = {
    "schema_version", "status", "decision", "authority", "candidate_evidence",
    "remote_envelope", "revision_trust", "source_identity", "recovery_anchor",
    "device_lifecycle", "g001_handoff", "selection_gate", "safety",
}


class ContractError(AssertionError):
    pass


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def _closed(value: object, fields: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise ContractError("closed schema mismatch")
    return value


def _exact(value: object, expected: object) -> None:
    if type(value) is not type(expected):
        raise ContractError("frozen type mismatch")
    if type(expected) is dict:
        if set(value) != set(expected):
            raise ContractError("frozen member mismatch")
        for key in expected:
            _exact(value[key], expected[key])
    elif type(expected) is list:
        if len(value) != len(expected):
            raise ContractError("frozen list length mismatch")
        for observed, wanted in zip(value, expected):
            _exact(observed, wanted)
    elif value != expected:
        raise ContractError("frozen value mismatch")


def _load() -> dict[str, object]:
    match = MODEL_RE.search(ADR.read_text(encoding="utf-8"))
    if match is None:
        raise ContractError("missing unique normative model")
    if len(MODEL_RE.findall(ADR.read_text(encoding="utf-8"))) != 1:
        raise ContractError("normative model count mismatch")
    return json.loads(match.group(1), object_pairs_hook=_pairs)


class CryptoQualificationContractTests(unittest.TestCase):
    def test_t_crypto_001_external_artifacts_are_pinned_audited_and_not_custom(self) -> None:
        item = _closed(_load()["candidate_evidence"], {
            "record_schema", "record_fields", "component_fields", "component_roles",
            "implementation_class", "custom_primitive", "digest_format", "attack_result_fields",
            "required_attack_outcomes", "allowed_statuses", "synthetic_status",
        })
        _exact(item["record_schema"], "watari.crypto-candidate-evidence.v1")
        _exact(item["record_fields"], ["schema_version", "candidate_id", "status", "evidence_class", "component_artifacts", "suite_manifest_digest", "attack_result_set_digest"])
        _exact(item["component_roles"], ["aead-codec", "revision-signature", "keyed-source-identity", "recovery-record-cas-provider"])
        _exact(item["component_fields"], ["role", "upstream_name", "upstream_version", "release_artifact_sha256", "release_signature_digest", "provenance_digest", "sbom_digest", "audit_evidence_digest", "implementation_class", "custom_primitive"])
        _exact(item["implementation_class"], "external-pinned-audited")
        _exact(item["custom_primitive"], False)
        _exact(item["digest_format"], "sha256: plus 64 lowercase hex")
        _exact(item["attack_result_fields"], ["case_id", "artifact_set_digest", "evidence_digest", "environment_digest", "observed_result", "expected_result"])
        _exact(item["required_attack_outcomes"], {"aead-tamper": "AEAD_AUTH_FAILED", "aead-wrong-key": "AEAD_AUTH_FAILED", "ciphertext-swap": "OBJECT_BINDING_FAILED", "signed-old-replay": "ROLLBACK_DETECTED", "manifest-tamper": "SIGNATURE_INVALID", "unknown-signer": "SIGNER_UNAUTHORIZED", "revoked-signer": "SIGNER_UNAUTHORIZED", "candidate-policy-self-authorization": "SIGNER_UNAUTHORIZED", "source-identity-domain-mismatch": "SOURCE_IDENTITY_INVALID", "source-identity-rotation-ambiguity": "SOURCE_IDENTITY_INVALID", "recovery-below-minimum": "RECOVERY_BELOW_MINIMUM", "recovery-anchor-cas-race": "ANCHOR_STALE", "lost-device-signature-reuse": "SIGNER_UNAUTHORIZED", "lost-device-recipient-not-rotated": "ROTATION_INCOMPLETE", "new-device-incomplete-restore": "ROTATION_INCOMPLETE"})
        _exact(item["allowed_statuses"], ["unobserved", "observed-rejected", "observed-complete"])
        _exact(item["synthetic_status"], "structural-only")
        bad = copy.deepcopy(item); bad["custom_primitive"] = True
        with self.assertRaises(ContractError): _exact(bad["custom_primitive"], False)
        for forged in (0, 0.0):
            bad = copy.deepcopy(item); bad["custom_primitive"] = forged
            with self.assertRaises(ContractError): _exact(bad["custom_primitive"], False)

    def test_t_crypto_002_metadata_and_aead_attacks_fail_before_use(self) -> None:
        item = _closed(_load()["remote_envelope"], {"policy_schema", "plaintext_metadata_allowlist", "semantic_plaintext_forbidden", "aead_binding_fields", "remote_locator_modes", "unknown_metadata", "attack_outcomes"})
        _exact(item["policy_schema"], "watari.remote-envelope-policy.v1")
        _exact(item["plaintext_metadata_allowlist"], ["bootstrap.schema_version", "bootstrap.state_id", "bootstrap.crypto_suite", "bootstrap.owner_root_key_fingerprint", "bootstrap.genesis_digest", "revision_head.schema_version", "revision_head.state_id", "revision_head.monotonic_revision", "revision_head.parent_revision_digest", "revision_head.cipher_object_refs", "revision_head.signer_id", "revision_head.signature", "git.object_id", "git.parent_object_ids", "git.commit_signature"])
        _exact(item["semantic_plaintext_forbidden"], ["profile", "memory", "checkpoint", "dream", "device-content", "connector-content", "timezone", "policy", "key-reference", "logical-event-id", "payload-digest", "type-date-host-filename"])
        self.assertNotIn("bootstrap.timezone", item["plaintext_metadata_allowlist"])
        for value in ("profile", "memory", "checkpoint", "dream", "logical-event-id", "payload-digest", "type-date-host-filename"):
            self.assertIn(value, item["semantic_plaintext_forbidden"])
        _exact(item["remote_locator_modes"], ["ciphertext-sha256", "qualified-keyed-hmac"])
        _exact(item["aead_binding_fields"], ["envelope_schema", "state_id", "crypto_suite", "key_epoch", "opaque_locator", "signed_object_binding_digest"])
        _exact(item["unknown_metadata"], "reject-before-decrypt")
        outcomes = item["attack_outcomes"]
        _exact(outcomes, {"tamper": "AEAD_AUTH_FAILED;no-plaintext;no-state-mutation", "wrong-key": "AEAD_AUTH_FAILED;no-plaintext;no-state-mutation", "ciphertext-swap": "OBJECT_BINDING_FAILED;no-plaintext;no-state-mutation", "signed-old-replay": "ROLLBACK_DETECTED;no-plaintext;no-state-mutation"})
        bad = copy.deepcopy(outcomes); bad["tamper"] = "accept"
        with self.assertRaises(ContractError): _exact(bad["tamper"], "AEAD_AUTH_FAILED;no-plaintext;no-state-mutation")

    def test_t_crypto_003_signature_binds_manifest_and_expected_old_authority(self) -> None:
        item = _closed(_load()["revision_trust"], {"projection_schema", "projection_fields", "signature_input", "signature_implementation", "genesis_authority", "non_genesis_authority", "candidate_policy_authority", "secondary_parent_authority", "unknown_or_revoked_signer", "binding", "revision_chain"})
        _exact(item["projection_fields"], ["revision_schema", "state_id", "monotonic_revision", "parent_revision_digest", "commit_oid", "transaction_manifest_digest", "cipher_object_set_digest", "crypto_suite", "authorization_policy_revision", "authorization_policy_digest", "active_signer_set_digest", "active_recipient_set_digest", "signer_id"])
        _exact((item["projection_schema"], item["signature_input"], item["signature_implementation"]), ("watari.signed-revision-projection.v1", "D003-canonical-closed-projection-bytes", "candidate-pinned-external-artifact-only"))
        _exact(item["genesis_authority"], "out-of-band-owner-root-only")
        _exact(item["non_genesis_authority"], "verified-expected-old-policy-only")
        _exact((item["candidate_policy_authority"], item["secondary_parent_authority"]), ("forbidden", "forbidden"))
        _exact(item["unknown_or_revoked_signer"], "SIGNER_UNAUTHORIZED;reject-before-ref-or-state-change")
        _exact(item["binding"], "signature-plus-transaction-manifest-plus-tree-plus-cipher-object-set-must-all-match")
        _exact(item["revision_chain"], "strict-monotonic-parent-chain-and-recovery-minimum-required")
        bad = copy.deepcopy(item); bad["non_genesis_authority"] = "candidate-policy"
        with self.assertRaises(ContractError): _exact(bad["non_genesis_authority"], "verified-expected-old-policy-only")

    def test_t_crypto_004_source_identity_is_keyed_domain_separated_and_rotation_safe(self) -> None:
        item = _closed(_load()["source_identity"], {"schema", "key_purpose", "input_domain", "input_parts", "input_framing", "output", "raw_provider_id", "recipient_or_signer_rotation", "identity_key_rotation", "unknown_epoch_or_alias", "unkeyed_fallback"})
        _exact(item["input_parts"], ["state_id", "connector_instance_id", "source_lineage_digest", "provider_event_id_bytes"])
        _exact((item["schema"], item["key_purpose"], item["input_domain"]), ("watari.keyed-source-identity-policy.v1", "source-identity-key/v1;distinct-from-aead-signing-and-recovery", "stable-source-event/v1"))
        _exact(item["input_framing"], "D003-WATARI-domain-separated-length-frame-as-qualified-keyed-256-bit-input")
        _exact(item["output"], "watari-source-v1: plus 64 lowercase hex")
        _exact(item["raw_provider_id"], "transient-input-only;never-store-log-or-remote-name")
        _exact(item["recipient_or_signer_rotation"], "identity-key-and-output-unchanged")
        _exact(item["identity_key_rotation"], "owner-authorized-versioned-migration-with-encrypted-alias-evidence;preserve-existing-event-ids")
        _exact(item["unknown_epoch_or_alias"], "SOURCE_IDENTITY_INVALID;quarantine-no-recompute")
        _exact(item["unkeyed_fallback"], "forbidden")
        bad = copy.deepcopy(item); bad["identity_key_rotation"] = "silent-recompute"
        with self.assertRaises(ContractError): _exact(bad["identity_key_rotation"], "owner-authorized-versioned-migration-with-encrypted-alias-evidence;preserve-existing-event-ids")

    def test_t_crypto_005_recovery_anchor_enforces_minimum_revision_and_cas(self) -> None:
        item = _closed(_load()["recovery_anchor"], {"record_schema", "record_fields", "signature_input", "storage", "update_order", "cas_failure", "restore_order", "rollback"})
        _exact(item["record_schema"], "watari.recovery-anchor.v1")
        _exact(item["record_fields"], ["record_schema", "state_id", "crypto_suite", "owner_root_key_fingerprint", "genesis_digest", "minimum_accepted_revision", "minimum_accepted_revision_digest", "recovery_record_revision", "previous_record_digest", "active_device_policy_digest", "active_recipient_set_digest", "recovery_material_reference_digest", "owner_signature"])
        _exact(item["signature_input"], "D003-canonical-record-without-owner_signature")
        _exact(item["storage"], "out-of-band-provider;reference-bound-secret-never-product-repo")
        _exact(item["update_order"], ["conditional-push-signed-revision", "refetch-and-verify-exact-remote", "cas-out-of-band-record-with-expected-old"])
        _exact(item["cas_failure"], "ANCHOR_STALE;no-remote-rewind;stop-new-push;report-rpo")
        _exact(item["restore_order"], ["read-and-verify-out-of-band-anchor", "fetch-remote-into-temporary-root", "reject-below-minimum-or-nondescendant", "verify-signatures-and-decrypt", "strict-verify-canonical-state", "atomic-current-switch"])
        _exact(item["rollback"], "remote-below-minimum-or-not-descendant:RECOVERY_BELOW_MINIMUM")
        bad = copy.deepcopy(item); bad["record_schema"] = "watari.recovery-anchor.v2"
        with self.assertRaises(ContractError): _exact(bad["record_schema"], "watari.recovery-anchor.v1")

    def test_t_crypto_006_lost_device_revokes_rotates_and_restores_atomically(self) -> None:
        item = _closed(_load()["device_lifecycle"], {"schema", "transition_order", "signature_revocation", "recipient_rotation", "partial_transition", "past_access", "new_device_activation"})
        _exact(item["schema"], "watari.device-lifecycle-qualification.v1")
        _exact(item["transition_order"], ["verify-expected-old-owner-policy", "owner-authorized-policy-transition-revokes-signer-and-changes-recipient-key-epoch", "conditional-push-refetch-and-verify", "recovery-anchor-expected-old-cas", "new-device-temporary-restore-and-strict-verify"])
        _exact(item["signature_revocation"], "future-signatures-rejected-at-policy-transition")
        _exact(item["recipient_rotation"], "separate-mandatory-active-recipient-and-data-key-epoch-change")
        _exact(item["partial_transition"], "ROTATION_INCOMPLETE;reject-and-anchor-not-advanced")
        _exact(item["past_access"], "previously-obtained-plaintext-keys-and-ciphertext-cannot-be-retracted")
        _exact(item["new_device_activation"], "only-after-temporary-restore-and-strict-verify")
        bad = copy.deepcopy(item); bad["partial_transition"] = "accept"
        with self.assertRaises(ContractError): _exact(bad["partial_transition"], "ROTATION_INCOMPLETE;reject-and-anchor-not-advanced")

    def test_t_crypto_007_g001_handoff_binds_d011_corpus_layout_and_artifacts(self) -> None:
        item = _closed(_load()["g001_handoff"], {"schema", "record_fields", "d011_corpus_schema", "corpus_fields", "layout_ids", "event_counts", "same_input", "d011_current_harness", "d011_plan_digest", "store", "g003_repeat"})
        _exact(item["schema"], "watari.crypto-layout-handoff.v1")
        _exact(item["record_fields"], ["schema_version", "evidence_class", "candidate_record_digest", "attack_result_set_digest", "codec_artifact_digest", "corpus_input", "d011_plan_digest", "layout_result_digests", "platform_observation_digest", "cleanup_evidence_digest", "review_attestation_digest"])
        _exact(item["d011_corpus_schema"], "watari.storage-corpus-input.future.v1;reserved-not-implemented-by-d010")
        _exact(item["corpus_fields"], ["schema_version", "status", "codec_artifact_digest", "corpus_artifact_digest", "event_count", "payload_bytes", "payload_stream_sha256", "ordered_payload_lengths_sha256", "prestage_duration_ns"])
        _exact(item["layout_ids"], ["loose-encrypted-object-candidate.v1", "immutable-pack-segment-candidate.v1"])
        _exact(item["event_counts"], [10000, 100000])
        _exact(item["d011_plan_digest"], "sha256:6047c8927daf04330764b774f2c7a227bc8d3478ebf3192d62da94475b052817")
        _exact(item["d011_current_harness"], "synthetic-stand-in-only;never-qualification")
        _exact((item["same_input"], item["store"], item["g003_repeat"]), ("same-corpus-artifact-bytes-lengths-order-for-every-candidate-and-layout", "private-audit-store-only", "same-candidate-corpus-codec-and-layout-artifacts-required"))
        bad = copy.deepcopy(item); bad["event_counts"] = [10000]
        with self.assertRaises(ContractError): _exact(bad["event_counts"], [10000, 100000])
        for index in range(2):
            bad = copy.deepcopy(item); bad["event_counts"][index] = float(bad["event_counts"][index])
            with self.assertRaises(ContractError): _exact(bad["event_counts"], [10000, 100000])

    def test_t_crypto_008_incomplete_or_synthetic_evidence_cannot_select(self) -> None:
        model = _closed(_load(), TOP_FIELDS)
        _exact((model["schema_version"], model["status"], model["decision"]), ("watari.crypto-qualification-plan.v1", "frozen-procedure;non-authoritative", "DEC-OPEN-005:open"))
        _exact(model["authority"], {"d010": "procedure-only", "g001": "observed-complete-candidate-recommendation-only", "g002": "bounded-wrapper-of-recommended-external-implementation", "g003": "same-artifact-repeat-and-final-high-trust-decision"})
        gate = _closed(model["selection_gate"], {"d010_output", "synthetic_evidence", "g001_requires", "g001_result", "final_requires", "missing_or_unknown", "forbidden_d010_statuses", "decision_after_d010"})
        _exact(gate["d010_output"], "structural-only")
        _exact(gate["synthetic_evidence"], "never-qualification")
        _exact(gate["g001_requires"], ["all-component-artifacts-pinned-external-audited-and-no-custom-primitive", "all-attack-results-observed-against-exact-artifacts", "closed-g001-handoff-complete", "both-layouts-at-both-scales-with-identical-corpus-and-budgets", "platform-cleanup-and-independent-high-trust-review-complete"])
        _exact(gate["g001_result"], "candidate-recommendation-only")
        _exact(gate["final_requires"], ["g001-observed-complete-recommendation", "g002-bounded-wrapper", "g003-exact-artifact-repeat", "g003-high-trust-approval"])
        _exact(gate["missing_or_unknown"], "EVIDENCE_INCOMPLETE;reject-no-fallback")
        _exact(gate["forbidden_d010_statuses"], ["selected", "qualified", "accepted"])
        _exact(gate["decision_after_d010"], "DEC-OPEN-005:open")
        expected_safety = {"network": "none", "credentials": "none", "live_read": False, "external_write": False, "crypto_execution": False, "observed_evidence_produced": False, "persistent_artifacts": "none"}
        _exact(model["safety"], expected_safety)
        for key in ("live_read", "external_write", "crypto_execution", "observed_evidence_produced"):
            for forged in (0, 0.0):
                bad = copy.deepcopy(model["safety"]); bad[key] = forged
                with self.assertRaises(ContractError): _exact(bad, expected_safety)
        bad = copy.deepcopy(gate); bad["g001_requires"] = bad["g001_requires"][:-1]
        with self.assertRaises(ContractError): _exact(bad["g001_requires"], ["all-component-artifacts-pinned-external-audited-and-no-custom-primitive", "all-attack-results-observed-against-exact-artifacts", "closed-g001-handoff-complete", "both-layouts-at-both-scales-with-identical-corpus-and-budgets", "platform-cleanup-and-independent-high-trust-review-complete"])


if __name__ == "__main__":
    unittest.main()
