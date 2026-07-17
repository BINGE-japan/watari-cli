# Watari runtime adapter contract v1

Status: D006 design freeze
Issue: D006
Base SHA: `178629bb4d1b7a1c5d7c08b280d12d62f2814118`
Dependencies: D002 `c0a9fc211741135ee093c19219c9a16bb426c4eb`; D005 `178629bb4d1b7a1c5d7c08b280d12d62f2814118`

This contract separates a runtime adapter from Watari identity and state. Unknown or additional
schema members, versions, operations, routes, capabilities, and evidence fail closed. An adapter
must resolve route identity from the trusted D005 registry; model input cannot select or alter it.

```json
{
  "schema_version": "watari.runtime-contract.v1",
  "unknown_policy": "fail-closed",
  "schemas": {
    "adapter": "watari.runtime-adapter.v1",
    "request": "watari.runtime-request.v1",
    "capability": "watari.runtime-capability.v1",
    "qualification": "watari.runtime-qualification.v1",
    "launch_receipt": "watari.runtime-launch-receipt.v1",
    "explain": "watari.runtime-explain.v1"
  },
  "operations": ["detect", "qualify", "launch_interactive", "run_structured", "session_source", "memory_tools", "explain"],
  "route_binding": {
    "registry_schema": "watari.route-matrix.v1",
    "policy_revision": "D003.route-policy.v1",
    "policy_digest": "watari-route-policy-v1:98c104e8266fb194a5c59d3d8e67e23fa87c9631249c50a13e9e48bf021be0e4",
    "identity_fields": ["route_id", "caller_runtime", "provider_model_class", "provider_id", "model_id", "endpoint_id", "network_endpoint_class", "credential_scope", "fallback_policy", "retention_zdr", "route_policy_digest"],
    "identity_source": "trusted-registry-only",
    "fallback": "disabled"
  },
  "auth": {
    "fields": ["provider_id", "reference_id", "scope", "state", "transport"],
    "transport": "bounded-fd-or-pipe",
    "forbidden": ["value", "argv", "environment", "global-copy", "log"]
  },
  "context": {
    "schema": "watari.context/v1",
    "fields": ["route_policy_digest", "visibility", "canonical_fingerprint", "effective_fingerprint", "transport"],
    "transports": ["stdin", "owner-private-file"],
    "argv": "deny",
    "visibility": "route-bound"
  },
  "project_layer": {
    "modes": ["none", "approved"],
    "approved_fields": ["digest", "root_scope_digest"],
    "changed": "reapproval-required",
    "auto_discovery": "deny",
    "model_override": "deny",
    "runtime_system_digest": "separate-required"
  },
  "capabilities": {
    "fields": ["mount", "retrieval", "shell", "file", "project", "external_write", "process", "network"],
    "source": "trusted-route-only",
    "model_escalation": "deny",
    "sandbox_evidence": "required-for-supported"
  },
  "qualification": {"support_status": ["unsupported", "supported"], "supported_requires": ["observed-runtime-evidence", "qualified-sandbox-evidence"], "declaration_only": "unsupported"},
  "operation_semantics": {
    "interactive": ["pty", "cwd", "ctrl-c", "exit-code", "child-cleanup"],
    "structured": ["bounded-input", "bounded-output", "timeout", "strict-schema", "unverified-output"],
    "session_source": ["watari-owned-root", "lineage", "receipt"],
    "memory_tools": ["memory.search", "memory.get", "memory.explain", "read-only", "session-scoped", "route-bound"]
  },
  "receipt": {
    "required_bindings": ["runtime_id", "adapter_version", "route_id", "provider_id", "model_id", "endpoint_id", "route_policy_digest", "auth_reference_digest", "canonical_fingerprint", "effective_fingerprint", "project_digest", "runtime_system_digest", "capability_digest", "session_lineage_digest", "launch_attestation_digest"],
    "verification_status": "structural-binding-only",
    "structural_tests_do_not_qualify_runtime": true
  },
  "explain": {
    "fields": ["runtime_id", "adapter_version", "redacted_argv", "environment_keys", "route_id", "canonical_fingerprint", "effective_fingerprint", "project_digest", "runtime_system_digest", "capability_status"],
    "forbidden": ["secret-value", "context-bytes", "absolute-host-path"],
    "redaction": "required"
  },
  "failure_codes": {"INVALID_SCHEMA": 11, "UNSUPPORTED": 12, "AUTH": 20, "POLICY": 50},
  "open_decisions": ["DEC-OPEN-003", "DEC-OPEN-004"]
}
```

## Conformance and support

`detect` observes an executable and version without claiming support. `qualify` compares observed
flags, isolation, injection, capture, and cleanup with the exact route and capability contract.
Only independently observed runtime evidence plus qualified sandbox evidence may produce
`supported`; declarations and these synthetic structural tests cannot. Until its later O-ticket
and sandbox qualification succeed, every concrete runtime/version/auth combination is
`unsupported` (exit 12).

Interactive launch propagates PTY, cwd, Ctrl-C, child exit, and cleanup. Structured execution has
bounded input/output, timeout, strict output schema, and keeps provider output unverified. Session
roots are Watari-owned; retrieval tools are read-only, session-scoped, and route-bound. Neither
path grants canonical, profile, checkpoint, credential, project, or external-write authority.

Context bytes use stdin or an owner-private temporary file, never argv. Auth is a reference and
scope only; missing, revoked, or mismatched references fail with AUTH or POLICY without fallback.
An approved project layer binds digest and root scope, remains below runtime safety and Watari
rules, and is separate from the runtime system digest. Changed or auto-discovered instructions
require approval before launch.

The launch receipt binds declared inputs structurally. D005 receipts and D006 synthetic fakes are
not evidence that a runtime launched, emitted bytes, isolated credentials, or captured authentic
egress/session data; later runtime and Z001 qualifications own those observations. Open decisions
do not create a trusted OpenRouter route or a public supported-runtime default.
