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

## Commit and push completion is mandatory

- A task that changes repository files is incomplete until relevant tests and
  `git diff --check` pass, the diff has been reviewed, and the task's changes
  have been committed with a meaningful message **and pushed to the configured
  upstream**. A local commit is not completion.
- Before reporting completion, run `git status --porcelain`, then `git push`,
  then verify `git rev-list --left-right --count @{upstream}...HEAD` is `0 0`.
  Do not send the final answer while the worktree has output or the branch is
  ahead of, behind, or diverged from its upstream.
- Never sweep unrelated pre-existing changes into a commit. If the worktree is
  already dirty at task start, stop before editing and report the conflict.
- If the branch has no upstream, push fails, or synchronization would require a
  merge/rebase/force-push, stop and report that the task is not complete. Never
  create an upstream or rewrite history automatically.
- The project-local Pi extension in `.pi/extensions/commit-worktree/` enforces
  commit, push, and upstream verification before final answers and again on
  graceful session shutdown.
