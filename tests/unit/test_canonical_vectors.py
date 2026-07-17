"""Contract tests for Watari's language-independent canonical vectors."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import unicodedata
import unittest
from bisect import bisect_right
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "canonical" / "vectors.json"
UNICODE_RANGES_FIXTURE = (
    ROOT / "tests" / "fixtures" / "canonical" / "unicode-15.0.0-assigned-ranges.json"
)
CONTRACT = ROOT / "docs" / "data-contract.md"

SAFE_INTEGER_MIN = -(2**53) + 1
SAFE_INTEGER_MAX = (2**53) - 1
UNICODE_VERSION = "15.0.0"
UNICODE_ENGINE_MINIMUM = (15, 0, 0)
UNICODE_RANGES_SHA256 = "5f50a0fa5ed02570bfb970ec6e6c81899e3482843bcdeb9a4d2776af805cf76b"
TIMESTAMP_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$")
INGRESS_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)
DECIMAL_RE = re.compile(
    r"^(?:0|0\.[0-9]*[1-9]|(?:[1-9][0-9]*)(?:\.[0-9]*[1-9])?|-(?:(?:[1-9][0-9]*)(?:\.[0-9]*[1-9])?|0\.[0-9]*[1-9]))$"
)
INGRESS_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
PREFIXES = {
    "payload/v1": "watari-payload-v1:",
    "event-id/v1": "watari-event-v1:",
    "event-envelope/v1": "watari-envelope-v1:",
    "context-fingerprint/canonical/v1": "watari-context-canonical-v1:",
    "context-fingerprint/effective/v1": "watari-context-effective-v1:",
}
EVENT_KEYS = {
    "schema_version",
    "event_id",
    "event_type",
    "recorded_at",
    "observed_at",
    "payload_schema",
    "payload",
    "payload_digest",
    "visibility",
    "source",
    "creator",
    "supersedes",
}
SOURCE_KEYS = {"connector_instance_id", "stable_source_event_digest", "dream_run_id"}
CREATOR_KEYS = {"kind", "model_policy_digest"}
CONTEXT_MANIFEST_KEYS = {
    "schema_version",
    "context_schema",
    "projection_kind",
    "policy_revision",
    "profile_revision",
    "memory_revision",
    "project_revision",
    "visibility",
    "route_policy_digest",
}
ALLOWED_PAYLOAD_SCHEMAS = {"watari.memory.fact/v1"}
VISIBILITIES = {"local-only", "trusted-model", "low-risk-model"}
EVENT_TYPES = {"memory", "correction", "tombstone"}
CREATOR_KINDS = {"manual", "migration", "dream"}
_UNICODE_RANGES: tuple[tuple[int, int], ...] | None = None
_UNICODE_RANGE_STARTS: tuple[int, ...] | None = None


class CanonicalizationError(ValueError):
    """The value cannot enter Watari's canonical domain."""


def _unicode_engine_version() -> tuple[int, int, int]:
    match = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)", unicodedata.unidata_version)
    if match is None:
        raise CanonicalizationError("unknown Unicode normalization engine version")
    version = tuple(int(part) for part in match.groups())
    if version < UNICODE_ENGINE_MINIMUM:
        raise CanonicalizationError("Unicode normalization engine is older than 15.0.0")
    return version


def _normalize_string(value: str) -> str:
    _unicode_engine_version()
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise CanonicalizationError("lone surrogate")
    if any(not _is_unicode_15_assigned(ord(char)) for char in value):
        raise CanonicalizationError("unassigned Unicode 15.0 code point")
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


def normalize(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _normalize_string(value)
    if isinstance(value, int):
        if not SAFE_INTEGER_MIN <= value <= SAFE_INTEGER_MAX:
            raise CanonicalizationError("unsafe integer")
        return value
    if isinstance(value, float):
        raise CanonicalizationError("floating point is forbidden")
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            if not isinstance(raw_key, str):
                raise CanonicalizationError("object key is not a string")
            key = _normalize_string(raw_key)
            if key in output:
                raise CanonicalizationError("key collision after normalization")
            output[key] = normalize(raw_value)
        return output
    raise CanonicalizationError(f"unsupported type: {type(value).__name__}")


def _utf16_sort_key(value: str) -> bytes:
    return value.encode("utf-16-be")


def _serialize(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(_serialize(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=_utf16_sort_key)
        return "{" + ",".join(_serialize(key) + ":" + _serialize(value[key]) for key in keys) + "}"
    raise AssertionError(f"normalize() admitted {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    return _serialize(normalize(value)).encode("utf-8")


def parse_json(raw: str) -> Any:
    def reject_number(token: str) -> Any:
        raise CanonicalizationError(f"forbidden JSON number: {token}")

    def object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise CanonicalizationError("duplicate object name")
            output[key] = value
        return output

    return json.loads(
        raw,
        object_pairs_hook=object_without_duplicates,
        parse_float=reject_number,
        parse_constant=reject_number,
    )


def _load_unicode_15_ranges() -> tuple[tuple[int, int], ...]:
    global _UNICODE_RANGES, _UNICODE_RANGE_STARTS
    if _UNICODE_RANGES is not None:
        return _UNICODE_RANGES
    data = parse_json(UNICODE_RANGES_FIXTURE.read_text(encoding="utf-8"))
    if set(data) != {"schema_version", "unicode_version", "assigned_ranges"}:
        raise CanonicalizationError("Unicode assignment fixture members do not match v1")
    if data["schema_version"] != 1 or data["unicode_version"] != UNICODE_VERSION:
        raise CanonicalizationError("unknown Unicode assignment fixture")
    parsed: list[tuple[int, int]] = []
    for pair in data["assigned_ranges"]:
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or any(not isinstance(item, str) or re.fullmatch(r"[0-9A-F]{4,6}", item) is None for item in pair)
        ):
            raise CanonicalizationError("invalid Unicode assignment range")
        start, end = (int(item, 16) for item in pair)
        if start > end or end > 0x10FFFF or (parsed and start <= parsed[-1][1]):
            raise CanonicalizationError("overlapping or unordered Unicode assignment range")
        parsed.append((start, end))
    if not parsed:
        raise CanonicalizationError("empty Unicode assignment table")
    _UNICODE_RANGES = tuple(parsed)
    _UNICODE_RANGE_STARTS = tuple(start for start, _ in parsed)
    return _UNICODE_RANGES


def _is_unicode_15_assigned(code_point: int) -> bool:
    ranges = _load_unicode_15_ranges()
    assert _UNICODE_RANGE_STARTS is not None
    index = bisect_right(_UNICODE_RANGE_STARTS, code_point) - 1
    return index >= 0 and code_point <= ranges[index][1]


def normalize_decimal(value: str) -> str:
    if not isinstance(value, str) or INGRESS_DECIMAL_RE.fullmatch(value) is None:
        raise CanonicalizationError("invalid ingress decimal")
    negative = value.startswith("-")
    unsigned = value[1:] if negative else value
    integer, separator, fraction = unsigned.partition(".")
    fraction = fraction.rstrip("0") if separator else ""
    normalized = integer + ("." + fraction if fraction else "")
    if normalized == "0":
        return "0"
    return ("-" if negative else "") + normalized


def normalize_timestamp(value: str) -> str:
    if not isinstance(value, str) or INGRESS_TIMESTAMP_RE.fullmatch(value) is None:
        raise CanonicalizationError("invalid ingress timestamp")
    zone = value[-1] if value.endswith("Z") else value[-6:]
    if zone == "-00:00":
        raise CanonicalizationError("unknown UTC offset")
    if zone != "Z" and (int(zone[1:3]) > 23 or int(zone[4:6]) > 59):
        raise CanonicalizationError("timestamp offset is out of range")
    main = value[:-1] if value.endswith("Z") else value[:-6]
    fraction = main.partition(".")[2]
    if len(fraction) > 6:
        raise CanonicalizationError("timestamp precision exceeds microseconds")
    iso_value = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(iso_value)
    except ValueError as error:
        raise CanonicalizationError("invalid calendar timestamp") from error
    if parsed.tzinfo is None:
        raise CanonicalizationError("timestamp offset is required")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _require_exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise CanonicalizationError(f"{label} members do not match v1")
    return value


def _require_nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CanonicalizationError(f"{label} must be a nonempty string")
    return value


def _require_typed_digest(value: Any, prefix: str, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(re.escape(prefix) + r"[0-9a-f]{64}", value) is None:
        raise CanonicalizationError(f"{label} is not a typed lowercase digest")
    return value


def validate_event_envelope(
    value: Any,
    allowed_payload_schemas: set[str] = ALLOWED_PAYLOAD_SCHEMAS,
) -> dict[str, Any]:
    envelope = _require_exact_keys(normalize(value), EVENT_KEYS, "event envelope")
    if type(envelope["schema_version"]) is not int or envelope["schema_version"] != 1:
        raise CanonicalizationError("unsupported event schema version")
    if not isinstance(envelope["event_type"], str) or envelope["event_type"] not in EVENT_TYPES:
        raise CanonicalizationError("unknown event type")
    if not isinstance(envelope["visibility"], str) or envelope["visibility"] not in VISIBILITIES:
        raise CanonicalizationError("unknown visibility")
    assert_timestamp(envelope["recorded_at"])
    if envelope["observed_at"] is not None:
        assert_timestamp(envelope["observed_at"])

    payload_schema = _require_nonempty_string(envelope["payload_schema"], "payload_schema")
    if payload_schema not in allowed_payload_schemas:
        raise CanonicalizationError("payload schema is not allowlisted")
    _require_typed_digest(envelope["event_id"], "watari-event-v1:", "event_id")
    _require_typed_digest(envelope["payload_digest"], "watari-payload-v1:", "payload_digest")

    source = _require_exact_keys(envelope["source"], SOURCE_KEYS, "source")
    creator = _require_exact_keys(envelope["creator"], CREATOR_KEYS, "creator")
    if not isinstance(creator["kind"], str) or creator["kind"] not in CREATOR_KINDS:
        raise CanonicalizationError("unknown creator kind")
    _require_nonempty_string(source["connector_instance_id"], "connector_instance_id")
    _require_typed_digest(
        source["stable_source_event_digest"],
        "watari-source-v1:",
        "stable_source_event_digest",
    )
    if source["dream_run_id"] is not None:
        _require_nonempty_string(source["dream_run_id"], "dream_run_id")
    if creator["model_policy_digest"] is not None:
        _require_typed_digest(
            creator["model_policy_digest"],
            "watari-policy-v1:",
            "model_policy_digest",
        )

    if creator["kind"] == "dream":
        if source["dream_run_id"] is None or creator["model_policy_digest"] is None:
            raise CanonicalizationError("dream source binding is incomplete")
    elif source["dream_run_id"] is not None:
        raise CanonicalizationError("non-dream creator has a dream_run_id")

    if envelope["event_type"] == "memory":
        if envelope["supersedes"] is not None:
            raise CanonicalizationError("memory event cannot supersede")
    else:
        _require_typed_digest(envelope["supersedes"], "watari-event-v1:", "supersedes")
        if envelope["supersedes"] == envelope["event_id"]:
            raise CanonicalizationError("event cannot supersede itself")

    if payload_digest(envelope["payload"]) != envelope["payload_digest"]:
        raise CanonicalizationError("payload digest mismatch")
    identity = {
        "connector_instance_id": source["connector_instance_id"],
        "event_type": envelope["event_type"],
        "payload_digest": envelope["payload_digest"],
        "payload_schema": payload_schema,
        "schema_version": envelope["schema_version"],
        "stable_source_event_digest": source["stable_source_event_digest"],
    }
    if event_id(identity) != envelope["event_id"]:
        raise CanonicalizationError("event ID mismatch")
    return envelope


def validate_context_manifest(kind: str, value: Any) -> dict[str, Any]:
    if kind not in {"canonical", "effective"}:
        raise CanonicalizationError("unknown context projection kind")
    manifest = _require_exact_keys(normalize(value), CONTEXT_MANIFEST_KEYS, "context manifest")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise CanonicalizationError("unsupported context manifest version")
    if manifest["context_schema"] != "watari.context/v1":
        raise CanonicalizationError("unknown context schema")
    if manifest["projection_kind"] != kind:
        raise CanonicalizationError("context projection kind mismatch")
    for field in ("policy_revision", "profile_revision", "memory_revision"):
        _require_nonempty_string(manifest[field], field)
    if manifest["project_revision"] is not None:
        _require_nonempty_string(manifest["project_revision"], "project_revision")
    if not isinstance(manifest["visibility"], str) or manifest["visibility"] not in VISIBILITIES:
        raise CanonicalizationError("unknown context visibility")
    _require_typed_digest(
        manifest["route_policy_digest"],
        "watari-route-policy-v1:",
        "route_policy_digest",
    )
    return manifest


def validate_fixture_header(value: Any) -> None:
    if not isinstance(value, dict):
        raise CanonicalizationError("canonical fixture is not an object")
    if value.get("schema_version") != 1 or value.get("contract") != "watari-canonical-v1":
        raise CanonicalizationError("unknown canonical fixture contract")
    if value.get("unicode_normalization_version") != UNICODE_VERSION:
        raise CanonicalizationError("unknown Unicode normalization dataset")


def apply_mutation(value: Any, mutation: dict[str, Any]) -> Any:
    output = deepcopy(value)
    path = mutation["path"]
    parent = output
    for component in path[:-1]:
        parent = parent[component]
    if mutation["op"] == "set":
        parent[path[-1]] = mutation["value"]
    elif mutation["op"] == "remove":
        del parent[path[-1]]
    else:
        raise AssertionError(f"unknown fixture mutation: {mutation['op']}")
    return output


def framed_hash(domain: str, *parts: bytes) -> str:
    frame = bytearray(b"WATARI\x00")
    frame.extend(domain.encode("ascii"))
    frame.append(0)
    for part in parts:
        frame.extend(struct.pack(">Q", len(part)))
        frame.extend(part)
    return PREFIXES[domain] + hashlib.sha256(frame).hexdigest()


def payload_digest(payload: Any) -> str:
    return framed_hash("payload/v1", canonical_bytes(payload))


def event_id(identity: dict[str, Any]) -> str:
    return framed_hash("event-id/v1", canonical_bytes(identity))


def envelope_digest(envelope: dict[str, Any]) -> str:
    return framed_hash("event-envelope/v1", canonical_bytes(envelope))


def context_fingerprint(kind: str, manifest: dict[str, Any], context: bytes) -> str:
    if not isinstance(context, bytes):
        raise CanonicalizationError("context must be exact bytes")
    validated_manifest = validate_context_manifest(kind, manifest)
    domain = f"context-fingerprint/{kind}/v1"
    return framed_hash(domain, canonical_bytes(validated_manifest), context)


def assert_timestamp(value: str) -> None:
    if not isinstance(value, str) or not TIMESTAMP_RE.fullmatch(value):
        raise CanonicalizationError("timestamp is not fixed-precision UTC")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as error:
        raise CanonicalizationError("timestamp is not a valid calendar instant") from error


class CanonicalVectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.vectors = parse_json(FIXTURE.read_text(encoding="utf-8"))
        validate_fixture_header(cls.vectors)

    def test_fixture_and_contract_are_versioned(self) -> None:
        self.assertEqual(self.vectors["schema_version"], 1)
        self.assertEqual(self.vectors["contract"], "watari-canonical-v1")
        self.assertEqual(self.vectors["unicode_normalization_version"], UNICODE_VERSION)
        text = CONTRACT.read_text(encoding="utf-8")
        for marker in (
            "RFC 8785",
            "UTF-16",
            "Unicode NFC",
            "Unicode 15.0.0",
            "LF",
            "WATARI\\x00",
            "physical object layout is intentionally undecided",
        ):
            self.assertIn(marker, text)

    def test_unicode_assignment_table_is_host_independent(self) -> None:
        ranges = _load_unicode_15_ranges()
        self.assertEqual(
            hashlib.sha256(UNICODE_RANGES_FIXTURE.read_bytes()).hexdigest(),
            UNICODE_RANGES_SHA256,
        )
        self.assertEqual(len(ranges), 707)
        self.assertTrue(_is_unicode_15_assigned(ord("é")))
        self.assertTrue(_is_unicode_15_assigned(ord("😀")))
        self.assertFalse(_is_unicode_15_assigned(0x2EBF0))
        self.assertEqual(UNICODE_VERSION, self.vectors["unicode_normalization_version"])
        self.assertGreaterEqual(_unicode_engine_version(), UNICODE_ENGINE_MINIMUM)

    def test_unicode_15_normalization_vectors(self) -> None:
        for vector in self.vectors["unicode_normalization_vectors"]:
            with self.subTest(vector=vector["id"]):
                raw = "".join(chr(int(item, 16)) for item in vector["input_code_points"])
                normalized = _normalize_string(raw)
                self.assertEqual(
                    [f"{ord(char):04X}" for char in normalized],
                    vector["normalized_code_points"],
                )
                self.assertEqual(normalized.encode("utf-8").hex(), vector["normalized_utf8_hex"])

    def test_vector_ids_are_unique_and_prefixed(self) -> None:
        groups = (
            "canonical_json_vectors",
            "digest_vectors",
            "event_vectors",
            "context_vectors",
            "scalar_normalization_vectors",
            "unicode_normalization_vectors",
            "rejection_vectors",
        )
        ids = [vector["id"] for group in groups for vector in self.vectors[group]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(item.startswith("T-CANON-") for item in ids))

    def test_canonical_json_golden_vectors(self) -> None:
        for vector in self.vectors["canonical_json_vectors"]:
            with self.subTest(vector=vector["id"]):
                normalized = normalize(vector["input"])
                self.assertEqual(normalized, vector["normalized"])
                actual = canonical_bytes(vector["input"])
                self.assertEqual(actual.decode("utf-8"), vector["canonical_json"])
                self.assertEqual(actual.hex(), vector["canonical_utf8_hex"])
                self.assertFalse(actual.startswith(b"\xef\xbb\xbf"))
                self.assertFalse(actual.endswith(b"\n"))
        utf16_vector = next(
            item for item in self.vectors["canonical_json_vectors"] if item["id"] == "T-CANON-002"
        )
        self.assertLess(
            utf16_vector["canonical_json"].index("😀"),
            utf16_vector["canonical_json"].index("�"),
        )

    def test_domain_separated_digest_vectors(self) -> None:
        for vector in self.vectors["digest_vectors"]:
            with self.subTest(vector=vector["id"]):
                parts = [bytes.fromhex(item) for item in vector["parts_hex"]]
                self.assertEqual(framed_hash(vector["domain"], *parts), vector["digest"])
                self.assertRegex(vector["digest"], rf"^{re.escape(PREFIXES[vector['domain']])}[0-9a-f]{{64}}$")
        self.assertNotEqual(
            framed_hash("payload/v1", b"a", b"bc"),
            framed_hash("payload/v1", b"ab", b"c"),
        )

    def test_event_golden_vectors(self) -> None:
        for vector in self.vectors["event_vectors"]:
            with self.subTest(vector=vector["id"]):
                envelope = vector["envelope"]
                self.assertEqual(validate_event_envelope(envelope), envelope)
                self.assertRegex(envelope["event_id"], r"^watari-event-v1:[0-9a-f]{64}$")
                self.assertRegex(envelope["payload_digest"], r"^watari-payload-v1:[0-9a-f]{64}$")
                self.assertRegex(vector["envelope_digest"], r"^watari-envelope-v1:[0-9a-f]{64}$")
                if envelope["event_type"] == "memory":
                    self.assertIsNone(envelope["supersedes"])
                if envelope["creator"]["kind"] == "dream":
                    self.assertIsNotNone(envelope["source"]["dream_run_id"])
                    self.assertIsNotNone(envelope["creator"]["model_policy_digest"])
                self.assertEqual(payload_digest(envelope["payload"]), envelope["payload_digest"])
                identity = {
                    "connector_instance_id": envelope["source"]["connector_instance_id"],
                    "event_type": envelope["event_type"],
                    "payload_digest": envelope["payload_digest"],
                    "payload_schema": envelope["payload_schema"],
                    "schema_version": envelope["schema_version"],
                    "stable_source_event_digest": envelope["source"]["stable_source_event_digest"],
                }
                self.assertEqual(identity, vector["identity_projection"])
                self.assertEqual(event_id(identity), envelope["event_id"])
                alternate_schema = dict(identity, payload_schema="watari.memory.fact/v2")
                self.assertNotEqual(event_id(alternate_schema), envelope["event_id"])
                self.assertEqual(canonical_bytes(envelope).hex(), vector["canonical_envelope_hex"])
                self.assertEqual(envelope_digest(envelope), vector["envelope_digest"])
                assert_timestamp(envelope["recorded_at"])
                if envelope["observed_at"] is not None:
                    assert_timestamp(envelope["observed_at"])

    def test_context_fingerprint_golden_vectors(self) -> None:
        for vector in self.vectors["context_vectors"]:
            with self.subTest(vector=vector["id"]):
                context = bytes.fromhex(vector["context_bytes_hex"])
                self.assertEqual(vector["context_utf8"].encode("utf-8"), context)
                self.assertEqual(vector["manifest"]["projection_kind"], vector["kind"])
                self.assertEqual(
                    context_fingerprint(vector["kind"], vector["manifest"], context),
                    vector["fingerprint"],
                )
                self.assertRegex(vector["fingerprint"], rf"^watari-context-{vector['kind']}-v1:[0-9a-f]{{64}}$")

    def test_context_fingerprint_uses_exact_bytes_and_projection_domain(self) -> None:
        effective_vector = next(item for item in self.vectors["context_vectors"] if item["kind"] == "effective")
        canonical_vector = next(item for item in self.vectors["context_vectors"] if item["kind"] == "canonical")
        manifest = effective_vector["manifest"]
        lf = context_fingerprint("effective", manifest, b"line one\nline two\n")
        crlf = context_fingerprint("effective", manifest, b"line one\r\nline two\r\n")
        nfc = context_fingerprint("effective", manifest, "Café".encode("utf-8"))
        nfd = context_fingerprint("effective", manifest, "Cafe\u0301".encode("utf-8"))
        canonical_manifest = canonical_vector["manifest"]
        canonical = context_fingerprint("canonical", canonical_manifest, b"line one\nline two\n")
        self.assertNotEqual(lf, crlf)
        self.assertNotEqual(nfc, nfd)
        self.assertNotEqual(lf.split(":", 1)[1], canonical.split(":", 1)[1])

    def test_scalar_ingress_normalization_vectors(self) -> None:
        normalizers = {"decimal": normalize_decimal, "timestamp": normalize_timestamp}
        for vector in self.vectors["scalar_normalization_vectors"]:
            with self.subTest(vector=vector["id"]):
                actual = normalizers[vector["kind"]](vector["input"])
                self.assertEqual(actual, vector["canonical"])
                if vector["kind"] == "decimal":
                    self.assertIsNotNone(DECIMAL_RE.fullmatch(actual))
                else:
                    assert_timestamp(actual)

    def test_fail_closed_rejection_vectors(self) -> None:
        event = self.vectors["event_vectors"][0]["envelope"]
        contexts = {item["kind"]: item for item in self.vectors["context_vectors"]}
        for vector in self.vectors["rejection_vectors"]:
            with self.subTest(vector=vector["id"]):
                with self.assertRaises(CanonicalizationError):
                    validator = vector["validator"]
                    if validator == "json-text":
                        parse_json(vector["input"])
                    elif validator == "canonical-value":
                        canonical_bytes(vector["input"])
                    elif validator == "fixture-header":
                        validate_fixture_header(apply_mutation(self.vectors, vector["mutation"]))
                    elif validator == "event-envelope":
                        validate_event_envelope(apply_mutation(event, vector["mutation"]))
                    elif validator == "context-manifest":
                        base = contexts[vector["base_kind"]]
                        manifest = apply_mutation(base["manifest"], vector["mutation"])
                        validate_context_manifest(vector.get("kind", base["kind"]), manifest)
                    else:
                        raise AssertionError(f"unknown rejection validator: {validator}")

    def test_invalid_canonical_inputs_fail_closed(self) -> None:
        invalid = [1.0, float("nan"), float("inf"), 2**53, -(2**53), "\ud800", chr(0x2EBF0)]
        for value in invalid:
            with self.subTest(value=repr(value)):
                with self.assertRaises(CanonicalizationError):
                    canonical_bytes(value)
        with self.assertRaises(CanonicalizationError):
            canonical_bytes({"e\u0301": 1, "é": 2})
        for raw in ('{"a":1,"a":2}', '{"number":1.0}', '{"number":NaN}'):
            with self.subTest(raw=raw):
                with self.assertRaises(CanonicalizationError):
                    parse_json(raw)

    def test_decimal_string_profile(self) -> None:
        accepted = ("0", "1", "-1", "0.01", "-0.01", "123.45")
        rejected = ("-0", "+1", "01", "1.0", "1.20", ".5", "1.", "1e3", "1\n")
        for value in accepted:
            self.assertIsNotNone(DECIMAL_RE.fullmatch(value), value)
        for value in rejected:
            self.assertIsNone(DECIMAL_RE.fullmatch(value), value)
        for value in ("+1", "01", "1e3", ".5", "1."):
            with self.assertRaises(CanonicalizationError):
                normalize_decimal(value)

    def test_timestamp_profile(self) -> None:
        assert_timestamp("2026-07-17T01:02:03.000004Z")
        for value in (
            "2026-07-17T01:02:03Z",
            "2026-07-17T01:02:03.000004+00:00",
            "2026-07-17T01:02:60.000000Z",
        ):
            with self.subTest(value=value):
                with self.assertRaises((CanonicalizationError, ValueError)):
                    assert_timestamp(value)
        for value in (
            "2026-07-17T01:02:03.1234567Z",
            "2026-07-17T01:02:03-00:00",
            "2026-07-17T01:02:03+09:60",
            "2026-07-17T01:02:60Z",
            "2026-07-17T01:02:03",
        ):
            with self.subTest(ingress=value):
                with self.assertRaises(CanonicalizationError):
                    normalize_timestamp(value)


if __name__ == "__main__":
    unittest.main()
