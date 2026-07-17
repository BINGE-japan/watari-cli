# Watari migration acceptance contract v1

Status: D012 structural freeze. Every field below is an evidence requirement
for later tickets, not evidence that migration, restore, qualification, or
cutover has occurred.

Feature inventory is snapshot-bound and exhaustive. `journal` and
`external-completion` are mandatory families, while later read-only inventory
may add rows. Each row has exactly one outcome: qualified evidence, or a waiver
signed by the owner against the same source snapshot. D012 chooses neither.

<!-- migration-acceptance:start -->
```json
{
  "schema": "watari.migration-acceptance/v1",
  "status": "structural-only-unqualified",
  "trace": ["RQ-015", "AC-015", "RQ-016", "AC-016"],
  "feature_parity": {
    "required_families": ["journal", "external-completion"],
    "row_fields": ["feature_id", "source_snapshot_digest", "disposition", "evidence_digest", "waiver_id", "waiver_owner", "waiver_signature"],
    "coverage": "inventory-to-manifest-exact-bijection",
    "disposition": "qualified-evidence-xor-owner-signed-snapshot-waiver",
    "staleness": "feature-source-change-blocks-cutover",
    "reject": ["unclassified", "duplicate", "missing", "stale", "both", "neither", "waiver-snapshot-mismatch"]
  },
  "clean_room_restore": {
    "evidence_fields": ["artifact_digest", "signature_verification_digest", "provenance_digest", "clean_home_before_digest", "allowed_home_diff_digest", "disposable_state_cleanup_digest", "restored_state_revision", "profile_digest", "memory_event_set_digest", "derived_view_digest", "checkpoint_digest", "fixed_evaluation_time", "credential_scan_digest", "canonical_before_digest", "canonical_after_digest", "naked_cli_context_count", "uninstall_reinstall_digest"],
    "invariants": ["destructive-tests-use-disposable-state", "personal-restore-read-only", "canonical-before-equals-after", "profile-memory-derived-checkpoint-match", "naked-cli-context-zero", "human-injected-credentials-not-artifacts", "uninstall-preserves-state-and-reinstall-restores"]
  },
  "rollback_boundary": {
    "pre_canary": ["zero-canary-events-and-checkpoints", "attestation-unconsumed", "target-at-final-imported-revision", "legacy-at-final-source-digest", "abandon-target-generation-remote-anchor", "legacy-restart-human-decision-only"],
    "after_first_target_write": ["automatic-rollback-forbidden", "legacy-cursor-rewind-forbidden", "legacy-writer-restart-forbidden", "stop-all-writers-and-recover-target"]
  },
  "owner_decisions": {
    "writer_stop_time": "owner-supplied-later",
    "migration_profile_diff": "owner-supplied-later",
    "feature_parity_dispositions": "owner-supplied-later",
    "canary_batch": "owner-supplied-later",
    "recovery_authority_and_retention": "owner-supplied-later",
    "claude_cancellation_time": "owner-supplied-later"
  },
  "qualification_boundary": {
    "authority": "none",
    "claims_qualification": false,
    "creates_evidence": false,
    "performs_cutover": false
  }
}
```
<!-- migration-acceptance:end -->

Clean-room destructive tests use a separate disposable state. Restoring a
personal state is read-only and must leave its canonical digest unchanged.
Before a canary, target abandonment and any legacy-writer restart require the
listed zero-write conditions and a human decision. Once the canary or later
production writer adds a canonical write beyond the final imported revision,
automatic rollback, cursor rewind, and legacy-writer restart are forbidden;
recovery proceeds from verified snapshots and immutable events.
