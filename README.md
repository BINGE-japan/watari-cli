# Watari CLI

Watari CLI is a pull-only personal-agent harness. It is intended to appear only
when `watari` is invoked while keeping user-owned profile and memory portable
across supported AI runtimes.

Status: the `watari` CLI is implemented — memory engine (`src/watari_cli/`) and
bundled persona skill (`skills/watari/`), with subcommands status/host/dream/
recall/ingest/audit/regen/init/install/chat.

The memory schema (log/state model, cursors, and the deterministic folding
rules) is specified in [`skills/watari/SCHEMA.md`](skills/watari/SCHEMA.md); the
engine that implements it lives in `src/watari_cli/engine/`. A post-MVP roadmap
of memory ideas is in [`docs/memory-roadmap.md`](docs/memory-roadmap.md).

This repository contains product code and tests only. User state, runtime
sessions, credentials, and recovery material are separate artifacts and must not
be committed here.
