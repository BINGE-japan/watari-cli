#!/usr/bin/env python3
"""Synthetic, non-authoritative storage qualification harness for D011.

The harness never reads Watari state, credentials, or network resources.  Every
benchmark write is made below a fresh TemporaryDirectory and removed before a
worker reports success.  The 10k/100k qualification is intentionally *not* run
by the test-oriented ``--self-test`` mode.
"""

from __future__ import annotations

import argparse
import copy
import functools
import hashlib
import io
import json
import math
import os
import platform
import re
import resource
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable


PLAN_SCHEMA = "watari.storage-benchmark-plan.v1"
RESULT_SCHEMA = "watari.storage-benchmark-result.v1"
SAMPLE_SCHEMA = "watari.storage-benchmark-sample.v1"
SUITE_SCHEMA = "watari.storage-benchmark-suite.v1"
VALIDATION_SCHEMA = "watari.storage-harness-validation.v1"
LOOSE_LAYOUT = "loose-encrypted-object-candidate.v1"
PACK_LAYOUT = "immutable-pack-segment-candidate.v1"
LAYOUT_IDS = (LOOSE_LAYOUT, PACK_LAYOUT)
OPERATIONS = (
    "create",
    "status",
    "clone-equivalent",
    "copy",
    "pull-equivalent",
    "rebuild",
    "backup",
)
SCALAR_METRICS = (
    "payload_bytes",
    "repo_size_bytes",
    "working_size_bytes",
    "inode_count",
    "file_count",
    "mergeability_proxy_conflicting_paths",
    "single_corruption_blast_radius_events",
    "single_corruption_blast_radius_bytes",
    "peak_rss_bytes",
)
FILESYSTEM_METADATA_FIELDS = (
    "system",
    "release",
    "machine",
    "distribution_id",
    "distribution_version_id",
    "python_implementation",
    "python_version",
    "wsl2_detected",
    "required_platform_match",
    "statvfs_block_size",
    "statvfs_fragment_size",
    "statvfs_name_max",
    "filesystem_type",
    "cache_policy",
    "temp_root_device_id",
    "temp_root_same_device",
)
FUTURE_G001_CORPUS_REQUIRED_FIELDS = (
    "schema_version",
    "status",
    "codec_artifact_digest",
    "corpus_artifact_digest",
    "event_count",
    "payload_bytes",
    "payload_stream_sha256",
    "ordered_payload_lengths_sha256",
    "prestage_duration_ns",
)
FIXED_SEED = 0x574154415249  # ASCII-like "WATARI", within the JSON safe-integer range.
JSON_SAFE_INTEGER_MAX = (1 << 53) - 1
QUALIFICATION_EVENT_COUNTS = (10_000, 100_000)
QUALIFICATION_WARMUPS = 1
QUALIFICATION_REPETITIONS = 6
QUALIFICATION_SEGMENT_EVENTS = 256
SELF_TEST_EVENT_COUNT = 32
SELF_TEST_WARMUPS = 1
SELF_TEST_REPETITIONS = 3
SELF_TEST_SEGMENT_EVENTS = 8
WORKER_TIMEOUT_SECONDS = 7_200
SUPERVISOR_MARKER = "watari-d011-supervised-worker-v1\n"
PACK_MAGIC = b"WATARI-BENCH-PACK-V1\x00"
PAYLOAD_BUCKETS = (
    {"bytes": 256, "weight": 50},
    {"bytes": 1_024, "weight": 30},
    {"bytes": 4_096, "weight": 15},
    {"bytes": 16_384, "weight": 5},
)
PAYLOAD_GOLDEN_EVIDENCE = (
    {
        "event_count": 1,
        "payload_bytes": 256,
        "payload_stream_sha256": "sha256:a647691d3ea3fdb332acabd03308da3fafa7d539a3bda7e17cdb7a92c4459dde",
    },
    {
        "event_count": SELF_TEST_EVENT_COUNT,
        "payload_bytes": 64_256,
        "payload_stream_sha256": "sha256:bc623f60e320f3db34be71e48cc75563c07b2663971e07a8a7613a3902fdb092",
    },
    {
        "event_count": 10_000,
        "payload_bytes": 18_362_368,
        "payload_stream_sha256": "sha256:ae8b579c8ecbafd4be2d3932a1c35b6ef9f327fbdb687a1e9b7b3bea6b4c3fdd",
    },
    {
        "event_count": 100_000,
        "payload_bytes": 187_856_128,
        "payload_stream_sha256": "sha256:4d37f3a6428cff471f7f23efc23144ce5d3d972517f22d0a0f64b44762472eda",
    },
)


class ContractError(ValueError):
    """The closed D011 schema or an invariant did not match."""


PLAN: dict[str, Any] = {
    "schema_version": PLAN_SCHEMA,
    "status": "non-authoritative",
    "decision": "proposed",
    "authority_gate": "G001-and-G003-observation-required",
    "platform_scope": {
        "system": "Linux",
        "distribution": "Ubuntu-24.04",
        "runtime": "WSL2",
        "python_minimum": "3.11",
    },
    "fixed_seed": FIXED_SEED,
    "event_counts": list(QUALIFICATION_EVENT_COUNTS),
    "codec_input_policy": {
        "d011_mode": "synthetic-opaque-stand-in-only",
        "authoritative_run": "forbidden-until-separate-versioned-corpus-contract",
        "future_gate": "D010-then-G001-corpus-contract-implementation-and-review",
        "future_corpus_schema": "watari.storage-corpus-input.future.v1",
        "future_corpus_required_fields": list(FUTURE_G001_CORPUS_REQUIRED_FIELDS),
        "future_prestage_timing": "excluded-from-layout-durations-and-reported-separately",
        "layout_input_equality": "same-corpus-artifact-digest-bytes-lengths-and-order",
        "arbitrary_local_corpus_read": "forbidden",
    },
    "layouts": [
        {
            "layout_id": LOOSE_LAYOUT,
            "storage_unit": "one-qualified-codec-output-per-immutable-file",
            "compression": "disabled",
            "qualified_codec_required": True,
            "authentication_unit_event_limit": 1,
        },
        {
            "layout_id": PACK_LAYOUT,
            "storage_unit": "content-addressed-immutable-segment",
            "compression": "disabled",
            "qualified_codec_required": True,
            "authentication_unit_event_limit": QUALIFICATION_SEGMENT_EVENTS,
        },
    ],
    "payload_distribution": {
        "schema_version": "watari.storage-payload-distribution.v1",
        "kind": "weighted-discrete-exact-bytes",
        "buckets": list(PAYLOAD_BUCKETS),
        "weight_total": 100,
        "generator": "sha256-counter-stream-synthetic-opaque-bytes",
        "semantic_content": "none",
        "golden_evidence": list(PAYLOAD_GOLDEN_EVIDENCE),
    },
    "measurement": {
        "warmup_repetitions": QUALIFICATION_WARMUPS,
        "measured_repetitions": QUALIFICATION_REPETITIONS,
        "layout_order": "alternate-first-layout-by-cycle",
        "worker_isolation": "fresh-python-process-per-layout-repetition",
        "worker_timeout_seconds": WORKER_TIMEOUT_SECONDS,
        "timer": "time.perf_counter_ns",
        "statistics": {
            "median": "nearest-rank-p50",
            "p95": "nearest-rank-p95",
        },
        "operations": list(OPERATIONS),
        "fresh_temp_root_per_worker": True,
        "cache_policy": "one-warmup-then-as-observed-no-privileged-cache-drop",
        "durability": "fsync-file-and-containing-directory",
        "pull_base_fraction": {"numerator": 9, "denominator": 10},
        "backup_format": "uncompressed-tar-canonical-files-only",
        "derived_index_in_repository": False,
    },
    "metrics": {
        "duration_unit": "nanoseconds",
        "duration_metrics": list(OPERATIONS),
        "scalar_metrics": list(SCALAR_METRICS),
        "required_statistics": ["median", "p95"],
    },
    "filesystem_metadata": {
        "fields": list(FILESYSTEM_METADATA_FIELDS),
        "path_scope": "synthetic-temporary-root-only",
        "filesystem_type_observation": "unavailable-in-python-standard-library",
        "mount_source_collection": "forbidden",
    },
    "budgets": {
        "schema_version": "watari.storage-benchmark-budget.v1",
        "qualification_rule": "all-common-and-layout-specific-limits-must-pass",
        "selection_rule": "G003-prefers-eligible-loose-else-eligible-pack-else-no-selection",
        "common_by_event_count": [
            {
                "event_count": 10_000,
                "duration_p95_ns": {
                    "create": 120_000_000_000,
                    "status": 15_000_000_000,
                    "clone-equivalent": 90_000_000_000,
                    "copy": 60_000_000_000,
                    "pull-equivalent": 45_000_000_000,
                    "rebuild": 45_000_000_000,
                    "backup": 90_000_000_000,
                },
                "repo_size_bytes_max": 536_870_912,
                "working_size_bytes_max": 1_073_741_824,
                "peak_rss_bytes_max": 536_870_912,
                "repo_to_payload_ratio_max": {"numerator": 2, "denominator": 1},
                "working_to_payload_ratio_max": {"numerator": 4, "denominator": 1},
            },
            {
                "event_count": 100_000,
                "duration_p95_ns": {
                    "create": 1_200_000_000_000,
                    "status": 120_000_000_000,
                    "clone-equivalent": 600_000_000_000,
                    "copy": 600_000_000_000,
                    "pull-equivalent": 300_000_000_000,
                    "rebuild": 300_000_000_000,
                    "backup": 900_000_000_000,
                },
                "repo_size_bytes_max": 4_294_967_296,
                "working_size_bytes_max": 6_442_450_944,
                "peak_rss_bytes_max": 2_147_483_648,
                "repo_to_payload_ratio_max": {"numerator": 2, "denominator": 1},
                "working_to_payload_ratio_max": {"numerator": 4, "denominator": 1},
            },
        ],
        "layout_limits": [
            {
                "layout_id": LOOSE_LAYOUT,
                "file_count_max_by_event_count": [
                    {"event_count": 10_000, "max": 10_010},
                    {"event_count": 100_000, "max": 100_010},
                ],
                "inode_count_max_by_event_count": [
                    {"event_count": 10_000, "max": 10_020},
                    {"event_count": 100_000, "max": 100_020},
                ],
                "mergeability_proxy_conflicting_paths_max": 1,
                "single_corruption_blast_radius_events_max": 1,
                "single_corruption_blast_radius_bytes_max": 16_384,
            },
            {
                "layout_id": PACK_LAYOUT,
                "file_count_max_by_event_count": [
                    {"event_count": 10_000, "max": 50},
                    {"event_count": 100_000, "max": 410},
                ],
                "inode_count_max_by_event_count": [
                    {"event_count": 10_000, "max": 60},
                    {"event_count": 100_000, "max": 420},
                ],
                "mergeability_proxy_conflicting_paths_max": 1,
                "single_corruption_blast_radius_events_max": QUALIFICATION_SEGMENT_EVENTS,
                "single_corruption_blast_radius_bytes_max": QUALIFICATION_SEGMENT_EVENTS * 16_384,
            },
        ],
    },
    "cleanup": {
        "temporary_root": "python-tempfile-per-worker",
        "remove_on_success": True,
        "remove_on_failure": True,
        "persistent_artifacts": "none-stdout-json-only",
        "network": "forbidden",
        "credentials": "forbidden",
        "live_state": "forbidden",
    },
}


def _exact_dict(value: Any, keys: Iterable[str], label: str) -> dict[str, Any]:
    expected = set(keys)
    if type(value) is not dict or set(value) != expected:
        raise ContractError(f"{label} members do not match v1")
    return value


def _exact_list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise ContractError(f"{label} must be a list")
    return value


def _positive_int(value: Any, label: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if type(value) is not int or value < minimum or value > JSON_SAFE_INTEGER_MAX:
        raise ContractError(
            f"{label} must be an integer from {minimum} through {JSON_SAFE_INTEGER_MAX}"
        )
    return value


def _bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ContractError(f"{label} must be boolean")
    return value


def _nonempty(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        raise ContractError(f"{label} must be a nonempty string")
    return value


def _validate_ratio(value: Any, label: str) -> None:
    ratio = _exact_dict(value, {"numerator", "denominator"}, label)
    _positive_int(ratio["numerator"], f"{label}.numerator")
    _positive_int(ratio["denominator"], f"{label}.denominator")


def validate_plan(value: Any) -> dict[str, Any]:
    plan = _exact_dict(
        value,
        {
            "schema_version",
            "status",
            "decision",
            "authority_gate",
            "platform_scope",
            "fixed_seed",
            "event_counts",
            "codec_input_policy",
            "layouts",
            "payload_distribution",
            "measurement",
            "metrics",
            "filesystem_metadata",
            "budgets",
            "cleanup",
        },
        "benchmark plan",
    )
    if plan["schema_version"] != PLAN_SCHEMA:
        raise ContractError("unknown benchmark plan schema")
    if plan["status"] != "non-authoritative" or plan["decision"] != "proposed":
        raise ContractError("D011 may not make an authoritative layout decision")
    if plan["authority_gate"] != "G001-and-G003-observation-required":
        raise ContractError("unknown authority gate")
    platform_scope = _exact_dict(
        plan["platform_scope"],
        {"system", "distribution", "runtime", "python_minimum"},
        "platform scope",
    )
    if platform_scope != {
        "system": "Linux",
        "distribution": "Ubuntu-24.04",
        "runtime": "WSL2",
        "python_minimum": "3.11",
    }:
        raise ContractError("unknown platform scope")
    if plan["fixed_seed"] != FIXED_SEED:
        raise ContractError("fixed seed changed")
    if plan["event_counts"] != list(QUALIFICATION_EVENT_COUNTS):
        raise ContractError("qualification scales must be exactly 10k and 100k")
    codec_policy = _exact_dict(
        plan["codec_input_policy"],
        {
            "d011_mode",
            "authoritative_run",
            "future_gate",
            "future_corpus_schema",
            "future_corpus_required_fields",
            "future_prestage_timing",
            "layout_input_equality",
            "arbitrary_local_corpus_read",
        },
        "codec input policy",
    )
    if codec_policy != {
        "d011_mode": "synthetic-opaque-stand-in-only",
        "authoritative_run": "forbidden-until-separate-versioned-corpus-contract",
        "future_gate": "D010-then-G001-corpus-contract-implementation-and-review",
        "future_corpus_schema": "watari.storage-corpus-input.future.v1",
        "future_corpus_required_fields": list(FUTURE_G001_CORPUS_REQUIRED_FIELDS),
        "future_prestage_timing": "excluded-from-layout-durations-and-reported-separately",
        "layout_input_equality": "same-corpus-artifact-digest-bytes-lengths-and-order",
        "arbitrary_local_corpus_read": "forbidden",
    }:
        raise ContractError("codec input policy changed")

    layouts = _exact_list(plan["layouts"], "layouts")
    if len(layouts) != 2:
        raise ContractError("exactly two layout candidates are required")
    observed_layout_ids: list[str] = []
    for item in layouts:
        layout = _exact_dict(
            item,
            {
                "layout_id",
                "storage_unit",
                "compression",
                "qualified_codec_required",
                "authentication_unit_event_limit",
            },
            "layout",
        )
        observed_layout_ids.append(_nonempty(layout["layout_id"], "layout_id"))
        if layout["compression"] != "disabled":
            raise ContractError("compression must remain disabled for the comparison")
        if _bool(layout["qualified_codec_required"], "qualified_codec_required") is not True:
            raise ContractError("qualified codec output is required")
        _positive_int(layout["authentication_unit_event_limit"], "authentication_unit_event_limit")
    if tuple(observed_layout_ids) != LAYOUT_IDS:
        raise ContractError("unknown or reordered layout candidate")
    if [layout["storage_unit"] for layout in layouts] != [
        "one-qualified-codec-output-per-immutable-file",
        "content-addressed-immutable-segment",
    ]:
        raise ContractError("layout storage unit changed")
    if layouts[0]["authentication_unit_event_limit"] != 1:
        raise ContractError("loose layout must have one event per failure domain")
    if layouts[1]["authentication_unit_event_limit"] != QUALIFICATION_SEGMENT_EVENTS:
        raise ContractError("pack segment limit changed")

    distribution = _exact_dict(
        plan["payload_distribution"],
        {
            "schema_version",
            "kind",
            "buckets",
            "weight_total",
            "generator",
            "semantic_content",
            "golden_evidence",
        },
        "payload distribution",
    )
    if distribution["schema_version"] != "watari.storage-payload-distribution.v1":
        raise ContractError("unknown payload distribution schema")
    if distribution["kind"] != "weighted-discrete-exact-bytes":
        raise ContractError("unknown payload distribution kind")
    buckets = _exact_list(distribution["buckets"], "payload buckets")
    normalized_buckets: list[dict[str, int]] = []
    for item in buckets:
        bucket = _exact_dict(item, {"bytes", "weight"}, "payload bucket")
        normalized_buckets.append(
            {
                "bytes": _positive_int(bucket["bytes"], "payload bytes"),
                "weight": _positive_int(bucket["weight"], "payload weight"),
            }
        )
    if tuple(normalized_buckets) != PAYLOAD_BUCKETS:
        raise ContractError("payload distribution changed")
    if sum(bucket["weight"] for bucket in normalized_buckets) != distribution["weight_total"]:
        raise ContractError("payload weights do not match weight_total")
    if distribution["weight_total"] != 100:
        raise ContractError("payload weight_total must be 100")
    if distribution["generator"] != "sha256-counter-stream-synthetic-opaque-bytes":
        raise ContractError("unknown synthetic payload generator")
    if distribution["semantic_content"] != "none":
        raise ContractError("benchmark payloads must not contain semantic content")
    golden_evidence = _exact_list(distribution["golden_evidence"], "payload golden evidence")
    normalized_golden: list[dict[str, Any]] = []
    for item in golden_evidence:
        golden = _exact_dict(
            item,
            {"event_count", "payload_bytes", "payload_stream_sha256"},
            "payload golden evidence item",
        )
        normalized_golden.append(
            {
                "event_count": _positive_int(golden["event_count"], "golden event_count"),
                "payload_bytes": _positive_int(golden["payload_bytes"], "golden payload_bytes"),
                "payload_stream_sha256": _nonempty(
                    golden["payload_stream_sha256"], "golden payload digest"
                ),
            }
        )
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", golden["payload_stream_sha256"]):
            raise ContractError("payload golden digest is not canonical sha256")
    if tuple(normalized_golden) != PAYLOAD_GOLDEN_EVIDENCE:
        raise ContractError("fixed payload golden evidence changed")

    measurement = _exact_dict(
        plan["measurement"],
        {
            "warmup_repetitions",
            "measured_repetitions",
            "layout_order",
            "worker_isolation",
            "worker_timeout_seconds",
            "timer",
            "statistics",
            "operations",
            "fresh_temp_root_per_worker",
            "cache_policy",
            "durability",
            "pull_base_fraction",
            "backup_format",
            "derived_index_in_repository",
        },
        "measurement",
    )
    if measurement["warmup_repetitions"] != QUALIFICATION_WARMUPS:
        raise ContractError("warmup count changed")
    if measurement["measured_repetitions"] != QUALIFICATION_REPETITIONS:
        raise ContractError("measured repetition count changed")
    if measurement["layout_order"] != "alternate-first-layout-by-cycle":
        raise ContractError("layout order policy changed")
    if measurement["worker_isolation"] != "fresh-python-process-per-layout-repetition":
        raise ContractError("worker isolation changed")
    if measurement["worker_timeout_seconds"] != WORKER_TIMEOUT_SECONDS:
        raise ContractError("worker timeout changed")
    if measurement["timer"] != "time.perf_counter_ns":
        raise ContractError("unknown timer")
    statistics_schema = _exact_dict(measurement["statistics"], {"median", "p95"}, "statistics")
    if statistics_schema != {"median": "nearest-rank-p50", "p95": "nearest-rank-p95"}:
        raise ContractError("unknown statistics definition")
    if measurement["operations"] != list(OPERATIONS):
        raise ContractError("unknown, missing, or reordered operation metric")
    if _bool(measurement["fresh_temp_root_per_worker"], "fresh_temp_root_per_worker") is not True:
        raise ContractError("fresh temp root is required")
    if measurement["cache_policy"] != "one-warmup-then-as-observed-no-privileged-cache-drop":
        raise ContractError("unknown cache policy")
    if measurement["durability"] != "fsync-file-and-containing-directory":
        raise ContractError("unknown durability policy")
    _validate_ratio(measurement["pull_base_fraction"], "pull_base_fraction")
    if measurement["pull_base_fraction"] != {"numerator": 9, "denominator": 10}:
        raise ContractError("pull base fraction changed")
    if measurement["backup_format"] != "uncompressed-tar-canonical-files-only":
        raise ContractError("unknown backup format")
    if _bool(measurement["derived_index_in_repository"], "derived_index_in_repository") is not False:
        raise ContractError("derived index must stay outside repository size")

    metrics = _exact_dict(
        plan["metrics"],
        {"duration_unit", "duration_metrics", "scalar_metrics", "required_statistics"},
        "metrics",
    )
    if metrics["duration_unit"] != "nanoseconds":
        raise ContractError("unknown duration unit")
    if metrics["duration_metrics"] != list(OPERATIONS):
        raise ContractError("unknown duration metric")
    if metrics["scalar_metrics"] != list(SCALAR_METRICS):
        raise ContractError("unknown scalar metric")
    if metrics["required_statistics"] != ["median", "p95"]:
        raise ContractError("unknown statistics output")

    filesystem = _exact_dict(
        plan["filesystem_metadata"],
        {"fields", "path_scope", "filesystem_type_observation", "mount_source_collection"},
        "filesystem metadata",
    )
    if filesystem["fields"] != list(FILESYSTEM_METADATA_FIELDS):
        raise ContractError("unknown filesystem metadata field")
    if filesystem["path_scope"] != "synthetic-temporary-root-only":
        raise ContractError("filesystem metadata escaped the temporary root")
    if filesystem["filesystem_type_observation"] != "unavailable-in-python-standard-library":
        raise ContractError("filesystem type observation policy changed")
    if filesystem["mount_source_collection"] != "forbidden":
        raise ContractError("mount source collection must remain forbidden")

    _validate_budgets(plan["budgets"])
    cleanup = _exact_dict(
        plan["cleanup"],
        {
            "temporary_root",
            "remove_on_success",
            "remove_on_failure",
            "persistent_artifacts",
            "network",
            "credentials",
            "live_state",
        },
        "cleanup",
    )
    if cleanup != {
        "temporary_root": "python-tempfile-per-worker",
        "remove_on_success": True,
        "remove_on_failure": True,
        "persistent_artifacts": "none-stdout-json-only",
        "network": "forbidden",
        "credentials": "forbidden",
        "live_state": "forbidden",
    }:
        raise ContractError("cleanup/safety policy changed")
    return plan


def _validate_budgets(value: Any) -> None:
    budgets = _exact_dict(
        value,
        {"schema_version", "qualification_rule", "selection_rule", "common_by_event_count", "layout_limits"},
        "budgets",
    )
    if budgets["schema_version"] != "watari.storage-benchmark-budget.v1":
        raise ContractError("unknown budget schema")
    if budgets["qualification_rule"] != "all-common-and-layout-specific-limits-must-pass":
        raise ContractError("unknown qualification rule")
    if budgets["selection_rule"] != "G003-prefers-eligible-loose-else-eligible-pack-else-no-selection":
        raise ContractError("unknown selection rule")
    common = _exact_list(budgets["common_by_event_count"], "common budgets")
    if [item.get("event_count") for item in common if type(item) is dict] != list(QUALIFICATION_EVENT_COUNTS):
        raise ContractError("budget scales must be exactly 10k and 100k")
    for item in common:
        limit = _exact_dict(
            item,
            {
                "event_count",
                "duration_p95_ns",
                "repo_size_bytes_max",
                "working_size_bytes_max",
                "peak_rss_bytes_max",
                "repo_to_payload_ratio_max",
                "working_to_payload_ratio_max",
            },
            "common budget",
        )
        _positive_int(limit["event_count"], "budget event_count")
        durations = _exact_dict(limit["duration_p95_ns"], OPERATIONS, "duration budget")
        for operation in OPERATIONS:
            _positive_int(durations[operation], f"duration budget {operation}")
        for key in ("repo_size_bytes_max", "working_size_bytes_max", "peak_rss_bytes_max"):
            _positive_int(limit[key], key)
        _validate_ratio(limit["repo_to_payload_ratio_max"], "repo_to_payload_ratio_max")
        _validate_ratio(limit["working_to_payload_ratio_max"], "working_to_payload_ratio_max")

    layout_limits = _exact_list(budgets["layout_limits"], "layout budgets")
    if [item.get("layout_id") for item in layout_limits if type(item) is dict] != list(LAYOUT_IDS):
        raise ContractError("unknown layout budget")
    for item in layout_limits:
        limit = _exact_dict(
            item,
            {
                "layout_id",
                "file_count_max_by_event_count",
                "inode_count_max_by_event_count",
                "mergeability_proxy_conflicting_paths_max",
                "single_corruption_blast_radius_events_max",
                "single_corruption_blast_radius_bytes_max",
            },
            "layout budget",
        )
        for table_name in ("file_count_max_by_event_count", "inode_count_max_by_event_count"):
            table = _exact_list(limit[table_name], table_name)
            if [row.get("event_count") for row in table if type(row) is dict] != list(
                QUALIFICATION_EVENT_COUNTS
            ):
                raise ContractError(f"{table_name} scales changed")
            for row in table:
                exact_row = _exact_dict(row, {"event_count", "max"}, table_name)
                _positive_int(exact_row["event_count"], f"{table_name}.event_count")
                _positive_int(exact_row["max"], f"{table_name}.max")
        for key in (
            "mergeability_proxy_conflicting_paths_max",
            "single_corruption_blast_radius_events_max",
            "single_corruption_blast_radius_bytes_max",
        ):
            _positive_int(limit[key], key, allow_zero=key.startswith("mergeability"))
    if budgets != PLAN["budgets"]:
        raise ContractError("frozen D011 budget value changed")


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def plan_digest() -> str:
    validate_plan(PLAN)
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(PLAN)).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    encoded = _canonical_json_bytes(value) + b"\n"
    with path.open("wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ContractError("durability boundary requires a regular file")
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _copy_file_durable(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise ContractError("copy source must be a regular file")
    shutil.copy2(source, destination)
    _fsync_file(destination)


def _fsync_tree(root: Path) -> None:
    for current, directories, filenames in os.walk(root, topdown=False):
        current_path = Path(current)
        for filename in filenames:
            _fsync_file(current_path / filename)
        for directory in directories:
            path = current_path / directory
            if path.is_symlink() or not path.is_dir():
                raise ContractError("durability boundary requires regular directories")
        _fsync_directory(current_path)


def _copytree_durable(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination)
    _fsync_tree(destination)


def _payload_size(index: int, seed: int, branch: str) -> int:
    digest = hashlib.sha256(f"size\x00{seed}\x00{branch}\x00{index}".encode("ascii")).digest()
    point = int.from_bytes(digest[:8], "big") % 100
    cumulative = 0
    for bucket in PAYLOAD_BUCKETS:
        cumulative += bucket["weight"]
        if point < cumulative:
            return bucket["bytes"]
    raise AssertionError("payload distribution is not exhaustive")


def _opaque_payload(index: int, seed: int, branch: str) -> bytes:
    size = _payload_size(index, seed, branch)
    prefix = f"opaque\x00{seed}\x00{branch}\x00{index}\x00".encode("ascii")
    output = bytearray()
    counter = 0
    while len(output) < size:
        output.extend(hashlib.sha256(prefix + struct.pack(">Q", counter)).digest())
        counter += 1
    return bytes(output[:size])


def _record(index: int, seed: int, branch: str = "main") -> tuple[str, bytes]:
    payload = _opaque_payload(index, seed, branch)
    locator = hashlib.sha256(b"watari-bench-locator\x00" + payload).hexdigest()
    return locator, payload


@functools.lru_cache(maxsize=32)
def _expected_payload_bytes(
    event_count: int,
    seed: int,
    branch: str = "main",
    start_index: int = 0,
) -> int:
    """Return the exact fixed-generator byte total without materializing payloads."""

    return sum(
        _payload_size(start_index + offset, seed, branch) for offset in range(event_count)
    )


@functools.lru_cache(maxsize=16)
def _expected_payload_stream_sha256(
    event_count: int,
    seed: int,
    branch: str = "main",
    start_index: int = 0,
) -> str:
    """Recompute the exact framed byte stream produced by the fixed generator."""

    hasher = hashlib.sha256()
    for offset in range(event_count):
        payload = _opaque_payload(start_index + offset, seed, branch)
        _update_payload_stream_digest(hasher, payload)
    return "sha256:" + hasher.hexdigest()


def _contract_payload_evidence(event_count: int, seed: int) -> tuple[int, str]:
    if seed == FIXED_SEED:
        for golden in PAYLOAD_GOLDEN_EVIDENCE:
            if golden["event_count"] == event_count:
                return golden["payload_bytes"], golden["payload_stream_sha256"]
    return (
        _expected_payload_bytes(event_count, seed),
        _expected_payload_stream_sha256(event_count, seed),
    )


def _update_payload_stream_digest(hasher: Any, payload: bytes) -> None:
    """Frame each payload length so the digest binds bytes, lengths, and order."""

    hasher.update(struct.pack(">Q", len(payload)))
    hasher.update(payload)


def _head(layout_id: str, event_count: int, seed: int, branch: str) -> dict[str, Any]:
    return {
        "schema_version": "watari.storage-bench-head.v1",
        "layout_id": layout_id,
        "event_count": event_count,
        "seed": seed,
        "branch": branch,
    }


def _validate_head(value: Any) -> dict[str, Any]:
    head = _exact_dict(value, {"schema_version", "layout_id", "event_count", "seed", "branch"}, "head")
    if head["schema_version"] != "watari.storage-bench-head.v1":
        raise ContractError("unknown storage head schema")
    if head["layout_id"] not in LAYOUT_IDS:
        raise ContractError("unknown head layout")
    _positive_int(head["event_count"], "head.event_count", allow_zero=True)
    _positive_int(head["seed"], "head.seed")
    _nonempty(head["branch"], "head.branch")
    return head


def _create_store(
    root: Path,
    layout_id: str,
    event_count: int,
    seed: int,
    segment_event_limit: int,
    *,
    start_index: int = 0,
    branch: str = "main",
) -> tuple[int, str]:
    if layout_id not in LAYOUT_IDS:
        raise ContractError("unknown layout")
    _positive_int(event_count, "event_count")
    _positive_int(segment_event_limit, "segment_event_limit")
    root.mkdir(parents=True, exist_ok=False)
    objects = root / "objects"
    objects.mkdir()
    index: dict[str, dict[str, Any]] = {}
    seen_locators: set[str] = set()
    payload_bytes = 0
    payload_stream_hasher = hashlib.sha256()
    if layout_id == LOOSE_LAYOUT:
        for offset in range(event_count):
            locator, payload = _record(start_index + offset, seed, branch)
            if locator in seen_locators:
                raise ContractError("duplicate synthetic locator")
            seen_locators.add(locator)
            path = objects / f"{locator}.obj"
            with path.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            index[locator] = {"path": f"objects/{path.name}", "offset": 0, "length": len(payload)}
            payload_bytes += len(payload)
            _update_payload_stream_digest(payload_stream_hasher, payload)
    else:
        for segment_start in range(0, event_count, segment_event_limit):
            segment_count = min(segment_event_limit, event_count - segment_start)
            temporary = objects / f"segment-{segment_start:012d}.tmp"
            segment_hasher = hashlib.sha256()
            pending: list[tuple[str, int, int]] = []
            with temporary.open("xb") as handle:
                handle.write(PACK_MAGIC)
                segment_hasher.update(PACK_MAGIC)
                for local_offset in range(segment_count):
                    locator, payload = _record(start_index + segment_start + local_offset, seed, branch)
                    if locator in seen_locators:
                        raise ContractError("duplicate synthetic locator")
                    seen_locators.add(locator)
                    record_header = bytes.fromhex(locator) + struct.pack(">Q", len(payload))
                    payload_offset = handle.tell() + len(record_header)
                    handle.write(record_header)
                    handle.write(payload)
                    segment_hasher.update(record_header)
                    segment_hasher.update(payload)
                    pending.append((locator, payload_offset, len(payload)))
                    payload_bytes += len(payload)
                    _update_payload_stream_digest(payload_stream_hasher, payload)
                handle.flush()
                os.fsync(handle.fileno())
            segment_name = f"{segment_hasher.hexdigest()}.pack"
            final_path = objects / segment_name
            if final_path.exists():
                raise ContractError("duplicate immutable pack segment")
            os.replace(temporary, final_path)
            for locator, payload_offset, length in pending:
                index[locator] = {
                    "path": f"objects/{segment_name}",
                    "offset": payload_offset,
                    "length": length,
                }
    _fsync_directory(objects)
    _write_json(root / "head.json", _head(layout_id, event_count, seed, branch))
    _write_json(root / "index.json", {"schema_version": "watari.storage-bench-index.v1", "objects": index})
    _fsync_directory(root)
    return payload_bytes, "sha256:" + payload_stream_hasher.hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="ascii") as handle:
        return json.load(handle, object_pairs_hook=_reject_duplicate_pairs)


def _load_index(root: Path) -> dict[str, dict[str, Any]]:
    value = _exact_dict(_read_json(root / "index.json"), {"schema_version", "objects"}, "derived index")
    if value["schema_version"] != "watari.storage-bench-index.v1":
        raise ContractError("unknown derived index schema")
    if type(value["objects"]) is not dict:
        raise ContractError("derived index objects must be an object")
    result: dict[str, dict[str, Any]] = {}
    for locator, raw_entry in value["objects"].items():
        if type(locator) is not str or len(locator) != 64:
            raise ContractError("invalid synthetic locator")
        try:
            bytes.fromhex(locator)
        except ValueError as error:
            raise ContractError("invalid hexadecimal synthetic locator") from error
        entry = _exact_dict(raw_entry, {"path", "offset", "length"}, "index entry")
        _nonempty(entry["path"], "index path")
        _positive_int(entry["offset"], "index offset", allow_zero=True)
        _positive_int(entry["length"], "index length")
        result[locator] = entry
    return result


def _status(root: Path) -> int:
    head = _validate_head(_read_json(root / "head.json"))
    index = _load_index(root)
    if len(index) != head["event_count"]:
        raise ContractError("head/index event count mismatch")
    observed = 0
    storage_units: dict[str, os.stat_result] = {}
    for locator, entry in index.items():
        relative = Path(entry["path"])
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or len(relative.parts) != 2
            or relative.parts[0] != "objects"
        ):
            raise ContractError("index escaped the synthetic root")
        path = root / relative
        storage_stat = storage_units.get(entry["path"])
        if storage_stat is None:
            storage_stat = path.lstat()
            if not stat.S_ISREG(storage_stat.st_mode):
                raise ContractError("index referenced a non-regular storage unit")
            storage_units[entry["path"]] = storage_stat
        if entry["offset"] + entry["length"] > storage_stat.st_size:
            raise ContractError("index entry is outside its storage unit")
        if head["layout_id"] == LOOSE_LAYOUT:
            if path.suffix != ".obj" or entry["offset"] != 0 or path.stem != locator:
                raise ContractError("loose index entry does not match its storage unit")
        elif head["layout_id"] == PACK_LAYOUT:
            if path.suffix != ".pack" or entry["offset"] < len(PACK_MAGIC) + 40:
                raise ContractError("pack index entry does not match its storage unit")
        observed += 1
    return observed


def _rebuild(root: Path) -> int:
    head = _validate_head(_read_json(root / "head.json"))
    layout_id = head["layout_id"]
    objects = root / "objects"
    rebuilt: dict[str, dict[str, Any]] = {}
    if layout_id == LOOSE_LAYOUT:
        for path in sorted(objects.glob("*.obj")):
            if len(path.stem) != 64:
                raise ContractError("invalid loose object filename")
            rebuilt[path.stem] = {"path": f"objects/{path.name}", "offset": 0, "length": path.stat().st_size}
    elif layout_id == PACK_LAYOUT:
        for path in sorted(objects.glob("*.pack")):
            file_size = path.stat().st_size
            with path.open("rb") as handle:
                if handle.read(len(PACK_MAGIC)) != PACK_MAGIC:
                    raise ContractError("invalid pack magic")
                while handle.tell() < file_size:
                    header = handle.read(40)
                    if len(header) != 40:
                        raise ContractError("truncated pack record header")
                    locator = header[:32].hex()
                    length = struct.unpack(">Q", header[32:])[0]
                    payload_offset = handle.tell()
                    if length < 1 or payload_offset + length > file_size:
                        raise ContractError("pack record exceeds segment")
                    handle.seek(length, io.SEEK_CUR)
                    if locator in rebuilt:
                        raise ContractError("duplicate object locator")
                    rebuilt[locator] = {
                        "path": f"objects/{path.name}",
                        "offset": payload_offset,
                        "length": length,
                    }
    else:
        raise ContractError("unknown layout during rebuild")
    if len(rebuilt) != head["event_count"]:
        raise ContractError("rebuild event count mismatch")
    _write_json(root / "index.json", {"schema_version": "watari.storage-bench-index.v1", "objects": rebuilt})
    _fsync_directory(root)
    return len(rebuilt)


def _canonical_paths(root: Path) -> list[Path]:
    paths = [root / "head.json"]
    paths.extend(sorted((root / "objects").iterdir()))
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ContractError("canonical storage contains a non-regular file")
    return paths


def _copy_canonical(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "objects").mkdir()
    _copy_file_durable(source / "head.json", destination / "head.json")
    for path in sorted((source / "objects").iterdir()):
        _copy_file_durable(path, destination / "objects" / path.name)
    _fsync_directory(destination / "objects")
    _fsync_directory(destination)


def _tree_footprint(root: Path) -> tuple[int, int, int, int]:
    repo_size = 0
    working_size = 0
    files = 0
    inodes: set[tuple[int, int]] = set()
    for current, directories, filenames in os.walk(root):
        current_path = Path(current)
        for name in [".", *directories, *filenames]:
            path = current_path if name == "." else current_path / name
            stat = path.lstat()
            inodes.add((stat.st_dev, stat.st_ino))
            if path.is_file():
                files += 1
                working_size += stat.st_blocks * 512
                if path.name != "index.json":
                    repo_size += stat.st_size
    return repo_size, working_size, len(inodes), files


def _base_event_count(event_count: int, segment_event_limit: int) -> int:
    target = event_count * 9 // 10
    aligned = target - (target % segment_event_limit)
    if aligned == 0 and event_count > segment_event_limit:
        aligned = segment_event_limit
    if aligned >= event_count:
        aligned = max(0, event_count - segment_event_limit)
    return aligned


def _prepare_pull_base(
    source: Path,
    destination: Path,
    layout_id: str,
    event_count: int,
    seed: int,
    segment_event_limit: int,
) -> int:
    base_count = _base_event_count(event_count, segment_event_limit)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "objects").mkdir()
    full_index = _load_index(source)
    required_paths: set[str] = set()
    for index in range(base_count):
        locator, _ = _record(index, seed)
        required_paths.add(full_index[locator]["path"])
    for relative in sorted(required_paths):
        source_path = source / relative
        _copy_file_durable(source_path, destination / "objects" / source_path.name)
    _fsync_directory(destination / "objects")
    _write_json(destination / "head.json", _head(layout_id, base_count, seed, "main"))
    _rebuild(destination)
    return base_count


def _pull_missing(source: Path, destination: Path) -> None:
    destination_objects = destination / "objects"
    for source_path in sorted((source / "objects").iterdir()):
        destination_path = destination_objects / source_path.name
        if not destination_path.exists():
            _copy_file_durable(source_path, destination_path)
    _fsync_directory(destination_objects)
    _copy_file_durable(source / "head.json", destination / "head.json")
    index_path = destination / "index.json"
    if index_path.exists():
        index_path.unlink()
    _rebuild(destination)
    _status(destination)


def _backup(source: Path, archive: Path) -> None:
    with tarfile.open(archive, mode="w") as bundle:
        for path in _canonical_paths(source):
            bundle.add(path, arcname=path.relative_to(source), recursive=False)
    _fsync_file(archive)
    _fsync_directory(archive.parent)
    with tarfile.open(archive, mode="r") as bundle:
        members = bundle.getmembers()
        if not members or any(member.issym() or member.islnk() for member in members):
            raise ContractError("backup verification failed")


def _path_digest_map(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.name == "index.json":
            continue
        result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _mergeability_proxy(root: Path, layout_id: str, seed: int, segment_event_limit: int) -> dict[str, int]:
    append_events = 2
    left = root / "merge-left"
    right = root / "merge-right"
    _create_store(
        left,
        layout_id,
        append_events,
        seed,
        segment_event_limit,
        start_index=1_000_000,
        branch="left",
    )
    _create_store(
        right,
        layout_id,
        append_events,
        seed,
        segment_event_limit,
        start_index=1_000_000,
        branch="right",
    )
    left_paths = _path_digest_map(left)
    right_paths = _path_digest_map(right)
    common = set(left_paths) & set(right_paths)
    conflicts = sum(left_paths[path] != right_paths[path] for path in common)
    identical = len(common) - conflicts
    return {
        "branch_append_events": append_events,
        "conflicting_paths": conflicts,
        "identical_paths": identical,
        "left_only_paths": len(set(left_paths) - set(right_paths)),
        "right_only_paths": len(set(right_paths) - set(left_paths)),
        "union_paths": len(set(left_paths) | set(right_paths)),
    }


def _corruption_probe(source: Path, layout_id: str) -> dict[str, Any]:
    head = _validate_head(_read_json(source / "head.json"))
    index = _load_index(source)
    if not index:
        raise ContractError("corruption probe requires at least one object")
    first, _ = _record(0, head["seed"], head["branch"])
    if first not in index:
        raise ContractError("corruption probe could not find the first generated event")
    target_relative = index[first]["path"]
    same_container = [entry for entry in index.values() if entry["path"] == target_relative]
    target = source / target_relative
    original_digest = hashlib.sha256(target.read_bytes()).digest()
    total_bytes = sum(entry["length"] for entry in same_container)
    with target.open("r+b") as handle:
        offset = index[first]["offset"] + min(index[first]["length"] - 1, index[first]["length"] // 2)
        handle.seek(offset)
        original = handle.read(1)
        if len(original) != 1:
            raise ContractError("corruption probe could not read target byte")
        handle.seek(offset)
        handle.write(bytes([original[0] ^ 0x01]))
        handle.flush()
        os.fsync(handle.fileno())
    detected = hashlib.sha256(target.read_bytes()).digest() != original_digest
    expected_events = 1 if layout_id == LOOSE_LAYOUT else len(same_container)
    return {
        "probe": "single-bit-flip-in-one-authentication-unit-proxy",
        "detected": detected,
        "events": expected_events,
        "bytes": total_bytes,
    }


def _environment_metadata(root: Path) -> dict[str, Any]:
    statvfs = os.statvfs(root)
    root_stat = os.stat(root)
    parent_stat = os.stat(root.parent)
    release = platform.release()
    wsl2 = platform.system() == "Linux" and "microsoft-standard-WSL2" in release
    try:
        os_release = platform.freedesktop_os_release()
    except OSError:
        os_release = {}
    distribution_id = os_release.get("ID", "unknown")
    distribution_version_id = os_release.get("VERSION_ID", "unknown")
    python_supported = sys.version_info >= (3, 11)
    return {
        "system": platform.system(),
        "release": release,
        "machine": platform.machine(),
        "distribution_id": distribution_id,
        "distribution_version_id": distribution_version_id,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "wsl2_detected": wsl2,
        "required_platform_match": (
            wsl2
            and platform.system() == "Linux"
            and distribution_id == "ubuntu"
            and distribution_version_id == "24.04"
            and python_supported
        ),
        "statvfs_block_size": statvfs.f_bsize,
        "statvfs_fragment_size": statvfs.f_frsize,
        "statvfs_name_max": statvfs.f_namemax,
        "filesystem_type": "unavailable-in-python-standard-library",
        "cache_policy": "as-observed-no-privileged-cache-drop",
        "temp_root_device_id": root_stat.st_dev,
        "temp_root_same_device": root_stat.st_dev == parent_stat.st_dev,
    }


def _duration(callable_: Any) -> tuple[int, Any]:
    started = time.perf_counter_ns()
    result = callable_()
    return time.perf_counter_ns() - started, result


def _peak_rss_bytes() -> int:
    # Linux reports ru_maxrss in KiB. D011 supports Ubuntu/WSL2 only.
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


def _worker_sample(
    layout_id: str,
    event_count: int,
    seed: int,
    repetition: int,
    warmup: bool,
    segment_event_limit: int,
) -> dict[str, Any]:
    if layout_id not in LAYOUT_IDS:
        raise ContractError("unknown worker layout")
    _positive_int(event_count, "worker event_count")
    _positive_int(seed, "worker seed")
    _positive_int(repetition, "worker repetition", allow_zero=True)
    _bool(warmup, "worker warmup")
    _positive_int(segment_event_limit, "worker segment_event_limit")
    temporary_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="worker-", dir=Path.cwd()) as temporary:
        temporary_path = Path(temporary)
        source = temporary_path / "source"
        durations: dict[str, int] = {}
        durations["create"], payload_evidence = _duration(
            lambda: _create_store(source, layout_id, event_count, seed, segment_event_limit)
        )
        payload_bytes, payload_stream_sha256 = payload_evidence
        durations["status"], observed = _duration(lambda: _status(source))
        if observed != event_count:
            raise ContractError("status did not observe every event")
        repo_size, working_size, inode_count, file_count = _tree_footprint(source)

        clone = temporary_path / "clone"
        durations["clone-equivalent"], _ = _duration(
            lambda: (_copy_canonical(source, clone), _rebuild(clone), _status(clone))
        )

        copy_destination = temporary_path / "copy"
        durations["copy"], _ = _duration(lambda: _copytree_durable(source, copy_destination))

        pull_destination = temporary_path / "pull"
        base_count = _prepare_pull_base(
            source, pull_destination, layout_id, event_count, seed, segment_event_limit
        )
        durations["pull-equivalent"], _ = _duration(lambda: _pull_missing(source, pull_destination))

        index_path = source / "index.json"
        index_path.unlink()
        durations["rebuild"], rebuilt = _duration(lambda: (_rebuild(source), _status(source)))
        if rebuilt[0] != event_count or rebuilt[1] != event_count:
            raise ContractError("rebuild did not restore every event")

        archive = temporary_path / "backup.tar"
        durations["backup"], _ = _duration(lambda: _backup(source, archive))
        mergeability = _mergeability_proxy(temporary_path, layout_id, seed, segment_event_limit)
        corruption = _corruption_probe(source, layout_id)
        environment = _environment_metadata(temporary_path)
        sample = {
            "schema_version": SAMPLE_SCHEMA,
            "layout_id": layout_id,
            "event_count": event_count,
            "seed": seed,
            "repetition": repetition,
            "warmup": warmup,
            "comparison_segment_event_limit": segment_event_limit,
            "pull_base_event_count": base_count,
            "duration_ns": durations,
            "payload_bytes": payload_bytes,
            "payload_stream_sha256": payload_stream_sha256,
            "repo_size_bytes": repo_size,
            "working_size_bytes": working_size,
            "inode_count": inode_count,
            "file_count": file_count,
            "mergeability_proxy": mergeability,
            "single_corruption_blast_radius": corruption,
            "peak_rss_bytes": _peak_rss_bytes(),
            "environment": environment,
            "cleanup_verified": False,
        }
    removed = temporary_path is not None and not temporary_path.exists()
    sample["cleanup_verified"] = removed
    validate_sample(sample, verify_generator_digest=False)
    return sample


def validate_sample(
    value: Any, *, verify_generator_digest: bool = True
) -> dict[str, Any]:
    sample = _exact_dict(
        value,
        {
            "schema_version",
            "layout_id",
            "event_count",
            "seed",
            "repetition",
            "warmup",
            "comparison_segment_event_limit",
            "pull_base_event_count",
            "duration_ns",
            "payload_bytes",
            "payload_stream_sha256",
            "repo_size_bytes",
            "working_size_bytes",
            "inode_count",
            "file_count",
            "mergeability_proxy",
            "single_corruption_blast_radius",
            "peak_rss_bytes",
            "environment",
            "cleanup_verified",
        },
        "benchmark sample",
    )
    if sample["schema_version"] != SAMPLE_SCHEMA:
        raise ContractError("unknown sample schema")
    if sample["layout_id"] not in LAYOUT_IDS:
        raise ContractError("unknown sample layout")
    for key in (
        "event_count",
        "seed",
        "comparison_segment_event_limit",
        "payload_bytes",
        "repo_size_bytes",
        "working_size_bytes",
        "inode_count",
        "file_count",
        "peak_rss_bytes",
    ):
        _positive_int(sample[key], key)
    _positive_int(sample["repetition"], "repetition", allow_zero=True)
    _positive_int(sample["pull_base_event_count"], "pull_base_event_count", allow_zero=True)
    _bool(sample["warmup"], "warmup")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", _nonempty(
        sample["payload_stream_sha256"], "payload_stream_sha256"
    )):
        raise ContractError("payload stream digest is not canonical sha256")
    expected_payload_bytes, expected_payload_digest = _contract_payload_evidence(
        sample["event_count"], sample["seed"]
    )
    if sample["payload_bytes"] != expected_payload_bytes:
        raise ContractError("payload byte total does not match the fixed generator")
    if verify_generator_digest:
        if sample["payload_stream_sha256"] != expected_payload_digest:
            raise ContractError("payload stream digest does not match the fixed generator")
    durations = _exact_dict(sample["duration_ns"], OPERATIONS, "duration metrics")
    for operation in OPERATIONS:
        _positive_int(durations[operation], f"duration {operation}")
    mergeability = _exact_dict(
        sample["mergeability_proxy"],
        {
            "branch_append_events",
            "conflicting_paths",
            "identical_paths",
            "left_only_paths",
            "right_only_paths",
            "union_paths",
        },
        "mergeability proxy",
    )
    for key, metric in mergeability.items():
        _positive_int(metric, f"mergeability.{key}", allow_zero=key != "branch_append_events")
    branch_units = (
        2
        if sample["layout_id"] == LOOSE_LAYOUT
        else math.ceil(2 / sample["comparison_segment_event_limit"])
    )
    expected_mergeability = {
        "branch_append_events": 2,
        "conflicting_paths": 1,
        "identical_paths": 0,
        "left_only_paths": branch_units,
        "right_only_paths": branch_units,
        "union_paths": 1 + 2 * branch_units,
    }
    if mergeability != expected_mergeability:
        raise ContractError("mergeability proxy is inconsistent with the fixed two-event branches")
    corruption = _exact_dict(
        sample["single_corruption_blast_radius"],
        {"probe", "detected", "events", "bytes"},
        "corruption blast radius",
    )
    if corruption["probe"] != "single-bit-flip-in-one-authentication-unit-proxy":
        raise ContractError("unknown corruption probe")
    if _bool(corruption["detected"], "corruption detected") is not True:
        raise ContractError("corruption probe was not detected")
    _positive_int(corruption["events"], "corruption events")
    _positive_int(corruption["bytes"], "corruption bytes")
    expected_corruption_events = (
        1
        if sample["layout_id"] == LOOSE_LAYOUT
        else min(sample["event_count"], sample["comparison_segment_event_limit"])
    )
    expected_corruption_bytes = _expected_payload_bytes(
        expected_corruption_events, sample["seed"]
    )
    if corruption["events"] != expected_corruption_events:
        raise ContractError("corruption event radius does not match the first storage unit")
    if corruption["bytes"] != expected_corruption_bytes:
        raise ContractError("corruption byte radius does not match the fixed generator")
    environment = _exact_dict(sample["environment"], FILESYSTEM_METADATA_FIELDS, "environment")
    for key in (
        "system",
        "release",
        "machine",
        "distribution_id",
        "distribution_version_id",
        "python_implementation",
        "python_version",
        "filesystem_type",
        "cache_policy",
    ):
        _nonempty(environment[key], f"environment.{key}")
    for key in ("wsl2_detected", "required_platform_match", "temp_root_same_device"):
        _bool(environment[key], f"environment.{key}")
    for key in ("statvfs_block_size", "statvfs_fragment_size", "statvfs_name_max"):
        _positive_int(environment[key], f"environment.{key}")
    _positive_int(environment["temp_root_device_id"], "environment.temp_root_device_id", allow_zero=True)
    if environment["filesystem_type"] != "unavailable-in-python-standard-library":
        raise ContractError("unknown filesystem type observation")
    if environment["cache_policy"] != "as-observed-no-privileged-cache-drop":
        raise ContractError("unknown sample cache policy")
    version_match = re.fullmatch(r"([0-9]+)\.([0-9]+)(?:\.[0-9]+)?", environment["python_version"])
    if version_match is None:
        raise ContractError("environment python_version is not major.minor[.patch]")
    python_supported = tuple(int(part) for part in version_match.groups()) >= (3, 11)
    expected_wsl2 = (
        environment["system"] == "Linux"
        and "microsoft-standard-WSL2" in environment["release"]
    )
    if environment["wsl2_detected"] != expected_wsl2:
        raise ContractError("wsl2_detected does not match environment metadata")
    expected_platform_match = (
        expected_wsl2
        and environment["distribution_id"] == "ubuntu"
        and environment["distribution_version_id"] == "24.04"
        and python_supported
    )
    if environment["required_platform_match"] != expected_platform_match:
        raise ContractError("required_platform_match does not match environment metadata")
    if environment["temp_root_same_device"] is not True:
        raise ContractError("sample temporary root crossed devices")
    if _bool(sample["cleanup_verified"], "cleanup_verified") is not True:
        raise ContractError("temporary worker root was not removed")
    return sample


def _worker_subprocess(
    layout_id: str,
    event_count: int,
    seed: int,
    repetition: int,
    warmup: bool,
    segment_event_limit: int,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--_worker",
        "--layout",
        layout_id,
        "--event-count",
        str(event_count),
        "--seed",
        str(seed),
        "--repetition",
        str(repetition),
        "--segment-event-limit",
        str(segment_event_limit),
    ]
    if warmup:
        command.append("--warmup")
    supervisor_path: Path | None = None
    sample: dict[str, Any] | None = None
    with tempfile.TemporaryDirectory(prefix="watari-d011-supervisor-") as supervisor:
        supervisor_path = Path(supervisor)
        (supervisor_path / ".watari-d011-supervisor").write_text(
            SUPERVISOR_MARKER, encoding="ascii"
        )
        completed = subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=WORKER_TIMEOUT_SECONDS,
            cwd=supervisor_path,
        )
        if completed.returncode != 0:
            raise ContractError(
                f"benchmark worker failed ({completed.returncode}): {completed.stderr.strip()[:500]}"
            )
        try:
            sample = json.loads(completed.stdout, object_pairs_hook=_reject_duplicate_pairs)
        except json.JSONDecodeError as error:
            raise ContractError("benchmark worker returned invalid JSON") from error
        validate_sample(sample)
    if sample is None or supervisor_path is None:
        raise ContractError("benchmark supervisor returned no sample")
    sample["cleanup_verified"] = sample["cleanup_verified"] and not supervisor_path.exists()
    return validate_sample(sample)


def _nearest_rank(values: list[int], percentile: int) -> int:
    if not values:
        raise ContractError("statistics require at least one value")
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered) / 100))
    return ordered[rank - 1]


def _stats(values: list[int]) -> dict[str, int]:
    return {"median": _nearest_rank(values, 50), "p95": _nearest_rank(values, 95)}


def _summarize(layout_id: str, samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        raise ContractError("layout summary requires measured samples")
    duration_summary = {
        operation: _stats([sample["duration_ns"][operation] for sample in samples])
        for operation in OPERATIONS
    }
    scalar_values: dict[str, list[int]] = {metric: [] for metric in SCALAR_METRICS}
    for sample in samples:
        scalar_values["payload_bytes"].append(sample["payload_bytes"])
        scalar_values["repo_size_bytes"].append(sample["repo_size_bytes"])
        scalar_values["working_size_bytes"].append(sample["working_size_bytes"])
        scalar_values["inode_count"].append(sample["inode_count"])
        scalar_values["file_count"].append(sample["file_count"])
        scalar_values["mergeability_proxy_conflicting_paths"].append(
            sample["mergeability_proxy"]["conflicting_paths"]
        )
        scalar_values["single_corruption_blast_radius_events"].append(
            sample["single_corruption_blast_radius"]["events"]
        )
        scalar_values["single_corruption_blast_radius_bytes"].append(
            sample["single_corruption_blast_radius"]["bytes"]
        )
        scalar_values["peak_rss_bytes"].append(sample["peak_rss_bytes"])
    return {
        "layout_id": layout_id,
        "samples": samples,
        "summary": {
            "duration_ns": duration_summary,
            "scalar": {metric: _stats(values) for metric, values in scalar_values.items()},
        },
    }


def _budget_for_event_count(event_count: int) -> dict[str, Any] | None:
    for budget in PLAN["budgets"]["common_by_event_count"]:
        if budget["event_count"] == event_count:
            return budget
    return None


def _layout_budget(layout_id: str) -> dict[str, Any]:
    for budget in PLAN["budgets"]["layout_limits"]:
        if budget["layout_id"] == layout_id:
            return budget
    raise ContractError("missing layout budget")


def _table_limit(table: list[dict[str, int]], event_count: int) -> int:
    for row in table:
        if row["event_count"] == event_count:
            return row["max"]
    raise ContractError("missing scale-specific layout limit")


def _budget_evaluation(event_count: int, layouts: list[dict[str, Any]]) -> dict[str, Any]:
    common = _budget_for_event_count(event_count)
    if common is None:
        return {"applicable": False, "all_passed": None, "checks": []}
    checks: list[dict[str, Any]] = []
    for layout in layouts:
        layout_id = layout["layout_id"]
        summary = layout["summary"]
        for operation in OPERATIONS:
            checks.append(
                {
                    "layout_id": layout_id,
                    "metric": f"duration_ns.{operation}.p95",
                    "observed": summary["duration_ns"][operation]["p95"],
                    "limit": common["duration_p95_ns"][operation],
                    "passed": summary["duration_ns"][operation]["p95"]
                    <= common["duration_p95_ns"][operation],
                }
            )
        scalar = summary["scalar"]
        scalar_limits = {
            "repo_size_bytes": common["repo_size_bytes_max"],
            "working_size_bytes": common["working_size_bytes_max"],
            "peak_rss_bytes": common["peak_rss_bytes_max"],
        }
        specific = _layout_budget(layout_id)
        scalar_limits.update(
            {
                "file_count": _table_limit(specific["file_count_max_by_event_count"], event_count),
                "inode_count": _table_limit(specific["inode_count_max_by_event_count"], event_count),
                "mergeability_proxy_conflicting_paths": specific["mergeability_proxy_conflicting_paths_max"],
                "single_corruption_blast_radius_events": specific[
                    "single_corruption_blast_radius_events_max"
                ],
                "single_corruption_blast_radius_bytes": specific["single_corruption_blast_radius_bytes_max"],
            }
        )
        for metric, limit in scalar_limits.items():
            observed = scalar[metric]["p95"]
            checks.append(
                {
                    "layout_id": layout_id,
                    "metric": f"{metric}.p95",
                    "observed": observed,
                    "limit": limit,
                    "passed": observed <= limit,
                }
            )
        for metric, ratio_key in (
            ("repo_size_bytes", "repo_to_payload_ratio_max"),
            ("working_size_bytes", "working_to_payload_ratio_max"),
        ):
            observed = scalar[metric]["p95"]
            payload = scalar["payload_bytes"]["p95"]
            ratio = common[ratio_key]
            passed = observed * ratio["denominator"] <= payload * ratio["numerator"]
            checks.append(
                {
                    "layout_id": layout_id,
                    "metric": f"{metric}_to_payload_ratio.p95",
                    "observed": observed,
                    "limit": payload * ratio["numerator"] // ratio["denominator"],
                    "passed": passed,
                }
            )
    return {
        "applicable": True,
        "all_passed": all(check["passed"] for check in checks),
        "checks": checks,
    }


def _input_consistency(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        raise ContractError("input consistency requires measured samples")
    first = samples[0]
    return {
        "samples": len(samples),
        "payload_bytes": first["payload_bytes"],
        "payload_stream_sha256": first["payload_stream_sha256"],
        "all_exact_inputs_equal": all(
            sample["payload_bytes"] == first["payload_bytes"]
            and sample["payload_stream_sha256"] == first["payload_stream_sha256"]
            for sample in samples
        ),
    }


def _environment_consistency(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        raise ContractError("environment consistency requires measured samples")
    first_environment = samples[0]["environment"]
    return {
        "samples": len(samples),
        "all_required_platform_match": all(
            sample["environment"]["required_platform_match"] for sample in samples
        ),
        "all_temp_root_same_device": all(
            sample["environment"]["temp_root_same_device"] for sample in samples
        ),
        "all_exact_metadata_equal": all(
            sample["environment"] == first_environment for sample in samples
        ),
    }


def run_benchmark(
    event_count: int,
    warmups: int,
    repetitions: int,
    segment_event_limit: int,
    *,
    qualification: bool,
) -> dict[str, Any]:
    validate_plan(PLAN)
    _positive_int(event_count, "event_count")
    _positive_int(warmups, "warmups", allow_zero=True)
    _positive_int(repetitions, "repetitions")
    _positive_int(segment_event_limit, "segment_event_limit")
    measured: dict[str, list[dict[str, Any]]] = {layout_id: [] for layout_id in LAYOUT_IDS}
    total_cycles = warmups + repetitions
    for cycle in range(total_cycles):
        order = LAYOUT_IDS if cycle % 2 == 0 else tuple(reversed(LAYOUT_IDS))
        warmup = cycle < warmups
        for layout_id in order:
            sample = _worker_subprocess(
                layout_id,
                event_count,
                FIXED_SEED,
                cycle,
                warmup,
                segment_event_limit,
            )
            if not warmup:
                measured[layout_id].append(sample)
    layouts = [_summarize(layout_id, measured[layout_id]) for layout_id in LAYOUT_IDS]
    all_samples = [sample for values in measured.values() for sample in values]
    if not all_samples:
        raise ContractError("benchmark produced no measured environment")
    result = {
        "schema_version": RESULT_SCHEMA,
        "status": "non-authoritative",
        "decision": "proposed",
        "plan_digest": plan_digest(),
        "mode": "synthetic-scale" if qualification else "self-test",
        "event_count": event_count,
        "run_config": {
            "fixed_seed": FIXED_SEED,
            "warmup_repetitions": warmups,
            "measured_repetitions": repetitions,
            "pack_segment_event_limit": segment_event_limit,
            "layout_order": "alternate-first-layout-by-cycle",
        },
        "input_consistency": _input_consistency(all_samples),
        "environment_consistency": _environment_consistency(all_samples),
        "layouts": layouts,
        "budget_evaluation": _budget_evaluation(event_count, layouts),
        "cleanup": {
            "all_worker_roots_removed": all(
                sample["cleanup_verified"] for values in measured.values() for sample in values
            ),
            "persistent_artifacts": "none",
        },
    }
    validate_result(result)
    return result


def validate_result(value: Any) -> dict[str, Any]:
    result = _exact_dict(
        value,
        {
            "schema_version",
            "status",
            "decision",
            "plan_digest",
            "mode",
            "event_count",
            "run_config",
            "input_consistency",
            "environment_consistency",
            "layouts",
            "budget_evaluation",
            "cleanup",
        },
        "benchmark result",
    )
    if result["schema_version"] != RESULT_SCHEMA:
        raise ContractError("unknown result schema")
    if result["status"] != "non-authoritative" or result["decision"] != "proposed":
        raise ContractError("result attempted an authoritative decision")
    if result["plan_digest"] != plan_digest():
        raise ContractError("result plan digest mismatch")
    if result["mode"] not in {"synthetic-scale", "self-test"}:
        raise ContractError("unknown result mode")
    _positive_int(result["event_count"], "result.event_count")
    run_config = _exact_dict(
        result["run_config"],
        {
            "fixed_seed",
            "warmup_repetitions",
            "measured_repetitions",
            "pack_segment_event_limit",
            "layout_order",
        },
        "run config",
    )
    if run_config["fixed_seed"] != FIXED_SEED:
        raise ContractError("result seed mismatch")
    _positive_int(run_config["warmup_repetitions"], "warmup repetitions", allow_zero=True)
    _positive_int(run_config["measured_repetitions"], "measured repetitions")
    _positive_int(run_config["pack_segment_event_limit"], "pack segment event limit")
    if run_config["layout_order"] != "alternate-first-layout-by-cycle":
        raise ContractError("result layout order mismatch")
    if result["mode"] == "synthetic-scale":
        if result["event_count"] not in QUALIFICATION_EVENT_COUNTS:
            raise ContractError("qualification used an unapproved scale")
        if run_config["warmup_repetitions"] != QUALIFICATION_WARMUPS:
            raise ContractError("qualification warmup count mismatch")
        if run_config["measured_repetitions"] != QUALIFICATION_REPETITIONS:
            raise ContractError("qualification repetition count mismatch")
        if run_config["pack_segment_event_limit"] != QUALIFICATION_SEGMENT_EVENTS:
            raise ContractError("qualification pack segment limit mismatch")
    else:
        if result["event_count"] != SELF_TEST_EVENT_COUNT:
            raise ContractError("self-test event count mismatch")
        if run_config["warmup_repetitions"] != SELF_TEST_WARMUPS:
            raise ContractError("self-test warmup count mismatch")
        if run_config["measured_repetitions"] != SELF_TEST_REPETITIONS:
            raise ContractError("self-test repetition count mismatch")
        if run_config["pack_segment_event_limit"] != SELF_TEST_SEGMENT_EVENTS:
            raise ContractError("self-test pack segment limit mismatch")
    input_consistency = _exact_dict(
        result["input_consistency"],
        {"samples", "payload_bytes", "payload_stream_sha256", "all_exact_inputs_equal"},
        "input consistency",
    )
    _positive_int(input_consistency["samples"], "input samples")
    _positive_int(input_consistency["payload_bytes"], "input payload bytes")
    if not re.fullmatch(
        r"sha256:[0-9a-f]{64}",
        _nonempty(input_consistency["payload_stream_sha256"], "input payload digest"),
    ):
        raise ContractError("input consistency digest is not canonical sha256")
    if _bool(input_consistency["all_exact_inputs_equal"], "all_exact_inputs_equal") is not True:
        raise ContractError("layout inputs were not byte-for-byte identical")
    consistency = _exact_dict(
        result["environment_consistency"],
        {
            "samples",
            "all_required_platform_match",
            "all_temp_root_same_device",
            "all_exact_metadata_equal",
        },
        "environment consistency",
    )
    _positive_int(consistency["samples"], "environment samples")
    _bool(consistency["all_required_platform_match"], "all_required_platform_match")
    if _bool(consistency["all_temp_root_same_device"], "all_temp_root_same_device") is not True:
        raise ContractError("worker temporary roots crossed devices")
    if _bool(consistency["all_exact_metadata_equal"], "all_exact_metadata_equal") is not True:
        raise ContractError("layout comparison mixed runtime or filesystem metadata")
    if result["mode"] == "synthetic-scale" and not consistency["all_required_platform_match"]:
        raise ContractError("synthetic scale run requires the WSL2 kernel scope")
    layouts = _exact_list(result["layouts"], "result layouts")
    if [layout.get("layout_id") for layout in layouts if type(layout) is dict] != list(LAYOUT_IDS):
        raise ContractError("unknown result layout")
    all_samples: list[dict[str, Any]] = []
    for layout in layouts:
        exact_layout = _exact_dict(layout, {"layout_id", "samples", "summary"}, "layout result")
        samples = _exact_list(exact_layout["samples"], "layout samples")
        if len(samples) != run_config["measured_repetitions"]:
            raise ContractError("measured sample count mismatch")
        expected_repetitions = list(
            range(
                run_config["warmup_repetitions"],
                run_config["warmup_repetitions"] + run_config["measured_repetitions"],
            )
        )
        if [sample.get("repetition") for sample in samples if type(sample) is dict] != expected_repetitions:
            raise ContractError("sample repetitions are missing, duplicated, or reordered")
        for sample in samples:
            validate_sample(sample)
            all_samples.append(sample)
            if sample["layout_id"] != exact_layout["layout_id"]:
                raise ContractError("sample/layout mismatch")
            if sample["event_count"] != result["event_count"]:
                raise ContractError("sample scale mismatch")
            if sample["seed"] != run_config["fixed_seed"]:
                raise ContractError("sample seed mismatch")
            if sample["comparison_segment_event_limit"] != run_config["pack_segment_event_limit"]:
                raise ContractError("sample comparison segment limit mismatch")
            expected_base = _base_event_count(
                result["event_count"], run_config["pack_segment_event_limit"]
            )
            if sample["pull_base_event_count"] != expected_base:
                raise ContractError("sample pull base is not shared and pack-aligned")
            if sample["warmup"]:
                raise ContractError("warmup leaked into measured samples")
        summary = _exact_dict(exact_layout["summary"], {"duration_ns", "scalar"}, "summary")
        duration = _exact_dict(summary["duration_ns"], OPERATIONS, "duration summary")
        scalar = _exact_dict(summary["scalar"], SCALAR_METRICS, "scalar summary")
        for mapping, label in ((duration, "duration"), (scalar, "scalar")):
            for metric, raw_stats in mapping.items():
                stats_value = _exact_dict(raw_stats, {"median", "p95"}, f"{label}.{metric}")
                _positive_int(stats_value["median"], f"{label}.{metric}.median", allow_zero=True)
                _positive_int(stats_value["p95"], f"{label}.{metric}.p95", allow_zero=True)
        recomputed = _summarize(exact_layout["layout_id"], samples)["summary"]
        if summary != recomputed:
            raise ContractError("summary does not match measured samples")
    _validate_budget_evaluation(result["budget_evaluation"], result["event_count"])
    expected_budget = _budget_evaluation(result["event_count"], layouts)
    if result["budget_evaluation"] != expected_budget:
        raise ContractError("budget evaluation does not match summaries and frozen limits")
    expected_input_consistency = _input_consistency(all_samples)
    if input_consistency != expected_input_consistency:
        raise ContractError("input consistency does not match measured samples")
    expected_consistency = _environment_consistency(all_samples)
    if consistency != expected_consistency:
        raise ContractError("environment consistency does not match samples")
    cleanup = _exact_dict(
        result["cleanup"],
        {"all_worker_roots_removed", "persistent_artifacts"},
        "result cleanup",
    )
    if _bool(cleanup["all_worker_roots_removed"], "all_worker_roots_removed") is not True:
        raise ContractError("a benchmark worker root leaked")
    if cleanup["persistent_artifacts"] != "none":
        raise ContractError("benchmark persisted an artifact")
    return result


def validate_suite(value: Any) -> dict[str, Any]:
    suite = _exact_dict(
        value,
        {
            "schema_version",
            "status",
            "decision",
            "plan_digest",
            "environment_consistency",
            "reports",
        },
        "benchmark suite",
    )
    if suite["schema_version"] != SUITE_SCHEMA:
        raise ContractError("unknown benchmark suite schema")
    if suite["status"] != "non-authoritative" or suite["decision"] != "proposed":
        raise ContractError("benchmark suite attempted an authoritative decision")
    if suite["plan_digest"] != plan_digest():
        raise ContractError("benchmark suite plan digest mismatch")
    reports = _exact_list(suite["reports"], "benchmark suite reports")
    if [report.get("event_count") for report in reports if type(report) is dict] != list(
        QUALIFICATION_EVENT_COUNTS
    ):
        raise ContractError("suite reports must be unique ordered 10k and 100k scales")
    suite_samples: list[dict[str, Any]] = []
    for report in reports:
        validate_result(report)
        if report["mode"] != "synthetic-scale":
            raise ContractError("benchmark suite contains a non-scale report")
        if report["plan_digest"] != suite["plan_digest"]:
            raise ContractError("suite/report plan digest mismatch")
        for layout in report["layouts"]:
            suite_samples.extend(layout["samples"])
    suite_consistency = _exact_dict(
        suite["environment_consistency"],
        {
            "samples",
            "all_required_platform_match",
            "all_temp_root_same_device",
            "all_exact_metadata_equal",
        },
        "suite environment consistency",
    )
    if suite_consistency != _environment_consistency(suite_samples):
        raise ContractError("suite environment consistency does not match every report")
    if suite_consistency["all_exact_metadata_equal"] is not True:
        raise ContractError("suite mixed runtime or filesystem metadata between scales")
    return suite


def _build_suite(reports: list[dict[str, Any]]) -> dict[str, Any]:
    samples = [
        sample
        for report in reports
        for layout in report["layouts"]
        for sample in layout["samples"]
    ]
    suite = {
        "schema_version": SUITE_SCHEMA,
        "status": "non-authoritative",
        "decision": "proposed",
        "plan_digest": plan_digest(),
        "environment_consistency": _environment_consistency(samples),
        "reports": reports,
    }
    return validate_suite(suite)


def _validate_budget_evaluation(value: Any, event_count: int) -> None:
    evaluation = _exact_dict(value, {"applicable", "all_passed", "checks"}, "budget evaluation")
    applicable = _bool(evaluation["applicable"], "budget applicable")
    checks = _exact_list(evaluation["checks"], "budget checks")
    if not applicable:
        if evaluation["all_passed"] is not None or checks:
            raise ContractError("non-applicable budget emitted checks")
        if event_count in QUALIFICATION_EVENT_COUNTS:
            raise ContractError("qualification scale omitted its budget")
        return
    if type(evaluation["all_passed"]) is not bool:
        raise ContractError("budget all_passed must be boolean")
    if event_count not in QUALIFICATION_EVENT_COUNTS or not checks:
        raise ContractError("budget applied to an unknown scale")
    observed_passes: list[bool] = []
    observed_metric_keys: list[tuple[str, str]] = []
    for item in checks:
        check = _exact_dict(item, {"layout_id", "metric", "observed", "limit", "passed"}, "budget check")
        if check["layout_id"] not in LAYOUT_IDS:
            raise ContractError("budget check has unknown layout")
        metric = _nonempty(check["metric"], "budget metric")
        observed_metric_keys.append((check["layout_id"], metric))
        _positive_int(check["observed"], "budget observed", allow_zero=True)
        _positive_int(check["limit"], "budget limit", allow_zero=True)
        passed = _bool(check["passed"], "budget passed")
        if passed != (check["observed"] <= check["limit"]):
            raise ContractError("budget check pass flag does not match observed/limit")
        observed_passes.append(passed)
    expected_metrics = [f"duration_ns.{operation}.p95" for operation in OPERATIONS]
    expected_metrics.extend(
        [
            "repo_size_bytes.p95",
            "working_size_bytes.p95",
            "peak_rss_bytes.p95",
            "file_count.p95",
            "inode_count.p95",
            "mergeability_proxy_conflicting_paths.p95",
            "single_corruption_blast_radius_events.p95",
            "single_corruption_blast_radius_bytes.p95",
            "repo_size_bytes_to_payload_ratio.p95",
            "working_size_bytes_to_payload_ratio.p95",
        ]
    )
    expected_metric_keys = [
        (layout_id, metric) for layout_id in LAYOUT_IDS for metric in expected_metrics
    ]
    if observed_metric_keys != expected_metric_keys:
        raise ContractError("unknown, missing, duplicate, or reordered budget metric")
    if evaluation["all_passed"] != all(observed_passes):
        raise ContractError("budget aggregate mismatch")


def _minimal_valid_sample() -> dict[str, Any]:
    durations = {operation: 1 for operation in OPERATIONS}
    first_payload_bytes, first_payload_digest = _contract_payload_evidence(1, FIXED_SEED)
    return {
        "schema_version": SAMPLE_SCHEMA,
        "layout_id": LOOSE_LAYOUT,
        "event_count": 1,
        "seed": FIXED_SEED,
        "repetition": 0,
        "warmup": False,
        "comparison_segment_event_limit": 1,
        "pull_base_event_count": 0,
        "duration_ns": durations,
        "payload_bytes": first_payload_bytes,
        "payload_stream_sha256": first_payload_digest,
        "repo_size_bytes": 1,
        "working_size_bytes": 1,
        "inode_count": 1,
        "file_count": 1,
        "mergeability_proxy": {
            "branch_append_events": 2,
            "conflicting_paths": 1,
            "identical_paths": 0,
            "left_only_paths": 2,
            "right_only_paths": 2,
            "union_paths": 5,
        },
        "single_corruption_blast_radius": {
            "probe": "single-bit-flip-in-one-authentication-unit-proxy",
            "detected": True,
            "events": 1,
            "bytes": first_payload_bytes,
        },
        "peak_rss_bytes": 1,
        "environment": {
            "system": "Linux",
            "release": "synthetic",
            "machine": "synthetic",
            "distribution_id": "unknown",
            "distribution_version_id": "unknown",
            "python_implementation": "CPython",
            "python_version": "3.11",
            "wsl2_detected": False,
            "required_platform_match": False,
            "statvfs_block_size": 1,
            "statvfs_fragment_size": 1,
            "statvfs_name_max": 1,
            "filesystem_type": "unavailable-in-python-standard-library",
            "cache_policy": "as-observed-no-privileged-cache-drop",
            "temp_root_device_id": 1,
            "temp_root_same_device": True,
        },
        "cleanup_verified": True,
    }


def _minimal_valid_result(
    *, synthetic_scale: bool, event_count: int | None = None
) -> dict[str, Any]:
    if synthetic_scale:
        event_count = 10_000 if event_count is None else event_count
        if event_count not in QUALIFICATION_EVENT_COUNTS:
            raise ContractError("synthetic result fixture has an unknown scale")
    else:
        if event_count not in (None, SELF_TEST_EVENT_COUNT):
            raise ContractError("self-test fixture scale changed")
        event_count = SELF_TEST_EVENT_COUNT
    warmups = QUALIFICATION_WARMUPS if synthetic_scale else SELF_TEST_WARMUPS
    repetitions = QUALIFICATION_REPETITIONS if synthetic_scale else SELF_TEST_REPETITIONS
    segment_limit = (
        QUALIFICATION_SEGMENT_EVENTS if synthetic_scale else SELF_TEST_SEGMENT_EVENTS
    )
    samples_by_layout: dict[str, list[dict[str, Any]]] = {}
    for layout_id in LAYOUT_IDS:
        samples: list[dict[str, Any]] = []
        for repetition in range(warmups, warmups + repetitions):
            sample = _minimal_valid_sample()
            sample["layout_id"] = layout_id
            sample["event_count"] = event_count
            sample["repetition"] = repetition
            sample["comparison_segment_event_limit"] = segment_limit
            sample["pull_base_event_count"] = _base_event_count(event_count, segment_limit)
            payload_bytes, payload_digest = _contract_payload_evidence(
                event_count, FIXED_SEED
            )
            sample["payload_bytes"] = payload_bytes
            sample["payload_stream_sha256"] = payload_digest
            branch_units = (
                2 if layout_id == LOOSE_LAYOUT else math.ceil(2 / segment_limit)
            )
            sample["mergeability_proxy"] = {
                "branch_append_events": 2,
                "conflicting_paths": 1,
                "identical_paths": 0,
                "left_only_paths": branch_units,
                "right_only_paths": branch_units,
                "union_paths": 1 + 2 * branch_units,
            }
            corruption_events = (
                1 if layout_id == LOOSE_LAYOUT else min(event_count, segment_limit)
            )
            sample["single_corruption_blast_radius"]["events"] = corruption_events
            sample["single_corruption_blast_radius"]["bytes"] = _expected_payload_bytes(
                corruption_events, FIXED_SEED
            )
            if synthetic_scale:
                sample["environment"].update(
                    {
                        "release": "5.15-microsoft-standard-WSL2",
                        "distribution_id": "ubuntu",
                        "distribution_version_id": "24.04",
                        "python_version": "3.11.0",
                        "wsl2_detected": True,
                        "required_platform_match": True,
                    }
                )
            validate_sample(sample)
            samples.append(sample)
        samples_by_layout[layout_id] = samples
    layouts = [
        _summarize(layout_id, samples_by_layout[layout_id]) for layout_id in LAYOUT_IDS
    ]
    all_samples = [sample for samples in samples_by_layout.values() for sample in samples]
    return {
        "schema_version": RESULT_SCHEMA,
        "status": "non-authoritative",
        "decision": "proposed",
        "plan_digest": plan_digest(),
        "mode": "synthetic-scale" if synthetic_scale else "self-test",
        "event_count": event_count,
        "run_config": {
            "fixed_seed": FIXED_SEED,
            "warmup_repetitions": warmups,
            "measured_repetitions": repetitions,
            "pack_segment_event_limit": segment_limit,
            "layout_order": "alternate-first-layout-by-cycle",
        },
        "input_consistency": _input_consistency(all_samples),
        "environment_consistency": _environment_consistency(all_samples),
        "layouts": layouts,
        "budget_evaluation": _budget_evaluation(event_count, layouts),
        "cleanup": {"all_worker_roots_removed": True, "persistent_artifacts": "none"},
    }


def _must_reject(label: str, value: Any, validator: Any) -> dict[str, Any]:
    try:
        validator(value)
    except ContractError:
        return {"case": label, "expected": "reject", "observed": "reject", "passed": True}
    raise ContractError(f"negative validation case unexpectedly passed: {label}")


def validation_report() -> dict[str, Any]:
    validate_plan(PLAN)
    for golden in PAYLOAD_GOLDEN_EVIDENCE[:2]:
        if _expected_payload_bytes(golden["event_count"], FIXED_SEED) != golden["payload_bytes"]:
            raise ContractError("small fixed-generator byte golden mismatch")
        if (
            _expected_payload_stream_sha256(golden["event_count"], FIXED_SEED)
            != golden["payload_stream_sha256"]
        ):
            raise ContractError("small fixed-generator stream golden mismatch")
    minimal_loose = _minimal_valid_sample()
    validate_sample(minimal_loose)
    minimal_pack = copy.deepcopy(minimal_loose)
    minimal_pack["layout_id"] = PACK_LAYOUT
    validate_sample(minimal_pack)
    budget_fixture = _budget_evaluation(
        10_000,
        [
            _summarize(LOOSE_LAYOUT, [minimal_loose]),
            _summarize(PACK_LAYOUT, [minimal_pack]),
        ],
    )
    _validate_budget_evaluation(budget_fixture, 10_000)
    minimal_result = _minimal_valid_result(synthetic_scale=False)
    validate_result(minimal_result)
    scale_result = _minimal_valid_result(synthetic_scale=True)
    validate_result(scale_result)
    scale_result_100k = _minimal_valid_result(synthetic_scale=True, event_count=100_000)
    scale_suite = _build_suite([scale_result, scale_result_100k])
    validate_suite(scale_suite)
    cases = [
        {"case": "default-plan", "expected": "accept", "observed": "accept", "passed": True},
        {"case": "small-generator-golden", "expected": "accept", "observed": "accept", "passed": True},
        {"case": "minimal-sample", "expected": "accept", "observed": "accept", "passed": True},
        {"case": "minimal-result", "expected": "accept", "observed": "accept", "passed": True},
        {"case": "synthetic-scale-result", "expected": "accept", "observed": "accept", "passed": True},
        {"case": "synthetic-scale-suite", "expected": "accept", "observed": "accept", "passed": True},
        {"case": "budget-metric-matrix", "expected": "accept", "observed": "accept", "passed": True},
    ]
    unknown_schema = copy.deepcopy(PLAN)
    unknown_schema["schema_version"] = "watari.storage-benchmark-plan.v999"
    cases.append(_must_reject("unknown-schema", unknown_schema, validate_plan))
    unknown_layout = copy.deepcopy(PLAN)
    unknown_layout["layouts"][1]["layout_id"] = "unknown-layout.v1"
    cases.append(_must_reject("unknown-layout", unknown_layout, validate_plan))
    unknown_metric = copy.deepcopy(PLAN)
    unknown_metric["metrics"]["duration_metrics"].append("unknown-metric")
    cases.append(_must_reject("unknown-metric", unknown_metric, validate_plan))
    changed_budget = copy.deepcopy(PLAN)
    changed_budget["budgets"]["common_by_event_count"][0]["duration_p95_ns"]["create"] += 1
    cases.append(_must_reject("changed-frozen-budget", changed_budget, validate_plan))
    changed_payload_golden = copy.deepcopy(PLAN)
    changed_payload_golden["payload_distribution"]["golden_evidence"][0]["payload_bytes"] += 1
    cases.append(
        _must_reject("changed-payload-golden", changed_payload_golden, validate_plan)
    )
    unknown_member = _minimal_valid_sample()
    unknown_member["attacker_extension"] = True
    cases.append(_must_reject("unknown-sample-member", unknown_member, validate_sample))
    unknown_sample_metric = _minimal_valid_sample()
    unknown_sample_metric["duration_ns"]["unknown-metric"] = 1
    cases.append(
        _must_reject("unknown-sample-metric", unknown_sample_metric, validate_sample)
    )
    unsupported_python = _minimal_valid_sample()
    unsupported_python["environment"].update(
        {
            "release": "5.15-microsoft-standard-WSL2",
            "distribution_id": "ubuntu",
            "distribution_version_id": "24.04",
            "python_version": "3.10.9",
            "wsl2_detected": True,
            "required_platform_match": True,
        }
    )
    cases.append(
        _must_reject("unsupported-python-platform-claim", unsupported_python, validate_sample)
    )
    wrong_device = _minimal_valid_sample()
    wrong_device["environment"]["temp_root_same_device"] = False
    cases.append(_must_reject("cross-device-temp-root", wrong_device, validate_sample))
    wrong_payload_total = _minimal_valid_sample()
    wrong_payload_total["payload_bytes"] += 1
    cases.append(
        _must_reject("fixed-generator-payload-total-mismatch", wrong_payload_total, validate_sample)
    )
    wrong_seed = copy.deepcopy(minimal_result)
    wrong_seed["layouts"][0]["samples"][0]["seed"] = 123
    cases.append(_must_reject("sample-seed-mismatch", wrong_seed, validate_result))
    wrong_repetition = copy.deepcopy(minimal_result)
    wrong_repetition["layouts"][0]["samples"][0]["repetition"] = 999
    cases.append(
        _must_reject("sample-repetition-mismatch", wrong_repetition, validate_result)
    )
    wrong_consistency = copy.deepcopy(minimal_result)
    wrong_consistency["environment_consistency"]["samples"] = 999
    cases.append(
        _must_reject("environment-consistency-mismatch", wrong_consistency, validate_result)
    )
    wrong_payload_digest = copy.deepcopy(scale_result)
    for sample in wrong_payload_digest["layouts"][1]["samples"]:
        sample["payload_stream_sha256"] = "sha256:" + "11" * 32
    wrong_payload_digest["layouts"][1]["summary"] = _summarize(
        PACK_LAYOUT, wrong_payload_digest["layouts"][1]["samples"]
    )["summary"]
    wrong_payload_digest["budget_evaluation"] = _budget_evaluation(
        wrong_payload_digest["event_count"], wrong_payload_digest["layouts"]
    )
    cases.append(
        _must_reject("cross-layout-input-digest-mismatch", wrong_payload_digest, validate_result)
    )
    wrong_generator_digest = copy.deepcopy(minimal_result)
    for layout in wrong_generator_digest["layouts"]:
        for sample in layout["samples"]:
            sample["payload_stream_sha256"] = "sha256:" + "22" * 32
    wrong_generator_digest["input_consistency"] = _input_consistency(
        [
            sample
            for layout in wrong_generator_digest["layouts"]
            for sample in layout["samples"]
        ]
    )
    cases.append(
        _must_reject(
            "fixed-generator-stream-digest-mismatch",
            wrong_generator_digest,
            validate_result,
        )
    )
    mixed_environment = copy.deepcopy(scale_result)
    for sample in mixed_environment["layouts"][1]["samples"]:
        sample["environment"]["machine"] = "aarch64"
    cases.append(
        _must_reject("cross-layout-environment-mismatch", mixed_environment, validate_result)
    )
    wrong_merge = _minimal_valid_sample()
    wrong_merge["mergeability_proxy"]["branch_append_events"] = 1
    cases.append(_must_reject("mergeability-invariant-mismatch", wrong_merge, validate_sample))
    wrong_cache_policy = _minimal_valid_sample()
    wrong_cache_policy["environment"]["cache_policy"] = "synthetic"
    cases.append(_must_reject("unknown-sample-cache-policy", wrong_cache_policy, validate_sample))
    wrong_corruption = copy.deepcopy(minimal_pack)
    wrong_corruption["single_corruption_blast_radius"]["bytes"] += 1
    cases.append(_must_reject("corruption-radius-mismatch", wrong_corruption, validate_sample))
    cases.append(
        _must_reject(
            "duplicate-json-member",
            [("schema_version", "v1"), ("schema_version", "v2")],
            _reject_duplicate_pairs,
        )
    )
    unknown_budget_metric = copy.deepcopy(budget_fixture)
    unknown_budget_metric["checks"][0]["metric"] = "unknown-budget-metric"
    cases.append(
        _must_reject(
            "unknown-budget-metric",
            unknown_budget_metric,
            lambda value: _validate_budget_evaluation(value, 10_000),
        )
    )
    forged_budget = copy.deepcopy(scale_result)
    forged_budget["budget_evaluation"]["checks"][0].update(
        {"observed": 0, "limit": 0, "passed": True}
    )
    cases.append(_must_reject("forged-budget-values", forged_budget, validate_result))
    legacy_self_test_config = copy.deepcopy(minimal_result)
    legacy_self_test_config["event_count"] = 1
    legacy_self_test_config["run_config"].update(
        {
            "warmup_repetitions": 0,
            "measured_repetitions": 1,
            "pack_segment_event_limit": 1,
        }
    )
    cases.append(
        _must_reject("noncanonical-self-test-config", legacy_self_test_config, validate_result)
    )
    unknown_suite_member = copy.deepcopy(scale_suite)
    unknown_suite_member["attacker_extension"] = True
    cases.append(
        _must_reject("unknown-suite-member", unknown_suite_member, validate_suite)
    )
    reordered_suite = copy.deepcopy(scale_suite)
    reordered_suite["reports"].reverse()
    cases.append(_must_reject("reordered-suite-reports", reordered_suite, validate_suite))
    duplicated_suite = copy.deepcopy(scale_suite)
    duplicated_suite["reports"][1] = copy.deepcopy(duplicated_suite["reports"][0])
    cases.append(_must_reject("duplicated-suite-scale", duplicated_suite, validate_suite))
    mixed_scale_environment = copy.deepcopy(scale_suite)
    hundred_k_report = mixed_scale_environment["reports"][1]
    for layout in hundred_k_report["layouts"]:
        for sample in layout["samples"]:
            sample["environment"]["machine"] = "aarch64"
            sample["environment"]["temp_root_device_id"] = 999
    hundred_k_samples = [
        sample for layout in hundred_k_report["layouts"] for sample in layout["samples"]
    ]
    hundred_k_report["environment_consistency"] = _environment_consistency(
        hundred_k_samples
    )
    suite_samples = [
        sample
        for report in mixed_scale_environment["reports"]
        for layout in report["layouts"]
        for sample in layout["samples"]
    ]
    mixed_scale_environment["environment_consistency"] = _environment_consistency(
        suite_samples
    )
    cases.append(
        _must_reject(
            "cross-scale-suite-environment-mismatch",
            mixed_scale_environment,
            validate_suite,
        )
    )
    forged_suite_digest = copy.deepcopy(scale_suite)
    forged_suite_digest["plan_digest"] = "sha256:" + "00" * 32
    cases.append(_must_reject("forged-suite-plan-digest", forged_suite_digest, validate_suite))
    return {
        "schema_version": VALIDATION_SCHEMA,
        "plan_digest": plan_digest(),
        "cases": cases,
        "all_passed": all(case["passed"] for case in cases),
    }


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true", help="validate and print the frozen 10k/100k plan")
    modes.add_argument(
        "--validate",
        action="store_true",
        help="run closed-schema acceptance and rejection vectors",
    )
    modes.add_argument(
        "--self-test",
        action="store_true",
        help="run a small synthetic benchmark in temporary roots",
    )
    modes.add_argument(
        "--run",
        action="store_true",
        help="run the non-authoritative synthetic 10k/100k scale plan",
    )
    modes.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--layout", choices=LAYOUT_IDS, help=argparse.SUPPRESS)
    parser.add_argument("--event-count", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--seed", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--repetition", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--segment-event-limit", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--warmup", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.dry_run:
            validate_plan(PLAN)
            _print_json(PLAN)
            return 0
        if args.validate:
            _print_json(validation_report())
            return 0
        if args.self_test:
            report = run_benchmark(
                SELF_TEST_EVENT_COUNT,
                SELF_TEST_WARMUPS,
                SELF_TEST_REPETITIONS,
                SELF_TEST_SEGMENT_EVENTS,
                qualification=False,
            )
            _print_json(report)
            return 0
        if args.run:
            validate_plan(PLAN)
            reports = []
            for event_count in QUALIFICATION_EVENT_COUNTS:
                reports.append(
                    run_benchmark(
                        event_count,
                        QUALIFICATION_WARMUPS,
                        QUALIFICATION_REPETITIONS,
                        QUALIFICATION_SEGMENT_EVENTS,
                        qualification=True,
                    )
                )
            _print_json(_build_suite(reports))
            return 0
        if args._worker:
            supervisor_root = Path.cwd()
            marker = supervisor_root / ".watari-d011-supervisor"
            supervisor_stat = supervisor_root.stat()
            if (
                not supervisor_root.name.startswith("watari-d011-supervisor-")
                or supervisor_root.parent.resolve() != Path(tempfile.gettempdir()).resolve()
                or supervisor_root.is_symlink()
                or supervisor_stat.st_uid != os.geteuid()
                or supervisor_stat.st_mode & 0o077
                or not marker.is_file()
                or marker.read_text(encoding="ascii") != SUPERVISOR_MARKER
            ):
                raise ContractError("worker is not inside a parent-owned synthetic supervisor root")
            required = {
                "layout": args.layout,
                "event_count": args.event_count,
                "seed": args.seed,
                "repetition": args.repetition,
                "segment_event_limit": args.segment_event_limit,
            }
            if any(value is None for value in required.values()):
                raise ContractError("worker arguments are incomplete")
            _print_json(
                _worker_sample(
                    args.layout,
                    args.event_count,
                    args.seed,
                    args.repetition,
                    args.warmup,
                    args.segment_event_limit,
                )
            )
            return 0
    except (ContractError, OSError, subprocess.SubprocessError) as error:
        print(f"storage_harness: {error}", file=sys.stderr)
        return 2
    raise AssertionError("argparse accepted no mode")


if __name__ == "__main__":
    raise SystemExit(main())
