# Watari legacy migration contract v1

Status: D012 structural freeze. This contract defines schemas and fail-closed
invariants only. It does not inspect a legacy root, qualify cryptography, make
owner decisions, migrate data, stop a writer, or authorize a cutover.

All digests use the D003 canonical framing. Capsule encryption and signing are
opaque interfaces until their later qualification tickets. The scope manifest
classifies every discovered item exactly once. Capsule entries retain exact
relative path bytes, object kind, mode, and raw content bytes; credentials,
runtime sessions, and caches are recorded only as exclusions. A credential-like
row found inside an included log remains lossless in the encrypted capsule but
is quarantined from canonical state.

Every migration operation treats the legacy source as read-only. An
authoritative snapshot additionally requires independently stopped legacy
writers and identical scope digests before and after its scan. Shadow capsules
are rehearsal evidence only and can never be relabelled as authoritative.

<!-- migration-contract:start -->
```json
{
  "schema": "watari.migration-contract/v1",
  "status": "structural-only-unqualified",
  "trace": ["RQ-015", "AC-015", "RQ-016", "AC-016"],
  "scope": {
    "capsule_categories": ["global-persona-rules", "watari-policy-design-schema", "knowledge", "memory-log", "derived-state", "connector-checkpoint", "writer-definition", "scheduler-definition", "legacy-comparison-evidence", "project-local-instruction"],
    "excluded_categories": ["credential-store", "runtime-session", "cache"],
    "coverage": "every-discovered-item-exactly-one-category-and-disposition",
    "unknown": "reject",
    "project_local": "capsule-not-global-profile"
  },
  "capsule": {
    "invariants": ["exact-path-kind-mode-content-bytes", "scope-equals-capsule-union-exclusions", "counts-and-set-digests-recomputed", "source-before-equals-source-after", "shadow-non-authoritative"]
  },
  "plan": {
    "mapping_fields": ["legacy_row_digest", "active_derived_contribution", "outcome", "canonical_event_id", "quarantine_reason", "visibility"],
    "outcomes": ["canonical-event", "quarantine"],
    "mapping_rule": "every-row-exactly-once-and-event-xor-quarantine",
    "credential_candidate": "quarantine",
    "canonical_exclusions": ["absolute-host-path", "raw-provider-id"],
    "default_visibility": "local-only"
  },
  "review": {
    "bindings": ["snapshot_digest", "event_set_digest", "evaluation_time", "profile_diff_digest", "visibility_decision_set_digest", "quarantine_decision_set_digest", "approver_id", "approved_at", "signature"],
    "profile": "review-only-never-auto-apply",
    "visibility_promotion": "explicit-trusted-model-only",
    "low_risk_promotion": "forbidden",
    "stale_binding": "reject"
  },
  "import": {
    "invariants": ["default-dry-run", "explicit-canonically-empty-target", "private-copy-on-write-generation", "pointer-after-verify-and-D004-complete", "idempotency-key-migration-snapshot-review", "replay-same-result-no-second-change", "unresolved-active-quarantine-blocks", "legacy-source-never-output"]
  },
  "verify": {
    "evaluation_time": "fixed-canonical-UTC-no-wall-clock",
    "parity": "same-time-semantic-and-hash-including-approved-quarantine",
    "checkpoint": "nonregressing-reviewed-proposal-no-max-merge-preserve-unbound",
    "d004_migration_binding_fields": ["binding_schema", "binding_kind", "transaction_id", "source_key", "checkpoint_before_digest", "checkpoint_after_digest", "migration_snapshot_digest", "review_artifact_digest", "imported_event_variant_set_digest", "imported_event_count", "status"],
    "checkpoint_result_equation": "old-map-overlaid-by-exact-bound-writes"
  },
  "final_delta": {
    "bindings": ["stable_capsule_digest", "delta_capsule_digest", "final_scope_digest", "writer_stop_evidence_digest"],
    "source": "before-equals-after",
    "order": "final-import-then-strict-verify-then-attest"
  },
  "stop_attestation": {
    "fields": ["attestation_schema", "approval_id", "owner_id", "final_capsule_digest", "final_source_digest", "target_state_id", "target_revision", "legacy_writer_stop_digest", "issued_at", "expires_at", "nonce", "signature"],
    "signature": "opaque-until-qualified",
    "consumption": "exactly-once-first-production-transaction",
    "reject": ["expired", "replayed", "source-mutated", "target-mutated", "capsule-mismatch", "writer-restarted"]
  },
  "source_invariant": "legacy-source-always-unchanged-by-watari-migration"
}
```
<!-- migration-contract:end -->

An active-derived row cannot be removed from parity by calling it quarantine.
Apply remains blocked until review binds an approved redacted canonical mapping
or an equivalent reviewed local-only representation. A checkpoint changes only
through the separate D004 `migration_import` binding; max-merge and unbound
writes are invalid. Before a canary, abandoning a target does not mutate the
source. After a production write, migration never rewinds the old checkpoint or
automatically restarts an old writer.
