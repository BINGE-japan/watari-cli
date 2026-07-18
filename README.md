# Watari CLI

Watari CLI is a pull-only personal-agent harness. It is intended to appear only
when `watari` is invoked while keeping user-owned profile and memory portable
across supported AI runtimes.

Status: the `watari` CLI is implemented — memory engine (`src/watari_cli/`) and
bundled persona skill (`src/watari_cli/skill/`, shipped as package data in the
wheel), with subcommands status/host/dream/recall/ingest/audit/regen/init/
install/chat/connector.

The memory schema (log/state model, cursors, and the deterministic folding
rules) is specified in
[`src/watari_cli/skill/SCHEMA.md`](src/watari_cli/skill/SCHEMA.md); the
engine that implements it lives in `src/watari_cli/engine/`. A post-MVP roadmap
of memory ideas is in [`docs/memory-roadmap.md`](docs/memory-roadmap.md).

This repository contains product code and tests only. User state, runtime
sessions, credentials, and recovery material are separate artifacts and must not
be committed here.
