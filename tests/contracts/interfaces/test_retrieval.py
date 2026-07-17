import copy
import hashlib
import hmac
import json
import re
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).parents[3]
DOC = ROOT / "docs" / "retrieval-contract.md"
ROUTES = ROOT / "docs" / "adr" / "005-data-routes.md"
RUNTIME = ROOT / "docs" / "runtime-contract.md"
DATA_CONTRACT = ROOT / "docs" / "data-contract.md"
CANONICAL_VECTORS = ROOT / "tests" / "fixtures" / "canonical" / "vectors.json"
OPS = ["memory.search", "memory.get", "memory.explain"]
D003_EVENT_NAMESPACE = "watari-event-v1:"
D003_CANONICAL_EVENT_ID = "watari-event-v1:260cb9d801fe49eb2a208ae6412eca048900e4ba15944aa0b75131e18c983251"
D003_EVENT_ID_IN_TEXT = re.compile(r"(?<![A-Za-z0-9])watari-event-v1:[0-9a-f]{64}(?![A-Za-z0-9])", re.I)
FILE_ABSOLUTE_URI = re.compile(r"(?<![A-Za-z0-9+.-])file:(?:/{1,3}|\\{1,2})[^\s]+", re.I)
POSIX_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9/])/(?!/)(?:[^/\\\s]+/)*[^/\\\s]+")
MULTISLASH_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9:/])/{2,}[^/\\\s]+(?:/[^/\\\s]+)*")
WINDOWS_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/](?:[^\\/\s]+[\\/])*[^\\/\s]+|\\\\[^\\/\s]+[\\/][^\\/\s]+(?:[\\/][^\\/\s]+)*)")
ROUTE_FIELDS = [
    "route_id", "caller_runtime", "provider_model_class", "provider_id",
    "model_id", "endpoint_id", "network_endpoint_class", "credential_scope",
    "fallback_policy", "retention_zdr", "route_policy_digest",
]
SESSION_FIELDS = [
    "schema_version", "session_id", "runtime_id", "adapter_version", "route_id",
    "caller_runtime", "provider_model_class", "provider_id", "model_id", "endpoint_id",
    "network_endpoint_class", "credential_scope", "fallback_policy", "retention_zdr",
    "route_policy_digest", "visibility", "profile_revision", "memory_revision",
    "canonical_fingerprint", "effective_fingerprint", "project_mode", "project_digest",
    "project_root_scope_digest", "capability_digest", "launch_attestation_digest",
    "issued_at", "expires_at", "support_status",
]
CLOSED = {
    "schemas": {"session", "request", "response", "result_ref", "audit_receipt", "candidate_proposal"},
    "route_binding": {"registry_schema", "runtime_contract_schema", "policy_revision", "policy_digest", "identity_fields", "identity_source", "required_capability", "fallback"},
    "session_binding": {"server_fixed_fields", "field_source", "revision_semantics", "client_override", "transport", "capability_token", "expiry", "replay", "global_registration", "state_key_mount", "same_uid_boundary_claim"},
    "digest_formats": {"session_id_digest", "session_id_digest_origin", "source_binding", "proposal_digest"},
    "request_shapes": set(OPS),
    "response_shapes": {"common_fields", "search_fields", "get_fields", "explain_fields", "result_fields", "unknown_fields"},
    "reference_policy": {"kind", "origin", "scope_bindings", "raw_event_id_input", "raw_event_id_output", "cross_session", "expired", "enumeration", "absolute_host_path", "forbidden_search_modes"},
    "bounds": {"query_max_utf8_bytes", "search_max_results", "search_max_response_bytes", "get_max_response_bytes", "explain_max_response_bytes", "session_max_unique_results", "session_max_response_bytes", "pagination", "request_over_limit", "result_over_limit"},
    "project_trust": {"modes", "approved_required_fields", "none_required_values", "source", "changed", "auto_discovery", "authority", "absolute_host_path_exposure", "record_text_path_revalidation"},
    "audit_receipt": {"schema", "fields", "event_ids", "response_exposure", "forbidden"},
    "proposal_boundary": {"handoff_operation", "schema", "required_server_bindings", "result", "review", "retrieval_service_persistence", "denied_writes"},
    "qualification": {"structural_status", "real_runtime_default", "supported_requires", "structural_tests_do_not_qualify"},
}
PINNED = {
    "schemas": {"session": "watari.retrieval-session.v1", "request": "watari.retrieval-request.v1", "response": "watari.retrieval-response.v1", "result_ref": "watari.retrieval-result-ref.v1", "audit_receipt": "watari.retrieval-audit-receipt.v1", "candidate_proposal": "watari.memory-candidate-proposal.v1"},
    "route_binding": {"registry_schema": "watari.route-matrix.v1", "runtime_contract_schema": "watari.runtime-contract.v1", "policy_revision": "D003.route-policy.v1", "policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4", "identity_fields": ROUTE_FIELDS, "identity_source": "trusted-server-registry-only", "required_capability": "allow:session-scoped-retrieval", "fallback": "disabled"},
    "session_binding": {"server_fixed_fields": SESSION_FIELDS, "field_source": "trusted-explicit-launch-registration-snapshot", "revision_semantics": "exact-session-snapshot", "client_override": "deny", "transport": "owner-only-session-scoped-local-capability", "capability_token": "ephemeral-unlogged", "expiry": "required", "replay": "deny-request-id-reuse", "global_registration": "deny", "state_key_mount": "deny", "same_uid_boundary_claim": "deny"},
    "digest_formats": {"session_id_digest": "watari.retrieval-session-id-digest.v1", "session_id_digest_origin": "server-private-domain-separated-hmac-sha256", "source_binding": "watari.memory-source-binding.v1", "proposal_digest": "watari.memory-candidate-proposal-digest.v1"},
    "request_shapes": {"memory.search": ["schema_version", "request_id", "operation", "query", "limit"], "memory.get": ["schema_version", "request_id", "operation", "result_ref"], "memory.explain": ["schema_version", "request_id", "operation", "result_ref"]},
    "response_shapes": {"common_fields": ["schema_version", "request_id", "operation", "audit_receipt_id"], "search_fields": ["results", "returned_count", "returned_bytes", "truncated"], "get_fields": ["result_ref", "projection", "returned_bytes", "truncated"], "explain_fields": ["result_ref", "route_id", "visibility", "profile_revision", "memory_revision", "project_digest", "selection_reason", "returned_bytes", "truncated"], "result_fields": ["result_ref", "projection", "returned_bytes"], "unknown_fields": "deny"},
    "reference_policy": {"kind": "opaque-session-digest-reference", "origin": "server-private-secret-nonce-digest", "scope_bindings": ["full-registered-session-snapshot", "event-identity", "server-private-nonce"], "raw_event_id_input": "deny", "raw_event_id_output": "deny", "cross_session": "deny", "expired": "deny", "enumeration": "deny", "absolute_host_path": "deny", "forbidden_search_modes": ["empty", "wildcard", "match-all", "cursor", "offset", "raw-event-id"]},
    "bounds": {"query_max_utf8_bytes": 4096, "search_max_results": 20, "search_max_response_bytes": 65536, "get_max_response_bytes": 32768, "explain_max_response_bytes": 8192, "session_max_unique_results": 100, "session_max_response_bytes": 262144, "pagination": "deny", "request_over_limit": "policy-deny-no-clamp", "result_over_limit": "explicit-truncation-with-audit"},
    "project_trust": {"modes": ["none", "approved"], "approved_required_fields": ["project_digest", "project_root_scope_digest"], "none_required_values": {"project_digest": None, "project_root_scope_digest": None}, "source": "trusted-launch-receipt-only", "changed": "reapproval-required", "auto_discovery": "deny", "authority": "deny-route-visibility-revision-change", "absolute_host_path_exposure": "deny", "record_text_path_revalidation": "fail-closed-at-load-and-before-return"},
    "audit_receipt": {"schema": "watari.retrieval-audit-receipt.v1", "fields": ["audit_receipt_id", "session_id_digest", "request_id", "operation", "route_id", "route_policy_digest", "profile_revision", "memory_revision", "project_digest", "returned_event_ids", "returned_count", "returned_bytes", "truncated", "outcome"], "event_ids": "local-audit-only", "response_exposure": "audit-receipt-id-only", "forbidden": ["query", "projection", "semantic-bytes", "result-ref", "capability-token", "credential", "absolute-host-path"]},
    "proposal_boundary": {"handoff_operation": "memory.propose", "schema": "watari.memory-candidate-proposal.v1", "required_server_bindings": ["session_id_digest", "route_id", "route_policy_digest", "profile_revision", "memory_revision", "project_digest", "source_binding", "proposal_digest"], "result": "immutable-candidate-only", "review": "required-before-canonical-event", "retrieval_service_persistence": "deny", "denied_writes": ["canonical-event", "profile", "checkpoint", "credential", "project", "connector", "external-action"]},
    "qualification": {"structural_status": "unqualified", "real_runtime_default": "unsupported", "supported_requires": ["observed-runtime-evidence", "qualified-sandbox-evidence"], "structural_tests_do_not_qualify": True},
    "failure_codes": {"INVALID_SCHEMA": 11, "UNSUPPORTED": 12, "INTEGRITY": 40, "POLICY": 50},
}
PINNED_TOP = {"schema_version": "watari.retrieval-contract.v1", "unknown_policy": "fail-closed", "operations": OPS, "requirements_trace": ["RQ-009", "RQ-012", "RQ-013", "NM-004", "NM-005", "AC-009", "AC-012", "AC-013", "SB-003", "SB-006"], "open_decisions": ["DEC-OPEN-003", "DEC-OPEN-004"]}
POLICY_COUNTEREXAMPLES = [
    ("session_binding", "state_key_mount", "allow"), ("session_binding", "same_uid_boundary_claim", "allow"),
    ("session_binding", "global_registration", "allow"), ("session_binding", "transport", "global"),
    ("session_binding", "capability_token", "logged"), ("reference_policy", "forbidden_search_modes", []),
    ("bounds", "session_max_response_bytes", 262145), ("bounds", "pagination", "allow"),
    ("bounds", "request_over_limit", "silent-clamp"), ("bounds", "result_over_limit", "silent"),
    ("project_trust", "changed", "allow"), ("project_trust", "authority", "allow"),
    ("project_trust", "record_text_path_revalidation", "skip"),
    ("audit_receipt", "forbidden", []), ("proposal_boundary", "retrieval_service_persistence", "allow"),
    ("proposal_boundary", "denied_writes", []), ("proposal_boundary", "handoff_operation", "memory.write"),
    ("failure_codes", "POLICY", 0), ("qualification", "structural_tests_do_not_qualify", 0),
    ("reference_policy", "forbidden_search_modes", ["empty", "wildcard", "match-all", "cursor", "offset", "raw-event-id", "raw-event-id"]),
]


class Reject(ValueError):
    pass


def json_block(path):
    blocks = re.findall(r"```json\n(.*?)\n```", path.read_text(encoding="utf-8"), re.S)
    if len(blocks) != 1:
        raise AssertionError(f"expected one JSON block in {path}, got {len(blocks)}")

    def closed(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate key: {key}")
            value[key] = item
        return value

    return json.loads(blocks[0], object_pairs_hook=closed)


def timestamp(value):
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise Reject("timestamp")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def strict_equal(actual, expected):
    if type(actual) is not type(expected): return False
    if isinstance(expected, dict): return set(actual) == set(expected) and all(strict_equal(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list): return len(actual) == len(expected) and all(strict_equal(a, e) for a, e in zip(actual, expected))
    return actual == expected


def contains_absolute_host_path(value):
    return bool(FILE_ABSOLUTE_URI.search(value) or POSIX_ABSOLUTE_PATH.search(value) or MULTISLASH_ABSOLUTE_PATH.search(value) or WINDOWS_ABSOLUTE_PATH.search(value))


class SyntheticRetrievalServer:
    def __init__(self, contract, matrix, now="2026-07-17T00:30:00Z", records=None,
                 profile_revision="profile.v1", memory_revision="memory.v1"):
        self.c, self.routes, self.now = contract, {r["route_id"]: r for r in matrix["routes"]}, timestamp(now)
        self.profile_revision, self.memory_revision = profile_revision, memory_revision
        self.records = records or [
            {"event_id": "event.synthetic.2048", "projection": "x" * 2048, "reason": "selected-by-policy"},
            {"event_id": "event.synthetic.2", "projection": "second synthetic memory", "reason": "selected-by-policy"},
            {"event_id": "event.synthetic.3", "projection": "another synthetic memory", "reason": "selected-by-policy"},
        ]
        for record in self.records: self._validate_record(record)
        self.refs, self.audits, self.seen_request_ids = {}, {}, set()
        self.sessions, self.requests, self.results, self.audit_requests = {}, {}, {}, {}
        self.session_bytes, self.session_events = {}, {}
        self.ref_counter = self.audit_counter = 0
        self.secret = b"server-private-synthetic-retrieval-secret"
        for key, value in self.c["bounds"].items():
            if key.endswith(("_bytes", "_results")) and type(value) is not int:
                raise Reject("bound-type")
        self._pin_policy()

    def _pin_policy(self):
        if any(not strict_equal(self.c[section], expected) for section, expected in PINNED.items()):
            raise Reject("unpinned-policy")
        if any(not strict_equal(self.c.get(key), value) for key, value in PINNED_TOP.items()): raise Reject("unpinned-top")

    @staticmethod
    def _validate_record(record):
        if type(record) is not dict or type(record.get("event_id")) is not str: raise Reject("record-shape")
        for field in ("projection", "reason"):
            value = record.get(field)
            if type(value) is not str or contains_absolute_host_path(value):
                raise Reject("absolute-host-path")
        return record

    def validate_session(self, session):
        if set(session) != set(SESSION_FIELDS) or session["schema_version"] != self.c["schemas"]["session"]:
            raise Reject("session-shape")
        route_id = session["route_id"]
        if type(route_id) is not str: raise Reject("route-id")
        route = self.routes.get(route_id)
        if not route or route["capability_set"]["retrieval"] != self.c["route_binding"]["required_capability"]:
            raise Reject("route-capability")
        for key in ROUTE_FIELDS:
            if session[key] != route[key]:
                raise Reject(f"route:{key}")
        if route["input_visibility"] != [session["visibility"]]:
            raise Reject("visibility")
        if session["profile_revision"] != self.profile_revision or session["memory_revision"] != self.memory_revision:
            raise Reject("revision")
        if session["support_status"] != "unsupported":
            raise Reject("unqualified")
        if session["project_mode"] == "none":
            if session["project_digest"] is not None or session["project_root_scope_digest"] is not None:
                raise Reject("project-none")
        elif session["project_mode"] == "approved":
            patterns = {"project_digest": r"watari-project-v1:[0-9a-f]{64}", "project_root_scope_digest": r"watari-project-root-v1:[0-9a-f]{64}"}
            if any(type(session[key]) is not str or not re.fullmatch(pattern, session[key]) for key, pattern in patterns.items()):
                raise Reject("project-approved")
        else:
            raise Reject("project-mode")
        for key in ("session_id", "runtime_id", "adapter_version", "profile_revision", "memory_revision"):
            if type(session[key]) is not str or not session[key]:
                raise Reject(f"typed:{key}")
        typed = {"canonical_fingerprint": r"watari-context-canonical-v1:[0-9a-f]{64}", "effective_fingerprint": r"watari-context-effective-v1:[0-9a-f]{64}", "capability_digest": r"watari-capability-v1:[0-9a-f]{64}", "launch_attestation_digest": r"watari-attestation-v1:[0-9a-f]{64}"}
        if any(type(session[key]) is not str or not re.fullmatch(pattern, session[key]) for key, pattern in typed.items()): raise Reject("typed-binding")
        issued, expires = timestamp(session["issued_at"]), timestamp(session["expires_at"])
        if not issued <= self.now < expires:
            raise Reject("expired")
        return route

    def register_launch(self, session):
        route = self.validate_session(session); session_id = session["session_id"]
        if session_id in self.sessions: raise Reject("duplicate-session-id")
        self.sessions[session_id] = copy.deepcopy(session)
        return route

    def _trusted_session(self, session):
        if type(session) is not dict or type(session.get("session_id")) is not str: raise Reject("presented-session")
        snapshot = self.sessions.get(session["session_id"])
        if snapshot is None or snapshot != session: raise Reject("session-snapshot-mismatch")
        self.validate_session(snapshot)
        return snapshot

    def _validate_request(self, session, request):
        session = self._trusted_session(session)
        operation = request.get("operation")
        if type(operation) is not str: raise Reject("operation-type")
        shape = self.c["request_shapes"].get(operation)
        if shape is None or set(request) != set(shape):
            raise Reject("request-shape")
        if request["schema_version"] != self.c["schemas"]["request"]:
            raise Reject("request-schema")
        request_id = request["request_id"]
        if type(request_id) is not str or not request_id or request_id in self.seen_request_ids:
            raise Reject("request-replay")
        if operation == "memory.search":
            query, limit = request["query"], request["limit"]
            if type(query) is not str or not query.strip() or len(query.encode("utf-8")) > self.c["bounds"]["query_max_utf8_bytes"]:
                raise Reject("query")
            folded = query.strip().casefold()
            if "*" in query or "?" in query or folded in {"all", "match all", "match-all"}:
                raise Reject("all-records")
            if folded.startswith("raw-event-id:") or re.fullmatch(r"event\.[a-z0-9._:-]+", folded) or D003_EVENT_ID_IN_TEXT.search(query):
                raise Reject("raw-event-id")
            if type(limit) is not int or not 1 <= limit <= self.c["bounds"]["search_max_results"]:
                raise Reject("limit")
        else:
            ref = request["result_ref"]
            if type(ref) is not str or not re.fullmatch(re.escape(self.c["schemas"]["result_ref"]) + r":[0-9a-f]{64}", ref):
                raise Reject("result-ref")
        self.seen_request_ids.add(request_id)
        self.requests[request_id] = {"session": copy.deepcopy(session), "request": copy.deepcopy(request)}
        return session

    def _mint(self, session, record):
        record = self._validate_record(record)
        self.ref_counter += 1
        nonce = self.ref_counter.to_bytes(8, "big")
        material = json.dumps({"session": session, "event_id": record["event_id"]}, sort_keys=True, separators=(",", ":")).encode()
        ref = f'{self.c["schemas"]["result_ref"]}:{hashlib.sha256(self.secret + nonce + material).hexdigest()}'
        self.refs[ref] = {"session": copy.deepcopy(session), "record": copy.deepcopy(record)}
        return ref

    def _resolve(self, session, ref):
        session = self._trusted_session(session)
        stored = self.refs.get(ref)
        if stored is None or stored["session"] != session:
            raise Reject("forged-or-cross-session-ref")
        return self._validate_record(stored["record"])

    @staticmethod
    def _cut(text, maximum):
        raw = text.encode("utf-8")
        projected = raw[:maximum].decode("utf-8", "ignore")
        return projected, len(projected.encode("utf-8")), len(raw) > len(projected.encode("utf-8"))

    def _remaining(self, session):
        return max(0, self.c["bounds"]["session_max_response_bytes"] - self.session_bytes.get(session["session_id"], 0))

    def _session_digest(self, session):
        message = b"watari/retrieval/session-id-digest/v1\x00" + session["session_id"].encode("utf-8")
        digest = hmac.new(self.secret, message, hashlib.sha256).hexdigest()
        return f'{self.c["digest_formats"]["session_id_digest"]}:{digest}'

    def _audit(self, request_id):
        state = self.results[request_id]; session, request = state["session"], state["request"]
        self.audit_counter += 1
        values = [
            f"audit.synthetic.{self.audit_counter}", self._session_digest(session), request["request_id"],
            request["operation"], session["route_id"], session["route_policy_digest"], session["profile_revision"],
            session["memory_revision"], session["project_digest"], list(state["event_ids"]), len(state["event_ids"]),
            state["returned_bytes"], state["truncated"], "ok",
        ]
        receipt = dict(zip(self.c["audit_receipt"]["fields"], values))
        self.audits[receipt["audit_receipt_id"]] = receipt
        self.audit_requests[receipt["audit_receipt_id"]] = request_id
        self.validate_audit(receipt)
        return receipt

    def validate_audit(self, receipt):
        if type(receipt) is not dict or set(receipt) != set(self.c["audit_receipt"]["fields"]): raise Reject("audit-shape")
        request_id = self.audit_requests.get(receipt.get("audit_receipt_id"))
        state = self.results.get(request_id)
        if state is None or receipt.get("request_id") != request_id: raise Reject("audit-authority")
        session, request = state["session"], state["request"]
        values = [receipt["audit_receipt_id"], self._session_digest(session), request_id, request["operation"],
                  session["route_id"], session["route_policy_digest"], session["profile_revision"], session["memory_revision"],
                  session["project_digest"], list(state["event_ids"]), len(state["event_ids"]), state["returned_bytes"], state["truncated"], "ok"]
        expected = dict(zip(self.c["audit_receipt"]["fields"], values))
        if any(type(receipt[k]) is not int or receipt[k] < 0 for k in ("returned_count", "returned_bytes")): raise Reject("audit-int")
        if type(receipt["truncated"]) is not bool or type(receipt["returned_event_ids"]) is not list: raise Reject("audit-types")
        if not all(type(event_id) is str for event_id in receipt["returned_event_ids"]): raise Reject("audit-event-type")
        if receipt != expected: raise Reject("audit-correlation")
        return True

    def _response(self, session, request, body, event_ids, returned_bytes, truncated):
        self.results[request["request_id"]] = {"session": copy.deepcopy(self.sessions[session["session_id"]]),
                                               "request": copy.deepcopy(self.requests[request["request_id"]]["request"]),
                                               "body": copy.deepcopy(body), "event_ids": list(event_ids),
                                               "returned_bytes": returned_bytes, "truncated": truncated}
        receipt = self._audit(request["request_id"])
        response = {"schema_version": self.c["schemas"]["response"], "request_id": request["request_id"],
                    "operation": request["operation"], "audit_receipt_id": receipt["audit_receipt_id"], **body}
        self.validate_response(response)
        return response

    def validate_response(self, response):
        if type(response) is not dict: raise Reject("response-type")
        state = self.results.get(response.get("request_id"))
        if state is None: raise Reject("response-authority")
        request, session = state["request"], state["session"]
        names = {"memory.search": "search_fields", "memory.get": "get_fields", "memory.explain": "explain_fields"}
        shape = set(self.c["response_shapes"]["common_fields"] + self.c["response_shapes"][names[request["operation"]]])
        audit_id = next((key for key, value in self.audit_requests.items() if value == request["request_id"]), None)
        expected = {"schema_version": self.c["schemas"]["response"], "request_id": request["request_id"],
                    "operation": request["operation"], "audit_receipt_id": audit_id, **state["body"]}
        if set(response) != shape or response != expected: raise Reject("response-correlation")
        if type(response["returned_bytes"]) is not int or response["returned_bytes"] < 0 or type(response["truncated"]) is not bool: raise Reject("response-types")
        if request["operation"] == "memory.search":
            if type(response["returned_count"]) is not int or response["returned_count"] < 0 or type(response["results"]) is not list: raise Reject("response-count")
            event_ids, total = [], 0
            for result in response["results"]:
                if type(result) is not dict or set(result) != set(self.c["response_shapes"]["result_fields"]): raise Reject("result-shape")
                if type(result["result_ref"]) is not str or type(result["projection"]) is not str or type(result["returned_bytes"]) is not int or result["returned_bytes"] < 0: raise Reject("result-types")
                stored = self.refs.get(result["result_ref"])
                if stored is None or stored["session"] != session or result["returned_bytes"] != len(result["projection"].encode()) or result["projection"] != self._cut(stored["record"]["projection"], result["returned_bytes"])[0]: raise Reject("result-correlation")
                event_ids.append(stored["record"]["event_id"]); total += result["returned_bytes"]
            if response["returned_count"] != len(response["results"]) or event_ids != state["event_ids"] or total != response["returned_bytes"]: raise Reject("search-correlation")
            matches = [r for r in self.records if request["query"].casefold() in r["projection"].casefold()]
            if response["truncated"] != (len(matches) > len(response["results"]) or any(len(self.refs[r["result_ref"]]["record"]["projection"].encode()) > r["returned_bytes"] for r in response["results"])): raise Reject("search-truncation")
        else:
            if type(response["result_ref"]) is not str or response["result_ref"] != request["result_ref"]: raise Reject("response-ref")
            stored = self.refs.get(response["result_ref"]); field = "projection" if request["operation"] == "memory.get" else "selection_reason"
            if stored is None or stored["session"] != session or type(response[field]) is not str: raise Reject("response-result")
            source = stored["record"]["projection" if field == "projection" else "reason"]
            if state["event_ids"] != [stored["record"]["event_id"]] or response["returned_bytes"] != len(response[field].encode()) or response[field] != self._cut(source, response["returned_bytes"])[0] or response["truncated"] != (len(source.encode()) > response["returned_bytes"]): raise Reject("response-bytes")
        return True

    def search(self, session, request):
        session = self._validate_request(session, request)
        matches = [r for r in self.records if request["query"].casefold() in r["projection"].casefold()]
        results, event_ids, total, truncated = [], [], 0, len(matches) > request["limit"]
        known = self.session_events.setdefault(session["session_id"], set())
        for record in matches[:request["limit"]]:
            if record["event_id"] not in known and len(known) >= self.c["bounds"]["session_max_unique_results"]:
                truncated = True; break
            maximum = min(self.c["bounds"]["search_max_response_bytes"] - total, self._remaining(session))
            if maximum <= 0:
                truncated = True; break
            projection, size, cut = self._cut(record["projection"], maximum)
            ref = self._mint(session, record)
            results.append({"result_ref": ref, "projection": projection, "returned_bytes": size})
            event_ids.append(record["event_id"]); known.add(record["event_id"]); total += size; truncated |= cut
            if cut:
                break
        self.session_bytes[session["session_id"]] = self.session_bytes.get(session["session_id"], 0) + total
        return self._response(session, request, {"results": results, "returned_count": len(results), "returned_bytes": total, "truncated": truncated}, event_ids, total, truncated)

    def get(self, session, request):
        session = self._validate_request(session, request); record = self._resolve(session, request["result_ref"])
        projection, size, truncated = self._cut(record["projection"], min(self.c["bounds"]["get_max_response_bytes"], self._remaining(session)))
        self.session_bytes[session["session_id"]] = self.session_bytes.get(session["session_id"], 0) + size
        body = {"result_ref": request["result_ref"], "projection": projection, "returned_bytes": size, "truncated": truncated}
        return self._response(session, request, body, [record["event_id"]], size, truncated)

    def explain(self, session, request):
        session = self._validate_request(session, request); record = self._resolve(session, request["result_ref"])
        reason, size, truncated = self._cut(record["reason"], min(self.c["bounds"]["explain_max_response_bytes"], self._remaining(session)))
        self.session_bytes[session["session_id"]] = self.session_bytes.get(session["session_id"], 0) + size
        body = {"result_ref": request["result_ref"], "route_id": session["route_id"], "visibility": session["visibility"],
                "profile_revision": session["profile_revision"], "memory_revision": session["memory_revision"],
                "project_digest": session["project_digest"], "selection_reason": reason, "returned_bytes": size, "truncated": truncated}
        return self._response(session, request, body, [record["event_id"]], size, truncated)

    def validate_proposal(self, session, proposal):
        session = self._trusted_session(session); boundary = self.c["proposal_boundary"]
        expected = {"schema_version", "result", "review", "writes"} | set(boundary["required_server_bindings"])
        if set(proposal) != expected or proposal["schema_version"] != boundary["schema"]:
            raise Reject("proposal-shape")
        bindings = {"session_id_digest": self._session_digest(session), "route_id": session["route_id"],
                    "route_policy_digest": session["route_policy_digest"], "profile_revision": session["profile_revision"],
                    "memory_revision": session["memory_revision"], "project_digest": session["project_digest"]}
        if any(proposal[k] != v for k, v in bindings.items()):
            raise Reject("proposal-binding")
        if any(type(proposal[key]) is not str or not re.fullmatch(re.escape(self.c["digest_formats"][key]) + r":[0-9a-f]{64}", proposal[key]) for key in ("source_binding", "proposal_digest")):
            raise Reject("proposal-source")
        if proposal["result"] != boundary["result"] or proposal["review"] != boundary["review"] or proposal["writes"] != []:
            raise Reject("proposal-authority")
        return True


def make_session(server, route_id="route.codex.full-watari.v1", session_id="session.synthetic.1", project_mode="approved"):
    route = server.routes[route_id]
    session = {"schema_version": server.c["schemas"]["session"], "session_id": session_id,
               "runtime_id": f"runtime.{route['caller_runtime']}.synthetic", "adapter_version": "adapter.v1",
               **{key: copy.deepcopy(route[key]) for key in ROUTE_FIELDS}, "visibility": route["input_visibility"][0],
               "profile_revision": server.profile_revision, "memory_revision": server.memory_revision,
               "canonical_fingerprint": "watari-context-canonical-v1:" + "1" * 64,
               "effective_fingerprint": "watari-context-effective-v1:" + "2" * 64,
               "project_mode": project_mode, "project_digest": "watari-project-v1:" + "3" * 64,
               "project_root_scope_digest": "watari-project-root-v1:" + "4" * 64,
               "capability_digest": "watari-capability-v1:" + "5" * 64,
               "launch_attestation_digest": "watari-attestation-v1:" + "6" * 64,
               "issued_at": "2026-07-17T00:00:00Z", "expires_at": "2026-07-17T01:00:00Z", "support_status": "unsupported"}
    if project_mode == "none":
        session["project_digest"] = session["project_root_scope_digest"] = None
    return session


def registered_session(server, **kwargs):
    session = make_session(server, **kwargs); server.register_launch(session)
    return session


def search_request(contract, request_id, query="synthetic", limit=20):
    return {"schema_version": contract["schemas"]["request"], "request_id": request_id,
            "operation": "memory.search", "query": query, "limit": limit}


def ref_request(contract, request_id, operation, ref):
    return {"schema_version": contract["schemas"]["request"], "request_id": request_id,
            "operation": operation, "result_ref": ref}


class RetrievalContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract, cls.matrix, cls.runtime = json_block(DOC), json_block(ROUTES), json_block(RUNTIME)
        cls.canonical_event_id = json.loads(CANONICAL_VECTORS.read_text(encoding="utf-8"))["event_vectors"][0]["envelope"]["event_id"]

    def server(self, **kwargs):
        return SyntheticRetrievalServer(self.contract, self.matrix, **kwargs)

    def test_t_retrieval_reference_contract_and_closed_schema(self):
        top = {"schema_version", "unknown_policy", "operations", "failure_codes", "requirements_trace", "open_decisions"} | set(CLOSED)
        self.assertEqual(set(self.contract), top)
        for section, fields in CLOSED.items():
            self.assertEqual(set(self.contract[section]), fields, section)
        self.assertEqual((self.contract["schema_version"], self.contract["unknown_policy"], self.contract["operations"]), ("watari.retrieval-contract.v1", "fail-closed", OPS))
        self.assertEqual(self.contract["route_binding"]["identity_fields"], ROUTE_FIELDS)
        self.assertEqual(self.contract["route_binding"]["policy_digest"], self.matrix["route_policy_digest"])
        self.assertEqual(self.contract["route_binding"]["runtime_contract_schema"], self.runtime["schema_version"])
        self.assertEqual(self.contract["session_binding"]["server_fixed_fields"], SESSION_FIELDS)
        self.assertEqual(self.canonical_event_id, D003_CANONICAL_EVENT_ID)
        self.assertIn("| event identity | `event-id/v1` | `watari-event-v1:` |", DATA_CONTRACT.read_text(encoding="utf-8"))
        self.assertRegex(self.canonical_event_id, "^" + re.escape(D003_EVENT_NAMESPACE) + r"[0-9a-f]{64}$")
        self.assertEqual(self.contract["session_binding"]["replay"], "deny-request-id-reuse")
        self.assertIn("truncated", self.contract["response_shapes"]["explain_fields"])
        self.server()
        mutations = POLICY_COUNTEREXAMPLES + [("requirements_trace", None, [])]
        for section, key, value in mutations:
            changed = copy.deepcopy(self.contract)
            if key is None: changed[section] = value
            else: changed[section][key] = value
            with self.assertRaises(Reject): SyntheticRetrievalServer(changed, self.matrix)

    def test_t_retrieval_eligible_routes_and_typed_sessions(self):
        server = self.server()
        for route_id in ("route.codex.full-watari.v1", "route.pi.openai-codex.trusted-dream.v1"):
            session = make_session(server, route_id, f"session.{route_id}"); self.assertEqual(server.register_launch(session)["route_id"], route_id)
        server = self.server(); pi = registered_session(server, route_id="route.pi.openai-codex.trusted-dream.v1", session_id="session.pi.search")
        self.assertEqual(server.search(pi, search_request(self.contract, "request.pi", "synthetic", 19))["returned_count"], 2)
        with self.assertRaises(Reject):
            server.register_launch(make_session(server, "route.pi.openrouter.low-risk-utility.v1", "session.openrouter"))
        base = registered_session(server, session_id="session.bound")
        for key in SESSION_FIELDS:
            bad = copy.deepcopy(base); bad[key] = {} if isinstance(bad[key], dict) else "forged"
            with self.assertRaises(Reject): server.search(bad, search_request(self.contract, f"request.session.{key}", "ok", 1))
        bad = copy.deepcopy(base); bad["unknown"] = True
        with self.assertRaises(Reject): server.search(bad, search_request(self.contract, "request.session.unknown", "ok", 1))
        swapped = make_session(server, "route.pi.openai-codex.trusted-dream.v1", "session.bound")
        with self.assertRaises(Reject): server.search(swapped, search_request(self.contract, "request.route-swap", "ok", 1))

    def test_t_retrieval_search_shapes_types_replay_and_minting(self):
        server, session = self.server(), None
        session = registered_session(server)
        one = server.search(session, search_request(self.contract, "request.x", "x", 1))
        self.assertEqual((one["returned_count"], one["returned_bytes"], one["truncated"]), (1, 2048, False))
        two = server.search(session, search_request(self.contract, "request.synthetic", "synthetic", 19))
        self.assertEqual(two["returned_count"], 2); self.assertNotEqual(two["results"][0]["result_ref"], two["results"][1]["result_ref"])
        self.assertEqual(server.search(session, search_request(self.contract, "request.none", "not-found", 20))["returned_count"], 0)
        invalid = [("", 1), ("*", 1), ("match-all", 1), ("event.synthetic.2", 1), ("raw-event-id:event.synthetic.2", 1), (self.canonical_event_id, 1), (self.canonical_event_id.upper(), 1), ("raw-event-id:" + self.canonical_event_id, 1), ("find " + self.canonical_event_id, 1), ("id=" + self.canonical_event_id, 1), (self.canonical_event_id + " suffix", 1), ("a" * 4097, 1), ("ok", True), ("ok", 1.0), ("ok", 0), ("ok", 21)]
        for index, (query, limit) in enumerate(invalid):
            with self.assertRaises(Reject): server.search(session, search_request(self.contract, f"request.bad.{index}", query, limit))
        for key in ("event_id", "cursor", "offset", "visibility", "route_id"):
            request = search_request(self.contract, f"request.extra.{key}", "ok", 1); request[key] = "forged"
            with self.assertRaises(Reject): server.search(session, request)
        replay = search_request(self.contract, "request.replay", "ok", 1); server.search(session, replay)
        with self.assertRaises(Reject): server.search(session, replay)

    def test_t_retrieval_get_explain_same_session_refs_only(self):
        server, session = self.server(), None
        session = registered_session(server); found = server.search(session, search_request(self.contract, "request.search", "synthetic", 20))
        first, second = (result["result_ref"] for result in found["results"])
        self.assertRegex(first, r"^watari\.retrieval-result-ref\.v1:[0-9a-f]{64}$")
        got = server.get(session, ref_request(self.contract, "request.get", "memory.get", first))
        explained = server.explain(session, ref_request(self.contract, "request.explain", "memory.explain", first))
        self.assertEqual((got["result_ref"], explained["result_ref"]), (first, first)); self.assertIn("truncated", explained)
        for ref in ("watari.retrieval-result-ref.v1:" + "0" * 64, "watari.retrieval-result-ref.v1:4", "event.synthetic.2", [], {}):
            with self.assertRaises(Reject): server.get(session, ref_request(self.contract, f"request.ref.{ref}", "memory.get", ref))
        other = registered_session(server, session_id="session.other")
        with self.assertRaises(Reject): server.get(other, ref_request(self.contract, "request.cross", "memory.get", first))
        raw = ref_request(self.contract, "request.raw", "memory.get", first); raw["event_id"] = "event.synthetic.2"
        with self.assertRaises(Reject): server.get(session, raw)
        for key, value in (("result_ref", second), ("result_ref", "watari.retrieval-result-ref.v1:" + "0" * 64), ("projection", []), ("projection", {}), ("projection", "forged"), ("returned_bytes", -1), ("returned_bytes", True), ("returned_bytes", 1.0), ("truncated", 0)):
            bad = copy.deepcopy(got); bad[key] = value
            with self.assertRaises(Reject): server.validate_response(bad)
        network_text = "see https://example.com/x and ssh://host.example/x"
        network_server = self.server(records=[{"event_id": "event.network-url", "projection": network_text, "reason": network_text}]); network_session = registered_session(network_server, session_id="session.network-url")
        network_found = network_server.search(network_session, search_request(self.contract, "request.network.search", "https", 1)); network_ref = network_found["results"][0]["result_ref"]
        network_get = network_server.get(network_session, ref_request(self.contract, "request.network.get", "memory.get", network_ref))["projection"]
        network_explain = network_server.explain(network_session, ref_request(self.contract, "request.network.explain", "memory.explain", network_ref))["selection_reason"]
        for url in ("https://example.com/x", "ssh://host.example/x"): self.assertIn(url, network_get); self.assertIn(url, network_explain)
        punctuation_paths = tuple(f"x{delimiter}/home/binge/private/data.json" for delimiter in ",;)]}>|-_.@")
        paths = ("/home/binge/private/data.json", "//home/binge/private/data.json", "///home/binge/private/data.json", "source=/home/binge/private/data.json", "source=//home/binge/private/data.json", "source=///home/binge/private/data.json", "path:/home/binge/private/data.json", "file:/home/binge/private/data.json", "file:///home/binge/private/data.json", r"C:\Users\binge\private\data.json", r"\\server\share\private\data.json") + punctuation_paths
        for index, path in enumerate(paths):
            record = {"event_id": f"event.path.init.{index}", "projection": "safe", "reason": path}
            with self.assertRaises(Reject): self.server(records=[record])
            path_server = self.server(); path_session = registered_session(path_server, session_id=f"session.path.{index}")
            path_server.records[1]["projection"] = "leak " + path
            with self.assertRaises(Reject): path_server.search(path_session, search_request(self.contract, f"request.path.search.{index}", "leak", 1))
            found = path_server.search(path_session, search_request(self.contract, f"request.path.seed.{index}", "another", 1)); path_ref = found["results"][0]["result_ref"]
            path_server.refs[path_ref]["record"]["projection"] = path
            with self.assertRaises(Reject): path_server.get(path_session, ref_request(self.contract, f"request.path.get.{index}", "memory.get", path_ref))
            path_server.refs[path_ref]["record"]["projection"] = "safe"; path_server.refs[path_ref]["record"]["reason"] = path
            with self.assertRaises(Reject): path_server.explain(path_session, ref_request(self.contract, f"request.path.explain.{index}", "memory.explain", path_ref))

    def test_t_retrieval_operation_and_session_bounds_are_enforced(self):
        record = {"event_id": "event.large", "projection": "z" * 70000, "reason": "r" * 9000}
        server = self.server(records=[record]); session = registered_session(server)
        searched = server.search(session, search_request(self.contract, "request.large", "z", 20))
        ref = searched["results"][0]["result_ref"]
        got = server.get(session, ref_request(self.contract, "request.large.get", "memory.get", ref))
        explained = server.explain(session, ref_request(self.contract, "request.large.explain", "memory.explain", ref))
        self.assertEqual((searched["returned_bytes"], got["returned_bytes"], explained["returned_bytes"]), (65536, 32768, 8192))
        self.assertTrue(searched["truncated"] and got["truncated"] and explained["truncated"])
        for index in range(8):
            server.get(session, ref_request(self.contract, f"request.budget.{index}", "memory.get", ref))
        self.assertLessEqual(server.session_bytes[session["session_id"]], self.contract["bounds"]["session_max_response_bytes"])
        unique_server = self.server(records=[record]); unique_session = registered_session(unique_server, session_id="session.unique")
        unique_server.session_events[unique_session["session_id"]] = {f"event.{i}" for i in range(100)}
        blocked = unique_server.search(unique_session, search_request(self.contract, "request.unique-bound", "z", 20))
        self.assertEqual(blocked["returned_count"], 0); self.assertTrue(blocked["truncated"])

    def test_t_retrieval_project_none_approved_and_separation(self):
        server = self.server()
        self.assertEqual(server.register_launch(make_session(server, session_id="session.none", project_mode="none"))["route_id"], "route.codex.full-watari.v1")
        self.assertEqual(server.register_launch(make_session(server, session_id="session.approved", project_mode="approved"))["route_id"], "route.codex.full-watari.v1")
        for mode, digest, root in (("none", "forged", None), ("approved", None, None), ("changed", "d", "r")):
            session = make_session(server); session.update(project_mode=mode, project_digest=digest, project_root_scope_digest=root)
            with self.assertRaises(Reject): server.register_launch(session)
        session = make_session(server); session["project_digest"] = "/host/private"
        with self.assertRaises(Reject): server.register_launch(session)

    def test_t_retrieval_candidate_proposal_is_exact_review_only(self):
        server, session = self.server(), None
        session = registered_session(server, session_id="/host/private/session.proposal")
        proposal = {"schema_version": self.contract["proposal_boundary"]["schema"],
                    "session_id_digest": server._session_digest(session), "route_id": session["route_id"],
                    "route_policy_digest": session["route_policy_digest"], "profile_revision": session["profile_revision"],
                    "memory_revision": session["memory_revision"], "project_digest": session["project_digest"],
                    "source_binding": "watari.memory-source-binding.v1:" + "7" * 64,
                    "proposal_digest": "watari.memory-candidate-proposal-digest.v1:" + "8" * 64,
                    "result": "immutable-candidate-only", "review": "required-before-canonical-event", "writes": []}
        self.assertTrue(server.validate_proposal(session, proposal))
        self.assertRegex(proposal["session_id_digest"], r"^watari\.retrieval-session-id-digest\.v1:[0-9a-f]{64}$")
        self.assertNotIn(session["session_id"], json.dumps(proposal))
        for key, value in (("source_binding", None), ("source_binding", "/host/private"), ("source_binding", "source.synthetic.1"), ("proposal_digest", "/host/private"), ("proposal_digest", "proposal.synthetic.1"), ("route_id", "forged"), ("review", "skip"), ("writes", ["canonical-event"]), ("canonical_write", True)):
            bad = copy.deepcopy(proposal); bad[key] = value
            with self.assertRaises(Reject): server.validate_proposal(session, bad)

    def test_t_retrieval_audit_correlation_content_and_qualification(self):
        server, session = self.server(), None
        session = registered_session(server, session_id="/host/private/session.audit"); response = server.search(session, search_request(self.contract, "request.audit", "x", 1))
        receipt = server.audits[response["audit_receipt_id"]]; event_ids = receipt["returned_event_ids"]
        self.assertTrue(server.validate_audit(receipt))
        self.assertRegex(receipt["session_id_digest"], r"^watari\.retrieval-session-id-digest\.v1:[0-9a-f]{64}$")
        self.assertNotIn(session["session_id"], json.dumps(receipt))
        self.assertNotIn(event_ids[0], json.dumps(response)); self.assertEqual(self.contract["audit_receipt"]["event_ids"], "local-audit-only")
        for value in (-1, True, 1.0):
            bad = copy.deepcopy(response); bad["returned_count"] = value
            with self.assertRaises(Reject): server.validate_response(bad)
        for key, value in (("returned_count", -1), ("returned_count", True), ("returned_bytes", 2048.0), ("truncated", 0), ("returned_event_ids", ["forged"]), ("request_id", "forged"), ("operation", "memory.get"), ("query", "secret")):
            bad = copy.deepcopy(receipt); bad[key] = value
            with self.assertRaises(Reject): server.validate_audit(bad)
        self.assertEqual(self.contract["qualification"], {"structural_status": "unqualified", "real_runtime_default": "unsupported", "supported_requires": ["observed-runtime-evidence", "qualified-sandbox-evidence"], "structural_tests_do_not_qualify": True})
        self.assertEqual(self.contract["open_decisions"], ["DEC-OPEN-003", "DEC-OPEN-004"])


if __name__ == "__main__":
    unittest.main()
