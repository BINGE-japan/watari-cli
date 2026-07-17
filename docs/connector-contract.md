# Watari connector contract

Status: D008 design freeze
Issue: D008
Base: `178629bb4d1b7a1c5d7c08b280d12d62f2814118`
Dependencies: D002 `c0a9fc211741135ee093c19219c9a16bb426c4eb`; D005 `178629bb4d1b7a1c5d7c08b280d12d62f2814118`

This contract qualifies synthetic structure, not a real connector. Its descriptor requires
`qualification_status=synthetic-structural-conformance-only` and a `connector-synthetic-` ID;
renaming that fixture never qualifies production. Every real connector remains `unsupported`
until X001/X011/Q016. Unknown fields, versions, methods, paths,
classifications, and states fail closed. No connector output has instruction authority.

## Machine contract

```json
{
  "schema_version": "D008.connector-contract.v1",
  "unknown_policy": "fail-closed",
  "support_policy": "real-connectors-unsupported-until-X001-X011-Q016",
  "schemas": {
    "descriptor": "watari.connector-contract.v1",
    "scan_input": "watari.connector-scan-input.v1",
    "page": "watari.connector-page.v1",
    "trusted_context": "watari.connector-trusted-context.v1",
    "result": "watari.connector-scan-result.v1"
  },
  "route_binding": {
    "route_id": "route.connector.read-only.v1",
    "route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4"
  },
  "route_template_binding": {"required": true, "source_policy": "enabled-read-only", "allowed_method_paths": ["GET /approved-scope/**"], "credential_scope": "connector-instance-scoped", "source_policy_digest": "watari-source-policy-v1:9f61e2066c5e9ff08a6b958237e8627b18f4fa4e00ca14bb46bce81ce45bf8a9", "checkpoint_lineage_binding": "required-at-D008-evidence-boundary", "contract_digest": "watari-connector-v1:42d2ce3be9a548e586b0c38de0ff9293125ea1100dffbdd07260f6a3f74d592c"},
  "descriptor_fields": ["schema_version", "connector_instance_id", "qualification_status", "enabled", "ownership", "owner_device_id", "required", "source_policy", "source_policy_digest", "allowed_method_paths", "write_method_paths", "credential_reference_class", "credential_scope", "revocation_reference_class", "classification", "pagination_policy", "coordinator_policy", "retention_policy_id", "retry_policy", "checkpoint_lineage_binding", "route_template_contract_digest", "contract_digest"],
  "scan_input_fields": ["schema_version", "descriptor", "requests", "pages", "trusted_context"],
  "request_fields": ["method", "path", "cursor"],
  "transport_response_fields": ["redirect_endpoint"],
  "page_fields": ["schema_version", "device_id", "connector_instance_id", "source_policy_digest", "source_lineage_digest", "snapshot_digest", "checkpoint_before_digest", "coordinator_epoch", "request_cursor", "next_cursor", "complete", "items", "error"],
  "item_fields": ["stable_item_digest", "classification", "instruction_authority"],
  "trusted_context_fields": ["schema_version", "provenance", "device_id", "connector_instance_id", "source_policy_digest", "source_lineage_digest", "snapshot_digest", "checkpoint_before_digest", "coordinator"],
  "coordinator_fields": ["verification_status", "latest_remote_verified", "online", "owner_revision_digest", "coordinator_device_id", "coordinator_epoch"],
  "result_fields": ["schema_version", "status", "failure_token", "failure_code", "evidence_status", "accepted_item_digests", "next_cursor", "checkpoint_proposal", "canonical_write", "checkpoint_write", "external_write"],
  "checkpoint_proposal_fields": ["device_id", "connector_instance_id", "source_policy_digest", "source_lineage_digest", "snapshot_digest", "checkpoint_before_digest", "coordinator_epoch", "accepted_item_set_digest"],
  "failure_codes": {"NONE": 0, "INVALID_SCHEMA": 11, "UNSUPPORTED": 12, "AUTH": 20, "SOURCE": 21, "POLICY": 50, "PARTIAL": 60},
  "trace": ["RQ-005", "AC-005", "MX-005"]
}
```

## Read and evidence boundary

The trusted D005 matrix supplies the fixed route template and its `watari-connector-v1:42d2…592c`
digest. A separate instance descriptor binds that template digest and has its own recomputed
D003-canonical `watari-connector-v1:` digest; it must already be NFC/LF-normalized. V1 permits only
the template's `GET /approved-scope/**`. Its write-method list is empty; unknown methods, traversal, and
any transport redirect are rejected. Request, transport-response, item, and proposal shapes are
closed; their missing or extra fields fail closed. Credential values never enter the
descriptor, scan input, page, result, log, or fixture.

Code-owned validators require `device-<lowercase-safe-suffix>` and
`connector-synthetic-<lowercase-safe-suffix>`; empty, path-like, uppercase, Unicode, and non-string
IDs are invalid. Required reference/policy IDs are exact literals, while retention IDs use a closed
lowercase dot/hyphen pattern. Device-local owner IDs are valid device IDs; shared owners are null.

Raw content is `local-only`, `unverified-context;connector-evidence-only`, has
`instruction_authority=none`, and cannot egress to a model. A page item may carry only its stable
opaque digest, that classification, and no instruction authority. Connector content cannot alter
profile, policy, credentials, canonical state, a checkpoint, or an external system.

Pagination cursors are D003-framed typed digests bound to instance, source-policy, lineage,
snapshot, checkpoint-before, device, nullable coordinator epoch, and position. Current and next
cursors form one non-repeating sequence; snapshot drift, duplicate or
out-of-order identities, an invalid terminal marker, or a partial/error page cannot produce a
checkpoint proposal. Auth expiry is `AUTH`; format/source drift is `SOURCE`; rate limit, timeout,
and partial completion are `PARTIAL`. Required failures are never reported as success.

## Coordinator and checkpoint lineage

The connector observation and `watari.connector-trusted-context.v1` are separate verifier inputs.
The complete trusted context and current coordinator are validated before the first transport call.
The trusted context must have provenance `independent-trusted-state-verifier`; a connector's own
copy is not trusted. Device-local sources require the owner device and a null coordinator. Shared
sources require online, latest-remote-verified, independently verified current coordinator device
and integer epoch. Both coordinator booleans are exact `bool` true values, never numeric `1`.
There is no offline run or automatic failover.

D005's `required-at-D008-evidence-boundary` value is only a static requirement. Evidence is accepted
here only after every observed device/instance/policy/lineage/snapshot/checkpoint/epoch value equals
the independent context. Success returns a data-only checkpoint proposal bound to the exact accepted
item set. `canonical_write`, `checkpoint_write`, and `external_write` are always false; D004/S011
later verify and atomically apply any proposal.

DEC-OPEN-003/004/006 do not enable a model route or real connector. DEC-OPEN-005 remains open: this
contract consumes opaque independently verified revision evidence and chooses no crypto, signer,
trust anchor, coordinator transfer, or physical layout.
