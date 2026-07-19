# Scheduling ワタリの夢を見る (headless dream)

The original hand-rolled Watari grew its memory automatically every night:
an external routine (a scheduler, outside the assistant itself) invoked the
agent headless with a "go consolidate" instruction. watari-cli only
documents the on-demand path today — saying "夢を見て" inside a live
conversation, or running `watari dream` by hand. This doc covers reproducing
the automatic nightly version, faithful to the original: **scheduling stays
external**. watari-cli does not ship a scheduler of its own — `watari chat`
remains a pull-only launcher; you point a real scheduler (cron, a systemd
timer, launchd, Windows Task Scheduler, ...) at it.

## How it fits together

`watari chat` already knows how to launch Pi with the bundled skill and the
right `WATARI_HOME`, and passes any extra arguments straight through to Pi.
Pi has a non-interactive mode (`--print` / `-p`: run the given prompt to
completion — including whatever tool calls it needs — then exit) that suits
a scheduled job with no TTY and nothing waiting on interactive input.

## Recipe (cron example)

    # crontab -e — runs nightly at 4am
    0 4 * * * WATARI_HOME=/path/to/your/memory watari chat -- --no-session -p "夢を見て" >> /path/to/dream.log 2>&1

Notes:

- **Everything meant for Pi goes after `--`.** `watari chat`'s own parser
  only knows `--home`/`--runtime`/`--show`; anything else (like `-p` or
  `--no-session`) is rejected as "unrecognized arguments" unless it comes
  after the `--` separator, which tells `watari chat` to stop parsing and
  pass the rest straight through. `watari chat --show -- --no-session -p
  "夢を見て"` is a good way to double-check the composed command before
  wiring it into a real schedule.
- `-p` / `--print` and `--no-session` are real Pi CLI flags (checked against
  the installed `@earendil-works/pi-coding-agent --help`, not guessed).
  `--no-session` keeps the run ephemeral so a nightly job doesn't pile up
  session files — drop it if you'd rather keep a session history of dream
  runs.
- Set `WATARI_HOME` explicitly on the cron line: cron's environment is
  minimal, and it's not worth relying on a saved `watari install` config
  being picked up implicitly (it will be, if cron runs as the same user with
  the same `$HOME`/`XDG_CONFIG_HOME` — but being explicit here is cheap and
  robust either way).
- Prefer having `pi` itself installed and on cron's `PATH`. `watari chat`
  falls back to `npx -y @earendil-works/pi-coding-agent` when `pi` isn't
  found, which re-resolves the package over the network on every run — fine
  interactively, but an avoidable network dependency and startup cost for a
  nightly job.
- The model/runtime choice for this run is entirely Pi's own concern (its
  own config, or `--provider`/`--model` flags passed the same way after
  `--`) — `watari chat` doesn't need to know or care, matching the general
  design (see the "provider/model" cleanup in the project history).

## What actually happens each run

Nothing new: it's the same "夢を見る" procedure the skill already documents,
just triggered by cron instead of a live "夢を見て" — the agent runs `watari
dream --json`, judges the candidates, writes rows with `watari ingest
--rows ... --advance-pi`, and finishes with `watari audit`. Cursors, dedup,
and the three-tier judgment rules all behave identically whether the prompt
came from a person or from cron.
