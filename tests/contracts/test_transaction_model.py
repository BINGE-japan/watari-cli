"""Executable contract for Watari's canonical transaction model."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import itertools
import json
import re
import struct
import unicodedata
import unittest
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ADR = ROOT / "docs" / "adr" / "004-transaction.md"
CANONICAL_ORACLE = ROOT / "tests" / "unit" / "test_canonical_vectors.py"
_CANONICAL_SPEC = importlib.util.spec_from_file_location(
    "watari_d003_canonical_oracle", CANONICAL_ORACLE
)
if _CANONICAL_SPEC is None or _CANONICAL_SPEC.loader is None:
    raise RuntimeError("cannot load the D003 canonical oracle")
_CANONICAL_MODULE = importlib.util.module_from_spec(_CANONICAL_SPEC)
_CANONICAL_SPEC.loader.exec_module(_CANONICAL_MODULE)
d003_canonical_bytes = _CANONICAL_MODULE.canonical_bytes
MODEL_RE = re.compile(
    r"<!-- transaction-model:start -->\s*```json\s*(.*?)\s*```\s*<!-- transaction-model:end -->",
    re.DOTALL,
)

STATES = [
    "PREPARED",
    "COMMIT_CREATED",
    "VIEW_PUBLISHED",
    "REF_UPDATED",
    "COMPLETE",
]
OPERATIONS = [
    "prepare_and_fsync",
    "create_and_verify_signed_commit",
    "record_commit_created",
    "publish_and_verify_immutable_view",
    "record_view_published",
    "compare_and_swap_ref",
    "record_ref_updated",
    "publish_transaction_receipt",
    "record_complete",
]
TRANSACTION_KINDS = [
    "genesis",
    "ordinary",
    "dream_apply",
    "sync_merge",
    "migration_import",
    "policy_transition",
]
KIND_MATRIX = {
    "genesis": {
        "expected_old": "null",
        "parents": "none",
        "authorization": "genesis_anchor",
        "sync_certificate": "forbidden",
        "dream_bindings": "forbidden",
        "migration_bindings": "forbidden",
        "result_policy": "initial",
    },
    "ordinary": {
        "expected_old": "required",
        "parents": "expected_old_only",
        "authorization": "expected_old_policy",
        "sync_certificate": "forbidden",
        "dream_bindings": "forbidden",
        "migration_bindings": "forbidden",
        "result_policy": "unchanged",
    },
    "dream_apply": {
        "expected_old": "required",
        "parents": "expected_old_only",
        "authorization": "expected_old_policy",
        "sync_certificate": "forbidden",
        "dream_bindings": "required_nonempty",
        "migration_bindings": "forbidden",
        "result_policy": "unchanged",
    },
    "sync_merge": {
        "expected_old": "required",
        "parents": "expected_old_first_and_at_least_two",
        "authorization": "expected_old_policy",
        "sync_certificate": "required",
        "dream_bindings": "forbidden",
        "migration_bindings": "forbidden",
        "result_policy": "unchanged",
    },
    "migration_import": {
        "expected_old": "required",
        "parents": "expected_old_only",
        "authorization": "expected_old_policy",
        "sync_certificate": "forbidden",
        "dream_bindings": "forbidden",
        "migration_bindings": "required_nonempty",
        "result_policy": "unchanged",
    },
    "policy_transition": {
        "expected_old": "required",
        "parents": "expected_old_only",
        "authorization": "expected_old_policy",
        "sync_certificate": "forbidden",
        "dream_bindings": "forbidden",
        "migration_bindings": "forbidden",
        "result_policy": "changed",
    },
}
CAPABILITY_MAP = {
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
    "migration_binding_count": "migration.import",
}
DIFF_KEYS = set(CAPABILITY_MAP)
KIND_CAPABILITY_CONSTRAINTS = {
    "genesis": {
        "required": {"genesis.create", "state.configure"},
        "allowed": {"genesis.create", "state.configure"},
    },
    "ordinary": {
        "required": set(),
        "allowed": {
            "event.append",
            "event.correct",
            "event.tombstone",
            "profile.write",
            "state.configure",
            "conflict.resolve",
        },
    },
    "dream_apply": {
        "required": {"dream.apply", "checkpoint.advance"},
        "allowed": {"event.append", "dream.apply", "checkpoint.advance"},
    },
    "sync_merge": {
        "required": {"sync.merge"},
        "allowed": {"sync.merge", "conflict.resolve"},
    },
    "migration_import": {
        "required": {"migration.import"},
        "allowed": {
            "migration.import",
            "event.append",
            "event.correct",
            "event.tombstone",
            "profile.write",
            "checkpoint.advance",
            "state.configure",
        },
    },
    "policy_transition": {
        "required": {"policy.transition"},
        "allowed": {"policy.transition", "state.configure"},
    },
}
INTENT_FIELDS = {
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
    "proposed_changes",
}
PROPOSED_CHANGE_FIELDS = {"class", "digest"}
TRANSACTION_MANIFEST_FIELDS = {
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
    "resolution_decision_count",
}
PARENT_BINDING_FIELDS = {"oid", "canonical_state_digest"}
MANIFEST_AUTHORIZATION_FIELDS = {
    "source",
    "policy_revision",
    "policy_digest",
    "signer_id",
    "declared_capabilities",
}
LOGICAL_SCHEMA_VERSION_FIELDS = {
    "event",
    "profile",
    "checkpoint",
    "dream_run_manifest",
    "transaction",
}
DIFF_DIGEST_CLASSES = {
    "canonical_events",
    "profile_events",
    "source_checkpoints",
    "dream_run_manifests",
    "state_manifest",
    "policy",
    "sync_merge_certificate",
    "checkpoint_bindings",
    "migration_bindings",
    "resolution_decisions",
}
REQUIRED_COMMIT_VALIDATIONS = {
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
    "no_unexpected_paths",
}
RECOVERY_JOURNAL_STATES = [
    "ABSENT",
    *STATES,
    "CORRUPT",
    "TORN",
    "MULTIPLE",
    "UNKNOWN",
]
INVALID_JOURNAL_STATES = {"CORRUPT", "TORN", "MULTIPLE", "UNKNOWN"}
RECOVERY_TX_KINDS = ["none", "genesis", "non-genesis"]
REF_RELATIONS = ["old", "new", "other", "uninitialized"]
AUTHORITY_STATES = [
    "valid-current",
    "expected-absent-genesis",
    "confirmed-uninitialized",
    "invalid",
]
BINDING_STATES = [
    "not-applicable",
    "prepared-intent-valid",
    "manifest-matching",
    "mismatch",
]
VIEW_STATES = ["matching", "stale", "missing", "invalid"]
RECEIPT_STATES = ["not-applicable", "matching", "missing", "invalid"]

SOURCE_KEY_FIELDS = {
    "device_id",
    "connector_instance_id",
    "source_lineage_digest",
    "coordinator_epoch",
}
COMPLETION_KEY_FIELDS = {
    "device_id",
    "connector_instance_id",
    "source_lineage_digest",
    "local_date",
    "policy_revision",
}
DREAM_BINDING_FIELDS = {
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
    "status",
}
MIGRATION_BINDING_FIELDS = {
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
    "status",
}
DECISION_WITNESS_FIELDS = {"outcome", "event_variant"}
DREAM_EVENT_WITNESS_FIELDS = {
    "event_variant",
    "dream_run_id",
    "source_key",
    "model_policy_digest",
}
DREAM_RUN_MANIFEST_FIELDS = {
    "manifest_schema",
    "transaction_id",
    "dream_run_id",
    "source_key",
    "checkpoint_binding_digest",
    "accepted_event_variant_set_digest",
    "accepted_event_count",
    "model_policy_digest",
    "status",
}
VIEW_RECEIPT_FIELDS = {
    "receipt_schema",
    "view_schema",
    "source_commit_oid",
    "canonical_tree_digest",
    "materializer_digest",
    "materialized_view_digest",
}
TRANSACTION_RECEIPT_FIELDS = {
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
    "status",
}
JOURNAL_INTENT_MIRRORS = {
    "transaction_kind": "transaction_kind",
    "state_id": "state_id",
    "transaction_id": "transaction_id",
    "canonical_ref": "canonical_ref",
    "expected_old_oid": "expected_old_oid",
    "authorization_policy_revision": "authorization_policy_revision",
    "authorization_policy_digest": "authorization_policy_digest",
    "result_policy_revision": "result_policy_revision",
    "result_policy_digest": "result_policy_digest",
}
VIEW_ENTRY_FIELDS = {"path", "type", "mode", "length", "content_digest"}
RESOLUTION_FIELDS = {
    "class",
    "conflict_key",
    "variant_digests",
    "outcome",
    "selected_variant_digest",
    "strategy",
    "authorization_policy_revision",
    "authorization_policy_digest",
    "required_capability",
    "decision_digest",
}


def parse_model() -> tuple[str, dict[str, Any]]:
    text = ADR.read_text(encoding="utf-8")
    match = MODEL_RE.search(text)
    if match is None:
        raise AssertionError("machine-readable transaction model is missing")

    def reject_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise AssertionError(f"duplicate transaction model member: {key}")
            output[key] = value
        return output

    return text, json.loads(
        match.group(1), object_pairs_hook=reject_duplicate_members
    )


def canonical_ascii_json(value: Any) -> bytes:
    def json_value(item: Any) -> Any:
        if isinstance(item, tuple):
            return [json_value(value) for value in item]
        if isinstance(item, list):
            return [json_value(value) for value in item]
        if isinstance(item, dict):
            return {key: json_value(value) for key, value in item.items()}
        return item

    return d003_canonical_bytes(json_value(value))


def framed_digest(domain: str, *parts: bytes) -> bytes:
    framed = b"WATARI\x00" + domain.encode("ascii") + b"\x00"
    for part in parts:
        framed += struct.pack(">Q", len(part)) + part
    return hashlib.sha256(framed).digest()


def typed_json_digest(domain: str, prefix: str, value: Any) -> str:
    return prefix + framed_digest(domain, canonical_ascii_json(value)).hex()


def intent_digest(intent: dict[str, Any]) -> str:
    if set(intent) != INTENT_FIELDS:
        raise ValueError("intent fields are not exact")
    return "watari-transaction-intent-v1:" + framed_digest(
        "transaction-intent/v1", canonical_ascii_json(intent)
    ).hex()


def intent_errors(intent: dict[str, Any]) -> set[str]:
    errors: set[str] = set()
    if not isinstance(intent, dict):
        return {"intent_fields"}
    if set(intent) != INTENT_FIELDS:
        return {"intent_fields"}
    if intent["schema_version"] != 1:
        errors.add("intent_version")
    if intent["intent_schema"] != "watari.transaction-intent/v1":
        errors.add("intent_schema")
    values = intent["canonical_input_digests"]
    if (
        not isinstance(values, list)
        or any(not isinstance(value, str) for value in values)
        or values != sorted(set(values))
    ):
        errors.add("canonical_input_digests_not_sorted_unique")
    proposed_changes = intent["proposed_changes"]
    if not isinstance(proposed_changes, list) or any(
        not isinstance(item, dict) or set(item) != PROPOSED_CHANGE_FIELDS
        for item in proposed_changes
    ):
        errors.add("proposed_change_schema")
    else:
        classes = [item["class"] for item in proposed_changes]
        if any(
            not isinstance(item["class"], str)
            or not isinstance(item["digest"], str)
            for item in proposed_changes
        ):
            errors.add("proposed_change_value_type")
        elif classes != sorted(classes) or len(classes) != len(set(classes)):
            errors.add("proposed_changes_not_sorted_unique_by_class")
    parent_oids = intent["ordered_parent_oids"]
    if (
        not isinstance(parent_oids, list)
        or any(not isinstance(oid, str) for oid in parent_oids)
        or len(parent_oids) != len(set(parent_oids))
    ):
        errors.add("duplicate_parent_oid")
    return errors


def synthetic_intent() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "intent_schema": "watari.transaction-intent/v1",
        "transaction_kind": "ordinary",
        "state_id": "state-1",
        "transaction_id": "tx-1",
        "canonical_ref": "refs/watari/current",
        "expected_old_oid": "old-oid",
        "ordered_parent_oids": ["old-oid"],
        "authorization_policy_revision": "policy-1",
        "authorization_policy_digest": "watari-policy-v1:" + "1" * 64,
        "result_policy_revision": "policy-1",
        "result_policy_digest": "watari-policy-v1:" + "1" * 64,
        "canonical_input_digests": ["watari-input-v1:" + "2" * 64],
        "proposed_changes": [
            {
                "class": "canonical_events",
                "digest": "watari-change-v1:" + "3" * 64,
            }
        ],
    }


def tree_diff_digest(changed_class_digests: dict[str, str]) -> str:
    return typed_json_digest(
        "tree-diff/v1",
        "watari-tree-diff-v1:",
        {
            "schema_version": 1,
            "changed_class_digests": changed_class_digests,
        },
    )


def candidate_binding_errors(
    intent: dict[str, Any],
    manifest: dict[str, Any],
    actual_changed_class_digests: dict[str, str],
    actual_canonical_input_digests: list[str],
) -> set[str]:
    errors: set[str] = set()
    if intent_errors(intent):
        errors.add("prepared_intent_invalid")
        return errors
    if not isinstance(manifest, dict):
        return {"transaction_manifest_fields"}
    if set(manifest) != TRANSACTION_MANIFEST_FIELDS:
        errors.add("transaction_manifest_fields")
        return errors
    if manifest["manifest_schema"] != "watari.transaction-manifest/v1":
        errors.add("transaction_manifest_schema")
    parent_bindings = manifest["ordered_parent_bindings"]
    if not isinstance(parent_bindings, list) or any(
        not isinstance(binding, dict) or set(binding) != PARENT_BINDING_FIELDS
        for binding in parent_bindings
    ):
        errors.add("parent_binding_fields")
        return errors
    if (
        not isinstance(manifest["authorization"], dict)
        or set(manifest["authorization"]) != MANIFEST_AUTHORIZATION_FIELDS
    ):
        errors.add("manifest_authorization_fields")
        return errors
    if (
        not isinstance(actual_changed_class_digests, dict)
        or any(
            not isinstance(class_name, str) or not isinstance(digest, str)
            for class_name, digest in actual_changed_class_digests.items()
        )
    ):
        return errors | {"changed_class_digest_map"}
    if not set(actual_changed_class_digests) <= DIFF_DIGEST_CLASSES:
        errors.add("changed_class_out_of_scope")
    mirrors = {
        "transaction_kind": manifest["transaction_kind"],
        "state_id": manifest["state_id"],
        "transaction_id": manifest["transaction_id"],
        "canonical_ref": manifest["canonical_ref"],
        "expected_old_oid": manifest["expected_old_oid"],
        "ordered_parent_oids": [item["oid"] for item in manifest["ordered_parent_bindings"]],
        "authorization_policy_revision": manifest["authorization"]["policy_revision"],
        "authorization_policy_digest": manifest["authorization"]["policy_digest"],
        "result_policy_revision": manifest["result_policy_revision"],
        "result_policy_digest": manifest["result_policy_digest"],
    }
    for field, value in mirrors.items():
        if value != intent[field]:
            errors.add(f"intent_manifest_mirror:{field}")
    if manifest["prepared_intent_digest"] != intent_digest(intent):
        errors.add("prepared_intent_digest")
    proposed_change_map = {
        item["class"]: item["digest"] for item in intent["proposed_changes"]
    }
    if proposed_change_map != actual_changed_class_digests:
        errors.add("proposed_changes")
    if (
        not isinstance(actual_canonical_input_digests, list)
        or any(not isinstance(digest, str) for digest in actual_canonical_input_digests)
        or intent["canonical_input_digests"]
        != sorted(set(actual_canonical_input_digests))
    ):
        errors.add("canonical_input_digests")
    if manifest["changed_class_digests"] != actual_changed_class_digests:
        errors.add("changed_class_digests")
    try:
        expected_tree_diff_digest = tree_diff_digest(actual_changed_class_digests)
    except (KeyError, TypeError, ValueError):
        errors.add("tree_diff_value")
    else:
        if manifest["tree_diff_digest"] != expected_tree_diff_digest:
            errors.add("tree_diff_digest")
    return errors


def sync_merge_certificate_digest(certificate: dict[str, Any]) -> str:
    return typed_json_digest(
        "sync-merge-certificate/v1",
        "watari-sync-merge-certificate-v1:",
        certificate,
    )


def transaction_manifest_semantic_errors(
    manifest: dict[str, Any],
    *,
    actual_parent_bindings: list[dict[str, str]],
    expected_authorization_from_anchor_and_diff: dict[str, Any],
    actual_logical_schema_versions: dict[str, int],
    actual_checkpoint_bindings: list[dict[str, Any]],
    actual_sync_merge_certificate: dict[str, Any] | None,
    actual_migration_bindings: list[dict[str, Any]],
    actual_resolution_decisions: list[dict[str, Any]],
) -> set[str]:
    if not isinstance(manifest, dict) or set(manifest) != TRANSACTION_MANIFEST_FIELDS:
        return {"transaction_manifest_fields"}
    errors: set[str] = set()
    if not isinstance(actual_parent_bindings, list) or any(
        not isinstance(binding, dict) or set(binding) != PARENT_BINDING_FIELDS
        for binding in actual_parent_bindings
    ):
        errors.add("actual_parent_binding_fields")
    elif manifest["ordered_parent_bindings"] != actual_parent_bindings:
        errors.add("ordered_parent_bindings_semantic")

    if (
        not isinstance(expected_authorization_from_anchor_and_diff, dict)
        or set(expected_authorization_from_anchor_and_diff)
        != MANIFEST_AUTHORIZATION_FIELDS
    ):
        errors.add("expected_authorization_fields")
    elif manifest["authorization"] != expected_authorization_from_anchor_and_diff:
        errors.add("authorization_semantic")
    manifest_authorization = manifest["authorization"]
    declared_capabilities = (
        manifest_authorization.get("declared_capabilities")
        if isinstance(manifest_authorization, dict)
        else None
    )
    if (
        not isinstance(declared_capabilities, list)
        or any(not isinstance(item, str) for item in declared_capabilities)
        or declared_capabilities != sorted(set(declared_capabilities))
    ):
        errors.add("authorization_capabilities_not_sorted_unique")

    if (
        not isinstance(actual_logical_schema_versions, dict)
        or set(actual_logical_schema_versions) != LOGICAL_SCHEMA_VERSION_FIELDS
        or any(
            isinstance(version, bool) or not isinstance(version, int) or version < 1
            for version in actual_logical_schema_versions.values()
        )
    ):
        errors.add("actual_logical_schema_versions")
    elif manifest["logical_schema_versions"] != actual_logical_schema_versions:
        errors.add("logical_schema_versions_semantic")

    checkpoint_schema_valid = isinstance(actual_checkpoint_bindings, list) and all(
        isinstance(binding, dict) and set(binding) == DREAM_BINDING_FIELDS
        for binding in actual_checkpoint_bindings
    )
    if not checkpoint_schema_valid:
        errors.add("actual_checkpoint_binding_schema")
    else:
        try:
            checkpoint_errors = checkpoint_binding_set_errors(
                "dream_run",
                actual_checkpoint_bindings,
                manifest["checkpoint_binding_set_digest"],
                manifest["checkpoint_binding_count"],
            )
            errors |= {f"manifest:{error}" for error in checkpoint_errors}
        except (KeyError, TypeError, ValueError):
            errors.add("actual_checkpoint_binding_value")

    migration_schema_valid = isinstance(actual_migration_bindings, list) and all(
        isinstance(binding, dict) and set(binding) == MIGRATION_BINDING_FIELDS
        for binding in actual_migration_bindings
    )
    if not migration_schema_valid:
        errors.add("actual_migration_binding_schema")
    else:
        try:
            migration_errors = checkpoint_binding_set_errors(
                "migration_import",
                actual_migration_bindings,
                manifest["migration_binding_set_digest"],
                manifest["migration_binding_count"],
            )
            errors |= {f"manifest:{error}" for error in migration_errors}
        except (KeyError, TypeError, ValueError):
            errors.add("actual_migration_binding_value")

    expected_sync_digest = (
        None
        if actual_sync_merge_certificate is None
        else sync_merge_certificate_digest(actual_sync_merge_certificate)
    )
    if manifest["sync_merge_certificate_digest"] != expected_sync_digest:
        errors.add("sync_merge_certificate_digest_semantic")
    resolution_schema_valid = isinstance(actual_resolution_decisions, list) and all(
        isinstance(decision, dict) and set(decision) == RESOLUTION_FIELDS
        for decision in actual_resolution_decisions
    )
    if not resolution_schema_valid:
        errors.add("actual_resolution_decision_schema")
    else:
        if manifest["resolution_decision_count"] != len(actual_resolution_decisions):
            errors.add("resolution_decision_count_semantic")
        try:
            expected_resolution_digest = resolution_decision_set_digest(
                actual_resolution_decisions
            )
        except (KeyError, TypeError, ValueError):
            errors.add("actual_resolution_decision_value")
        else:
            if (
                manifest["resolution_decision_set_digest"]
                != expected_resolution_digest
            ):
                errors.add("resolution_decision_set_digest_semantic")

    kind = manifest["transaction_kind"]
    if kind == "dream_apply":
        if not actual_checkpoint_bindings:
            errors.add("dream_checkpoint_bindings_required")
    elif actual_checkpoint_bindings:
        errors.add("dream_checkpoint_bindings_forbidden")
    if kind == "migration_import":
        if not actual_migration_bindings:
            errors.add("migration_bindings_required")
    elif actual_migration_bindings:
        errors.add("migration_bindings_forbidden")
    if kind == "sync_merge":
        if actual_sync_merge_certificate is None:
            errors.add("sync_merge_certificate_required")
    elif actual_sync_merge_certificate is not None:
        errors.add("sync_merge_certificate_forbidden")
    return errors


def complete_manifest_binding_errors(
    intent: dict[str, Any],
    manifest: dict[str, Any],
    actual_changed_class_digests: dict[str, str],
    actual_canonical_input_digests: list[str],
    **semantic_inputs: Any,
) -> set[str]:
    errors = candidate_binding_errors(
        intent,
        manifest,
        actual_changed_class_digests,
        actual_canonical_input_digests,
    )
    errors |= transaction_manifest_semantic_errors(manifest, **semantic_inputs)
    return errors


def synthetic_manifest(
    intent: dict[str, Any], changed_class_digests: dict[str, str]
) -> dict[str, Any]:
    return {
        "manifest_schema": "watari.transaction-manifest/v1",
        "transaction_kind": intent["transaction_kind"],
        "state_id": intent["state_id"],
        "transaction_id": intent["transaction_id"],
        "canonical_ref": intent["canonical_ref"],
        "expected_old_oid": intent["expected_old_oid"],
        "ordered_parent_bindings": [
            {"oid": oid, "canonical_state_digest": f"state:{oid}"}
            for oid in intent["ordered_parent_oids"]
        ],
        "prepared_intent_digest": intent_digest(intent),
        "authorization": {
            "source": "expected_old_commit",
            "policy_revision": intent["authorization_policy_revision"],
            "policy_digest": intent["authorization_policy_digest"],
            "signer_id": "signer-owner-1",
            "declared_capabilities": ["event.append"],
        },
        "result_policy_revision": intent["result_policy_revision"],
        "result_policy_digest": intent["result_policy_digest"],
        "logical_schema_versions": {
            "event": 1,
            "profile": 1,
            "checkpoint": 1,
            "dream_run_manifest": 1,
            "transaction": 1,
        },
        "tree_diff_digest": tree_diff_digest(changed_class_digests),
        "changed_class_digests": changed_class_digests,
        "checkpoint_binding_set_digest": checkpoint_binding_set_digest(
            "dream_run", []
        ),
        "checkpoint_binding_count": 0,
        "sync_merge_certificate_digest": None,
        "migration_binding_set_digest": checkpoint_binding_set_digest(
            "migration_import", []
        ),
        "migration_binding_count": 0,
        "resolution_decision_set_digest": resolution_decision_set_digest([]),
        "resolution_decision_count": 0,
    }


def journal_binding_errors(journal: dict[str, Any]) -> set[str]:
    errors: set[str] = set()
    intent = journal["prepared_intent"]
    if intent_errors(intent):
        errors.add("prepared_intent_invalid")
        return errors
    if journal["prepared_intent_digest"] != intent_digest(intent):
        errors.add("prepared_intent_digest")
    for journal_field, intent_field in JOURNAL_INTENT_MIRRORS.items():
        if journal[journal_field] != intent[intent_field]:
            errors.add(f"journal_intent_mirror:{journal_field}")
    return errors


IMMUTABLE_STATE_CLASSES = {
    "canonical_event_variants",
    "profile_events",
    "dream_run_manifests",
}


def non_sync_state_errors(
    kind: str,
    expected_old: dict[str, set[str]],
    authorized_additions: dict[str, set[str]],
    result: dict[str, set[str]],
) -> set[str]:
    errors: set[str] = set()
    if set(expected_old) != IMMUTABLE_STATE_CLASSES:
        return {"old_state_schema"}
    if set(authorized_additions) != IMMUTABLE_STATE_CLASSES:
        return {"addition_state_schema"}
    if set(result) != IMMUTABLE_STATE_CLASSES:
        return {"result_state_schema"}
    for class_name in IMMUTABLE_STATE_CLASSES:
        old_values = expected_old[class_name]
        additions = authorized_additions[class_name]
        if old_values & additions:
            errors.add(f"addition_not_new:{class_name}")
        if kind == "genesis":
            if old_values:
                errors.add(f"genesis_old_state:{class_name}")
            expected = additions
        elif kind in {"ordinary", "dream_apply", "migration_import"}:
            expected = old_values | additions
        elif kind == "policy_transition":
            if additions:
                errors.add(f"policy_transition_addition:{class_name}")
            expected = old_values
        else:
            return {"non_sync_kind"}
        if result[class_name] != expected:
            errors.add(f"lossless_state_equation:{class_name}")
    return errors


def checkpoint_map_errors(
    kind: str,
    expected_old: dict[str, str],
    bound_writes: dict[str, str],
    result: dict[str, str],
    binding_source_keys: set[str],
) -> set[str]:
    errors: set[str] = set()
    if set(bound_writes) != binding_source_keys:
        errors.add("checkpoint_write_binding_bijection")
    if kind == "genesis":
        if expected_old or bound_writes or result:
            errors.add("genesis_checkpoint_map_not_empty")
        return errors
    if kind in {"ordinary", "policy_transition"}:
        if bound_writes or binding_source_keys:
            errors.add("checkpoint_write_forbidden_for_kind")
        expected = expected_old
    elif kind in {"dream_apply", "migration_import"}:
        expected = {**expected_old, **bound_writes}
    else:
        return {"non_sync_checkpoint_kind"}
    if result != expected:
        errors.add("checkpoint_map_equation")
    return errors


def kind_errors(tx: dict[str, Any]) -> set[str]:
    errors: set[str] = set()
    kind = tx.get("transaction_kind")
    if kind not in KIND_MATRIX:
        return {"unknown_kind"}
    old = tx["expected_old_oid"]
    parents = tx["parent_oids"]
    if kind == "genesis":
        if old is not None or parents:
            errors.add("genesis_parent")
        if tx["authorization_basis"] != "genesis_anchor":
            errors.add("genesis_anchor")
    else:
        if not isinstance(old, str) or not old:
            errors.add("missing_old")
        if not parents or parents[0] != old:
            errors.add("old_not_first")
        if tx["authorization_basis"] != "expected_old_policy":
            errors.add("wrong_old_policy")
    if kind == "sync_merge":
        if len(parents) < 2 or tx["sync_certificate"] is None:
            errors.add("merge_certificate_required")
    elif tx["sync_certificate"] is not None:
        errors.add("merge_certificate_forbidden")
    if kind == "dream_apply":
        if not isinstance(tx["dream_bindings"], list) or not tx["dream_bindings"]:
            errors.add("dream_bindings_required")
    elif tx["dream_bindings"] is not None:
        errors.add("dream_bindings_forbidden")
    if kind == "migration_import":
        if not isinstance(tx["migration_bindings"], list) or not tx["migration_bindings"]:
            errors.add("migration_bindings_required")
    elif tx["migration_bindings"] is not None:
        errors.add("migration_bindings_forbidden")
    policy_relation = tx["result_policy_relation"]
    expected_relation = KIND_MATRIX[kind]["result_policy"]
    if policy_relation != expected_relation:
        errors.add("bad_result_policy_relation")
    if kind not in {"genesis", "sync_merge"} and parents != [old]:
        errors.add("nonmerge_parent_shape")
    return errors


def valid_tx(kind: str) -> dict[str, Any]:
    old = None if kind == "genesis" else "old"
    parents = [] if kind == "genesis" else ["old"]
    if kind == "sync_merge":
        parents = ["old", "remote"]
    return {
        "transaction_kind": kind,
        "expected_old_oid": old,
        "parent_oids": parents,
        "authorization_basis": (
            "genesis_anchor" if kind == "genesis" else "expected_old_policy"
        ),
        "sync_certificate": {"parent_oids": parents} if kind == "sync_merge" else None,
        "dream_bindings": [{}] if kind == "dream_apply" else None,
        "migration_bindings": [{}] if kind == "migration_import" else None,
        "result_policy_relation": KIND_MATRIX[kind]["result_policy"],
    }


def derive_capabilities(diff: dict[str, Any]) -> set[str]:
    if set(diff) != DIFF_KEYS:
        raise ValueError("tree diff fields are not exact")
    capabilities: set[str] = set()
    for field, capability in CAPABILITY_MAP.items():
        value = diff[field]
        if isinstance(value, bool):
            active = value
        elif isinstance(value, int) and value >= 0:
            active = value > 0
        else:
            raise ValueError(f"invalid diff value: {field}")
        if active:
            capabilities.add(capability)
    if not capabilities:
        raise ValueError("no-op transaction")
    return capabilities


def transaction_capability_errors(kind: str, capabilities: set[str]) -> set[str]:
    constraints = KIND_CAPABILITY_CONSTRAINTS[kind]
    errors: set[str] = set()
    if not constraints["required"] <= capabilities:
        errors.add("missing_kind_capability")
    if not capabilities <= constraints["allowed"]:
        errors.add("capability_forbidden_for_kind")
    return errors


def empty_diff() -> dict[str, Any]:
    return {
        key: False if key in {"genesis_created", "state_manifest_changed", "policy_changed"} else 0
        for key in CAPABILITY_MAP
    }


def authorization_errors(
    *, kind: str, diff: dict[str, Any], authorization: dict[str, Any]
) -> set[str]:
    errors: set[str] = set()
    expected_source = "genesis_anchor" if kind == "genesis" else "expected_old_commit"
    if authorization["source"] != expected_source:
        errors.add("bad_anchor_source")
    if not authorization["anchor_revision_and_digest_match"]:
        errors.add("anchor_mismatch")
    if not authorization["bound_to_expected_old_oid"]:
        errors.add("authorization_replay")
    if not authorization["signer_known_and_not_revoked"]:
        errors.add("bad_signer")
    derived = derive_capabilities(diff)
    if set(authorization["declared_capabilities"]) != derived:
        errors.add("declared_capability_mismatch")
    if not derived <= set(authorization["granted_capabilities"]):
        errors.add("ungranted_capability")
    return errors


def resolution_decision_digest(decision: dict[str, Any]) -> str:
    if set(decision) != RESOLUTION_FIELDS:
        raise ValueError("resolution decision fields are not exact")
    body = {key: value for key, value in decision.items() if key != "decision_digest"}
    return typed_json_digest(
        "resolution-decision/v1",
        "watari-resolution-decision-v1:",
        body,
    )


def resolution_decision_set_digest(decisions: list[dict[str, Any]]) -> str:
    digests = sorted(resolution_decision_digest(item) for item in decisions)
    return typed_json_digest(
        "resolution-decision-set/v1",
        "watari-resolution-decision-set-v1:",
        {"schema_version": 1, "decision_digests": digests},
    )


def make_resolution_decision(
    class_name: str,
    conflict_key: str,
    variant_digests: list[str],
    outcome: str,
    selected_variant_digest: str | None,
    strategy: str,
) -> dict[str, Any]:
    decision = {
        "class": class_name,
        "conflict_key": conflict_key,
        "variant_digests": sorted(variant_digests),
        "outcome": outcome,
        "selected_variant_digest": selected_variant_digest,
        "strategy": strategy,
        "authorization_policy_revision": "policy-old",
        "authorization_policy_digest": "watari-policy-v1:" + "a" * 64,
        "required_capability": "conflict.resolve",
        "decision_digest": "",
    }
    decision["decision_digest"] = resolution_decision_digest(decision)
    return decision


def resolution_binding_errors(
    decisions: list[dict[str, Any]],
    expected_conflicts: dict[tuple[str, str], set[str]],
    declared_count: int,
    declared_set_digest: str,
    expected_authorization_policy_revision: str,
    expected_authorization_policy_digest: str,
) -> set[str]:
    errors: set[str] = set()
    if any(set(decision) != RESOLUTION_FIELDS for decision in decisions):
        return {"resolution_schema"}
    decision_keys = [(item["class"], item["conflict_key"]) for item in decisions]
    if len(decision_keys) != len(set(decision_keys)):
        errors.add("duplicate_resolution_key")
    if set(decision_keys) != set(expected_conflicts):
        errors.add("resolution_conflict_bijection")
    for decision in decisions:
        if decision["class"] not in {"event", "profile", "checkpoint"}:
            errors.add("resolution_class")
        if decision["class"] == "event" and decision["outcome"] != "quarantine":
            errors.add("event_conflict_must_quarantine")
        if decision["variant_digests"] != sorted(set(decision["variant_digests"])):
            errors.add("resolution_variants_not_sorted_unique")
        if decision["outcome"] not in {"select", "quarantine"}:
            errors.add("resolution_outcome")
        if decision["outcome"] == "quarantine" and decision["selected_variant_digest"] is not None:
            errors.add("quarantine_selected_variant")
        if (
            decision["outcome"] == "select"
            and decision["selected_variant_digest"] not in decision["variant_digests"]
        ):
            errors.add("selected_variant_not_in_conflict")
        if decision["decision_digest"] != resolution_decision_digest(decision):
            errors.add("resolution_digest")
        expected_variants = expected_conflicts.get(
            (decision["class"], decision["conflict_key"])
        )
        if expected_variants is not None and set(decision["variant_digests"]) != expected_variants:
            errors.add("resolution_variant_set")
        if decision["required_capability"] != "conflict.resolve":
            errors.add("resolution_capability")
        if decision["strategy"] in {"max", "last-writer-wins"}:
            errors.add("implicit_resolution")
        if (
            decision["authorization_policy_revision"]
            != expected_authorization_policy_revision
            or decision["authorization_policy_digest"]
            != expected_authorization_policy_digest
        ):
            errors.add("resolution_authorization")
    if declared_count != len(decisions):
        errors.add("resolution_decision_count")
    if declared_set_digest != resolution_decision_set_digest(decisions):
        errors.add("resolution_decision_set_digest")
    return errors


def bind_resolution_decisions(
    merge: dict[str, Any], decisions: list[dict[str, Any]]
) -> None:
    merge["resolution_decisions"] = decisions
    merge["resolution_decision_count"] = len(decisions)
    merge["resolution_decision_set_digest"] = resolution_decision_set_digest(decisions)


def merge_errors(merge: dict[str, Any]) -> set[str]:
    errors: set[str] = set()
    parents = merge["parent_oids"]
    if len(parents) < 2 or len(parents) != len(set(parents)):
        errors.add("bad_parent_set")
    if merge["certificate_parent_oids"] != parents:
        errors.add("certificate_parent_order")
    if len(merge["parent_state_digests"]) != len(parents):
        errors.add("parent_state_digest_count")
    if merge["candidate_additions"]:
        errors.add("pure_merge_additions")

    event_union = set().union(*map(set, merge["parent_event_variants"]))
    profile_union = set().union(*map(set, merge["parent_profile_events"]))
    dream_union = set().union(*map(set, merge["parent_dream_manifests"]))
    if set(merge["result_event_variants"]) != event_union:
        errors.add("event_union_mismatch")
    if set(merge["result_profile_events"]) != profile_union:
        errors.add("profile_union_mismatch")
    if set(merge["result_dream_manifests"]) != dream_union:
        errors.add("dream_union_mismatch")

    variants_by_id: dict[str, set[str]] = {}
    for event_id, envelope_digest in event_union:
        variants_by_id.setdefault(event_id, set()).add(envelope_digest)
    profiles_by_key: dict[str, set[str]] = {}
    for key, digest in profile_union:
        profiles_by_key.setdefault(key, set()).add(digest)
    checkpoint_variants: dict[str, set[tuple[str, str]]] = {}
    for parent in merge["parent_checkpoints"]:
        for source_key, lineage, digest in parent:
            checkpoint_variants.setdefault(source_key, set()).add((lineage, digest))

    expected_conflicts = {
        **{
            ("event", key): digests
            for key, digests in variants_by_id.items()
            if len(digests) > 1
        },
        **{
            ("profile", key): digests
            for key, digests in profiles_by_key.items()
            if len(digests) > 1
        },
        **{
            ("checkpoint", key): {digest for _, digest in variants}
            for key, variants in checkpoint_variants.items()
            if len(variants) > 1
        },
    }
    decisions = merge["resolution_decisions"]
    resolution_errors = resolution_binding_errors(
        decisions,
        expected_conflicts,
        merge["resolution_decision_count"],
        merge["resolution_decision_set_digest"],
        merge["expected_authorization_policy_revision"],
        merge["expected_authorization_policy_digest"],
    )
    errors |= resolution_errors
    if "resolution_schema" in resolution_errors:
        return errors
    decision_keys = [(item["class"], item["conflict_key"]) for item in decisions]
    decision_index = dict(zip(decision_keys, decisions, strict=True))

    for event_id, digests in variants_by_id.items():
        if len(digests) > 1:
            decision = decision_index.get(("event", event_id))
            if (
                decision is None
                or decision["outcome"] != "quarantine"
                or decision["selected_variant_digest"] is not None
                or set(decision["variant_digests"]) != digests
            ):
                errors.add("event_conflict_not_quarantined")

    for key, digests in profiles_by_key.items():
        if len(digests) > 1:
            decision = decision_index.get(("profile", key))
            if (
                decision is None
                or set(decision["variant_digests"]) != digests
                or decision["outcome"] not in {"select", "quarantine"}
            ):
                errors.add("profile_resolution_missing")

    result_checkpoints = {
        source_key: (lineage, digest)
        for source_key, lineage, digest in merge["result_checkpoints"]
    }
    if len(result_checkpoints) != len(merge["result_checkpoints"]):
        errors.add("duplicate_result_checkpoint")
    causal_pairs = set(map(tuple, merge["verified_causal_descendant_pairs"]))
    for source_key, variants in checkpoint_variants.items():
        if len(variants) == 1:
            if result_checkpoints.get(source_key) != next(iter(variants)):
                errors.add("compatible_checkpoint_changed")
            continue
        decision = decision_index.get(("checkpoint", source_key))
        variant_digests = {digest for _, digest in variants}
        if decision is None or set(decision["variant_digests"]) != variant_digests:
            errors.add("checkpoint_resolution_missing")
            continue
        selected = decision["selected_variant_digest"]
        if decision["outcome"] == "quarantine":
            if source_key in result_checkpoints:
                errors.add("quarantined_checkpoint_active")
        elif selected is not None:
            selected_variants = [item for item in variants if item[1] == selected]
            if len(selected_variants) != 1 or result_checkpoints.get(source_key) != selected_variants[0]:
                errors.add("checkpoint_selection_mismatch")
            if decision["strategy"] == "verified-causal-descendant":
                if any(
                    other_digest != selected
                    and (selected, other_digest) not in causal_pairs
                    for _, other_digest in variants
                ):
                    errors.add("unverified_causal_descendant")

    if set(result_checkpoints) - set(checkpoint_variants):
        errors.add("undeclared_result_checkpoint")

    return errors


def base_merge() -> dict[str, Any]:
    return {
        "parent_oids": ["old", "remote"],
        "certificate_parent_oids": ["old", "remote"],
        "parent_state_digests": ["state-old", "state-remote"],
        "candidate_additions": [],
        "parent_event_variants": [
            [("a", "env-a"), ("b", "env-b")],
            [("b", "env-b"), ("c", "env-c")],
        ],
        "result_event_variants": [("a", "env-a"), ("b", "env-b"), ("c", "env-c")],
        "parent_profile_events": [
            [("name", "profile-1")],
            [("name", "profile-1")],
        ],
        "result_profile_events": [("name", "profile-1")],
        "parent_dream_manifests": [["dream-1"], ["dream-2"]],
        "result_dream_manifests": ["dream-1", "dream-2"],
        "parent_checkpoints": [
            [("source-1", "lineage-1", "checkpoint-1")],
            [("source-1", "lineage-1", "checkpoint-1")],
        ],
        "result_checkpoints": [("source-1", "lineage-1", "checkpoint-1")],
        "verified_causal_descendant_pairs": [],
        "resolution_decisions": [],
        "resolution_decision_count": 0,
        "resolution_decision_set_digest": resolution_decision_set_digest([]),
        "expected_authorization_policy_revision": "policy-old",
        "expected_authorization_policy_digest": "watari-policy-v1:" + "a" * 64,
    }


def supersedes_errors(
    parent_event_sets: list[list[dict[str, Any]]],
    additions: list[dict[str, Any]],
) -> set[str]:
    errors: set[str] = set()
    raw_events = [event for parent in parent_event_sets for event in parent] + additions
    unique_events: dict[tuple[str, str], dict[str, Any]] = {}
    for item in raw_events:
        key = (item["event_id"], item["envelope_digest"])
        existing = unique_events.get(key)
        if existing is not None and existing["supersedes"] != item["supersedes"]:
            errors.add("same_variant_semantic_mismatch")
        unique_events.setdefault(key, item)
    events = list(unique_events.values())
    variants_by_id: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        variants_by_id.setdefault(event["event_id"], []).append(event)
        if event["origin"] == "parent" and not event["origin_chain_valid"]:
            errors.add("invalid_parent_origin")
        if event["origin"] == "addition" and not event["local_authorized"]:
            errors.add("unauthorized_addition")

    edges: dict[tuple[str, str], tuple[str, str]] = {}
    successors: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        target_id = event["supersedes"]
        if target_id is None:
            continue
        targets = variants_by_id.get(target_id, [])
        if not targets:
            errors.add("missing_target")
            continue
        if len(targets) != 1:
            errors.add("ambiguous_target")
            continue
        source_key = (event["event_id"], event["envelope_digest"])
        target_key = (targets[0]["event_id"], targets[0]["envelope_digest"])
        edges[source_key] = target_key
        successors.setdefault(target_id, []).append(event)

    visiting: set[tuple[str, str]] = set()
    visited: set[tuple[str, str]] = set()

    def visit(node: tuple[str, str]) -> None:
        if node in visiting:
            errors.add("supersedes_cycle")
            return
        if node in visited:
            return
        visiting.add(node)
        if node in edges:
            visit(edges[node])
        visiting.remove(node)
        visited.add(node)

    for node in edges:
        visit(node)
    for siblings in successors.values():
        if len(siblings) > 1 and any(item["active_selected"] for item in siblings):
            errors.add("parallel_successor_auto_selected")
    return errors


def event(
    event_id: str,
    *,
    supersedes: str | None = None,
    origin: str = "parent",
    envelope_digest: str | None = None,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "envelope_digest": envelope_digest or f"env-{event_id}",
        "supersedes": supersedes,
        "origin": origin,
        "origin_chain_valid": True,
        "local_authorized": True,
        "active_selected": False,
    }


def set_digest(values: list[Any]) -> str:
    canonical_items = sorted(values, key=canonical_ascii_json)
    return typed_json_digest(
        "checkpoint-item-set/v1",
        "watari-checkpoint-item-set-v1:",
        {"schema_version": 1, "items": canonical_items},
    )


def has_duplicate_canonical_values(values: list[Any]) -> bool:
    return len(values) != len({canonical_ascii_json(value) for value in values})


def canonical_sorted_unique(values: list[Any]) -> list[Any]:
    return sorted(values, key=canonical_ascii_json)


def is_canonical_sorted_unique(values: list[Any]) -> bool:
    return not has_duplicate_canonical_values(values) and values == canonical_sorted_unique(
        values
    )


def decision_digest(decisions: dict[str, dict[str, Any]]) -> str:
    return typed_json_digest(
        "dream-decision-manifest/v1",
        "watari-dream-decision-manifest-v1:",
        {"schema_version": 1, "decisions": decisions},
    )


def checkpoint_binding_digest(kind: str, binding: dict[str, Any]) -> str:
    domains = {
        "dream_run": (
            "checkpoint-binding/dream/v1",
            "watari-checkpoint-dream-v1:",
        ),
        "migration_import": (
            "checkpoint-binding/migration/v1",
            "watari-checkpoint-migration-v1:",
        ),
    }
    domain, prefix = domains[kind]
    return typed_json_digest(domain, prefix, binding)


def checkpoint_binding_set_digest(kind: str, bindings: list[dict[str, Any]]) -> str:
    return typed_json_digest(
        f"checkpoint-binding-set/{kind}/v1",
        f"watari-checkpoint-{kind}-set-v1:",
        {
            "schema_version": 1,
            "binding_digests": sorted(
                checkpoint_binding_digest(kind, binding) for binding in bindings
            ),
        },
    )


def checkpoint_binding_set_errors(
    kind: str,
    bindings: list[dict[str, Any]],
    declared_digest: str,
    declared_count: int,
) -> set[str]:
    errors = checkpoint_transaction_errors(bindings)
    if declared_count != len(bindings):
        errors.add("checkpoint_binding_count")
    if declared_digest != checkpoint_binding_set_digest(kind, bindings):
        errors.add("checkpoint_binding_set_digest")
    return errors


def checkpoint_binding_errors(
    binding: dict[str, Any],
    *,
    scanned_items: list[str],
    decisions: dict[str, dict[str, Any]],
    candidate_dream_events: list[dict[str, Any]],
    expected_old_source_event_variants: list[tuple[str, str]],
    result_source_event_variants: list[tuple[str, str]],
    unresolved_candidates: list[str],
    quarantine_items: list[str],
    candidate_profile_event_count: int,
    expected_transaction_id: str,
    expected_source_key: dict[str, Any],
    expected_checkpoint_before: str,
    exact_checkpoint_proposal: str,
    expected_source_snapshot_digest: str,
    expected_model_policy_digest: str,
    expected_completion_local_date: str,
    expected_completion_policy_revision: str,
    existing_dream_run_ids: set[str],
) -> set[str]:
    errors: set[str] = set()
    if set(binding) != DREAM_BINDING_FIELDS:
        errors.add("binding_schema")
        return errors
    if set(binding["source_key"]) != SOURCE_KEY_FIELDS:
        errors.add("source_key_schema")
    if set(binding["completion_key"]) != COMPLETION_KEY_FIELDS:
        errors.add("completion_key_schema")
    if binding["binding_schema"] != "watari.checkpoint-binding.dream/v1":
        errors.add("binding_schema_value")
    if binding["binding_kind"] != "dream_run":
        errors.add("binding_kind")
    if binding["transaction_id"] != expected_transaction_id:
        errors.add("transaction_id")
    if binding["source_key"] != expected_source_key:
        errors.add("source_key")
    if not is_canonical_sorted_unique(scanned_items):
        errors.add("scan_keys_not_sorted_unique")
        return errors
    if binding["dream_run_id"] in existing_dream_run_ids:
        errors.add("dream_run_replay")
    if binding["checkpoint_before_digest"] != expected_checkpoint_before:
        errors.add("checkpoint_before")
    if binding["checkpoint_after_digest"] != exact_checkpoint_proposal:
        errors.add("checkpoint_after")
    if binding["source_snapshot_digest"] != expected_source_snapshot_digest:
        errors.add("source_snapshot")
    if binding["model_policy_digest"] != expected_model_policy_digest:
        errors.add("model_policy")
    if set(decisions) != set(scanned_items):
        errors.add("scan_decision_coverage")
    if any(set(item) != DECISION_WITNESS_FIELDS for item in decisions.values()):
        errors.add("decision_witness_schema")
    if any(item["outcome"] not in {"accept", "reject", "quarantine"} for item in decisions.values()):
        errors.add("decision_outcome")
    if binding["scan_manifest_digest"] != set_digest(scanned_items):
        errors.add("scan_digest")

    accepted = canonical_sorted_unique(
        item["event_variant"]
        for item in decisions.values()
        if item["outcome"] == "accept"
    )
    if has_duplicate_canonical_values(accepted):
        errors.add("accepted_event_variants_not_unique")
    if binding["decision_manifest_digest"] != decision_digest(decisions):
        errors.add("decision_digest")
    if binding["accepted_event_variant_set_digest"] != set_digest(accepted):
        errors.add("accepted_set_digest")
    if binding["accepted_event_count"] != len(accepted):
        errors.add("accepted_count")
    if not is_canonical_sorted_unique(expected_old_source_event_variants):
        errors.add("old_source_event_variants_not_sorted_unique")
    if not is_canonical_sorted_unique(result_source_event_variants):
        errors.add("result_source_event_variants_not_sorted_unique")
    expected_result_source_events = canonical_sorted_unique(
        expected_old_source_event_variants + accepted
    )
    if has_duplicate_canonical_values(expected_result_source_events):
        errors.add("accepted_source_event_already_exists")
    if result_source_event_variants != expected_result_source_events:
        errors.add("result_source_event_equation")
    if binding["result_source_event_set_digest"] != set_digest(result_source_event_variants):
        errors.add("result_source_event_set")

    if any(set(item) != DREAM_EVENT_WITNESS_FIELDS for item in candidate_dream_events):
        errors.add("dream_event_witness_schema")
    event_variants = [item["event_variant"] for item in candidate_dream_events]
    if not is_canonical_sorted_unique(event_variants):
        errors.add("candidate_dream_event_variants_not_sorted_unique")
    if event_variants != accepted:
        errors.add("dream_event_set")
    for item in candidate_dream_events:
        if (
            item["dream_run_id"] != binding["dream_run_id"]
            or item["source_key"] != binding["source_key"]
            or item["model_policy_digest"] != expected_model_policy_digest
        ):
            errors.add("dream_event_binding")
    if binding["status"] != "complete":
        errors.add("run_not_complete")
    if binding["unresolved_candidate_set_digest"] != set_digest(unresolved_candidates):
        errors.add("unresolved_set_digest")
    if binding["unresolved_candidate_count"] != len(unresolved_candidates):
        errors.add("unresolved_count")
    if binding["unresolved_candidate_count"] != 0:
        errors.add("unresolved_candidates")
    if binding["quarantine_set_digest"] != set_digest(quarantine_items):
        errors.add("quarantine_set_digest")
    if binding["quarantine_count"] != len(quarantine_items):
        errors.add("quarantine_count")
    if binding["quarantine_count"] != 0:
        errors.add("quarantine_blocks_checkpoint")
    if candidate_profile_event_count != 0:
        errors.add("dream_profile_change")
    if (
        binding["source_key"]["coordinator_epoch"] is not None
        and not binding["source_key"]["coordinator_epoch"].startswith("epoch-current-")
    ):
        errors.add("stale_coordinator_epoch")
    for field in ("device_id", "connector_instance_id", "source_lineage_digest"):
        if binding["completion_key"][field] != binding["source_key"][field]:
            errors.add("completion_source_mismatch")
    if binding["completion_key"]["local_date"] != expected_completion_local_date:
        errors.add("completion_local_date")
    if (
        binding["completion_key"]["policy_revision"]
        != expected_completion_policy_revision
    ):
        errors.add("completion_policy_revision")
    return errors


def dream_run_manifest(binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "manifest_schema": "watari.dream-run-manifest/v1",
        "transaction_id": binding["transaction_id"],
        "dream_run_id": binding["dream_run_id"],
        "source_key": binding["source_key"],
        "checkpoint_binding_digest": checkpoint_binding_digest(
            "dream_run", binding
        ),
        "accepted_event_variant_set_digest": binding[
            "accepted_event_variant_set_digest"
        ],
        "accepted_event_count": binding["accepted_event_count"],
        "model_policy_digest": binding["model_policy_digest"],
        "status": "complete",
    }


def dream_transaction_global_errors(
    bindings: list[dict[str, Any]],
    candidate_dream_events: list[dict[str, Any]],
    candidate_dream_run_manifests: list[dict[str, Any]],
    actual_global_dream_event_additions: list[tuple[str, str]],
) -> set[str]:
    errors = checkpoint_transaction_errors(bindings)
    binding_by_run_id = {
        binding["dream_run_id"]: binding
        for binding in bindings
        if set(binding) == DREAM_BINDING_FIELDS
    }
    if len(binding_by_run_id) != len(bindings):
        errors.add("dream_binding_schema_or_run_id_bijection")

    if any(set(item) != DREAM_EVENT_WITNESS_FIELDS for item in candidate_dream_events):
        errors.add("dream_event_witness_schema")
    else:
        event_variants = [item["event_variant"] for item in candidate_dream_events]
        if not is_canonical_sorted_unique(event_variants):
            errors.add("global_dream_event_variants_not_sorted_unique")
        if not is_canonical_sorted_unique(actual_global_dream_event_additions):
            errors.add("global_dream_additions_not_sorted_unique")
        if actual_global_dream_event_additions != event_variants:
            errors.add("global_dream_addition_equation")
        for item in candidate_dream_events:
            binding = binding_by_run_id.get(item["dream_run_id"])
            if binding is None:
                errors.add("dream_event_without_binding")
            elif (
                item["source_key"] != binding["source_key"]
                or item["model_policy_digest"] != binding["model_policy_digest"]
            ):
                errors.add("dream_event_global_binding")

    manifest_run_ids: list[str] = []
    for manifest in candidate_dream_run_manifests:
        if set(manifest) != DREAM_RUN_MANIFEST_FIELDS:
            errors.add("dream_run_manifest_schema")
            continue
        run_id = manifest["dream_run_id"]
        manifest_run_ids.append(run_id)
        binding = binding_by_run_id.get(run_id)
        if binding is None:
            errors.add("dream_manifest_without_binding")
        elif manifest != dream_run_manifest(binding):
            errors.add("dream_manifest_binding")
    if len(manifest_run_ids) != len(set(manifest_run_ids)):
        errors.add("duplicate_dream_run_manifest")
    if set(manifest_run_ids) != set(binding_by_run_id):
        errors.add("dream_binding_manifest_bijection")
    return errors


def migration_binding_errors(
    binding: dict[str, Any],
    *,
    expected_transaction_id: str,
    expected_source_key: dict[str, Any],
    expected_checkpoint_before: str,
    reviewed_checkpoint_after: str,
    expected_migration_snapshot_digest: str,
    expected_review_artifact_digest: str,
    imported_event_variants: list[tuple[str, str]],
) -> set[str]:
    errors: set[str] = set()
    if set(binding) != MIGRATION_BINDING_FIELDS:
        return {"migration_binding_schema"}
    if set(binding["source_key"]) != SOURCE_KEY_FIELDS:
        errors.add("migration_source_key_schema")
    if has_duplicate_canonical_values(imported_event_variants):
        errors.add("migration_imported_set_not_sorted_unique")
    exact_values = {
        "binding_schema": "watari.checkpoint-binding.migration/v1",
        "binding_kind": "migration_import",
        "transaction_id": expected_transaction_id,
        "source_key": expected_source_key,
        "checkpoint_before_digest": expected_checkpoint_before,
        "checkpoint_after_digest": reviewed_checkpoint_after,
        "migration_snapshot_digest": expected_migration_snapshot_digest,
        "review_artifact_digest": expected_review_artifact_digest,
        "imported_event_variant_set_digest": set_digest(imported_event_variants),
        "imported_event_count": len(imported_event_variants),
        "status": "complete",
    }
    for field, expected in exact_values.items():
        if binding[field] != expected:
            errors.add(f"migration_binding:{field}")
    return errors


def base_checkpoint_witness(
    accepted: list[tuple[str, str]] | None = None,
) -> tuple[dict[str, Any], list[str], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    accepted = accepted if accepted is not None else [("event-1", "env-1")]
    scanned = [f"source-{index}" for index in range(len(accepted))] or ["source-empty"]
    decisions: dict[str, dict[str, Any]] = {}
    if accepted:
        for source_id, variant in zip(scanned, accepted, strict=True):
            decisions[source_id] = {"outcome": "accept", "event_variant": variant}
    else:
        decisions[scanned[0]] = {"outcome": "reject", "event_variant": None}
    source_key = {
        "device_id": "device-1",
        "connector_instance_id": "connector-1",
        "source_lineage_digest": "lineage-1",
        "coordinator_epoch": None,
    }
    run_id = "run-1"
    policy = "watari-policy-v1:" + "4" * 64
    dream_events = [
        {
            "event_variant": variant,
            "dream_run_id": run_id,
            "source_key": source_key,
            "model_policy_digest": policy,
        }
        for variant in accepted
    ]
    binding = {
        "binding_schema": "watari.checkpoint-binding.dream/v1",
        "binding_kind": "dream_run",
        "transaction_id": "tx-1",
        "dream_run_id": run_id,
        "source_key": source_key,
        "checkpoint_before_digest": "checkpoint-before",
        "checkpoint_after_digest": "checkpoint-after",
        "result_source_event_set_digest": set_digest(accepted),
        "source_snapshot_digest": "snapshot-1",
        "scan_manifest_digest": set_digest(scanned),
        "decision_manifest_digest": decision_digest(decisions),
        "accepted_event_variant_set_digest": set_digest(accepted),
        "accepted_event_count": len(accepted),
        "unresolved_candidate_set_digest": set_digest([]),
        "unresolved_candidate_count": 0,
        "quarantine_set_digest": set_digest([]),
        "quarantine_count": 0,
        "model_policy_digest": policy,
        "completion_key": {
            "device_id": "device-1",
            "connector_instance_id": "connector-1",
            "source_lineage_digest": "lineage-1",
            "local_date": "2026-07-17",
            "policy_revision": "policy-1",
        },
        "status": "complete",
    }
    return binding, scanned, decisions, dream_events


def base_migration_binding() -> dict[str, Any]:
    imported = [("event-legacy-1", "env-legacy-1")]
    return {
        "binding_schema": "watari.checkpoint-binding.migration/v1",
        "binding_kind": "migration_import",
        "transaction_id": "tx-migration-1",
        "source_key": {
            "device_id": "legacy-device",
            "connector_instance_id": "legacy-import-1",
            "source_lineage_digest": "legacy-lineage-1",
            "coordinator_epoch": None,
        },
        "checkpoint_before_digest": "checkpoint-before",
        "checkpoint_after_digest": "checkpoint-reviewed-after",
        "migration_snapshot_digest": "snapshot-legacy",
        "review_artifact_digest": "review-approved",
        "imported_event_variant_set_digest": set_digest(imported),
        "imported_event_count": len(imported),
        "status": "complete",
    }


def checkpoint_transaction_errors(bindings: list[dict[str, Any]]) -> set[str]:
    errors: set[str] = set()
    source_keys = [canonical_ascii_json(item["source_key"]) for item in bindings]
    run_ids = [item.get("dream_run_id") for item in bindings if item.get("dream_run_id")]
    if len(source_keys) != len(set(source_keys)):
        errors.add("duplicate_checkpoint_source_key")
    if len(run_ids) != len(set(run_ids)):
        errors.add("duplicate_dream_run_id")
    return errors


def checkpoint_source_key_id(source_key: dict[str, Any]) -> str:
    return typed_json_digest(
        "checkpoint-source-key/v1",
        "watari-checkpoint-source-v1:",
        source_key,
    )


def checkpoint_transaction_state_errors(
    kind: str,
    bindings: list[dict[str, Any]],
    expected_old_checkpoint_map: dict[str, str],
    actual_result_checkpoint_map: dict[str, str],
) -> set[str]:
    errors = checkpoint_transaction_errors(bindings)
    if errors:
        return errors
    bound_writes = {
        checkpoint_source_key_id(binding["source_key"]): binding[
            "checkpoint_after_digest"
        ]
        for binding in bindings
    }
    return checkpoint_map_errors(
        kind,
        expected_old_checkpoint_map,
        bound_writes,
        actual_result_checkpoint_map,
        set(bound_writes),
    )


def simulate_prefix(
    model: dict[str, Any], completed_operations: int, initial_ref: str
) -> dict[str, Any]:
    snapshot = {
        "journal_state": None,
        "ref": initial_ref,
        "commit_valid": False,
        "new_oid": None,
        "view_published": False,
        "transaction_receipt": False,
    }
    for operation in model["operations"][:completed_operations]:
        snapshot.update(operation["effects"])
    return snapshot


FIXED_NORMAL_PREFIXES = [
    (None, "old", False, False, False),
    ("PREPARED", "old", False, False, False),
    ("PREPARED", "old", True, False, False),
    ("COMMIT_CREATED", "old", True, False, False),
    ("COMMIT_CREATED", "old", True, True, False),
    ("VIEW_PUBLISHED", "old", True, True, False),
    ("VIEW_PUBLISHED", "new", True, True, False),
    ("REF_UPDATED", "new", True, True, False),
    ("REF_UPDATED", "new", True, True, True),
    ("COMPLETE", "new", True, True, True),
]
FIXED_GENESIS_PREFIXES = [
    (state, "absent" if ref == "old" else ref, commit, view, receipt)
    for state, ref, commit, view, receipt in FIXED_NORMAL_PREFIXES
]


@dataclass(frozen=True)
class RecoveryResult:
    decision: str
    ref_action: str
    view_action: str
    receipt_action: str
    journal_action: str
    reader: str


def independent_view_action(view_state: str) -> str:
    return {
        "matching": "PIN_MATCHING",
        "stale": "MATERIALIZE_CURRENT",
        "missing": "MATERIALIZE_CURRENT",
        "invalid": "QUARANTINE_AND_MATERIALIZE_CURRENT",
    }[view_state]


def independent_receipt_action(receipt_state: str) -> str:
    return {
        "not-applicable": "NONE",
        "matching": "KEEP_MATCHING",
        "missing": "REGENERATE_FROM_VERIFIED_MANIFEST_AND_VIEW",
        "invalid": "QUARANTINE_AND_REGENERATE_FROM_VERIFIED_MANIFEST_AND_VIEW",
    }[receipt_state]


def independent_recovery_oracle(snapshot: dict[str, str]) -> RecoveryResult:
    state = snapshot["journal_state"]
    kind = snapshot["transaction_kind"]
    ref = snapshot["ref_relation"]
    authority = snapshot["authority_state"]
    binding = snapshot["binding_state"]
    view = snapshot["view_state"]
    receipt = snapshot["receipt_state"]
    fail = lambda decision: RecoveryResult(
        decision, "NONE", "NONE", "NONE", "NONE", "DENY"
    )
    current = lambda decision, journal_action="NONE": RecoveryResult(
        decision,
        "NONE",
        independent_view_action(view),
        independent_receipt_action(receipt),
        journal_action,
        "ALLOW_AFTER_PIN",
    )
    uninitialized = lambda decision, journal_action="NONE": RecoveryResult(
        decision, "NONE", "NONE", "NONE", journal_action, "NOT_INITIALIZED"
    )

    if state in INVALID_JOURNAL_STATES:
        return fail("JOURNAL_INVALID_FAIL_CLOSED")
    if ref == "other":
        return fail("REF_CONFLICT_FAIL_CLOSED")
    if binding == "mismatch":
        return fail("BINDING_MISMATCH_FAIL_CLOSED")
    if authority == "invalid":
        return fail("INVALID_AUTHORITY_FAIL_CLOSED")

    if (
        state == "ABSENT"
        and kind == "none"
        and ref == "new"
        and authority == "valid-current"
        and binding == "not-applicable"
        and receipt in {"matching", "missing", "invalid"}
    ):
        return current("NOOP_COMPLETE")
    if (
        state == "ABSENT"
        and kind == "none"
        and ref == "uninitialized"
        and authority == "confirmed-uninitialized"
        and binding == "not-applicable"
        and receipt == "not-applicable"
    ):
        return uninitialized("NOOP_UNINITIALIZED")

    if state in {"PREPARED", "COMMIT_CREATED", "VIEW_PUBLISHED"} and ref == "old":
        expected_binding = (
            "prepared-intent-valid" if state == "PREPARED" else "manifest-matching"
        )
        if binding != expected_binding:
            return fail("BINDING_MISMATCH_FAIL_CLOSED")
        if receipt != "not-applicable":
            return fail("INVALID_COMBINATION_FAIL_CLOSED")
        if kind == "genesis" and authority == "expected-absent-genesis":
            return uninitialized(
                "ABORT_KEEP_UNINITIALIZED", "ARCHIVE_ABORT_AND_DELETE_ACTIVE"
            )
        if kind == "non-genesis" and authority == "valid-current":
            return current("ABORT_KEEP_OLD", "ARCHIVE_ABORT_AND_DELETE_ACTIVE")

    if state in {"PREPARED", "COMMIT_CREATED"} and ref == "new":
        return fail("UNREACHABLE_PREFIX_FAIL_CLOSED")
    if state in {"REF_UPDATED", "COMPLETE"} and ref == "old":
        return fail("ROLLBACK_FAIL_CLOSED")
    if ref == "uninitialized":
        return fail("REF_MISSING_FAIL_CLOSED")

    if (
        state in {"VIEW_PUBLISHED", "REF_UPDATED", "COMPLETE"}
        and kind in {"genesis", "non-genesis"}
        and ref == "new"
        and authority == "valid-current"
        and binding == "manifest-matching"
        and receipt in {"matching", "missing", "invalid"}
    ):
        if state == "COMPLETE":
            return current("NOOP_COMPLETE", "VERIFY_RECEIPT_AND_DELETE_ACTIVE")
        return current("ROLL_FORWARD_NEW", "ROLL_FORWARD_TO_COMPLETE_AND_DELETE_ACTIVE")
    return fail("INVALID_COMBINATION_FAIL_CLOSED")


def rule_matches(rule: dict[str, Any], snapshot: dict[str, str]) -> bool:
    return all(snapshot[field] in allowed for field, allowed in rule["when"].items())


def contract_recovery(
    model: dict[str, Any], snapshot: dict[str, str]
) -> RecoveryResult:
    recovery = model["recovery"]
    outcome = recovery["default_outcome"]
    for rule in recovery["ordered_rules"]:
        if rule_matches(rule, snapshot):
            outcome = rule["outcome"]
            break
    view_policy = outcome["view_policy"]
    view_action = (
        recovery["view_actions"][snapshot["view_state"]]
        if view_policy == "ensure-current"
        else "NONE"
    )
    receipt_policy = outcome.get(
        "receipt_policy", recovery["outcome_defaults"]["receipt_policy"]
    )
    receipt_action = (
        recovery["receipt_actions"][snapshot["receipt_state"]]
        if receipt_policy == "ensure-current"
        else "NONE"
    )
    return RecoveryResult(
        outcome["decision"],
        outcome["ref_action"],
        view_action,
        receipt_action,
        outcome.get(
            "journal_action", recovery["outcome_defaults"]["journal_action"]
        ),
        outcome["reader"],
    )


def recovery_terminal_class(result: RecoveryResult) -> str | None:
    if result.reader == "DENY":
        if result.journal_action != "NONE":
            raise AssertionError("failed recovery cannot mutate the journal")
        return None
    expected_actions = {
        "NOOP_UNINITIALIZED": ("NONE", "CONFIRMED_UNINITIALIZED"),
        "ABORT_KEEP_UNINITIALIZED": (
            "ARCHIVE_ABORT_AND_DELETE_ACTIVE",
            "CONFIRMED_UNINITIALIZED",
        ),
        "ABORT_KEEP_OLD": ("ARCHIVE_ABORT_AND_DELETE_ACTIVE", "COMPLETE_OLD"),
        "ROLL_FORWARD_NEW": (
            "ROLL_FORWARD_TO_COMPLETE_AND_DELETE_ACTIVE",
            "COMPLETE_NEW",
        ),
    }
    if result.decision == "NOOP_COMPLETE":
        if result.journal_action not in {
            "NONE",
            "VERIFY_RECEIPT_AND_DELETE_ACTIVE",
        }:
            raise AssertionError("complete recovery has an invalid journal action")
        return "COMPLETE_NEW"
    expected_action, terminal = expected_actions[result.decision]
    if result.journal_action != expected_action:
        raise AssertionError("recovery plan does not reach its terminal class")
    return terminal


def view_file_digest(content: bytes) -> str:
    return "watari-view-file-v1:" + framed_digest("view-file/v1", content).hex()


def materialized_view_manifest(
    entries: list[dict[str, Any]], actual_lstat_paths: list[str]
) -> dict[str, Any]:
    manifest_entries: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for raw in entries:
        if set(raw) != {"path", "type", "mode", "content", "link_count"}:
            raise ValueError("view source entry fields are not exact")
        path = raw["path"]
        if not isinstance(path, str):
            raise ValueError("invalid view path type")
        pure = PurePosixPath(path)
        if (
            path != unicodedata.normalize("NFC", path)
            or path.startswith("/")
            or "\\" in path
            or str(pure) != path
            or not pure.parts
            or pure.parts[0] != "data"
            or any(part in {"", ".", ".."} for part in pure.parts)
            or path in seen_paths
        ):
            raise ValueError("invalid or duplicate view path")
        seen_paths.add(path)
        if raw["type"] == "file":
            if raw["mode"] != "0400" or raw["link_count"] != 1:
                raise ValueError("file mode or hard-link count is invalid")
            if not isinstance(raw["content"], bytes):
                raise ValueError("file content must be exact bytes")
            length = len(raw["content"])
            content_digest: str | None = view_file_digest(raw["content"])
        elif raw["type"] == "directory":
            if (
                raw["mode"] != "0500"
                or raw["content"] is not None
                or raw["link_count"] is not None
            ):
                raise ValueError("directory representation is invalid")
            length = 0
            content_digest = None
        else:
            raise ValueError("symlink or special entry is forbidden")
        manifest_entries.append(
            {
                "path": path,
                "type": raw["type"],
                "mode": raw["mode"],
                "length": length,
                "content_digest": content_digest,
            }
        )
    if actual_lstat_paths != sorted(set(actual_lstat_paths), key=lambda value: value.encode("utf-8")):
        raise ValueError("lstat paths are not sorted and unique")
    if set(actual_lstat_paths) != seen_paths:
        raise ValueError("manifest entries do not equal the complete lstat walk")
    entry_index = {item["path"]: item for item in manifest_entries}
    if entry_index.get("data", {}).get("type") != "directory":
        raise ValueError("data root directory is required")
    for path in seen_paths - {"data"}:
        parent = str(PurePosixPath(path).parent)
        if entry_index.get(parent, {}).get("type") != "directory":
            raise ValueError("every entry parent must be a represented directory")
    manifest_entries.sort(key=lambda item: item["path"].encode("utf-8"))
    return {
        "schema_version": 1,
        "view_schema": "watari.materialized-view/v1",
        "entries": manifest_entries,
    }


def materialized_view_digest(
    entries: list[dict[str, Any]], actual_lstat_paths: list[str]
) -> str:
    return typed_json_digest(
        "materialized-view/v1",
        "watari-materialized-view-v1:",
        materialized_view_manifest(entries, actual_lstat_paths),
    )


def view_receipt_digest(receipt: dict[str, Any]) -> str:
    if set(receipt) != VIEW_RECEIPT_FIELDS:
        raise ValueError("view receipt fields are not exact")
    return typed_json_digest(
        "view-receipt/v1",
        "watari-view-receipt-v1:",
        receipt,
    )


def derive_transaction_receipt(
    signed_manifest: dict[str, Any],
    verified_commit_oid: str,
    view_receipt: dict[str, Any],
) -> dict[str, Any]:
    if set(signed_manifest) != TRANSACTION_MANIFEST_FIELDS:
        raise ValueError("signed manifest fields are not exact")
    if set(view_receipt) != VIEW_RECEIPT_FIELDS:
        raise ValueError("view receipt fields are not exact")
    return {
        "receipt_schema": "watari.transaction-receipt/v1",
        "state_id": signed_manifest["state_id"],
        "transaction_id": signed_manifest["transaction_id"],
        "transaction_kind": signed_manifest["transaction_kind"],
        "canonical_ref": signed_manifest["canonical_ref"],
        "expected_old_oid": signed_manifest["expected_old_oid"],
        "new_oid": verified_commit_oid,
        "prepared_intent_digest": signed_manifest["prepared_intent_digest"],
        "authorization_policy_revision": signed_manifest["authorization"][
            "policy_revision"
        ],
        "authorization_policy_digest": signed_manifest["authorization"][
            "policy_digest"
        ],
        "result_policy_revision": signed_manifest["result_policy_revision"],
        "result_policy_digest": signed_manifest["result_policy_digest"],
        "view_receipt_digest": view_receipt_digest(view_receipt),
        "status": "complete",
    }


def transaction_receipt_digest(receipt: dict[str, Any]) -> str:
    if set(receipt) != TRANSACTION_RECEIPT_FIELDS:
        raise ValueError("transaction receipt fields are not exact")
    return typed_json_digest(
        "transaction-receipt/v1",
        "watari-transaction-receipt-v1:",
        receipt,
    )


def transaction_receipt_errors(
    receipt: dict[str, Any], expected: dict[str, Any]
) -> set[str]:
    if set(receipt) != TRANSACTION_RECEIPT_FIELDS:
        return {"transaction_receipt_schema"}
    if set(expected) != TRANSACTION_RECEIPT_FIELDS:
        return {"transaction_receipt_expected_schema"}
    errors = {
        f"transaction_receipt:{field}"
        for field, value in expected.items()
        if receipt[field] != value
    }
    if receipt["receipt_schema"] != "watari.transaction-receipt/v1":
        errors.add("transaction_receipt:receipt_schema")
    if receipt["status"] != "complete":
        errors.add("transaction_receipt:status")
    return errors


def receipt_repair_binding_errors(
    *,
    journal_state: str,
    journal_transaction_receipt_digest: str | None,
    regenerated_transaction_receipt_digest: str,
) -> set[str]:
    if journal_state == "COMPLETE":
        if (
            journal_transaction_receipt_digest is None
            or journal_transaction_receipt_digest
            != regenerated_transaction_receipt_digest
        ):
            return {"journal_transaction_receipt_digest_mismatch"}
    elif journal_state in {"VIEW_PUBLISHED", "REF_UPDATED", "ABSENT"}:
        if journal_transaction_receipt_digest is not None:
            return {"journal_state_forbids_transaction_receipt_digest"}
    else:
        return {"receipt_repair_journal_state"}
    return set()


def validate_view_receipt(
    *,
    pinned_oid: str,
    receipt: dict[str, str] | None,
    expected_view_schema: str,
    expected_tree_digest: str,
    expected_materializer_digest: str,
    actual_view_digest: str,
) -> str:
    if receipt is None:
        return "REBUILD_OR_FAIL"
    if set(receipt) != VIEW_RECEIPT_FIELDS:
        return "QUARANTINE_AND_REBUILD"
    if (
        receipt["receipt_schema"] != "watari.view-receipt/v1"
        or receipt["source_commit_oid"] != pinned_oid
        or receipt["view_schema"] != expected_view_schema
        or receipt["canonical_tree_digest"] != expected_tree_digest
        or receipt["materializer_digest"] != expected_materializer_digest
    ):
        return "REBUILD_OR_FAIL"
    if receipt["materialized_view_digest"] != actual_view_digest:
        return "QUARANTINE_AND_REBUILD"
    return "PIN"


class TransactionModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text, cls.model = parse_model()

    def test_state_graph_prepublishes_view_and_fault_prefixes_are_fixed(self) -> None:
        self.assertEqual(self.model["schema_version"], 1)
        self.assertEqual(self.model["states"], STATES)
        self.assertEqual([item["name"] for item in self.model["operations"]], OPERATIONS)
        transitions = [(item["from"], item["to"]) for item in self.model["transitions"]]
        self.assertEqual(
            transitions,
            [
                (None, "PREPARED"),
                ("PREPARED", "COMMIT_CREATED"),
                ("COMMIT_CREATED", "VIEW_PUBLISHED"),
                ("VIEW_PUBLISHED", "REF_UPDATED"),
                ("REF_UPDATED", "COMPLETE"),
            ],
        )
        for initial_ref, expected_prefixes in (
            ("old", FIXED_NORMAL_PREFIXES),
            ("absent", FIXED_GENESIS_PREFIXES),
        ):
            for prefix, expected in enumerate(expected_prefixes):
                with self.subTest(initial_ref=initial_ref, prefix=prefix):
                    snapshot = simulate_prefix(self.model, prefix, initial_ref)
                    actual = (
                        snapshot["journal_state"],
                        snapshot["ref"],
                        snapshot["commit_valid"],
                        snapshot["view_published"],
                        snapshot["transaction_receipt"],
                    )
                    self.assertEqual(actual, expected)
                    if snapshot["ref"] == "new":
                        self.assertTrue(snapshot["commit_valid"])
                        self.assertTrue(snapshot["view_published"])

    def test_every_d004_digest_reuses_d003_canonical_bytes_and_frame(self) -> None:
        rules = self.model["digest_rules"]
        self.assertEqual(
            rules["canonical_json"], "D003-NFC-LF-JCS-UTF16-key-order"
        )
        self.assertEqual(
            rules["frame"], "D003-WATARI-domain-separated-length-frame"
        )
        self.assertEqual(
            canonical_ascii_json({"value": "e\u0301\r\nline"}),
            canonical_ascii_json({"value": "é\nline"}),
        )
        self.assertEqual(
            canonical_ascii_json({"\ue000": 1, "\U00010000": 2}),
            b'{"\xf0\x90\x80\x80":2,"\xee\x80\x80":1}',
        )
        self.assertTrue(set_digest(["b", "a"]).startswith(
            "watari-checkpoint-item-set-v1:"
        ))
        self.assertTrue(decision_digest({}).startswith(
            "watari-dream-decision-manifest-v1:"
        ))

    def test_transaction_kind_matrix_is_closed_and_cross_field_validated(self) -> None:
        contract = self.model["transaction_kinds"]
        self.assertEqual(contract["allowed"], TRANSACTION_KINDS)
        self.assertEqual(contract["unknown_kind"], "reject")
        rows = {item["kind"]: {k: v for k, v in item.items() if k != "kind"} for item in contract["matrix"]}
        self.assertEqual(rows, KIND_MATRIX)
        for kind in TRANSACTION_KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(kind_errors(valid_tx(kind)), set())
        genesis = valid_tx("genesis")
        genesis["parent_oids"] = ["foreign"]
        self.assertIn("genesis_parent", kind_errors(genesis))
        merge = valid_tx("sync_merge")
        merge["sync_certificate"] = None
        self.assertIn("merge_certificate_required", kind_errors(merge))
        ordinary = valid_tx("ordinary")
        ordinary["sync_certificate"] = {}
        self.assertIn("merge_certificate_forbidden", kind_errors(ordinary))

    def test_prepared_intent_has_exact_digest_and_manifest_binding(self) -> None:
        intent_contract = self.model["prepared_intent"]
        self.assertEqual(set(intent_contract["exact_fields"]), INTENT_FIELDS)
        self.assertEqual(
            set(intent_contract["proposed_change_entry_fields"]),
            PROPOSED_CHANGE_FIELDS,
        )
        self.assertTrue(intent_contract["proposed_change_classes_unique"])
        self.assertTrue(intent_contract["proposed_change_digest_values_may_repeat"])
        self.assertEqual(intent_contract["canonicalization"], "D003-canonical-json")
        self.assertEqual(intent_contract["digest_domain"], "transaction-intent/v1")
        self.assertEqual(
            intent_contract["digest_prefix"], "watari-transaction-intent-v1:"
        )
        vector = intent_contract["test_vector"]
        self.assertEqual(vector["intent"], synthetic_intent())
        self.assertEqual(intent_errors(vector["intent"]), set())
        self.assertEqual(vector["digest"], intent_digest(vector["intent"]))
        baseline_digest = vector["digest"]
        for field in sorted(INTENT_FIELDS):
            with self.subTest(field=field):
                mutated = json.loads(json.dumps(vector["intent"]))
                value = mutated[field]
                if isinstance(value, list):
                    value.append("mutation")
                elif isinstance(value, int):
                    mutated[field] = value + 1
                elif value is None:
                    mutated[field] = "mutation"
                else:
                    mutated[field] = f"{value}-mutation"
                self.assertNotEqual(intent_digest(mutated), baseline_digest)
        duplicate = json.loads(json.dumps(vector["intent"]))
        duplicate["proposed_changes"].append(
            {
                "class": "canonical_events",
                "digest": "watari-change-v1:" + "4" * 64,
            }
        )
        self.assertIn(
            "proposed_changes_not_sorted_unique_by_class", intent_errors(duplicate)
        )
        self.assertIn(
            "prepared_intent_digest",
            self.model["transaction_manifest"]["required_fields"],
        )
        manifest_contract = self.model["transaction_manifest"]
        self.assertEqual(
            set(manifest_contract["required_fields"]), TRANSACTION_MANIFEST_FIELDS
        )
        self.assertEqual(
            set(manifest_contract["authorization_fields"]),
            MANIFEST_AUTHORIZATION_FIELDS,
        )
        self.assertTrue(
            {
                "checkpoint_binding_set_digest",
                "checkpoint_binding_count",
                "migration_binding_set_digest",
                "migration_binding_count",
                "resolution_decision_set_digest",
                "resolution_decision_count",
            }
            <= set(manifest_contract["required_fields"])
        )
        self.assertTrue(manifest_contract["intent_manifest_mirrors_must_equal"])
        self.assertEqual(
            manifest_contract["proposed_changes_equation"],
            "sorted_class_digest_entries_equal_exact_actual_changed_class_digest_map",
        )
        self.assertEqual(
            manifest_contract["canonical_input_digests_equation"],
            "sorted_unique_exact_verified_external_and_parent_input_digests",
        )
        self.assertEqual(
            set(manifest_contract["changed_class_digest_scope"]),
            DIFF_DIGEST_CLASSES,
        )
        self.assertEqual(
            manifest_contract["transaction_manifest_in_changed_class_digests"],
            "forbidden_self_reference",
        )
        self.assertIn(
            "transaction_manifest", self.model["atomic_commit_members"]
        )
        self.assertNotIn(
            "transaction_manifest", manifest_contract["changed_class_digest_scope"]
        )
        actual = {
            "canonical_events": vector["intent"]["proposed_changes"][0]["digest"]
        }
        inputs = vector["intent"]["canonical_input_digests"]
        manifest = synthetic_manifest(vector["intent"], actual)
        self.assertEqual(
            candidate_binding_errors(vector["intent"], manifest, actual, inputs), set()
        )
        self.assertEqual(set(manifest), TRANSACTION_MANIFEST_FIELDS)
        for field in sorted(TRANSACTION_MANIFEST_FIELDS):
            with self.subTest(missing_manifest_field=field):
                missing_field = copy.deepcopy(manifest)
                del missing_field[field]
                self.assertIn(
                    "transaction_manifest_fields",
                    candidate_binding_errors(
                        vector["intent"], missing_field, actual, inputs
                    ),
                )
        extra_field = copy.deepcopy(manifest)
        extra_field["unknown"] = None
        self.assertIn(
            "transaction_manifest_fields",
            candidate_binding_errors(vector["intent"], extra_field, actual, inputs),
        )
        bad_authorization = copy.deepcopy(manifest)
        bad_authorization["authorization"]["unknown"] = None
        self.assertIn(
            "manifest_authorization_fields",
            candidate_binding_errors(
                vector["intent"], bad_authorization, actual, inputs
            ),
        )
        authorization_array = copy.deepcopy(manifest)
        authorization_array["authorization"] = sorted(MANIFEST_AUTHORIZATION_FIELDS)
        self.assertIn(
            "manifest_authorization_fields",
            candidate_binding_errors(
                vector["intent"], authorization_array, actual, inputs
            ),
        )
        bad_parent_binding = copy.deepcopy(manifest)
        bad_parent_binding["ordered_parent_bindings"][0]["unknown"] = None
        self.assertIn(
            "parent_binding_fields",
            candidate_binding_errors(
                vector["intent"], bad_parent_binding, actual, inputs
            ),
        )
        parent_binding_array = copy.deepcopy(manifest)
        parent_binding_array["ordered_parent_bindings"] = [
            sorted(PARENT_BINDING_FIELDS)
        ]
        self.assertIn(
            "parent_binding_fields",
            candidate_binding_errors(
                vector["intent"], parent_binding_array, actual, inputs
            ),
        )
        manifest_mutations = {
            "transaction_kind": lambda item: item.__setitem__("transaction_kind", "dream_apply"),
            "state_id": lambda item: item.__setitem__("state_id", "state-other"),
            "transaction_id": lambda item: item.__setitem__("transaction_id", "tx-other"),
            "canonical_ref": lambda item: item.__setitem__("canonical_ref", "refs/watari/other"),
            "expected_old_oid": lambda item: item.__setitem__("expected_old_oid", "old-other"),
            "ordered_parent_oids": lambda item: item["ordered_parent_bindings"][0].__setitem__("oid", "old-other"),
            "authorization_policy_revision": lambda item: item["authorization"].__setitem__("policy_revision", "policy-other"),
            "authorization_policy_digest": lambda item: item["authorization"].__setitem__("policy_digest", "watari-policy-v1:" + "9" * 64),
            "result_policy_revision": lambda item: item.__setitem__("result_policy_revision", "policy-other"),
            "result_policy_digest": lambda item: item.__setitem__("result_policy_digest", "watari-policy-v1:" + "8" * 64),
        }
        for field, mutate in manifest_mutations.items():
            with self.subTest(manifest_mirror=field):
                mutated_manifest = json.loads(json.dumps(manifest))
                mutate(mutated_manifest)
                self.assertIn(
                    f"intent_manifest_mirror:{field}",
                    candidate_binding_errors(
                        vector["intent"], mutated_manifest, actual, inputs
                    ),
                )
        changed_actual = {"canonical_events": "watari-change-v1:" + "4" * 64}
        self.assertTrue(
            candidate_binding_errors(vector["intent"], manifest, changed_actual, inputs)
        )
        self.assertIn(
            "canonical_input_digests",
            candidate_binding_errors(
                vector["intent"],
                manifest,
                actual,
                ["watari-input-v1:" + "5" * 64],
            ),
        )
        self_referential_actual = {
            **actual,
            "transaction_manifest": "watari-change-v1:" + "9" * 64,
        }
        self_referential_intent = synthetic_intent()
        self_referential_intent["proposed_changes"].append(
            {
                "class": "transaction_manifest",
                "digest": "watari-change-v1:" + "9" * 64,
            }
        )
        self_referential_manifest = synthetic_manifest(
            self_referential_intent, self_referential_actual
        )
        self.assertIn(
            "changed_class_out_of_scope",
            candidate_binding_errors(
                self_referential_intent,
                self_referential_manifest,
                self_referential_actual,
                inputs,
            ),
        )
        paired_intent = synthetic_intent()
        paired_intent["proposed_changes"] = [
            {"class": "canonical_events", "digest": "watari-change-v1:" + "6" * 64},
            {"class": "profile_events", "digest": "watari-change-v1:" + "7" * 64},
        ]
        paired_actual = {
            item["class"]: item["digest"] for item in paired_intent["proposed_changes"]
        }
        paired_manifest = synthetic_manifest(paired_intent, paired_actual)
        self.assertEqual(
            candidate_binding_errors(
                paired_intent, paired_manifest, paired_actual, inputs
            ),
            set(),
        )
        swapped_actual = {
            "canonical_events": paired_actual["profile_events"],
            "profile_events": paired_actual["canonical_events"],
        }
        swapped_manifest = synthetic_manifest(paired_intent, swapped_actual)
        self.assertIn(
            "proposed_changes",
            candidate_binding_errors(
                paired_intent, swapped_manifest, swapped_actual, inputs
            ),
        )
        repeated_digest_intent = synthetic_intent()
        repeated_digest_intent["proposed_changes"] = [
            {"class": "canonical_events", "digest": "watari-change-v1:" + "8" * 64},
            {"class": "profile_events", "digest": "watari-change-v1:" + "8" * 64},
        ]
        self.assertEqual(intent_errors(repeated_digest_intent), set())

    def test_transaction_manifest_semantics_are_recomputed_conjunctively(self) -> None:
        contract = self.model["transaction_manifest"]
        self.assertEqual(
            set(contract["logical_schema_version_fields"]),
            LOGICAL_SCHEMA_VERSION_FIELDS,
        )
        self.assertEqual(
            set(contract["semantic_inputs_recomputed_conjunctively"]),
            {
                "ordered_parent_bindings_from_verified_parent_oids_and_state_digests",
                "authorization_from_trusted_anchor_signer_and_recomputed_diff_capabilities",
                "logical_schema_versions_from_candidate_objects",
                "checkpoint_binding_set_from_candidate_objects",
                "sync_merge_certificate_from_candidate_object",
                "migration_binding_set_from_candidate_objects",
                "resolution_decision_set_from_candidate_objects",
            },
        )
        intent = synthetic_intent()
        actual = {
            item["class"]: item["digest"] for item in intent["proposed_changes"]
        }
        manifest = synthetic_manifest(intent, actual)
        semantic_inputs = {
            "actual_parent_bindings": copy.deepcopy(
                manifest["ordered_parent_bindings"]
            ),
            "expected_authorization_from_anchor_and_diff": copy.deepcopy(
                manifest["authorization"]
            ),
            "actual_logical_schema_versions": copy.deepcopy(
                manifest["logical_schema_versions"]
            ),
            "actual_checkpoint_bindings": [],
            "actual_sync_merge_certificate": None,
            "actual_migration_bindings": [],
            "actual_resolution_decisions": [],
        }
        self.assertEqual(
            complete_manifest_binding_errors(
                intent,
                manifest,
                actual,
                intent["canonical_input_digests"],
                **semantic_inputs,
            ),
            set(),
        )

        mutations = {
            "parent_state": lambda item: item["ordered_parent_bindings"][0].__setitem__(
                "canonical_state_digest", "state:attacker"
            ),
            "authorization_source": lambda item: item["authorization"].__setitem__(
                "source", "candidate_policy"
            ),
            "authorization_signer": lambda item: item["authorization"].__setitem__(
                "signer_id", "signer-attacker"
            ),
            "authorization_capability": lambda item: item["authorization"].__setitem__(
                "declared_capabilities", ["policy.transition"]
            ),
            "logical_schema": lambda item: item["logical_schema_versions"].__setitem__(
                "event", 2
            ),
            "checkpoint_digest": lambda item: item.__setitem__(
                "checkpoint_binding_set_digest", "watari-checkpoint-dream-set-v1:" + "0" * 64
            ),
            "checkpoint_count": lambda item: item.__setitem__(
                "checkpoint_binding_count", 1
            ),
            "sync_certificate": lambda item: item.__setitem__(
                "sync_merge_certificate_digest", "watari-sync-merge-certificate-v1:" + "0" * 64
            ),
            "migration_digest": lambda item: item.__setitem__(
                "migration_binding_set_digest", "watari-checkpoint-migration_import-set-v1:" + "0" * 64
            ),
            "migration_count": lambda item: item.__setitem__(
                "migration_binding_count", 1
            ),
            "resolution_digest": lambda item: item.__setitem__(
                "resolution_decision_set_digest", "watari-resolution-decision-set-v1:" + "0" * 64
            ),
            "resolution_count": lambda item: item.__setitem__(
                "resolution_decision_count", 1
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(semantic_manifest_mutation=name):
                mutated = copy.deepcopy(manifest)
                mutate(mutated)
                self.assertTrue(
                    complete_manifest_binding_errors(
                        intent,
                        mutated,
                        actual,
                        intent["canonical_input_digests"],
                        **semantic_inputs,
                    )
                )

        actual_parent_attacker = copy.deepcopy(
            semantic_inputs["actual_parent_bindings"]
        )
        actual_parent_attacker[0]["canonical_state_digest"] = "state:attacker"
        self.assertIn(
            "ordered_parent_bindings_semantic",
            transaction_manifest_semantic_errors(
                manifest,
                **{
                    **semantic_inputs,
                    "actual_parent_bindings": actual_parent_attacker,
                },
            ),
        )
        actual_schemas = copy.deepcopy(
            semantic_inputs["actual_logical_schema_versions"]
        )
        actual_schemas["event"] = 2
        self.assertIn(
            "logical_schema_versions_semantic",
            transaction_manifest_semantic_errors(
                manifest,
                **{
                    **semantic_inputs,
                    "actual_logical_schema_versions": actual_schemas,
                },
            ),
        )
        self.assertIn(
            "actual_checkpoint_binding_schema",
            transaction_manifest_semantic_errors(
                manifest,
                **{**semantic_inputs, "actual_checkpoint_bindings": [{}]},
            ),
        )
        self.assertIn(
            "actual_migration_binding_schema",
            transaction_manifest_semantic_errors(
                manifest,
                **{**semantic_inputs, "actual_migration_bindings": [{}]},
            ),
        )
        self.assertIn(
            "actual_resolution_decision_schema",
            transaction_manifest_semantic_errors(
                manifest,
                **{**semantic_inputs, "actual_resolution_decisions": [{}]},
            ),
        )

        dream_binding, _, _, _ = base_checkpoint_witness()
        dream_intent = synthetic_intent()
        dream_intent["transaction_kind"] = "dream_apply"
        dream_manifest = synthetic_manifest(dream_intent, actual)
        dream_manifest["checkpoint_binding_set_digest"] = checkpoint_binding_set_digest(
            "dream_run", [dream_binding]
        )
        dream_manifest["checkpoint_binding_count"] = 1
        dream_semantics = {
            **semantic_inputs,
            "actual_parent_bindings": copy.deepcopy(
                dream_manifest["ordered_parent_bindings"]
            ),
            "expected_authorization_from_anchor_and_diff": copy.deepcopy(
                dream_manifest["authorization"]
            ),
            "actual_logical_schema_versions": copy.deepcopy(
                dream_manifest["logical_schema_versions"]
            ),
            "actual_checkpoint_bindings": [dream_binding],
        }
        self.assertEqual(
            transaction_manifest_semantic_errors(
                dream_manifest, **dream_semantics
            ),
            set(),
        )

        certificate = {"schema_version": 1, "parent_oids": ["old", "remote"]}
        sync_manifest = copy.deepcopy(manifest)
        sync_manifest["transaction_kind"] = "sync_merge"
        sync_manifest["sync_merge_certificate_digest"] = sync_merge_certificate_digest(
            certificate
        )
        self.assertEqual(
            transaction_manifest_semantic_errors(
                sync_manifest,
                **{
                    **semantic_inputs,
                    "actual_sync_merge_certificate": certificate,
                },
            ),
            set(),
        )

    def test_all_nonreceipt_digest_families_match_literal_goldens(self) -> None:
        vectors = self.model["typed_digest_test_vectors"]
        manifest_contract = self.model["transaction_manifest"]
        self.assertEqual(manifest_contract["tree_diff_digest_domain"], "tree-diff/v1")
        self.assertEqual(
            manifest_contract["tree_diff_digest_prefix"], "watari-tree-diff-v1:"
        )
        self.assertEqual(
            manifest_contract["sync_merge_certificate_digest_domain"],
            "sync-merge-certificate/v1",
        )
        self.assertEqual(
            manifest_contract["sync_merge_certificate_digest_prefix"],
            "watari-sync-merge-certificate-v1:",
        )
        self.assertEqual(
            set(vectors),
            {
                "tree_diff_base",
                "resolution_decision_event_quarantine",
                "resolution_decision_set_event_quarantine",
                "checkpoint_item_set_single",
                "dream_decision_manifest_reject_single",
                "checkpoint_dream_binding_base",
                "checkpoint_dream_binding_set_base",
                "checkpoint_source_key_base",
                "checkpoint_migration_binding_base",
                "checkpoint_migration_binding_set_base",
                "sync_merge_certificate_base",
            },
        )
        tree_diff = {"canonical_events": "watari-change-v1:" + "3" * 64}
        self.assertEqual(tree_diff_digest(tree_diff), vectors["tree_diff_base"])

        resolution = make_resolution_decision(
            "event",
            "event-1",
            ["env-a", "env-b"],
            "quarantine",
            None,
            "preserve-all",
        )
        self.assertEqual(
            resolution_decision_digest(resolution),
            vectors["resolution_decision_event_quarantine"],
        )
        self.assertEqual(
            resolution_decision_set_digest([resolution]),
            vectors["resolution_decision_set_event_quarantine"],
        )
        self.assertEqual(
            set_digest(["item-1"]), vectors["checkpoint_item_set_single"]
        )
        self.assertEqual(
            decision_digest(
                {"source-1": {"outcome": "reject", "event_variant": None}}
            ),
            vectors["dream_decision_manifest_reject_single"],
        )

        dream_binding, _, _, _ = base_checkpoint_witness()
        self.assertEqual(
            checkpoint_binding_digest("dream_run", dream_binding),
            vectors["checkpoint_dream_binding_base"],
        )
        self.assertEqual(
            checkpoint_binding_set_digest("dream_run", [dream_binding]),
            vectors["checkpoint_dream_binding_set_base"],
        )
        self.assertEqual(
            checkpoint_source_key_id(dream_binding["source_key"]),
            vectors["checkpoint_source_key_base"],
        )

        migration_binding = base_migration_binding()
        self.assertEqual(
            checkpoint_binding_digest("migration_import", migration_binding),
            vectors["checkpoint_migration_binding_base"],
        )
        self.assertEqual(
            checkpoint_binding_set_digest("migration_import", [migration_binding]),
            vectors["checkpoint_migration_binding_set_base"],
        )
        certificate = {"schema_version": 1, "parent_oids": ["old", "remote"]}
        self.assertEqual(
            sync_merge_certificate_digest(certificate),
            vectors["sync_merge_certificate_base"],
        )

    def test_capability_set_is_recomputed_from_structural_diff(self) -> None:
        derivation = self.model["capability_derivation"]
        self.assertEqual(derivation["field_to_capability"], CAPABILITY_MAP)
        self.assertTrue(derivation["declared_set_must_equal_recomputed_set"])
        machine_constraints = {
            kind: {
                "required": set(value["required"]),
                "allowed": set(value["allowed"]),
            }
            for kind, value in derivation["kind_constraints"].items()
        }
        self.assertEqual(machine_constraints, KIND_CAPABILITY_CONSTRAINTS)
        for field, capability in CAPABILITY_MAP.items():
            with self.subTest(field=field):
                diff = empty_diff()
                diff[field] = True if isinstance(diff[field], bool) else 1
                self.assertEqual(derive_capabilities(diff), {capability})
        diff = empty_diff()
        diff["local_memory_event_count"] = 2
        diff["local_checkpoint_change_count"] = 1
        diff["local_dream_manifest_count"] = 1
        derived = {"event.append", "checkpoint.advance", "dream.apply"}
        self.assertEqual(derive_capabilities(diff), derived)
        authorization = {
            "source": "expected_old_commit",
            "anchor_revision_and_digest_match": True,
            "bound_to_expected_old_oid": True,
            "signer_known_and_not_revoked": True,
            "declared_capabilities": sorted(derived),
            "granted_capabilities": sorted(derived),
        }
        self.assertEqual(
            authorization_errors(kind="dream_apply", diff=diff, authorization=authorization),
            set(),
        )
        authorization["declared_capabilities"] = ["event.append"]
        self.assertIn(
            "declared_capability_mismatch",
            authorization_errors(kind="dream_apply", diff=diff, authorization=authorization),
        )
        authorization["declared_capabilities"] = sorted(derived)
        authorization["granted_capabilities"] = ["event.append"]
        self.assertIn(
            "ungranted_capability",
            authorization_errors(kind="dream_apply", diff=diff, authorization=authorization),
        )
        self.assertEqual(
            transaction_capability_errors("dream_apply", derived), set()
        )
        self.assertIn(
            "capability_forbidden_for_kind",
            transaction_capability_errors(
                "dream_apply", derived | {"profile.write"}
            ),
        )
        self.assertIn(
            "missing_kind_capability",
            transaction_capability_errors("dream_apply", {"event.append"}),
        )

    def test_non_sync_transactions_preserve_exact_immutable_state(self) -> None:
        equations = self.model["state_transition_equations"]
        self.assertEqual(
            equations["ordinary_dream_migration"],
            "expected_old_exact_sets_union_authorized_additions",
        )
        self.assertEqual(equations["policy_transition"], "expected_old_exact_sets")
        self.assertEqual(equations["genesis"], "authorized_additions_only")
        old = {
            "canonical_event_variants": {"event-old"},
            "profile_events": {"profile-old"},
            "dream_run_manifests": {"dream-old"},
        }
        additions = {
            "canonical_event_variants": {"event-new"},
            "profile_events": set(),
            "dream_run_manifests": set(),
        }
        result = {
            class_name: old[class_name] | additions[class_name]
            for class_name in IMMUTABLE_STATE_CLASSES
        }
        for kind in ("ordinary", "dream_apply", "migration_import"):
            with self.subTest(kind=kind):
                self.assertEqual(
                    non_sync_state_errors(kind, old, additions, result), set()
                )
        dropped_old = {key: set(value) for key, value in result.items()}
        dropped_old["canonical_event_variants"] = {"event-new", "event-newer"}
        self.assertIn(
            "lossless_state_equation:canonical_event_variants",
            non_sync_state_errors("ordinary", old, additions, dropped_old),
        )
        self.assertEqual(
            non_sync_state_errors(
                "policy_transition",
                old,
                {key: set() for key in IMMUTABLE_STATE_CLASSES},
                old,
            ),
            set(),
        )
        self.assertTrue(non_sync_state_errors("policy_transition", old, additions, result))
        empty = {key: set() for key in IMMUTABLE_STATE_CLASSES}
        self.assertEqual(non_sync_state_errors("genesis", empty, additions, additions), set())
        self.assertTrue(non_sync_state_errors("genesis", old, additions, additions))
        old_checkpoints = {"source-a": "cp-a-old", "source-b": "cp-b-old"}
        writes = {"source-a": "cp-a-new"}
        expected_checkpoints = {"source-a": "cp-a-new", "source-b": "cp-b-old"}
        self.assertEqual(
            checkpoint_map_errors(
                "dream_apply",
                old_checkpoints,
                writes,
                expected_checkpoints,
                {"source-a"},
            ),
            set(),
        )
        dropped_other_source = {"source-a": "cp-a-new"}
        self.assertIn(
            "checkpoint_map_equation",
            checkpoint_map_errors(
                "dream_apply",
                old_checkpoints,
                writes,
                dropped_other_source,
                {"source-a"},
            ),
        )
        self.assertIn(
            "checkpoint_write_binding_bijection",
            checkpoint_map_errors(
                "migration_import",
                old_checkpoints,
                writes,
                expected_checkpoints,
                {"source-a", "source-b"},
            ),
        )
        ordinary_decision = make_resolution_decision(
            "profile",
            "profile-key",
            ["profile-a", "profile-b"],
            "select",
            "profile-b",
            "owner-approved",
        )
        ordinary_conflicts = {
            ("profile", "profile-key"): {"profile-a", "profile-b"}
        }
        self.assertEqual(
            resolution_binding_errors(
                [ordinary_decision],
                ordinary_conflicts,
                1,
                resolution_decision_set_digest([ordinary_decision]),
                "policy-old",
                "watari-policy-v1:" + "a" * 64,
            ),
            set(),
        )
        self.assertIn(
            "resolution_decision_count",
            resolution_binding_errors(
                [ordinary_decision],
                ordinary_conflicts,
                0,
                resolution_decision_set_digest([ordinary_decision]),
                "policy-old",
                "watari-policy-v1:" + "a" * 64,
            ),
        )
        event_select = make_resolution_decision(
            "event",
            "event-key",
            ["env-a", "env-b"],
            "select",
            "env-a",
            "owner-approved",
        )
        self.assertIn(
            "event_conflict_must_quarantine",
            resolution_binding_errors(
                [event_select],
                {("event", "event-key"): {"env-a", "env-b"}},
                1,
                resolution_decision_set_digest([event_select]),
                "policy-old",
                "watari-policy-v1:" + "a" * 64,
            ),
        )

    def test_sync_merge_computes_lossless_union_and_resolution_bindings(self) -> None:
        sync = self.model["sync_merge"]
        self.assertTrue(sync["candidate_additions_must_be_empty"])
        self.assertEqual(
            sync["immutable_result_equation"],
            "exact_union_of_all_verified_parent_variants",
        )
        self.assertEqual(set(sync["resolution_decision_fields"]), RESOLUTION_FIELDS)
        self.assertEqual(sync["resolution_key"], "class_plus_conflict_key")
        self.assertTrue(sync["resolution_key_must_be_unique"])
        self.assertTrue(sync["decision_keys_equal_recomputed_conflict_keys"])
        self.assertEqual(sync["resolution_digest_domain"], "resolution-decision/v1")
        self.assertEqual(
            sync["resolution_set_digest_domain"], "resolution-decision-set/v1"
        )
        merge = base_merge()
        self.assertEqual(merge_errors(merge), set())
        for key, value in (
            ("result_event_variants", [("a", "env-a"), ("b", "env-b")]),
            ("result_profile_events", []),
            ("result_dream_manifests", ["dream-1"]),
            ("candidate_additions", [("new", "env-new")]),
        ):
            with self.subTest(key=key):
                mutated = base_merge()
                mutated[key] = value
                self.assertTrue(merge_errors(mutated))

        conflict = base_merge()
        conflict["parent_event_variants"][1].append(("a", "env-a-evil"))
        conflict["result_event_variants"].append(("a", "env-a-evil"))
        self.assertIn("event_conflict_not_quarantined", merge_errors(conflict))
        event_decision = make_resolution_decision(
            "event",
            "a",
            ["env-a", "env-a-evil"],
            "quarantine",
            None,
            "preserve-all",
        )
        bind_resolution_decisions(conflict, [event_decision])
        self.assertEqual(merge_errors(conflict), set())
        attacker_policy = copy.deepcopy(conflict)
        attacker_decision = attacker_policy["resolution_decisions"][0]
        attacker_decision["authorization_policy_revision"] = "policy-secondary"
        attacker_decision["authorization_policy_digest"] = (
            "watari-policy-v1:" + "b" * 64
        )
        attacker_decision["decision_digest"] = resolution_decision_digest(
            attacker_decision
        )
        bind_resolution_decisions(attacker_policy, [attacker_decision])
        self.assertIn("resolution_authorization", merge_errors(attacker_policy))
        duplicate = copy.deepcopy(conflict)
        second = copy.deepcopy(event_decision)
        second["outcome"] = "select"
        second["selected_variant_digest"] = "env-a"
        second["decision_digest"] = resolution_decision_digest(second)
        bind_resolution_decisions(duplicate, [event_decision, second])
        self.assertIn("duplicate_resolution_key", merge_errors(duplicate))
        tampered = copy.deepcopy(conflict)
        tampered["resolution_decisions"][0]["decision_digest"] = "tampered"
        self.assertIn("resolution_digest", merge_errors(tampered))
        missing = copy.deepcopy(conflict)
        bind_resolution_decisions(missing, [])
        self.assertIn("resolution_conflict_bijection", merge_errors(missing))
        extra = base_merge()
        bind_resolution_decisions(extra, [event_decision])
        self.assertIn("resolution_conflict_bijection", merge_errors(extra))

        checkpoint_conflict = base_merge()
        checkpoint_conflict["parent_checkpoints"][1] = [
            ("source-1", "lineage-1", "checkpoint-2")
        ]
        checkpoint_conflict["result_checkpoints"] = [
            ("source-1", "lineage-1", "checkpoint-2")
        ]
        self.assertIn(
            "checkpoint_resolution_missing", merge_errors(checkpoint_conflict)
        )
        checkpoint_decision = make_resolution_decision(
            "checkpoint",
            "source-1",
            ["checkpoint-1", "checkpoint-2"],
            "select",
            "checkpoint-2",
            "verified-causal-descendant",
        )
        bind_resolution_decisions(checkpoint_conflict, [checkpoint_decision])
        self.assertIn(
            "unverified_causal_descendant", merge_errors(checkpoint_conflict)
        )
        checkpoint_conflict["verified_causal_descendant_pairs"] = [
            ("checkpoint-2", "checkpoint-1")
        ]
        self.assertEqual(merge_errors(checkpoint_conflict), set())

    def test_supersedes_graph_uses_all_parent_union_and_origin_authority(self) -> None:
        rules = self.model["event_integrity"]
        self.assertEqual(
            rules["reference_scope"],
            "all_verified_parent_variants_union_transaction_additions",
        )
        parent_one = [event("base-a"), event("corr", supersedes="base-b")]
        parent_two = [event("base-b")]
        self.assertEqual(supersedes_errors([parent_one, parent_two], []), set())
        duplicate_base = event("base-b")
        self.assertEqual(
            supersedes_errors(
                [parent_one + [duplicate_base], parent_two],
                [event("local-corr", supersedes="base-b", origin="addition")],
            ),
            set(),
        )

        cross_cycle_one = [event("x", supersedes="y")]
        cross_cycle_two = [event("y", supersedes="x")]
        self.assertIn(
            "supersedes_cycle",
            supersedes_errors([cross_cycle_one, cross_cycle_two], []),
        )
        ambiguous = [
            event("target", envelope_digest="env-1"),
            event("target", envelope_digest="env-2"),
        ]
        self.assertIn(
            "ambiguous_target",
            supersedes_errors([ambiguous], [event("corr", supersedes="target", origin="addition")]),
        )
        unauthorized = event("local", origin="addition")
        unauthorized["local_authorized"] = False
        self.assertIn(
            "unauthorized_addition", supersedes_errors([parent_two], [unauthorized])
        )

    def test_checkpoint_binding_is_closed_and_compares_actual_sets(self) -> None:
        checkpoint = self.model["checkpoint_bindings"]
        dream_schema = checkpoint["dream_run"]
        self.assertEqual(set(dream_schema["exact_fields"]), DREAM_BINDING_FIELDS)
        self.assertEqual(set(dream_schema["source_key_fields"]), SOURCE_KEY_FIELDS)
        self.assertEqual(
            set(dream_schema["completion_key_fields"]), COMPLETION_KEY_FIELDS
        )
        self.assertTrue(dream_schema["dream_run_id_unique_and_nonreplayable"])
        self.assertTrue(dream_schema["one_checkpoint_write_per_source_key"])
        self.assertEqual(
            dream_schema["result_source_event_set_equation"],
            "expected_old_exact_source_event_set_union_accepted_event_set",
        )
        self.assertEqual(
            set(dream_schema["dream_run_manifest"]["exact_fields"]),
            DREAM_RUN_MANIFEST_FIELDS,
        )
        self.assertTrue(
            dream_schema["dream_run_manifest"]["binding_run_id_bijection"]
        )
        self.assertEqual(
            checkpoint["migration_import"]["binding_kind"], "migration_import"
        )
        self.assertEqual(
            set(checkpoint["migration_import"]["exact_fields"]),
            MIGRATION_BINDING_FIELDS,
        )
        self.assertEqual(
            checkpoint["dream_run"]["digest_domain"],
            "checkpoint-binding/dream/v1",
        )
        self.assertEqual(
            checkpoint["migration_import"]["digest_domain"],
            "checkpoint-binding/migration/v1",
        )

        binding, scanned, decisions, dream_events = base_checkpoint_witness()
        kwargs = {
            "scanned_items": scanned,
            "decisions": decisions,
            "candidate_dream_events": dream_events,
            "expected_old_source_event_variants": [],
            "result_source_event_variants": [
                item["event_variant"] for item in dream_events
            ],
            "unresolved_candidates": [],
            "quarantine_items": [],
            "candidate_profile_event_count": 0,
            "expected_transaction_id": "tx-1",
            "expected_source_key": binding["source_key"],
            "expected_checkpoint_before": "checkpoint-before",
            "exact_checkpoint_proposal": "checkpoint-after",
            "expected_source_snapshot_digest": "snapshot-1",
            "expected_model_policy_digest": "watari-policy-v1:" + "4" * 64,
            "expected_completion_local_date": "2026-07-17",
            "expected_completion_policy_revision": "policy-1",
            "existing_dream_run_ids": set(),
        }
        self.assertEqual(checkpoint_binding_errors(binding, **kwargs), set())
        self.assertEqual(checkpoint_transaction_errors([binding]), set())
        self.assertEqual(
            checkpoint_transaction_errors([binding, json.loads(json.dumps(binding))]),
            {"duplicate_checkpoint_source_key", "duplicate_dream_run_id"},
        )
        source_id = checkpoint_source_key_id(binding["source_key"])
        old_checkpoint_map = {
            source_id: "checkpoint-before",
            "watari-checkpoint-source-v1:other": "checkpoint-other",
        }
        result_checkpoint_map = {
            source_id: "checkpoint-after",
            "watari-checkpoint-source-v1:other": "checkpoint-other",
        }
        self.assertEqual(
            checkpoint_transaction_state_errors(
                "dream_apply", [binding], old_checkpoint_map, result_checkpoint_map
            ),
            set(),
        )
        attacker_checkpoint_map = {
            **result_checkpoint_map,
            source_id: "checkpoint-attacker",
        }
        self.assertIn(
            "checkpoint_map_equation",
            checkpoint_transaction_state_errors(
                "dream_apply",
                [binding],
                old_checkpoint_map,
                attacker_checkpoint_map,
            ),
        )
        empty_binding, empty_scanned, empty_decisions, empty_events = base_checkpoint_witness([])
        self.assertEqual(
            checkpoint_binding_errors(
                empty_binding,
                scanned_items=empty_scanned,
                decisions=empty_decisions,
                candidate_dream_events=empty_events,
                expected_old_source_event_variants=[],
                result_source_event_variants=[],
                unresolved_candidates=[],
                quarantine_items=[],
                candidate_profile_event_count=0,
                expected_transaction_id="tx-1",
                expected_source_key=empty_binding["source_key"],
                expected_checkpoint_before="checkpoint-before",
                exact_checkpoint_proposal="checkpoint-after",
                expected_source_snapshot_digest="snapshot-1",
                expected_model_policy_digest="watari-policy-v1:" + "4" * 64,
                expected_completion_local_date="2026-07-17",
                expected_completion_policy_revision="policy-1",
                existing_dream_run_ids=set(),
            ),
            set(),
        )

        mutations = {
            "accepted_event_count": 2,
            "decision_manifest_digest": "wrong",
            "checkpoint_before_digest": "wrong",
            "checkpoint_after_digest": "wrong",
            "transaction_id": "tx-other",
            "source_snapshot_digest": "snapshot-other",
            "model_policy_digest": "watari-policy-v1:" + "7" * 64,
            "status": "partial",
            "unresolved_candidate_count": 1,
            "quarantine_count": 1,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                mutated = json.loads(json.dumps(binding))
                mutated[field] = value
                self.assertTrue(checkpoint_binding_errors(mutated, **kwargs))
        for field, value in (
            ("local_date", "2026-07-18"),
            ("policy_revision", "policy-other"),
        ):
            with self.subTest(completion_field=field):
                mutated = json.loads(json.dumps(binding))
                mutated["completion_key"][field] = value
                self.assertTrue(checkpoint_binding_errors(mutated, **kwargs))
        changed_binding = json.loads(json.dumps(binding))
        changed_events = json.loads(json.dumps(dream_events))
        changed_policy = "watari-policy-v1:" + "6" * 64
        changed_binding["model_policy_digest"] = changed_policy
        for item in changed_events:
            item["model_policy_digest"] = changed_policy
        self.assertIn(
            "model_policy",
            checkpoint_binding_errors(
                changed_binding,
                **{**kwargs, "candidate_dream_events": changed_events},
            ),
        )
        declared_digest = checkpoint_binding_set_digest("dream_run", [binding])
        self.assertEqual(
            checkpoint_binding_set_errors(
                "dream_run", [binding], declared_digest, 1
            ),
            set(),
        )
        mutated_binding = json.loads(json.dumps(binding))
        mutated_binding["source_snapshot_digest"] = "snapshot-other"
        self.assertNotEqual(
            declared_digest,
            checkpoint_binding_set_digest("dream_run", [mutated_binding]),
        )
        self.assertIn(
            "checkpoint_binding_count",
            checkpoint_binding_set_errors("dream_run", [binding], declared_digest, 0),
        )
        self.assertIn(
            "dream_run_replay",
            checkpoint_binding_errors(
                binding, **{**kwargs, "existing_dream_run_ids": {"run-1"}}
            ),
        )
        duplicate_binding, duplicate_scanned, duplicate_decisions, duplicate_events = (
            base_checkpoint_witness(
                [("event-duplicate", "env-duplicate")] * 2
            )
        )
        duplicate_kwargs = {
            **kwargs,
            "scanned_items": duplicate_scanned,
            "decisions": duplicate_decisions,
            "candidate_dream_events": duplicate_events,
            "result_source_event_variants": [
                item["event_variant"] for item in duplicate_events
            ],
            "expected_source_key": duplicate_binding["source_key"],
        }
        self.assertIn(
            "accepted_event_variants_not_unique",
            checkpoint_binding_errors(duplicate_binding, **duplicate_kwargs),
        )
        self.assertIn(
            "scan_keys_not_sorted_unique",
            checkpoint_binding_errors(
                binding,
                **{
                    **kwargs,
                    "scanned_items": ["Cafe\u0301", "Café"],
                    "decisions": {
                        "Cafe\u0301": {
                            "outcome": "accept",
                            "event_variant": ("event-1", "env-1"),
                        },
                        "Café": {"outcome": "reject", "event_variant": None},
                    },
                },
            ),
        )

        old_source_events = [("event-old", "env-old")]
        result_source_events = canonical_sorted_unique(
            old_source_events
            + [item["event_variant"] for item in dream_events]
        )
        state_bound = copy.deepcopy(binding)
        state_bound["result_source_event_set_digest"] = set_digest(
            result_source_events
        )
        state_kwargs = {
            **kwargs,
            "expected_old_source_event_variants": old_source_events,
            "result_source_event_variants": result_source_events,
        }
        self.assertEqual(checkpoint_binding_errors(state_bound, **state_kwargs), set())
        attacker_result = [item["event_variant"] for item in dream_events]
        attacker_binding = copy.deepcopy(state_bound)
        attacker_binding["result_source_event_set_digest"] = set_digest(attacker_result)
        self.assertIn(
            "result_source_event_equation",
            checkpoint_binding_errors(
                attacker_binding,
                **{**state_kwargs, "result_source_event_variants": attacker_result},
            ),
        )
        extra_result = canonical_sorted_unique(
            result_source_events + [("event-attacker", "env-attacker")]
        )
        extra_binding = copy.deepcopy(state_bound)
        extra_binding["result_source_event_set_digest"] = set_digest(extra_result)
        self.assertIn(
            "result_source_event_equation",
            checkpoint_binding_errors(
                extra_binding,
                **{**state_kwargs, "result_source_event_variants": extra_result},
            ),
        )

        run_manifest = dream_run_manifest(binding)
        additions = [item["event_variant"] for item in dream_events]
        self.assertEqual(
            dream_transaction_global_errors(
                [binding], dream_events, [run_manifest], additions
            ),
            set(),
        )
        self.assertIn(
            "dream_binding_manifest_bijection",
            dream_transaction_global_errors([binding], dream_events, [], additions),
        )
        extra_manifest = copy.deepcopy(run_manifest)
        extra_manifest["dream_run_id"] = "run-attacker"
        self.assertTrue(
            dream_transaction_global_errors(
                [binding], dream_events, [run_manifest, extra_manifest], additions
            )
        )
        tampered_manifest = copy.deepcopy(run_manifest)
        tampered_manifest["accepted_event_count"] += 1
        self.assertIn(
            "dream_manifest_binding",
            dream_transaction_global_errors(
                [binding], dream_events, [tampered_manifest], additions
            ),
        )
        attacker_additions = canonical_sorted_unique(
            additions + [("event-attacker", "env-attacker")]
        )
        self.assertIn(
            "global_dream_addition_equation",
            dream_transaction_global_errors(
                [binding], dream_events, [run_manifest], attacker_additions
            ),
        )

    def test_migration_binding_is_recomputed_from_reviewed_import(self) -> None:
        contract = self.model["checkpoint_bindings"]["migration_import"]
        self.assertTrue(contract["checkpoint_before_matches_expected_old"])
        self.assertTrue(contract["checkpoint_after_matches_reviewed_proposal"])
        self.assertTrue(contract["imported_set_and_count_recomputed_from_candidate"])
        self.assertTrue(contract["status_must_be_complete"])
        source_key = {
            "device_id": "legacy-device",
            "connector_instance_id": "legacy-import-1",
            "source_lineage_digest": "legacy-lineage-1",
            "coordinator_epoch": None,
        }
        imported = [("event-legacy-1", "env-legacy-1")]
        binding = {
            "binding_schema": "watari.checkpoint-binding.migration/v1",
            "binding_kind": "migration_import",
            "transaction_id": "tx-migration-1",
            "source_key": source_key,
            "checkpoint_before_digest": "checkpoint-before",
            "checkpoint_after_digest": "checkpoint-reviewed-after",
            "migration_snapshot_digest": "snapshot-legacy",
            "review_artifact_digest": "review-approved",
            "imported_event_variant_set_digest": set_digest(imported),
            "imported_event_count": len(imported),
            "status": "complete",
        }
        kwargs = {
            "expected_transaction_id": "tx-migration-1",
            "expected_source_key": source_key,
            "expected_checkpoint_before": "checkpoint-before",
            "reviewed_checkpoint_after": "checkpoint-reviewed-after",
            "expected_migration_snapshot_digest": "snapshot-legacy",
            "expected_review_artifact_digest": "review-approved",
            "imported_event_variants": imported,
        }
        self.assertEqual(migration_binding_errors(binding, **kwargs), set())
        for field in sorted(MIGRATION_BINDING_FIELDS):
            with self.subTest(field=field):
                mutated = json.loads(json.dumps(binding))
                value = mutated[field]
                if isinstance(value, dict):
                    value["device_id"] = "other-device"
                elif isinstance(value, int):
                    mutated[field] = value + 1
                else:
                    mutated[field] = f"{value}-other"
                self.assertTrue(migration_binding_errors(mutated, **kwargs))
        declared_digest = checkpoint_binding_set_digest("migration_import", [binding])
        self.assertEqual(
            checkpoint_binding_set_errors(
                "migration_import", [binding], declared_digest, 1
            ),
            set(),
        )
        candidate_changed = json.loads(json.dumps(binding))
        candidate_changed["imported_event_count"] = 2
        self.assertNotEqual(
            declared_digest,
            checkpoint_binding_set_digest("migration_import", [candidate_changed]),
        )
        self.assertIn(
            "duplicate_checkpoint_source_key",
            checkpoint_transaction_errors([binding, json.loads(json.dumps(binding))]),
        )

    def test_journal_schema_is_state_specific_and_exact(self) -> None:
        journal = self.model["journal"]
        self.assertEqual(journal["active_journal_max"], 1)
        self.assertTrue(journal["absent_is_recovery_input_not_state"])
        self.assertTrue(journal["fields_are_exactly_required_list"])
        self.assertEqual(journal["unknown_fields"], "reject")
        self.assertEqual(journal["journal_intent_mirror_fields"], JOURNAL_INTENT_MIRRORS)
        self.assertEqual(
            journal["mirror_mismatch"], "BINDING_MISMATCH_FAIL_CLOSED"
        )
        schemas = journal["state_schemas"]
        self.assertEqual(set(schemas), set(STATES))
        prepared = schemas["PREPARED"]
        self.assertIn("prepared_intent_digest", prepared["required"])
        self.assertNotIn("new_oid", prepared["required"])
        self.assertIn("new_oid", prepared["forbidden"])
        for state in STATES[1:]:
            self.assertIn("new_oid", schemas[state]["required"])
            self.assertIn("verification_evidence_digest", schemas[state]["required"])
        self.assertIn("view_receipt_digest", schemas["VIEW_PUBLISHED"]["required"])
        self.assertIn("transaction_receipt_digest", schemas["COMPLETE"]["required"])
        intent = synthetic_intent()
        sample = {
            "prepared_intent": intent,
            "prepared_intent_digest": intent_digest(intent),
            **{
                journal_field: intent[intent_field]
                for journal_field, intent_field in JOURNAL_INTENT_MIRRORS.items()
            },
        }
        self.assertEqual(journal_binding_errors(sample), set())
        for field in JOURNAL_INTENT_MIRRORS:
            with self.subTest(journal_mirror=field):
                mutated = json.loads(json.dumps(sample))
                value = mutated[field]
                if value is None:
                    mutated[field] = "other"
                else:
                    mutated[field] = f"{value}-other"
                self.assertIn(
                    f"journal_intent_mirror:{field}",
                    journal_binding_errors(mutated),
                )

    def test_recovery_rules_match_independent_oracle_for_all_axes(self) -> None:
        recovery = self.model["recovery"]
        self.assertEqual(recovery["journal_states"], RECOVERY_JOURNAL_STATES)
        self.assertEqual(recovery["transaction_kinds"], RECOVERY_TX_KINDS)
        self.assertEqual(recovery["ref_relations"], REF_RELATIONS)
        self.assertEqual(recovery["authority_states"], AUTHORITY_STATES)
        self.assertEqual(recovery["binding_states"], BINDING_STATES)
        self.assertEqual(recovery["view_states"], VIEW_STATES)
        self.assertEqual(recovery["receipt_states"], RECEIPT_STATES)
        checked = 0
        for values in itertools.product(
            RECOVERY_JOURNAL_STATES,
            RECOVERY_TX_KINDS,
            REF_RELATIONS,
            AUTHORITY_STATES,
            BINDING_STATES,
            VIEW_STATES,
            RECEIPT_STATES,
        ):
            snapshot = dict(
                zip(
                    (
                        "journal_state",
                        "transaction_kind",
                        "ref_relation",
                        "authority_state",
                        "binding_state",
                        "view_state",
                        "receipt_state",
                    ),
                    values,
                    strict=True,
                )
            )
            with self.subTest(**snapshot):
                expected = independent_recovery_oracle(snapshot)
                actual = contract_recovery(self.model, snapshot)
                self.assertEqual(actual, expected)
                self.assertEqual(actual.ref_action, "NONE")
                if actual.reader == "ALLOW_AFTER_PIN":
                    self.assertNotEqual(actual.view_action, "NONE")
                else:
                    self.assertEqual(actual.view_action, "NONE")
                    self.assertEqual(actual.receipt_action, "NONE")
                terminal = recovery_terminal_class(actual)
                if actual.reader == "DENY":
                    self.assertIsNone(terminal)
                else:
                    self.assertIn(
                        terminal,
                        {
                            "COMPLETE_OLD",
                            "COMPLETE_NEW",
                            "CONFIRMED_UNINITIALIZED",
                        },
                    )
            checked += 1
        self.assertEqual(
            checked,
            len(RECOVERY_JOURNAL_STATES)
            * len(RECOVERY_TX_KINDS)
            * len(REF_RELATIONS)
            * len(AUTHORITY_STATES)
            * len(BINDING_STATES)
            * len(VIEW_STATES)
            * len(RECEIPT_STATES),
        )
        self.assertEqual(checked, 30_720)

    def test_transaction_receipt_is_exact_and_recoverable_derivation(self) -> None:
        contract = self.model["transaction_receipt"]
        self.assertEqual(set(contract["exact_fields"]), TRANSACTION_RECEIPT_FIELDS)
        self.assertEqual(contract["digest_domain"], "transaction-receipt/v1")
        self.assertEqual(contract["digest_prefix"], "watari-transaction-receipt-v1:")
        self.assertEqual(
            self.model["recovery"]["receipt_repair_order"],
            "after_view_verification_before_reader_release",
        )
        self.assertEqual(self.model["recovery"]["receipt_repair_ref_action"], "NONE")
        receipt = {
            "receipt_schema": "watari.transaction-receipt/v1",
            "state_id": "state-1",
            "transaction_id": "tx-1",
            "transaction_kind": "ordinary",
            "canonical_ref": "refs/watari/current",
            "expected_old_oid": "old-oid",
            "new_oid": "new-oid",
            "prepared_intent_digest": "watari-transaction-intent-v1:cdd772a07de07feba3d09d1dcd9fc7c338b02bb44186494f6b11224183b4cf46",
            "authorization_policy_revision": "policy-1",
            "authorization_policy_digest": "watari-policy-v1:" + "1" * 64,
            "result_policy_revision": "policy-1",
            "result_policy_digest": "watari-policy-v1:" + "1" * 64,
            "view_receipt_digest": "watari-view-receipt-v1:8192a6b914ee1291f09519fc32b3c333f5969243043e8ca20da3731d4540eabe",
            "status": "complete",
        }
        intent = synthetic_intent()
        actual_changes = {
            item["class"]: item["digest"] for item in intent["proposed_changes"]
        }
        manifest = synthetic_manifest(intent, actual_changes)
        view_receipt = self.model["materialization"][
            "view_receipt_digest_contract"
        ]["test_vector"]["receipt"]
        self.assertEqual(
            receipt,
            derive_transaction_receipt(manifest, "new-oid", view_receipt),
        )
        self.assertEqual(transaction_receipt_errors(receipt, receipt), set())
        self.assertEqual(contract["test_vector"]["receipt"], receipt)
        self.assertEqual(
            contract["test_vector"]["digest"], transaction_receipt_digest(receipt)
        )
        receipt_digest = transaction_receipt_digest(receipt)
        self.assertEqual(
            receipt_repair_binding_errors(
                journal_state="COMPLETE",
                journal_transaction_receipt_digest=receipt_digest,
                regenerated_transaction_receipt_digest=receipt_digest,
            ),
            set(),
        )
        self.assertIn(
            "journal_transaction_receipt_digest_mismatch",
            receipt_repair_binding_errors(
                journal_state="COMPLETE",
                journal_transaction_receipt_digest="watari-transaction-receipt-v1:wrong",
                regenerated_transaction_receipt_digest=receipt_digest,
            ),
        )
        self.assertEqual(
            receipt_repair_binding_errors(
                journal_state="ABSENT",
                journal_transaction_receipt_digest=None,
                regenerated_transaction_receipt_digest=receipt_digest,
            ),
            set(),
        )
        for journal_state in ("VIEW_PUBLISHED", "REF_UPDATED"):
            with self.subTest(repair_journal_state=journal_state):
                self.assertEqual(
                    receipt_repair_binding_errors(
                        journal_state=journal_state,
                        journal_transaction_receipt_digest=None,
                        regenerated_transaction_receipt_digest=receipt_digest,
                    ),
                    set(),
                )
        for field in sorted(TRANSACTION_RECEIPT_FIELDS):
            with self.subTest(receipt_field=field):
                mutated = json.loads(json.dumps(receipt))
                mutated[field] = f"{mutated[field]}-other"
                self.assertTrue(transaction_receipt_errors(mutated, receipt))
        base_snapshot = {
            "journal_state": "COMPLETE",
            "transaction_kind": "non-genesis",
            "ref_relation": "new",
            "authority_state": "valid-current",
            "binding_state": "manifest-matching",
            "view_state": "matching",
        }
        expected_actions = {
            "matching": "KEEP_MATCHING",
            "missing": "REGENERATE_FROM_VERIFIED_MANIFEST_AND_VIEW",
            "invalid": "QUARANTINE_AND_REGENERATE_FROM_VERIFIED_MANIFEST_AND_VIEW",
        }
        for state, action in expected_actions.items():
            with self.subTest(receipt_state=state):
                result = contract_recovery(
                    self.model, {**base_snapshot, "receipt_state": state}
                )
                self.assertEqual(result.receipt_action, action)
                self.assertEqual(result.ref_action, "NONE")

    def test_genesis_and_normal_fault_prefixes_map_to_recovery(self) -> None:
        normal_cases = [
            {
                "journal_state": state or "ABSENT",
                "transaction_kind": "none" if state is None else "non-genesis",
                "ref_relation": "new" if state is None else ref,
                "authority_state": "valid-current",
                "binding_state": (
                    "not-applicable"
                    if state is None
                    else "prepared-intent-valid"
                    if state == "PREPARED"
                    else "manifest-matching"
                ),
                "view_state": "matching",
                "receipt_state": (
                    "matching"
                    if state is None or transaction_receipt
                    else "missing"
                    if ref == "new"
                    else "not-applicable"
                ),
            }
            for state, ref, _, _, transaction_receipt in FIXED_NORMAL_PREFIXES
        ]
        genesis_cases = []
        for state, ref, _, _, transaction_receipt in FIXED_GENESIS_PREFIXES:
            if state is None:
                genesis_cases.append(
                    {
                        "journal_state": "ABSENT",
                        "transaction_kind": "none",
                        "ref_relation": "uninitialized",
                        "authority_state": "confirmed-uninitialized",
                        "binding_state": "not-applicable",
                        "view_state": "missing",
                        "receipt_state": "not-applicable",
                    }
                )
            else:
                genesis_cases.append(
                    {
                        "journal_state": state,
                        "transaction_kind": "genesis",
                        "ref_relation": "old" if ref == "absent" else "new",
                        "authority_state": (
                            "expected-absent-genesis"
                            if ref == "absent"
                            else "valid-current"
                        ),
                        "binding_state": (
                            "prepared-intent-valid"
                            if state == "PREPARED"
                            else "manifest-matching"
                        ),
                        "view_state": "missing" if ref == "absent" else "matching",
                        "receipt_state": (
                            "matching"
                            if transaction_receipt
                            else "missing"
                            if ref == "new"
                            else "not-applicable"
                        ),
                    }
                )
        for label, cases in (("normal", normal_cases), ("genesis", genesis_cases)):
            for prefix, snapshot in enumerate(cases):
                with self.subTest(label=label, prefix=prefix):
                    result = contract_recovery(self.model, snapshot)
                    self.assertFalse(result.decision.endswith("FAIL_CLOSED"))
        unreachable = dict(normal_cases[1])
        unreachable.update(
            {
                "journal_state": "PREPARED",
                "ref_relation": "new",
                "authority_state": "valid-current",
                "binding_state": "manifest-matching",
            }
        )
        self.assertEqual(
            contract_recovery(self.model, unreachable).decision,
            "UNREACHABLE_PREFIX_FAIL_CLOSED",
        )

    def test_view_receipt_binds_output_bytes_and_v1_gc_preserves_pins(self) -> None:
        materialization = self.model["materialization"]
        self.assertEqual(materialization["layout"], "immutable_commit_oid_directories")
        self.assertEqual(
            materialization["install"],
            "same_filesystem_rename_temp_to_absent_oid_path",
        )
        self.assertIn("materialized_view_digest", materialization["receipt_fields"])
        self.assertEqual(materialization["canonical_view_gc_v1"], "forbidden")
        self.assertTrue(materialization["pin_survives_ref_change"])
        self.assertEqual(
            materialization["scope"],
            "time_invariant_canonical_materialization_only",
        )
        self.assertTrue(
            materialization["noncanonical_cache_may_never_satisfy_oid_view_validation"]
        )
        digest_contract = materialization["view_digest_contract"]
        self.assertEqual(digest_contract["receipt_path"], "receipt.json")
        self.assertTrue(digest_contract["receipt_excluded_from_digest"])
        self.assertEqual(set(digest_contract["entry_fields"]), VIEW_ENTRY_FIELDS)
        self.assertEqual(digest_contract["sort"], "relative_path_utf8_byte_order")
        self.assertEqual(digest_contract["digest_domain"], "materialized-view/v1")
        self.assertTrue(digest_contract["data_root_directory_required"])
        self.assertTrue(digest_contract["every_parent_path_present_and_directory"])
        self.assertTrue(
            digest_contract["entry_paths_equal_complete_owner_private_lstat_walk"]
        )
        raw_entries = [
            {
                "path": "data",
                "type": "directory",
                "mode": "0500",
                "content": None,
                "link_count": None,
            },
            {
                "path": "data/profile.json",
                "type": "file",
                "mode": "0400",
                "content": b'{"name":"Watari"}\n',
                "link_count": 1,
            },
        ]
        lstat_paths = ["data", "data/profile.json"]
        manifest = materialized_view_manifest(raw_entries, lstat_paths)
        view_digest = materialized_view_digest(raw_entries, lstat_paths)
        self.assertEqual(digest_contract["test_vector"]["manifest"], manifest)
        self.assertEqual(digest_contract["test_vector"]["digest"], view_digest)
        changed_content = json.loads(json.dumps(digest_contract["test_vector"]["manifest"]))
        changed_content["entries"][1]["content_digest"] = "watari-view-file-v1:" + "0" * 64
        self.assertNotEqual(
            view_digest,
            typed_json_digest(
                "materialized-view/v1",
                "watari-materialized-view-v1:",
                changed_content,
            ),
        )
        manifest_mutations = {
            "path": "data/profile-other.json",
            "type": "directory",
            "mode": "0500",
            "length": 19,
            "content_digest": "watari-view-file-v1:" + "5" * 64,
        }
        for field, value in manifest_mutations.items():
            with self.subTest(view_manifest_field=field):
                mutated_manifest = copy.deepcopy(manifest)
                mutated_manifest["entries"][1][field] = value
                self.assertNotEqual(
                    view_digest,
                    typed_json_digest(
                        "materialized-view/v1",
                        "watari-materialized-view-v1:",
                        mutated_manifest,
                    ),
                )
        for field, value in (
            ("path", "receipt.json"),
            ("type", "symlink"),
            ("mode", "0600"),
            ("link_count", 2),
        ):
            with self.subTest(invalid_view_source=field):
                invalid = [dict(item) for item in raw_entries]
                invalid[1][field] = value
                with self.assertRaises(ValueError):
                    materialized_view_manifest(
                        invalid, sorted(item["path"] for item in invalid)
                    )
        with self.assertRaises(ValueError):
            materialized_view_manifest(raw_entries[1:], ["data/profile.json"])
        bad_parent = raw_entries + [
            {
                "path": "data/profile.json/child",
                "type": "file",
                "mode": "0400",
                "content": b"child",
                "link_count": 1,
            }
        ]
        with self.assertRaises(ValueError):
            materialized_view_manifest(
                bad_parent,
                ["data", "data/profile.json", "data/profile.json/child"],
            )
        with self.assertRaises(ValueError):
            materialized_view_manifest(raw_entries, ["data"])
        receipt_contract = materialization["view_receipt_digest_contract"]
        receipt = receipt_contract["test_vector"]["receipt"]
        self.assertEqual(
            receipt_contract["test_vector"]["digest"], view_receipt_digest(receipt)
        )
        for field in sorted(VIEW_RECEIPT_FIELDS):
            with self.subTest(view_receipt_field=field):
                mutated_receipt = copy.deepcopy(receipt)
                mutated_receipt[field] = f"{mutated_receipt[field]}-other"
                self.assertNotEqual(
                    receipt_contract["test_vector"]["digest"],
                    view_receipt_digest(mutated_receipt),
                )
        self.assertEqual(
            validate_view_receipt(
                pinned_oid="oid-1",
                receipt=receipt,
                expected_view_schema="watari.materialized-view/v1",
                expected_tree_digest="watari-tree-v1:" + "1" * 64,
                expected_materializer_digest="watari-materializer-v1:" + "2" * 64,
                actual_view_digest=view_digest,
            ),
            "PIN",
        )
        self.assertEqual(
            validate_view_receipt(
                pinned_oid="oid-1",
                receipt=receipt,
                expected_view_schema="watari.materialized-view/v1",
                expected_tree_digest="watari-tree-v1:" + "1" * 64,
                expected_materializer_digest="watari-materializer-v1:" + "2" * 64,
                actual_view_digest="tampered",
            ),
            "QUARANTINE_AND_REBUILD",
        )
        self.assertFalse(
            materialization["gc_policy"]["may_delete_ever_canonical_view"]
        )
        self.assertFalse(
            materialization["gc_policy"]["may_delete_pinned_view"]
        )

    def test_commit_validation_fault_points_and_human_boundaries(self) -> None:
        self.assertEqual(
            set(self.model["commit_validations"]), REQUIRED_COMMIT_VALIDATIONS
        )
        expected_faults = {
            f"{position}:{operation}"
            for operation in OPERATIONS
            for position in ("before", "after")
        }
        self.assertEqual(set(self.model["fault_points"]), expected_faults)
        ref_update = self.model["ref_update"]
        self.assertEqual(ref_update["ref"], "refs/watari/current")
        self.assertEqual(ref_update["operation"], "compare-and-swap")
        self.assertTrue(ref_update["never_force"])
        self.assertTrue(ref_update["never_retry_with_observed_ref"])
        normalized = " ".join(self.text.split()).lower()
        for marker in (
            "candidate policy cannot authorize",
            "view is published before the ref",
            "lossless union",
            "all scanned items",
            "unknown journal state fails closed",
            "no automatic rollback",
            "reader pins",
            "canonical views are never deleted in v1",
            "push failure is sync pending",
        ):
            self.assertIn(marker, normalized)


if __name__ == "__main__":
    unittest.main()
