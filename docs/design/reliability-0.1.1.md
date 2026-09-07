# Reliability corrections in 0.1.1

The review identified failures at boundaries between individually tested components.
This release keeps the file-based memory architecture and adds regression tests
before changing those boundaries. All test inputs are synthetic; no live memory or
service credentials are used.

## Storage and concurrency

- Git synchronization requires `WATARI_HOME` to equal Git's canonical top-level
  directory. Nested memory must not stage, commit, configure, pull, or push its parent.
  An explicit setup attempt inside a parent repository is rejected as well.
- Process and thread locks serialize memory ingestion, state generation, host writes,
  and CLI operations including Git. Locks live in XDG state, keyed by canonical path.
  Ordinary read-only status/help and an uninitialized home do not create lock files.
- Every incoming field consumed by regeneration is type-checked before mutation.
  Unknown explicit format versions and undeclared sources are rejected. Unversioned
  legacy rows remain version 1; omission of the legacy `source` field is compatible.
- Regeneration is previewed with both complete candidate genres before persistence.
  A versioned redo journal contains the validated target contents. Durable writes use
  unique owner-only temporary files, fsync, atomic replacement, and directory fsync.
  A crash after the journal is durable is completed on the next memory operation;
  failed validation never creates a journal. Log replacement preserves the existing
  contents verbatim and appends new rows (logical append-only history).
- Recovery validates all relative target paths before writing. Journal and temporary
  files are excluded from Git. Pi does not inject state while a journal is pending.
- Settings updates use a separate lock. Registration, credential updates, and freee's
  rotating-token exchange include their read/modify/write window in that lock.
  Malformed settings are no longer silently treated as empty settings.

## Completeness and time

- Linear/GitHub/Notion/Calendar/Drive IDs include the full update timestamp, rather than
  only the day. Old IDs remain in history; rereading an old update may add one extra
  historical row during migration. No automatic rewind or live backfill is performed.
- Paginated readers return a complete batch or an error, not a partial batch whose
  maximum time could leap over unread items. Repeating page tokens and page limits
  fail closed. GitHub incomplete searches and its 1000-result cap also fail closed.
  This prioritizes preservation over progress: large results may require a narrower
  explicit `--since` window; automatic historical range partitioning is not implemented.
- Gmail preserves millisecond timestamps and reads every listed message, including
  messages beyond the former 50-item cap. Message bodies are not fetched.
- Ordering and memory folding compare instants, not raw ISO strings. Equal-timestamp
  rows are not split by transcript batch limits.
- Pi session versions 1/2/3 are supported; absent headers' version fields mean legacy
  version 1. Unknown versions prevent advancement. Organizing includes assistant text
  as context, never thinking or tool calls and never as independent factual evidence.
  The lower-level user-only extraction API remains available for coverage checks.

## Relay and remote concurrency

- The queue is fsynced before offsets. A partial trailing queue row is discarded before
  retry, since that source position has not been acknowledged. Multiple local chat
  processes use the same lock and reload offsets on every tick.
- Delivery is at-least-once. A crash after remote success can cause a replay; stable
  message IDs prevent duplicate memory facts. This release does not claim exactly-once
  delivery or protection against an independently corrupted/deleted source file.
- Drive snapshots carry the response's strong ETag and file ID. Append and pruning use
  conditional PATCH with `If-Match`; a conflict keeps the queue/data for a later retry.
  Pruning empties or rewrites content conditionally, rather than deleting by name.
  A provider that omits the ETag or does not support this operation is not silently
  downgraded to an unsafe overwrite. Legacy/custom adapters must implement the same
  snapshot/conditional-update contract or pruning is skipped.
- A racing initial file creation is never converted to overwrite. Duplicate names are
  rejected rather than selecting an arbitrary copy. Supported single-host writers
  serialize creation through the local queue lock; shared machine identifiers on
  independent installations are not supported.
- Network access is required only for the existing explicit service operations. The
  new request-header access exists specifically to prevent remote lost updates; no
  additional credential collection or background destination is introduced.

## Approval, UI, and operation

- Slack setup pins workspace, bot, and bot-user IDs. An unexpected bot name or missing
  identity is rejected. Before the approval dialog, `auth.test` must match the pinned
  IDs and name; the dialog includes the actual IDs. The token/identity are read in one
  configuration snapshot and held through approval. Older configurations need a user-run
  `watari connect slack` before posting. Tests never send real Slack messages.
- Only Slack's URL-angle-bracket normalization is accepted in the response text check.
  Changed prose/destinations/threads still fail confirmation. A post-confirmation
  mismatch must be checked in Slack, not automatically resent.
- Fast mode records successful tools and clears evidence each input. Explicit evidence
  registration remains unnecessary there. Unverified responses are not hidden.
- The bounded memory modes enforce their byte cap even when one identifier is huge.
  Unsupported explicit state versions are rejected, including in full-context mode.
- The developer Pi guard only observes Git state. It never publishes untested changes
  on progress text, final text, or shutdown. The agent remains responsible for tests,
  reviewing and committing only its changes, pushing, and checking upstream equality.
- macOS's verified root-owned `/var` and `/tmp` aliases are canonicalized; arbitrary
  symlinks, hardlinks, secret paths, and wrong owners remain rejected. Platform tests
  mock PowerShell discovery instead of requiring a live WSL installation.
- Background organization records exit code and completion time, not model output.
  `watari status` reports the last recorded result. If the parent chat process exits
  before the monitoring thread sees completion, a new result may not be recorded;
  normal process exit is not evidence that all memory content is correct.

## Privacy and limits

README, Google setup, the persona, and `/forget` distinguish selected memory, raw
conversation, Git history, remote synchronization, and the selected AI provider.
There is no promise that secrets in a conversation are detected or removed. Do not
enter secrets. `/forget` is not an erasure of every copy or history. Retention pruning
runs when connected and conflict-free; 90 days is not an unconditional deletion SLA.

CI installs pinned public test dependencies, then runs Python tests and real Pi
extension factories with fake APIs on Linux/macOS. Python 3.11 and 3.13 are included.
This does not establish live Slack/Google compatibility, two-machine end-to-end
behavior, native Windows support, model-specific memory accuracy, or exhaustive
TypeScript type safety. Those checks remain separate from mock-based regression tests.
Performance indexing/caching and license selection remain separate decisions; this
patch does not silently choose redistribution terms for the owner.
