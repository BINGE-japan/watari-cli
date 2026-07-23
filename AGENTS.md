# Watari CLI product repository

**Start with `SPEC.md`** — the project's goal, requirements, scope, current
status, and settled decisions live there, so the intent doesn't have to be
restated each session. This file is the development discipline; `SPEC.md` is
the "what and why."

This repository contains the installable Watari CLI product: a memory engine
(`src/watari_cli/`) and a bundled persona skill (`src/watari_cli/skill/`,
shipped as package data in the wheel). The memory schema is specified in
`src/watari_cli/skill/SCHEMA.md`.

## Safety boundary

- Never modify `~/.claude`, `~/.codex`, `~/.pi`, any live Watari memory tree
  (a real user's `WATARI_HOME` in production use on the development machine),
  schedulers, or external services from ordinary implementation work.
- Use synthetic data only. Never copy credentials, OAuth state, personal
  transcripts, email, calendar, Slack, Linear, or user memory into this repo.
- Network, credentials, live reads, and external writes stay out of the product
  code unless a change explicitly records why they are needed.
- Runtime state belongs below an explicit temporary `WATARI_HOME`; it is never
  committed.

## Implementation discipline

- Add the named failing test first. Do not delete, skip, or weaken tests to make
  an implementation pass.
- Unknown schema, source, runtime, or state versions fail closed.
- Use `uv` for Python tooling. Do not use yarn.
- Keep the shipped code generic and portable. Personal data belongs in the
  user's own `WATARI_HOME` cartridge, not in this repository.
