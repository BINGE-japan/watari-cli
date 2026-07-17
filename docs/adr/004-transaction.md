# ADR-004: Canonical transaction, immutable views, and crash recovery

Status: accepted for the private-pilot logical model. D010 qualifies the
cryptographic implementation; D011 selects the physical object layout.

## Decision

Watari has one local canonical writer at a time. The local
`refs/watari/current` Git ref names the only authoritative commit. Journals,
candidate commits, derived views, receipts, caches, mutable hints, and remote
refs are evidence or derivations, never authority.

A candidate commit is built and fully verified, then its immutable commit-OID
view is published before the ref. The ref moves once through compare-and-swap
against the expected old OID. The ref update is the authority switch. A reader
therefore never sees a newly authoritative OID before its view is durable.

For every non-genesis transaction, the authorization policy comes only from the
verified expected-old commit. A candidate policy cannot authorize its own
commit. A policy transition requires the old policy's `policy.transition`
capability and becomes effective only for later transactions. Genesis alone
uses an out-of-band owner trust anchor.

## Machine-readable model

This JSON block is normative. Prose explains it but cannot override it.

<!-- transaction-model:start -->
```json
{
  "schema_version": 1,
  "digest_rules": {
    "canonical_json": "D003-NFC-LF-JCS-UTF16-key-order",
    "frame": "D003-WATARI-domain-separated-length-frame",
    "raw_sha256_without_typed_frame": "forbidden",
    "applies_to": "every_D004_v1_digest"
  },
  "typed_digest_test_vectors": {
    "tree_diff_base": "watari-tree-diff-v1:fd46edda28728a45523ed65fd05ce6091cee249a83b33c56578ecd8aac800753",
    "resolution_decision_event_quarantine": "watari-resolution-decision-v1:25d884e4cd8bda1f58ae485e2638c0f9963dd9fcf56fd09d301b615ff6dbc57d",
    "resolution_decision_set_event_quarantine": "watari-resolution-decision-set-v1:b3d2b11d2495ce40c149a8da3a98e0bface71b7529eab6279ce83611f1725f6d",
    "checkpoint_item_set_single": "watari-checkpoint-item-set-v1:b0b784d6f2b59d81e8b6e708a0604f17a0e38a0b081266261837a949a142e69f",
    "dream_decision_manifest_reject_single": "watari-dream-decision-manifest-v1:c4aa38759625ce6815880d298aaa509e315e2f8e1c0f043b790e4aa63972d4a3",
    "checkpoint_dream_binding_base": "watari-checkpoint-dream-v1:eebb4512c3f2fc2331ade5ce42d179452352950f0fc1e0335077825ca85e2745",
    "checkpoint_dream_binding_set_base": "watari-checkpoint-dream_run-set-v1:f374924d5ed978df72950eb0a725b93ba1bd8ec11ebc9ddfcc85f88b63dea650",
    "checkpoint_source_key_base": "watari-checkpoint-source-v1:f5480795cd9b402efee0f139b01f0f417e98e43b653157312014317143a3b8bd",
    "checkpoint_migration_binding_base": "watari-checkpoint-migration-v1:57b522ec6da0144b3584f75b5946d8b672212dd1dc771bd6611360f540e682a0",
    "checkpoint_migration_binding_set_base": "watari-checkpoint-migration_import-set-v1:1b44bdb97509d0cd1f785015f0d8f52915436d37074a275b1c5d9990db663e83",
    "sync_merge_certificate_base": "watari-sync-merge-certificate-v1:9f412e9c3938f638dd3531e65d5d1365de01fabc8338fb0c2fc9629a227217ae"
  },
  "states": [
    "PREPARED",
    "COMMIT_CREATED",
    "VIEW_PUBLISHED",
    "REF_UPDATED",
    "COMPLETE"
  ],
  "transitions": [
    {"from": null, "to": "PREPARED"},
    {"from": "PREPARED", "to": "COMMIT_CREATED"},
    {"from": "COMMIT_CREATED", "to": "VIEW_PUBLISHED"},
    {"from": "VIEW_PUBLISHED", "to": "REF_UPDATED"},
    {"from": "REF_UPDATED", "to": "COMPLETE"}
  ],
  "operations": [
    {
      "name": "prepare_and_fsync",
      "effects": {"journal_state": "PREPARED"}
    },
    {
      "name": "create_and_verify_signed_commit",
      "effects": {
        "commit_valid": true,
        "new_oid": "verified_signed_commit_oid"
      }
    },
    {
      "name": "record_commit_created",
      "effects": {"journal_state": "COMMIT_CREATED"}
    },
    {
      "name": "publish_and_verify_immutable_view",
      "effects": {"view_published": true}
    },
    {
      "name": "record_view_published",
      "effects": {"journal_state": "VIEW_PUBLISHED"}
    },
    {
      "name": "compare_and_swap_ref",
      "effects": {"ref": "new"}
    },
    {
      "name": "record_ref_updated",
      "effects": {"journal_state": "REF_UPDATED"}
    },
    {
      "name": "publish_transaction_receipt",
      "effects": {"transaction_receipt": true}
    },
    {
      "name": "record_complete",
      "effects": {"journal_state": "COMPLETE"}
    }
  ],
  "transaction_kinds": {
    "allowed": [
      "genesis",
      "ordinary",
      "dream_apply",
      "sync_merge",
      "migration_import",
      "policy_transition"
    ],
    "unknown_kind": "reject",
    "manifest_unknown_fields": "reject",
    "matrix": [
      {
        "kind": "genesis",
        "expected_old": "null",
        "parents": "none",
        "authorization": "genesis_anchor",
        "sync_certificate": "forbidden",
        "dream_bindings": "forbidden",
        "migration_bindings": "forbidden",
        "result_policy": "initial"
      },
      {
        "kind": "ordinary",
        "expected_old": "required",
        "parents": "expected_old_only",
        "authorization": "expected_old_policy",
        "sync_certificate": "forbidden",
        "dream_bindings": "forbidden",
        "migration_bindings": "forbidden",
        "result_policy": "unchanged"
      },
      {
        "kind": "dream_apply",
        "expected_old": "required",
        "parents": "expected_old_only",
        "authorization": "expected_old_policy",
        "sync_certificate": "forbidden",
        "dream_bindings": "required_nonempty",
        "migration_bindings": "forbidden",
        "result_policy": "unchanged"
      },
      {
        "kind": "sync_merge",
        "expected_old": "required",
        "parents": "expected_old_first_and_at_least_two",
        "authorization": "expected_old_policy",
        "sync_certificate": "required",
        "dream_bindings": "forbidden",
        "migration_bindings": "forbidden",
        "result_policy": "unchanged"
      },
      {
        "kind": "migration_import",
        "expected_old": "required",
        "parents": "expected_old_only",
        "authorization": "expected_old_policy",
        "sync_certificate": "forbidden",
        "dream_bindings": "forbidden",
        "migration_bindings": "required_nonempty",
        "result_policy": "unchanged"
      },
      {
        "kind": "policy_transition",
        "expected_old": "required",
        "parents": "expected_old_only",
        "authorization": "expected_old_policy",
        "sync_certificate": "forbidden",
        "dream_bindings": "forbidden",
        "migration_bindings": "forbidden",
        "result_policy": "changed"
      }
    ]
  },
  "prepared_intent": {
    "schema": "watari.transaction-intent/v1",
    "exact_fields": [
      "schema_version",
      "intent_schema",
      "transaction_kind",
      "state_id",
      "transaction_id",
      "canonical_ref",
      "expected_old_oid",
      "ordered_parent_oids",
      "authorization_policy_revision",
      "authorization_policy_digest",
      "result_policy_revision",
      "result_policy_digest",
      "canonical_input_digests",
      "proposed_changes"
    ],
    "set_fields_sorted_unique": ["canonical_input_digests"],
    "proposed_change_entry_fields": ["class", "digest"],
    "proposed_changes_order": "class_utf8_byte_order",
    "proposed_change_classes_unique": true,
    "proposed_change_digest_values_may_repeat": true,
    "ordered_fields": ["ordered_parent_oids"],
    "canonicalization": "D003-canonical-json",
    "digest_domain": "transaction-intent/v1",
    "digest_prefix": "watari-transaction-intent-v1:",
    "test_vector": {
      "intent": {
        "schema_version": 1,
        "intent_schema": "watari.transaction-intent/v1",
        "transaction_kind": "ordinary",
        "state_id": "state-1",
        "transaction_id": "tx-1",
        "canonical_ref": "refs/watari/current",
        "expected_old_oid": "old-oid",
        "ordered_parent_oids": ["old-oid"],
        "authorization_policy_revision": "policy-1",
        "authorization_policy_digest": "watari-policy-v1:1111111111111111111111111111111111111111111111111111111111111111",
        "result_policy_revision": "policy-1",
        "result_policy_digest": "watari-policy-v1:1111111111111111111111111111111111111111111111111111111111111111",
        "canonical_input_digests": ["watari-input-v1:2222222222222222222222222222222222222222222222222222222222222222"],
        "proposed_changes": [
          {
            "class": "canonical_events",
            "digest": "watari-change-v1:3333333333333333333333333333333333333333333333333333333333333333"
          }
        ]
      },
      "digest": "watari-transaction-intent-v1:cdd772a07de07feba3d09d1dcd9fc7c338b02bb44186494f6b11224183b4cf46"
    }
  },
  "transaction_manifest": {
    "schema": "watari.transaction-manifest/v1",
    "unknown_fields": "reject",
    "required_fields": [
      "manifest_schema",
      "transaction_kind",
      "state_id",
      "transaction_id",
      "canonical_ref",
      "expected_old_oid",
      "ordered_parent_bindings",
      "prepared_intent_digest",
      "authorization",
      "result_policy_revision",
      "result_policy_digest",
      "logical_schema_versions",
      "tree_diff_digest",
      "changed_class_digests",
      "checkpoint_binding_set_digest",
      "checkpoint_binding_count",
      "sync_merge_certificate_digest",
      "migration_binding_set_digest",
      "migration_binding_count",
      "resolution_decision_set_digest",
      "resolution_decision_count"
    ],
    "parent_binding_fields": ["oid", "canonical_state_digest"],
    "authorization_fields": [
      "source",
      "policy_revision",
      "policy_digest",
      "signer_id",
      "declared_capabilities"
    ],
    "logical_schema_version_fields": [
      "event",
      "profile",
      "checkpoint",
      "dream_run_manifest",
      "transaction"
    ],
    "logical_schema_versions_positive_integers": true,
    "prepared_intent_digest_copied_exactly": true,
    "intent_manifest_mirrors_must_equal": true,
    "intent_manifest_mirror_fields": [
      "transaction_kind",
      "state_id",
      "transaction_id",
      "canonical_ref",
      "expected_old_oid",
      "ordered_parent_oids_from_ordered_parent_bindings",
      "authorization_policy_revision_from_authorization",
      "authorization_policy_digest_from_authorization",
      "result_policy_revision",
      "result_policy_digest"
    ],
    "canonical_input_digests_equation": "sorted_unique_exact_verified_external_and_parent_input_digests",
    "proposed_changes_equation": "sorted_class_digest_entries_equal_exact_actual_changed_class_digest_map",
    "changed_class_digests_equation": "exact_recomputed_candidate_tree_class_digest_map",
    "changed_class_digest_scope": [
      "canonical_events",
      "profile_events",
      "source_checkpoints",
      "dream_run_manifests",
      "state_manifest",
      "policy",
      "sync_merge_certificate",
      "checkpoint_bindings",
      "migration_bindings",
      "resolution_decisions"
    ],
    "transaction_manifest_in_changed_class_digests": "forbidden_self_reference",
    "transaction_manifest_integrity": "signed_git_tree_and_commit_object",
    "tree_diff_digest_domain": "tree-diff/v1",
    "tree_diff_digest_prefix": "watari-tree-diff-v1:",
    "binding_set_digests_and_counts_recomputed": true,
    "semantic_inputs_recomputed_conjunctively": [
      "ordered_parent_bindings_from_verified_parent_oids_and_state_digests",
      "authorization_from_trusted_anchor_signer_and_recomputed_diff_capabilities",
      "logical_schema_versions_from_candidate_objects",
      "checkpoint_binding_set_from_candidate_objects",
      "sync_merge_certificate_from_candidate_object",
      "migration_binding_set_from_candidate_objects",
      "resolution_decision_set_from_candidate_objects"
    ],
    "sync_merge_certificate_digest_domain": "sync-merge-certificate/v1",
    "sync_merge_certificate_digest_prefix": "watari-sync-merge-certificate-v1:",
    "kind_binding_presence_rules_rechecked_from_actual_objects": true,
    "resolution_decisions_bound_for_every_transaction_kind": true,
    "same_event_id_conflict_outcome_for_every_transaction_kind": "quarantine_preserve_all_variants",
    "self_oid_field_forbidden": true
  },
  "capability_derivation": {
    "diff_schema": "watari.tree-diff/v1",
    "unknown_diff_fields": "reject",
    "negative_counts": "reject",
    "no_op_diff": "reject",
    "field_to_capability": {
      "genesis_created": "genesis.create",
      "local_memory_event_count": "event.append",
      "local_correction_event_count": "event.correct",
      "local_tombstone_event_count": "event.tombstone",
      "local_profile_event_count": "profile.write",
      "local_checkpoint_change_count": "checkpoint.advance",
      "local_dream_manifest_count": "dream.apply",
      "state_manifest_changed": "state.configure",
      "policy_changed": "policy.transition",
      "secondary_parent_count": "sync.merge",
      "conflict_resolution_count": "conflict.resolve",
      "migration_binding_count": "migration.import"
    },
    "kind_constraints": {
      "genesis": {
        "required": ["genesis.create", "state.configure"],
        "allowed": ["genesis.create", "state.configure"]
      },
      "ordinary": {
        "required": [],
        "allowed": [
          "event.append",
          "event.correct",
          "event.tombstone",
          "profile.write",
          "state.configure",
          "conflict.resolve"
        ]
      },
      "dream_apply": {
        "required": ["dream.apply", "checkpoint.advance"],
        "allowed": ["event.append", "dream.apply", "checkpoint.advance"]
      },
      "sync_merge": {
        "required": ["sync.merge"],
        "allowed": ["sync.merge", "conflict.resolve"]
      },
      "migration_import": {
        "required": ["migration.import"],
        "allowed": [
          "migration.import",
          "event.append",
          "event.correct",
          "event.tombstone",
          "profile.write",
          "checkpoint.advance",
          "state.configure"
        ]
      },
      "policy_transition": {
        "required": ["policy.transition"],
        "allowed": ["policy.transition", "state.configure"]
      }
    },
    "declared_set_must_equal_recomputed_set": true,
    "every_recomputed_capability_must_be_granted_by_anchor": true
  },
  "authorization": {
    "normal_policy_source": "expected_old_commit",
    "genesis_policy_source": "out_of_band_owner_trust_anchor",
    "candidate_policy_cannot_authorize_same_commit": true,
    "secondary_parent_policy_is_not_authority": true,
    "authorization_revision_and_digest_must_match_anchor": true,
    "authorization_bound_to_expected_old_oid": true,
    "revocation_evaluated_at_anchor_policy": true,
    "policy_change_effective_for": "subsequent_transactions_only"
  },
  "ref_update": {
    "ref": "refs/watari/current",
    "operation": "compare-and-swap",
    "expected_non_genesis": "old_oid",
    "expected_genesis": "zero_oid_and_ref_absent",
    "new": "verified_signed_commit_oid",
    "never_force": true,
    "never_retry_with_observed_ref": true
  },
  "commit_validations": [
    "object_exists",
    "signature_valid",
    "prepared_intent_digest_matches_manifest",
    "transaction_kind_constraints_valid",
    "signer_authorized_by_trusted_old_policy_or_genesis_anchor",
    "candidate_policy_cannot_self_authorize",
    "declared_capabilities_equal_recomputed_tree_diff_capabilities",
    "expected_old_is_first_parent_or_genesis",
    "additional_parents_declared_ordered_unique_and_verified",
    "sync_merge_certificate_valid_when_required",
    "merge_tree_losslessly_preserves_all_parent_immutable_variants",
    "merge_conflicts_have_bound_authorized_decisions",
    "event_references_valid_across_all_parent_union_and_additions",
    "supersedes_graph_acyclic_across_all_parent_union_and_additions",
    "event_authorization_valid_by_origin",
    "checkpoint_dream_event_binding_valid",
    "tree_schema_valid",
    "transaction_manifest_matches",
    "canonical_digests_valid",
    "no_unexpected_paths"
  ],
  "atomic_commit_members": [
    "canonical_events",
    "profile_events",
    "source_checkpoints",
    "dream_run_manifests",
    "state_manifest_if_changed",
    "transaction_manifest"
  ],
  "state_transition_equations": {
    "immutable_classes": [
      "canonical_event_variants",
      "profile_events",
      "dream_run_manifests"
    ],
    "genesis": "authorized_additions_only",
    "ordinary_dream_migration": "expected_old_exact_sets_union_authorized_additions",
    "policy_transition": "expected_old_exact_sets",
    "sync_merge": "exact_union_of_all_verified_parent_variants",
    "source_checkpoint_maps": {
      "genesis": "empty",
      "ordinary_and_policy_transition": "expected_old_exact_map",
      "dream_and_migration": "expected_old_exact_map_overlaid_by_exact_bound_writes",
      "bound_write_keys_equal_binding_source_keys": true,
      "unbound_old_sources_must_be_preserved": true
    },
    "authorized_additions_must_be_new": true,
    "counts_and_typed_set_digests_recomputed_from_candidate_tree": true
  },
  "sync_merge": {
    "algorithm": "lossless-immutable-union-v1",
    "pure_merge": true,
    "candidate_additions_must_be_empty": true,
    "certificate_required_for_parent_count_greater_than_one": true,
    "certificate_forbidden_for_parent_count_less_than_or_equal_to_one": true,
    "expected_old_is_first_parent": true,
    "ordered_unique_parent_bindings": true,
    "per_parent_bindings": [
      "parent_oid",
      "canonical_state_digest",
      "event_variant_set_digest_and_count",
      "profile_event_set_digest_and_count",
      "dream_manifest_set_digest_and_count",
      "checkpoint_set_digest_and_count"
    ],
    "immutable_union_classes": [
      "canonical_event_variants",
      "profile_events",
      "dream_run_manifests"
    ],
    "immutable_result_equation": "exact_union_of_all_verified_parent_variants",
    "result_bindings": [
      "result_event_variant_set_digest_and_count",
      "result_profile_event_set_digest_and_count",
      "result_dream_manifest_set_digest_and_count",
      "event_conflict_set_digest",
      "profile_conflict_set_digest",
      "checkpoint_conflict_set_digest",
      "resolution_decision_set_digest"
    ],
    "resolution_decision_fields": [
      "class",
      "conflict_key",
      "variant_digests",
      "outcome",
      "selected_variant_digest",
      "strategy",
      "authorization_policy_revision",
      "authorization_policy_digest",
      "required_capability",
      "decision_digest"
    ],
    "resolution_unknown_fields": "reject",
    "resolution_key": "class_plus_conflict_key",
    "resolution_key_must_be_unique": true,
    "variant_digests_must_be_sorted_unique": true,
    "decision_keys_equal_recomputed_conflict_keys": true,
    "resolution_digest_domain": "resolution-decision/v1",
    "resolution_digest_prefix": "watari-resolution-decision-v1:",
    "resolution_set_digest_domain": "resolution-decision-set/v1",
    "resolution_set_digest_prefix": "watari-resolution-decision-set-v1:",
    "resolution_set_digest_and_count_recomputed": true,
    "resolution_authorization_revision_and_digest_equal_expected_old_policy": true,
    "event_id_collision": "preserve_all_variants_and_quarantine",
    "profile_conflict": "explicit_authorized_select_or_quarantine",
    "checkpoint_conflict": "identical_causal_descendant_or_explicit_authorized_resolution",
    "last_writer_wins": false,
    "checkpoint_max_merge": false,
    "secondary_parent_policy_auto_activation": false
  },
  "event_integrity": {
    "variant_identity": "event_id_plus_envelope_digest",
    "reference_scope": "all_verified_parent_variants_union_transaction_additions",
    "supersedes_source": "D003-event-envelope",
    "target_missing": "reject",
    "target_ambiguous_or_quarantined": "reject",
    "graph": "acyclic",
    "parallel_successors": "preserve_all_and_active_conflict_quarantine",
    "origin_authorization": {
      "verified_parent_event": "originating_parent_trust_chain",
      "transaction_addition": "local_expected_old_policy_or_genesis_anchor",
      "conflict_decision": "local_expected_old_policy"
    }
  },
  "checkpoint_bindings": {
    "unknown_binding_kind": "reject",
    "dream_run": {
      "binding_schema": "watari.checkpoint-binding.dream/v1",
      "binding_kind": "dream_run",
      "unknown_fields": "reject",
      "digest_domain": "checkpoint-binding/dream/v1",
      "digest_prefix": "watari-checkpoint-dream-v1:",
      "item_set_digest_domain": "checkpoint-item-set/v1",
      "item_set_digest_prefix": "watari-checkpoint-item-set-v1:",
      "decision_manifest_digest_domain": "dream-decision-manifest/v1",
      "decision_manifest_digest_prefix": "watari-dream-decision-manifest-v1:",
      "exact_fields": [
        "binding_schema",
        "binding_kind",
        "transaction_id",
        "dream_run_id",
        "source_key",
        "checkpoint_before_digest",
        "checkpoint_after_digest",
        "result_source_event_set_digest",
        "source_snapshot_digest",
        "scan_manifest_digest",
        "decision_manifest_digest",
        "accepted_event_variant_set_digest",
        "accepted_event_count",
        "unresolved_candidate_set_digest",
        "unresolved_candidate_count",
        "quarantine_set_digest",
        "quarantine_count",
        "model_policy_digest",
        "completion_key",
        "status"
      ],
      "source_key_fields": [
        "device_id",
        "connector_instance_id",
        "source_lineage_digest",
        "coordinator_epoch"
      ],
      "completion_key_fields": [
        "device_id",
        "connector_instance_id",
        "source_lineage_digest",
        "local_date",
        "policy_revision"
      ],
      "dream_run_id_unique_and_nonreplayable": true,
      "one_checkpoint_write_per_source_key": true,
      "checkpoint_before_matches_expected_old": true,
      "checkpoint_after_matches_exact_scan_proposal": true,
      "scan_keys_order_and_identity": "sorted_unique_D003_canonical_item_bytes_after_NFC_LF_normalization",
      "decision_keys_equal_scanned_item_keys": true,
      "accepted_event_set_equals_candidate_dream_event_set": true,
      "result_source_event_set_equation": "expected_old_exact_source_event_set_union_accepted_event_set",
      "accepted_candidate_and_result_event_variants_sorted_unique": true,
      "dream_event_run_source_and_policy_must_match": true,
      "global_dream_additions_equal_exact_union_of_bound_candidate_dream_events": true,
      "dream_run_manifest": {
        "schema": "watari.dream-run-manifest/v1",
        "unknown_fields": "reject",
        "exact_fields": [
          "manifest_schema",
          "transaction_id",
          "dream_run_id",
          "source_key",
          "checkpoint_binding_digest",
          "accepted_event_variant_set_digest",
          "accepted_event_count",
          "model_policy_digest",
          "status"
        ],
        "binding_run_id_bijection": true,
        "checkpoint_binding_digest_recomputed": true,
        "mirrored_fields_equal_binding": true,
        "status_must_be_complete": true
      },
      "zero_accepted_events_allowed_with_complete_scan": true,
      "status_must_be_complete": true,
      "unresolved_and_quarantine_counts_must_be_zero": true,
      "shared_source_requires_current_coordinator_epoch": true,
      "dream_cannot_change_profile": true
    },
    "migration_import": {
      "binding_schema": "watari.checkpoint-binding.migration/v1",
      "binding_kind": "migration_import",
      "unknown_fields": "reject",
      "digest_domain": "checkpoint-binding/migration/v1",
      "digest_prefix": "watari-checkpoint-migration-v1:",
      "dream_run_id": "forbidden",
      "exact_fields": [
        "binding_schema",
        "binding_kind",
        "transaction_id",
        "source_key",
        "checkpoint_before_digest",
        "checkpoint_after_digest",
        "migration_snapshot_digest",
        "review_artifact_digest",
        "imported_event_variant_set_digest",
        "imported_event_count",
        "status"
      ],
      "required_evidence": [
        "migration_snapshot_digest",
        "review_artifact_digest",
        "source_key",
        "checkpoint_before_digest",
        "checkpoint_after_digest",
        "imported_event_variant_set_digest"
      ],
      "one_checkpoint_write_per_source_key": true,
      "checkpoint_before_matches_expected_old": true,
      "checkpoint_after_matches_reviewed_proposal": true,
      "snapshot_digest_matches_actual_import_source": true,
      "review_artifact_digest_matches_approved_review": true,
      "imported_set_and_count_recomputed_from_candidate": true,
      "status_must_be_complete": true
    },
    "binding_sets": {
      "dream_run": {
        "digest_domain": "checkpoint-binding-set/dream_run/v1",
        "digest_prefix": "watari-checkpoint-dream_run-set-v1:",
        "manifest_digest_field": "checkpoint_binding_set_digest",
        "manifest_count_field": "checkpoint_binding_count"
      },
      "migration_import": {
        "digest_domain": "checkpoint-binding-set/migration_import/v1",
        "digest_prefix": "watari-checkpoint-migration_import-set-v1:",
        "manifest_digest_field": "migration_binding_set_digest",
        "manifest_count_field": "migration_binding_count"
      }
    },
    "set_digest_input": "sorted_exact_typed_binding_digests",
    "set_digest_and_count_recomputed_from_candidate_tree": true,
    "source_key_digest_domain": "checkpoint-source-key/v1",
    "source_key_digest_prefix": "watari-checkpoint-source-v1:",
    "bound_write_map_equation": "each_binding_source_key_digest_maps_to_its_checkpoint_after_digest",
    "actual_result_checkpoint_map_must_equal_old_map_overlaid_by_bound_write_map": true
  },
  "fault_points": [
    "before:prepare_and_fsync",
    "after:prepare_and_fsync",
    "before:create_and_verify_signed_commit",
    "after:create_and_verify_signed_commit",
    "before:record_commit_created",
    "after:record_commit_created",
    "before:publish_and_verify_immutable_view",
    "after:publish_and_verify_immutable_view",
    "before:record_view_published",
    "after:record_view_published",
    "before:compare_and_swap_ref",
    "after:compare_and_swap_ref",
    "before:record_ref_updated",
    "after:record_ref_updated",
    "before:publish_transaction_receipt",
    "after:publish_transaction_receipt",
    "before:record_complete",
    "after:record_complete"
  ],
  "recovery": {
    "journal_states": [
      "ABSENT",
      "PREPARED",
      "COMMIT_CREATED",
      "VIEW_PUBLISHED",
      "REF_UPDATED",
      "COMPLETE",
      "CORRUPT",
      "TORN",
      "MULTIPLE",
      "UNKNOWN"
    ],
    "transaction_kinds": ["none", "genesis", "non-genesis"],
    "ref_relations": ["old", "new", "other", "uninitialized"],
    "authority_states": [
      "valid-current",
      "expected-absent-genesis",
      "confirmed-uninitialized",
      "invalid"
    ],
    "binding_states": [
      "not-applicable",
      "prepared-intent-valid",
      "manifest-matching",
      "mismatch"
    ],
    "view_states": ["matching", "stale", "missing", "invalid"],
    "receipt_states": ["not-applicable", "matching", "missing", "invalid"],
    "classification": {
      "genesis_ref_absent_with_active_journal": "old",
      "confirmed_clean_install_without_active_journal": "uninitialized",
      "deleted_ref_after_prior_initialization": "invalid",
      "prepared_binding": "recompute_prepared_intent_digest_without_candidate_manifest",
      "commit_or_later_binding": "candidate_signed_manifest_matches_journal_intent"
    },
    "view_actions": {
      "matching": "PIN_MATCHING",
      "stale": "MATERIALIZE_CURRENT",
      "missing": "MATERIALIZE_CURRENT",
      "invalid": "QUARANTINE_AND_MATERIALIZE_CURRENT"
    },
    "receipt_actions": {
      "matching": "KEEP_MATCHING",
      "missing": "REGENERATE_FROM_VERIFIED_MANIFEST_AND_VIEW",
      "invalid": "QUARANTINE_AND_REGENERATE_FROM_VERIFIED_MANIFEST_AND_VIEW"
    },
    "receipt_repair_preconditions": [
      "current_ref_authority_valid",
      "signed_manifest_binding_valid",
      "current_immutable_view_verified_or_rebuilt"
    ],
    "receipt_repair_order": "after_view_verification_before_reader_release",
    "receipt_repair_ref_action": "NONE",
    "complete_journal_receipt_digest_must_equal_regenerated_digest": true,
    "complete_journal_receipt_digest_mismatch": "BINDING_MISMATCH_FAIL_CLOSED",
    "view_published_ref_updated_and_absent_repair_require_no_journal_receipt_digest": true,
    "outcome_defaults": {"receipt_policy": "none", "journal_action": "NONE"},
    "journal_action_programs": {
      "ARCHIVE_ABORT_AND_DELETE_ACTIVE": [
        "write_and_fsync_immutable_abort_audit",
        "delete_active_journal_and_fsync_parent"
      ],
      "ROLL_FORWARD_TO_COMPLETE_AND_DELETE_ACTIVE": {
        "VIEW_PUBLISHED": [
          "record_and_fsync_REF_UPDATED",
          "ensure_transaction_receipt",
          "record_and_fsync_COMPLETE",
          "delete_active_journal_and_fsync_parent"
        ],
        "REF_UPDATED": [
          "ensure_transaction_receipt",
          "record_and_fsync_COMPLETE",
          "delete_active_journal_and_fsync_parent"
        ]
      },
      "VERIFY_RECEIPT_AND_DELETE_ACTIVE": [
        "verify_or_repair_transaction_receipt",
        "delete_active_journal_and_fsync_parent"
      ]
    },
    "reader_release_after_journal_action_complete": true,
    "ordered_rules": [
      {
        "id": "invalid-journal",
        "when": {
          "journal_state": ["CORRUPT", "TORN", "MULTIPLE", "UNKNOWN"]
        },
        "outcome": {
          "decision": "JOURNAL_INVALID_FAIL_CLOSED",
          "ref_action": "NONE",
          "view_policy": "none",
          "reader": "DENY"
        }
      },
      {
        "id": "other-ref",
        "when": {"ref_relation": ["other"]},
        "outcome": {
          "decision": "REF_CONFLICT_FAIL_CLOSED",
          "ref_action": "NONE",
          "view_policy": "none",
          "reader": "DENY"
        }
      },
      {
        "id": "explicit-binding-mismatch",
        "when": {"binding_state": ["mismatch"]},
        "outcome": {
          "decision": "BINDING_MISMATCH_FAIL_CLOSED",
          "ref_action": "NONE",
          "view_policy": "none",
          "reader": "DENY"
        }
      },
      {
        "id": "invalid-authority",
        "when": {"authority_state": ["invalid"]},
        "outcome": {
          "decision": "INVALID_AUTHORITY_FAIL_CLOSED",
          "ref_action": "NONE",
          "view_policy": "none",
          "reader": "DENY"
        }
      },
      {
        "id": "absent-valid-current",
        "when": {
          "journal_state": ["ABSENT"],
          "transaction_kind": ["none"],
          "ref_relation": ["new"],
          "authority_state": ["valid-current"],
          "binding_state": ["not-applicable"],
          "receipt_state": ["matching", "missing", "invalid"]
        },
        "outcome": {
          "decision": "NOOP_COMPLETE",
          "ref_action": "NONE",
          "view_policy": "ensure-current",
          "receipt_policy": "ensure-current",
          "reader": "ALLOW_AFTER_PIN"
        }
      },
      {
        "id": "absent-confirmed-uninitialized",
        "when": {
          "journal_state": ["ABSENT"],
          "transaction_kind": ["none"],
          "ref_relation": ["uninitialized"],
          "authority_state": ["confirmed-uninitialized"],
          "binding_state": ["not-applicable"],
          "receipt_state": ["not-applicable"]
        },
        "outcome": {
          "decision": "NOOP_UNINITIALIZED",
          "ref_action": "NONE",
          "view_policy": "none",
          "reader": "NOT_INITIALIZED"
        }
      },
      {
        "id": "prepared-old-wrong-binding",
        "when": {
          "journal_state": ["PREPARED"],
          "ref_relation": ["old"],
          "binding_state": ["not-applicable", "manifest-matching"]
        },
        "outcome": {
          "decision": "BINDING_MISMATCH_FAIL_CLOSED",
          "ref_action": "NONE",
          "view_policy": "none",
          "reader": "DENY"
        }
      },
      {
        "id": "candidate-old-wrong-binding",
        "when": {
          "journal_state": ["COMMIT_CREATED", "VIEW_PUBLISHED"],
          "ref_relation": ["old"],
          "binding_state": ["not-applicable", "prepared-intent-valid"]
        },
        "outcome": {
          "decision": "BINDING_MISMATCH_FAIL_CLOSED",
          "ref_action": "NONE",
          "view_policy": "none",
          "reader": "DENY"
        }
      },
      {
        "id": "normal-prepared-abort",
        "when": {
          "journal_state": ["PREPARED"],
          "transaction_kind": ["non-genesis"],
          "ref_relation": ["old"],
          "authority_state": ["valid-current"],
          "binding_state": ["prepared-intent-valid"],
          "receipt_state": ["not-applicable"]
        },
        "outcome": {
          "decision": "ABORT_KEEP_OLD",
          "ref_action": "NONE",
          "view_policy": "ensure-current",
          "journal_action": "ARCHIVE_ABORT_AND_DELETE_ACTIVE",
          "reader": "ALLOW_AFTER_PIN"
        }
      },
      {
        "id": "normal-candidate-abort",
        "when": {
          "journal_state": ["COMMIT_CREATED", "VIEW_PUBLISHED"],
          "transaction_kind": ["non-genesis"],
          "ref_relation": ["old"],
          "authority_state": ["valid-current"],
          "binding_state": ["manifest-matching"],
          "receipt_state": ["not-applicable"]
        },
        "outcome": {
          "decision": "ABORT_KEEP_OLD",
          "ref_action": "NONE",
          "view_policy": "ensure-current",
          "journal_action": "ARCHIVE_ABORT_AND_DELETE_ACTIVE",
          "reader": "ALLOW_AFTER_PIN"
        }
      },
      {
        "id": "genesis-prepared-abort",
        "when": {
          "journal_state": ["PREPARED"],
          "transaction_kind": ["genesis"],
          "ref_relation": ["old"],
          "authority_state": ["expected-absent-genesis"],
          "binding_state": ["prepared-intent-valid"],
          "receipt_state": ["not-applicable"]
        },
        "outcome": {
          "decision": "ABORT_KEEP_UNINITIALIZED",
          "ref_action": "NONE",
          "view_policy": "none",
          "journal_action": "ARCHIVE_ABORT_AND_DELETE_ACTIVE",
          "reader": "NOT_INITIALIZED"
        }
      },
      {
        "id": "genesis-candidate-abort",
        "when": {
          "journal_state": ["COMMIT_CREATED", "VIEW_PUBLISHED"],
          "transaction_kind": ["genesis"],
          "ref_relation": ["old"],
          "authority_state": ["expected-absent-genesis"],
          "binding_state": ["manifest-matching"],
          "receipt_state": ["not-applicable"]
        },
        "outcome": {
          "decision": "ABORT_KEEP_UNINITIALIZED",
          "ref_action": "NONE",
          "view_policy": "none",
          "journal_action": "ARCHIVE_ABORT_AND_DELETE_ACTIVE",
          "reader": "NOT_INITIALIZED"
        }
      },
      {
        "id": "ref-new-before-view-journal",
        "when": {
          "journal_state": ["PREPARED", "COMMIT_CREATED"],
          "ref_relation": ["new"]
        },
        "outcome": {
          "decision": "UNREACHABLE_PREFIX_FAIL_CLOSED",
          "ref_action": "NONE",
          "view_policy": "none",
          "reader": "DENY"
        }
      },
      {
        "id": "rollback-after-authority-switch",
        "when": {
          "journal_state": ["REF_UPDATED", "COMPLETE"],
          "ref_relation": ["old"]
        },
        "outcome": {
          "decision": "ROLLBACK_FAIL_CLOSED",
          "ref_action": "NONE",
          "view_policy": "none",
          "reader": "DENY"
        }
      },
      {
        "id": "missing-active-ref",
        "when": {"ref_relation": ["uninitialized"]},
        "outcome": {
          "decision": "REF_MISSING_FAIL_CLOSED",
          "ref_action": "NONE",
          "view_policy": "none",
          "reader": "DENY"
        }
      },
      {
        "id": "new-authority-roll-forward",
        "when": {
          "journal_state": ["VIEW_PUBLISHED", "REF_UPDATED"],
          "transaction_kind": ["genesis", "non-genesis"],
          "ref_relation": ["new"],
          "authority_state": ["valid-current"],
          "binding_state": ["manifest-matching"],
          "receipt_state": ["matching", "missing", "invalid"]
        },
        "outcome": {
          "decision": "ROLL_FORWARD_NEW",
          "ref_action": "NONE",
          "view_policy": "ensure-current",
          "receipt_policy": "ensure-current",
          "journal_action": "ROLL_FORWARD_TO_COMPLETE_AND_DELETE_ACTIVE",
          "reader": "ALLOW_AFTER_PIN"
        }
      },
      {
        "id": "complete-authority-noop",
        "when": {
          "journal_state": ["COMPLETE"],
          "transaction_kind": ["genesis", "non-genesis"],
          "ref_relation": ["new"],
          "authority_state": ["valid-current"],
          "binding_state": ["manifest-matching"],
          "receipt_state": ["matching", "missing", "invalid"]
        },
        "outcome": {
          "decision": "NOOP_COMPLETE",
          "ref_action": "NONE",
          "view_policy": "ensure-current",
          "receipt_policy": "ensure-current",
          "journal_action": "VERIFY_RECEIPT_AND_DELETE_ACTIVE",
          "reader": "ALLOW_AFTER_PIN"
        }
      }
    ],
    "default_outcome": {
      "decision": "INVALID_COMBINATION_FAIL_CLOSED",
      "ref_action": "NONE",
      "view_policy": "none",
      "reader": "DENY"
    }
  },
  "transaction_receipt": {
    "schema": "watari.transaction-receipt/v1",
    "unknown_fields": "reject",
    "exact_fields": [
      "receipt_schema",
      "state_id",
      "transaction_id",
      "transaction_kind",
      "canonical_ref",
      "expected_old_oid",
      "new_oid",
      "prepared_intent_digest",
      "authorization_policy_revision",
      "authorization_policy_digest",
      "result_policy_revision",
      "result_policy_digest",
      "view_receipt_digest",
      "status"
    ],
    "status_must_be_complete": true,
    "all_fields_match_verified_manifest_journal_and_view_receipt": true,
    "deterministic_derivation_sources": {
      "signed_transaction_manifest": [
        "state_id",
        "transaction_id",
        "transaction_kind",
        "canonical_ref",
        "expected_old_oid",
        "prepared_intent_digest",
        "authorization_policy_revision",
        "authorization_policy_digest",
        "result_policy_revision",
        "result_policy_digest"
      ],
      "verified_commit_object_identity": ["new_oid"],
      "typed_view_receipt": ["view_receipt_digest"],
      "schema_constant": ["receipt_schema", "status"]
    },
    "journal_required_for_regeneration": false,
    "digest_domain": "transaction-receipt/v1",
    "digest_prefix": "watari-transaction-receipt-v1:",
    "authoritative": false,
    "missing": "regenerate_only_from_verified_manifest_and_view",
    "invalid": "quarantine_and_regenerate_only_from_verified_manifest_and_view",
    "regeneration_never_changes_ref": true,
    "test_vector": {
      "receipt": {
        "receipt_schema": "watari.transaction-receipt/v1",
        "state_id": "state-1",
        "transaction_id": "tx-1",
        "transaction_kind": "ordinary",
        "canonical_ref": "refs/watari/current",
        "expected_old_oid": "old-oid",
        "new_oid": "new-oid",
        "prepared_intent_digest": "watari-transaction-intent-v1:cdd772a07de07feba3d09d1dcd9fc7c338b02bb44186494f6b11224183b4cf46",
        "authorization_policy_revision": "policy-1",
        "authorization_policy_digest": "watari-policy-v1:1111111111111111111111111111111111111111111111111111111111111111",
        "result_policy_revision": "policy-1",
        "result_policy_digest": "watari-policy-v1:1111111111111111111111111111111111111111111111111111111111111111",
        "view_receipt_digest": "watari-view-receipt-v1:8192a6b914ee1291f09519fc32b3c333f5969243043e8ca20da3731d4540eabe",
        "status": "complete"
      },
      "digest": "watari-transaction-receipt-v1:35c8c1c66d98a7d603560d2e18e52768b75a7dd51618b004d936459ec0c29427"
    }
  },
  "journal": {
    "active_journal_max": 1,
    "absent_is_recovery_input_not_state": true,
    "historical_receipts_never_override_ref_or_journal": true,
    "owner_private": true,
    "same_local_filesystem": true,
    "reject_symlink": true,
    "atomic_replace": true,
    "fsync_file_and_parent": true,
    "monotonic_states": true,
    "secret_free": true,
    "fields_are_exactly_required_list": true,
    "unknown_fields": "reject",
    "journal_intent_mirror_fields": {
      "transaction_kind": "transaction_kind",
      "state_id": "state_id",
      "transaction_id": "transaction_id",
      "canonical_ref": "canonical_ref",
      "expected_old_oid": "expected_old_oid",
      "authorization_policy_revision": "authorization_policy_revision",
      "authorization_policy_digest": "authorization_policy_digest",
      "result_policy_revision": "result_policy_revision",
      "result_policy_digest": "result_policy_digest"
    },
    "journal_intent_mirrors_must_equal": true,
    "prepared_intent_digest_must_recompute": true,
    "mirror_mismatch": "BINDING_MISMATCH_FAIL_CLOSED",
    "state_schemas": {
      "PREPARED": {
        "required": [
          "journal_schema_version",
          "transaction_kind",
          "state_id",
          "transaction_id",
          "journal_state",
          "canonical_ref",
          "expected_old_oid",
          "authorization_policy_revision",
          "authorization_policy_digest",
          "result_policy_revision",
          "result_policy_digest",
          "prepared_intent",
          "prepared_intent_digest"
        ],
        "forbidden": [
          "new_oid",
          "verification_evidence_digest",
          "view_receipt_digest",
          "transaction_receipt_digest"
        ]
      },
      "COMMIT_CREATED": {
        "required": [
          "journal_schema_version",
          "transaction_kind",
          "state_id",
          "transaction_id",
          "journal_state",
          "canonical_ref",
          "expected_old_oid",
          "authorization_policy_revision",
          "authorization_policy_digest",
          "result_policy_revision",
          "result_policy_digest",
          "prepared_intent",
          "prepared_intent_digest",
          "new_oid",
          "verification_evidence_digest"
        ],
        "forbidden": ["view_receipt_digest", "transaction_receipt_digest"]
      },
      "VIEW_PUBLISHED": {
        "required": [
          "journal_schema_version",
          "transaction_kind",
          "state_id",
          "transaction_id",
          "journal_state",
          "canonical_ref",
          "expected_old_oid",
          "authorization_policy_revision",
          "authorization_policy_digest",
          "result_policy_revision",
          "result_policy_digest",
          "prepared_intent",
          "prepared_intent_digest",
          "new_oid",
          "verification_evidence_digest",
          "view_schema",
          "view_receipt_digest"
        ],
        "forbidden": ["transaction_receipt_digest"]
      },
      "REF_UPDATED": {
        "required": [
          "journal_schema_version",
          "transaction_kind",
          "state_id",
          "transaction_id",
          "journal_state",
          "canonical_ref",
          "expected_old_oid",
          "authorization_policy_revision",
          "authorization_policy_digest",
          "result_policy_revision",
          "result_policy_digest",
          "prepared_intent",
          "prepared_intent_digest",
          "new_oid",
          "verification_evidence_digest",
          "view_schema",
          "view_receipt_digest"
        ],
        "forbidden": ["transaction_receipt_digest"]
      },
      "COMPLETE": {
        "required": [
          "journal_schema_version",
          "transaction_kind",
          "state_id",
          "transaction_id",
          "journal_state",
          "canonical_ref",
          "expected_old_oid",
          "authorization_policy_revision",
          "authorization_policy_digest",
          "result_policy_revision",
          "result_policy_digest",
          "prepared_intent",
          "prepared_intent_digest",
          "new_oid",
          "verification_evidence_digest",
          "view_schema",
          "view_receipt_digest",
          "transaction_receipt_digest"
        ],
        "forbidden": []
      }
    }
  },
  "materialization": {
    "source": "verified_commit_tree",
    "scope": "time_invariant_canonical_materialization_only",
    "time_policy_or_freshness_dependent_outputs": "excluded_to_noncanonical_cache",
    "noncanonical_cache_key": [
      "commit_oid",
      "policy_digest",
      "evaluation_time_digest",
      "cache_schema"
    ],
    "noncanonical_cache_may_never_satisfy_oid_view_validation": true,
    "layout": "immutable_commit_oid_directories",
    "path_template": "views/<view-schema>/<commit-oid>",
    "install": "same_filesystem_rename_temp_to_absent_oid_path",
    "never_replace_existing_oid_directory": true,
    "plain_nonempty_directory_replace": false,
    "fsync_all_files_directories_and_parent": true,
    "receipt_fields": [
      "receipt_schema",
      "view_schema",
      "source_commit_oid",
      "canonical_tree_digest",
      "materializer_digest",
      "materialized_view_digest"
    ],
    "receipt_unknown_fields": "reject",
    "view_receipt_digest_contract": {
      "canonicalization": "D003-canonical-json",
      "digest_domain": "view-receipt/v1",
      "digest_prefix": "watari-view-receipt-v1:",
      "test_vector": {
        "receipt": {
          "receipt_schema": "watari.view-receipt/v1",
          "view_schema": "watari.materialized-view/v1",
          "source_commit_oid": "oid-1",
          "canonical_tree_digest": "watari-tree-v1:1111111111111111111111111111111111111111111111111111111111111111",
          "materializer_digest": "watari-materializer-v1:2222222222222222222222222222222222222222222222222222222222222222",
          "materialized_view_digest": "watari-materialized-view-v1:b074facdac15bbab20dfcacd7b54d1759817f29e811789a8ca0024de9278a962"
        },
        "digest": "watari-view-receipt-v1:8192a6b914ee1291f09519fc32b3c333f5969243043e8ca20da3731d4540eabe"
      }
    },
    "view_digest_contract": {
      "view_schema": "watari.materialized-view/v1",
      "data_root": "data/",
      "receipt_path": "receipt.json",
      "receipt_excluded_from_digest": true,
      "source_entry_fields": ["path", "type", "mode", "content", "link_count"],
      "entry_fields": ["path", "type", "mode", "length", "content_digest"],
      "allowed_types": ["directory", "file"],
      "file_mode": "0400",
      "directory_mode": "0500",
      "file_link_count": 1,
      "symlinks_hardlinks_devices_fifos_and_sockets": "reject",
      "path": "NFC_relative_POSIX_path_beneath_data_without_dot_segments",
      "sort": "relative_path_utf8_byte_order",
      "data_root_directory_required": true,
      "every_parent_path_present_and_directory": true,
      "entry_paths_equal_complete_owner_private_lstat_walk": true,
      "secure_walk_does_not_follow_symlinks": true,
      "file_content_digest_domain": "view-file/v1",
      "file_content_digest_prefix": "watari-view-file-v1:",
      "manifest_canonicalization": "D003-canonical-json",
      "digest_domain": "materialized-view/v1",
      "digest_prefix": "watari-materialized-view-v1:",
      "test_vector": {
        "manifest": {
          "schema_version": 1,
          "view_schema": "watari.materialized-view/v1",
          "entries": [
            {
              "path": "data",
              "type": "directory",
              "mode": "0500",
              "length": 0,
              "content_digest": null
            },
            {
              "path": "data/profile.json",
              "type": "file",
              "mode": "0400",
              "length": 18,
              "content_digest": "watari-view-file-v1:a957e306e5c3d3a620a0fe4d7126be599ff2c6f4deb62344a87170a61c740efa"
            }
          ]
        },
        "digest": "watari-materialized-view-v1:b074facdac15bbab20dfcacd7b54d1759817f29e811789a8ca0024de9278a962"
      }
    },
    "authoritative": false,
    "rebuildable": true,
    "pin_survives_ref_change": true,
    "canonical_view_gc_v1": "forbidden",
    "gc_policy": {
      "may_delete_temporary_view": true,
      "may_delete_never_canonical_failed_candidate_after_audit": true,
      "may_delete_ever_canonical_view": false,
      "may_delete_pinned_view": false
    },
    "reader_protocol": {
      "read_ref_then_open_oid_view": true,
      "validate_receipt_oid_tree_materializer_and_view_digest": true,
      "recheck_ref_before_pin": true,
      "pin_for_command_lifetime": true,
      "mismatch": "retry_rebuild_or_fail_without_stale_read",
      "never_read_mutable_current_directory": true
    }
  }
}
```
<!-- transaction-model:end -->

## Transaction intent, kinds, and authorization

Every D004 v1 digest reuses D003 normalization, JCS UTF-16 key ordering, and
the typed `WATARI\x00` length frame. Raw SHA-256 of JSON text is never a D004
digest. This applies equally to intent, tree diff, conflicts, checkpoint item
sets, decisions, bindings, views, and receipts.
The machine model carries literal golden values for every D004 digest family
used by tree-diff, resolution, checkpoint, dream, migration, and sync binding.
Tests compare the independently canonicalized fixture to those literals, so a
domain, prefix, framing, or normalization change cannot pass by comparing one
mutable helper to itself.

`PREPARED` stores the full closed-schema intent plus its typed digest. The
digest uses D003 canonical JSON and D003's exact
`WATARI\x00 || domain || lengths || parts` frame with domain
`transaction-intent/v1`. The signed transaction manifest copies that digest
directly. It cannot contain its own Git OID, because that would be
self-referential. From `COMMIT_CREATED` onward, the journal binds the observed
OID and verification-evidence digest in addition to the same intent.

Every field duplicated between intent, journal, and signed manifest must be
byte-for-byte equal. The verifier derives the actual changed-class map and
tree-diff digest from the candidate tree, then requires the intent's sorted
`{class, digest}` entries to equal that map. Keeping each pair in one entry
prevents class/digest permutation while still permitting two classes to have
the same digest value.
The transaction manifest is an atomic member of the same Git commit but is not
in that changed-class map: including its own bytes would create a digest
self-reference. Its integrity instead comes from the signed Git tree and commit
object. The changed-class map has the closed scope listed by the machine model;
an unknown class or `transaction_manifest` is rejected.
Canonical input digests likewise equal the exact verified parent and external
input set. A valid signature over a manifest that describes different bytes is
therefore still rejected.

Manifest validation is conjunctive, not a collection of optional helpers. In
one verifier pass, ordered parent OID/state-digest pairs come from verified
parents; authorization comes from the trusted anchor, verified signer, and
recomputed diff capabilities; logical schema versions come from candidate
objects; and every checkpoint, migration, sync-certificate, and resolution
digest/count is recomputed from its actual candidate object set. Transaction
kind presence rules are then checked against those same actual objects.

The six transaction kinds have exact parent, anchor, and binding rules. Unknown
kinds and unknown fields are rejected. Genesis has no parent, a null expected
old OID, an externally pinned owner anchor, and a CAS expecting an absent ref.
A sync merge has at least two ordered, unique parents and a certificate.
Dream and migration bindings are legal only for their respective kinds.
Policy changes are legal only in `policy_transition`.

The verifier derives required capabilities from the actual tree diff. Local
memory, correction, tombstone, profile, checkpoint, dream, state-policy,
secondary-parent, conflict-resolution, and migration changes map to the exact
capabilities in the model. Declared capabilities must equal the recomputed set;
every member must be granted by the trusted old policy or genesis anchor.
Extra declarations, omitted capabilities, unknown diff fields, negative counts,
and no-op commits are rejected.

Outside `sync_merge`, immutable history also has an exact equation. Genesis has
only authorized additions and no old set. Ordinary, dream, and migration
transactions produce the expected-old exact sets union authorized additions.
A policy transition leaves every immutable set unchanged. Adding a replacement
while dropping an old event never satisfies these equations.

## Lossless merge and D003 event graph

`sync_merge` is a pure merge. Candidate additions must be empty; a user write
after merging is a new transaction. For canonical event variants, profile
events, and dream manifests, the result is the lossless union of all verified
parents. Every parent and result root/count is certificate-bound and
recomputed. Same event ID with different envelopes preserves every variant and
creates active quarantine. Profile and checkpoint conflicts bind the exact
variants, outcome, selected variant or null, strategy, old policy revision and digest,
`conflict.resolve` capability, and decision digest. Last-writer-wins and
checkpoint max merge are forbidden.

Resolution keys are unique `(class, conflict_key)` pairs. Their set is exactly
the recomputed conflict-key set: no missing, extra, or duplicate decisions are
accepted. Variant digests are sorted and unique; every decision digest and the
typed decision-set digest/count are recomputed. The same transaction-manifest
binding applies when an ordinary transaction uses `conflict.resolve`, not only
when a sync certificate exists. Recomputing a decision under a secondary or
candidate policy does not authorize it; both revision and digest must equal the
expected-old policy.
For every transaction kind, not only `sync_merge`, a same-event-ID conflict
must preserve all variants with a `quarantine` outcome. An authorized `select`
decision is still invalid for this conflict class.

The D003 supersedes graph is revalidated over all verified parent variants
union transaction additions, not only the first parent. This catches a target
or cycle spanning devices. Parent events retain authorization from their
verified origin trust chain. New local events and conflict decisions require
the local expected-old policy; a secondary parent's policy never becomes local
authority. Missing, ambiguous, or quarantined targets and cycles are rejected.
Parallel successors remain preserved in active conflict quarantine and are
never auto-selected.

## Checkpoint and dream binding

A changed dream checkpoint has one closed-schema binding. Its source key
contains device, connector instance, lineage, and nullable coordinator epoch;
its completion key contains those identities plus local date and policy
revision. The verifier recomputes scan, decision, accepted-event, unresolved,
and quarantine sets from actual candidate objects rather than trusting counts.
Scan keys are normalized through D003 first and sorted by their canonical item
bytes; canonically equivalent NFC/NFD spellings are duplicates, not two items.
All scanned items have exactly one accept, reject, or quarantine decision.
Every accepted variant equals one candidate dream event whose run ID, source,
and model policy match the binding. Accepted, candidate, and result event
variants are sorted unique sets; two scan items cannot inflate counts by
accepting the same canonical variant twice.

For each source, the candidate result event set must equal the expected-old
source event set union the accepted variants. The binding digest is recomputed
from that result; recomputing both an attacker-chosen result and its digest does
not satisfy the union equation. Across the whole transaction, the global dream
event additions equal exactly the union of bound candidate dream events.
Every dream binding has exactly one closed-schema dream-run manifest with the
same run ID, and every such manifest has exactly one binding. The manifest
recomputes the full checkpoint-binding digest and mirrors the transaction,
source, accepted-set, model-policy, and completion status fields; missing,
extra, duplicate, or unbound manifests are rejected.

Transaction ID, source key and snapshot, model policy, completion date, and
completion policy are compared with independently verified transaction inputs;
changing the binding and candidate events together cannot change those inputs.
Each binding receives a typed digest, and the signed manifest carries the exact
recomputed binding-set digest and count.

The transaction verifier independently derives a bound write map whose key is
the typed digest of each binding's source key and whose value is that binding's
`checkpoint_after_digest`. The actual candidate checkpoint map must equal the
complete expected-old map overlaid by exactly these key/value pairs. Matching
only the set of source keys is insufficient.

A complete scan with zero accepted events is valid and still has an empty
accepted-set digest. A partial run, replayed run ID, mismatched old/proposed
checkpoint, unresolved candidate, quarantine, stale coordinator epoch,
duplicate checkpoint write for the same source key, or dream profile change
cannot advance the checkpoint. Migration imports use their separate typed
binding and cannot pretend to be dream runs.

A migration binding independently matches the expected-old checkpoint, reviewed
checkpoint proposal, actual migration snapshot, approved review artifact, and
exact imported event-variant set/count. Its status must be complete. Duplicate
source keys are rejected across all checkpoint bindings.

The checkpoint, accepted events, dream manifest, and transaction manifest are
committed in the same tree. Raw connector data, secrets, scratch, journal
files, views, and caches never enter the canonical commit.

## State and durability order

`PREPARED` means the intent and journal are durable; no candidate OID exists.
`COMMIT_CREATED` means all candidate objects and verification evidence are
durable but non-authoritative. `VIEW_PUBLISHED` means the candidate OID's view
was fsynced and atomically renamed into its absent OID path. The view is
published before the ref, but readers cannot discover it through the old ref.
`REF_UPDATED` means the exact CAS succeeded. `COMPLETE` means the immutable
transaction receipt and final journal record are durable.

Every journal transition writes the complete state-specific document to a
same-filesystem temporary file, fsyncs it, atomically replaces the journal, and
fsyncs the parent directory. Unknown or future-state fields are forbidden.
After `COMPLETE`, the active journal may be deleted and its parent fsynced;
`ABSENT` is therefore a normal recovery input rather than an active state.

## Recovery

Recovery acquires the writer lock and classifies the actual journal, kind, ref,
authority, intent/manifest binding, view, and transaction receipt. The ordered rules are the entire
guard and outcome program. The contract interpreter reads only those rules;
the test oracle is separately hard-coded and exhaustively compares all 30,720
axis combinations.

A clean install with no active journal and independent owner-only evidence that
no genesis was ever accepted is `uninitialized`. During an active genesis,
ref absence is the expected `old` relation, not a missing-ref error.
`PREPARED` validates the stored intent directly because no candidate manifest
exists yet. `COMMIT_CREATED` and later require the signed candidate manifest
to carry the same intent digest.

Only `VIEW_PUBLISHED + new` is the legitimate CAS-success/journal-lag window.
`PREPARED + new` and `COMMIT_CREATED + new` are unreachable under the
durable order and fail closed. `REF_UPDATED` or `COMPLETE` with the old ref
is rollback evidence. Unknown journal state fails closed. Torn, corrupt, or
multiple journals, unrelated refs, invalid authority, or binding mismatch also
fail without changing any ref. Recovery has no automatic rollback.

A matching transaction receipt is kept. A missing receipt is regenerated, and
an invalid receipt is quarantined then regenerated, only after the signed
manifest and current immutable view have been independently verified. Receipt
fields derive only from that manifest, the verified commit OID, the typed view
receipt, and schema constants; journal deletion loses no required input. If a
`COMPLETE` journal still exists, its recorded receipt digest must equal the
regenerated digest or recovery fails closed as a binding mismatch. Receipt
repair is a derived-evidence operation and never changes the canonical ref.

Every successful active-journal outcome also names a durable journal program.
An abort first writes an immutable abort audit, then deletes and fsyncs the
active journal. Roll-forward resumes monotonically from `VIEW_PUBLISHED` or
`REF_UPDATED`, ensures the receipt, records `COMPLETE`, and deletes the active
journal. A pre-existing `COMPLETE` journal is deleted only after receipt
verification or repair. Readers are released only after the selected program
reaches complete-old, complete-new, or confirmed-uninitialized terminal state.

## Immutable views and reader lifetime

Views live at `views/<view-schema>/<commit-oid>/`. Files and directories are
fsynced before a same-filesystem rename into an absent OID path. Materialized
data is below `data/`; the fixed top-level `receipt.json` is excluded to avoid a
self-reference. The digest covers a D003-canonical manifest of every NFC POSIX
relative path in UTF-8 byte order, its file type, fixed mode, length, and typed
content digest. Symlinks, hard links, devices, FIFOs, and sockets are rejected.
A receipt binds the source OID, canonical tree, materializer, and this exact
manifest digest. A mismatched output digest is quarantined and rebuilt; OID
equality alone is insufficient.

The OID-keyed view contains only time-invariant canonical materialization.
Freshness, heat, policy evaluation, ranking, and other time-dependent derived
outputs live in a noncanonical cache keyed by commit OID, policy digest,
evaluation-time digest, and cache schema. Such a cache can never satisfy the
OID-view receipt check or become authority.

The reader pins one verified OID/view for the command lifetime. A ref change
after pin does not change that command's snapshot. Canonical views are never
deleted in v1, so a concurrent GC cannot invalidate the pin. GC may remove
known temporary views and, after audit, candidates proven never canonical, but
never a pinned or ever-canonical view.

## Fault and remote semantics

The fault model kills the writer immediately before and after every operation.
Both ordinary and genesis prefixes are fixed independently of the machine
effects and must recover to complete old, complete new, or confirmed
uninitialized state. No successful prefix updates a ref during recovery.
Implementation tickets reuse the oracle for real fsync, disk-full, corrupt
object/receipt, lock, concurrent reader, and CAS-race tests.

A local transaction succeeds at `COMPLETE`. Push is a later sync operation.
A push failure is sync pending, not rollback or local transaction failure. A
remote revision can become local authority only through verification,
prepublished view, and local compare-and-swap.
