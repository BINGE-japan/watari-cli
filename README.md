# Watari CLI

Watari CLI is a pull-only personal-agent harness. It is intended to appear only
when `watari` is invoked while keeping user-owned profile and memory portable
across supported AI runtimes.

## Getting started

    uv tool install .
    watari install
    watari chat

`watari install` sets up (or adopts an existing cartridge, or restores one
from a git backup) a memory cartridge and remembers where it lives. `watari
chat` then launches the bundled skill inside your AI runtime (Pi by default;
pass `--show` to print the command instead of running it, or extra arguments
to pass straight through to the runtime).

Run `watari --help`, or `watari <subcommand> --help`, for the full set of
subcommands: status/host/dream/recall/ingest/audit/regen/init/install/chat/
connector.

Memory only grows on demand by default (saying "夢を見て" in a conversation,
or running `watari dream` by hand). To reproduce the original's automatic
nightly growth, see
[`docs/headless-dream.md`](docs/headless-dream.md) for scheduling that
headless, outside the CLI.

## Your own reference material

The original hand-rolled Watari kept a `knowledge/` folder of the user's own
reference notes (style guides, glossaries, and the like) that the assistant
read on demand for specific topics. watari-cli does not ship or hardcode a
directory for this — keep such material wherever suits you (a synced notes
vault, a project's own docs, ...), and let Watari know where: declare it as a
`connector` (`watari connector add`) if it should be scanned automatically
during dream, or just mention the location in conversation so it lands as an
ordinary recorded fact through the normal ingest flow.

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
