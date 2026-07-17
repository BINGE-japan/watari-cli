# Watari retrieval service contract v1

Status: D009 design freeze
Issue: D009
Base SHA: `8faf9c41ead0fec483fb864191ecea4715bb6a81`
Dependencies: D005 `178629bb4d1b7a1c5d7c08b280d12d62f2814118`; D006 `8faf9c41ead0fec483fb864191ecea4715bb6a81`

An explicit synthetic launch boundary registers a server-owned immutable session snapshot before
use. This closed contract rejects model-selected, unknown, or snapshot-mismatched fields.

```json
{
  "schema_version": "watari.retrieval-contract.v1",
  "unknown_policy": "fail-closed",
  "schemas": {"session": "watari.retrieval-session.v1", "request": "watari.retrieval-request.v1", "response": "watari.retrieval-response.v1", "result_ref": "watari.retrieval-result-ref.v1", "audit_receipt": "watari.retrieval-audit-receipt.v1", "candidate_proposal": "watari.memory-candidate-proposal.v1"},
  "operations": ["memory.search", "memory.get", "memory.explain"],
  "route_binding": {"registry_schema": "watari.route-matrix.v1", "runtime_contract_schema": "watari.runtime-contract.v1", "policy_revision": "D003.route-policy.v1", "policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4", "identity_fields": ["route_id", "caller_runtime", "provider_model_class", "provider_id", "model_id", "endpoint_id", "network_endpoint_class", "credential_scope", "fallback_policy", "retention_zdr", "route_policy_digest"], "identity_source": "trusted-server-registry-only", "required_capability": "allow:session-scoped-retrieval", "fallback": "disabled"},
  "session_binding": {"server_fixed_fields": ["schema_version", "session_id", "runtime_id", "adapter_version", "route_id", "caller_runtime", "provider_model_class", "provider_id", "model_id", "endpoint_id", "network_endpoint_class", "credential_scope", "fallback_policy", "retention_zdr", "route_policy_digest", "visibility", "profile_revision", "memory_revision", "canonical_fingerprint", "effective_fingerprint", "project_mode", "project_digest", "project_root_scope_digest", "capability_digest", "launch_attestation_digest", "issued_at", "expires_at", "support_status"], "field_source": "trusted-explicit-launch-registration-snapshot", "revision_semantics": "exact-session-snapshot", "client_override": "deny", "transport": "owner-only-session-scoped-local-capability", "capability_token": "ephemeral-unlogged", "expiry": "required", "replay": "deny-request-id-reuse", "global_registration": "deny", "state_key_mount": "deny", "same_uid_boundary_claim": "deny"},
  "digest_formats": {"session_id_digest": "watari.retrieval-session-id-digest.v1", "session_id_digest_origin": "server-private-domain-separated-hmac-sha256", "source_binding": "watari.memory-source-binding.v1", "proposal_digest": "watari.memory-candidate-proposal-digest.v1"},
  "request_shapes": {"memory.search": ["schema_version", "request_id", "operation", "query", "limit"], "memory.get": ["schema_version", "request_id", "operation", "result_ref"], "memory.explain": ["schema_version", "request_id", "operation", "result_ref"]},
  "response_shapes": {"common_fields": ["schema_version", "request_id", "operation", "audit_receipt_id"], "search_fields": ["results", "returned_count", "returned_bytes", "truncated"], "get_fields": ["result_ref", "projection", "returned_bytes", "truncated"], "explain_fields": ["result_ref", "route_id", "visibility", "profile_revision", "memory_revision", "project_digest", "selection_reason", "returned_bytes", "truncated"], "result_fields": ["result_ref", "projection", "returned_bytes"], "unknown_fields": "deny"},
  "reference_policy": {"kind": "opaque-session-digest-reference", "origin": "server-private-secret-nonce-digest", "scope_bindings": ["full-registered-session-snapshot", "event-identity", "server-private-nonce"], "raw_event_id_input": "deny", "raw_event_id_output": "deny", "cross_session": "deny", "expired": "deny", "enumeration": "deny", "absolute_host_path": "deny", "forbidden_search_modes": ["empty", "wildcard", "match-all", "cursor", "offset", "raw-event-id"]},
  "bounds": {"query_max_utf8_bytes": 4096, "search_max_results": 20, "search_max_response_bytes": 65536, "get_max_response_bytes": 32768, "explain_max_response_bytes": 8192, "session_max_unique_results": 100, "session_max_response_bytes": 262144, "pagination": "deny", "request_over_limit": "policy-deny-no-clamp", "result_over_limit": "explicit-truncation-with-audit"},
  "project_trust": {"modes": ["none", "approved"], "approved_required_fields": ["project_digest", "project_root_scope_digest"], "none_required_values": {"project_digest": null, "project_root_scope_digest": null}, "source": "trusted-launch-receipt-only", "changed": "reapproval-required", "auto_discovery": "deny", "authority": "deny-route-visibility-revision-change", "absolute_host_path_exposure": "deny", "record_text_path_revalidation": "fail-closed-at-load-and-before-return"},
  "audit_receipt": {"schema": "watari.retrieval-audit-receipt.v1", "fields": ["audit_receipt_id", "session_id_digest", "request_id", "operation", "route_id", "route_policy_digest", "profile_revision", "memory_revision", "project_digest", "returned_event_ids", "returned_count", "returned_bytes", "truncated", "outcome"], "event_ids": "local-audit-only", "response_exposure": "audit-receipt-id-only", "forbidden": ["query", "projection", "semantic-bytes", "result-ref", "capability-token", "credential", "absolute-host-path"]},
  "proposal_boundary": {"handoff_operation": "memory.propose", "schema": "watari.memory-candidate-proposal.v1", "required_server_bindings": ["session_id_digest", "route_id", "route_policy_digest", "profile_revision", "memory_revision", "project_digest", "source_binding", "proposal_digest"], "result": "immutable-candidate-only", "review": "required-before-canonical-event", "retrieval_service_persistence": "deny", "denied_writes": ["canonical-event", "profile", "checkpoint", "credential", "project", "connector", "external-action"]},
  "qualification": {"structural_status": "unqualified", "real_runtime_default": "unsupported", "supported_requires": ["observed-runtime-evidence", "qualified-sandbox-evidence"], "structural_tests_do_not_qualify": true},
  "failure_codes": {"INVALID_SCHEMA": 11, "UNSUPPORTED": 12, "INTEGRITY": 40, "POLICY": 50},
  "requirements_trace": ["RQ-009", "RQ-012", "RQ-013", "NM-004", "NM-005", "AC-009", "AC-012", "AC-013", "SB-003", "SB-006"],
  "open_decisions": ["DEC-OPEN-003", "DEC-OPEN-004"]
}
```

All digest formats are their named namespace plus `:` and 64 lowercase hexadecimal characters.
Only the registered full snapshot can use secret-and-nonce digest references. Raw IDs, replay,
cross-session references, and silent limit clamping are denied. Audit stores exact returned event
IDs and byte counts locally; model responses expose only the receipt ID. Retrieval cannot persist
candidate proposals or write state. OpenRouter retrieval remains denied, and synthetic conformance
does not qualify any real runtime or sandbox.
