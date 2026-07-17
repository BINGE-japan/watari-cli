# ADR-005: data routes and threat boundaries

Status: frozen for D005
Issue: D005
Depends: D001, D003
Dependency SHAs: D001 `0d4f062ef8ecd567e977838f90c3330563c7d140`; D003 `dd753a559571f09f1c6323b1342946ff62fe842c`
Schema: `watari.route-matrix.v1`

このADRのJSON route matrixがT-ROUTE-MATRIXの唯一のallowlistです。未知のroute、provider、model、endpoint、fallback、visibility、capability、project layerは拒否し、全mutationは拒否します。OpenRouterはlow-risk utility専用で、private memory、raw connector data、credential、canonical writeを受け取りません。provider出力は未検証contextであり、local user turnだけがtrusted-dream candidateの一次根拠です。外部runtime sandboxは必須です。

## Machine-readable route matrix

```json
{
  "schema_version": "watari.route-matrix.v1",
  "visibility_values": [
    "local-only",
    "trusted-model",
    "low-risk-model"
  ],
  "unknown_policy": "fail-closed",
  "provider_output_default_trust": "unverified-context",
  "route_policy_revision": "D003.route-policy.v1",
  "route_policy_digest": "watari-route-policy-v1:e117add0f8bf0d01c45b2c0a821b843e2732ec20e89cd3c8b3fdeecf869985c4",
  "capability_values": [
    "deny",
    "allow:approved-project-read",
    "allow:session-scoped-retrieval",
    "allow:bounded-child-process",
    "allow:exact-provider-endpoint",
    "allow:receipt-root-read",
    "allow:connector-approved-root-read",
    "allow:connector-read-endpoint"
  ],
  "fallback_values": [
    "disabled"
  ],
  "retention_zdr_values": [
    "provider-contract-required",
    "local-bounded",
    "source-bounded"
  ],
  "context_selection": {
    "selection_key": "route_id",
    "multi_match": "reject",
    "implicit_default": "deny",
    "approved_project_layer": "required-digest-root-scope",
    "changed_project_layer": "reapproval-required"
  },
  "mutation_policy": {
    "canonical_write": "deny",
    "profile_write": "deny",
    "checkpoint_write": "deny",
    "connector_write": "deny",
    "external_write": "deny",
    "credential_write": "deny",
    "project_layer_write": "deny"
  },
  "projection_policy": {
    "wire_bytes": "exact-allowlisted-projection",
    "source_visibility_required": true,
    "sent_visibility_required": true,
    "declassification": "forbidden",
    "visibility_elevation": "reject",
    "policy_digest_excluded_paths": [
      "route_policy_digest",
      "routes[*].route_policy_digest",
      "test_vectors",
      "routes[*].golden_fingerprint",
      "routes[*].wire_projection.sent_bytes_digest",
      "routes[*].wire_projection.sample_bytes_digest",
      "routes[*].connector_contract.contract_digest"
    ]
  },
  "connector_instance_policy": {
    "identifier_class": "opaque-non-PII",
    "forbidden_fields": [
      "absolute_path",
      "email_or_person_name",
      "credential_or_token"
    ],
    "source_policy_digest": "required"
  },
  "routes": [
    {
      "route_id": "route.codex.full-watari.v1",
      "caller_runtime": "codex-cli",
      "provider_model_class": "trusted-model",
      "provider_id": "provider.openai.codex-cli.v1",
      "model_id": "model.codex.full-watari.v1",
      "endpoint_id": "endpoint.codex.approved.v1",
      "input_visibility": [
        "trusted-model"
      ],
      "allowed_projection": [
        "profile.explicit",
        "memory.trusted-projection",
        "user.turn",
        "source.verified-projection"
      ],
      "forbidden_data": [
        "local-only",
        "credential.value",
        "state.key",
        "raw.runtime.state",
        "unapproved.project.instructions"
      ],
      "network_endpoint_class": "codex-approved-egress",
      "credential_reference_class": "runtime-dedicated-secret-reference",
      "credential_scope": "runtime.codex-dedicated",
      "fallback_policy": "disabled",
      "retention_zdr": {
        "retention_class": "provider-contract-required",
        "zero_data_retention": "required",
        "fallback_retention": "deny"
      },
      "output_trust": "unverified-context;candidate-only",
      "canonical_write": false,
      "dream": false,
      "sandbox_class": "mandatory-external-runtime-no-state-key-mount",
      "route_policy_revision": "D003.route-policy.v1",
      "route_policy_digest": "watari-route-policy-v1:e117add0f8bf0d01c45b2c0a821b843e2732ec20e89cd3c8b3fdeecf869985c4",
      "golden_fingerprint": "watari-context-effective-v1:1f2777c4e8c74a585971811a3dab29359ba3a90347182bae7b657ea27af434e7",
      "capability_set": {
        "mount": "deny",
        "retrieval": "allow:session-scoped-retrieval",
        "shell": "deny",
        "file": "deny",
        "project": "allow:approved-project-read",
        "external_write": "deny",
        "process": "allow:bounded-child-process",
        "network": "allow:exact-provider-endpoint"
      },
      "project_layer_policy": {
        "approved_digest_required": true,
        "root_scope_required": true,
        "auto_discovery": "deny",
        "model_override": "deny"
      },
      "wire_projection": {
        "source_visibility": [
          "trusted-model"
        ],
        "sent_visibility": [
          "trusted-model"
        ],
        "allowed_projection": [
          "profile.explicit",
          "memory.trusted-projection",
          "user.turn",
          "source.verified-projection"
        ],
        "byte_selection": "exact-allowlisted-projection",
        "sent_bytes_digest": "watari-wire-bytes-v1:2d09d8d1a72e2840a0ae5acd9c957057a37783a404c631f0b8f33117d0e6b686",
        "declassification": "forbidden",
        "sample_bytes_hex": "7761746172692d776972652d73616d706c652d76313a726f7574652e636f6465782e66756c6c2d7761746172692e76310a",
        "sample_bytes_digest": "watari-wire-bytes-v1:2d09d8d1a72e2840a0ae5acd9c957057a37783a404c631f0b8f33117d0e6b686"
      },
      "direction": {
        "egress": {
          "enabled": true,
          "endpoint_id": "endpoint.codex.approved.v1",
          "allowed_visibility": [
            "trusted-model"
          ],
          "fallback_policy": "disabled",
          "capture": "required"
        },
        "ingress": {
          "enabled": true,
          "accepted_output_trust": "unverified-context;candidate-only",
          "accepted_roles": [
            "evidence"
          ],
          "provider_output_as_primary_evidence": false,
          "canonical_write": "deny"
        }
      },
      "session_receipt": {
        "required": false,
        "session_lineage": "not-applicable",
        "watari_launch_attestation": "not-applicable",
        "origin_route_model_policy": "not-applicable",
        "role_provenance": [],
        "primary_evidence_roles": [
          "user"
        ],
        "provider_output_status": "unverified-context",
        "schema_version": "watari.session-receipt.v1",
        "turn_schema": "watari.turn-receipt.v1",
        "source_binding": "required",
        "role_capture": "observed-role",
        "source_capture": "observed-source"
      },
      "connector_contract": {
        "required": false,
        "connector_instance_id_policy": "not-applicable",
        "connector_instance_id": "not-applicable",
        "source_policy": "not-applicable",
        "allowed_method_paths": [],
        "forbidden_method_paths": [],
        "credential_scope": "not-applicable",
        "contract_digest": "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1",
        "read_only": true
      },
      "origin_policy": {
        "primary_evidence_roles": [
          "evidence"
        ],
        "provider_output_primary_evidence": false,
        "source_binding": "required",
        "allowed_origin_route_ids": [],
        "provider_output_policy": "not-applicable"
      },
      "fail_closed_conditions": [
        "unknown-schema",
        "unknown-visibility",
        "unknown-route",
        "provider-mismatch",
        "fallback-not-allowlisted",
        "capability-mismatch",
        "sandbox-missing",
        "model-mismatch"
      ],
      "d001_trace": [
        "MX-001",
        "RQ-002",
        "RQ-004",
        "AC-002",
        "SB-001",
        "SB-003",
        "SB-004"
      ]
    },
    {
      "route_id": "route.pi.openai-codex.trusted-dream.v1",
      "caller_runtime": "pi",
      "provider_model_class": "trusted-model",
      "provider_id": "provider.openai.api.v1",
      "model_id": "model.openai-codex.trusted-dream.v1",
      "endpoint_id": "endpoint.openai.exact.v1",
      "input_visibility": [
        "trusted-model"
      ],
      "allowed_projection": [
        "user.turn",
        "source.verified-projection",
        "memory.dream-candidate"
      ],
      "forbidden_data": [
        "local-only",
        "credential.value",
        "raw.connector.data",
        "canonical.event",
        "state.key"
      ],
      "network_endpoint_class": "openai-approved-egress",
      "credential_reference_class": "runtime-dedicated-secret-reference",
      "credential_scope": "runtime.pi-openai-codex-dedicated",
      "fallback_policy": "disabled",
      "retention_zdr": {
        "retention_class": "provider-contract-required",
        "zero_data_retention": "required",
        "fallback_retention": "deny"
      },
      "output_trust": "unverified-context;dream-candidate-only",
      "canonical_write": false,
      "dream": true,
      "sandbox_class": "mandatory-external-runtime-no-state-key-mount",
      "route_policy_revision": "D003.route-policy.v1",
      "route_policy_digest": "watari-route-policy-v1:e117add0f8bf0d01c45b2c0a821b843e2732ec20e89cd3c8b3fdeecf869985c4",
      "golden_fingerprint": "watari-context-effective-v1:eb2b1faf5c2fbcaa1d9e1a821e988f0ce46f164c0a989da891ac851bea1fc0a0",
      "capability_set": {
        "mount": "deny",
        "retrieval": "allow:session-scoped-retrieval",
        "shell": "deny",
        "file": "deny",
        "project": "allow:approved-project-read",
        "external_write": "deny",
        "process": "allow:bounded-child-process",
        "network": "allow:exact-provider-endpoint"
      },
      "project_layer_policy": {
        "approved_digest_required": true,
        "root_scope_required": true,
        "auto_discovery": "deny",
        "model_override": "deny"
      },
      "wire_projection": {
        "source_visibility": [
          "trusted-model"
        ],
        "sent_visibility": [
          "trusted-model"
        ],
        "allowed_projection": [
          "user.turn",
          "source.verified-projection",
          "memory.dream-candidate"
        ],
        "byte_selection": "exact-allowlisted-projection",
        "sent_bytes_digest": "watari-wire-bytes-v1:fffc52d9651394ab7f2641724f0b7f7e8a8b3d2e981dcba4ae307be141a6cade",
        "declassification": "forbidden",
        "sample_bytes_hex": "7761746172692d776972652d73616d706c652d76313a726f7574652e70692e6f70656e61692d636f6465782e747275737465642d647265616d2e76310a",
        "sample_bytes_digest": "watari-wire-bytes-v1:fffc52d9651394ab7f2641724f0b7f7e8a8b3d2e981dcba4ae307be141a6cade"
      },
      "direction": {
        "egress": {
          "enabled": true,
          "endpoint_id": "endpoint.openai.exact.v1",
          "allowed_visibility": [
            "trusted-model"
          ],
          "fallback_policy": "disabled",
          "capture": "required"
        },
        "ingress": {
          "enabled": true,
          "accepted_output_trust": "unverified-context;dream-candidate-only",
          "accepted_roles": [
            "evidence"
          ],
          "provider_output_as_primary_evidence": false,
          "canonical_write": "deny"
        }
      },
      "session_receipt": {
        "required": false,
        "session_lineage": "not-applicable",
        "watari_launch_attestation": "not-applicable",
        "origin_route_model_policy": "not-applicable",
        "role_provenance": [],
        "primary_evidence_roles": [
          "user"
        ],
        "provider_output_status": "unverified-context",
        "schema_version": "watari.session-receipt.v1",
        "turn_schema": "watari.turn-receipt.v1",
        "source_binding": "required",
        "role_capture": "observed-role",
        "source_capture": "observed-source"
      },
      "connector_contract": {
        "required": false,
        "connector_instance_id_policy": "not-applicable",
        "connector_instance_id": "not-applicable",
        "source_policy": "not-applicable",
        "allowed_method_paths": [],
        "forbidden_method_paths": [],
        "credential_scope": "not-applicable",
        "contract_digest": "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1",
        "read_only": true
      },
      "origin_policy": {
        "primary_evidence_roles": [
          "user"
        ],
        "provider_output_primary_evidence": false,
        "source_binding": "required",
        "allowed_origin_route_ids": [],
        "provider_output_policy": "not-applicable"
      },
      "fail_closed_conditions": [
        "unknown-schema",
        "unknown-visibility",
        "unknown-route",
        "provider-mismatch",
        "fallback-not-allowlisted",
        "capability-mismatch",
        "sandbox-missing",
        "model-mismatch",
        "candidate-source-unbound"
      ],
      "d001_trace": [
        "MX-002",
        "RQ-004",
        "RQ-006",
        "AC-006",
        "SB-001",
        "SB-003",
        "SB-004"
      ]
    },
    {
      "route_id": "route.pi.openrouter.low-risk-utility.v1",
      "caller_runtime": "pi",
      "provider_model_class": "low-risk-model",
      "provider_id": "provider.openrouter.api.v1",
      "model_id": "model.openrouter.low-risk-utility.v1",
      "endpoint_id": "endpoint.openrouter.exact.v1",
      "input_visibility": [
        "low-risk-model"
      ],
      "allowed_projection": [
        "user.turn",
        "utility.task.minimal"
      ],
      "forbidden_data": [
        "private.memory",
        "raw.connector.data",
        "credential.value",
        "canonical.event",
        "local-only",
        "state.key"
      ],
      "network_endpoint_class": "openrouter-approved-egress",
      "credential_reference_class": "provider.openrouter-dedicated-not-model-input",
      "credential_scope": "runtime.openrouter-dedicated",
      "fallback_policy": "disabled",
      "retention_zdr": {
        "retention_class": "provider-contract-required",
        "zero_data_retention": "required",
        "fallback_retention": "deny"
      },
      "output_trust": "unverified-context;utility-output-only",
      "canonical_write": false,
      "dream": false,
      "sandbox_class": "mandatory-external-runtime-no-state-key-mount",
      "route_policy_revision": "D003.route-policy.v1",
      "route_policy_digest": "watari-route-policy-v1:e117add0f8bf0d01c45b2c0a821b843e2732ec20e89cd3c8b3fdeecf869985c4",
      "golden_fingerprint": "watari-context-effective-v1:6741236b4c3c3acc0acf22997cec99b37db1bccab0c6ebd15053f61168278a96",
      "capability_set": {
        "mount": "deny",
        "retrieval": "deny",
        "shell": "deny",
        "file": "deny",
        "project": "deny",
        "external_write": "deny",
        "process": "allow:bounded-child-process",
        "network": "allow:exact-provider-endpoint"
      },
      "project_layer_policy": {
        "approved_digest_required": true,
        "root_scope_required": true,
        "auto_discovery": "deny",
        "model_override": "deny"
      },
      "wire_projection": {
        "source_visibility": [
          "low-risk-model"
        ],
        "sent_visibility": [
          "low-risk-model"
        ],
        "allowed_projection": [
          "user.turn",
          "utility.task.minimal"
        ],
        "byte_selection": "exact-allowlisted-projection",
        "sent_bytes_digest": "watari-wire-bytes-v1:af87aa8b8146e9e54599928ed27f6e5054b698b995d62536b4b867d90c886f4e",
        "declassification": "forbidden",
        "sample_bytes_hex": "7761746172692d776972652d73616d706c652d76313a726f7574652e70692e6f70656e726f757465722e6c6f772d7269736b2d7574696c6974792e76310a",
        "sample_bytes_digest": "watari-wire-bytes-v1:af87aa8b8146e9e54599928ed27f6e5054b698b995d62536b4b867d90c886f4e"
      },
      "direction": {
        "egress": {
          "enabled": true,
          "endpoint_id": "endpoint.openrouter.exact.v1",
          "allowed_visibility": [
            "low-risk-model"
          ],
          "fallback_policy": "disabled",
          "capture": "required"
        },
        "ingress": {
          "enabled": true,
          "accepted_output_trust": "unverified-context;utility-output-only",
          "accepted_roles": [
            "evidence"
          ],
          "provider_output_as_primary_evidence": false,
          "canonical_write": "deny"
        }
      },
      "session_receipt": {
        "required": false,
        "session_lineage": "not-applicable",
        "watari_launch_attestation": "not-applicable",
        "origin_route_model_policy": "not-applicable",
        "role_provenance": [],
        "primary_evidence_roles": [
          "user"
        ],
        "provider_output_status": "unverified-context",
        "schema_version": "watari.session-receipt.v1",
        "turn_schema": "watari.turn-receipt.v1",
        "source_binding": "required",
        "role_capture": "observed-role",
        "source_capture": "observed-source"
      },
      "connector_contract": {
        "required": false,
        "connector_instance_id_policy": "not-applicable",
        "connector_instance_id": "not-applicable",
        "source_policy": "not-applicable",
        "allowed_method_paths": [],
        "forbidden_method_paths": [],
        "credential_scope": "not-applicable",
        "contract_digest": "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1",
        "read_only": true
      },
      "origin_policy": {
        "primary_evidence_roles": [
          "evidence"
        ],
        "provider_output_primary_evidence": false,
        "source_binding": "required",
        "allowed_origin_route_ids": [],
        "provider_output_policy": "not-applicable"
      },
      "fail_closed_conditions": [
        "unknown-schema",
        "unknown-visibility",
        "unknown-route",
        "provider-mismatch",
        "fallback-not-allowlisted",
        "capability-mismatch",
        "sandbox-missing",
        "model-mismatch",
        "private-data-request",
        "credential-request",
        "canonical-write-request"
      ],
      "d001_trace": [
        "MX-003",
        "RQ-004",
        "RQ-009",
        "NM-004",
        "AC-009",
        "SB-001",
        "SB-003",
        "SB-004"
      ]
    },
    {
      "route_id": "route.session-receipt.claude.v1",
      "caller_runtime": "session-receipt",
      "provider_model_class": "local-only",
      "provider_id": "provider.local-session.v1",
      "model_id": "model.none.v1",
      "endpoint_id": "endpoint.local-only.v1",
      "input_visibility": [
        "local-only"
      ],
      "allowed_projection": [
        "session.receipt"
      ],
      "forbidden_data": [
        "credential.value",
        "unapproved.project.instructions"
      ],
      "network_endpoint_class": "none",
      "credential_reference_class": "none-in-receipt",
      "credential_scope": "none",
      "fallback_policy": "disabled",
      "retention_zdr": {
        "retention_class": "local-bounded",
        "zero_data_retention": "not-applicable",
        "fallback_retention": "deny"
      },
      "output_trust": "local-receipt",
      "canonical_write": false,
      "dream": false,
      "sandbox_class": "mandatory-external-runtime-no-state-key-mount",
      "route_policy_revision": "D003.route-policy.v1",
      "route_policy_digest": "watari-route-policy-v1:e117add0f8bf0d01c45b2c0a821b843e2732ec20e89cd3c8b3fdeecf869985c4",
      "golden_fingerprint": "watari-context-effective-v1:58028445de274c11d63aedfb844670b13622867510c2005d1a17232bb6deed4f",
      "capability_set": {
        "mount": "deny",
        "retrieval": "deny",
        "shell": "deny",
        "file": "allow:receipt-root-read",
        "project": "deny",
        "external_write": "deny",
        "process": "allow:bounded-child-process",
        "network": "deny"
      },
      "project_layer_policy": {
        "approved_digest_required": true,
        "root_scope_required": true,
        "auto_discovery": "deny",
        "model_override": "deny"
      },
      "wire_projection": {
        "source_visibility": [
          "local-only"
        ],
        "sent_visibility": [
          "local-only"
        ],
        "allowed_projection": [
          "session.receipt"
        ],
        "byte_selection": "exact-allowlisted-projection",
        "sent_bytes_digest": "watari-wire-bytes-v1:966920edc9320531ad765bc8cc9715f82c2b26576a71359b56b426ae59c05fda",
        "declassification": "forbidden",
        "sample_bytes_hex": "7761746172692d776972652d73616d706c652d76313a726f7574652e73657373696f6e2d726563656970742e636c617564652e76310a",
        "sample_bytes_digest": "watari-wire-bytes-v1:966920edc9320531ad765bc8cc9715f82c2b26576a71359b56b426ae59c05fda"
      },
      "direction": {
        "egress": {
          "enabled": false,
          "endpoint_id": "endpoint.local-only.v1",
          "allowed_visibility": [
            "local-only"
          ],
          "fallback_policy": "disabled",
          "capture": "required"
        },
        "ingress": {
          "enabled": true,
          "accepted_output_trust": "local-receipt",
          "accepted_roles": [
            "user",
            "assistant",
            "tool",
            "system"
          ],
          "provider_output_as_primary_evidence": false,
          "canonical_write": "deny"
        }
      },
      "session_receipt": {
        "required": true,
        "session_lineage": "required",
        "watari_launch_attestation": "required",
        "origin_route_model_policy": "required",
        "role_provenance": [
          "user",
          "assistant",
          "tool",
          "system"
        ],
        "primary_evidence_roles": [
          "user"
        ],
        "provider_output_status": "unverified-context",
        "schema_version": "watari.session-receipt.v1",
        "turn_schema": "watari.turn-receipt.v1",
        "source_binding": "required",
        "role_capture": "observed-role",
        "source_capture": "observed-source"
      },
      "connector_contract": {
        "required": false,
        "connector_instance_id_policy": "not-applicable",
        "connector_instance_id": "not-applicable",
        "source_policy": "not-applicable",
        "allowed_method_paths": [],
        "forbidden_method_paths": [],
        "credential_scope": "not-applicable",
        "contract_digest": "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1",
        "read_only": true
      },
      "origin_policy": {
        "primary_evidence_roles": [
          "user"
        ],
        "provider_output_primary_evidence": false,
        "source_binding": "required",
        "allowed_origin_route_ids": [
          "route.session-receipt.claude.v1"
        ],
        "provider_output_policy": "deny-until-qualified-model-route"
      },
      "fail_closed_conditions": [
        "unknown-schema",
        "unknown-visibility",
        "unknown-route",
        "provider-mismatch",
        "fallback-not-allowlisted",
        "capability-mismatch",
        "sandbox-missing",
        "session-drift"
      ],
      "d001_trace": [
        "MX-004",
        "RQ-002",
        "RQ-004",
        "AC-002",
        "AC-004",
        "SB-001",
        "SB-003",
        "SB-004"
      ]
    },
    {
      "route_id": "route.session-receipt.codex.v1",
      "caller_runtime": "session-receipt",
      "provider_model_class": "local-only",
      "provider_id": "provider.local-session.v1",
      "model_id": "model.none.v1",
      "endpoint_id": "endpoint.local-only.v1",
      "input_visibility": [
        "local-only"
      ],
      "allowed_projection": [
        "session.receipt"
      ],
      "forbidden_data": [
        "credential.value",
        "unapproved.project.instructions"
      ],
      "network_endpoint_class": "none",
      "credential_reference_class": "none-in-receipt",
      "credential_scope": "none",
      "fallback_policy": "disabled",
      "retention_zdr": {
        "retention_class": "local-bounded",
        "zero_data_retention": "not-applicable",
        "fallback_retention": "deny"
      },
      "output_trust": "local-receipt",
      "canonical_write": false,
      "dream": false,
      "sandbox_class": "mandatory-external-runtime-no-state-key-mount",
      "route_policy_revision": "D003.route-policy.v1",
      "route_policy_digest": "watari-route-policy-v1:e117add0f8bf0d01c45b2c0a821b843e2732ec20e89cd3c8b3fdeecf869985c4",
      "golden_fingerprint": "watari-context-effective-v1:5c1ca43e2e210a7eb175e0f6439400aafb044f6c26eeed04380bbef472582b78",
      "capability_set": {
        "mount": "deny",
        "retrieval": "deny",
        "shell": "deny",
        "file": "allow:receipt-root-read",
        "project": "deny",
        "external_write": "deny",
        "process": "allow:bounded-child-process",
        "network": "deny"
      },
      "project_layer_policy": {
        "approved_digest_required": true,
        "root_scope_required": true,
        "auto_discovery": "deny",
        "model_override": "deny"
      },
      "wire_projection": {
        "source_visibility": [
          "local-only"
        ],
        "sent_visibility": [
          "local-only"
        ],
        "allowed_projection": [
          "session.receipt"
        ],
        "byte_selection": "exact-allowlisted-projection",
        "sent_bytes_digest": "watari-wire-bytes-v1:4978c3f6467eda12dc85685311ffd3244350d380e13993c65b932b29b3026291",
        "declassification": "forbidden",
        "sample_bytes_hex": "7761746172692d776972652d73616d706c652d76313a726f7574652e73657373696f6e2d726563656970742e636f6465782e76310a",
        "sample_bytes_digest": "watari-wire-bytes-v1:4978c3f6467eda12dc85685311ffd3244350d380e13993c65b932b29b3026291"
      },
      "direction": {
        "egress": {
          "enabled": false,
          "endpoint_id": "endpoint.local-only.v1",
          "allowed_visibility": [
            "local-only"
          ],
          "fallback_policy": "disabled",
          "capture": "required"
        },
        "ingress": {
          "enabled": true,
          "accepted_output_trust": "local-receipt",
          "accepted_roles": [
            "user",
            "assistant",
            "tool",
            "system"
          ],
          "provider_output_as_primary_evidence": false,
          "canonical_write": "deny"
        }
      },
      "session_receipt": {
        "required": true,
        "session_lineage": "required",
        "watari_launch_attestation": "required",
        "origin_route_model_policy": "required",
        "role_provenance": [
          "user",
          "assistant",
          "tool",
          "system"
        ],
        "primary_evidence_roles": [
          "user"
        ],
        "provider_output_status": "unverified-context",
        "schema_version": "watari.session-receipt.v1",
        "turn_schema": "watari.turn-receipt.v1",
        "source_binding": "required",
        "role_capture": "observed-role",
        "source_capture": "observed-source"
      },
      "connector_contract": {
        "required": false,
        "connector_instance_id_policy": "not-applicable",
        "connector_instance_id": "not-applicable",
        "source_policy": "not-applicable",
        "allowed_method_paths": [],
        "forbidden_method_paths": [],
        "credential_scope": "not-applicable",
        "contract_digest": "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1",
        "read_only": true
      },
      "origin_policy": {
        "primary_evidence_roles": [
          "user"
        ],
        "provider_output_primary_evidence": false,
        "source_binding": "required",
        "allowed_origin_route_ids": [
          "route.codex.full-watari.v1"
        ],
        "provider_output_policy": "allow-unverified-context"
      },
      "fail_closed_conditions": [
        "unknown-schema",
        "unknown-visibility",
        "unknown-route",
        "provider-mismatch",
        "fallback-not-allowlisted",
        "capability-mismatch",
        "sandbox-missing",
        "session-drift"
      ],
      "d001_trace": [
        "MX-004",
        "RQ-002",
        "RQ-004",
        "AC-002",
        "AC-004",
        "SB-001",
        "SB-003",
        "SB-004"
      ]
    },
    {
      "route_id": "route.session-receipt.pi-high-trust.v1",
      "caller_runtime": "session-receipt",
      "provider_model_class": "local-only",
      "provider_id": "provider.local-session.v1",
      "model_id": "model.none.v1",
      "endpoint_id": "endpoint.local-only.v1",
      "input_visibility": [
        "local-only"
      ],
      "allowed_projection": [
        "session.receipt"
      ],
      "forbidden_data": [
        "credential.value",
        "unapproved.project.instructions"
      ],
      "network_endpoint_class": "none",
      "credential_reference_class": "none-in-receipt",
      "credential_scope": "none",
      "fallback_policy": "disabled",
      "retention_zdr": {
        "retention_class": "local-bounded",
        "zero_data_retention": "not-applicable",
        "fallback_retention": "deny"
      },
      "output_trust": "local-receipt",
      "canonical_write": false,
      "dream": false,
      "sandbox_class": "mandatory-external-runtime-no-state-key-mount",
      "route_policy_revision": "D003.route-policy.v1",
      "route_policy_digest": "watari-route-policy-v1:e117add0f8bf0d01c45b2c0a821b843e2732ec20e89cd3c8b3fdeecf869985c4",
      "golden_fingerprint": "watari-context-effective-v1:1581ff250c39c0bfe9f94331aab3bf2d094bb003098f5751bdcfb4d3201d80f4",
      "capability_set": {
        "mount": "deny",
        "retrieval": "deny",
        "shell": "deny",
        "file": "allow:receipt-root-read",
        "project": "deny",
        "external_write": "deny",
        "process": "allow:bounded-child-process",
        "network": "deny"
      },
      "project_layer_policy": {
        "approved_digest_required": true,
        "root_scope_required": true,
        "auto_discovery": "deny",
        "model_override": "deny"
      },
      "wire_projection": {
        "source_visibility": [
          "local-only"
        ],
        "sent_visibility": [
          "local-only"
        ],
        "allowed_projection": [
          "session.receipt"
        ],
        "byte_selection": "exact-allowlisted-projection",
        "sent_bytes_digest": "watari-wire-bytes-v1:e7f3a7c55ca953ca580baba635eb99345b2a842df0a77bba69d7189befa48bc8",
        "declassification": "forbidden",
        "sample_bytes_hex": "7761746172692d776972652d73616d706c652d76313a726f7574652e73657373696f6e2d726563656970742e70692d686967682d74727573742e76310a",
        "sample_bytes_digest": "watari-wire-bytes-v1:e7f3a7c55ca953ca580baba635eb99345b2a842df0a77bba69d7189befa48bc8"
      },
      "direction": {
        "egress": {
          "enabled": false,
          "endpoint_id": "endpoint.local-only.v1",
          "allowed_visibility": [
            "local-only"
          ],
          "fallback_policy": "disabled",
          "capture": "required"
        },
        "ingress": {
          "enabled": true,
          "accepted_output_trust": "local-receipt",
          "accepted_roles": [
            "user",
            "assistant",
            "tool",
            "system"
          ],
          "provider_output_as_primary_evidence": false,
          "canonical_write": "deny"
        }
      },
      "session_receipt": {
        "required": true,
        "session_lineage": "required",
        "watari_launch_attestation": "required",
        "origin_route_model_policy": "required",
        "role_provenance": [
          "user",
          "assistant",
          "tool",
          "system"
        ],
        "primary_evidence_roles": [
          "user"
        ],
        "provider_output_status": "unverified-context",
        "schema_version": "watari.session-receipt.v1",
        "turn_schema": "watari.turn-receipt.v1",
        "source_binding": "required",
        "role_capture": "observed-role",
        "source_capture": "observed-source"
      },
      "connector_contract": {
        "required": false,
        "connector_instance_id_policy": "not-applicable",
        "connector_instance_id": "not-applicable",
        "source_policy": "not-applicable",
        "allowed_method_paths": [],
        "forbidden_method_paths": [],
        "credential_scope": "not-applicable",
        "contract_digest": "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1",
        "read_only": true
      },
      "origin_policy": {
        "primary_evidence_roles": [
          "user"
        ],
        "provider_output_primary_evidence": false,
        "source_binding": "required",
        "allowed_origin_route_ids": [
          "route.pi.openai-codex.trusted-dream.v1"
        ],
        "provider_output_policy": "allow-unverified-context"
      },
      "fail_closed_conditions": [
        "unknown-schema",
        "unknown-visibility",
        "unknown-route",
        "provider-mismatch",
        "fallback-not-allowlisted",
        "capability-mismatch",
        "sandbox-missing",
        "session-drift"
      ],
      "d001_trace": [
        "MX-004",
        "RQ-002",
        "RQ-004",
        "AC-002",
        "AC-004",
        "SB-001",
        "SB-003",
        "SB-004"
      ]
    },
    {
      "route_id": "route.connector.read-only.v1",
      "caller_runtime": "connector",
      "provider_model_class": "local-only",
      "provider_id": "provider.connector.v1",
      "model_id": "model.none.v1",
      "endpoint_id": "endpoint.connector-read-only.v1",
      "input_visibility": [
        "local-only"
      ],
      "allowed_projection": [
        "connector.approved-projection"
      ],
      "forbidden_data": [
        "credential.value",
        "raw.connector.data",
        "canonical.event"
      ],
      "network_endpoint_class": "connector-read-only-egress",
      "credential_reference_class": "connector-read-only",
      "credential_scope": "connector-instance-scoped",
      "fallback_policy": "disabled",
      "retention_zdr": {
        "retention_class": "source-bounded",
        "zero_data_retention": "not-applicable",
        "fallback_retention": "deny"
      },
      "output_trust": "unverified-context;connector-evidence-only",
      "canonical_write": false,
      "dream": false,
      "sandbox_class": "mandatory-external-runtime-no-state-key-mount",
      "route_policy_revision": "D003.route-policy.v1",
      "route_policy_digest": "watari-route-policy-v1:e117add0f8bf0d01c45b2c0a821b843e2732ec20e89cd3c8b3fdeecf869985c4",
      "golden_fingerprint": "watari-context-effective-v1:7f30cf643f6587e5cb77bec44a92e08c9154bb42773b6ba9453694291c4a316e",
      "capability_set": {
        "mount": "deny",
        "retrieval": "deny",
        "shell": "deny",
        "file": "allow:connector-approved-root-read",
        "project": "deny",
        "external_write": "deny",
        "process": "allow:bounded-child-process",
        "network": "allow:connector-read-endpoint"
      },
      "project_layer_policy": {
        "approved_digest_required": true,
        "root_scope_required": true,
        "auto_discovery": "deny",
        "model_override": "deny"
      },
      "wire_projection": {
        "source_visibility": [
          "local-only"
        ],
        "sent_visibility": [
          "local-only"
        ],
        "allowed_projection": [
          "connector.approved-projection"
        ],
        "byte_selection": "exact-allowlisted-projection",
        "sent_bytes_digest": "watari-wire-bytes-v1:9d89e1aeaa1680d4d9c2123b250890ccd6da01db6322e16cb13a4d55b6dbe745",
        "declassification": "forbidden",
        "sample_bytes_hex": "7761746172692d776972652d73616d706c652d76313a726f7574652e636f6e6e6563746f722e726561642d6f6e6c792e76310a",
        "sample_bytes_digest": "watari-wire-bytes-v1:9d89e1aeaa1680d4d9c2123b250890ccd6da01db6322e16cb13a4d55b6dbe745"
      },
      "direction": {
        "egress": {
          "enabled": true,
          "endpoint_id": "endpoint.connector-read-only.v1",
          "allowed_visibility": [
            "local-only"
          ],
          "fallback_policy": "disabled",
          "capture": "required"
        },
        "ingress": {
          "enabled": true,
          "accepted_output_trust": "unverified-context;connector-evidence-only",
          "accepted_roles": [
            "evidence"
          ],
          "provider_output_as_primary_evidence": false,
          "canonical_write": "deny"
        }
      },
      "session_receipt": {
        "required": false,
        "session_lineage": "not-applicable",
        "watari_launch_attestation": "not-applicable",
        "origin_route_model_policy": "not-applicable",
        "role_provenance": [],
        "primary_evidence_roles": [
          "user"
        ],
        "provider_output_status": "unverified-context",
        "schema_version": "watari.session-receipt.v1",
        "turn_schema": "watari.turn-receipt.v1",
        "source_binding": "required",
        "role_capture": "not-applicable",
        "source_capture": "not-applicable"
      },
      "connector_contract": {
        "required": true,
        "connector_instance_id_policy": "opaque-non-PII",
        "connector_instance_id": "connector-instance-opaque-ref",
        "source_policy": "enabled-read-only",
        "allowed_method_paths": [
          "GET /approved-scope/**"
        ],
        "forbidden_method_paths": [
          "POST /",
          "PUT /",
          "PATCH /",
          "DELETE /"
        ],
        "credential_scope": "connector-instance-scoped",
        "contract_digest": "watari-connector-v1:42d2ce3be9a548e586b0c38de0ff9293125ea1100dffbdd07260f6a3f74d592c",
        "read_only": true,
        "source_policy_digest": "watari-source-policy-v1:9f61e2066c5e9ff08a6b958237e8627b18f4fa4e00ca14bb46bce81ce45bf8a9",
        "checkpoint_lineage_binding": "required-at-D008-evidence-boundary"
      },
      "origin_policy": {
        "primary_evidence_roles": [
          "evidence"
        ],
        "provider_output_primary_evidence": false,
        "source_binding": "required",
        "allowed_origin_route_ids": [],
        "provider_output_policy": "not-applicable"
      },
      "fail_closed_conditions": [
        "unknown-schema",
        "unknown-visibility",
        "unknown-route",
        "provider-mismatch",
        "fallback-not-allowlisted",
        "capability-mismatch",
        "sandbox-missing",
        "connector-scope-drift",
        "connector-write-request",
        "source-policy-drift"
      ],
      "d001_trace": [
        "MX-005",
        "RQ-005",
        "AC-005",
        "SB-001",
        "SB-003",
        "SB-004"
      ]
    }
  ],
  "session_receipt_schema": {
    "schema_version": "watari.session-receipt.v1",
    "turn_schema": "watari.turn-receipt.v1",
    "required_fields": [
      "schema_version",
      "turn_id",
      "route_id",
      "origin_route_id",
      "bytes_digest",
      "role",
      "source",
      "session_lineage_digest",
      "watari_launch_attestation_digest",
      "origin_route_provider_model_policy_digest",
      "primary_evidence"
    ],
    "role_values": [
      "user",
      "assistant",
      "tool",
      "system"
    ],
    "source_values": [
      "local-user-turn",
      "local-assistant-turn",
      "provider-output",
      "local-tool-turn",
      "local-system-turn"
    ],
    "allowed_role_source_pairs": [
      {
        "role": "user",
        "source": "local-user-turn"
      },
      {
        "role": "assistant",
        "source": "local-assistant-turn"
      },
      {
        "role": "assistant",
        "source": "provider-output"
      },
      {
        "role": "tool",
        "source": "local-tool-turn"
      },
      {
        "role": "system",
        "source": "local-system-turn"
      }
    ],
    "primary_evidence_rule": "capture-receipt-user-local-user-turn-only",
    "provider_ingress_user": "deny"
  },
  "test_vectors": {
    "routes": {
      "route.codex.full-watari.v1": {
        "golden_fingerprint": "watari-context-effective-v1:1f2777c4e8c74a585971811a3dab29359ba3a90347182bae7b657ea27af434e7",
        "wire_bytes_digest": "watari-wire-bytes-v1:2d09d8d1a72e2840a0ae5acd9c957057a37783a404c631f0b8f33117d0e6b686",
        "connector_digest": "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1"
      },
      "route.pi.openai-codex.trusted-dream.v1": {
        "golden_fingerprint": "watari-context-effective-v1:eb2b1faf5c2fbcaa1d9e1a821e988f0ce46f164c0a989da891ac851bea1fc0a0",
        "wire_bytes_digest": "watari-wire-bytes-v1:fffc52d9651394ab7f2641724f0b7f7e8a8b3d2e981dcba4ae307be141a6cade",
        "connector_digest": "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1"
      },
      "route.pi.openrouter.low-risk-utility.v1": {
        "golden_fingerprint": "watari-context-effective-v1:6741236b4c3c3acc0acf22997cec99b37db1bccab0c6ebd15053f61168278a96",
        "wire_bytes_digest": "watari-wire-bytes-v1:af87aa8b8146e9e54599928ed27f6e5054b698b995d62536b4b867d90c886f4e",
        "connector_digest": "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1"
      },
      "route.session-receipt.claude.v1": {
        "golden_fingerprint": "watari-context-effective-v1:58028445de274c11d63aedfb844670b13622867510c2005d1a17232bb6deed4f",
        "wire_bytes_digest": "watari-wire-bytes-v1:966920edc9320531ad765bc8cc9715f82c2b26576a71359b56b426ae59c05fda",
        "connector_digest": "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1"
      },
      "route.session-receipt.codex.v1": {
        "golden_fingerprint": "watari-context-effective-v1:5c1ca43e2e210a7eb175e0f6439400aafb044f6c26eeed04380bbef472582b78",
        "wire_bytes_digest": "watari-wire-bytes-v1:4978c3f6467eda12dc85685311ffd3244350d380e13993c65b932b29b3026291",
        "connector_digest": "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1"
      },
      "route.session-receipt.pi-high-trust.v1": {
        "golden_fingerprint": "watari-context-effective-v1:1581ff250c39c0bfe9f94331aab3bf2d094bb003098f5751bdcfb4d3201d80f4",
        "wire_bytes_digest": "watari-wire-bytes-v1:e7f3a7c55ca953ca580baba635eb99345b2a842df0a77bba69d7189befa48bc8",
        "connector_digest": "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1"
      },
      "route.connector.read-only.v1": {
        "golden_fingerprint": "watari-context-effective-v1:7f30cf643f6587e5cb77bec44a92e08c9154bb42773b6ba9453694291c4a316e",
        "wire_bytes_digest": "watari-wire-bytes-v1:9d89e1aeaa1680d4d9c2123b250890ccd6da01db6322e16cb13a4d55b6dbe745",
        "connector_digest": "watari-connector-v1:42d2ce3be9a548e586b0c38de0ff9293125ea1100dffbdd07260f6a3f74d592c"
      }
    },
    "receipts": {
      "route.session-receipt.claude.v1": {
        "user": {
          "observed_turn_id": "turn:route.session-receipt.claude.v1:user",
          "observed_capture_route_id": "route.session-receipt.claude.v1",
          "observed_origin_route_id": "route.session-receipt.claude.v1",
          "observed_bytes_hex": "7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e636c617564652e76313a757365720a",
          "observed_role": "user",
          "observed_source": "local-user-turn",
          "observed_session_lineage": "lineage:route.session-receipt.claude.v1:user",
          "observed_launch_attestation": "attestation:route.session-receipt.claude.v1:route.session-receipt.claude.v1",
          "receipt": {
            "schema_version": "watari.turn-receipt.v1",
            "turn_id": "turn:route.session-receipt.claude.v1:user",
            "route_id": "route.session-receipt.claude.v1",
            "origin_route_id": "route.session-receipt.claude.v1",
            "bytes_digest": "watari-wire-bytes-v1:d4bf6c7638e77dbdace472708aa27e50cf8f08963a2b3f0323ea17c20685a899",
            "role": "user",
            "source": "local-user-turn",
            "session_lineage_digest": "watari-lineage-v1:7c55ac996cb7aa060636369576a1979c3e7c6227b8b130a426a4ce21cbeca7e7",
            "watari_launch_attestation_digest": "watari-attestation-v1:603c1fc53ac6fdf5ec2bdbf572737c656458844ae60a2165728f20de2af44a7d",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:872dbcc8047e8e6413a6c2d1adc1e573f4c4ae296101f101b223e7f95730b807",
            "primary_evidence": true
          }
        },
        "assistant": {
          "observed_turn_id": "turn:route.session-receipt.claude.v1:assistant",
          "observed_capture_route_id": "route.session-receipt.claude.v1",
          "observed_origin_route_id": "route.session-receipt.claude.v1",
          "observed_bytes_hex": "7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e636c617564652e76313a617373697374616e740a",
          "observed_role": "assistant",
          "observed_source": "local-assistant-turn",
          "observed_session_lineage": "lineage:route.session-receipt.claude.v1:assistant",
          "observed_launch_attestation": "attestation:route.session-receipt.claude.v1:route.session-receipt.claude.v1",
          "receipt": {
            "schema_version": "watari.turn-receipt.v1",
            "turn_id": "turn:route.session-receipt.claude.v1:assistant",
            "route_id": "route.session-receipt.claude.v1",
            "origin_route_id": "route.session-receipt.claude.v1",
            "bytes_digest": "watari-wire-bytes-v1:9e8b3e8cb60e54c96e0f0095a05386cff7c0ac10fe8fe9554148e561dc3ce3ef",
            "role": "assistant",
            "source": "local-assistant-turn",
            "session_lineage_digest": "watari-lineage-v1:493bb2ae88764ab4ff718fdf367e0c11d8ed82e51b62783c109edd86e3544be5",
            "watari_launch_attestation_digest": "watari-attestation-v1:603c1fc53ac6fdf5ec2bdbf572737c656458844ae60a2165728f20de2af44a7d",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:872dbcc8047e8e6413a6c2d1adc1e573f4c4ae296101f101b223e7f95730b807",
            "primary_evidence": false
          }
        },
        "tool": {
          "observed_turn_id": "turn:route.session-receipt.claude.v1:tool",
          "observed_capture_route_id": "route.session-receipt.claude.v1",
          "observed_origin_route_id": "route.session-receipt.claude.v1",
          "observed_bytes_hex": "7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e636c617564652e76313a746f6f6c0a",
          "observed_role": "tool",
          "observed_source": "local-tool-turn",
          "observed_session_lineage": "lineage:route.session-receipt.claude.v1:tool",
          "observed_launch_attestation": "attestation:route.session-receipt.claude.v1:route.session-receipt.claude.v1",
          "receipt": {
            "schema_version": "watari.turn-receipt.v1",
            "turn_id": "turn:route.session-receipt.claude.v1:tool",
            "route_id": "route.session-receipt.claude.v1",
            "origin_route_id": "route.session-receipt.claude.v1",
            "bytes_digest": "watari-wire-bytes-v1:3d12baefb745a644cc9d4272fe0f895a49e391de71d1673341d46ac10783b09c",
            "role": "tool",
            "source": "local-tool-turn",
            "session_lineage_digest": "watari-lineage-v1:5c62f54a274802cd9851f91b3c6c1784dad59b1a8ed360c1d72e377680cf5553",
            "watari_launch_attestation_digest": "watari-attestation-v1:603c1fc53ac6fdf5ec2bdbf572737c656458844ae60a2165728f20de2af44a7d",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:872dbcc8047e8e6413a6c2d1adc1e573f4c4ae296101f101b223e7f95730b807",
            "primary_evidence": false
          }
        },
        "system": {
          "observed_turn_id": "turn:route.session-receipt.claude.v1:system",
          "observed_capture_route_id": "route.session-receipt.claude.v1",
          "observed_origin_route_id": "route.session-receipt.claude.v1",
          "observed_bytes_hex": "7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e636c617564652e76313a73797374656d0a",
          "observed_role": "system",
          "observed_source": "local-system-turn",
          "observed_session_lineage": "lineage:route.session-receipt.claude.v1:system",
          "observed_launch_attestation": "attestation:route.session-receipt.claude.v1:route.session-receipt.claude.v1",
          "receipt": {
            "schema_version": "watari.turn-receipt.v1",
            "turn_id": "turn:route.session-receipt.claude.v1:system",
            "route_id": "route.session-receipt.claude.v1",
            "origin_route_id": "route.session-receipt.claude.v1",
            "bytes_digest": "watari-wire-bytes-v1:1834893827e4e923263a9312a0a877f6d88ec956153f3678d8ca7a1fb9e72eb5",
            "role": "system",
            "source": "local-system-turn",
            "session_lineage_digest": "watari-lineage-v1:2fd99c6fad90cbad54948995b663c3247b17ad8e6c1b43bd3d970a389cd80325",
            "watari_launch_attestation_digest": "watari-attestation-v1:603c1fc53ac6fdf5ec2bdbf572737c656458844ae60a2165728f20de2af44a7d",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:872dbcc8047e8e6413a6c2d1adc1e573f4c4ae296101f101b223e7f95730b807",
            "primary_evidence": false
          }
        }
      },
      "route.session-receipt.codex.v1": {
        "user": {
          "observed_turn_id": "turn:route.session-receipt.codex.v1:user",
          "observed_capture_route_id": "route.session-receipt.codex.v1",
          "observed_origin_route_id": "route.codex.full-watari.v1",
          "observed_bytes_hex": "7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e636f6465782e76313a757365720a",
          "observed_role": "user",
          "observed_source": "local-user-turn",
          "observed_session_lineage": "lineage:route.session-receipt.codex.v1:user",
          "observed_launch_attestation": "attestation:route.session-receipt.codex.v1:route.codex.full-watari.v1",
          "receipt": {
            "schema_version": "watari.turn-receipt.v1",
            "turn_id": "turn:route.session-receipt.codex.v1:user",
            "route_id": "route.session-receipt.codex.v1",
            "origin_route_id": "route.codex.full-watari.v1",
            "bytes_digest": "watari-wire-bytes-v1:edac1a991b619cd24f552be61acc5dde4c87312d6a8dcb5262df34a68c4c98ff",
            "role": "user",
            "source": "local-user-turn",
            "session_lineage_digest": "watari-lineage-v1:670ea6b2aa4d64938aee184ebd15174b6efd2715f3c345861ffd3aa047b210ba",
            "watari_launch_attestation_digest": "watari-attestation-v1:562afb898b08fbfc5f1306526db9638ce20012c8e369b98418c0d1f95673eae6",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:8d1983d10bb71dfcb4fb9f5ba5b504811cf584658e99fc9f067585ff3c75a992",
            "primary_evidence": true
          }
        },
        "assistant": {
          "observed_turn_id": "turn:route.session-receipt.codex.v1:assistant",
          "observed_capture_route_id": "route.session-receipt.codex.v1",
          "observed_origin_route_id": "route.codex.full-watari.v1",
          "observed_bytes_hex": "7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e636f6465782e76313a617373697374616e740a",
          "observed_role": "assistant",
          "observed_source": "local-assistant-turn",
          "observed_session_lineage": "lineage:route.session-receipt.codex.v1:assistant",
          "observed_launch_attestation": "attestation:route.session-receipt.codex.v1:route.codex.full-watari.v1",
          "receipt": {
            "schema_version": "watari.turn-receipt.v1",
            "turn_id": "turn:route.session-receipt.codex.v1:assistant",
            "route_id": "route.session-receipt.codex.v1",
            "origin_route_id": "route.codex.full-watari.v1",
            "bytes_digest": "watari-wire-bytes-v1:61c65ed425f3f9317c8b7015dc4be9822b27c7294e7fd5f8bbf732c7dd7e9425",
            "role": "assistant",
            "source": "local-assistant-turn",
            "session_lineage_digest": "watari-lineage-v1:75795411e048cc6dc04121ef66057a5e1aac0190467ecd3c6081b09ece8c7844",
            "watari_launch_attestation_digest": "watari-attestation-v1:562afb898b08fbfc5f1306526db9638ce20012c8e369b98418c0d1f95673eae6",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:8d1983d10bb71dfcb4fb9f5ba5b504811cf584658e99fc9f067585ff3c75a992",
            "primary_evidence": false
          }
        },
        "tool": {
          "observed_turn_id": "turn:route.session-receipt.codex.v1:tool",
          "observed_capture_route_id": "route.session-receipt.codex.v1",
          "observed_origin_route_id": "route.codex.full-watari.v1",
          "observed_bytes_hex": "7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e636f6465782e76313a746f6f6c0a",
          "observed_role": "tool",
          "observed_source": "local-tool-turn",
          "observed_session_lineage": "lineage:route.session-receipt.codex.v1:tool",
          "observed_launch_attestation": "attestation:route.session-receipt.codex.v1:route.codex.full-watari.v1",
          "receipt": {
            "schema_version": "watari.turn-receipt.v1",
            "turn_id": "turn:route.session-receipt.codex.v1:tool",
            "route_id": "route.session-receipt.codex.v1",
            "origin_route_id": "route.codex.full-watari.v1",
            "bytes_digest": "watari-wire-bytes-v1:84deea574159e6549f1b11a606a213dbdab8c44a0654ed996e3b78b52cbaf132",
            "role": "tool",
            "source": "local-tool-turn",
            "session_lineage_digest": "watari-lineage-v1:d57c1663ce27c73a8664dfc315be1e2da8cca78fcb91b33e1d8cd0ee2ef46ea4",
            "watari_launch_attestation_digest": "watari-attestation-v1:562afb898b08fbfc5f1306526db9638ce20012c8e369b98418c0d1f95673eae6",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:8d1983d10bb71dfcb4fb9f5ba5b504811cf584658e99fc9f067585ff3c75a992",
            "primary_evidence": false
          }
        },
        "system": {
          "observed_turn_id": "turn:route.session-receipt.codex.v1:system",
          "observed_capture_route_id": "route.session-receipt.codex.v1",
          "observed_origin_route_id": "route.codex.full-watari.v1",
          "observed_bytes_hex": "7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e636f6465782e76313a73797374656d0a",
          "observed_role": "system",
          "observed_source": "local-system-turn",
          "observed_session_lineage": "lineage:route.session-receipt.codex.v1:system",
          "observed_launch_attestation": "attestation:route.session-receipt.codex.v1:route.codex.full-watari.v1",
          "receipt": {
            "schema_version": "watari.turn-receipt.v1",
            "turn_id": "turn:route.session-receipt.codex.v1:system",
            "route_id": "route.session-receipt.codex.v1",
            "origin_route_id": "route.codex.full-watari.v1",
            "bytes_digest": "watari-wire-bytes-v1:66dce2c65d4360f063be9a4378dad38b2514a8d04675c09c07e514579f2acd25",
            "role": "system",
            "source": "local-system-turn",
            "session_lineage_digest": "watari-lineage-v1:2fb5c0593a6dcb3a555432345d3f303022b3b2f7592642d20b6187d9d48661ac",
            "watari_launch_attestation_digest": "watari-attestation-v1:562afb898b08fbfc5f1306526db9638ce20012c8e369b98418c0d1f95673eae6",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:8d1983d10bb71dfcb4fb9f5ba5b504811cf584658e99fc9f067585ff3c75a992",
            "primary_evidence": false
          }
        }
      },
      "route.session-receipt.pi-high-trust.v1": {
        "user": {
          "observed_turn_id": "turn:route.session-receipt.pi-high-trust.v1:user",
          "observed_capture_route_id": "route.session-receipt.pi-high-trust.v1",
          "observed_origin_route_id": "route.pi.openai-codex.trusted-dream.v1",
          "observed_bytes_hex": "7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e70692d686967682d74727573742e76313a757365720a",
          "observed_role": "user",
          "observed_source": "local-user-turn",
          "observed_session_lineage": "lineage:route.session-receipt.pi-high-trust.v1:user",
          "observed_launch_attestation": "attestation:route.session-receipt.pi-high-trust.v1:route.pi.openai-codex.trusted-dream.v1",
          "receipt": {
            "schema_version": "watari.turn-receipt.v1",
            "turn_id": "turn:route.session-receipt.pi-high-trust.v1:user",
            "route_id": "route.session-receipt.pi-high-trust.v1",
            "origin_route_id": "route.pi.openai-codex.trusted-dream.v1",
            "bytes_digest": "watari-wire-bytes-v1:d80ce5ddbc40686e931329bf8852dd1d16749f9139ff52ece82e735c52f402e8",
            "role": "user",
            "source": "local-user-turn",
            "session_lineage_digest": "watari-lineage-v1:4d50e12cdbcc647cb3feba06916a5fcb5e741d08827724860f2f9b6e549278c2",
            "watari_launch_attestation_digest": "watari-attestation-v1:5c13615984732ad0953e1f9ec9275f38201e76f1e9d7c8e756553b0511727b70",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:a7016357e8f8c3dd26c48e8f61d6d2ec8709088ae27d21b0a49584f00c97ae5f",
            "primary_evidence": true
          }
        },
        "assistant": {
          "observed_turn_id": "turn:route.session-receipt.pi-high-trust.v1:assistant",
          "observed_capture_route_id": "route.session-receipt.pi-high-trust.v1",
          "observed_origin_route_id": "route.pi.openai-codex.trusted-dream.v1",
          "observed_bytes_hex": "7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e70692d686967682d74727573742e76313a617373697374616e740a",
          "observed_role": "assistant",
          "observed_source": "local-assistant-turn",
          "observed_session_lineage": "lineage:route.session-receipt.pi-high-trust.v1:assistant",
          "observed_launch_attestation": "attestation:route.session-receipt.pi-high-trust.v1:route.pi.openai-codex.trusted-dream.v1",
          "receipt": {
            "schema_version": "watari.turn-receipt.v1",
            "turn_id": "turn:route.session-receipt.pi-high-trust.v1:assistant",
            "route_id": "route.session-receipt.pi-high-trust.v1",
            "origin_route_id": "route.pi.openai-codex.trusted-dream.v1",
            "bytes_digest": "watari-wire-bytes-v1:8544f4774a68885d77d65aa46c893c0a802c3aa183b171140fd28ecee0cf1578",
            "role": "assistant",
            "source": "local-assistant-turn",
            "session_lineage_digest": "watari-lineage-v1:75133fcddf1b6bcb6ebb342f0a8ada3495c999b9bad36d7f8d946087f23f211c",
            "watari_launch_attestation_digest": "watari-attestation-v1:5c13615984732ad0953e1f9ec9275f38201e76f1e9d7c8e756553b0511727b70",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:a7016357e8f8c3dd26c48e8f61d6d2ec8709088ae27d21b0a49584f00c97ae5f",
            "primary_evidence": false
          }
        },
        "tool": {
          "observed_turn_id": "turn:route.session-receipt.pi-high-trust.v1:tool",
          "observed_capture_route_id": "route.session-receipt.pi-high-trust.v1",
          "observed_origin_route_id": "route.pi.openai-codex.trusted-dream.v1",
          "observed_bytes_hex": "7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e70692d686967682d74727573742e76313a746f6f6c0a",
          "observed_role": "tool",
          "observed_source": "local-tool-turn",
          "observed_session_lineage": "lineage:route.session-receipt.pi-high-trust.v1:tool",
          "observed_launch_attestation": "attestation:route.session-receipt.pi-high-trust.v1:route.pi.openai-codex.trusted-dream.v1",
          "receipt": {
            "schema_version": "watari.turn-receipt.v1",
            "turn_id": "turn:route.session-receipt.pi-high-trust.v1:tool",
            "route_id": "route.session-receipt.pi-high-trust.v1",
            "origin_route_id": "route.pi.openai-codex.trusted-dream.v1",
            "bytes_digest": "watari-wire-bytes-v1:bc27c51dcf6c78490572ba3d606c8ef1901e7799763657314b1060ed9a884a2d",
            "role": "tool",
            "source": "local-tool-turn",
            "session_lineage_digest": "watari-lineage-v1:539eb1e577f24e5a997fecbd5f961168b19226bac9b3c78904b0ea393a617c05",
            "watari_launch_attestation_digest": "watari-attestation-v1:5c13615984732ad0953e1f9ec9275f38201e76f1e9d7c8e756553b0511727b70",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:a7016357e8f8c3dd26c48e8f61d6d2ec8709088ae27d21b0a49584f00c97ae5f",
            "primary_evidence": false
          }
        },
        "system": {
          "observed_turn_id": "turn:route.session-receipt.pi-high-trust.v1:system",
          "observed_capture_route_id": "route.session-receipt.pi-high-trust.v1",
          "observed_origin_route_id": "route.pi.openai-codex.trusted-dream.v1",
          "observed_bytes_hex": "7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e70692d686967682d74727573742e76313a73797374656d0a",
          "observed_role": "system",
          "observed_source": "local-system-turn",
          "observed_session_lineage": "lineage:route.session-receipt.pi-high-trust.v1:system",
          "observed_launch_attestation": "attestation:route.session-receipt.pi-high-trust.v1:route.pi.openai-codex.trusted-dream.v1",
          "receipt": {
            "schema_version": "watari.turn-receipt.v1",
            "turn_id": "turn:route.session-receipt.pi-high-trust.v1:system",
            "route_id": "route.session-receipt.pi-high-trust.v1",
            "origin_route_id": "route.pi.openai-codex.trusted-dream.v1",
            "bytes_digest": "watari-wire-bytes-v1:1356f2543ff7c9643ef626cc62439ebe9d1dcedeb1e0d0cbc156342259b37361",
            "role": "system",
            "source": "local-system-turn",
            "session_lineage_digest": "watari-lineage-v1:f50885eb7bc77b40b9e6fe582016a5db5a556b4d427f7c4b7a933ab2219120fe",
            "watari_launch_attestation_digest": "watari-attestation-v1:5c13615984732ad0953e1f9ec9275f38201e76f1e9d7c8e756553b0511727b70",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:a7016357e8f8c3dd26c48e8f61d6d2ec8709088ae27d21b0a49584f00c97ae5f",
            "primary_evidence": false
          }
        }
      }
    }
  }
}
```

## Route policy versus actual turn receipt

The route policy is a static closed allowlist. Its D003 typed-frame digest covers every documented
top-level, route, and nested policy leaf except the exact code-owned derived paths declared in
`projection_policy.policy_digest_excluded_paths`. The verifier never reads exclusions from the
matrix; its frozen `POLICY_EXCLUDED_PATHS` is the authority. Exclusions are limited to the policy
self-digests, the complete `test_vectors` subtree, context goldens, wire digests, and connector
contract digests.

A turn receipt is separate evidence. The verifier receives independently observed turn ID, capture
route ID, origin launch route ID, bytes, semantic role, source, session lineage, and launch
attestation. It resolves both route IDs from the trusted matrix and derives runtime,
provider/model, and policy identities from those records. Caller-supplied provider, model, runtime,
or policy strings are not accepted.

The capture route must require session receipts, the semantic role must be one of
`user`, `assistant`, `tool`, or `system`, the role/source pair must be allowlisted, and the
origin launch route must be in that capture route's explicit origin allowlist. Provider is a
source (`provider-output`), not a role. Provider output is always nonprimary. Only
`user/local-user-turn` on a qualified capture route is primary evidence.

For non-receipt routes, `direction.ingress.accepted_roles=["evidence"]` names the route-level
ingress evidence class; it is not a `watari.turn-receipt.v1` semantic role. Disabled connector
receipt capture fields are `not-applicable`, so the matrix never represents provider as a turn
role.

Codex receipt capture is bound to `route.codex.full-watari.v1`; Pi high-trust receipt capture is
bound to `route.pi.openai-codex.trusted-dream.v1`. No qualified Claude model route exists in D005.
The Claude receipt route therefore accepts capture-only local roles with its own route as a local
origin marker, but this does not prove a model origin. Claude `provider-output` remains
`deny-until-qualified-model-route`.

## Connector qualification boundary

The connector contract binds GET-only methods, read-only state, source policy, credential scope,
and `checkpoint_lineage_binding=required-at-D008-evidence-boundary`. D005 defines that static
requirement only; it does not claim that any actual checkpoint lineage has been observed or
verified. Connector evidence remains unqualified until D008 supplies an independent observed
lineage verifier. Method, scope, source-policy, credential, or contract drift fails closed.
