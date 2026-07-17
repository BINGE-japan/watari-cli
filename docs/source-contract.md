# Watari source contract v1
Status: D007 design freeze
Dependencies: D002 `c0a9fc211741135ee093c19219c9a16bb426c4eb`, D005 `178629bb4d1b7a1c5d7c08b280d12d62f2814118`
Sourceはuntrusted inputでcanonical stateを更新できません。Unknown schema/version/format/status/
provenance、identity・lineage driftはfail closedです。
<!-- source-contract:start -->
```json
{
  "schema": "source-contract.v1",
  "schemas": {
    "request": {"id": "watari.source-scan-request.v1", "fields": ["schema", "adapter_id", "adapter_version", "device_id", "connector_instance_id", "expected_source_lineage_digest", "expected_coordinator_epoch", "committed_checkpoint", "bounds", "receipt_observations"]},
    "bounds": {"id": "watari.source-bounds.v1", "fields": ["schema", "max_items", "max_bytes"]},
    "receipt_observation": {"id": "watari.source-receipt-observation.v1", "fields": ["schema", "turn_id", "capture_route_id", "origin_route_id", "session_lineage", "launch_attestation", "observed_bytes", "observed_role", "observed_source"]},
    "result": {"id": "watari.source-scan-result.v1", "fields": ["schema", "status", "source_key", "format_revision", "source_snapshot_digest", "items", "checkpoint_proposal", "errors"]},
    "item": {"id": "watari.source-item.v1", "fields": ["schema", "stable_source_event_digest", "canonical_item_bytes", "content_digest", "role", "source", "session_lineage_digest", "provenance_kind", "turn_receipt"]},
    "checkpoint_proposal": {"id": "watari.source-checkpoint-proposal.v1", "fields": ["schema", "source_key", "checkpoint_before_digest", "checkpoint_after_digest", "source_snapshot_digest", "scan_manifest_digest", "opaque_position"]}
  },
  "source_key_fields": ["device_id", "connector_instance_id", "source_lineage_digest", "coordinator_epoch"],
  "role_source_pairs": [["user", "local-user-turn"], ["assistant", "local-assistant-turn"], ["assistant", "provider-output"], ["tool", "local-tool-turn"], ["system", "local-system-turn"]],
  "conformance_formats": ["watari.fake-source/v1"],
  "identity": {
    "connector_instance_id": "watari-source-instance-v1:64-lower-hex",
    "stable_source_event_digest": "watari-source-v1:64-lower-hex; keyed construction deferred to D010",
    "adapter_versions": {"adapter.synthetic": ["1"]},
    "provenance_values": ["turn-receipt-structural"],
    "coordinator_epoch": "null-or-epoch-current-<safe-nonempty-suffix>",
    "exact_replay": "deduplicate-full-bound-item",
    "same_identity_changed-content-or-provenance": "reject-identity-conflict"
  },
  "snapshot": {
    "item_binding": "D003-canonical(content,identity,role,source,lineage,provenance,full-receipt)",
    "digest": "D003-frame(source-snapshot/v1,format_revision,full-item-scan-manifest)",
    "mutation_truncation_rewrite_or_bounds_overflow": "reject"
  },
  "checkpoint": {
    "status_values": ["complete", "partial", "rejected"],
    "error_values": ["watari.source-error.invalid-schema/v1", "watari.source-error.unsupported/v1", "watari.source-error.drift/v1", "watari.source-error.identity-conflict/v1", "watari.source-error.bounds/v1", "watari.source-error.policy/v1"],
    "complete": "one-bound-proposal-required",
    "partial_or_rejected": "proposal-must-be-null",
    "after_digest": "D003-frame(source-checkpoint/v1,before,source_key,snapshot,scan,opaque_position)",
    "before_digest": "watari-checkpoint-v1:64-lower-hex; no implicit genesis",
    "authority": "proposal-only-D004-transaction-required",
    "forbidden_fields": ["transaction_id", "dream_run_id", "canonical_ref", "accepted_event_set", "model_policy_digest"]
  },
  "qualification": {
    "default_support": "unsupported",
    "structural_receipt_authenticates_source": false,
    "trusted_receipt_policy": "D005-route-matrix-and-independent-observation",
    "required_dependencies": ["D006", "D007", "Z001"],
    "provider_output": "assistant-nonprimary",
    "primary_candidate": "qualified-user-local-user-turn-only"
  },
  "open_decisions": {"DEC-OPEN-001": "out-of-scope-no-default", "DEC-OPEN-002": "out-of-scope-no-default", "DEC-OPEN-003": "OpenRouter-not-trusted-source", "DEC-OPEN-004": "public-source-set-unsupported-until-qualified", "DEC-OPEN-005": "keyed-digest-and-layout-opaque", "DEC-OPEN-006": "no-source-auto-enable"}
}
```
<!-- source-contract:end -->
Requestはtrusted lineage/closed coordinator epoch、positive bounds、stable ID別のexact bytes/role/sourceを含む独立receipt観測を
閉じたschemaで渡します。Outputの自己申告route/origin/digestを信頼せず、D005の固定route matrixから
capture/origin/provider/model/policyを解決します。構造検証成功だけではsource authenticityを称しません。
各itemのD003 canonical contentと全provenance/receiptがscan、snapshot、proposalへ結合されます。同一ID・
同一bound itemだけをdeduplicateし、contentまたはprovenance差はconflictです。Provider outputは必ず
assistant/nonprimaryです。Unknown receipt schema/route/origin/digest、raw ID、bounds超過を拒否します。
Completeはerrors空、partial/rejectedはclosed error非空かつproposal nullです。Proposalはtyped before/source
key/snapshot/scan/positionから決定論的に再計算します。Partial/rejected、
source-chosen epoch、positionだけ変えたdigestはcheckpointを進めません。D004 transactionが全candidateと
expected-old stateを再検証し同じcommitへ入れた場合だけ権威を持ちます。

Testはsynthetic memoryだけを使い、network、credential、live source、external write、永続artifactは0です。
