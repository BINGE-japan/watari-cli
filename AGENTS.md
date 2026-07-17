# Watari CLI product repository

This repository contains the installable Watari CLI product. Work follows the
frozen baseline in `docs/baseline/` and its issue DAG.

## Safety boundary

- Never modify `~/.claude`, `~/.codex`, `~/.pi`, the live Watari memory tree,
  schedulers, or external services from ordinary implementation tickets.
- Use synthetic fixtures only. Never copy credentials, OAuth state, personal
  transcripts, email, calendar, Slack, Linear, or BINGE memory into this repo.
- Network, credentials, live reads, and external writes are forbidden unless a
  specific O/C ticket records its exact Authority and approval ID.
- Runtime state belongs below an explicit temporary `WATARI_HOME`; it is never
  committed.

## Implementation discipline

- Complete dependencies before starting a ticket. One ticket has one bounded
  purpose and an independent reviewer.
- Add the named failing test first. Do not delete, skip, or weaken tests to make
  an implementation pass.
- Unknown schema, source, runtime, or state versions fail closed.
- Use `uv` for Python tooling. Do not use yarn.
- Do not edit the frozen files under `docs/baseline/`. New product decisions go
  in the versioned documents referenced by the issue DAG.
