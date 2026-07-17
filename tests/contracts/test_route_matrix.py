import copy
import hashlib
import importlib.util
import json
import re
import struct
import unittest
from pathlib import Path


ADR = Path(__file__).parents[2] / "docs" / "adr" / "005-data-routes.md"
EXPECTED_ROUTE_IDS = {
    "route.codex.full-watari.v1",
    "route.pi.openai-codex.trusted-dream.v1",
    "route.pi.openrouter.low-risk-utility.v1",
    "route.session-receipt.claude.v1",
    "route.session-receipt.codex.v1",
    "route.session-receipt.pi-high-trust.v1",
    "route.connector.read-only.v1",
}
VISIBILITIES = {"local-only", "trusted-model", "low-risk-model"}
CAPABILITY_KEYS = {"mount", "retrieval", "shell", "file", "project", "external_write", "process", "network"}
MUTATION_KEYS = {"canonical_write", "profile_write", "checkpoint_write", "connector_write", "external_write", "credential_write", "project_layer_write"}
ROUTE_TOKEN = re.compile(r"^watari-route-policy-v1:[0-9a-f]{64}$")
CONTEXT_TOKEN = re.compile(r"^watari-context-effective-v1:[0-9a-f]{64}$")
WIRE_TOKEN = re.compile(r"^watari-wire-bytes-v1:[0-9a-f]{64}$")
LINEAGE_TOKEN = re.compile(r"^watari-lineage-v1:[0-9a-f]{64}$")
ATTESTATION_TOKEN = re.compile(r"^watari-attestation-v1:[0-9a-f]{64}$")
ORIGIN_TOKEN = re.compile(r"^watari-origin-v1:[0-9a-f]{64}$")
CONNECTOR_TOKEN = re.compile(r"^watari-connector-v1:[0-9a-f]{64}$")
TRACE = {
    "route.codex.full-watari.v1": {"MX-001", "RQ-002", "RQ-004", "AC-002"},
    "route.pi.openai-codex.trusted-dream.v1": {"MX-002", "RQ-004", "RQ-006", "AC-006"},
    "route.pi.openrouter.low-risk-utility.v1": {"MX-003", "RQ-004", "RQ-009", "NM-004", "AC-009"},
    "route.session-receipt.claude.v1": {"MX-004", "RQ-002", "RQ-004", "AC-002", "AC-004"},
    "route.session-receipt.codex.v1": {"MX-004", "RQ-002", "RQ-004", "AC-002", "AC-004"},
    "route.session-receipt.pi-high-trust.v1": {"MX-004", "RQ-002", "RQ-004", "AC-002", "AC-004"},
    "route.connector.read-only.v1": {"MX-005", "RQ-005", "AC-005"},
}
TRACE_FULL = {route_id: values | {"SB-001", "SB-003", "SB-004"} for route_id, values in TRACE.items()}
EXACT = {
    "route.codex.full-watari.v1": ("provider.openai.codex-cli.v1", "model.codex.full-watari.v1", "endpoint.codex.approved.v1", "runtime.codex-dedicated", "trusted-model", ["profile.explicit", "memory.trusted-projection", "user.turn", "source.verified-projection"]),
    "route.pi.openai-codex.trusted-dream.v1": ("provider.openai.api.v1", "model.openai-codex.trusted-dream.v1", "endpoint.openai.exact.v1", "runtime.pi-openai-codex-dedicated", "trusted-model", ["user.turn", "source.verified-projection", "memory.dream-candidate"]),
    "route.pi.openrouter.low-risk-utility.v1": ("provider.openrouter.api.v1", "model.openrouter.low-risk-utility.v1", "endpoint.openrouter.exact.v1", "runtime.openrouter-dedicated", "low-risk-model", ["user.turn", "utility.task.minimal"]),
    "route.session-receipt.claude.v1": ("provider.local-session.v1", "model.none.v1", "endpoint.local-only.v1", "none", "local-only", ["session.receipt"]),
    "route.session-receipt.codex.v1": ("provider.local-session.v1", "model.none.v1", "endpoint.local-only.v1", "none", "local-only", ["session.receipt"]),
    "route.session-receipt.pi-high-trust.v1": ("provider.local-session.v1", "model.none.v1", "endpoint.local-only.v1", "none", "local-only", ["session.receipt"]),
    "route.connector.read-only.v1": ("provider.connector.v1", "model.none.v1", "endpoint.connector-read-only.v1", "connector-instance-scoped", "local-only", ["connector.approved-projection"]),
}
EXPECTED_POLICY_DIGEST = "watari-route-policy-v1:3635e7573d1b7ea269683796284ab5d63671f771b3c14c787b43b9789122f40a"
EXPECTED_VECTORS = {
    'route.codex.full-watari.v1': ('watari-context-effective-v1:3b30c539fb4acca5fd80adfd031bc0379bcbf7ae16446a452bbf5b63162552c9', 'watari-wire-bytes-v1:2d09d8d1a72e2840a0ae5acd9c957057a37783a404c631f0b8f33117d0e6b686', 'watari-lineage-v1:2081ab7292f5670979529d4f9ad911bdc1b8a39892deaa30762776124de2b44c', 'watari-attestation-v1:9525072f17ca01426896ce2e38d1e8b09856433615cc54e8d24650ab580b0974', 'watari-origin-v1:67e42e39690c504aea6f9f84156478203408a6b0dd62183c732a83807b8fdac9', 'watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1'),
    'route.pi.openai-codex.trusted-dream.v1': ('watari-context-effective-v1:3e3c9b4970c8ee40a1bbf10259fd18cf45f262c82dc6b475cdccd45c8735a7ff', 'watari-wire-bytes-v1:fffc52d9651394ab7f2641724f0b7f7e8a8b3d2e981dcba4ae307be141a6cade', 'watari-lineage-v1:85fd52b50b11430ca20450cb599bd3cc0752105656c30fdc799449ee8e442f03', 'watari-attestation-v1:bb6f3e3428b4c7c128b5db7dd3e676cd067d4150aba4b91d91dda5b21580d2e4', 'watari-origin-v1:69ff29becb0c8d11edf264acd8c827b352b2cb525c9ef8e99d4ba7ceefc837f3', 'watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1'),
    'route.pi.openrouter.low-risk-utility.v1': ('watari-context-effective-v1:1d688cd4998af26e09a5fecce2b53932fe02920cc02b88d4178e51c54e646543', 'watari-wire-bytes-v1:af87aa8b8146e9e54599928ed27f6e5054b698b995d62536b4b867d90c886f4e', 'watari-lineage-v1:de3304e1a472459698c6bf02280f76dcd38d68a0925272c336ae4d661cf0130c', 'watari-attestation-v1:0342acd6ebfc6e43c38971c95612b94992633abb94859aecd6b11f271a49b8e3', 'watari-origin-v1:423ec9f8a3702f7a1089918838cd640476a0e24d2c21e60d0b828d55cd737b6c', 'watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1'),
    'route.session-receipt.claude.v1': ('watari-context-effective-v1:09bb7b3e52e90fef3a0e7cd361ce806cb5e09e9f86b51edc061538061f6b2cf2', 'watari-wire-bytes-v1:966920edc9320531ad765bc8cc9715f82c2b26576a71359b56b426ae59c05fda', 'watari-lineage-v1:f5b6bca251c76158c4d4f880c80eeb1d5c0573c09f3c5df3395170c7967986ee', 'watari-attestation-v1:acc7073b6860bef59ae0a1a6a6bcb6f84c65de01886778995569ed622d4dca84', 'watari-origin-v1:a5054dfa8f2fbab711627a331a0ace38108f76223d4fe00edfc0742c9a43e1f7', 'watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1'),
    'route.session-receipt.codex.v1': ('watari-context-effective-v1:5205225905b0bd77a562ba39fbab1913cca10d61ad3edd0b357845e2d92da609', 'watari-wire-bytes-v1:4978c3f6467eda12dc85685311ffd3244350d380e13993c65b932b29b3026291', 'watari-lineage-v1:4da8d577b04d162afc5c3f25937e84b3e2ddf6edc8ac88f012cb9069db6bd166', 'watari-attestation-v1:56714f2f266637ecf7d85ab087b111bd5577917746bffc416649c360a7dde7c6', 'watari-origin-v1:16a9b80a9ba3e8e46d215927151f2b7eeb208ad90166ba35587aae9a6e2c7cc8', 'watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1'),
    'route.session-receipt.pi-high-trust.v1': ('watari-context-effective-v1:705a384740f05aaa9df93fb03a56c12ff000e2cefdc1fce8f7d7ebe17e34a5f1', 'watari-wire-bytes-v1:e7f3a7c55ca953ca580baba635eb99345b2a842df0a77bba69d7189befa48bc8', 'watari-lineage-v1:59534dc5a444c7bf790281a75dead434087a939db2abf4d84324585feff3fee8', 'watari-attestation-v1:2366c9428fc06ddb6519bb803867de908d744eb9d6190c10729bc5ab1194e82c', 'watari-origin-v1:de40342104d38fed1a2b03bfc4af77a0c2b00b2d9ea347606ecaee7fe01bfae3', 'watari-connector-v1:931d23e342b0be08d8966913d12cc5d407c1cdc5503343e0d4d6328eec48afe1'),
    'route.connector.read-only.v1': ('watari-context-effective-v1:5b7117fd9cdcf7a7e3c0b4d6f97ddc148321608522e3bd99fcd1853b88d8c244', 'watari-wire-bytes-v1:9d89e1aeaa1680d4d9c2123b250890ccd6da01db6322e16cb13a4d55b6dbe745', 'watari-lineage-v1:adde0f7738e39e5ce05eb989bdcb8e5e9141aba5101b1c9cbd3cd29b17b3e61a', 'watari-attestation-v1:e5da59c32414f45882cfda0d1c488498a4d9936f09a1b4d4d4edf8888e64ad52', 'watari-origin-v1:52e55ea8f33d7fd600518ed426e9e5937685968d63e9a2012474da09a6b39e39', 'watari-connector-v1:f9e4bc1a0aa6a21aa5b003b29e53ecc30dec9d078c43051b2ca809f74309a3e2'),
}


EXPECTED_RECEIPT_GOLDENS = {
    'route.session-receipt.claude.v1': {
        'user': ('7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e636c617564652e76313a757365720a', 'lineage:route.session-receipt.claude.v1:user', 'attestation:route.session-receipt.claude.v1', 'provider.local-session.v1', 'model.none.v1', 'watari-wire-bytes-v1:d4bf6c7638e77dbdace472708aa27e50cf8f08963a2b3f0323ea17c20685a899', 'watari-lineage-v1:20da8a55baa676b0adac272b60e919fad1cf604c99ae01b7e4c1e4ec252c3c8a', 'watari-attestation-v1:c87aef69ee90f62275c0dd4564f1b54f67867050a020f9169c1f9f2c372612d3', 'watari-origin-v1:a5054dfa8f2fbab711627a331a0ace38108f76223d4fe00edfc0742c9a43e1f7', True),
        'assistant': ('7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e636c617564652e76313a617373697374616e740a', 'lineage:route.session-receipt.claude.v1:assistant', 'attestation:route.session-receipt.claude.v1', 'provider.local-session.v1', 'model.none.v1', 'watari-wire-bytes-v1:9e8b3e8cb60e54c96e0f0095a05386cff7c0ac10fe8fe9554148e561dc3ce3ef', 'watari-lineage-v1:fdddee85f6ace64322b068a03aacba715d2663181db4d0e7af359ad3328f530a', 'watari-attestation-v1:c87aef69ee90f62275c0dd4564f1b54f67867050a020f9169c1f9f2c372612d3', 'watari-origin-v1:a5054dfa8f2fbab711627a331a0ace38108f76223d4fe00edfc0742c9a43e1f7', False),
        'tool': ('7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e636c617564652e76313a746f6f6c0a', 'lineage:route.session-receipt.claude.v1:tool', 'attestation:route.session-receipt.claude.v1', 'provider.local-session.v1', 'model.none.v1', 'watari-wire-bytes-v1:3d12baefb745a644cc9d4272fe0f895a49e391de71d1673341d46ac10783b09c', 'watari-lineage-v1:5f4577136dccd27e5c4e60f4c391620709397bcc93aea3a4c4bd7a0ffdca9816', 'watari-attestation-v1:c87aef69ee90f62275c0dd4564f1b54f67867050a020f9169c1f9f2c372612d3', 'watari-origin-v1:a5054dfa8f2fbab711627a331a0ace38108f76223d4fe00edfc0742c9a43e1f7', False),
        'system': ('7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e636c617564652e76313a73797374656d0a', 'lineage:route.session-receipt.claude.v1:system', 'attestation:route.session-receipt.claude.v1', 'provider.local-session.v1', 'model.none.v1', 'watari-wire-bytes-v1:1834893827e4e923263a9312a0a877f6d88ec956153f3678d8ca7a1fb9e72eb5', 'watari-lineage-v1:1deda292d2e59f1dbd7a92442ba88cafcf70bd059961ea4719dcd853709b5184', 'watari-attestation-v1:c87aef69ee90f62275c0dd4564f1b54f67867050a020f9169c1f9f2c372612d3', 'watari-origin-v1:a5054dfa8f2fbab711627a331a0ace38108f76223d4fe00edfc0742c9a43e1f7', False),
    },
    'route.session-receipt.codex.v1': {
        'user': ('7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e636f6465782e76313a757365720a', 'lineage:route.session-receipt.codex.v1:user', 'attestation:route.session-receipt.codex.v1', 'provider.local-session.v1', 'model.none.v1', 'watari-wire-bytes-v1:edac1a991b619cd24f552be61acc5dde4c87312d6a8dcb5262df34a68c4c98ff', 'watari-lineage-v1:ff40b7b36f2da546677a885d205f9f65f293348f5571c5c880e7d44985a34634', 'watari-attestation-v1:00414eba310a4e03f90275fca55d8fae4a972f1cc7d1f7d8d718c7bc3563e4a5', 'watari-origin-v1:16a9b80a9ba3e8e46d215927151f2b7eeb208ad90166ba35587aae9a6e2c7cc8', True),
        'assistant': ('7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e636f6465782e76313a617373697374616e740a', 'lineage:route.session-receipt.codex.v1:assistant', 'attestation:route.session-receipt.codex.v1', 'provider.local-session.v1', 'model.none.v1', 'watari-wire-bytes-v1:61c65ed425f3f9317c8b7015dc4be9822b27c7294e7fd5f8bbf732c7dd7e9425', 'watari-lineage-v1:088f82ba958b53f6fe8225c023f82bb63d94469c5675c4ba2c27b3d8c1fc27c8', 'watari-attestation-v1:00414eba310a4e03f90275fca55d8fae4a972f1cc7d1f7d8d718c7bc3563e4a5', 'watari-origin-v1:16a9b80a9ba3e8e46d215927151f2b7eeb208ad90166ba35587aae9a6e2c7cc8', False),
        'tool': ('7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e636f6465782e76313a746f6f6c0a', 'lineage:route.session-receipt.codex.v1:tool', 'attestation:route.session-receipt.codex.v1', 'provider.local-session.v1', 'model.none.v1', 'watari-wire-bytes-v1:84deea574159e6549f1b11a606a213dbdab8c44a0654ed996e3b78b52cbaf132', 'watari-lineage-v1:9e6184f6d64cd5ee73e857046baad34400ca30f00b56e18303ab728dbc767413', 'watari-attestation-v1:00414eba310a4e03f90275fca55d8fae4a972f1cc7d1f7d8d718c7bc3563e4a5', 'watari-origin-v1:16a9b80a9ba3e8e46d215927151f2b7eeb208ad90166ba35587aae9a6e2c7cc8', False),
        'system': ('7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e636f6465782e76313a73797374656d0a', 'lineage:route.session-receipt.codex.v1:system', 'attestation:route.session-receipt.codex.v1', 'provider.local-session.v1', 'model.none.v1', 'watari-wire-bytes-v1:66dce2c65d4360f063be9a4378dad38b2514a8d04675c09c07e514579f2acd25', 'watari-lineage-v1:f74749655532e5712a739dc247d23fe5ef93abb11c97cbeac007f667ab405540', 'watari-attestation-v1:00414eba310a4e03f90275fca55d8fae4a972f1cc7d1f7d8d718c7bc3563e4a5', 'watari-origin-v1:16a9b80a9ba3e8e46d215927151f2b7eeb208ad90166ba35587aae9a6e2c7cc8', False),
    },
    'route.session-receipt.pi-high-trust.v1': {
        'user': ('7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e70692d686967682d74727573742e76313a757365720a', 'lineage:route.session-receipt.pi-high-trust.v1:user', 'attestation:route.session-receipt.pi-high-trust.v1', 'provider.local-session.v1', 'model.none.v1', 'watari-wire-bytes-v1:d80ce5ddbc40686e931329bf8852dd1d16749f9139ff52ece82e735c52f402e8', 'watari-lineage-v1:45dd3de1c7eb21cb015d9b90f380bd539dcc6e54d2dc173564782fe197195ce3', 'watari-attestation-v1:dccaaefe4a4de78ee548bbafe461ad596c34fb59692c502fc8feb95bd72999d8', 'watari-origin-v1:de40342104d38fed1a2b03bfc4af77a0c2b00b2d9ea347606ecaee7fe01bfae3', True),
        'assistant': ('7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e70692d686967682d74727573742e76313a617373697374616e740a', 'lineage:route.session-receipt.pi-high-trust.v1:assistant', 'attestation:route.session-receipt.pi-high-trust.v1', 'provider.local-session.v1', 'model.none.v1', 'watari-wire-bytes-v1:8544f4774a68885d77d65aa46c893c0a802c3aa183b171140fd28ecee0cf1578', 'watari-lineage-v1:f40e1460c65ad9074769c46c9dba7e1120fc9f6ec1693d29c58b4cc027a461f6', 'watari-attestation-v1:dccaaefe4a4de78ee548bbafe461ad596c34fb59692c502fc8feb95bd72999d8', 'watari-origin-v1:de40342104d38fed1a2b03bfc4af77a0c2b00b2d9ea347606ecaee7fe01bfae3', False),
        'tool': ('7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e70692d686967682d74727573742e76313a746f6f6c0a', 'lineage:route.session-receipt.pi-high-trust.v1:tool', 'attestation:route.session-receipt.pi-high-trust.v1', 'provider.local-session.v1', 'model.none.v1', 'watari-wire-bytes-v1:bc27c51dcf6c78490572ba3d606c8ef1901e7799763657314b1060ed9a884a2d', 'watari-lineage-v1:d3af092bbd111bef3669735d5644c2f6e2a1e80f91c79832d3c9a32ad194d76d', 'watari-attestation-v1:dccaaefe4a4de78ee548bbafe461ad596c34fb59692c502fc8feb95bd72999d8', 'watari-origin-v1:de40342104d38fed1a2b03bfc4af77a0c2b00b2d9ea347606ecaee7fe01bfae3', False),
        'system': ('7475726e2d62797465733a726f7574652e73657373696f6e2d726563656970742e70692d686967682d74727573742e76313a73797374656d0a', 'lineage:route.session-receipt.pi-high-trust.v1:system', 'attestation:route.session-receipt.pi-high-trust.v1', 'provider.local-session.v1', 'model.none.v1', 'watari-wire-bytes-v1:1356f2543ff7c9643ef626cc62439ebe9d1dcedeb1e0d0cbc156342259b37361', 'watari-lineage-v1:fe2bfbe79f2e6490b6f1397cec0b987b23b355869e387a37208711613fe01ec8', 'watari-attestation-v1:dccaaefe4a4de78ee548bbafe461ad596c34fb59692c502fc8feb95bd72999d8', 'watari-origin-v1:de40342104d38fed1a2b03bfc4af77a0c2b00b2d9ea347606ecaee7fe01bfae3', False),
    },
}

def d003_module():
    path = Path(__file__).parents[2] / "tests" / "unit" / "test_canonical_vectors.py"
    spec = importlib.util.spec_from_file_location("d003_canonical_vectors", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def policy_projection(matrix):
    excluded = tuple(matrix["test_vectors"]["excluded_paths"])
    def excluded_path(path):
        normalized = ".".join("*" if isinstance(part, int) else part for part in path).replace("routes.*", "routes[*]")
        return normalized in excluded
    def clean(value, path=()):
        if isinstance(value, dict):
            output = {}
            for key, child in value.items():
                child_path = path + (key,)
                if excluded_path(child_path):
                    continue
                output[key] = clean(child, child_path)
            return output
        if isinstance(value, list):
            return [clean(child, path + (index,)) for index, child in enumerate(value)]
        return value
    return clean(matrix)


def route_policy_digest(matrix, d003):
    payload = d003.canonical_bytes(policy_projection(matrix))
    frame = b"WATARI\x00route-policy/v1\x00" + struct.pack(">Q", len(payload)) + payload
    return "watari-route-policy-v1:" + hashlib.sha256(frame).hexdigest()


def typed_digest(prefix, domain, payload, d003):
    raw = payload if isinstance(payload, bytes) else d003.canonical_bytes(payload)
    frame = b"WATARI\x00" + domain.encode("ascii") + b"\x00" + struct.pack(">Q", len(raw)) + raw
    return prefix + hashlib.sha256(frame).hexdigest()


RECEIPT_KEYS = {"schema_version", "turn_id", "route_id", "bytes_digest", "role", "source", "session_lineage_digest", "watari_launch_attestation_digest", "origin_route_provider_model_policy_digest", "primary_evidence"}
ROLE_SOURCE = {"user": "local-user-turn", "assistant": "local-assistant-turn", "tool": "local-tool-turn", "system": "local-system-turn", "provider": "provider-output"}


def turn_receipt_errors(receipt, *, observed_bytes, observed_role, observed_source, expected_route_id, expected_session_lineage, expected_launch_attestation, expected_provider_id, expected_model_id, expected_route_policy_digest, d003):
    """Return fail-closed errors by comparing a receipt to independent capture inputs."""
    errors = set()
    try:
        if not isinstance(receipt, dict):
            return {"receipt.type"}
        missing = RECEIPT_KEYS - set(receipt)
        unknown = set(receipt) - RECEIPT_KEYS
        errors |= {"receipt.missing:" + key for key in missing}
        errors |= {"receipt.unknown:" + key for key in unknown}
        if errors:
            return errors
        if receipt["schema_version"] != "watari.turn-receipt.v1":
            errors.add("schema_version")
        if not isinstance(receipt["turn_id"], str) or not receipt["turn_id"]:
            errors.add("turn_id.type")
        if receipt["route_id"] != expected_route_id:
            errors.add("route_id")
        if not isinstance(observed_bytes, bytes):
            errors.add("observed_bytes.type")
        else:
            expected_bytes_digest = typed_digest("watari-wire-bytes-v1:", "wire-bytes/v1", observed_bytes, d003)
            if receipt["bytes_digest"] != expected_bytes_digest:
                errors.add("bytes_digest")
        if observed_role not in ROLE_SOURCE:
            errors.add("observed_role")
        if observed_source != ROLE_SOURCE.get(observed_role):
            errors.add("role_source")
        if receipt["role"] != observed_role:
            errors.add("role")
        if receipt["source"] != observed_source:
            errors.add("source")
        expected_primary = observed_role == "user" and observed_source == "local-user-turn"
        if type(receipt["primary_evidence"]) is not bool or receipt["primary_evidence"] != expected_primary:
            errors.add("primary_evidence")
        if receipt["session_lineage_digest"] != typed_digest("watari-lineage-v1:", "session-lineage/v1", {"route_id": expected_route_id, "lineage": expected_session_lineage}, d003):
            errors.add("session_lineage_digest")
        if receipt["watari_launch_attestation_digest"] != typed_digest("watari-attestation-v1:", "watari-attestation/v1", {"route_id": expected_route_id, "attestation": expected_launch_attestation, "caller_runtime": "session-receipt"}, d003):
            errors.add("watari_launch_attestation_digest")
        expected_origin = {"route_id": expected_route_id, "provider_id": expected_provider_id, "model_id": expected_model_id, "route_policy_digest": expected_route_policy_digest}
        if receipt["origin_route_provider_model_policy_digest"] != typed_digest("watari-origin-v1:", "origin-route/v1", expected_origin, d003):
            errors.add("origin_route_provider_model_policy_digest")
    except Exception as error:
        errors.add("verifier.exception:" + type(error).__name__)
    return errors


def assert_exact_keys(test, value, expected, label):
    test.assertIsInstance(value, dict, label)
    test.assertEqual(set(value), set(expected), label)


def load_matrix():
    text = ADR.read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)\n```", text, re.DOTALL)
    if len(blocks) != 1:
        raise AssertionError(f"T-ROUTE-MATRIX requires exactly one JSON block, got {len(blocks)}")
    def reject_duplicate(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON member")
            result[key] = value
        return result
    return json.loads(blocks[0], object_pairs_hook=reject_duplicate)


class RouteMatrixTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = load_matrix()
        cls.routes = {route["route_id"]: route for route in cls.matrix["routes"]}
        cls.d003 = d003_module()

    def test_t_route_matrix_schema_and_exact_routes(self):
        required_top = {
            "schema_version", "route_policy_revision", "route_policy_digest", "visibility_values",
            "capability_values", "fallback_values", "retention_zdr_values", "context_selection",
            "mutation_policy", "projection_policy", "connector_instance_policy", "routes",
        }
        self.assertTrue(required_top <= self.matrix.keys())
        self.assertEqual(self.matrix["schema_version"], "watari.route-matrix.v1")
        self.assertEqual(self.matrix["route_policy_revision"], "D003.route-policy.v1")
        self.assertRegex(self.matrix["route_policy_digest"], ROUTE_TOKEN)
        self.assertEqual(self.matrix["route_policy_digest"], route_policy_digest(self.matrix, self.d003))
        self.assertEqual(set(self.routes), EXPECTED_ROUTE_IDS)
        self.assertEqual(len(self.routes), len(self.matrix["routes"]))
        required_route = {
            "route_id", "caller_runtime", "provider_model_class", "provider_id", "model_id", "endpoint_id",
            "input_visibility", "allowed_projection", "forbidden_data", "network_endpoint_class",
            "credential_reference_class", "credential_scope", "fallback_policy", "retention_zdr",
            "output_trust", "canonical_write", "dream", "sandbox_class", "fail_closed_conditions",
            "route_policy_revision", "route_policy_digest", "golden_fingerprint", "capability_set",
            "project_layer_policy", "wire_projection", "direction", "session_receipt",
            "connector_contract", "origin_policy", "d001_trace",
        }
        for route in self.matrix["routes"]:
            self.assertTrue(required_route <= route.keys(), route["route_id"])
            self.assertRegex(route["golden_fingerprint"], CONTEXT_TOKEN, route["route_id"])
            self.assertEqual(route["route_policy_revision"], self.matrix["route_policy_revision"], route["route_id"])
            self.assertEqual(route["route_policy_digest"], self.matrix["route_policy_digest"], route["route_id"])
            for field in ("provider_id", "model_id", "endpoint_id", "credential_scope"):
                self.assertTrue(route[field])
                self.assertNotIn("*", route[field])
            self.assertTrue(set(route["d001_trace"]) >= TRACE[route["route_id"]])

    def test_t_route_matrix_rejects_all_mutation_and_fallbacks(self):
        self.assertEqual(self.matrix["unknown_policy"], "fail-closed")
        self.assertEqual(self.matrix["fallback_values"], ["disabled"])
        self.assertEqual(set(self.matrix["mutation_policy"]), MUTATION_KEYS)
        self.assertTrue(all(value == "deny" for value in self.matrix["mutation_policy"].values()))
        for route in self.routes.values():
            self.assertFalse(route["canonical_write"], route["route_id"])
            self.assertEqual(route["fallback_policy"], "disabled", route["route_id"])
            self.assertEqual(route["direction"]["ingress"]["canonical_write"], "deny", route["route_id"])
            self.assertEqual(route["capability_set"]["external_write"], "deny", route["route_id"])
            self.assertIn("unknown-route", route["fail_closed_conditions"])
            self.assertIn("capability-mismatch", route["fail_closed_conditions"])
            self.assertIn("fallback-not-allowlisted", route["fail_closed_conditions"] or ["not-required"])

    def test_t_route_matrix_visibility_projection_and_direction(self):
        self.assertEqual(self.matrix["projection_policy"]["declassification"], "forbidden")
        for route in self.routes.values():
            self.assertTrue(set(route["input_visibility"]) <= VISIBILITIES, route["route_id"])
            wire = route["wire_projection"]
            self.assertEqual(wire["source_visibility"], route["input_visibility"], route["route_id"])
            self.assertEqual(wire["sent_visibility"], route["input_visibility"], route["route_id"])
            self.assertEqual(wire["declassification"], "forbidden", route["route_id"])
            self.assertEqual(wire["byte_selection"], "exact-allowlisted-projection", route["route_id"])
            self.assertRegex(wire["sent_bytes_digest"], WIRE_TOKEN, route["route_id"])
            self.assertNotEqual(wire["sent_bytes_digest"], route["golden_fingerprint"], route["route_id"])
            self.assertEqual(bytes.fromhex(wire["sample_bytes_hex"]), ("watari-wire-sample-v1:" + route["route_id"] + "\n").encode())
            self.assertEqual(set(route["direction"]), {"egress", "ingress"}, route["route_id"])
            self.assertIn("enabled", route["direction"]["egress"])
            self.assertIn("enabled", route["direction"]["ingress"])
            self.assertFalse(route["direction"]["ingress"]["provider_output_as_primary_evidence"])

    def test_t_route_matrix_openrouter_closed_capabilities(self):
        route = self.routes["route.pi.openrouter.low-risk-utility.v1"]
        self.assertEqual(set(route["capability_set"]), CAPABILITY_KEYS)
        for key in ("mount", "retrieval", "shell", "file", "project", "external_write"):
            self.assertEqual(route["capability_set"][key], "deny", key)
        self.assertEqual(route["capability_set"]["process"], "allow:bounded-child-process")
        self.assertEqual(route["capability_set"]["network"], "allow:exact-provider-endpoint")
        for forbidden in ("private.memory", "raw.connector.data", "credential.value", "canonical.event"):
            self.assertIn(forbidden, route["forbidden_data"])
        self.assertFalse(route["dream"])
        self.assertIn("not-model-input", route["credential_reference_class"])

    def test_t_route_matrix_receipt_and_connector_provenance(self):
        receipt_ids = [route_id for route_id in self.routes if route_id.startswith("route.session-receipt")]
        for route_id in receipt_ids:
            receipt = self.routes[route_id]["session_receipt"]
            self.assertTrue(receipt["required"], route_id)
            for key in ("session_lineage", "watari_launch_attestation", "origin_route_model_policy", "role_provenance"):
                self.assertNotEqual(receipt[key], "not-applicable", route_id)
            self.assertEqual(receipt["primary_evidence_roles"], ["user"], route_id)
            self.assertEqual(receipt["provider_output_status"], "unverified-context", route_id)
            self.assertEqual(self.routes[route_id]["origin_policy"]["primary_evidence_roles"], ["user"])
            self.assertFalse(self.routes[route_id]["origin_policy"]["provider_output_primary_evidence"])
        connector = self.routes["route.connector.read-only.v1"]["connector_contract"]
        self.assertTrue(connector["required"])
        self.assertEqual(connector["connector_instance_id_policy"], "opaque-non-PII")
        self.assertNotRegex(connector["connector_instance_id"], r"[/@\\]|\.\.")
        self.assertEqual(connector["source_policy"], "enabled-read-only")
        self.assertEqual(connector["allowed_method_paths"], ["GET /approved-scope/**"])
        self.assertTrue(all(not path.startswith(("POST", "PUT", "PATCH", "DELETE")) for path in connector["allowed_method_paths"]))
        self.assertRegex(connector["contract_digest"], CONNECTOR_TOKEN)
        self.assertTrue(connector["read_only"])

    def test_t_route_matrix_context_selection_and_d001_coverage(self):
        selection = self.matrix["context_selection"]
        self.assertEqual(selection["selection_key"], "route_id")
        self.assertEqual(selection["multi_match"], "reject")
        self.assertEqual(selection["implicit_default"], "deny")
        self.assertEqual(selection["approved_project_layer"], "required-digest-root-scope")
        self.assertEqual(selection["changed_project_layer"], "reapproval-required")
        covered = {trace for route in self.routes.values() for trace in route["d001_trace"]}
        self.assertTrue({"MX-001", "MX-002", "MX-003", "MX-004", "MX-005"} <= covered)
        for route in self.routes.values():
            project = route["project_layer_policy"]
            self.assertTrue(project["approved_digest_required"])
            self.assertTrue(project["root_scope_required"])
            self.assertEqual(project["auto_discovery"], "deny")
            self.assertEqual(project["model_override"], "deny")

    def _validate_closed(self, matrix):
        top = {"schema_version", "visibility_values", "unknown_policy", "provider_output_default_trust", "route_policy_revision", "route_policy_digest", "capability_values", "fallback_values", "retention_zdr_values", "context_selection", "mutation_policy", "projection_policy", "connector_instance_policy", "session_receipt_schema", "test_vectors", "routes"}
        assert_exact_keys(self, matrix, top, "top schema")
        self.assertEqual(matrix["visibility_values"], ["local-only", "trusted-model", "low-risk-model"])
        self.assertEqual(matrix["unknown_policy"], "fail-closed")
        self.assertEqual(matrix["provider_output_default_trust"], "unverified-context")
        self.assertEqual(matrix["fallback_values"], ["disabled"])
        self.assertEqual(matrix["route_policy_revision"], "D003.route-policy.v1")
        self.assertRegex(matrix["route_policy_digest"], ROUTE_TOKEN)
        self.assertEqual(matrix["route_policy_digest"], route_policy_digest(matrix, self.d003))
        self.assertEqual(matrix["route_policy_digest"], EXPECTED_POLICY_DIGEST)
        self.assertIsInstance(matrix["routes"], list)
        self.assertIsInstance(matrix["capability_values"], list)
        self.assertIsInstance(matrix["retention_zdr_values"], list)
        assert_exact_keys(self, matrix["session_receipt_schema"], {"schema_version", "turn_schema", "required_fields", "role_values", "source_values", "primary_evidence_rule", "provider_ingress_user", "role_source_map"}, "session schema")
        self.assertEqual(matrix["session_receipt_schema"]["schema_version"], "watari.session-receipt.v1")
        self.assertEqual(matrix["session_receipt_schema"]["turn_schema"], "watari.turn-receipt.v1")
        self.assertEqual(matrix["session_receipt_schema"]["required_fields"], ["bytes_digest", "role", "source", "session_lineage_digest", "watari_launch_attestation_digest", "origin_route_provider_model_policy_digest"])
        self.assertEqual(matrix["session_receipt_schema"]["role_values"], ["user", "assistant", "tool", "system", "provider"])
        self.assertEqual(matrix["session_receipt_schema"]["source_values"], ["local-user-turn", "local-assistant-turn", "local-tool-turn", "local-system-turn", "provider-output"])
        self.assertEqual(matrix["session_receipt_schema"]["role_source_map"], ROLE_SOURCE)
        self.assertEqual(matrix["session_receipt_schema"]["primary_evidence_rule"], "local-user-turn-only")
        self.assertEqual(matrix["session_receipt_schema"]["provider_ingress_user"], "deny")
        assert_exact_keys(self, matrix["context_selection"], {"selection_key", "multi_match", "implicit_default", "approved_project_layer", "changed_project_layer"}, "context selection")
        self.assertEqual(matrix["context_selection"], {"selection_key": "route_id", "multi_match": "reject", "implicit_default": "deny", "approved_project_layer": "required-digest-root-scope", "changed_project_layer": "reapproval-required"})
        assert_exact_keys(self, matrix["connector_instance_policy"], {"identifier_class", "forbidden_fields", "source_policy_digest"}, "connector instance policy")
        self.assertEqual(matrix["connector_instance_policy"]["identifier_class"], "opaque-non-PII")
        assert_exact_keys(self, matrix["test_vectors"], {"excluded_paths", "wire_domain", "receipt_domains", "connector_domain", "routes", "receipts"}, "test vectors")
        self.assertEqual(matrix["test_vectors"]["excluded_paths"], ["route_policy_digest", "routes[*].route_policy_digest", "test_vectors", "routes[*].golden_fingerprint", "routes[*].wire_projection.sent_bytes_digest", "routes[*].wire_projection.sample_bytes_digest", "routes[*].session_receipt.bytes_digest", "routes[*].session_receipt.session_lineage_digest", "routes[*].session_receipt.watari_launch_attestation_digest", "routes[*].session_receipt.origin_route_provider_model_policy_digest", "routes[*].connector_contract.contract_digest"])
        self.assertEqual(matrix["unknown_policy"], "fail-closed")
        self.assertEqual(set(matrix["mutation_policy"]), MUTATION_KEYS)
        self.assertTrue(all(value == "deny" for value in matrix["mutation_policy"].values()))
        self.assertEqual(matrix["projection_policy"], {"wire_bytes": "exact-allowlisted-projection", "source_visibility_required": True, "sent_visibility_required": True, "declassification": "forbidden", "visibility_elevation": "reject"})
        self.assertEqual(set(route["route_id"] for route in matrix["routes"]), EXPECTED_ROUTE_IDS)
        for rid, role_vectors in matrix["test_vectors"]["receipts"].items():
            self.assertIn(rid, EXPECTED_ROUTE_IDS)
            self.assertEqual(set(role_vectors), {"user", "assistant", "tool", "system"})
            route = next(route for route in matrix["routes"] if route["route_id"] == rid)
            for role, vector in role_vectors.items():
                assert_exact_keys(self, vector, {"observed_bytes_hex", "expected_session_lineage", "expected_launch_attestation", "expected_provider_id", "expected_model_id", "receipt"}, rid + ":" + role)
                literal = EXPECTED_RECEIPT_GOLDENS[rid][role]
                receipt = vector["receipt"]
                self.assertEqual((vector["observed_bytes_hex"], vector["expected_session_lineage"], vector["expected_launch_attestation"], vector["expected_provider_id"], vector["expected_model_id"], receipt["bytes_digest"], receipt["session_lineage_digest"], receipt["watari_launch_attestation_digest"], receipt["origin_route_provider_model_policy_digest"], receipt["primary_evidence"]), literal, rid + ":" + role)
                self.assertEqual(turn_receipt_errors(vector["receipt"], observed_bytes=bytes.fromhex(vector["observed_bytes_hex"]), observed_role=role, observed_source=ROLE_SOURCE[role], expected_route_id=rid, expected_session_lineage=vector["expected_session_lineage"], expected_launch_attestation=vector["expected_launch_attestation"], expected_provider_id=vector["expected_provider_id"], expected_model_id=vector["expected_model_id"], expected_route_policy_digest=matrix["route_policy_digest"], d003=self.d003), set(), rid + ":" + role)
                self.assertEqual(vector["expected_provider_id"], route["provider_id"])
                self.assertEqual(vector["expected_model_id"], route["model_id"])
        route_keys = {"route_id", "caller_runtime", "provider_model_class", "provider_id", "model_id", "endpoint_id", "input_visibility", "allowed_projection", "forbidden_data", "network_endpoint_class", "credential_reference_class", "credential_scope", "fallback_policy", "retention_zdr", "output_trust", "canonical_write", "dream", "sandbox_class", "route_policy_revision", "route_policy_digest", "golden_fingerprint", "capability_set", "project_layer_policy", "wire_projection", "direction", "session_receipt", "connector_contract", "origin_policy", "fail_closed_conditions", "d001_trace"}
        for route in matrix["routes"]:
            self.assertIsInstance(route, dict, "route")
            rid = route["route_id"]
            assert_exact_keys(self, route, route_keys, rid)
            provider, model, endpoint, scope, visibility, projection = EXACT[rid]
            self.assertEqual((route["provider_id"], route["model_id"], route["endpoint_id"], route["credential_scope"], route["input_visibility"][0], route["allowed_projection"]), (provider, model, endpoint, scope, visibility, projection), rid)
            self.assertEqual(route["route_policy_digest"], matrix["route_policy_digest"])
            for field in ("route_id", "caller_runtime", "provider_model_class", "provider_id", "model_id", "endpoint_id", "credential_scope", "sandbox_class"):
                self.assertIsInstance(route[field], str, rid)
            self.assertIsInstance(route["input_visibility"], list, rid)
            self.assertIsInstance(route["allowed_projection"], list, rid)
            self.assertIsInstance(route["forbidden_data"], list, rid)
            self.assertIsInstance(route["fail_closed_conditions"], list, rid)
            self.assertIsInstance(route["d001_trace"], list, rid)
            self.assertIsInstance(route["canonical_write"], bool, rid)
            self.assertIsInstance(route["dream"], bool, rid)
            expected_vectors = EXPECTED_VECTORS[rid]
            self.assertEqual(tuple(matrix["test_vectors"]["routes"][rid].values()), expected_vectors)
            self.assertEqual((route["golden_fingerprint"], route["wire_projection"]["sent_bytes_digest"], route["connector_contract"]["contract_digest"]), (expected_vectors[0], expected_vectors[1], expected_vectors[5]), rid)
            self.assertRegex(route["golden_fingerprint"], CONTEXT_TOKEN)
            exact_bytes = bytes.fromhex(route["wire_projection"]["sample_bytes_hex"])
            self.assertEqual(route["wire_projection"]["sent_bytes_digest"], typed_digest("watari-wire-bytes-v1:", "wire-bytes/v1", exact_bytes, self.d003), rid)
            connector_body = {key: value for key, value in route["connector_contract"].items() if key != "contract_digest"}
            self.assertEqual(route["connector_contract"]["contract_digest"], typed_digest("watari-connector-v1:", "connector-contract/v1", connector_body, self.d003), rid)
            self.assertEqual(route["fallback_policy"], "disabled")
            self.assertEqual(route["sandbox_class"], "mandatory-external-runtime-no-state-key-mount")
            self.assertFalse(route["canonical_write"])
            self.assertNotIn("allow:any", json.dumps(route))
            self.assertIn("unknown-route", route["fail_closed_conditions"])
            self.assertIn("capability-mismatch", route["fail_closed_conditions"])
            self.assertIn("fallback-not-allowlisted", route["fail_closed_conditions"])
            assert_exact_keys(self, route["retention_zdr"], {"retention_class", "zero_data_retention", "fallback_retention"}, rid)
            assert_exact_keys(self, route["capability_set"], CAPABILITY_KEYS, rid)
            self.assertEqual(route["capability_set"]["external_write"], "deny")
            assert_exact_keys(self, route["wire_projection"], {"source_visibility", "sent_visibility", "allowed_projection", "byte_selection", "declassification", "sent_bytes_digest", "sample_bytes_hex", "sample_bytes_digest"}, rid)
            assert_exact_keys(self, route["direction"], {"egress", "ingress"}, rid)
            assert_exact_keys(self, route["direction"]["egress"], {"enabled", "endpoint_id", "allowed_visibility", "fallback_policy", "capture"}, rid)
            assert_exact_keys(self, route["direction"]["ingress"], {"enabled", "accepted_output_trust", "accepted_roles", "provider_output_as_primary_evidence", "canonical_write"}, rid)
            assert_exact_keys(self, route["session_receipt"], {"required", "session_lineage", "watari_launch_attestation", "origin_route_model_policy", "role_provenance", "primary_evidence_roles", "provider_output_status", "schema_version", "turn_schema", "source_binding", "role_capture", "source_capture"}, rid)
            connector_keys = {"required", "connector_instance_id_policy", "connector_instance_id", "source_policy", "allowed_method_paths", "forbidden_method_paths", "credential_scope", "contract_digest", "read_only"}
            if rid == "route.connector.read-only.v1": connector_keys |= {"source_policy_digest", "checkpoint_lineage_digest"}
            assert_exact_keys(self, route["connector_contract"], connector_keys, rid)
            assert_exact_keys(self, route["origin_policy"], {"primary_evidence_roles", "provider_output_primary_evidence", "source_binding"}, rid)
            self.assertTrue(set(route["input_visibility"]) <= VISIBILITIES)
            self.assertEqual(route["wire_projection"]["source_visibility"], route["input_visibility"])
            self.assertEqual(route["wire_projection"]["sent_visibility"], route["input_visibility"])
            self.assertEqual(route["wire_projection"]["allowed_projection"], route["allowed_projection"])
            self.assertEqual(route["wire_projection"]["declassification"], "forbidden")
            self.assertRegex(route["wire_projection"]["sent_bytes_digest"], WIRE_TOKEN)
            self.assertNotEqual(route["wire_projection"]["sent_bytes_digest"], route["golden_fingerprint"])
            self.assertEqual(route["wire_projection"]["sample_bytes_digest"], route["wire_projection"]["sent_bytes_digest"])
            self.assertEqual(route["session_receipt"]["source_binding"], "required")
            self.assertEqual(route["session_receipt"]["session_lineage"], "required" if rid.startswith("route.session-receipt") else "not-applicable")
            self.assertEqual(route["session_receipt"]["watari_launch_attestation"], "required" if rid.startswith("route.session-receipt") else "not-applicable")
            self.assertIsInstance(route["session_receipt"]["role_provenance"], list)
            self.assertTrue(set(route["session_receipt"]["role_provenance"]) <= {"user", "assistant", "tool", "system"})
            self.assertEqual(route["session_receipt"]["primary_evidence_roles"], ["user"])
            self.assertEqual(route["session_receipt"]["provider_output_status"], "unverified-context")
            self.assertEqual(route["origin_policy"]["source_binding"], "required")
            self.assertFalse(route["origin_policy"]["provider_output_primary_evidence"])
            self.assertEqual(route["origin_policy"]["primary_evidence_roles"], ["user"] if rid.startswith("route.session-receipt") or "trusted-dream" in rid else ["evidence"])
            self.assertEqual(route["direction"]["egress"]["endpoint_id"], route["endpoint_id"])
            self.assertEqual(route["direction"]["egress"]["allowed_visibility"], route["input_visibility"])
            self.assertEqual(route["direction"]["ingress"]["accepted_roles"], ["user", "assistant", "tool", "system"] if rid.startswith("route.session-receipt") else ["evidence"])
            is_receipt = rid.startswith("route.session-receipt")
            self.assertEqual(route["direction"]["egress"]["enabled"], not is_receipt)
            self.assertEqual(route["session_receipt"]["required"], is_receipt)
            self.assertEqual(route["session_receipt"]["role_capture"], "provider" if rid == "route.connector.read-only.v1" else "observed-role")
            self.assertEqual(route["session_receipt"]["source_capture"], "provider-output" if rid == "route.connector.read-only.v1" else "observed-source")
            self.assertIn(route["retention_zdr"]["zero_data_retention"], {"required", "not-applicable"})
            connector = route["connector_contract"]
            self.assertIsInstance(connector["allowed_method_paths"], list)
            self.assertEqual(connector["allowed_method_paths"], ["GET /approved-scope/**"] if rid == "route.connector.read-only.v1" else [])
            self.assertEqual(connector["source_policy"], "enabled-read-only" if rid == "route.connector.read-only.v1" else "not-applicable")
            self.assertEqual(connector["credential_scope"], route["credential_scope"] if rid == "route.connector.read-only.v1" else "not-applicable")
            self.assertTrue(connector["read_only"])
            if rid == "route.connector.read-only.v1":
                self.assertRegex(connector["source_policy_digest"], r"^watari-source-policy-v1:[0-9a-f]{64}$")
                self.assertRegex(connector["checkpoint_lineage_digest"], r"^watari-checkpoint-v1:[0-9a-f]{64}$")
                self.assertEqual(connector["source_policy_digest"], typed_digest("watari-source-policy-v1:", "source-policy/v1", {"route_id": rid, "source_policy": connector["source_policy"], "allowed_method_paths": connector["allowed_method_paths"], "credential_scope": connector["credential_scope"]}, self.d003))
                self.assertEqual(connector["checkpoint_lineage_digest"], typed_digest("watari-checkpoint-v1:", "checkpoint-lineage/v1", {"route_id": rid, "checkpoint_lineage": "required"}, self.d003))
            self.assertEqual(set(route["d001_trace"]), TRACE_FULL[rid])

    def _assert_rejected(self, candidate):
        with self.assertRaises(AssertionError):
            self._validate_closed(candidate)

    def test_t_route_matrix_real_d003_vectors_and_closed_schema(self):
        self._validate_closed(self.matrix)
        policy = self.matrix["route_policy_digest"]
        for route in self.matrix["routes"]:
            manifest = {"schema_version": 1, "context_schema": "watari.context/v1", "projection_kind": "effective", "policy_revision": self.matrix["route_policy_revision"], "profile_revision": "profile.v1", "memory_revision": "memory.v1", "project_revision": "project.v1", "visibility": route["input_visibility"][0], "route_policy_digest": policy}
            context = bytes.fromhex(route["wire_projection"]["sample_bytes_hex"])
            self.assertEqual(self.d003.context_fingerprint("effective", manifest, context), route["golden_fingerprint"])

    def test_t_turn_receipt_verifier_accepts_four_roles_and_provider_output(self):
        for route_id, role_vectors in self.matrix["test_vectors"]["receipts"].items():
            route = self.routes[route_id]
            for role in ("user", "assistant", "tool", "system"):
                vector = role_vectors[role]
                errors = turn_receipt_errors(vector["receipt"], observed_bytes=bytes.fromhex(vector["observed_bytes_hex"]), observed_role=role, observed_source=ROLE_SOURCE[role], expected_route_id=route_id, expected_session_lineage=vector["expected_session_lineage"], expected_launch_attestation=vector["expected_launch_attestation"], expected_provider_id=vector["expected_provider_id"], expected_model_id=vector["expected_model_id"], expected_route_policy_digest=self.matrix["route_policy_digest"], d003=self.d003)
                self.assertEqual(errors, set(), (route_id, role))
                self.assertEqual(vector["receipt"]["primary_evidence"], role == "user")
            provider_bytes = b"provider-output-bytes\n"
            provider_lineage = "provider-lineage"
            provider_attestation = "provider-attestation"
            provider = {"schema_version": "watari.turn-receipt.v1", "turn_id": "turn:provider", "route_id": route_id, "bytes_digest": typed_digest("watari-wire-bytes-v1:", "wire-bytes/v1", provider_bytes, self.d003), "role": "provider", "source": "provider-output", "session_lineage_digest": typed_digest("watari-lineage-v1:", "session-lineage/v1", {"route_id": route_id, "lineage": provider_lineage}, self.d003), "watari_launch_attestation_digest": typed_digest("watari-attestation-v1:", "watari-attestation/v1", {"route_id": route_id, "attestation": provider_attestation, "caller_runtime": "session-receipt"}, self.d003), "origin_route_provider_model_policy_digest": typed_digest("watari-origin-v1:", "origin-route/v1", {"route_id": route_id, "provider_id": route["provider_id"], "model_id": route["model_id"], "route_policy_digest": self.matrix["route_policy_digest"]}, self.d003), "primary_evidence": False}
            self.assertEqual(turn_receipt_errors(provider, observed_bytes=provider_bytes, observed_role="provider", observed_source="provider-output", expected_route_id=route_id, expected_session_lineage=provider_lineage, expected_launch_attestation=provider_attestation, expected_provider_id=route["provider_id"], expected_model_id=route["model_id"], expected_route_policy_digest=self.matrix["route_policy_digest"], d003=self.d003), set())

    def test_t_turn_receipt_verifier_rejects_forgery_recomputed_digests_and_malformed(self):
        vector = self.matrix["test_vectors"]["receipts"]["route.session-receipt.claude.v1"]["assistant"]
        forged = copy.deepcopy(vector["receipt"])
        observed = bytes.fromhex(vector["observed_bytes_hex"])
        forged["role"] = "user"
        forged["source"] = "local-user-turn"
        forged["primary_evidence"] = True
        forged["bytes_digest"] = typed_digest("watari-wire-bytes-v1:", "wire-bytes/v1", observed, self.d003)
        forged["session_lineage_digest"] = typed_digest("watari-lineage-v1:", "session-lineage/v1", {"route_id": vector["receipt"]["route_id"], "lineage": vector["expected_session_lineage"]}, self.d003)
        forged["watari_launch_attestation_digest"] = typed_digest("watari-attestation-v1:", "watari-attestation/v1", {"route_id": vector["receipt"]["route_id"], "attestation": vector["expected_launch_attestation"], "caller_runtime": "session-receipt"}, self.d003)
        forged["origin_route_provider_model_policy_digest"] = typed_digest("watari-origin-v1:", "origin-route/v1", {"route_id": vector["receipt"]["route_id"], "provider_id": vector["expected_provider_id"], "model_id": vector["expected_model_id"], "route_policy_digest": self.matrix["route_policy_digest"]}, self.d003)
        errors = turn_receipt_errors(forged, observed_bytes=observed, observed_role="assistant", observed_source="local-assistant-turn", expected_route_id=vector["receipt"]["route_id"], expected_session_lineage=vector["expected_session_lineage"], expected_launch_attestation=vector["expected_launch_attestation"], expected_provider_id=vector["expected_provider_id"], expected_model_id=vector["expected_model_id"], expected_route_policy_digest=self.matrix["route_policy_digest"], d003=self.d003)
        self.assertTrue({"role", "source", "primary_evidence"} <= errors)
        for field, bad in (("bytes_digest", None), ("role", 1), ("source", []), ("session_lineage_digest", None), ("primary_evidence", "true")):
            malformed = copy.deepcopy(vector["receipt"]); malformed[field] = bad
            errors = turn_receipt_errors(malformed, observed_bytes=observed, observed_role="assistant", observed_source="local-assistant-turn", expected_route_id=vector["receipt"]["route_id"], expected_session_lineage=vector["expected_session_lineage"], expected_launch_attestation=vector["expected_launch_attestation"], expected_provider_id=vector["expected_provider_id"], expected_model_id=vector["expected_model_id"], expected_route_policy_digest=self.matrix["route_policy_digest"], d003=self.d003)
            self.assertTrue(errors, field)
        unknown = copy.deepcopy(vector["receipt"]); unknown["unknown"] = True
        self.assertTrue(turn_receipt_errors(unknown, observed_bytes=observed, observed_role="assistant", observed_source="local-assistant-turn", expected_route_id=vector["receipt"]["route_id"], expected_session_lineage=vector["expected_session_lineage"], expected_launch_attestation=vector["expected_launch_attestation"], expected_provider_id=vector["expected_provider_id"], expected_model_id=vector["expected_model_id"], expected_route_policy_digest=self.matrix["route_policy_digest"], d003=self.d003))

    def test_t_route_matrix_exact_excluded_path_matching(self):
        base = route_policy_digest(self.matrix, self.d003)
        excluded = copy.deepcopy(self.matrix); excluded["routes"][0]["wire_projection"]["sent_bytes_digest"] += "x"
        self.assertEqual(route_policy_digest(excluded, self.d003), base)
        excluded = copy.deepcopy(self.matrix); excluded["routes"][0]["route_policy_digest"] += "x"
        self.assertEqual(route_policy_digest(excluded, self.d003), base)
        included = copy.deepcopy(self.matrix); included["session_receipt_schema"]["golden_fingerprint"] = "policy-leaf"
        self.assertNotEqual(route_policy_digest(included, self.d003), base)
        included = copy.deepcopy(self.matrix); included["routes"][0]["connector_contract"]["golden_fingerprint"] = "policy-leaf"
        self.assertNotEqual(route_policy_digest(included, self.d003), base)

    def test_t_route_matrix_negative_mutation_corpus(self):
        mutations = []
        candidate = copy.deepcopy(self.matrix); candidate["unknown"] = True; mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix); candidate["routes"][0]["provider_id"], candidate["routes"][1]["provider_id"] = candidate["routes"][1]["provider_id"], candidate["routes"][0]["provider_id"]; mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix); candidate["routes"][2]["capability_set"]["network"] = "allow:any"; mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix); candidate["routes"][0]["sandbox_class"] = "none"; mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix); candidate["routes"][2]["allowed_projection"].append("private.memory"); mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix); candidate["routes"][3]["direction"]["egress"]["enabled"] = True; mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix); candidate["routes"][0]["retention_zdr"]["zero_data_retention"] = "disabled"; mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix); candidate["routes"][0]["origin_policy"]["source_binding"] = "disabled"; mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix); candidate["routes"][3]["session_receipt"]["role"] = "assistant"; mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix); candidate["routes"][1]["direction"]["ingress"]["accepted_roles"] = ["user"]; mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix); candidate["routes"][6]["connector_contract"]["allowed_method_paths"] = ["POST /approved-scope/**"]; mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix); candidate["routes"][6]["connector_contract"]["checkpoint_lineage_digest"] += "x"; mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix); candidate["routes"][0]["d001_trace"].append("UNKNOWN"); mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix); candidate["routes"][0]["session_receipt"]["role_provenance"] = "user"; mutations.append(candidate)
        for malformed in (None, "routes", 1, {}):
            candidate = copy.deepcopy(self.matrix); candidate["routes"] = malformed; mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix); candidate["routes"][0]["capability_set"] = "deny"; mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix); candidate["routes"][0]["wire_projection"] = None; mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix); candidate["routes"][0]["direction"]["ingress"]["accepted_roles"] = "user"; mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix); candidate["routes"][6]["connector_contract"]["allowed_method_paths"] = 1; mutations.append(candidate)
        candidate = copy.deepcopy(self.matrix); candidate["routes"][0]["origin_policy"] = None; mutations.append(candidate)
        for forged_role in ("assistant", "system", "tool", "provider"):
            candidate = copy.deepcopy(self.matrix); candidate["routes"][3]["session_receipt"]["role"] = forged_role; mutations.append(candidate)
        for candidate in mutations:
            self._assert_rejected(candidate)

    def test_t_route_matrix_mutation_changes_policy_vector_and_user_provenance(self):
        candidate = copy.deepcopy(self.matrix)
        candidate["routes"][0]["allowed_projection"].append("unapproved.extra")
        self.assertNotEqual(route_policy_digest(candidate, self.d003), self.matrix["route_policy_digest"])
        for route in self.matrix["routes"]:
            if route["route_id"].startswith("route.session-receipt"):
                self.assertEqual(route["session_receipt"]["role_capture"], "observed-role")
                self.assertEqual(route["session_receipt"]["source_capture"], "observed-source")
            else:
                self.assertNotIn("user", route["direction"]["ingress"]["accepted_roles"])
                self.assertNotEqual(route["session_receipt"]["role_capture"], "user")

    def test_t_route_matrix_nested_schema_and_duplicate_members(self):
        for route in self.matrix["routes"]:
            rid = route["route_id"]
            assert_exact_keys(self, route["retention_zdr"], {"retention_class", "zero_data_retention", "fallback_retention"}, rid)
            assert_exact_keys(self, route["capability_set"], CAPABILITY_KEYS, rid)
            assert_exact_keys(self, route["project_layer_policy"], {"approved_digest_required", "root_scope_required", "auto_discovery", "model_override"}, rid)
            assert_exact_keys(self, route["wire_projection"], {"source_visibility", "sent_visibility", "allowed_projection", "byte_selection", "declassification", "sent_bytes_digest", "sample_bytes_hex", "sample_bytes_digest"}, rid)
            assert_exact_keys(self, route["direction"]["egress"], {"enabled", "endpoint_id", "allowed_visibility", "fallback_policy", "capture"}, rid)
            assert_exact_keys(self, route["direction"]["ingress"], {"enabled", "accepted_output_trust", "accepted_roles", "provider_output_as_primary_evidence", "canonical_write"}, rid)
            assert_exact_keys(self, route["session_receipt"], {"required", "session_lineage", "watari_launch_attestation", "origin_route_model_policy", "role_provenance", "primary_evidence_roles", "provider_output_status", "schema_version", "turn_schema", "source_binding", "role_capture", "source_capture"}, rid)
            connector_keys = {"required", "connector_instance_id_policy", "connector_instance_id", "source_policy", "allowed_method_paths", "forbidden_method_paths", "credential_scope", "contract_digest", "read_only"}
            if rid == "route.connector.read-only.v1": connector_keys |= {"source_policy_digest", "checkpoint_lineage_digest"}
            assert_exact_keys(self, route["connector_contract"], connector_keys, rid)
            assert_exact_keys(self, route["origin_policy"], {"primary_evidence_roles", "provider_output_primary_evidence", "source_binding"}, rid)
        def duplicate_reject(pairs):
            seen = set()
            for key, _ in pairs:
                if key in seen:
                    raise ValueError("duplicate JSON member")
                seen.add(key)
            return dict(pairs)
        with self.assertRaises(ValueError):
            json.loads('{"route_id":"a","route_id":"b"}', object_pairs_hook=duplicate_reject)

    def test_t_route_matrix_every_included_policy_leaf_changes_digest(self):
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
                self.fail(f"unhandled policy leaf type at {path}: {type(old)}")
            self.assertNotEqual(route_policy_digest(candidate, self.d003), self.matrix["route_policy_digest"], path)


if __name__ == "__main__":
    unittest.main()
