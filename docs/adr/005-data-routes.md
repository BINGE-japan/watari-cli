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
  "route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4",
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
      "route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4",
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
        "declassification": "forbidden"
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
      "route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4",
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
        "declassification": "forbidden"
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
      "route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4",
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
        "declassification": "forbidden"
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
      "route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4",
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
        "declassification": "forbidden"
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
        "provider_output_policy": "deny-until-allowlisted-model-origin"
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
      "route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4",
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
        "declassification": "forbidden"
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
      "route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4",
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
        "declassification": "forbidden"
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
      "route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4",
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
        "declassification": "forbidden"
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
    "provider_ingress_user": "deny",
    "launch_attestation_semantics": "opaque-nonempty-hash-bound-structural-only",
    "authenticity_dependencies": [
      "D006",
      "D007",
      "Z001"
    ]
  },
  "test_vectors": {
    "routes": {
      "route.codex.full-watari.v1": {
        "sample_bytes_hex": "7761746172692d776972652d73616d706c652d76313a726f7574652e636f6465782e66756c6c2d7761746172692e76310a",
        "golden_fingerprint": "watari-context-effective-v1:d6a8a09abe4b7ea1ada2115ea67cf46d0b69eeffc7e1cd48c2f16fbbf8356ad2",
        "wire_bytes_digest": "watari-wire-bytes-v1:2d09d8d1a72e2840a0ae5acd9c957057a37783a404c631f0b8f33117d0e6b686",
        "connector_digest": "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1"
      },
      "route.pi.openai-codex.trusted-dream.v1": {
        "sample_bytes_hex": "7761746172692d776972652d73616d706c652d76313a726f7574652e70692e6f70656e61692d636f6465782e747275737465642d647265616d2e76310a",
        "golden_fingerprint": "watari-context-effective-v1:cf55e31221003f077631cb68dd90667eb37fb55bd17ae46647e97d336476df4e",
        "wire_bytes_digest": "watari-wire-bytes-v1:fffc52d9651394ab7f2641724f0b7f7e8a8b3d2e981dcba4ae307be141a6cade",
        "connector_digest": "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1"
      },
      "route.pi.openrouter.low-risk-utility.v1": {
        "sample_bytes_hex": "7761746172692d776972652d73616d706c652d76313a726f7574652e70692e6f70656e726f757465722e6c6f772d7269736b2d7574696c6974792e76310a",
        "golden_fingerprint": "watari-context-effective-v1:bbf21f626672a78a34eb0c16d91479d082d11e142ca386d2829e18d9810b13db",
        "wire_bytes_digest": "watari-wire-bytes-v1:af87aa8b8146e9e54599928ed27f6e5054b698b995d62536b4b867d90c886f4e",
        "connector_digest": "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1"
      },
      "route.session-receipt.claude.v1": {
        "sample_bytes_hex": "7761746172692d776972652d73616d706c652d76313a726f7574652e73657373696f6e2d726563656970742e636c617564652e76310a",
        "golden_fingerprint": "watari-context-effective-v1:6af03080a6a4c6a08d5e4140a642db338f47db2b6b592d01d0b8f75b1f6e8347",
        "wire_bytes_digest": "watari-wire-bytes-v1:966920edc9320531ad765bc8cc9715f82c2b26576a71359b56b426ae59c05fda",
        "connector_digest": "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1"
      },
      "route.session-receipt.codex.v1": {
        "sample_bytes_hex": "7761746172692d776972652d73616d706c652d76313a726f7574652e73657373696f6e2d726563656970742e636f6465782e76310a",
        "golden_fingerprint": "watari-context-effective-v1:a51de229cfc44d2e3bc45358045e7d768335d22ea07f23d8a825693ce0a1fbe9",
        "wire_bytes_digest": "watari-wire-bytes-v1:4978c3f6467eda12dc85685311ffd3244350d380e13993c65b932b29b3026291",
        "connector_digest": "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1"
      },
      "route.session-receipt.pi-high-trust.v1": {
        "sample_bytes_hex": "7761746172692d776972652d73616d706c652d76313a726f7574652e73657373696f6e2d726563656970742e70692d686967682d74727573742e76310a",
        "golden_fingerprint": "watari-context-effective-v1:6f1b3a873289c89427bc63be9ca83b667b860635bea928d518b53517991516de",
        "wire_bytes_digest": "watari-wire-bytes-v1:e7f3a7c55ca953ca580baba635eb99345b2a842df0a77bba69d7189befa48bc8",
        "connector_digest": "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1"
      },
      "route.connector.read-only.v1": {
        "sample_bytes_hex": "7761746172692d776972652d73616d706c652d76313a726f7574652e636f6e6e6563746f722e726561642d6f6e6c792e76310a",
        "golden_fingerprint": "watari-context-effective-v1:6d938796c84325cc8fee17e32605409498861915f9b4298333f1602950e36f1a",
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
            "watari_launch_attestation_digest": "watari-attestation-v1:1945b5cb65077a7654f728b769d2e9043921477ebf56f00b0d9a97274cc38939",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:87d1a9988efe3825f989e393ec31c4052f42924b349aed2ad06f591ec3a9f302",
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
            "watari_launch_attestation_digest": "watari-attestation-v1:1945b5cb65077a7654f728b769d2e9043921477ebf56f00b0d9a97274cc38939",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:87d1a9988efe3825f989e393ec31c4052f42924b349aed2ad06f591ec3a9f302",
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
            "watari_launch_attestation_digest": "watari-attestation-v1:1945b5cb65077a7654f728b769d2e9043921477ebf56f00b0d9a97274cc38939",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:87d1a9988efe3825f989e393ec31c4052f42924b349aed2ad06f591ec3a9f302",
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
            "watari_launch_attestation_digest": "watari-attestation-v1:1945b5cb65077a7654f728b769d2e9043921477ebf56f00b0d9a97274cc38939",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:87d1a9988efe3825f989e393ec31c4052f42924b349aed2ad06f591ec3a9f302",
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
            "watari_launch_attestation_digest": "watari-attestation-v1:61acc90d51628dcf402d0cdc2ffff26a0ba8a98a5b1b2d30f8e94b3eb2d87e0f",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:a638bc982258bc433636e7aac917768b533758356a396b10a7ec8653142dd7d5",
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
            "watari_launch_attestation_digest": "watari-attestation-v1:61acc90d51628dcf402d0cdc2ffff26a0ba8a98a5b1b2d30f8e94b3eb2d87e0f",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:a638bc982258bc433636e7aac917768b533758356a396b10a7ec8653142dd7d5",
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
            "watari_launch_attestation_digest": "watari-attestation-v1:61acc90d51628dcf402d0cdc2ffff26a0ba8a98a5b1b2d30f8e94b3eb2d87e0f",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:a638bc982258bc433636e7aac917768b533758356a396b10a7ec8653142dd7d5",
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
            "watari_launch_attestation_digest": "watari-attestation-v1:61acc90d51628dcf402d0cdc2ffff26a0ba8a98a5b1b2d30f8e94b3eb2d87e0f",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:a638bc982258bc433636e7aac917768b533758356a396b10a7ec8653142dd7d5",
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
            "watari_launch_attestation_digest": "watari-attestation-v1:8c8461f48ca580949d692a4776a62400e2a4fa65f20493beec397c359cdbc5a6",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:6d3e37555ae89d1721b0484c1ba68198c0e7aa1c0261a19f8b0b3558cf0b6cf9",
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
            "watari_launch_attestation_digest": "watari-attestation-v1:8c8461f48ca580949d692a4776a62400e2a4fa65f20493beec397c359cdbc5a6",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:6d3e37555ae89d1721b0484c1ba68198c0e7aa1c0261a19f8b0b3558cf0b6cf9",
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
            "watari_launch_attestation_digest": "watari-attestation-v1:8c8461f48ca580949d692a4776a62400e2a4fa65f20493beec397c359cdbc5a6",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:6d3e37555ae89d1721b0484c1ba68198c0e7aa1c0261a19f8b0b3558cf0b6cf9",
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
            "watari_launch_attestation_digest": "watari-attestation-v1:8c8461f48ca580949d692a4776a62400e2a4fa65f20493beec397c359cdbc5a6",
            "origin_route_provider_model_policy_digest": "watari-origin-v1:6d3e37555ae89d1721b0484c1ba68198c0e7aa1c0261a19f8b0b3558cf0b6cf9",
            "primary_evidence": false
          }
        }
      }
    },
    "provider_output_receipts": {
      "case.receipt.provider-output.codex.accept-nonprimary.v1": {
        "case_id": "case.receipt.provider-output.codex.accept-nonprimary.v1",
        "observed_turn_id": "turn:case.receipt.provider-output.codex.accept-nonprimary.v1",
        "observed_capture_route_id": "route.session-receipt.codex.v1",
        "observed_origin_route_id": "route.codex.full-watari.v1",
        "observed_bytes_hex": "6c69746572616c2d70726f76696465722d6f75747075743a636f6465780a",
        "observed_role": "assistant",
        "observed_source": "provider-output",
        "observed_session_lineage": "literal-lineage:codex",
        "observed_launch_attestation": "opaque-launch-attestation:synthetic:codex",
        "receipt": {
          "schema_version": "watari.turn-receipt.v1",
          "turn_id": "turn:case.receipt.provider-output.codex.accept-nonprimary.v1",
          "route_id": "route.session-receipt.codex.v1",
          "origin_route_id": "route.codex.full-watari.v1",
          "bytes_digest": "watari-wire-bytes-v1:b2811d37f99f9b2ecda97cd5016700f598a735be2f21ad71a6f2b3ad5241df51",
          "role": "assistant",
          "source": "provider-output",
          "session_lineage_digest": "watari-lineage-v1:6b5dfc7a4d2c21c824a3738d38faa99615d4629e318ac3518fefc31cdbed05db",
          "watari_launch_attestation_digest": "watari-attestation-v1:96dd6b20f3aadf1772a77b01d84f9f5a6faea65ef86b889ca5c8c36a6d69af77",
          "origin_route_provider_model_policy_digest": "watari-origin-v1:a638bc982258bc433636e7aac917768b533758356a396b10a7ec8653142dd7d5",
          "primary_evidence": false
        },
        "expected_error_codes": []
      },
      "case.receipt.provider-output.pi.accept-nonprimary.v1": {
        "case_id": "case.receipt.provider-output.pi.accept-nonprimary.v1",
        "observed_turn_id": "turn:case.receipt.provider-output.pi.accept-nonprimary.v1",
        "observed_capture_route_id": "route.session-receipt.pi-high-trust.v1",
        "observed_origin_route_id": "route.pi.openai-codex.trusted-dream.v1",
        "observed_bytes_hex": "6c69746572616c2d70726f76696465722d6f75747075743a70690a",
        "observed_role": "assistant",
        "observed_source": "provider-output",
        "observed_session_lineage": "literal-lineage:pi",
        "observed_launch_attestation": "opaque-launch-attestation:synthetic:pi",
        "receipt": {
          "schema_version": "watari.turn-receipt.v1",
          "turn_id": "turn:case.receipt.provider-output.pi.accept-nonprimary.v1",
          "route_id": "route.session-receipt.pi-high-trust.v1",
          "origin_route_id": "route.pi.openai-codex.trusted-dream.v1",
          "bytes_digest": "watari-wire-bytes-v1:2786e97c4406981aba33c5a2f346ebce3dc4349aafae58f8ba74467e35f8f993",
          "role": "assistant",
          "source": "provider-output",
          "session_lineage_digest": "watari-lineage-v1:8a6b884c7f6eda7e274644460d043edeb18350ff43171649daa50c92a1d33073",
          "watari_launch_attestation_digest": "watari-attestation-v1:2545ddce8c0212f8dad499b323f87121432a1d8a64a7deb3febb99159263e3f4",
          "origin_route_provider_model_policy_digest": "watari-origin-v1:6d3e37555ae89d1721b0484c1ba68198c0e7aa1c0261a19f8b0b3558cf0b6cf9",
          "primary_evidence": false
        },
        "expected_error_codes": []
      },
      "case.receipt.provider-output.claude.deny.v1": {
        "case_id": "case.receipt.provider-output.claude.deny.v1",
        "observed_turn_id": "turn:case.receipt.provider-output.claude.deny.v1",
        "observed_capture_route_id": "route.session-receipt.claude.v1",
        "observed_origin_route_id": "route.session-receipt.claude.v1",
        "observed_bytes_hex": "6c69746572616c2d70726f76696465722d6f75747075743a636c617564650a",
        "observed_role": "assistant",
        "observed_source": "provider-output",
        "observed_session_lineage": "literal-lineage:claude",
        "observed_launch_attestation": "opaque-launch-attestation:synthetic:claude",
        "receipt": {
          "schema_version": "watari.turn-receipt.v1",
          "turn_id": "turn:case.receipt.provider-output.claude.deny.v1",
          "route_id": "route.session-receipt.claude.v1",
          "origin_route_id": "route.session-receipt.claude.v1",
          "bytes_digest": "watari-wire-bytes-v1:8908a779c11016715049ce1c0beab1cb9622dcbb69c84965729753d5cfc92f86",
          "role": "assistant",
          "source": "provider-output",
          "session_lineage_digest": "watari-lineage-v1:5b3637adeb5989cf28a1506c7762b27dabd64b1feeacbc52b1a2b394f34d4e7d",
          "watari_launch_attestation_digest": "watari-attestation-v1:e34bae953d62b180fdc9125581c136f6ad64de96778571b7cbe4695307f5b457",
          "origin_route_provider_model_policy_digest": "watari-origin-v1:87d1a9988efe3825f989e393ec31c4052f42924b349aed2ad06f591ec3a9f302",
          "primary_evidence": false
        },
        "expected_error_codes": [
          "capture_route.provider_output_denied"
        ]
      }
    },
    "egress_receipts": {
      "case.egress.structural-arbitrary.codex.v1": {
        "case_id": "case.egress.structural-arbitrary.codex.v1",
        "observed_egress_id": "egress:synthetic:arbitrary-codex",
        "observed_route_id": "route.codex.full-watari.v1",
        "observed_provider_id": "provider.openai.codex-cli.v1",
        "observed_model_id": "model.codex.full-watari.v1",
        "observed_endpoint_id": "endpoint.codex.approved.v1",
        "observed_bytes_hex": "007761746172692d6567726573732d6e6f6e66697874757265ff0d0a",
        "observed_context_manifest": {
          "schema_version": 1,
          "context_schema": "watari.context/v1",
          "projection_kind": "effective",
          "policy_revision": "D003.route-policy.v1",
          "profile_revision": "profile.v1",
          "memory_revision": "memory.v1",
          "project_revision": "project.v1",
          "visibility": "trusted-model",
          "route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4"
        },
        "observed_route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4",
        "observed_launch_attestation": "opaque-egress-launch:synthetic:arbitrary-codex",
        "observed_capability_evidence": "opaque-capability-evidence:synthetic:arbitrary-codex",
        "receipt": {
          "schema_version": "watari.egress-receipt.v1",
          "egress_id": "egress:synthetic:arbitrary-codex",
          "route_id": "route.codex.full-watari.v1",
          "provider_id": "provider.openai.codex-cli.v1",
          "model_id": "model.codex.full-watari.v1",
          "endpoint_id": "endpoint.codex.approved.v1",
          "bytes_digest": "watari-wire-bytes-v1:69cb9f7bfe3c841f821ab470ccbc38a0fc308b5994c48819a33382cfbbd5baf2",
          "context_fingerprint": "watari-context-effective-v1:d0cd623c43009e0a99f61dbbc56d8dce4b88c28c4a1fa1757f63db54d2c22f36",
          "route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4",
          "launch_attestation_digest": "watari-egress-launch-v1:4e38fb1a34cc4d533a7b5d2f0fad1670756b1775cbca300c645dd684af67c8ff",
          "capability_evidence_digest": "watari-capability-evidence-v1:6835d50e4c1bfa42a3a41eb61aa74b2da18ebdfff8ef6a3026de3f5a5fcf2f38",
          "verification_status": "structural-binding-only"
        },
        "expected_error_codes": []
      },
      "case.egress.structural-arbitrary.pi-openai-codex-trusted-dream.v1": {
        "case_id": "case.egress.structural-arbitrary.pi-openai-codex-trusted-dream.v1",
        "observed_egress_id": "egress:synthetic:arbitrary-pi-openai-codex-trusted-dream",
        "observed_route_id": "route.pi.openai-codex.trusted-dream.v1",
        "observed_provider_id": "provider.openai.api.v1",
        "observed_model_id": "model.openai-codex.trusted-dream.v1",
        "observed_endpoint_id": "endpoint.openai.exact.v1",
        "observed_bytes_hex": "007761746172692d6567726573732d6e6f6e666978747572652d76313a726f7574652e70692e6f70656e61692d636f6465782e747275737465642d647265616d2e7631ff0d0a",
        "observed_context_manifest": {
          "schema_version": 1,
          "context_schema": "watari.context/v1",
          "projection_kind": "effective",
          "policy_revision": "D003.route-policy.v1",
          "profile_revision": "profile.v1",
          "memory_revision": "memory.v1",
          "project_revision": "project.v1",
          "visibility": "trusted-model",
          "route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4"
        },
        "observed_route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4",
        "observed_launch_attestation": "opaque-egress-launch:synthetic:arbitrary-pi-openai-codex-trusted-dream",
        "observed_capability_evidence": "opaque-capability-evidence:synthetic:arbitrary-pi-openai-codex-trusted-dream",
        "receipt": {
          "schema_version": "watari.egress-receipt.v1",
          "egress_id": "egress:synthetic:arbitrary-pi-openai-codex-trusted-dream",
          "route_id": "route.pi.openai-codex.trusted-dream.v1",
          "provider_id": "provider.openai.api.v1",
          "model_id": "model.openai-codex.trusted-dream.v1",
          "endpoint_id": "endpoint.openai.exact.v1",
          "bytes_digest": "watari-wire-bytes-v1:fc54d619ad9c0abc0cdf83c2ab0e1e2237be64ab542e22eda079d8e44a29aa0b",
          "context_fingerprint": "watari-context-effective-v1:58ab8727691fe59495dbfe156ed1d036302d55bfde150d10c9a86b80cc4da195",
          "route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4",
          "launch_attestation_digest": "watari-egress-launch-v1:81c6fa411f0e30c0e35e3afecf95eab34d6cd456f2da6fb2870a697149209e4a",
          "capability_evidence_digest": "watari-capability-evidence-v1:d6b0d4eba17b9feecab6ce91350255bc8153f3fbfbe2dca00543d3b87eb2b783",
          "verification_status": "structural-binding-only"
        },
        "expected_error_codes": []
      },
      "case.egress.structural-arbitrary.pi-openrouter-low-risk-utility.v1": {
        "case_id": "case.egress.structural-arbitrary.pi-openrouter-low-risk-utility.v1",
        "observed_egress_id": "egress:synthetic:arbitrary-pi-openrouter-low-risk-utility",
        "observed_route_id": "route.pi.openrouter.low-risk-utility.v1",
        "observed_provider_id": "provider.openrouter.api.v1",
        "observed_model_id": "model.openrouter.low-risk-utility.v1",
        "observed_endpoint_id": "endpoint.openrouter.exact.v1",
        "observed_bytes_hex": "007761746172692d6567726573732d6e6f6e666978747572652d76313a726f7574652e70692e6f70656e726f757465722e6c6f772d7269736b2d7574696c6974792e7631ff0d0a",
        "observed_context_manifest": {
          "schema_version": 1,
          "context_schema": "watari.context/v1",
          "projection_kind": "effective",
          "policy_revision": "D003.route-policy.v1",
          "profile_revision": "profile.v1",
          "memory_revision": "memory.v1",
          "project_revision": "project.v1",
          "visibility": "low-risk-model",
          "route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4"
        },
        "observed_route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4",
        "observed_launch_attestation": "opaque-egress-launch:synthetic:arbitrary-pi-openrouter-low-risk-utility",
        "observed_capability_evidence": "opaque-capability-evidence:synthetic:arbitrary-pi-openrouter-low-risk-utility",
        "receipt": {
          "schema_version": "watari.egress-receipt.v1",
          "egress_id": "egress:synthetic:arbitrary-pi-openrouter-low-risk-utility",
          "route_id": "route.pi.openrouter.low-risk-utility.v1",
          "provider_id": "provider.openrouter.api.v1",
          "model_id": "model.openrouter.low-risk-utility.v1",
          "endpoint_id": "endpoint.openrouter.exact.v1",
          "bytes_digest": "watari-wire-bytes-v1:6982eb415f42614930b8021f0110af544faec16bbc4134cb2010b82838f7acb6",
          "context_fingerprint": "watari-context-effective-v1:1045b07a5bc51473847e584e49f6b83d6a02d092037cc8b2b9665b028bd21f16",
          "route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4",
          "launch_attestation_digest": "watari-egress-launch-v1:71b8c62c73f175a8207216e5106af40834f1bc6851b8976cc1125daa339426c5",
          "capability_evidence_digest": "watari-capability-evidence-v1:cb58cd4dae61ef700bce89fe881cea09c78e94a66131ee1a01dfd7398b375237",
          "verification_status": "structural-binding-only"
        },
        "expected_error_codes": []
      },
      "case.egress.structural-arbitrary.connector-read-only.v1": {
        "case_id": "case.egress.structural-arbitrary.connector-read-only.v1",
        "observed_egress_id": "egress:synthetic:arbitrary-connector-read-only",
        "observed_route_id": "route.connector.read-only.v1",
        "observed_provider_id": "provider.connector.v1",
        "observed_model_id": "model.none.v1",
        "observed_endpoint_id": "endpoint.connector-read-only.v1",
        "observed_bytes_hex": "007761746172692d6567726573732d6e6f6e666978747572652d76313a726f7574652e636f6e6e6563746f722e726561642d6f6e6c792e7631ff0d0a",
        "observed_context_manifest": {
          "schema_version": 1,
          "context_schema": "watari.context/v1",
          "projection_kind": "effective",
          "policy_revision": "D003.route-policy.v1",
          "profile_revision": "profile.v1",
          "memory_revision": "memory.v1",
          "project_revision": "project.v1",
          "visibility": "local-only",
          "route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4"
        },
        "observed_route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4",
        "observed_launch_attestation": "opaque-egress-launch:synthetic:arbitrary-connector-read-only",
        "observed_capability_evidence": "opaque-capability-evidence:synthetic:arbitrary-connector-read-only",
        "receipt": {
          "schema_version": "watari.egress-receipt.v1",
          "egress_id": "egress:synthetic:arbitrary-connector-read-only",
          "route_id": "route.connector.read-only.v1",
          "provider_id": "provider.connector.v1",
          "model_id": "model.none.v1",
          "endpoint_id": "endpoint.connector-read-only.v1",
          "bytes_digest": "watari-wire-bytes-v1:19306680256387141e3607f582b691e2fac2645431bad7ebf825d1e473993585",
          "context_fingerprint": "watari-context-effective-v1:d8a9debe63e023a9b471a06413ba0a2bf3894ce04d2835e786197fda02d78a09",
          "route_policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4",
          "launch_attestation_digest": "watari-egress-launch-v1:0b72111423f58464b274cf7e21896332f60d043b3b48b7d730d6ee122cd56d18",
          "capability_evidence_digest": "watari-capability-evidence-v1:fff63f662159bf1ef834b656fbeecc077a96fec5276570f9c89a82d05d763de0",
          "verification_status": "structural-binding-only"
        },
        "expected_error_codes": []
      }
    }
  },
  "egress_receipt_schema": {
    "schema_version": "watari.egress-receipt-schema.v1",
    "receipt_schema": "watari.egress-receipt.v1",
    "required_fields": [
      "schema_version",
      "egress_id",
      "route_id",
      "provider_id",
      "model_id",
      "endpoint_id",
      "bytes_digest",
      "context_fingerprint",
      "route_policy_digest",
      "launch_attestation_digest",
      "capability_evidence_digest",
      "verification_status"
    ],
    "structural_verification": "D005-only",
    "observed_egress_produced_by_D005": false,
    "authenticity_dependencies": [
      "D006",
      "C004",
      "Z001"
    ],
    "runtime_source_qualification_dependencies": [
      "D006",
      "D007"
    ],
    "launch_attestation_semantics": "opaque-nonempty-hash-bound"
  }
}
```

## Static route policy and structural egress receipt

The route matrix is a static closed allowlist. Its D003 typed-frame digest covers every documented
top-level, route, and nested policy leaf except the exact code-owned derived paths declared in
`projection_policy.policy_digest_excluded_paths`. The verifier never reads exclusions from the
matrix; its frozen `POLICY_EXCLUDED_PATHS` is authoritative. Exact exclusions are limited to policy
self-digests, the complete `test_vectors` subtree, and connector contract digests.

Each route's `wire_projection` contains only selection, visibility, and declassification policy.
Sample bytes, context fingerprints, and bytes digests exist only under `test_vectors`. They are
synthetic literal oracles and are not evidence that any egress occurred.

The closed `watari.egress-receipt.v1` structural verifier takes separately supplied egress ID,
route, provider, model, endpoint, exact bytes, a closed D003 effective-context manifest, policy,
opaque launch attestation, and opaque capability evidence. It validates that manifest, resolves the
route from the approved matrix, and recomputes the bytes, context, launch, and capability digests.
A successful result means only
`structural-binding-only`. D005 produces no observed egress and authenticates no runtime, launch,
source, sandbox, or capture. D006 supplies runtime qualification, C004 supplies the named route and
provider/endpoint verification, Z001 supplies sandbox/egress capture qualification, and D007
supplies runtime-session source qualification.

## Turn receipt structural boundary

A turn receipt uses separately supplied turn ID, capture route ID, declared origin route ID, bytes,
semantic role, source, session lineage, and launch-attestation value. The verifier resolves both
route IDs from the approved matrix and derives provider/model/runtime/policy identity from those
records. The capture route must require receipts, the semantic role must be one of `user`,
`assistant`, `tool`, or `system`, the role/source pair must be allowlisted, and the declared origin
route must be in the capture route's explicit allowlist. Provider is a source (`provider-output`),
not a role. Provider output is always nonprimary. Only `user/local-user-turn` on an allowlisted
receipt route is primary evidence.

The launch-attestation value is opaque, nonempty, and hash-bound only. D005 proves structural
binding to the capture route, declared origin route/runtime, and policy; it does not authenticate a
launch or establish that the declared origin was the runtime source. D006 and D007 must qualify
runtime/session source authenticity, while Z001 must qualify sandbox/egress capture.

For non-receipt routes, `direction.ingress.accepted_roles=["evidence"]` names a route-level evidence
class, not a `watari.turn-receipt.v1` semantic role. Disabled connector receipt fields are
`not-applicable`. Codex receipt capture allowlists `route.codex.full-watari.v1`; Pi high-trust
capture allowlists `route.pi.openai-codex.trusted-dream.v1`. D005 has no allowlisted external Claude
model origin. Claude's self-route is a local capture marker only, and Claude `provider-output`
remains `deny-until-allowlisted-model-origin`.

## Connector qualification boundary

The connector contract binds GET-only methods, read-only state, source policy, credential scope,
and `checkpoint_lineage_binding=required-at-D008-evidence-boundary`. D005 defines that static
requirement only; it does not observe or verify runtime checkpoint lineage. Connector evidence
remains structurally unaccepted until D008 supplies its independent lineage verifier. Method,
scope, source-policy, credential, or contract drift fails closed.

## Reviewed size exception and rationale

Disposition: a D005-only exception to the 300-line review guideline is proposed for this ADR and
its contract test and becomes effective only through the separately approved governance overlay.
The machine contract is one formal closed seven-route matrix with exact nested
schemas, code-owned exclusions, independent route/turn/provider-output/egress literals, and fixed
negative cases. Keeping those literals adjacent makes the security boundary directly reviewable.

Generating the literals would replace independent oracles with a shared implementation path.
Splitting them into new fixture or helper files would expand the proposed three-file overlay scope and
make cross-file review weaker. Obvious reusable digest and validation logic remains centralized;
the remaining size is intentional closed-schema and literal-oracle coverage, not runtime product
code. This exception does not apply to later tickets.

## Execution dependency note

D003 canonical framing and the named `T-ROUTE-MATRIX` test are required to execute and verify this
machine contract. This dependency statement does not self-authorize a frozen-DAG expansion or any
new implementation scope; repository governance is resolved separately by the root workflow.
