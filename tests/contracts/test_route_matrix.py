import copy
import hashlib
import importlib.util
import json
import re
import struct
import unittest
from pathlib import Path


ADR = Path(__file__).parents[2] / "docs" / "adr" / "005-data-routes.md"
THREAT_MODEL = Path(__file__).parents[2] / "docs" / "threat-model.md"

EXPECTED_ROUTE_IDS = {
    "route.codex.full-watari.v1",
    "route.pi.openai-codex.trusted-dream.v1",
    "route.pi.openrouter.low-risk-utility.v1",
    "route.session-receipt.claude.v1",
    "route.session-receipt.codex.v1",
    "route.session-receipt.pi-high-trust.v1",
    "route.connector.read-only.v1",
}
RECEIPT_ROUTE_IDS = {
    "route.session-receipt.claude.v1",
    "route.session-receipt.codex.v1",
    "route.session-receipt.pi-high-trust.v1",
}
EXPECTED_ORIGINS = {
    "route.session-receipt.claude.v1": ["route.session-receipt.claude.v1"],
    "route.session-receipt.codex.v1": ["route.codex.full-watari.v1"],
    "route.session-receipt.pi-high-trust.v1": [
        "route.pi.openai-codex.trusted-dream.v1"
    ],
}
SEMANTIC_ROLES = {"user", "assistant", "tool", "system"}
SOURCES = {
    "local-user-turn",
    "local-assistant-turn",
    "provider-output",
    "local-tool-turn",
    "local-system-turn",
}
ROLE_SOURCE_PAIRS = {
    ("user", "local-user-turn"),
    ("assistant", "local-assistant-turn"),
    ("assistant", "provider-output"),
    ("tool", "local-tool-turn"),
    ("system", "local-system-turn"),
}
LOCAL_ROLE_SOURCE = {
    "user": "local-user-turn",
    "assistant": "local-assistant-turn",
    "tool": "local-tool-turn",
    "system": "local-system-turn",
}
VISIBILITIES = {"local-only", "trusted-model", "low-risk-model"}
CAPABILITY_KEYS = {
    "mount",
    "retrieval",
    "shell",
    "file",
    "project",
    "external_write",
    "process",
    "network",
}
MUTATION_KEYS = {
    "canonical_write",
    "profile_write",
    "checkpoint_write",
    "connector_write",
    "external_write",
    "credential_write",
    "project_layer_write",
}
RECEIPT_KEYS = {
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
    "primary_evidence",
}
RECEIPT_VECTOR_KEYS = {
    "observed_turn_id",
    "observed_capture_route_id",
    "observed_origin_route_id",
    "observed_bytes_hex",
    "observed_role",
    "observed_source",
    "observed_session_lineage",
    "observed_launch_attestation",
    "receipt",
}
PROVIDER_OUTPUT_CASE_IDS = {
    "case.receipt.provider-output.codex.accept-nonprimary.v1",
    "case.receipt.provider-output.pi.accept-nonprimary.v1",
    "case.receipt.provider-output.claude.deny.v1",
}
PROVIDER_OUTPUT_VECTOR_KEYS = RECEIPT_VECTOR_KEYS | {
    "case_id",
    "expected_error_codes",
}
EGRESS_CASE_IDS = {
    "case.egress.structural-arbitrary.codex.v1",
    "case.egress.structural-arbitrary.pi-openai-codex-trusted-dream.v1",
    "case.egress.structural-arbitrary.pi-openrouter-low-risk-utility.v1",
    "case.egress.structural-arbitrary.connector-read-only.v1",
}
EGRESS_RECEIPT_KEYS = {
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
    "verification_status",
}
EGRESS_VECTOR_KEYS = {
    "case_id",
    "observed_egress_id",
    "observed_route_id",
    "observed_provider_id",
    "observed_model_id",
    "observed_endpoint_id",
    "observed_bytes_hex",
    "observed_context_manifest",
    "observed_route_policy_digest",
    "observed_launch_attestation",
    "observed_capability_evidence",
    "receipt",
    "expected_error_codes",
}
EGRESS_CONTEXT_MANIFEST_KEYS = {
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

ROUTE_TOKEN = re.compile(r"^watari-route-policy-v1:[0-9a-f]{64}$")
CONTEXT_TOKEN = re.compile(r"^watari-context-effective-v1:[0-9a-f]{64}$")
WIRE_TOKEN = re.compile(r"^watari-wire-bytes-v1:[0-9a-f]{64}$")
LINEAGE_TOKEN = re.compile(r"^watari-lineage-v1:[0-9a-f]{64}$")
ATTESTATION_TOKEN = re.compile(r"^watari-attestation-v1:[0-9a-f]{64}$")
ORIGIN_TOKEN = re.compile(r"^watari-origin-v1:[0-9a-f]{64}$")
CONNECTOR_TOKEN = re.compile(r"^watari-connector-v1:[0-9a-f]{64}$")
SOURCE_POLICY_TOKEN = re.compile(r"^watari-source-policy-v1:[0-9a-f]{64}$")
EGRESS_LAUNCH_TOKEN = re.compile(r"^watari-egress-launch-v1:[0-9a-f]{64}$")
CAPABILITY_EVIDENCE_TOKEN = re.compile(
    r"^watari-capability-evidence-v1:[0-9a-f]{64}$"
)

TRACE = {
    "route.codex.full-watari.v1": {"MX-001", "RQ-002", "RQ-004", "AC-002"},
    "route.pi.openai-codex.trusted-dream.v1": {
        "MX-002",
        "RQ-004",
        "RQ-006",
        "AC-006",
    },
    "route.pi.openrouter.low-risk-utility.v1": {
        "MX-003",
        "RQ-004",
        "RQ-009",
        "NM-004",
        "AC-009",
    },
    "route.session-receipt.claude.v1": {
        "MX-004",
        "RQ-002",
        "RQ-004",
        "AC-002",
        "AC-004",
    },
    "route.session-receipt.codex.v1": {
        "MX-004",
        "RQ-002",
        "RQ-004",
        "AC-002",
        "AC-004",
    },
    "route.session-receipt.pi-high-trust.v1": {
        "MX-004",
        "RQ-002",
        "RQ-004",
        "AC-002",
        "AC-004",
    },
    "route.connector.read-only.v1": {"MX-005", "RQ-005", "AC-005"},
}
TRACE_FULL = {
    route_id: values | {"SB-001", "SB-003", "SB-004"}
    for route_id, values in TRACE.items()
}
EXACT = {
    "route.codex.full-watari.v1": (
        "provider.openai.codex-cli.v1",
        "model.codex.full-watari.v1",
        "endpoint.codex.approved.v1",
        "runtime.codex-dedicated",
        "trusted-model",
        ["profile.explicit", "memory.trusted-projection", "user.turn", "source.verified-projection"],
    ),
    "route.pi.openai-codex.trusted-dream.v1": (
        "provider.openai.api.v1",
        "model.openai-codex.trusted-dream.v1",
        "endpoint.openai.exact.v1",
        "runtime.pi-openai-codex-dedicated",
        "trusted-model",
        ["user.turn", "source.verified-projection", "memory.dream-candidate"],
    ),
    "route.pi.openrouter.low-risk-utility.v1": (
        "provider.openrouter.api.v1",
        "model.openrouter.low-risk-utility.v1",
        "endpoint.openrouter.exact.v1",
        "runtime.openrouter-dedicated",
        "low-risk-model",
        ["user.turn", "utility.task.minimal"],
    ),
    "route.session-receipt.claude.v1": (
        "provider.local-session.v1",
        "model.none.v1",
        "endpoint.local-only.v1",
        "none",
        "local-only",
        ["session.receipt"],
    ),
    "route.session-receipt.codex.v1": (
        "provider.local-session.v1",
        "model.none.v1",
        "endpoint.local-only.v1",
        "none",
        "local-only",
        ["session.receipt"],
    ),
    "route.session-receipt.pi-high-trust.v1": (
        "provider.local-session.v1",
        "model.none.v1",
        "endpoint.local-only.v1",
        "none",
        "local-only",
        ["session.receipt"],
    ),
    "route.connector.read-only.v1": (
        "provider.connector.v1",
        "model.none.v1",
        "endpoint.connector-read-only.v1",
        "connector-instance-scoped",
        "local-only",
        ["connector.approved-projection"],
    ),
}

POLICY_EXCLUDED_PATHS = (
    ("route_policy_digest",),
    ("routes", "*", "route_policy_digest"),
    ("test_vectors",),
    ("routes", "*", "connector_contract", "contract_digest"),
)
POLICY_EXCLUDED_PATH_STRINGS = [
    "route_policy_digest",
    "routes[*].route_policy_digest",
    "test_vectors",
    "routes[*].connector_contract.contract_digest",
]
EXPECTED_EXCLUSION_MATCH_COUNTS = {
    ("route_policy_digest",): 1,
    ("routes", "*", "route_policy_digest"): 7,
    ("test_vectors",): 1,
    ("routes", "*", "connector_contract", "contract_digest"): 7,
}

EXPECTED_POLICY_DIGEST = (
    "watari-route-policy-v1:"
    "98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4"
)
EXPECTED_ROUTE_VECTORS = {
    "route.codex.full-watari.v1": (
        "7761746172692d776972652d73616d706c652d76313a726f7574652e636f6465782e66756c6c2d7761746172692e76310a",
        "watari-context-effective-v1:d6a8a09abe4b7ea1ada2115ea67cf46d0b69eeffc7e1cd48c2f16fbbf8356ad2",
        "watari-wire-bytes-v1:2d09d8d1a72e2840a0ae5acd9c957057a37783a404c631f0b8f33117d0e6b686",
        "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1",
    ),
    "route.pi.openai-codex.trusted-dream.v1": (
        "7761746172692d776972652d73616d706c652d76313a726f7574652e70692e6f70656e61692d636f6465782e747275737465642d647265616d2e76310a",
        "watari-context-effective-v1:cf55e31221003f077631cb68dd90667eb37fb55bd17ae46647e97d336476df4e",
        "watari-wire-bytes-v1:fffc52d9651394ab7f2641724f0b7f7e8a8b3d2e981dcba4ae307be141a6cade",
        "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1",
    ),
    "route.pi.openrouter.low-risk-utility.v1": (
        "7761746172692d776972652d73616d706c652d76313a726f7574652e70692e6f70656e726f757465722e6c6f772d7269736b2d7574696c6974792e76310a",
        "watari-context-effective-v1:bbf21f626672a78a34eb0c16d91479d082d11e142ca386d2829e18d9810b13db",
        "watari-wire-bytes-v1:af87aa8b8146e9e54599928ed27f6e5054b698b995d62536b4b867d90c886f4e",
        "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1",
    ),
    "route.session-receipt.claude.v1": (
        "7761746172692d776972652d73616d706c652d76313a726f7574652e73657373696f6e2d726563656970742e636c617564652e76310a",
        "watari-context-effective-v1:6af03080a6a4c6a08d5e4140a642db338f47db2b6b592d01d0b8f75b1f6e8347",
        "watari-wire-bytes-v1:966920edc9320531ad765bc8cc9715f82c2b26576a71359b56b426ae59c05fda",
        "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1",
    ),
    "route.session-receipt.codex.v1": (
        "7761746172692d776972652d73616d706c652d76313a726f7574652e73657373696f6e2d726563656970742e636f6465782e76310a",
        "watari-context-effective-v1:a51de229cfc44d2e3bc45358045e7d768335d22ea07f23d8a825693ce0a1fbe9",
        "watari-wire-bytes-v1:4978c3f6467eda12dc85685311ffd3244350d380e13993c65b932b29b3026291",
        "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1",
    ),
    "route.session-receipt.pi-high-trust.v1": (
        "7761746172692d776972652d73616d706c652d76313a726f7574652e73657373696f6e2d726563656970742e70692d686967682d74727573742e76310a",
        "watari-context-effective-v1:6f1b3a873289c89427bc63be9ca83b667b860635bea928d518b53517991516de",
        "watari-wire-bytes-v1:e7f3a7c55ca953ca580baba635eb99345b2a842df0a77bba69d7189befa48bc8",
        "watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1",
    ),
    "route.connector.read-only.v1": (
        "7761746172692d776972652d73616d706c652d76313a726f7574652e636f6e6e6563746f722e726561642d6f6e6c792e76310a",
        "watari-context-effective-v1:6d938796c84325cc8fee17e32605409498861915f9b4298333f1602950e36f1a",
        "watari-wire-bytes-v1:9d89e1aeaa1680d4d9c2123b250890ccd6da01db6322e16cb13a4d55b6dbe745",
        "watari-connector-v1:42d2ce3be9a548e586b0c38de0ff9293125ea1100dffbdd07260f6a3f74d592c",
    ),
}
EXPECTED_RECEIPT_VECTOR_DIGESTS = {
    ("route.session-receipt.claude.v1", "user"):
        "watari-receipt-vector-v1:c86967f08cc2e53a622d32fd22a539f8b2d118f4c46ccb5352835236021ad157",
    ("route.session-receipt.claude.v1", "assistant"):
        "watari-receipt-vector-v1:241572cbc0966c77b2a144a54c3a189e4f6e0053ed13af772d8728969b506e3d",
    ("route.session-receipt.claude.v1", "tool"):
        "watari-receipt-vector-v1:3c6baa52f02f30abac0eb5232b3d0e5763e2f71fbe79ff8275420e6b126ba338",
    ("route.session-receipt.claude.v1", "system"):
        "watari-receipt-vector-v1:563d406d4934425d79f4ef0df9d99e72abcaba2ad9c66fd9a2e05f95f8778690",
    ("route.session-receipt.codex.v1", "user"):
        "watari-receipt-vector-v1:d29bf8fef898ac4332f7d2e3a4eb0be1bbb2ecb627331355b9a22400a56482ef",
    ("route.session-receipt.codex.v1", "assistant"):
        "watari-receipt-vector-v1:34f9802e4b55d261fc3a3f7d85adf1219a15c0964ddb08e8850a192260f8cbaa",
    ("route.session-receipt.codex.v1", "tool"):
        "watari-receipt-vector-v1:9cc60e018d8a67f96d64f340c13deadf45c0ec8ee57091696a5a99faf4b7af90",
    ("route.session-receipt.codex.v1", "system"):
        "watari-receipt-vector-v1:c502798d87d22f49731e65c52d2a57e429f8dbc0f9b915c4bb3b4e9e72d6b1aa",
    ("route.session-receipt.pi-high-trust.v1", "user"):
        "watari-receipt-vector-v1:cf061fdefa07ae2122f4f288e58d77db70e0c2217c32dd32803760e7cb8793cf",
    ("route.session-receipt.pi-high-trust.v1", "assistant"):
        "watari-receipt-vector-v1:8b63b91d2158ee435d514ead33af1db273f4a51c02213b24e20ceb246d09b368",
    ("route.session-receipt.pi-high-trust.v1", "tool"):
        "watari-receipt-vector-v1:37e3b90b116b1bd89526b1217b43b810e931791d92b830894dc2d1f346a84c49",
    ("route.session-receipt.pi-high-trust.v1", "system"):
        "watari-receipt-vector-v1:2125b2fb0f4afc518c0f1f4a419160583ce23d3169de9e30105f71917d888341",
}
EXPECTED_PROVIDER_OUTPUT_VECTOR_DIGESTS = {
    "case.receipt.provider-output.codex.accept-nonprimary.v1":
        "watari-provider-output-vector-v1:61774840c06c63b0a351f3d24514016f19cc90d43348ed23231b9145fd7ce82c",
    "case.receipt.provider-output.pi.accept-nonprimary.v1":
        "watari-provider-output-vector-v1:d91082702600d565288dd3d6dce1db54b22fe2e9ebdbb4bd26b421e8c11e2889",
    "case.receipt.provider-output.claude.deny.v1":
        "watari-provider-output-vector-v1:409a34cb28fa868a44cc18a172c5e885bd172187751e2ddd6169cd443781fb1a",
}
EXPECTED_EGRESS_VECTOR_DIGESTS = {
    "case.egress.structural-arbitrary.codex.v1":
        "watari-egress-vector-v1:6772ba4246dc4946fc217db714b6dc4d674e42cb4396471658f68316c6dbc95d",
    "case.egress.structural-arbitrary.pi-openai-codex-trusted-dream.v1":
        "watari-egress-vector-v1:8cc5aca4ec8a33a72e0b9b0c1e6caac839e62a7f55cfb33eb70db948f55ee559",
    "case.egress.structural-arbitrary.pi-openrouter-low-risk-utility.v1":
        "watari-egress-vector-v1:df623f44eed76a21870173c6460e993f93f36273104971452f3b0b2535dae3d7",
    "case.egress.structural-arbitrary.connector-read-only.v1":
        "watari-egress-vector-v1:d1963a771fa8083d573d227af1beb53bfb9909815d2b38c56c71444820c196e4",
}


def d003_module():
    path = Path(__file__).parents[2] / "tests" / "unit" / "test_canonical_vectors.py"
    spec = importlib.util.spec_from_file_location("d003_canonical_vectors", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _path_matches(path, pattern):
    return len(path) == len(pattern) and all(
        actual == expected or (expected == "*" and isinstance(actual, int))
        for actual, expected in zip(path, pattern)
    )


def policy_projection(matrix):
    """Project policy with a code-owned exact exclusion set."""
    def clean(value, path=()):
        if isinstance(value, dict):
            output = {}
            for key, child in value.items():
                child_path = path + (key,)
                if any(
                    _path_matches(child_path, pattern)
                    for pattern in POLICY_EXCLUDED_PATHS
                ):
                    continue
                output[key] = clean(child, child_path)
            return output
        if isinstance(value, list):
            return [
                clean(child, path + (index,))
                for index, child in enumerate(value)
            ]
        return value

    return clean(matrix)


def policy_exclusion_match_counts(matrix):
    counts = {pattern: 0 for pattern in POLICY_EXCLUDED_PATHS}

    def walk(value, path=()):
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = path + (key,)
                matched = [
                    pattern
                    for pattern in POLICY_EXCLUDED_PATHS
                    if _path_matches(child_path, pattern)
                ]
                if matched:
                    if len(matched) != 1:
                        raise AssertionError(f"ambiguous exclusion at {child_path}")
                    counts[matched[0]] += 1
                    continue
                walk(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, path + (index,))

    walk(matrix)
    return counts


def route_policy_digest(matrix, d003):
    payload = d003.canonical_bytes(policy_projection(matrix))
    frame = (
        b"WATARI\x00route-policy/v1\x00"
        + struct.pack(">Q", len(payload))
        + payload
    )
    return "watari-route-policy-v1:" + hashlib.sha256(frame).hexdigest()


def typed_digest(prefix, domain, payload, d003):
    raw = payload if isinstance(payload, bytes) else d003.canonical_bytes(payload)
    frame = (
        b"WATARI\x00"
        + domain.encode("ascii")
        + b"\x00"
        + struct.pack(">Q", len(raw))
        + raw
    )
    return prefix + hashlib.sha256(frame).hexdigest()


def synthetic_context_manifest(matrix, route):
    return {
        "schema_version": 1,
        "context_schema": "watari.context/v1",
        "projection_kind": "effective",
        "policy_revision": matrix["route_policy_revision"],
        "profile_revision": "profile.v1",
        "memory_revision": "memory.v1",
        "project_revision": "project.v1",
        "visibility": route["input_visibility"][0],
        "route_policy_digest": matrix["route_policy_digest"],
    }


def context_fingerprint_for_observation(
    observed_context_manifest, observed_bytes, d003
):
    return d003.context_fingerprint(
        "effective", observed_context_manifest, observed_bytes
    )


def egress_receipt_errors(
    receipt,
    *,
    trusted_matrix,
    observed_egress_id,
    observed_route_id,
    observed_provider_id,
    observed_model_id,
    observed_endpoint_id,
    observed_bytes,
    observed_context_manifest,
    observed_route_policy_digest,
    observed_launch_attestation,
    observed_capability_evidence,
    d003,
):
    """Verify structural binding only; authenticity is outside D005."""
    errors = set()
    try:
        if type(receipt) is not dict:
            return {"egress_receipt.type"}
        missing = EGRESS_RECEIPT_KEYS - set(receipt)
        unknown = set(receipt) - EGRESS_RECEIPT_KEYS
        errors |= {"egress_receipt.missing:" + key for key in missing}
        errors |= {"egress_receipt.unknown:" + key for key in unknown}
        if missing or unknown:
            return errors

        for field in EGRESS_RECEIPT_KEYS:
            if not _nonempty_exact_string(receipt[field]):
                errors.add("egress_receipt.type:" + field)
        observed_strings = {
            "observed_egress_id": observed_egress_id,
            "observed_route_id": observed_route_id,
            "observed_provider_id": observed_provider_id,
            "observed_model_id": observed_model_id,
            "observed_endpoint_id": observed_endpoint_id,
            "observed_route_policy_digest": observed_route_policy_digest,
            "observed_launch_attestation": observed_launch_attestation,
            "observed_capability_evidence": observed_capability_evidence,
        }
        for name, value in observed_strings.items():
            if not _nonempty_exact_string(value):
                errors.add("egress_observation.type:" + name)
        if type(observed_bytes) is not bytes or not observed_bytes:
            errors.add("egress_observation.type:observed_bytes")
        if type(observed_context_manifest) is not dict:
            errors.add("egress_observation.type:observed_context_manifest")
        else:
            errors |= {
                "egress_context_manifest.missing:" + key
                for key in EGRESS_CONTEXT_MANIFEST_KEYS
                - set(observed_context_manifest)
            }
            errors |= {
                "egress_context_manifest.unknown:" + key
                for key in set(observed_context_manifest)
                - EGRESS_CONTEXT_MANIFEST_KEYS
            }
        if errors:
            return errors

        routes_value = trusted_matrix.get("routes")
        if type(routes_value) is not list:
            return {"trusted_matrix.routes"}
        routes = {
            route.get("route_id"): route
            for route in routes_value
            if type(route) is dict
        }
        if len(routes) != len(routes_value):
            return {"trusted_matrix.route"}
        route = routes.get(observed_route_id)
        if route is None:
            return {"egress_route.unknown"}

        policy_digest = trusted_matrix.get("route_policy_digest")
        if policy_digest != EXPECTED_POLICY_DIGEST:
            errors.add("trusted_matrix.unapproved_policy_digest")
        if route_policy_digest(trusted_matrix, d003) != policy_digest:
            errors.add("trusted_matrix.policy_digest_mismatch")
        if route.get("route_policy_digest") != policy_digest:
            errors.add("egress_route.policy_digest")
        if observed_route_policy_digest != policy_digest:
            errors.add("observed_route_policy_digest")
        if route.get("direction", {}).get("egress", {}).get("enabled") is not True:
            errors.add("egress_route.disabled")

        for field, observed in (
            ("provider_id", observed_provider_id),
            ("model_id", observed_model_id),
            ("endpoint_id", observed_endpoint_id),
        ):
            if route.get(field) != observed:
                errors.add("observed_" + field)

        comparisons = {
            "egress_id": observed_egress_id,
            "route_id": observed_route_id,
            "provider_id": observed_provider_id,
            "model_id": observed_model_id,
            "endpoint_id": observed_endpoint_id,
            "route_policy_digest": observed_route_policy_digest,
        }
        for field, observed in comparisons.items():
            if receipt[field] != observed:
                errors.add("egress_receipt." + field)
        if receipt["schema_version"] != "watari.egress-receipt.v1":
            errors.add("egress_receipt.schema_version")
        if receipt["verification_status"] != "structural-binding-only":
            errors.add("egress_receipt.verification_status")

        expected_bytes_digest = typed_digest(
            "watari-wire-bytes-v1:", "wire-bytes/v1", observed_bytes, d003
        )
        if receipt["bytes_digest"] != expected_bytes_digest:
            errors.add("egress_receipt.bytes_digest")

        try:
            validated_context_manifest = d003.validate_context_manifest(
                "effective", observed_context_manifest
            )
        except Exception:
            errors.add("egress_context_manifest.invalid")
            validated_context_manifest = None
        if validated_context_manifest is not None:
            if (
                validated_context_manifest["policy_revision"]
                != trusted_matrix.get("route_policy_revision")
            ):
                errors.add("egress_context_manifest.policy_revision")
            if (
                validated_context_manifest["route_policy_digest"]
                != policy_digest
            ):
                errors.add("egress_context_manifest.route_policy_digest")
            if (
                validated_context_manifest["visibility"]
                not in route.get("input_visibility", [])
            ):
                errors.add("egress_context_manifest.visibility")
            expected_context = context_fingerprint_for_observation(
                validated_context_manifest, observed_bytes, d003
            )
        else:
            expected_context = None
        if receipt["context_fingerprint"] != expected_context:
            errors.add("egress_receipt.context_fingerprint")

        expected_launch = typed_digest(
            "watari-egress-launch-v1:",
            "egress-launch/v1",
            {
                "route_id": observed_route_id,
                "provider_id": observed_provider_id,
                "model_id": observed_model_id,
                "endpoint_id": observed_endpoint_id,
                "route_policy_digest": observed_route_policy_digest,
                "attestation": observed_launch_attestation,
            },
            d003,
        )
        if receipt["launch_attestation_digest"] != expected_launch:
            errors.add("egress_receipt.launch_attestation_digest")

        expected_capability = typed_digest(
            "watari-capability-evidence-v1:",
            "capability-evidence/v1",
            {
                "route_id": observed_route_id,
                "caller_runtime": route.get("caller_runtime"),
                "route_policy_digest": observed_route_policy_digest,
                "evidence": observed_capability_evidence,
            },
            d003,
        )
        if receipt["capability_evidence_digest"] != expected_capability:
            errors.add("egress_receipt.capability_evidence_digest")

        for field, pattern in (
            ("bytes_digest", WIRE_TOKEN),
            ("context_fingerprint", CONTEXT_TOKEN),
            ("route_policy_digest", ROUTE_TOKEN),
            ("launch_attestation_digest", EGRESS_LAUNCH_TOKEN),
            ("capability_evidence_digest", CAPABILITY_EVIDENCE_TOKEN),
        ):
            if not pattern.fullmatch(receipt[field]):
                errors.add("egress_receipt.token:" + field)
    except Exception as error:
        errors.add("egress_verifier.exception:" + type(error).__name__)
    return errors


def assert_exact_keys(test, value, expected, label):
    if type(value) is not dict:
        test.fail(f"{label}: expected exact object, got {type(value).__name__}")
    test.assertEqual(set(value), set(expected), label)


def assert_exact_list(test, value, label):
    if type(value) is not list:
        test.fail(f"{label}: expected list, got {type(value).__name__}")


def load_matrix():
    text = ADR.read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)\n```", text, re.DOTALL)
    if len(blocks) != 1:
        raise AssertionError(
            f"T-ROUTE-MATRIX requires exactly one JSON block, got {len(blocks)}"
        )

    def reject_duplicate(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON member")
            result[key] = value
        return result

    return json.loads(blocks[0], object_pairs_hook=reject_duplicate)


def _nonempty_exact_string(value):
    return type(value) is str and bool(value)


def turn_receipt_errors(
    receipt,
    *,
    trusted_matrix,
    observed_turn_id,
    observed_capture_route_id,
    observed_origin_route_id,
    observed_bytes,
    observed_role,
    observed_source,
    observed_session_lineage,
    observed_launch_attestation,
    d003,
):
    """Verify a receipt against independent observations and trusted routes."""
    errors = set()
    try:
        if type(receipt) is not dict:
            return {"receipt.type"}
        missing = RECEIPT_KEYS - set(receipt)
        unknown = set(receipt) - RECEIPT_KEYS
        errors |= {"receipt.missing:" + key for key in missing}
        errors |= {"receipt.unknown:" + key for key in unknown}
        if missing or unknown:
            return errors

        string_fields = RECEIPT_KEYS - {"primary_evidence"}
        for field in string_fields:
            if not _nonempty_exact_string(receipt[field]):
                errors.add("receipt.type:" + field)
        if type(receipt["primary_evidence"]) is not bool:
            errors.add("receipt.type:primary_evidence")

        observed_strings = {
            "observed_turn_id": observed_turn_id,
            "observed_capture_route_id": observed_capture_route_id,
            "observed_origin_route_id": observed_origin_route_id,
            "observed_role": observed_role,
            "observed_source": observed_source,
            "observed_session_lineage": observed_session_lineage,
            "observed_launch_attestation": observed_launch_attestation,
        }
        for name, value in observed_strings.items():
            if not _nonempty_exact_string(value):
                errors.add("observation.type:" + name)
        if type(observed_bytes) is not bytes or not observed_bytes:
            errors.add("observation.type:observed_bytes")
        if errors:
            return errors

        if receipt["schema_version"] != "watari.turn-receipt.v1":
            errors.add("schema_version")
        if observed_role not in SEMANTIC_ROLES:
            errors.add("semantic_role")
        if observed_source not in SOURCES:
            errors.add("source")
        if (observed_role, observed_source) not in ROLE_SOURCE_PAIRS:
            errors.add("role_source_pair")

        routes_value = trusted_matrix.get("routes")
        if type(routes_value) is not list:
            return errors | {"trusted_matrix.routes"}
        routes = {}
        for route in routes_value:
            if type(route) is not dict or not _nonempty_exact_string(route.get("route_id")):
                return errors | {"trusted_matrix.route"}
            if route["route_id"] in routes:
                return errors | {"trusted_matrix.duplicate_route"}
            routes[route["route_id"]] = route

        capture = routes.get(observed_capture_route_id)
        origin = routes.get(observed_origin_route_id)
        if capture is None:
            errors.add("capture_route.unknown")
        if origin is None:
            errors.add("origin_route.unknown")
        if capture is None or origin is None:
            return errors

        policy_digest = trusted_matrix.get("route_policy_digest")
        if not _nonempty_exact_string(policy_digest):
            return errors | {"trusted_matrix.policy_digest"}
        if policy_digest != EXPECTED_POLICY_DIGEST:
            errors.add("trusted_matrix.unapproved_policy_digest")
        if route_policy_digest(trusted_matrix, d003) != policy_digest:
            errors.add("trusted_matrix.policy_digest_mismatch")
        if capture.get("route_policy_digest") != policy_digest:
            errors.add("capture_route.policy_digest")
        if origin.get("route_policy_digest") != policy_digest:
            errors.add("origin_route.policy_digest")

        receipt_policy = capture.get("session_receipt")
        ingress = capture.get("direction", {}).get("ingress")
        origin_policy = capture.get("origin_policy")
        if type(receipt_policy) is not dict or receipt_policy.get("required") is not True:
            errors.add("capture_route.receipt_not_required")
        if type(ingress) is not dict or observed_role not in ingress.get("accepted_roles", []):
            errors.add("capture_route.role_not_accepted")
        if (
            type(origin_policy) is not dict
            or observed_origin_route_id
            not in origin_policy.get("allowed_origin_route_ids", [])
        ):
            errors.add("capture_route.origin_not_allowed")
        if (
            observed_source == "provider-output"
            and origin_policy.get("provider_output_policy")
            != "allow-unverified-context"
        ):
            errors.add("capture_route.provider_output_denied")

        if receipt["turn_id"] != observed_turn_id:
            errors.add("turn_id")
        if receipt["route_id"] != observed_capture_route_id:
            errors.add("route_id")
        if receipt["origin_route_id"] != observed_origin_route_id:
            errors.add("origin_route_id")
        if receipt["role"] != observed_role:
            errors.add("role")
        if receipt["source"] != observed_source:
            errors.add("source_binding")

        expected_primary = (
            observed_role == "user" and observed_source == "local-user-turn"
        )
        if receipt["primary_evidence"] != expected_primary:
            errors.add("primary_evidence")
        if observed_source == "provider-output" and receipt["primary_evidence"]:
            errors.add("provider_output_primary")

        expected_bytes = typed_digest(
            "watari-wire-bytes-v1:", "wire-bytes/v1", observed_bytes, d003
        )
        if receipt["bytes_digest"] != expected_bytes:
            errors.add("bytes_digest")
        expected_lineage = typed_digest(
            "watari-lineage-v1:",
            "session-lineage/v1",
            {
                "capture_route_id": observed_capture_route_id,
                "lineage": observed_session_lineage,
            },
            d003,
        )
        if receipt["session_lineage_digest"] != expected_lineage:
            errors.add("session_lineage_digest")

        origin_runtime = origin.get("caller_runtime")
        provider_id = origin.get("provider_id")
        model_id = origin.get("model_id")
        for name, value in (
            ("origin_runtime", origin_runtime),
            ("provider_id", provider_id),
            ("model_id", model_id),
        ):
            if not _nonempty_exact_string(value):
                errors.add("trusted_origin.type:" + name)
        if any(error.startswith("trusted_origin.type:") for error in errors):
            return errors

        expected_attestation = typed_digest(
            "watari-attestation-v1:",
            "watari-attestation/v1",
            {
                "capture_route_id": observed_capture_route_id,
                "origin_route_id": observed_origin_route_id,
                "origin_caller_runtime": origin_runtime,
                "route_policy_digest": policy_digest,
                "attestation": observed_launch_attestation,
            },
            d003,
        )
        if receipt["watari_launch_attestation_digest"] != expected_attestation:
            errors.add("watari_launch_attestation_digest")

        expected_origin = typed_digest(
            "watari-origin-v1:",
            "origin-route/v1",
            {
                "origin_route_id": observed_origin_route_id,
                "provider_id": provider_id,
                "model_id": model_id,
                "route_policy_digest": policy_digest,
            },
            d003,
        )
        if (
            receipt["origin_route_provider_model_policy_digest"]
            != expected_origin
        ):
            errors.add("origin_route_provider_model_policy_digest")

        for field, pattern in (
            ("bytes_digest", WIRE_TOKEN),
            ("session_lineage_digest", LINEAGE_TOKEN),
            ("watari_launch_attestation_digest", ATTESTATION_TOKEN),
            ("origin_route_provider_model_policy_digest", ORIGIN_TOKEN),
        ):
            if not pattern.fullmatch(receipt[field]):
                errors.add("receipt.token:" + field)
    except Exception as error:
        errors.add("verifier.exception:" + type(error).__name__)
    return errors


def observation_kwargs(vector, matrix, d003):
    return {
        "trusted_matrix": matrix,
        "observed_turn_id": vector["observed_turn_id"],
        "observed_capture_route_id": vector["observed_capture_route_id"],
        "observed_origin_route_id": vector["observed_origin_route_id"],
        "observed_bytes": bytes.fromhex(vector["observed_bytes_hex"]),
        "observed_role": vector["observed_role"],
        "observed_source": vector["observed_source"],
        "observed_session_lineage": vector["observed_session_lineage"],
        "observed_launch_attestation": vector["observed_launch_attestation"],
        "d003": d003,
    }


def egress_observation_kwargs(vector, matrix, d003):
    return {
        "trusted_matrix": matrix,
        "observed_egress_id": vector["observed_egress_id"],
        "observed_route_id": vector["observed_route_id"],
        "observed_provider_id": vector["observed_provider_id"],
        "observed_model_id": vector["observed_model_id"],
        "observed_endpoint_id": vector["observed_endpoint_id"],
        "observed_bytes": bytes.fromhex(vector["observed_bytes_hex"]),
        "observed_context_manifest": vector["observed_context_manifest"],
        "observed_route_policy_digest": vector[
            "observed_route_policy_digest"
        ],
        "observed_launch_attestation": vector[
            "observed_launch_attestation"
        ],
        "observed_capability_evidence": vector[
            "observed_capability_evidence"
        ],
        "d003": d003,
    }


def receipt_from_observation(
    matrix,
    *,
    turn_id,
    capture_route_id,
    origin_route_id,
    observed_bytes,
    role,
    source,
    lineage,
    attestation,
    d003,
):
    """Construct synthetic evidence without taking provider/model input."""
    routes = {route["route_id"]: route for route in matrix["routes"]}
    origin = routes[origin_route_id]
    policy = matrix["route_policy_digest"]
    return {
        "schema_version": "watari.turn-receipt.v1",
        "turn_id": turn_id,
        "route_id": capture_route_id,
        "origin_route_id": origin_route_id,
        "bytes_digest": typed_digest(
            "watari-wire-bytes-v1:", "wire-bytes/v1", observed_bytes, d003
        ),
        "role": role,
        "source": source,
        "session_lineage_digest": typed_digest(
            "watari-lineage-v1:",
            "session-lineage/v1",
            {"capture_route_id": capture_route_id, "lineage": lineage},
            d003,
        ),
        "watari_launch_attestation_digest": typed_digest(
            "watari-attestation-v1:",
            "watari-attestation/v1",
            {
                "capture_route_id": capture_route_id,
                "origin_route_id": origin_route_id,
                "origin_caller_runtime": origin["caller_runtime"],
                "route_policy_digest": policy,
                "attestation": attestation,
            },
            d003,
        ),
        "origin_route_provider_model_policy_digest": typed_digest(
            "watari-origin-v1:",
            "origin-route/v1",
            {
                "origin_route_id": origin_route_id,
                "provider_id": origin["provider_id"],
                "model_id": origin["model_id"],
                "route_policy_digest": policy,
            },
            d003,
        ),
        "primary_evidence": role == "user" and source == "local-user-turn",
    }


class RouteMatrixTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = load_matrix()
        cls.d003 = d003_module()
        cls.routes = {
            route["route_id"]: route for route in cls.matrix["routes"]
        }

    def _validate_closed(self, matrix):
        top_keys = {
            "schema_version",
            "visibility_values",
            "unknown_policy",
            "provider_output_default_trust",
            "route_policy_revision",
            "route_policy_digest",
            "capability_values",
            "fallback_values",
            "retention_zdr_values",
            "context_selection",
            "mutation_policy",
            "projection_policy",
            "connector_instance_policy",
            "routes",
            "session_receipt_schema",
            "egress_receipt_schema",
            "test_vectors",
        }
        assert_exact_keys(self, matrix, top_keys, "top schema")
        self.assertEqual(matrix["schema_version"], "watari.route-matrix.v1")
        self.assertEqual(matrix["visibility_values"], [
            "local-only",
            "trusted-model",
            "low-risk-model",
        ])
        self.assertEqual(matrix["unknown_policy"], "fail-closed")
        self.assertEqual(
            matrix["provider_output_default_trust"], "unverified-context"
        )
        self.assertEqual(matrix["route_policy_revision"], "D003.route-policy.v1")
        self.assertEqual(matrix["fallback_values"], ["disabled"])
        self.assertRegex(matrix["route_policy_digest"], ROUTE_TOKEN)
        self.assertEqual(
            route_policy_digest(matrix, self.d003),
            matrix["route_policy_digest"],
        )
        self.assertEqual(matrix["route_policy_digest"], EXPECTED_POLICY_DIGEST)

        assert_exact_keys(
            self,
            matrix["context_selection"],
            {
                "selection_key",
                "multi_match",
                "implicit_default",
                "approved_project_layer",
                "changed_project_layer",
            },
            "context selection",
        )
        self.assertEqual(
            matrix["context_selection"],
            {
                "selection_key": "route_id",
                "multi_match": "reject",
                "implicit_default": "deny",
                "approved_project_layer": "required-digest-root-scope",
                "changed_project_layer": "reapproval-required",
            },
        )
        self.assertEqual(set(matrix["mutation_policy"]), MUTATION_KEYS)
        self.assertTrue(
            all(value == "deny" for value in matrix["mutation_policy"].values())
        )
        assert_exact_keys(
            self,
            matrix["projection_policy"],
            {
                "wire_bytes",
                "source_visibility_required",
                "sent_visibility_required",
                "declassification",
                "visibility_elevation",
                "policy_digest_excluded_paths",
            },
            "projection policy",
        )
        self.assertEqual(
            matrix["projection_policy"],
            {
                "wire_bytes": "exact-allowlisted-projection",
                "source_visibility_required": True,
                "sent_visibility_required": True,
                "declassification": "forbidden",
                "visibility_elevation": "reject",
                "policy_digest_excluded_paths": POLICY_EXCLUDED_PATH_STRINGS,
            },
        )
        assert_exact_keys(
            self,
            matrix["connector_instance_policy"],
            {"identifier_class", "forbidden_fields", "source_policy_digest"},
            "connector instance policy",
        )
        self.assertEqual(
            matrix["connector_instance_policy"]["identifier_class"],
            "opaque-non-PII",
        )

        schema = matrix["session_receipt_schema"]
        assert_exact_keys(
            self,
            schema,
            {
                "schema_version",
                "turn_schema",
                "required_fields",
                "role_values",
                "source_values",
                "allowed_role_source_pairs",
                "primary_evidence_rule",
                "provider_ingress_user",
                "launch_attestation_semantics",
                "authenticity_dependencies",
            },
            "session receipt schema",
        )
        self.assertEqual(schema["schema_version"], "watari.session-receipt.v1")
        self.assertEqual(schema["turn_schema"], "watari.turn-receipt.v1")
        self.assertEqual(schema["required_fields"], [
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
            "primary_evidence",
        ])
        self.assertEqual(set(schema["required_fields"]), RECEIPT_KEYS)
        self.assertEqual(schema["role_values"], [
            "user",
            "assistant",
            "tool",
            "system",
        ])
        self.assertEqual(set(schema["role_values"]), SEMANTIC_ROLES)
        self.assertEqual(schema["source_values"], [
            "local-user-turn",
            "local-assistant-turn",
            "provider-output",
            "local-tool-turn",
            "local-system-turn",
        ])
        self.assertEqual(schema["allowed_role_source_pairs"], [
            {"role": "user", "source": "local-user-turn"},
            {"role": "assistant", "source": "local-assistant-turn"},
            {"role": "assistant", "source": "provider-output"},
            {"role": "tool", "source": "local-tool-turn"},
            {"role": "system", "source": "local-system-turn"},
        ])
        self.assertEqual(
            {
                (pair["role"], pair["source"])
                for pair in schema["allowed_role_source_pairs"]
            },
            ROLE_SOURCE_PAIRS,
        )
        for pair in schema["allowed_role_source_pairs"]:
            assert_exact_keys(self, pair, {"role", "source"}, "role/source pair")
        self.assertEqual(
            schema["primary_evidence_rule"],
            "capture-receipt-user-local-user-turn-only",
        )
        self.assertEqual(schema["provider_ingress_user"], "deny")
        self.assertEqual(
            schema["launch_attestation_semantics"],
            "opaque-nonempty-hash-bound-structural-only",
        )
        self.assertEqual(
            schema["authenticity_dependencies"], ["D006", "D007", "Z001"]
        )

        egress_schema = matrix["egress_receipt_schema"]
        assert_exact_keys(
            self,
            egress_schema,
            {
                "schema_version",
                "receipt_schema",
                "required_fields",
                "structural_verification",
                "observed_egress_produced_by_D005",
                "authenticity_dependencies",
                "runtime_source_qualification_dependencies",
                "launch_attestation_semantics",
            },
            "egress receipt schema",
        )
        self.assertEqual(
            egress_schema,
            {
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
                    "verification_status",
                ],
                "structural_verification": "D005-only",
                "observed_egress_produced_by_D005": False,
                "authenticity_dependencies": ["D006", "C004", "Z001"],
                "runtime_source_qualification_dependencies": [
                    "D006",
                    "D007",
                ],
                "launch_attestation_semantics": "opaque-nonempty-hash-bound",
            },
        )
        self.assertEqual(
            set(egress_schema["required_fields"]), EGRESS_RECEIPT_KEYS
        )

        assert_exact_list(self, matrix["routes"], "routes")
        for route in matrix["routes"]:
            if type(route) is not dict or not _nonempty_exact_string(
                route.get("route_id")
            ):
                self.fail("route must be an object with nonempty route_id")
        route_ids = [route["route_id"] for route in matrix["routes"]]
        self.assertEqual(set(route_ids), EXPECTED_ROUTE_IDS)
        self.assertEqual(len(route_ids), len(set(route_ids)))
        routes = {route["route_id"]: route for route in matrix["routes"]}

        vector_root = matrix["test_vectors"]
        assert_exact_keys(
            self,
            vector_root,
            {
                "routes",
                "receipts",
                "provider_output_receipts",
                "egress_receipts",
            },
            "test vectors",
        )
        assert_exact_keys(
            self,
            vector_root["routes"],
            EXPECTED_ROUTE_IDS,
            "route vector set",
        )
        assert_exact_keys(
            self,
            vector_root["receipts"],
            RECEIPT_ROUTE_IDS,
            "receipt vector route set",
        )
        assert_exact_keys(
            self,
            vector_root["provider_output_receipts"],
            PROVIDER_OUTPUT_CASE_IDS,
            "provider-output case set",
        )
        assert_exact_keys(
            self,
            vector_root["egress_receipts"],
            EGRESS_CASE_IDS,
            "egress case set",
        )
        for route_id, vector in vector_root["routes"].items():
            assert_exact_keys(
                self,
                vector,
                {
                    "sample_bytes_hex",
                    "golden_fingerprint",
                    "wire_bytes_digest",
                    "connector_digest",
                },
                route_id + " route vector",
            )
            expected = EXPECTED_ROUTE_VECTORS[route_id]
            self.assertEqual(
                (
                    vector["sample_bytes_hex"],
                    vector["golden_fingerprint"],
                    vector["wire_bytes_digest"],
                    vector["connector_digest"],
                ),
                expected,
                route_id,
            )

        for capture_id, role_vectors in vector_root["receipts"].items():
            assert_exact_keys(
                self, role_vectors, SEMANTIC_ROLES, capture_id + " role vectors"
            )
            for role, vector in role_vectors.items():
                assert_exact_keys(
                    self,
                    vector,
                    RECEIPT_VECTOR_KEYS,
                    capture_id + ":" + role,
                )
                assert_exact_keys(
                    self,
                    vector["receipt"],
                    RECEIPT_KEYS,
                    capture_id + ":" + role + " receipt",
                )
                self.assertEqual(vector["observed_capture_route_id"], capture_id)
                self.assertEqual(
                    vector["observed_origin_route_id"],
                    EXPECTED_ORIGINS[capture_id][0],
                )
                self.assertEqual(vector["observed_role"], role)
                self.assertEqual(
                    vector["observed_source"], LOCAL_ROLE_SOURCE[role]
                )
                vector_digest = typed_digest(
                    "watari-receipt-vector-v1:",
                    "receipt-vector/v1",
                    vector,
                    self.d003,
                )
                self.assertEqual(
                    vector_digest,
                    EXPECTED_RECEIPT_VECTOR_DIGESTS[(capture_id, role)],
                    capture_id + ":" + role,
                )
                self.assertEqual(
                    turn_receipt_errors(
                        vector["receipt"],
                        **observation_kwargs(vector, matrix, self.d003),
                    ),
                    set(),
                    capture_id + ":" + role,
                )

        for case_id, vector in vector_root[
            "provider_output_receipts"
        ].items():
            assert_exact_keys(
                self, vector, PROVIDER_OUTPUT_VECTOR_KEYS, case_id
            )
            assert_exact_keys(
                self, vector["receipt"], RECEIPT_KEYS, case_id + " receipt"
            )
            self.assertEqual(vector["case_id"], case_id)
            self.assertEqual(vector["observed_role"], "assistant")
            self.assertEqual(vector["observed_source"], "provider-output")
            self.assertFalse(vector["receipt"]["primary_evidence"])
            self.assertEqual(
                typed_digest(
                    "watari-provider-output-vector-v1:",
                    "provider-output-receipt-vector/v1",
                    vector,
                    self.d003,
                ),
                EXPECTED_PROVIDER_OUTPUT_VECTOR_DIGESTS[case_id],
            )
            self.assertEqual(
                turn_receipt_errors(
                    vector["receipt"],
                    **observation_kwargs(vector, matrix, self.d003),
                ),
                set(vector["expected_error_codes"]),
                case_id,
            )

        for case_id, vector in vector_root["egress_receipts"].items():
            assert_exact_keys(self, vector, EGRESS_VECTOR_KEYS, case_id)
            assert_exact_keys(
                self,
                vector["receipt"],
                EGRESS_RECEIPT_KEYS,
                case_id + " receipt",
            )
            self.assertEqual(vector["case_id"], case_id)
            self.assertEqual(
                typed_digest(
                    "watari-egress-vector-v1:",
                    "egress-receipt-vector/v1",
                    vector,
                    self.d003,
                ),
                EXPECTED_EGRESS_VECTOR_DIGESTS[case_id],
            )
            self.assertEqual(
                egress_receipt_errors(
                    vector["receipt"],
                    **egress_observation_kwargs(vector, matrix, self.d003),
                ),
                set(vector["expected_error_codes"]),
                case_id,
            )
        route_keys = {
            "route_id",
            "caller_runtime",
            "provider_model_class",
            "provider_id",
            "model_id",
            "endpoint_id",
            "input_visibility",
            "allowed_projection",
            "forbidden_data",
            "network_endpoint_class",
            "credential_reference_class",
            "credential_scope",
            "fallback_policy",
            "retention_zdr",
            "output_trust",
            "canonical_write",
            "dream",
            "sandbox_class",
            "route_policy_revision",
            "route_policy_digest",
            "capability_set",
            "project_layer_policy",
            "wire_projection",
            "direction",
            "session_receipt",
            "connector_contract",
            "origin_policy",
            "fail_closed_conditions",
            "d001_trace",
        }
        for route_id, route in routes.items():
            assert_exact_keys(self, route, route_keys, route_id)
            provider, model, endpoint, scope, visibility, projection = EXACT[route_id]
            self.assertEqual(
                (
                    route["provider_id"],
                    route["model_id"],
                    route["endpoint_id"],
                    route["credential_scope"],
                    route["input_visibility"][0],
                    route["allowed_projection"],
                ),
                (provider, model, endpoint, scope, visibility, projection),
                route_id,
            )
            for field in (
                "route_id",
                "caller_runtime",
                "provider_model_class",
                "provider_id",
                "model_id",
                "endpoint_id",
                "credential_scope",
                "sandbox_class",
            ):
                self.assertTrue(_nonempty_exact_string(route[field]), field)
            self.assertEqual(
                route["route_policy_revision"],
                matrix["route_policy_revision"],
            )
            self.assertEqual(
                route["route_policy_digest"], matrix["route_policy_digest"]
            )
            route_vector = matrix["test_vectors"]["routes"][route_id]
            self.assertRegex(route_vector["golden_fingerprint"], CONTEXT_TOKEN)
            self.assertRegex(route_vector["wire_bytes_digest"], WIRE_TOKEN)
            self.assertEqual(
                route_vector["connector_digest"],
                route["connector_contract"]["contract_digest"],
            )
            self.assertEqual(route["fallback_policy"], "disabled")
            self.assertEqual(
                route["sandbox_class"],
                "mandatory-external-runtime-no-state-key-mount",
            )
            self.assertFalse(route["canonical_write"])
            self.assertNotIn("allow:any", json.dumps(route))
            for condition in (
                "unknown-route",
                "capability-mismatch",
                "fallback-not-allowlisted",
            ):
                self.assertIn(condition, route["fail_closed_conditions"])

            assert_exact_keys(
                self,
                route["retention_zdr"],
                {"retention_class", "zero_data_retention", "fallback_retention"},
                route_id,
            )
            assert_exact_keys(
                self, route["capability_set"], CAPABILITY_KEYS, route_id
            )
            self.assertEqual(route["capability_set"]["external_write"], "deny")
            assert_exact_keys(
                self,
                route["project_layer_policy"],
                {
                    "approved_digest_required",
                    "root_scope_required",
                    "auto_discovery",
                    "model_override",
                },
                route_id,
            )
            self.assertTrue(
                route["project_layer_policy"]["approved_digest_required"]
            )
            self.assertTrue(route["project_layer_policy"]["root_scope_required"])
            self.assertEqual(
                route["project_layer_policy"]["auto_discovery"], "deny"
            )
            self.assertEqual(
                route["project_layer_policy"]["model_override"], "deny"
            )

            wire = route["wire_projection"]
            assert_exact_keys(
                self,
                wire,
                {
                    "source_visibility",
                    "sent_visibility",
                    "allowed_projection",
                    "byte_selection",
                    "declassification",
                },
                route_id + " wire",
            )
            self.assertEqual(wire["source_visibility"], route["input_visibility"])
            self.assertEqual(wire["sent_visibility"], route["input_visibility"])
            self.assertEqual(
                wire["allowed_projection"], route["allowed_projection"]
            )
            self.assertEqual(
                wire["byte_selection"], "exact-allowlisted-projection"
            )
            self.assertEqual(wire["declassification"], "forbidden")
            self.assertFalse(
                {
                    "sent_bytes_digest",
                    "sample_bytes_hex",
                    "sample_bytes_digest",
                }
                & set(wire)
            )
            exact_bytes = bytes.fromhex(route_vector["sample_bytes_hex"])
            expected_wire = typed_digest(
                "watari-wire-bytes-v1:",
                "wire-bytes/v1",
                exact_bytes,
                self.d003,
            )
            self.assertEqual(route_vector["wire_bytes_digest"], expected_wire)
            self.assertNotEqual(
                route_vector["wire_bytes_digest"],
                route_vector["golden_fingerprint"],
            )

            direction = route["direction"]
            assert_exact_keys(self, direction, {"egress", "ingress"}, route_id)
            assert_exact_keys(
                self,
                direction["egress"],
                {
                    "enabled",
                    "endpoint_id",
                    "allowed_visibility",
                    "fallback_policy",
                    "capture",
                },
                route_id + " egress",
            )
            assert_exact_keys(
                self,
                direction["ingress"],
                {
                    "enabled",
                    "accepted_output_trust",
                    "accepted_roles",
                    "provider_output_as_primary_evidence",
                    "canonical_write",
                },
                route_id + " ingress",
            )
            self.assertEqual(
                direction["egress"]["endpoint_id"], route["endpoint_id"]
            )
            self.assertEqual(
                direction["egress"]["allowed_visibility"],
                route["input_visibility"],
            )
            self.assertFalse(
                direction["ingress"]["provider_output_as_primary_evidence"]
            )
            self.assertEqual(
                direction["ingress"]["canonical_write"], "deny"
            )

            receipt = route["session_receipt"]
            assert_exact_keys(
                self,
                receipt,
                {
                    "required",
                    "session_lineage",
                    "watari_launch_attestation",
                    "origin_route_model_policy",
                    "role_provenance",
                    "primary_evidence_roles",
                    "provider_output_status",
                    "schema_version",
                    "turn_schema",
                    "source_binding",
                    "role_capture",
                    "source_capture",
                },
                route_id + " receipt policy",
            )
            is_receipt = route_id in RECEIPT_ROUTE_IDS
            self.assertEqual(receipt["required"], is_receipt)
            self.assertEqual(
                direction["egress"]["enabled"], not is_receipt
            )
            self.assertEqual(
                direction["ingress"]["accepted_roles"],
                ["user", "assistant", "tool", "system"]
                if is_receipt
                else ["evidence"],
            )
            self.assertEqual(
                receipt["session_lineage"],
                "required" if is_receipt else "not-applicable",
            )
            self.assertEqual(
                receipt["watari_launch_attestation"],
                "required" if is_receipt else "not-applicable",
            )
            self.assertEqual(
                receipt["role_provenance"],
                ["user", "assistant", "tool", "system"] if is_receipt else [],
            )
            self.assertEqual(receipt["primary_evidence_roles"], ["user"])
            self.assertEqual(
                receipt["provider_output_status"], "unverified-context"
            )
            self.assertEqual(receipt["source_binding"], "required")
            self.assertEqual(
                receipt["role_capture"],
                "not-applicable"
                if route_id == "route.connector.read-only.v1"
                else "observed-role",
            )
            self.assertEqual(
                receipt["source_capture"],
                "not-applicable"
                if route_id == "route.connector.read-only.v1"
                else "observed-source",
            )

            connector = route["connector_contract"]
            connector_keys = {
                "required",
                "connector_instance_id_policy",
                "connector_instance_id",
                "source_policy",
                "allowed_method_paths",
                "forbidden_method_paths",
                "credential_scope",
                "contract_digest",
                "read_only",
            }
            if route_id == "route.connector.read-only.v1":
                connector_keys |= {
                    "source_policy_digest",
                    "checkpoint_lineage_binding",
                }
            assert_exact_keys(
                self, connector, connector_keys, route_id + " connector"
            )
            connector_body = {
                key: value
                for key, value in connector.items()
                if key != "contract_digest"
            }
            self.assertEqual(
                connector["contract_digest"],
                typed_digest(
                    "watari-connector-v1:",
                    "connector-contract/v1",
                    connector_body,
                    self.d003,
                ),
            )
            self.assertRegex(connector["contract_digest"], CONNECTOR_TOKEN)
            is_connector = route_id == "route.connector.read-only.v1"
            self.assertEqual(
                connector["allowed_method_paths"],
                ["GET /approved-scope/**"] if is_connector else [],
            )
            self.assertEqual(
                connector["source_policy"],
                "enabled-read-only" if is_connector else "not-applicable",
            )
            self.assertEqual(
                connector["credential_scope"],
                route["credential_scope"] if is_connector else "not-applicable",
            )
            self.assertTrue(connector["read_only"])

            origin_policy = route["origin_policy"]
            assert_exact_keys(
                self,
                origin_policy,
                {
                    "primary_evidence_roles",
                    "provider_output_primary_evidence",
                    "source_binding",
                    "allowed_origin_route_ids",
                    "provider_output_policy",
                },
                route_id + " origin policy",
            )
            self.assertFalse(
                origin_policy["provider_output_primary_evidence"]
            )
            self.assertEqual(origin_policy["source_binding"], "required")
            self.assertEqual(
                origin_policy["primary_evidence_roles"],
                ["user"]
                if route_id in RECEIPT_ROUTE_IDS
                or "trusted-dream" in route_id
                else ["evidence"],
            )
            self.assertEqual(
                origin_policy["allowed_origin_route_ids"],
                EXPECTED_ORIGINS.get(route_id, []),
            )
            self.assertEqual(
                origin_policy["provider_output_policy"],
                (
                    "deny-until-allowlisted-model-origin"
                    if route_id == "route.session-receipt.claude.v1"
                    else "allow-unverified-context"
                    if route_id in {
                        "route.session-receipt.codex.v1",
                        "route.session-receipt.pi-high-trust.v1",
                    }
                    else "not-applicable"
                ),
            )
            self.assertEqual(set(route["d001_trace"]), TRACE_FULL[route_id])
            self.assertEqual(
                len(route["d001_trace"]), len(TRACE_FULL[route_id]), route_id
            )

    def _assert_rejected(self, candidate):
        with self.assertRaises(AssertionError):
            self._validate_closed(candidate)

    def test_t_route_matrix_real_d003_vectors_and_closed_schema(self):
        self._validate_closed(self.matrix)
        for route in self.matrix["routes"]:
            vector = self.matrix["test_vectors"]["routes"][route["route_id"]]
            context = bytes.fromhex(vector["sample_bytes_hex"])
            self.assertEqual(
                context_fingerprint_for_observation(
                    synthetic_context_manifest(self.matrix, route),
                    context,
                    self.d003,
                ),
                vector["golden_fingerprint"],
            )

    def test_t_route_matrix_rejects_mutation_and_fallbacks(self):
        self.assertEqual(set(self.matrix["mutation_policy"]), MUTATION_KEYS)
        self.assertTrue(
            all(value == "deny" for value in self.matrix["mutation_policy"].values())
        )
        for route in self.routes.values():
            self.assertFalse(route["canonical_write"])
            self.assertEqual(route["fallback_policy"], "disabled")
            self.assertEqual(
                route["direction"]["ingress"]["canonical_write"], "deny"
            )
            self.assertEqual(route["capability_set"]["external_write"], "deny")

    def test_t_route_matrix_visibility_and_openrouter_capabilities(self):
        for route in self.routes.values():
            self.assertTrue(set(route["input_visibility"]) <= VISIBILITIES)
            self.assertEqual(
                route["wire_projection"]["source_visibility"],
                route["input_visibility"],
            )
            self.assertEqual(
                route["wire_projection"]["sent_visibility"],
                route["input_visibility"],
            )
        route = self.routes["route.pi.openrouter.low-risk-utility.v1"]
        self.assertEqual(set(route["capability_set"]), CAPABILITY_KEYS)
        for key in ("mount", "retrieval", "shell", "file", "project", "external_write"):
            self.assertEqual(route["capability_set"][key], "deny")
        self.assertEqual(
            route["capability_set"]["process"], "allow:bounded-child-process"
        )
        self.assertEqual(
            route["capability_set"]["network"], "allow:exact-provider-endpoint"
        )
        for forbidden in (
            "private.memory",
            "raw.connector.data",
            "credential.value",
            "canonical.event",
        ):
            self.assertIn(forbidden, route["forbidden_data"])
        self.assertFalse(route["dream"])
        self.assertIn("not-model-input", route["credential_reference_class"])

    def test_t_documented_structural_boundary_size_and_execution_dependency(self):
        adr_text = ADR.read_text(encoding="utf-8")
        threat_text = THREAT_MODEL.read_text(encoding="utf-8")
        for required in (
            "D005 produces no observed egress",
            "structural-binding-only",
            "opaque, nonempty, and hash-bound only",
            "D006",
            "D007",
            "C004",
            "Z001",
            "## Reviewed size exception and rationale",
            "## Execution dependency note",
            "D003 canonical framing",
            "`T-ROUTE-MATRIX`",
            "does not self-authorize a frozen-DAG expansion",
        ):
            self.assertIn(required, adr_text, required)
        for required in (
            "D005 produces no observed egress",
            "structural-binding-only",
            "opaque, nonempty, and",
            "hash-bound only",
        ):
            self.assertIn(required, threat_text, required)
        for forbidden in (
            "actual origin route",
            "qualified receipt route",
            "qualified Claude model",
            "deny-until-qualified-model-route",
        ):
            self.assertNotIn(forbidden, adr_text + threat_text, forbidden)

    def test_t_connector_is_static_d008_requirement_not_fake_evidence(self):
        connector = self.routes[
            "route.connector.read-only.v1"
        ]["connector_contract"]
        self.assertTrue(connector["required"])
        self.assertTrue(connector["read_only"])
        self.assertEqual(connector["source_policy"], "enabled-read-only")
        self.assertRegex(
            connector["source_policy_digest"], SOURCE_POLICY_TOKEN
        )
        self.assertEqual(
            connector["source_policy_digest"],
            typed_digest(
                "watari-source-policy-v1:",
                "source-policy/v1",
                {
                    "route_id": "route.connector.read-only.v1",
                    "source_policy": connector["source_policy"],
                    "allowed_method_paths": connector["allowed_method_paths"],
                    "credential_scope": connector["credential_scope"],
                },
                self.d003,
            ),
        )
        self.assertEqual(
            connector["allowed_method_paths"], ["GET /approved-scope/**"]
        )
        self.assertEqual(
            connector["forbidden_method_paths"],
            ["POST /", "PUT /", "PATCH /", "DELETE /"],
        )
        self.assertEqual(
            connector["credential_scope"], "connector-instance-scoped"
        )
        self.assertEqual(
            connector["connector_instance_id_policy"], "opaque-non-PII"
        )
        self.assertNotRegex(
            connector["connector_instance_id"], r"[/@\\]|\.\."
        )
        self.assertTrue(
            all(
                not path.startswith(("POST", "PUT", "PATCH", "DELETE"))
                for path in connector["allowed_method_paths"]
            )
        )
        self.assertEqual(
            connector["checkpoint_lineage_binding"],
            "required-at-D008-evidence-boundary",
        )
        self.assertNotIn("checkpoint_lineage_digest", connector)
        self.assertNotIn(
            "watari-checkpoint-v1:",
            json.dumps(self.matrix),
        )

    def test_t_receipt_vectors_are_literal_closed_and_all_validate(self):
        seen = set()
        for capture_id, role_vectors in self.matrix["test_vectors"]["receipts"].items():
            for role, vector in role_vectors.items():
                seen.add((capture_id, role))
                self.assertEqual(
                    typed_digest(
                        "watari-receipt-vector-v1:",
                        "receipt-vector/v1",
                        vector,
                        self.d003,
                    ),
                    EXPECTED_RECEIPT_VECTOR_DIGESTS[(capture_id, role)],
                )
                self.assertEqual(
                    turn_receipt_errors(
                        vector["receipt"],
                        **observation_kwargs(vector, self.matrix, self.d003),
                    ),
                    set(),
                )
        self.assertEqual(seen, set(EXPECTED_RECEIPT_VECTOR_DIGESTS))
        self.assertEqual(len(seen), 12)

    def test_t_egress_receipt_arbitrary_bytes_is_structural_only(self):
        vectors = self.matrix["test_vectors"]["egress_receipts"]
        fixture_bytes = {
            bytes.fromhex(route_vector["sample_bytes_hex"])
            for route_vector in self.matrix["test_vectors"]["routes"].values()
        }
        seen_routes = set()
        for case_id, vector in vectors.items():
            seen_routes.add(vector["observed_route_id"])
            observed_bytes = bytes.fromhex(vector["observed_bytes_hex"])
            self.assertNotIn(observed_bytes, fixture_bytes)
            self.assertEqual(
                typed_digest(
                    "watari-egress-vector-v1:",
                    "egress-receipt-vector/v1",
                    vector,
                    self.d003,
                ),
                EXPECTED_EGRESS_VECTOR_DIGESTS[case_id],
            )
            self.assertEqual(
                egress_receipt_errors(
                    vector["receipt"],
                    **egress_observation_kwargs(
                        vector, self.matrix, self.d003
                    ),
                ),
                set(),
            )
            self.assertEqual(
                vector["receipt"]["verification_status"],
                "structural-binding-only",
            )
        enabled_routes = {
            route["route_id"]
            for route in self.matrix["routes"]
            if route["direction"]["egress"]["enabled"]
        }
        self.assertEqual(seen_routes, enabled_routes)
        self.assertEqual(
            set(vectors), set(EXPECTED_EGRESS_VECTOR_DIGESTS)
        )
        self.assertFalse(
            self.matrix["egress_receipt_schema"][
                "observed_egress_produced_by_D005"
            ]
        )

    def test_t_egress_receipt_rejects_independent_observation_mutations(self):
        vector = self.matrix["test_vectors"]["egress_receipts"][
            "case.egress.structural-arbitrary.codex.v1"
        ]
        fixed_receipt = vector["receipt"]
        base = egress_observation_kwargs(vector, self.matrix, self.d003)
        mutations = (
            ("observed_egress_id", "egress:nonempty-alternative"),
            ("observed_route_id", "route.pi.openai-codex.trusted-dream.v1"),
            ("observed_provider_id", "provider.nonempty-alternative.v1"),
            ("observed_model_id", "model.nonempty-alternative.v1"),
            ("observed_endpoint_id", "endpoint.nonempty-alternative.v1"),
            ("observed_bytes", b"nonempty-arbitrary-egress-alternative"),
            (
                "observed_context_manifest",
                {
                    **base["observed_context_manifest"],
                    "profile_revision": "profile.nonempty-alternative",
                },
            ),
            (
                "observed_route_policy_digest",
                "watari-route-policy-v1:" + "1" * 64,
            ),
            (
                "observed_launch_attestation",
                "nonempty-alternative-opaque-launch",
            ),
            (
                "observed_capability_evidence",
                "nonempty-alternative-opaque-capability",
            ),
        )
        for field, alternative in mutations:
            altered = dict(base)
            altered[field] = alternative
            self.assertTrue(
                egress_receipt_errors(fixed_receipt, **altered), field
            )

        for field in EGRESS_RECEIPT_KEYS:
            candidate = copy.deepcopy(fixed_receipt)
            candidate[field] = "nonempty-alternative"
            self.assertTrue(
                egress_receipt_errors(candidate, **base), field
            )
        missing = copy.deepcopy(fixed_receipt)
        missing.pop("egress_id")
        self.assertTrue(egress_receipt_errors(missing, **base))
        unknown = copy.deepcopy(fixed_receipt)
        unknown["unknown"] = "nonempty"
        self.assertTrue(egress_receipt_errors(unknown, **base))
        for field in (
            "observed_egress_id",
            "observed_route_id",
            "observed_provider_id",
            "observed_model_id",
            "observed_endpoint_id",
            "observed_route_policy_digest",
            "observed_launch_attestation",
            "observed_capability_evidence",
        ):
            for malformed in (None, ""):
                altered = dict(base)
                altered[field] = malformed
                self.assertTrue(
                    egress_receipt_errors(fixed_receipt, **altered),
                    (field, malformed),
                )
        for malformed in (None, {}, {"unknown": "value"}):
            altered = dict(base)
            altered["observed_context_manifest"] = malformed
            self.assertTrue(
                egress_receipt_errors(fixed_receipt, **altered),
                ("observed_context_manifest", malformed),
            )
        for malformed in (None, b""):
            altered = dict(base)
            altered["observed_bytes"] = malformed
            self.assertTrue(egress_receipt_errors(fixed_receipt, **altered))

        disabled = dict(base)
        disabled.update(
            {
                "observed_route_id": "route.session-receipt.claude.v1",
                "observed_provider_id": "provider.local-session.v1",
                "observed_model_id": "model.none.v1",
                "observed_endpoint_id": "endpoint.local-only.v1",
                "observed_context_manifest": {
                    **base["observed_context_manifest"],
                    "visibility": "local-only",
                },
            }
        )
        self.assertIn(
            "egress_route.disabled",
            egress_receipt_errors(fixed_receipt, **disabled),
        )

    def test_t_receipt_provider_output_is_assistant_nonprimary_and_claude_denies(self):
        cases = self.matrix["test_vectors"]["provider_output_receipts"]
        self.assertEqual(set(cases), PROVIDER_OUTPUT_CASE_IDS)
        for case_id, vector in cases.items():
            self.assertEqual(
                typed_digest(
                    "watari-provider-output-vector-v1:",
                    "provider-output-receipt-vector/v1",
                    vector,
                    self.d003,
                ),
                EXPECTED_PROVIDER_OUTPUT_VECTOR_DIGESTS[case_id],
            )
            self.assertFalse(vector["receipt"]["primary_evidence"])
            self.assertEqual(
                turn_receipt_errors(
                    vector["receipt"],
                    **observation_kwargs(vector, self.matrix, self.d003),
                ),
                set(vector["expected_error_codes"]),
            )

        codex_case = cases[
            "case.receipt.provider-output.codex.accept-nonprimary.v1"
        ]
        pi_case = cases[
            "case.receipt.provider-output.pi.accept-nonprimary.v1"
        ]
        claude_case = cases[
            "case.receipt.provider-output.claude.deny.v1"
        ]
        self.assertEqual(
            turn_receipt_errors(
                codex_case["receipt"],
                **observation_kwargs(codex_case, self.matrix, self.d003),
            ),
            set(),
        )
        self.assertEqual(
            turn_receipt_errors(
                pi_case["receipt"],
                **observation_kwargs(pi_case, self.matrix, self.d003),
            ),
            set(),
        )
        self.assertEqual(
            turn_receipt_errors(
                claude_case["receipt"],
                **observation_kwargs(claude_case, self.matrix, self.d003),
            ),
            {"capture_route.provider_output_denied"},
        )

        forged_primary = copy.deepcopy(codex_case["receipt"])
        forged_primary["primary_evidence"] = True
        self.assertIn(
            "primary_evidence",
            turn_receipt_errors(
                forged_primary,
                **observation_kwargs(codex_case, self.matrix, self.d003),
            ),
        )

        fixed = codex_case["receipt"]
        base_kwargs = observation_kwargs(codex_case, self.matrix, self.d003)
        for field, alternative, expected_error in (
            ("observed_bytes", b"nonempty-alternative-provider-bytes", "bytes_digest"),
            (
                "observed_session_lineage",
                "nonempty-alternative-lineage",
                "session_lineage_digest",
            ),
            (
                "observed_launch_attestation",
                "nonempty-alternative-opaque-attestation",
                "watari_launch_attestation_digest",
            ),
        ):
            altered = dict(base_kwargs)
            altered[field] = alternative
            self.assertIn(
                expected_error,
                turn_receipt_errors(fixed, **altered),
                field,
            )

    def test_t_receipt_rejects_relabel_forgery_and_malformed_fields(self):
        vector = self.matrix["test_vectors"]["receipts"][
            "route.session-receipt.claude.v1"
        ]["assistant"]
        kwargs = observation_kwargs(vector, self.matrix, self.d003)
        forged = copy.deepcopy(vector["receipt"])
        forged["role"] = "user"
        forged["source"] = "local-user-turn"
        forged["primary_evidence"] = True
        errors = turn_receipt_errors(forged, **kwargs)
        self.assertTrue({"role", "source_binding", "primary_evidence"} <= errors)

        for field, bad in (
            ("turn_id", ""),
            ("origin_route_id", None),
            ("bytes_digest", None),
            ("role", 1),
            ("source", []),
            ("session_lineage_digest", None),
            ("watari_launch_attestation_digest", ""),
            ("origin_route_provider_model_policy_digest", {}),
            ("primary_evidence", "true"),
        ):
            malformed = copy.deepcopy(vector["receipt"])
            malformed[field] = bad
            self.assertTrue(
                turn_receipt_errors(malformed, **kwargs),
                field,
            )
        missing = copy.deepcopy(vector["receipt"])
        missing.pop("turn_id")
        self.assertTrue(turn_receipt_errors(missing, **kwargs))
        unknown = copy.deepcopy(vector["receipt"])
        unknown["unknown"] = True
        self.assertTrue(turn_receipt_errors(unknown, **kwargs))

    def test_t_receipt_rejects_independent_id_route_and_digest_mismatch(self):
        vector = self.matrix["test_vectors"]["receipts"][
            "route.session-receipt.codex.v1"
        ]["user"]
        kwargs = observation_kwargs(vector, self.matrix, self.d003)
        for field, value, expected_error in (
            ("turn_id", "turn:other", "turn_id"),
            (
                "origin_route_id",
                "route.pi.openai-codex.trusted-dream.v1",
                "origin_route_id",
            ),
            ("bytes_digest", WIRE_TOKEN.pattern.replace("^", ""), "bytes_digest"),
            (
                "session_lineage_digest",
                "watari-lineage-v1:" + "0" * 64,
                "session_lineage_digest",
            ),
            (
                "watari_launch_attestation_digest",
                "watari-attestation-v1:" + "0" * 64,
                "watari_launch_attestation_digest",
            ),
            (
                "origin_route_provider_model_policy_digest",
                "watari-origin-v1:" + "0" * 64,
                "origin_route_provider_model_policy_digest",
            ),
        ):
            candidate = copy.deepcopy(vector["receipt"])
            candidate[field] = value
            self.assertIn(
                expected_error,
                turn_receipt_errors(candidate, **kwargs),
                field,
            )

        altered = dict(kwargs)
        altered["observed_turn_id"] = "turn:independently-different"
        self.assertIn(
            "turn_id",
            turn_receipt_errors(vector["receipt"], **altered),
        )
        altered = dict(kwargs)
        altered["observed_origin_route_id"] = (
            "route.pi.openai-codex.trusted-dream.v1"
        )
        errors = turn_receipt_errors(vector["receipt"], **altered)
        self.assertTrue(
            {"capture_route.origin_not_allowed", "origin_route_id"} <= errors
        )

        resealed_matrix = copy.deepcopy(self.matrix)
        resealed_matrix["routes"][0]["provider_id"] = "provider.spoofed.v1"
        resealed_digest = route_policy_digest(resealed_matrix, self.d003)
        resealed_matrix["route_policy_digest"] = resealed_digest
        for route in resealed_matrix["routes"]:
            route["route_policy_digest"] = resealed_digest
        altered = dict(kwargs)
        altered["trusted_matrix"] = resealed_matrix
        self.assertIn(
            "trusted_matrix.unapproved_policy_digest",
            turn_receipt_errors(vector["receipt"], **altered),
        )

    def test_t_receipt_rejects_unknown_external_connector_and_empty_observations(self):
        vector = self.matrix["test_vectors"]["receipts"][
            "route.session-receipt.codex.v1"
        ]["user"]
        kwargs = observation_kwargs(vector, self.matrix, self.d003)

        for field in (
            "observed_turn_id",
            "observed_capture_route_id",
            "observed_origin_route_id",
            "observed_role",
            "observed_source",
            "observed_session_lineage",
            "observed_launch_attestation",
        ):
            for bad in (None, ""):
                altered = dict(kwargs)
                altered[field] = bad
                self.assertTrue(
                    turn_receipt_errors(vector["receipt"], **altered),
                    (field, bad),
                )
        for bad in (None, b""):
            altered = dict(kwargs)
            altered["observed_bytes"] = bad
            self.assertTrue(turn_receipt_errors(vector["receipt"], **altered))

        altered = dict(kwargs)
        altered["observed_capture_route_id"] = "route.unknown.v1"
        self.assertIn(
            "capture_route.unknown",
            turn_receipt_errors(vector["receipt"], **altered),
        )
        altered = dict(kwargs)
        altered["observed_origin_route_id"] = "route.unknown.v1"
        self.assertIn(
            "origin_route.unknown",
            turn_receipt_errors(vector["receipt"], **altered),
        )

        for capture_id in (
            "route.codex.full-watari.v1",
            "route.connector.read-only.v1",
        ):
            origin_id = capture_id
            receipt = receipt_from_observation(
                self.matrix,
                turn_id="turn:invalid-capture",
                capture_route_id=capture_id,
                origin_route_id=origin_id,
                observed_bytes=b"invalid-capture\n",
                role="user",
                source="local-user-turn",
                lineage="invalid-capture-lineage",
                attestation="invalid-capture-attestation",
                d003=self.d003,
            )
            errors = turn_receipt_errors(
                receipt,
                trusted_matrix=self.matrix,
                observed_turn_id="turn:invalid-capture",
                observed_capture_route_id=capture_id,
                observed_origin_route_id=origin_id,
                observed_bytes=b"invalid-capture\n",
                observed_role="user",
                observed_source="local-user-turn",
                observed_session_lineage="invalid-capture-lineage",
                observed_launch_attestation="invalid-capture-attestation",
                d003=self.d003,
            )
            self.assertIn("capture_route.receipt_not_required", errors)
            self.assertIn("capture_route.origin_not_allowed", errors)

    def test_t_receipt_rejects_nonsemantic_provider_role_and_bad_pairs(self):
        vector = self.matrix["test_vectors"]["receipts"][
            "route.session-receipt.codex.v1"
        ]["assistant"]
        kwargs = observation_kwargs(vector, self.matrix, self.d003)
        for role, source in (
            ("provider", "provider-output"),
            ("user", "provider-output"),
            ("tool", "provider-output"),
            ("system", "local-assistant-turn"),
        ):
            altered = dict(kwargs)
            altered["observed_role"] = role
            altered["observed_source"] = source
            errors = turn_receipt_errors(vector["receipt"], **altered)
            self.assertTrue(
                "semantic_role" in errors or "role_source_pair" in errors,
                (role, source, errors),
            )

    def test_t_route_vector_schema_rejects_missing_unknown_rename_and_turn_change(self):
        candidates = []
        candidate = copy.deepcopy(self.matrix)
        candidate["test_vectors"]["routes"].pop(
            "route.codex.full-watari.v1"
        )
        candidates.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["test_vectors"]["routes"]["route.unknown.v1"] = {}
        candidates.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        route_vector = candidate["test_vectors"]["routes"][
            "route.codex.full-watari.v1"
        ]
        route_vector["wire_digest"] = route_vector.pop("wire_bytes_digest")
        candidates.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["test_vectors"]["receipts"].pop(
            "route.session-receipt.codex.v1"
        )
        candidates.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["test_vectors"]["receipts"]["route.unknown.v1"] = {}
        candidates.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        receipt_vector = candidate["test_vectors"]["receipts"][
            "route.session-receipt.codex.v1"
        ]["user"]
        receipt_vector["capture_route"] = receipt_vector.pop(
            "observed_capture_route_id"
        )
        candidates.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["test_vectors"]["receipts"][
            "route.session-receipt.codex.v1"
        ]["user"]["receipt"]["turn_id"] = "turn:renamed"
        candidates.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["test_vectors"]["provider_output_receipts"].pop(
            "case.receipt.provider-output.pi.accept-nonprimary.v1"
        )
        candidates.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["test_vectors"]["provider_output_receipts"][
            "case.receipt.provider-output.unknown.v1"
        ] = {}
        candidates.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        provider_case = candidate["test_vectors"]["provider_output_receipts"][
            "case.receipt.provider-output.codex.accept-nonprimary.v1"
        ]
        provider_case["case"] = provider_case.pop("case_id")
        candidates.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["test_vectors"]["egress_receipts"].pop(
            "case.egress.structural-arbitrary.codex.v1"
        )
        candidates.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["test_vectors"]["egress_receipts"][
            "case.egress.structural-unknown.v1"
        ] = {}
        candidates.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        egress_case = candidate["test_vectors"]["egress_receipts"][
            "case.egress.structural-arbitrary.codex.v1"
        ]
        egress_case["bytes_hex"] = egress_case.pop("observed_bytes_hex")
        candidates.append(candidate)
        for candidate in candidates:
            self._assert_rejected(candidate)

    def test_t_policy_exclusions_are_code_owned_exact_and_counted(self):
        self.assertEqual(
            self.matrix["projection_policy"]["policy_digest_excluded_paths"],
            POLICY_EXCLUDED_PATH_STRINGS,
        )
        self.assertEqual(
            policy_exclusion_match_counts(self.matrix),
            EXPECTED_EXCLUSION_MATCH_COUNTS,
        )
        base = route_policy_digest(self.matrix, self.d003)
        for mutate in (
            lambda m: m["routes"][0]["connector_contract"].__setitem__(
                "contract_digest",
                m["routes"][0]["connector_contract"]["contract_digest"] + "x",
            ),
            lambda m: m["routes"][0].__setitem__(
                "route_policy_digest",
                m["routes"][0]["route_policy_digest"] + "x",
            ),
            lambda m: m.__setitem__("test_vectors", {"entirely": "derived"}),
        ):
            candidate = copy.deepcopy(self.matrix)
            mutate(candidate)
            self.assertEqual(route_policy_digest(candidate, self.d003), base)

        for path, value in (
            (("session_receipt_schema", "route_policy_digest"), "same-name"),
            (("routes", 0, "origin_policy", "contract_digest"), "same-name"),
            (("projection_policy", "test_vectors"), "same-name"),
        ):
            candidate = copy.deepcopy(self.matrix)
            parent = candidate
            for part in path[:-1]:
                parent = parent[part]
            parent[path[-1]] = value
            self.assertNotEqual(route_policy_digest(candidate, self.d003), base)

    def test_t_prior_audit_mutations_still_reject_after_resealing(self):
        candidates = []

        candidate = copy.deepcopy(self.matrix)
        candidate["context_selection"]["implicit_default"] = "allow"
        candidates.append(("context-selection", candidate))

        candidate = copy.deepcopy(self.matrix)
        candidate["provider_output_default_trust"] = "trusted"
        candidates.append(("provider-default", candidate))

        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["caller_runtime"] = "spoofed-runtime"
        candidates.append(("caller-runtime", candidate))

        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["provider_model_class"] = "low-risk-model"
        candidates.append(("provider-class", candidate))

        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["network_endpoint_class"] = "unbounded-egress"
        candidates.append(("network-class", candidate))

        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["wire_projection"]["byte_selection"] = "all"
        candidates.append(("wire-policy", candidate))

        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["session_receipt"]["source_binding"] = "optional"
        candidates.append(("receipt-policy", candidate))

        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][4]["origin_policy"]["allowed_origin_route_ids"] = [
            "route.pi.openrouter.low-risk-utility.v1"
        ]
        candidates.append(("origin-policy", candidate))

        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["fail_closed_conditions"].remove(
            "provider-mismatch"
        )
        candidates.append(("fail-condition", candidate))

        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["d001_trace"].remove("MX-001")
        candidates.append(("trace-subset", candidate))

        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][2]["forbidden_data"].remove("private.memory")
        candidates.append(("openrouter-private-data", candidate))

        for path in ("POST /approved-scope/**", "GET /global-admin/**"):
            candidate = copy.deepcopy(self.matrix)
            connector = candidate["routes"][6]["connector_contract"]
            connector["allowed_method_paths"] = [path]
            connector_body = {
                key: value
                for key, value in connector.items()
                if key != "contract_digest"
            }
            connector["contract_digest"] = typed_digest(
                "watari-connector-v1:",
                "connector-contract/v1",
                connector_body,
                self.d003,
            )
            candidates.append((path, candidate))

        for label, candidate in candidates:
            resealed = route_policy_digest(candidate, self.d003)
            self.assertNotEqual(resealed, self.matrix["route_policy_digest"], label)
            candidate["route_policy_digest"] = resealed
            for route in candidate["routes"]:
                route["route_policy_digest"] = resealed
            self._assert_rejected(candidate)

    def test_t_route_matrix_negative_mutation_corpus(self):
        mutations = []
        candidate = copy.deepcopy(self.matrix)
        candidate["unknown"] = True
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["provider_id"], candidate["routes"][1]["provider_id"] = (
            candidate["routes"][1]["provider_id"],
            candidate["routes"][0]["provider_id"],
        )
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][2]["capability_set"]["network"] = "allow:any"
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["sandbox_class"] = "none"
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][2]["allowed_projection"].append("private.memory")
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][3]["direction"]["egress"]["enabled"] = True
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["retention_zdr"]["zero_data_retention"] = "disabled"
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["origin_policy"]["source_binding"] = "disabled"
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][1]["direction"]["ingress"]["accepted_roles"] = ["user"]
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][6]["connector_contract"]["allowed_method_paths"] = [
            "POST /approved-scope/**"
        ]
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][6]["connector_contract"][
            "checkpoint_lineage_binding"
        ] = "verified"
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["d001_trace"].append("UNKNOWN")
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][3]["session_receipt"]["role_provenance"] = "user"
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][4]["origin_policy"][
            "allowed_origin_route_ids"
        ] = ["route.pi.openrouter.low-risk-utility.v1"]
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["session_receipt_schema"]["role_values"].append("provider")
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["capability_set"] = "deny"
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["wire_projection"] = None
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["direction"]["ingress"]["accepted_roles"] = "user"
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][6]["connector_contract"]["allowed_method_paths"] = 1
        mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["origin_policy"] = None
        mutations.append(candidate)
        for candidate in mutations:
            self._assert_rejected(candidate)

    def test_t_closed_schema_rejects_malformed_types_and_unknown_members(self):
        candidates = []
        for malformed in (None, "routes", 1, {}):
            candidate = copy.deepcopy(self.matrix)
            candidate["routes"] = malformed
            candidates.append(candidate)

        candidate = copy.deepcopy(self.matrix)
        candidate["test_vectors"] = None
        candidates.append(candidate)

        candidate = copy.deepcopy(self.matrix)
        candidate["session_receipt_schema"]["allowed_role_source_pairs"] = None
        candidates.append(candidate)

        candidate = copy.deepcopy(self.matrix)
        candidate["egress_receipt_schema"] = None
        candidates.append(candidate)

        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["direction"] = None
        candidates.append(candidate)

        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][4]["origin_policy"]["allowed_origin_route_ids"] = (
            "route.codex.full-watari.v1"
        )
        candidates.append(candidate)

        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][6]["connector_contract"] = []
        candidates.append(candidate)

        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["wire_projection"]["unknown"] = True
        candidates.append(candidate)

        candidate = copy.deepcopy(self.matrix)
        candidate["test_vectors"]["receipts"][
            "route.session-receipt.codex.v1"
        ]["user"]["receipt"] = None
        candidates.append(candidate)

        candidate = copy.deepcopy(self.matrix)
        candidate["test_vectors"]["provider_output_receipts"][
            "case.receipt.provider-output.codex.accept-nonprimary.v1"
        ]["receipt"] = None
        candidates.append(candidate)

        candidate = copy.deepcopy(self.matrix)
        candidate["test_vectors"]["egress_receipts"][
            "case.egress.structural-arbitrary.codex.v1"
        ]["receipt"] = None
        candidates.append(candidate)

        for candidate in candidates:
            self._assert_rejected(candidate)

    def test_t_route_matrix_nested_schema_and_duplicate_members(self):
        self._validate_closed(self.matrix)

        def duplicate_reject(pairs):
            seen = set()
            for key, _ in pairs:
                if key in seen:
                    raise ValueError("duplicate JSON member")
                seen.add(key)
            return dict(pairs)

        with self.assertRaises(ValueError):
            json.loads(
                '{"route_id":"a","route_id":"b"}',
                object_pairs_hook=duplicate_reject,
            )

    def test_t_every_included_policy_leaf_changes_digest(self):
        projection = policy_projection(self.matrix)
        paths = []

        def walk(value, path=()):
            if isinstance(value, dict):
                for key, child in value.items():
                    walk(child, path + (key,))
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, path + (index,))
            else:
                paths.append(path)

        walk(projection)
        self.assertGreater(len(paths), 100)
        for path in paths:
            candidate = copy.deepcopy(self.matrix)
            parent = candidate
            for component in path[:-1]:
                parent = parent[component]
            key = path[-1]
            old = parent[key]
            if isinstance(old, bool):
                parent[key] = not old
            elif isinstance(old, str):
                parent[key] = old + "-mutation"
            elif isinstance(old, int):
                parent[key] = old + 1
            else:
                self.fail(
                    f"unhandled policy leaf type at {path}: {type(old)}"
                )
            self.assertNotEqual(
                route_policy_digest(candidate, self.d003),
                self.matrix["route_policy_digest"],
                path,
            )


if __name__ == "__main__":
    unittest.main()
