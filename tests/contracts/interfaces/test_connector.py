import copy
import hashlib
import importlib.util
import json
import re
import struct
import unittest
from pathlib import Path
ROOT = Path(__file__).parents[3]
DOC = ROOT / "docs/connector-contract.md"
ROUTE = ROOT / "docs/adr/005-data-routes.md"
POLICY = "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4"
CODES = {"NONE": 0, "INVALID_SCHEMA": 11, "UNSUPPORTED": 12, "AUTH": 20, "SOURCE": 21, "POLICY": 50, "PARTIAL": 60}
DKEYS = {"schema_version", "connector_instance_id", "qualification_status", "enabled", "ownership", "owner_device_id", "required", "source_policy", "source_policy_digest", "allowed_method_paths", "write_method_paths", "credential_reference_class", "credential_scope", "revocation_reference_class", "classification", "pagination_policy", "coordinator_policy", "retention_policy_id", "retry_policy", "checkpoint_lineage_binding", "route_template_contract_digest", "contract_digest"}
QKEYS = {"method", "path", "cursor"}
PKEYS = {"schema_version", "device_id", "connector_instance_id", "source_policy_digest", "source_lineage_digest", "snapshot_digest", "checkpoint_before_digest", "coordinator_epoch", "request_cursor", "next_cursor", "complete", "items", "error"}
IKEYS = {"stable_item_digest", "classification", "instruction_authority"}
CKEYS = {"schema_version", "provenance", "device_id", "connector_instance_id", "source_policy_digest", "source_lineage_digest", "snapshot_digest", "checkpoint_before_digest", "coordinator"}
OKEYS = {"verification_status", "latest_remote_verified", "online", "owner_revision_digest", "coordinator_device_id", "coordinator_epoch"}
RKEYS = {"schema_version", "status", "failure_token", "failure_code", "evidence_status", "accepted_item_digests", "next_cursor", "checkpoint_proposal", "canonical_write", "checkpoint_write", "external_write"}
BKEYS = {"device_id", "connector_instance_id", "source_policy_digest", "source_lineage_digest", "snapshot_digest", "checkpoint_before_digest", "coordinator_epoch", "accepted_item_set_digest"}
TKEYS = {"redirect_endpoint"}
CLASSIFICATION = {"raw_visibility": "local-only", "output_trust": "unverified-context;connector-evidence-only", "instruction_authority": "none", "model_egress": "deny", "credential_values": "forbidden"}
UNSAFE = (None, [], {}, True, 1, "", "../path", "Uppercase", "unicode-é")
def load_d003():
    spec = importlib.util.spec_from_file_location("d003_connector", ROOT / "tests/unit/test_canonical_vectors.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
D003 = load_d003()
def load_d005_connector():
    match = re.search(r"```json\n(.*?)\n```", ROUTE.read_text(encoding="utf-8"), re.DOTALL); matrix = json.loads(match.group(1))
    route = next(item for item in matrix["routes"] if item["route_id"] == "route.connector.read-only.v1")
    return route["connector_contract"]
D005 = load_d005_connector()
def digest(prefix, domain, value):
    raw = D003.canonical_bytes(value)
    frame = b"WATARI\0" + domain.encode() + b"\0" + struct.pack(">Q", len(raw)) + raw
    return prefix + hashlib.sha256(frame).hexdigest()
def token(prefix, value):
    return prefix + hashlib.sha256(value.encode()).hexdigest()
def is_token(value, prefix):
    return isinstance(value, str) and re.fullmatch(re.escape(prefix) + r"[0-9a-f]{64}", value) is not None
def safe_id(value):
    return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*", value) is not None
def prefixed_id(value, prefix):
    return isinstance(value, str) and re.fullmatch(re.escape(prefix) + r"[a-z0-9]+(?:-[a-z0-9]+)*", value) is not None
def cursor_token(descriptor, context, position):
    coordinator = context["coordinator"]
    body = {k: context[k] for k in ("device_id", "connector_instance_id", "source_policy_digest", "source_lineage_digest", "snapshot_digest", "checkpoint_before_digest")}
    body.update({"coordinator_epoch": coordinator["coordinator_epoch"] if coordinator else None, "position": position})
    return digest("watari-connector-cursor-v1:", "connector-cursor/v1", body)
def proposal_valid(value):
    if not isinstance(value, dict) or set(value) != BKEYS:
        return False
    epoch = value["coordinator_epoch"]
    return (prefixed_id(value["device_id"], "device-") and prefixed_id(value["connector_instance_id"], "connector-synthetic-")
            and value["source_policy_digest"] == D005["source_policy_digest"] and is_token(value["source_lineage_digest"], "watari-source-lineage-v1:")
            and is_token(value["snapshot_digest"], "watari-source-snapshot-v1:") and is_token(value["checkpoint_before_digest"], "watari-checkpoint-v1:")
            and (epoch is None or (type(epoch) is int and epoch >= 0)) and is_token(value["accepted_item_set_digest"], "watari-checkpoint-item-set-v1:"))
def machine():
    match = re.search(r"```json\n(.*?)\n```", DOC.read_text(encoding="utf-8"), re.DOTALL)
    if not match:
        raise AssertionError("D008 machine block missing")
    return json.loads(match.group(1))
def fixture(shared=False):
    descriptor = {
        "schema_version": "watari.connector-contract.v1", "connector_instance_id": "connector-synthetic-01",
        "qualification_status": "synthetic-structural-conformance-only",
        "enabled": True, "ownership": "shared" if shared else "device-local", "owner_device_id": None if shared else "device-01",
        "required": True, "source_policy": "enabled-read-only", "source_policy_digest": D005["source_policy_digest"],
        "allowed_method_paths": ["GET /approved-scope/**"], "write_method_paths": [],
        "credential_reference_class": "connector-read-only", "credential_scope": "connector-instance-scoped",
        "revocation_reference_class": "provider-managed-reference", "classification": copy.deepcopy(CLASSIFICATION),
        "pagination_policy": "snapshot-cursor-instance-policy-bound",
        "coordinator_policy": "shared-current-only-no-auto-failover" if shared else "device-local-only",
        "retention_policy_id": "retention.synthetic.v1", "retry_policy": "bounded-no-silent-success",
        "checkpoint_lineage_binding": "required-at-D008-evidence-boundary", "route_template_contract_digest": D005["contract_digest"], "contract_digest": ""}
    descriptor["contract_digest"] = digest("watari-connector-v1:", "connector-contract/v1", {k: v for k, v in descriptor.items() if k != "contract_digest"})
    lineage, snapshot = token("watari-source-lineage-v1:", "lineage"), token("watari-source-snapshot-v1:", "snapshot")
    context = {"schema_version": "watari.connector-trusted-context.v1", "provenance": "independent-trusted-state-verifier",
               "device_id": "device-01", "connector_instance_id": descriptor["connector_instance_id"],
               "source_policy_digest": descriptor["source_policy_digest"], "source_lineage_digest": lineage,
               "snapshot_digest": snapshot, "checkpoint_before_digest": token("watari-checkpoint-v1:", "before"), "coordinator": None}
    if shared:
        context["coordinator"] = {"verification_status": "verified-current", "latest_remote_verified": True, "online": True,
                                  "owner_revision_digest": token("watari-revision-v1:", "owner"),
                                  "coordinator_device_id": "device-01", "coordinator_epoch": 7}
    cursor = cursor_token(descriptor, context, 1)
    requests = [{"method": "GET", "path": "/approved-scope/a", "cursor": None}, {"method": "GET", "path": "/approved-scope/b", "cursor": cursor}]
    pages = []
    for index, request_cursor in enumerate((None, cursor)):
        pages.append({"schema_version": "watari.connector-page.v1", "device_id": "device-01",
                      "connector_instance_id": descriptor["connector_instance_id"], "source_policy_digest": descriptor["source_policy_digest"],
                      "source_lineage_digest": lineage, "snapshot_digest": snapshot,
                      "checkpoint_before_digest": context["checkpoint_before_digest"], "coordinator_epoch": 7 if shared else None,
                      "request_cursor": request_cursor, "next_cursor": cursor if index == 0 else None, "complete": index == 1,
                      "items": [{"stable_item_digest": "watari-source-v1:" + str(index + 1) * 64,
                                 "classification": "local-only", "instruction_authority": "none"}], "error": None})
    return descriptor, requests, pages, context
def outcome(name, status="rejected", items=(), proposal=None):
    return {"schema_version": "watari.connector-scan-result.v1", "status": status, "failure_token": name,
            "failure_code": CODES[name], "evidence_status": "accepted-at-D008-boundary" if status == "complete" else "rejected",
            "accepted_item_digests": list(items), "next_cursor": None, "checkpoint_proposal": proposal,
            "canonical_write": False, "checkpoint_write": False, "external_write": False}
def validate(descriptor, requests, pages, context, transport=lambda _request: {"redirect_endpoint": None}):
    if not isinstance(descriptor, dict):
        return outcome("INVALID_SCHEMA")
    try:
        canonical = D003.normalize(descriptor) == descriptor
    except (TypeError, ValueError):
        canonical = False
    body = {k: v for k, v in descriptor.items() if k != "contract_digest"}
    if set(descriptor) != DKEYS or descriptor.get("schema_version") != "watari.connector-contract.v1" or not canonical:
        return outcome("INVALID_SCHEMA")
    if not safe_id(descriptor["connector_instance_id"]) or type(descriptor["enabled"]) is not bool or type(descriptor["required"]) is not bool:
        return outcome("INVALID_SCHEMA")
    if descriptor["contract_digest"] != digest("watari-connector-v1:", "connector-contract/v1", body):
        return outcome("POLICY")
    if not descriptor["enabled"] or descriptor["qualification_status"] != "synthetic-structural-conformance-only" or not prefixed_id(descriptor["connector_instance_id"], "connector-synthetic-"):
        return outcome("UNSUPPORTED")
    template = {"required": D005["required"], "source_policy": D005["source_policy"], "source_policy_digest": D005["source_policy_digest"],
                "allowed_method_paths": D005["allowed_method_paths"], "credential_scope": D005["credential_scope"],
                "checkpoint_lineage_binding": D005["checkpoint_lineage_binding"], "route_template_contract_digest": D005["contract_digest"]}
    policy = (all(descriptor[key] == value for key, value in template.items()) and re.fullmatch(r"[a-z0-9-]+", descriptor["connector_instance_id"])
              and descriptor["classification"] == CLASSIFICATION
              and descriptor["write_method_paths"] == [] and descriptor["credential_reference_class"] == "connector-read-only"
              and descriptor["credential_scope"] == "connector-instance-scoped" and descriptor["pagination_policy"] == "snapshot-cursor-instance-policy-bound"
              and descriptor["revocation_reference_class"] == "provider-managed-reference" and safe_id(descriptor["retention_policy_id"])
              and descriptor["coordinator_policy"] == ("shared-current-only-no-auto-failover" if descriptor["ownership"] == "shared" else "device-local-only")
              and is_token(descriptor["source_policy_digest"], "watari-source-policy-v1:")
              and descriptor["retry_policy"] == "bounded-no-silent-success" and descriptor["checkpoint_lineage_binding"] == "required-at-D008-evidence-boundary")
    if not policy:
        return outcome("POLICY")
    if not isinstance(requests, list) or not isinstance(pages, list):
        return outcome("INVALID_SCHEMA")
    for request in requests:
        if not isinstance(request, dict) or set(request) != QKEYS:
            return outcome("INVALID_SCHEMA")
        path = request.get("path", "")
        if not isinstance(request["method"], str) or not isinstance(path, str) or (request["cursor"] is not None and not isinstance(request["cursor"], str)):
            return outcome("INVALID_SCHEMA")
        if request.get("method") != "GET" or not path.startswith("/approved-scope/") or ".." in path or "%2e" in path.lower() or "://" in path:
            return outcome("POLICY")
    if not isinstance(context, dict) or set(context) != CKEYS or context.get("schema_version") != "watari.connector-trusted-context.v1" or context.get("provenance") != "independent-trusted-state-verifier":
        return outcome("POLICY")
    if any(context[k] != descriptor[k] for k in ("connector_instance_id", "source_policy_digest")):
        return outcome("POLICY")
    typed_context = (("source_policy_digest", "watari-source-policy-v1:"), ("source_lineage_digest", "watari-source-lineage-v1:"), ("snapshot_digest", "watari-source-snapshot-v1:"), ("checkpoint_before_digest", "watari-checkpoint-v1:"))
    if any(not is_token(context[key], prefix) for key, prefix in typed_context):
        return outcome("POLICY")
    if not prefixed_id(context["device_id"], "device-"):
        return outcome("POLICY")
    coordinator = context["coordinator"]
    if descriptor["ownership"] == "device-local":
        if coordinator is not None or not prefixed_id(descriptor["owner_device_id"], "device-") or context["device_id"] != descriptor["owner_device_id"]:
            return outcome("POLICY")
    elif descriptor["ownership"] == "shared":
        if descriptor["owner_device_id"] is not None or not isinstance(coordinator, dict) or set(coordinator) != OKEYS or coordinator.get("verification_status") != "verified-current":
            return outcome("POLICY")
        if type(coordinator.get("latest_remote_verified")) is not bool or type(coordinator.get("online")) is not bool or not coordinator["latest_remote_verified"] or not coordinator["online"]:
            return outcome("POLICY")
        if coordinator.get("coordinator_device_id") != context["device_id"] or type(coordinator.get("coordinator_epoch")) is not int or coordinator["coordinator_epoch"] < 0 or not is_token(coordinator.get("owner_revision_digest"), "watari-revision-v1:"):
            return outcome("POLICY")
    else:
        return outcome("POLICY")
    for request in requests:
        response = transport(request)
        if not isinstance(response, dict) or set(response) != TKEYS:
            return outcome("INVALID_SCHEMA")
        if response["redirect_endpoint"] is not None:
            return outcome("POLICY")
    if len(requests) != len(pages) or not pages:
        return outcome("SOURCE")
    expected, seen_cursors, items = None, set(), []
    epoch = coordinator["coordinator_epoch"] if coordinator else None
    for index, (request, page) in enumerate(zip(requests, pages)):
        if not isinstance(page, dict) or set(page) != PKEYS or page.get("schema_version") != "watari.connector-page.v1":
            return outcome("INVALID_SCHEMA")
        if type(page["complete"]) is not bool or not isinstance(page["items"], list) or (page["error"] is not None and not isinstance(page["error"], str)):
            return outcome("INVALID_SCHEMA")
        if page["error"]:
            name = "AUTH" if page["error"] == "auth-expired" else "PARTIAL" if page["error"] in {"rate-limit", "timeout", "partial"} else "SOURCE"
            return outcome(name, "partial")
        if request["cursor"] != expected or page["request_cursor"] != expected:
            return outcome("SOURCE")
        comparisons = {"device_id": context["device_id"], "connector_instance_id": descriptor["connector_instance_id"],
                       "source_policy_digest": descriptor["source_policy_digest"], "source_lineage_digest": context["source_lineage_digest"],
                       "snapshot_digest": context["snapshot_digest"], "checkpoint_before_digest": context["checkpoint_before_digest"], "coordinator_epoch": epoch}
        if not prefixed_id(page["device_id"], "device-") or any(page[k] != v for k, v in comparisons.items()):
            return outcome("POLICY")
        nxt = page["next_cursor"]
        required_next = None if page["complete"] else cursor_token(descriptor, context, index + 1)
        invalid_page = page["complete"] != (index == len(pages) - 1) or nxt != required_next or (nxt is not None and (nxt == expected or nxt in seen_cursors))
        if invalid_page:
            return outcome("SOURCE")
        seen_cursors.add(expected)
        expected = nxt
        for item in page["items"]:
            if not isinstance(item, dict) or set(item) != IKEYS:
                return outcome("INVALID_SCHEMA")
            if item["classification"] != "local-only" or item["instruction_authority"] != "none" or not is_token(item["stable_item_digest"], "watari-source-v1:"):
                return outcome("POLICY")
            if item["stable_item_digest"] in items or (items and item["stable_item_digest"] <= items[-1]):
                return outcome("SOURCE")
            items.append(item["stable_item_digest"])
    proposal = {k: context[k] for k in ("device_id", "connector_instance_id", "source_policy_digest", "source_lineage_digest", "snapshot_digest", "checkpoint_before_digest")}
    proposal.update({"coordinator_epoch": epoch, "accepted_item_set_digest": digest("watari-checkpoint-item-set-v1:", "checkpoint-item-set/v1", items)})
    return outcome("NONE", "complete", items, proposal)
class ConnectorContractTest(unittest.TestCase):
    def test_t_connector_schema_closed_and_traced(self):
        model = machine()
        expected = {"schema_version", "unknown_policy", "support_policy", "schemas", "route_binding", "route_template_binding", "descriptor_fields", "scan_input_fields", "request_fields", "transport_response_fields", "page_fields", "item_fields", "trusted_context_fields", "coordinator_fields", "result_fields", "checkpoint_proposal_fields", "failure_codes", "trace"}
        self.assertEqual(set(model), expected)
        self.assertEqual((model["schema_version"], model["unknown_policy"]), ("D008.connector-contract.v1", "fail-closed"))
        self.assertEqual(model["schemas"], {"descriptor": "watari.connector-contract.v1", "scan_input": "watari.connector-scan-input.v1", "page": "watari.connector-page.v1", "trusted_context": "watari.connector-trusted-context.v1", "result": "watari.connector-scan-result.v1"})
        self.assertEqual((set(model["descriptor_fields"]), set(model["page_fields"]), set(model["trusted_context_fields"]), set(model["result_fields"])), (DKEYS, PKEYS, CKEYS, RKEYS))
        self.assertEqual((set(model["request_fields"]), set(model["transport_response_fields"]), set(model["item_fields"]), set(model["checkpoint_proposal_fields"])), (QKEYS, TKEYS, IKEYS, BKEYS))
        self.assertEqual((model["support_policy"], set(model["coordinator_fields"])), ("real-connectors-unsupported-until-X001-X011-Q016", OKEYS))
        self.assertEqual((model["scan_input_fields"], model["failure_codes"], set(model["trace"])), (["schema_version", "descriptor", "requests", "pages", "trusted_context"], CODES, {"RQ-005", "AC-005", "MX-005"}))
        self.assertEqual(model["route_binding"], {"route_id": "route.connector.read-only.v1", "route_policy_digest": POLICY})
        template = {key: D005[key] for key in ("required", "source_policy", "allowed_method_paths", "credential_scope", "source_policy_digest", "checkpoint_lineage_binding", "contract_digest")}; self.assertEqual(model["route_template_binding"], template)
        self.assertIn(POLICY, ROUTE.read_text(encoding="utf-8"))
        descriptor, requests, pages, context = fixture(); descriptor["unknown"] = True
        self.assertEqual(validate(descriptor, requests, pages, context)["failure_token"], "INVALID_SCHEMA")
        descriptor, requests, pages, context = fixture(); descriptor["enabled"] = False; descriptor["contract_digest"] = digest("watari-connector-v1:", "connector-contract/v1", {k: v for k, v in descriptor.items() if k != "contract_digest"})
        self.assertEqual(validate(descriptor, requests, pages, context)["failure_token"], "UNSUPPORTED")
        descriptor, requests, pages, context = fixture(); descriptor["retention_policy_id"] = "retention.e\u0301.v1"; descriptor["contract_digest"] = digest("watari-connector-v1:", "connector-contract/v1", {k: v for k, v in descriptor.items() if k != "contract_digest"}); self.assertEqual(validate(descriptor, requests, pages, context)["failure_token"], "INVALID_SCHEMA")
        descriptor, requests, pages, context = fixture(); descriptor["connector_instance_id"] = "gmail-production"; context["connector_instance_id"] = "gmail-production"; [page.__setitem__("connector_instance_id", "gmail-production") for page in pages]; descriptor["contract_digest"] = digest("watari-connector-v1:", "connector-contract/v1", {k: v for k, v in descriptor.items() if k != "contract_digest"}); self.assertEqual(validate(descriptor, requests, pages, context)["failure_token"], "UNSUPPORTED")
        descriptor, requests, pages, context = fixture(); requests[0]["unknown"] = True; self.assertEqual(validate(descriptor, requests, pages, context)["failure_token"], "INVALID_SCHEMA")
        for key, value in (("required", False), ("source_policy", "other"), ("allowed_method_paths", ["GET /other/**"]), ("credential_scope", "other"), ("source_policy_digest", token("watari-source-policy-v1:", "other")), ("checkpoint_lineage_binding", "other"), ("route_template_contract_digest", token("watari-connector-v1:", "other")), ("revocation_reference_class", "other")):
            descriptor, requests, pages, context = fixture(); descriptor[key] = value; descriptor["contract_digest"] = digest("watari-connector-v1:", "connector-contract/v1", {k: v for k, v in descriptor.items() if k != "contract_digest"}); self.assertEqual(validate(descriptor, requests, pages, context)["failure_token"], "POLICY")
        for bad in UNSAFE:
            descriptor, requests, pages, context = fixture(); descriptor["connector_instance_id"] = bad; descriptor["contract_digest"] = digest("watari-connector-v1:", "connector-contract/v1", {k: v for k, v in descriptor.items() if k != "contract_digest"}); result = validate(descriptor, requests, pages, context); self.assertIn(result["failure_token"], {"INVALID_SCHEMA", "UNSUPPORTED"}); self.assertIsNone(result["checkpoint_proposal"])
            descriptor, requests, pages, context = fixture(); descriptor["retention_policy_id"] = bad; descriptor["contract_digest"] = digest("watari-connector-v1:", "connector-contract/v1", {k: v for k, v in descriptor.items() if k != "contract_digest"}); result = validate(descriptor, requests, pages, context); self.assertIn(result["failure_token"], {"INVALID_SCHEMA", "POLICY"}); self.assertIsNone(result["checkpoint_proposal"])
    def test_t_connector_accepts_bounded_get_complete_scan(self):
        result = validate(*fixture())
        self.assertEqual((set(result), result["status"], result["failure_code"], result["evidence_status"]), (RKEYS, "complete", 0, "accepted-at-D008-boundary"))
        self.assertIsNotNone(result["checkpoint_proposal"])
        self.assertTrue(proposal_valid(result["checkpoint_proposal"])); bad = dict(result["checkpoint_proposal"]); bad["unknown"] = True; self.assertFalse(proposal_valid(bad)); bad.pop("unknown"); bad.pop("snapshot_digest"); self.assertFalse(proposal_valid(bad))
        for key in BKEYS:
            bad = dict(result["checkpoint_proposal"]); bad[key] = True if key == "coordinator_epoch" else None; self.assertFalse(proposal_valid(bad), key)
        for unsafe in UNSAFE:
            bad = dict(result["checkpoint_proposal"]); bad["device_id"] = unsafe; self.assertFalse(proposal_valid(bad)); bad = dict(result["checkpoint_proposal"]); bad["connector_instance_id"] = unsafe; self.assertFalse(proposal_valid(bad))
        self.assertFalse(any(result[k] for k in ("canonical_write", "checkpoint_write", "external_write")))
    def test_t_connector_rejects_write_unknown_and_scope_escape_before_io(self):
        for method, path in (("POST", "/approved-scope/a"), ("PUT", "/approved-scope/a"), ("PATCH", "/approved-scope/a"), ("DELETE", "/approved-scope/a"), ("HEAD", "/approved-scope/a"), ("GET", "/other/a"), ("GET", "/approved-scope/../secret"), ("GET", "/approved-scope/%2e%2e/secret"), ("GET", "https://evil.invalid/a")):
            descriptor, requests, pages, context = fixture(); requests[0].update(method=method, path=path); calls = []
            self.assertEqual((validate(descriptor, requests, pages, context, calls.append)["failure_token"], calls), ("POLICY", []))
        descriptor, requests, pages, context = fixture(); calls = []; result = validate(descriptor, requests, pages, context, lambda request: (calls.append(request) or {"redirect_endpoint": "endpoint.evil"})); self.assertEqual((result["failure_token"], len(calls)), ("POLICY", 1))
    def test_t_connector_rejects_classification_instruction_and_secret_escalation(self):
        for key, value in (("raw_visibility", "trusted-model"), ("model_egress", "allow"), ("instruction_authority", "system"), ("credential_values", "present")):
            descriptor, requests, pages, context = fixture(); descriptor["classification"][key] = value
            descriptor["contract_digest"] = digest("watari-connector-v1:", "connector-contract/v1", {k: v for k, v in descriptor.items() if k != "contract_digest"})
            self.assertEqual(validate(descriptor, requests, pages, context)["failure_token"], "POLICY")
        descriptor, requests, pages, context = fixture(); pages[0]["items"][0]["credential"] = "synthetic-secret"; self.assertEqual(validate(descriptor, requests, pages, context)["failure_token"], "INVALID_SCHEMA")
        descriptor, requests, pages, context = fixture(); pages[0]["items"][0].pop("classification"); self.assertEqual(validate(descriptor, requests, pages, context)["failure_token"], "INVALID_SCHEMA")
    def test_t_connector_binds_pagination_to_instance_policy_snapshot_and_order(self):
        mutations = ((0, "next_cursor", None), (1, "next_cursor", "cursor-2"), (1, "request_cursor", "wrong"), (1, "connector_instance_id", "other"), (1, "source_policy_digest", "other"), (1, "snapshot_digest", "other"))
        for index, key, value in mutations:
            descriptor, requests, pages, context = fixture(); pages[index][key] = value
            self.assertNotEqual(validate(descriptor, requests, pages, context)["status"], "complete")
        descriptor, requests, pages, context = fixture(); pages[1]["items"][0] = copy.deepcopy(pages[0]["items"][0])
        self.assertEqual(validate(descriptor, requests, pages, context)["failure_token"], "SOURCE")
        descriptor, requests, pages, context = fixture(); pages[1]["complete"] = False; pages[1]["next_cursor"] = requests[1]["cursor"]; requests.append({"method": "GET", "path": "/approved-scope/c", "cursor": requests[1]["cursor"]}); tail = copy.deepcopy(pages[1]); tail.update(request_cursor=requests[1]["cursor"], next_cursor=None, complete=True); tail["items"][0]["stable_item_digest"] = "watari-source-v1:" + "3" * 64; pages.append(tail); self.assertEqual(validate(descriptor, requests, pages, context)["failure_token"], "SOURCE")
        descriptor, requests, pages, context = fixture(); foreign = copy.deepcopy(context); foreign["checkpoint_before_digest"] = token("watari-checkpoint-v1:", "foreign"); forged = cursor_token(descriptor, foreign, 1); pages[0]["next_cursor"] = requests[1]["cursor"] = pages[1]["request_cursor"] = forged; self.assertEqual(validate(descriptor, requests, pages, context)["failure_token"], "SOURCE")
    def test_t_connector_failures_are_typed_and_never_advance_checkpoint(self):
        for error, expected in (("auth-expired", "AUTH"), ("unknown-source", "SOURCE"), ("rate-limit", "PARTIAL"), ("timeout", "PARTIAL"), ("partial", "PARTIAL")):
            descriptor, requests, pages, context = fixture(); pages[0]["error"] = error; result = validate(descriptor, requests, pages, context)
            self.assertEqual((result["failure_token"], result["failure_code"], result["checkpoint_proposal"]), (expected, CODES[expected], None))
        descriptor, requests, pages, context = fixture(); pages[0]["schema_version"] = "watari.connector-page.v2"
        self.assertEqual(validate(descriptor, requests, pages, context)["failure_token"], "INVALID_SCHEMA")
        for case in ("descriptor", "descriptor-id", "requests", "request", "path", "page", "items", "item-value", "context-value"):
            descriptor, requests, pages, context = fixture()
            if case == "descriptor": descriptor = None
            elif case == "descriptor-id": descriptor["connector_instance_id"] = None
            elif case == "requests": requests = None
            elif case == "request": requests[0] = None
            elif case == "path": requests[0]["path"] = None
            elif case == "page": pages[0] = None
            elif case == "items": pages[0]["items"] = None
            elif case == "item-value": pages[0]["items"][0]["stable_item_digest"] = None
            else: context["source_lineage_digest"] = None
            result = validate(descriptor, requests, pages, context); self.assertIn(result["failure_token"], {"INVALID_SCHEMA", "POLICY", "SOURCE"}, case); self.assertIsNone(result["checkpoint_proposal"], case)
    def test_t_connector_shared_source_requires_independent_current_coordinator(self):
        self.assertEqual(validate(*fixture(shared=True))["status"], "complete")
        for key, value in (("online", False), ("latest_remote_verified", False), ("online", 1), ("online", 1.0), ("latest_remote_verified", 1), ("latest_remote_verified", 1.0), ("verification_status", "stale"), ("coordinator_device_id", "device-02"), ("coordinator_epoch", "7")):
            descriptor, requests, pages, context = fixture(shared=True); context["coordinator"][key] = value; calls = []
            self.assertEqual((validate(descriptor, requests, pages, context, calls.append)["failure_token"], calls), ("POLICY", []))
        descriptor, requests, pages, context = fixture(shared=True); pages[0]["trusted_context"] = context; calls = []
        self.assertEqual((validate(descriptor, requests, pages, None, calls.append)["status"], calls), ("rejected", []))
        descriptor, requests, pages, context = fixture(shared=True); descriptor["owner_device_id"] = "device-02"; descriptor["contract_digest"] = digest("watari-connector-v1:", "connector-contract/v1", {k: v for k, v in descriptor.items() if k != "contract_digest"}); calls = []; self.assertEqual((validate(descriptor, requests, pages, context, calls.append)["failure_token"], calls), ("POLICY", []))
    def test_t_connector_verifies_independent_checkpoint_lineage_at_evidence_boundary(self):
        descriptor, requests, pages, context = fixture(shared=True)
        self.assertEqual(validate(descriptor, requests, pages, context)["evidence_status"], "accepted-at-D008-boundary")
        for key in ("device_id", "connector_instance_id", "source_policy_digest", "source_lineage_digest", "snapshot_digest", "checkpoint_before_digest"):
            bad = copy.deepcopy(context); bad[key] = "forged"; calls = []
            self.assertEqual((validate(descriptor, requests, pages, bad, calls.append)["evidence_status"], calls), ("rejected", []))
        bad = copy.deepcopy(context); bad["coordinator"]["coordinator_epoch"] += 1
        self.assertIsNone(validate(descriptor, requests, pages, bad)["checkpoint_proposal"])
        self.assertEqual(validate(descriptor, requests, pages, None)["evidence_status"], "rejected")
        descriptor, requests, pages, context = fixture(); descriptor["source_policy_digest"] = context["source_policy_digest"] = "plain"; [page.__setitem__("source_policy_digest", "plain") for page in pages]; descriptor["contract_digest"] = digest("watari-connector-v1:", "connector-contract/v1", {k: v for k, v in descriptor.items() if k != "contract_digest"}); self.assertEqual(validate(descriptor, requests, pages, context)["failure_token"], "POLICY")
        for unsafe in UNSAFE:
            descriptor, requests, pages, context = fixture(); descriptor["owner_device_id"] = context["device_id"] = unsafe; [page.__setitem__("device_id", unsafe) for page in pages]; descriptor["contract_digest"] = digest("watari-connector-v1:", "connector-contract/v1", {k: v for k, v in descriptor.items() if k != "contract_digest"}); calls = []; result = validate(descriptor, requests, pages, context, calls.append); self.assertIn(result["failure_token"], {"INVALID_SCHEMA", "POLICY"}); self.assertIsNone(result["checkpoint_proposal"]); self.assertEqual(calls, [])
if __name__ == "__main__":
    unittest.main()
