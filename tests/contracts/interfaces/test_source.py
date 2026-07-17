import copy
import hashlib
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[3]
DOC = ROOT / "docs/source-contract.md"
D005_PATH = ROOT / "tests/contracts/test_route_matrix.py"
TYPED_SOURCE = re.compile(r"^watari-source-v1:[0-9a-f]{64}$")
TYPED_INSTANCE = re.compile(r"^watari-source-instance-v1:[0-9a-f]{64}$")
TYPED_CHECKPOINT = re.compile(r"^watari-checkpoint-v1:[0-9a-f]{64}$")
COORDINATOR_EPOCH = re.compile(r"^epoch-current-[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


D005 = load_module(D005_PATH, "d005_routes_for_source")
D003 = D005.d003_module()
MATRIX = D005.load_matrix()


def contract():
    text = DOC.read_text(encoding="utf-8")
    match = re.search(r"<!-- source-contract:start -->\n```json\n(.*?)\n```\n<!-- source-contract:end -->", text, re.S)
    if not match: raise AssertionError("missing normative source contract")
    return json.loads(match.group(1))


def framed(domain, prefix, *parts):
    data = b"WATARI\0" + domain.encode() + b"\0"
    data += b"".join(len(part).to_bytes(8, "big") + part for part in parts)
    return prefix + hashlib.sha256(data).hexdigest()


def canonical_content(raw):
    if type(raw) is not bytes or not raw: return None
    try:
        value = D003.parse_json(raw.decode("utf-8"))
        return value if D003.canonical_bytes(value) == raw else None
    except (UnicodeError, ValueError, TypeError):
        return None


def bound_item(item):
    content = canonical_content(item.get("canonical_item_bytes"))
    if content is None: return None
    projection = {key: value for key, value in item.items() if key != "canonical_item_bytes"}
    projection["canonical_content"] = content
    return D003.canonical_bytes(projection)


def unique_items(items):
    unique, conflicts = {}, set()
    for item in items:
        identity, binding = item.get("stable_source_event_digest"), bound_item(item)
        if identity in unique and unique[identity][0] != binding: conflicts.add(identity)
        else: unique[identity] = (binding, item)
    return [pair[1] for pair in unique.values()], conflicts


def scan_digest(items):
    unique, _ = unique_items(items)
    parts = [(item.get("stable_source_event_digest", "").encode() + b"\0" + (bound_item(item) or b"invalid"))
             for item in sorted(unique, key=lambda value: value.get("stable_source_event_digest", ""))]
    return framed("source-scan-manifest/v1", "watari-source-scan-v1:", *parts)


def snapshot_digest(result):
    return framed("source-snapshot/v1", "watari-source-snapshot-v1:",
                  result["format_revision"].encode(), scan_digest(result["items"]).encode())


def checkpoint_digest(proposal):
    fields = ("source_key", "checkpoint_before_digest", "source_snapshot_digest", "scan_manifest_digest", "opaque_position")
    return framed("source-checkpoint/v1", "watari-checkpoint-v1:",
                  D003.canonical_bytes({field: proposal[field] for field in fields}))


def seal(request, result):
    for item in result["items"]:
        raw = item["canonical_item_bytes"]
        item["content_digest"] = framed("source-content/v1", "watari-source-content-v1:", raw)
    result["source_snapshot_digest"] = snapshot_digest(result)
    proposal = {"schema": "watari.source-checkpoint-proposal.v1", "source_key": copy.deepcopy(result["source_key"]),
                "checkpoint_before_digest": request["committed_checkpoint"], "checkpoint_after_digest": "",
                "source_snapshot_digest": result["source_snapshot_digest"], "scan_manifest_digest": scan_digest(result["items"]),
                "opaque_position": "position.synthetic.1"}
    proposal["checkpoint_after_digest"] = checkpoint_digest(proposal)
    result["checkpoint_proposal"] = proposal
    return request, result


def fixture():
    stable = "watari-source-v1:" + "5" * 64
    raw = b'{"text":"synthetic"}'
    observation = {"schema": "watari.source-receipt-observation.v1", "turn_id": "turn.synthetic.1",
                   "capture_route_id": "route.session-receipt.codex.v1", "origin_route_id": "route.codex.full-watari.v1",
                   "session_lineage": "lineage:synthetic", "launch_attestation": "attestation:synthetic",
                   "observed_bytes": raw, "observed_role": "user", "observed_source": "local-user-turn"}
    receipt = D005.receipt_from_observation(MATRIX, turn_id=observation["turn_id"],
        capture_route_id=observation["capture_route_id"], origin_route_id=observation["origin_route_id"],
        observed_bytes=raw, role=observation["observed_role"], source=observation["observed_source"], lineage=observation["session_lineage"],
        attestation=observation["launch_attestation"], d003=D003)
    key = {"device_id": "device.synthetic", "connector_instance_id": "watari-source-instance-v1:" + "9" * 64,
           "source_lineage_digest": receipt["session_lineage_digest"], "coordinator_epoch": None}
    item = {"schema": "watari.source-item.v1", "stable_source_event_digest": stable,
            "canonical_item_bytes": raw, "content_digest": "", "role": "user", "source": "local-user-turn",
            "session_lineage_digest": key["source_lineage_digest"], "provenance_kind": "turn-receipt-structural",
            "turn_receipt": receipt}
    request = {"schema": "watari.source-scan-request.v1", "adapter_id": "adapter.synthetic", "adapter_version": "1",
               "device_id": key["device_id"], "connector_instance_id": key["connector_instance_id"],
               "expected_source_lineage_digest": key["source_lineage_digest"], "expected_coordinator_epoch": None,
               "committed_checkpoint": "watari-checkpoint-v1:" + "6" * 64,
               "bounds": {"schema": "watari.source-bounds.v1", "max_items": 10, "max_bytes": 4096},
               "receipt_observations": {stable: observation}}
    result = {"schema": "watari.source-scan-result.v1", "status": "complete", "source_key": key,
              "format_revision": "watari.fake-source/v1", "source_snapshot_digest": "", "items": [item],
              "checkpoint_proposal": None, "errors": []}
    return seal(request, result)


def _validate(c, request, result):
    errors = set()
    schemas = c["schemas"]
    if set(request) != set(schemas["request"]["fields"]) or request.get("schema") != schemas["request"]["id"]: errors.add("INVALID_REQUEST_SCHEMA")
    bounds = request.get("bounds")
    if type(bounds) is not dict or set(bounds) != set(schemas["bounds"]["fields"]) or bounds.get("schema") != schemas["bounds"]["id"] or any(type(bounds.get(key)) is not int or bounds[key] <= 0 for key in ("max_items", "max_bytes")): errors.add("INVALID_BOUNDS_SCHEMA")
    if set(result) != set(schemas["result"]["fields"]) or result.get("schema") != schemas["result"]["id"]: return {"INVALID_RESULT_SCHEMA"}, []
    if result["status"] not in c["checkpoint"]["status_values"]: errors.add("INVALID_STATUS")
    result_errors = result["errors"]
    if type(result_errors) is not list: errors.add("INVALID_RESULT_SCHEMA")
    elif any(type(token) is not str or token not in c["checkpoint"]["error_values"] for token in result_errors): errors.add("INVALID_ERROR_TOKEN")
    elif (result["status"] == "complete") != (result_errors == []): errors.add("STATUS_ERROR_MISMATCH")
    key = result["source_key"]
    if type(key) is not dict or set(key) != set(c["source_key_fields"]): errors.add("INVALID_SOURCE_KEY")
    if key.get("device_id") != request.get("device_id") or key.get("connector_instance_id") != request.get("connector_instance_id"): errors.add("IDENTITY_DRIFT")
    if key.get("source_lineage_digest") != request.get("expected_source_lineage_digest"): errors.add("LINEAGE_DRIFT")
    if key.get("coordinator_epoch") != request.get("expected_coordinator_epoch"): errors.add("COORDINATOR_DRIFT")
    epoch = request.get("expected_coordinator_epoch")
    if epoch is not None and (type(epoch) is not str or not COORDINATOR_EPOCH.fullmatch(epoch)): errors.add("INVALID_COORDINATOR_EPOCH")
    if type(request.get("committed_checkpoint")) is not str or not TYPED_CHECKPOINT.fullmatch(request["committed_checkpoint"]): errors.add("INVALID_COMMITTED_CHECKPOINT")
    versions = c["identity"]["adapter_versions"]
    if request.get("adapter_version") not in versions.get(request.get("adapter_id"), []): errors.add("UNSUPPORTED_VERSION")
    if any(type(value) is not str or not TYPED_INSTANCE.fullmatch(value) for value in (request.get("connector_instance_id"), key.get("connector_instance_id"))): errors.add("INVALID_INSTANCE_ID")
    if result["format_revision"] not in c["conformance_formats"]: errors.add("UNSUPPORTED_FORMAT")
    observations = request.get("receipt_observations", {})
    item_ids = {item.get("stable_source_event_digest") for item in result["items"] if type(item) is dict}
    if type(observations) is not dict or set(observations) != item_ids: errors.add("OBSERVATION_SET_MISMATCH")
    for item in result["items"]:
        if type(item) is not dict or set(item) != set(schemas["item"]["fields"]) or item.get("schema") != schemas["item"]["id"]: errors.add("INVALID_ITEM_SCHEMA"); continue
        if type(item["stable_source_event_digest"]) is not str or not TYPED_SOURCE.fullmatch(item["stable_source_event_digest"]): errors.add("INVALID_STABLE_ID")
        if item["provenance_kind"] not in c["identity"]["provenance_values"]: errors.add("INVALID_PROVENANCE")
        if (item["role"], item["source"]) not in D005.ROLE_SOURCE_PAIRS: errors.add("INVALID_ROLE_SOURCE")
        if item["session_lineage_digest"] != key.get("source_lineage_digest"): errors.add("LINEAGE_DRIFT")
        if canonical_content(item["canonical_item_bytes"]) is None: errors.add("NONCANONICAL_ITEM")
        if item["content_digest"] != framed("source-content/v1", "watari-source-content-v1:", item["canonical_item_bytes"]): errors.add("CONTENT_DRIFT")
        obs = observations.get(item["stable_source_event_digest"])
        if type(obs) is not dict or set(obs) != set(schemas["receipt_observation"]["fields"]) or obs.get("schema") != schemas["receipt_observation"]["id"]: errors.add("INVALID_RECEIPT_OBSERVATION"); continue
        if (item["canonical_item_bytes"], item["role"], item["source"]) != (obs["observed_bytes"], obs["observed_role"], obs["observed_source"]): errors.add("OBSERVATION_MISMATCH")
        receipt_errors = D005.turn_receipt_errors(item["turn_receipt"], trusted_matrix=MATRIX,
            observed_turn_id=obs["turn_id"], observed_capture_route_id=obs["capture_route_id"],
            observed_origin_route_id=obs["origin_route_id"], observed_bytes=obs["observed_bytes"],
            observed_role=obs["observed_role"], observed_source=obs["observed_source"], observed_session_lineage=obs["session_lineage"],
            observed_launch_attestation=obs["launch_attestation"], d003=D003)
        if receipt_errors: errors.add("INVALID_RECEIPT")
    unique, conflicts = unique_items(result["items"])
    if conflicts: errors.add("IDENTITY_CONFLICT")
    if type(bounds) is dict and (len(result["items"]) > bounds.get("max_items", -1) or sum(len(raw) if type(raw) is bytes else 0 for raw in (item.get("canonical_item_bytes") for item in result["items"])) > bounds.get("max_bytes", -1)): errors.add("BOUNDS_EXCEEDED")
    if result["source_snapshot_digest"] != snapshot_digest(result): errors.add("SNAPSHOT_DRIFT")
    proposal = result["checkpoint_proposal"]
    if result["status"] != "complete" and proposal is not None: errors.add("CHECKPOINT_ON_INCOMPLETE")
    if result["status"] == "complete":
        if type(proposal) is not dict or set(proposal) != set(schemas["checkpoint_proposal"]["fields"]) or proposal.get("schema") != schemas["checkpoint_proposal"]["id"]: errors.add("INVALID_CHECKPOINT_PROPOSAL")
        elif proposal["source_key"] != key or proposal["checkpoint_before_digest"] != request["committed_checkpoint"] or proposal["source_snapshot_digest"] != result["source_snapshot_digest"] or proposal["scan_manifest_digest"] != scan_digest(result["items"]): errors.add("UNBOUND_CHECKPOINT_PROPOSAL")
        elif proposal["checkpoint_after_digest"] != checkpoint_digest(proposal): errors.add("CHECKPOINT_DIGEST")
    return errors, unique

def validate(c, request, result):
    try: return _validate(c, request, result)
    except (AttributeError, KeyError, TypeError, UnicodeError, ValueError): return {"INVALID_VALUE"}, []
class SourceContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.c = contract()

    def test_t_source_contract_closed_schema_and_revision(self):
        self.assertEqual(set(self.c), {"schema", "schemas", "source_key_fields", "role_source_pairs", "conformance_formats", "identity", "snapshot", "checkpoint", "qualification", "open_decisions"})
        self.assertEqual(self.c["schema"], "source-contract.v1"); self.assertEqual(set(map(tuple, self.c["role_source_pairs"])), D005.ROLE_SOURCE_PAIRS)
        self.assertEqual(set(self.c["open_decisions"]), {f"DEC-OPEN-00{i}" for i in range(1, 7)}); self.assertEqual(validate(self.c, *fixture())[0], set())

    def test_t_source_identity_is_stable_opaque_and_source_bound(self):
        request, result = fixture(); result["source_key"]["connector_instance_id"] = "other"; self.assertIn("IDENTITY_DRIFT", validate(self.c, request, result)[0])
        request, result = fixture(); result["source_key"]["source_lineage_digest"] = "changed"; self.assertIn("LINEAGE_DRIFT", validate(self.c, request, result)[0])
        request, result = fixture(); result["source_key"]["coordinator_epoch"] = "source-chosen"; self.assertIn("COORDINATOR_DRIFT", validate(self.c, request, result)[0])
        request, result = fixture(); request["expected_coordinator_epoch"] = result["source_key"]["coordinator_epoch"] = "arbitrary"; seal(request, result); self.assertIn("INVALID_COORDINATOR_EPOCH", validate(self.c, request, result)[0])
        request, result = fixture(); request["expected_coordinator_epoch"] = result["source_key"]["coordinator_epoch"] = "epoch-current-device.1"; seal(request, result); self.assertEqual(validate(self.c, request, result)[0], set())
        request, result = fixture(); result["items"][0]["stable_source_event_digest"] = "raw-id"; self.assertIn("INVALID_STABLE_ID", validate(self.c, request, result)[0])
        for untyped in ("/synthetic/root", "C:\\synthetic\\root", "..", "api-token-value", "Alice laptop", "source.synthetic"):
            request, result = fixture(); request["connector_instance_id"] = result["source_key"]["connector_instance_id"] = untyped; seal(request, result); self.assertIn("INVALID_INSTANCE_ID", validate(self.c, request, result)[0], untyped)

    def test_t_source_roles_lineage_and_receipt_provenance(self):
        for primary in (False, True):
            request, result = fixture(); item = result["items"][0]; obs = next(iter(request["receipt_observations"].values())); item.update(role="assistant", source="provider-output"); item["turn_receipt"] = D005.receipt_from_observation(MATRIX, turn_id=obs["turn_id"], capture_route_id=obs["capture_route_id"], origin_route_id=obs["origin_route_id"], observed_bytes=item["canonical_item_bytes"], role=item["role"], source=item["source"], lineage=obs["session_lineage"], attestation=obs["launch_attestation"], d003=D003); item["turn_receipt"]["primary_evidence"] = primary; seal(request, result)
            self.assertTrue({"INVALID_RECEIPT", "OBSERVATION_MISMATCH"} <= validate(self.c, request, result)[0], primary)
        for field, value in (("schema_version", "unknown/v9"), ("route_id", "unknown"), ("origin_route_id", "unknown"), ("bytes_digest", "raw"), ("watari_launch_attestation_digest", "raw"), ("origin_route_provider_model_policy_digest", "raw")):
            request, result = fixture(); result["items"][0]["turn_receipt"][field] = value; seal(request, result); self.assertIn("INVALID_RECEIPT", validate(self.c, request, result)[0], field)
        for mode in ("missing", "extra"):
            request, result = fixture(); observations = request["receipt_observations"]; observations.pop(next(iter(observations))) if mode == "missing" else observations.update({"watari-source-v1:" + "8" * 64: copy.deepcopy(next(iter(observations.values())))})
            self.assertIn("OBSERVATION_SET_MISMATCH", validate(self.c, request, result)[0], mode)
        self.assertFalse(self.c["qualification"]["structural_receipt_authenticates_source"]); self.assertEqual(self.c["qualification"]["default_support"], "unsupported")

    def test_t_source_snapshot_is_immutable_and_content_bound(self):
        request, result = fixture(); result["items"][0]["canonical_item_bytes"] = b'{"text": "synthetic"}'
        self.assertTrue({"NONCANONICAL_ITEM", "CONTENT_DRIFT", "SNAPSHOT_DRIFT"} <= validate(self.c, request, result)[0])
        for field in ("role", "source", "session_lineage_digest", "provenance_kind"):
            request, result = fixture(); result["items"][0][field] = "changed"; self.assertIn("SNAPSHOT_DRIFT", validate(self.c, request, result)[0], field)
        for field in ("turn_id", "primary_evidence"):
            request, result = fixture(); result["items"][0]["turn_receipt"][field] = False if field == "primary_evidence" else "changed"; self.assertIn("SNAPSHOT_DRIFT", validate(self.c, request, result)[0], field)
        request, result = fixture(); item = result["items"][0]; obs = next(iter(request["receipt_observations"].values())); item["canonical_item_bytes"] = b'{"text":"replacement"}'; item["turn_receipt"] = D005.receipt_from_observation(MATRIX, turn_id=obs["turn_id"], capture_route_id=obs["capture_route_id"], origin_route_id=obs["origin_route_id"], observed_bytes=item["canonical_item_bytes"], role=item["role"], source=item["source"], lineage=obs["session_lineage"], attestation=obs["launch_attestation"], d003=D003); seal(request, result)
        self.assertTrue({"OBSERVATION_MISMATCH", "INVALID_RECEIPT"} <= validate(self.c, request, result)[0])

    def test_t_source_incremental_scan_deduplicates_exact_replays(self):
        request, result = fixture(); result["items"].append(copy.deepcopy(result["items"][0])); seal(request, result)
        errors, unique = validate(self.c, request, result); self.assertEqual(errors, set()); self.assertEqual(len(unique), 1)
        request, result = fixture(); other = copy.deepcopy(result["items"][0]); other["provenance_kind"] = "changed"; result["items"].append(other); seal(request, result)
        self.assertTrue({"IDENTITY_CONFLICT", "INVALID_PROVENANCE"} <= validate(self.c, request, result)[0])

    def test_t_source_conflicting_identity_and_unknown_format_fail_closed(self):
        request, result = fixture(); other = copy.deepcopy(result["items"][0]); other["canonical_item_bytes"] = b'{"text":"different"}'; result["items"].append(other); result["format_revision"] = "unknown/v9"; seal(request, result)
        self.assertTrue({"IDENTITY_CONFLICT", "UNSUPPORTED_FORMAT"} <= validate(self.c, request, result)[0])
        request, result = fixture(); request["adapter_version"] = "9"; self.assertIn("UNSUPPORTED_VERSION", validate(self.c, request, result)[0])
        for key in ("max_items", "max_bytes"):
            request, result = fixture(); request["bounds"][key] = 1
            if key == "max_items": result["items"].append(copy.deepcopy(result["items"][0]))
            self.assertIn("BOUNDS_EXCEEDED", validate(self.c, request, result)[0], key)

    def test_t_source_partial_scan_cannot_propose_checkpoint_advance(self):
        request, result = fixture(); result["status"] = "partial"; self.assertIn("CHECKPOINT_ON_INCOMPLETE", validate(self.c, request, result)[0])
        request, result = fixture(); result.update(status="partial", errors=["watari.source-error.drift/v1"], checkpoint_proposal=None); self.assertEqual(validate(self.c, request, result)[0], set())
        request, result = fixture(); result["errors"] = ["watari.source-error.drift/v1"]; self.assertIn("STATUS_ERROR_MISMATCH", validate(self.c, request, result)[0])
        request, result = fixture(); result.update(status="partial", checkpoint_proposal=None); self.assertIn("STATUS_ERROR_MISMATCH", validate(self.c, request, result)[0])
        request, result = fixture(); result.update(status="rejected", errors=["unknown"], checkpoint_proposal=None); self.assertIn("INVALID_ERROR_TOKEN", validate(self.c, request, result)[0])
        request, result = fixture(); result["status"] = "unknown"; self.assertIn("INVALID_STATUS", validate(self.c, request, result)[0])
        request, result = fixture(); request["bounds"]["extra"] = 1; self.assertIn("INVALID_BOUNDS_SCHEMA", validate(self.c, request, result)[0])

    def test_t_source_checkpoint_is_non_authoritative_d004_proposal(self):
        request, result = fixture(); result["checkpoint_proposal"]["transaction_id"] = "forbidden"; self.assertIn("INVALID_CHECKPOINT_PROPOSAL", validate(self.c, request, result)[0])
        request, result = fixture(); result["checkpoint_proposal"]["opaque_position"] = "changed"; self.assertIn("CHECKPOINT_DIGEST", validate(self.c, request, result)[0])
        request, result = fixture(); request["committed_checkpoint"] = "raw"; seal(request, result); self.assertIn("INVALID_COMMITTED_CHECKPOINT", validate(self.c, request, result)[0])
        self.assertEqual(self.c["checkpoint"]["authority"], "proposal-only-D004-transaction-required")
        self.assertTrue(set(self.c["checkpoint"]["forbidden_fields"]).isdisjoint(self.c["schemas"]["checkpoint_proposal"]["fields"]))


if __name__ == "__main__": unittest.main()
