# Watari CLI

Watari CLI runs **Watari** — your personal agent — on the Pi runtime. `watari
chat` launches a full Watari session (the bundled persona skill plus your own
memory); you talk to Watari for the whole session, not as an overlay that
surfaces on a keyword inside another assistant. Your memory and profile are a
portable, user-owned cartridge (a git repo) kept separate from the shipped
engine — so the engine can be handed to someone else, who then grows their own
Watari.

## Getting started

    uv tool install .
    watari install
    watari chat

`watari install` sets up (or adopts an existing cartridge, or restores one
from a git backup) a memory cartridge and remembers where it lives. `watari
chat` then launches Watari on Pi — the persona is injected as Pi's system prompt
and the memory is read through the `watari` CLI (pass `--show` to print the
command instead of running it, or extra arguments to pass straight through to
Pi). The Pi runtime needs **Node ≥22.19** on PATH; without it Pi fails to
start.

Run `watari --help`, or `watari <subcommand> --help`, for the full set of
subcommands: status/host/dream/recall/ingest/audit/regen/init/install/auth/
chat/connector.

Memory grows automatically: `watari chat` kicks off a background "dream" at
startup that distils recent conversations into the log (you can also say
"夢を見て" in a conversation, or run `watari dream` by hand). A scheduled/headless
variant is in [`docs/headless-dream.md`](docs/headless-dream.md).

## Using Watari on several machines

Point every machine at the same memory cartridge (a git remote) and Watari is
one agent everywhere: memory syncs over git (pulled before each session, pushed
after each write), and your conversations are relayed — user + assistant text
only, never tool output — through a private cloud folder (Google Drive
appDataFolder) so a dream on machine B can pick up what you said on machine A.
Raw transcripts never enter the git history (git can't forget); the cloud relay
is prunable and self-expires. Choose "sync" vs "local only" during `watari
install`. The relay needs a one-time Google OAuth app registration — see
[`docs/google-oauth-setup.md`](docs/google-oauth-setup.md) — after which each
machine logs in with `watari auth` (it takes the client_id/secret once, from a
prompt or `WATARI_GOOGLE_CLIENT_*`, and saves them to `config.json`; `watari
install` runs the same step). Until it is set up, sync is skipped and Watari
runs local-only.

## Connectors: other sources dream should read

For services watari-cli ships a built-in adapter for, `watari connect
<service>` walks you through it end to end: it explains what to open and what
to paste, verifies the credential with a real API call before saving it, and
registers the connector declaration for you. Built-in services so far: Linear
(personal API key), GitHub (fine-grained personal access token), Notion
(internal integration token), Slack (pasted user OAuth token, `xoxp-`, created
from an app manifest), and Chatwork (pasted API token). Run `watari connect`
with no argument for a menu of available services. Dream then reads it
deterministically with `watari connector read <name> [--since TS] [--json]`
(defaults to this machine's saved cursor); the cursor itself only advances via
`watari ingest --advance-ext`, same as every other source. Gmail and Google
Calendar are listed in the menu but not implemented yet (`watari connect
<name>` reports "not supported").

For anything without a built-in adapter — the original hand-rolled Watari's
`knowledge/` folder of reference notes, an Obsidian vault, or any other
tool — declare a custom connector instead: `watari connector add --name <slug>
--scope cloud|local --read "..."` records free-text instructions the agent
follows with its own tools (MCP, etc.) during dream. `watari connector list`
shows both kinds, labelled built-in vs. custom.

Status: the `watari` CLI is implemented — memory engine (`src/watari_cli/`) and
bundled persona skill (`src/watari_cli/skill/`, shipped as package data in the
wheel), with subcommands status/host/dream/recall/ingest/audit/regen/init/
install/auth/chat/connect/connector. The project's goal, scope, current status, and
settled decisions are in [`SPEC.md`](SPEC.md).

The memory schema (log/state model, cursors, and the deterministic folding
rules) is specified in
[`src/watari_cli/skill/SCHEMA.md`](src/watari_cli/skill/SCHEMA.md); the
engine that implements it lives in `src/watari_cli/engine/`. A post-MVP roadmap
of memory ideas is in [`docs/memory-roadmap.md`](docs/memory-roadmap.md).

This repository contains product code and tests only. User state, runtime
sessions, credentials, and recovery material are separate artifacts and must not
be committed here.
