# Watari CLI product repository

This repository contains the installable Watari CLI product: a memory engine
(`src/watari_cli/`) and a bundled persona skill (`skills/watari/`). The memory
schema is specified in `skills/watari/SCHEMA.md`.

## Safety boundary

- Never modify `~/.claude`, `~/.codex`, `~/.pi`, the live Watari memory tree,
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
