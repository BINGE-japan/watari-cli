# Watari CLI

Watari CLI is a pull-only personal-agent harness. It is intended to appear only
when `watari` is invoked while keeping user-owned profile and memory portable
across supported AI runtimes.

Status: repository bootstrap complete; product implementation has not started.

The frozen implementation and migration specification is stored in
[`docs/baseline/implementation-plan.md`](docs/baseline/implementation-plan.md).
The bounded dependency graph is stored in
[`docs/baseline/issue-dag.md`](docs/baseline/issue-dag.md).
The immutable baseline remains authoritative except for exact fields activated
through the owner-approved, digest-bound
[`issue-dag overlay registry`](docs/governance/issue-dag-overlays.jsonl).

This repository contains product code and synthetic fixtures only. User state,
runtime sessions, credentials, and recovery material are separate artifacts and
must not be committed here.
