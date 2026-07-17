# ADR-010: cryptography, trust, and recovery qualification procedure

Status: frozen procedure; no implementation or candidate is qualified or selected
Issue: D010
Depends: D003, D004, D005
Decision: `DEC-OPEN-005` remains open

## Decision boundary

D010 freezes a comparison and rejection procedure. It does not name a candidate,
execute cryptography, choose a suite or layout, or create observed evidence. A
candidate must use pinned, externally maintained and independently audited
implementations. A bounded wrapper may compose qualified APIs later, but it may
not implement a cryptographic primitive.

The following JSON block is normative. Every object and record named by it is a
closed schema: unknown or missing members, unknown versions or statuses, false
platform claims, and incomplete evidence fail closed without fallback.

<!-- crypto-qualification-model:start -->
```json
{
  "schema_version": "watari.crypto-qualification-plan.v1",
  "status": "frozen-procedure;non-authoritative",
  "decision": "DEC-OPEN-005:open",
  "authority": {
    "d010": "procedure-only",
    "g001": "observed-complete-candidate-recommendation-only",
    "g002": "bounded-wrapper-of-recommended-external-implementation",
    "g003": "same-artifact-repeat-and-final-high-trust-decision"
  },
  "candidate_evidence": {
    "record_schema": "watari.crypto-candidate-evidence.v1",
    "record_fields": ["schema_version", "candidate_id", "status", "evidence_class", "component_artifacts", "suite_manifest_digest", "attack_result_set_digest"],
    "component_fields": ["role", "upstream_name", "upstream_version", "release_artifact_sha256", "release_signature_digest", "provenance_digest", "sbom_digest", "audit_evidence_digest", "implementation_class", "custom_primitive"],
    "component_roles": ["aead-codec", "revision-signature", "keyed-source-identity", "recovery-record-cas-provider"],
    "implementation_class": "external-pinned-audited",
    "custom_primitive": false,
    "digest_format": "sha256: plus 64 lowercase hex",
    "attack_result_fields": ["case_id", "artifact_set_digest", "evidence_digest", "environment_digest", "observed_result", "expected_result"],
    "required_attack_outcomes": {"aead-tamper": "AEAD_AUTH_FAILED", "aead-wrong-key": "AEAD_AUTH_FAILED", "ciphertext-swap": "OBJECT_BINDING_FAILED", "signed-old-replay": "ROLLBACK_DETECTED", "manifest-tamper": "SIGNATURE_INVALID", "unknown-signer": "SIGNER_UNAUTHORIZED", "revoked-signer": "SIGNER_UNAUTHORIZED", "candidate-policy-self-authorization": "SIGNER_UNAUTHORIZED", "source-identity-domain-mismatch": "SOURCE_IDENTITY_INVALID", "source-identity-rotation-ambiguity": "SOURCE_IDENTITY_INVALID", "recovery-below-minimum": "RECOVERY_BELOW_MINIMUM", "recovery-anchor-cas-race": "ANCHOR_STALE", "lost-device-signature-reuse": "SIGNER_UNAUTHORIZED", "lost-device-recipient-not-rotated": "ROTATION_INCOMPLETE", "new-device-incomplete-restore": "ROTATION_INCOMPLETE"},
    "allowed_statuses": ["unobserved", "observed-rejected", "observed-complete"],
    "synthetic_status": "structural-only"
  },
  "remote_envelope": {
    "policy_schema": "watari.remote-envelope-policy.v1",
    "plaintext_metadata_allowlist": ["bootstrap.schema_version", "bootstrap.state_id", "bootstrap.crypto_suite", "bootstrap.owner_root_key_fingerprint", "bootstrap.genesis_digest", "revision_head.schema_version", "revision_head.state_id", "revision_head.monotonic_revision", "revision_head.parent_revision_digest", "revision_head.cipher_object_refs", "revision_head.signer_id", "revision_head.signature", "git.object_id", "git.parent_object_ids", "git.commit_signature"],
    "semantic_plaintext_forbidden": ["profile", "memory", "checkpoint", "dream", "device-content", "connector-content", "timezone", "policy", "key-reference", "logical-event-id", "payload-digest", "type-date-host-filename"],
    "aead_binding_fields": ["envelope_schema", "state_id", "crypto_suite", "key_epoch", "opaque_locator", "signed_object_binding_digest"],
    "remote_locator_modes": ["ciphertext-sha256", "qualified-keyed-hmac"],
    "unknown_metadata": "reject-before-decrypt",
    "attack_outcomes": {
      "tamper": "AEAD_AUTH_FAILED;no-plaintext;no-state-mutation",
      "wrong-key": "AEAD_AUTH_FAILED;no-plaintext;no-state-mutation",
      "ciphertext-swap": "OBJECT_BINDING_FAILED;no-plaintext;no-state-mutation",
      "signed-old-replay": "ROLLBACK_DETECTED;no-plaintext;no-state-mutation"
    }
  },
  "revision_trust": {
    "projection_schema": "watari.signed-revision-projection.v1",
    "projection_fields": ["revision_schema", "state_id", "monotonic_revision", "parent_revision_digest", "commit_oid", "transaction_manifest_digest", "cipher_object_set_digest", "crypto_suite", "authorization_policy_revision", "authorization_policy_digest", "active_signer_set_digest", "active_recipient_set_digest", "signer_id"],
    "signature_input": "D003-canonical-closed-projection-bytes",
    "signature_implementation": "candidate-pinned-external-artifact-only",
    "genesis_authority": "out-of-band-owner-root-only",
    "non_genesis_authority": "verified-expected-old-policy-only",
    "candidate_policy_authority": "forbidden",
    "secondary_parent_authority": "forbidden",
    "unknown_or_revoked_signer": "SIGNER_UNAUTHORIZED;reject-before-ref-or-state-change",
    "binding": "signature-plus-transaction-manifest-plus-tree-plus-cipher-object-set-must-all-match",
    "revision_chain": "strict-monotonic-parent-chain-and-recovery-minimum-required"
  },
  "source_identity": {
    "schema": "watari.keyed-source-identity-policy.v1",
    "key_purpose": "source-identity-key/v1;distinct-from-aead-signing-and-recovery",
    "input_domain": "stable-source-event/v1",
    "input_parts": ["state_id", "connector_instance_id", "source_lineage_digest", "provider_event_id_bytes"],
    "input_framing": "D003-WATARI-domain-separated-length-frame-as-qualified-keyed-256-bit-input",
    "output": "watari-source-v1: plus 64 lowercase hex",
    "raw_provider_id": "transient-input-only;never-store-log-or-remote-name",
    "recipient_or_signer_rotation": "identity-key-and-output-unchanged",
    "identity_key_rotation": "owner-authorized-versioned-migration-with-encrypted-alias-evidence;preserve-existing-event-ids",
    "unknown_epoch_or_alias": "SOURCE_IDENTITY_INVALID;quarantine-no-recompute",
    "unkeyed_fallback": "forbidden"
  },
  "recovery_anchor": {
    "record_schema": "watari.recovery-anchor.v1",
    "record_fields": ["record_schema", "state_id", "crypto_suite", "owner_root_key_fingerprint", "genesis_digest", "minimum_accepted_revision", "minimum_accepted_revision_digest", "recovery_record_revision", "previous_record_digest", "active_device_policy_digest", "active_recipient_set_digest", "recovery_material_reference_digest", "owner_signature"],
    "signature_input": "D003-canonical-record-without-owner_signature",
    "storage": "out-of-band-provider;reference-bound-secret-never-product-repo",
    "update_order": ["conditional-push-signed-revision", "refetch-and-verify-exact-remote", "cas-out-of-band-record-with-expected-old"],
    "cas_failure": "ANCHOR_STALE;no-remote-rewind;stop-new-push;report-rpo",
    "restore_order": ["read-and-verify-out-of-band-anchor", "fetch-remote-into-temporary-root", "reject-below-minimum-or-nondescendant", "verify-signatures-and-decrypt", "strict-verify-canonical-state", "atomic-current-switch"],
    "rollback": "remote-below-minimum-or-not-descendant:RECOVERY_BELOW_MINIMUM"
  },
  "device_lifecycle": {
    "schema": "watari.device-lifecycle-qualification.v1",
    "transition_order": ["verify-expected-old-owner-policy", "owner-authorized-policy-transition-revokes-signer-and-changes-recipient-key-epoch", "conditional-push-refetch-and-verify", "recovery-anchor-expected-old-cas", "new-device-temporary-restore-and-strict-verify"],
    "signature_revocation": "future-signatures-rejected-at-policy-transition",
    "recipient_rotation": "separate-mandatory-active-recipient-and-data-key-epoch-change",
    "partial_transition": "ROTATION_INCOMPLETE;reject-and-anchor-not-advanced",
    "past_access": "previously-obtained-plaintext-keys-and-ciphertext-cannot-be-retracted",
    "new_device_activation": "only-after-temporary-restore-and-strict-verify"
  },
  "g001_handoff": {
    "schema": "watari.crypto-layout-handoff.v1",
    "record_fields": ["schema_version", "evidence_class", "candidate_record_digest", "attack_result_set_digest", "codec_artifact_digest", "corpus_input", "d011_plan_digest", "layout_result_digests", "platform_observation_digest", "cleanup_evidence_digest", "review_attestation_digest"],
    "d011_corpus_schema": "watari.storage-corpus-input.future.v1;reserved-not-implemented-by-d010",
    "corpus_fields": ["schema_version", "status", "codec_artifact_digest", "corpus_artifact_digest", "event_count", "payload_bytes", "payload_stream_sha256", "ordered_payload_lengths_sha256", "prestage_duration_ns"],
    "layout_ids": ["loose-encrypted-object-candidate.v1", "immutable-pack-segment-candidate.v1"],
    "event_counts": [10000, 100000],
    "same_input": "same-corpus-artifact-bytes-lengths-order-for-every-candidate-and-layout",
    "d011_current_harness": "synthetic-stand-in-only;never-qualification",
    "d011_plan_digest": "sha256:6047c8927daf04330764b774f2c7a227bc8d3478ebf3192d62da94475b052817",
    "store": "private-audit-store-only",
    "g003_repeat": "same-candidate-corpus-codec-and-layout-artifacts-required"
  },
  "selection_gate": {
    "d010_output": "structural-only",
    "synthetic_evidence": "never-qualification",
    "g001_requires": ["all-component-artifacts-pinned-external-audited-and-no-custom-primitive", "all-attack-results-observed-against-exact-artifacts", "closed-g001-handoff-complete", "both-layouts-at-both-scales-with-identical-corpus-and-budgets", "platform-cleanup-and-independent-high-trust-review-complete"],
    "g001_result": "candidate-recommendation-only",
    "final_requires": ["g001-observed-complete-recommendation", "g002-bounded-wrapper", "g003-exact-artifact-repeat", "g003-high-trust-approval"],
    "missing_or_unknown": "EVIDENCE_INCOMPLETE;reject-no-fallback",
    "forbidden_d010_statuses": ["selected", "qualified", "accepted"],
    "decision_after_d010": "DEC-OPEN-005:open"
  },
  "safety": {
    "network": "none",
    "credentials": "none",
    "live_read": false,
    "external_write": false,
    "crypto_execution": false,
    "observed_evidence_produced": false,
    "persistent_artifacts": "none"
  }
}
```
<!-- crypto-qualification-model:end -->

## Rejection and evidence semantics

AEAD authentication is necessary but not sufficient: signed revision ancestry,
the expected-old authorization policy, and the out-of-band minimum revision are
checked independently. A cryptographically valid signature from an unknown or
revoked signer is rejected. Re-signing attacker-chosen manifest, tree, object,
policy, or recipient data does not satisfy the independent bindings.

Source identity input may contain a provider identifier only transiently inside
the qualified keyed operation. Normal recipient or signer rotation cannot
change existing source digests. Identity-key replacement requires an explicit
owner-authorized migration; ambiguity is quarantined rather than recomputed.

G001 must implement and review the separately versioned corpus-input boundary
reserved by D011. D010 fixtures, D011 validation/self-test, prose, digests, and
model output are not observations. No incomplete candidate is silently replaced
by a fallback. Only G003 may close the decision after repeating the exact G001
artifacts through the G002 wrapper under independent high-trust review.
