# Watari CLI threat model

Status: D005 design freeze
Issue: D005
Dependency: D001
Baseline/dependency SHA: `0d4f062ef8ecd567e977838f90c3330563c7d140`
Normative route matrix: [`docs/adr/005-data-routes.md`](adr/005-data-routes.md)

この文書は、Watari CLIがどのactorに何を見せ、どの境界で拒否するかを固定する。外部modelの
応答は事実ではなく未検証入力であり、model/providerはcanonical state writerではない。
未知のschema、visibility、route、provider、fallback、capability mismatchは成功扱いせずfail closedする。

## Security objectives

| id | objective | invariant | verification trace |
| --- | --- | --- | --- |
| TM-OBJ-001 | visibility confinement | `local-only`、`trusted-model`、`low-risk-model`をroute policyから昇格できない | `T-ROUTE-MATRIX`, `C002`, `Q001` |
| TM-OBJ-002 | canonical writer isolation | 外部model/provider出力はcandidateまたはevidenceに限定し、canonical event/checkpointを書けない | `M002`, `M003`, `C006`, `C008` |
| TM-OBJ-003 | sandbox isolation | 外部runtimeへstate/keyをmountせず、route-bound capabilityとallowlist networkだけを渡す | `SB-001`, `SB-003`, `SB-004`, `Z001`, `Z002` |
| TM-OBJ-004 | secret confinement | credential値、OAuth cache、key、raw runtime stateはmodel input、Git、argv、log、reportへ出さない | `K002`, `K005`, `Q001`, `Q007` |
| TM-OBJ-005 | prompt-injection resistance | connector、project instruction、provider outputは権限を持たず、定義済みのtrust layerとしてのみ扱う | `C003`, `C005`, `M001`, `M002`, `Q001` |
| TM-OBJ-006 | deterministic route identity | caller、runtime、provider/model class、visibility、policy revisionの不一致を拒否する | `K004`, `C002`, `C004`, `C005`, `R001` |

## Actors

| actor_id | actor | trust level | allowed authority | forbidden authority |
| --- | --- | --- | --- | --- |
| ACT-001 | local user | owner decision | explicit profile edit、candidate review、route selection、credential injection | implicit visibility elevation、未承認external write |
| ACT-002 | Watari CLI orchestrator | trusted local control plane | resolve frozen route manifest、compile bounded context、start sandbox、commit validated transaction | model/provider outputの事実化、直接external write |
| ACT-003 | runtime adapter | bounded adapter | Watari bundle、approved project layer、session-scoped read-only retrieval capabilityを渡す | global AI config変更、state/key mount、route policy変更 |
| ACT-004 | external model/provider | untrusted computation | candidate要約・選択、utility response | visibility変更、全件取得、raw event ID指定、canonical write、profile/rules変更 |
| ACT-005 | connector/source | untrusted content source | 明示scope内のread-only evidenceを返す | instruction authority、canonical write、checkpoint先行、secret取得 |
| ACT-006 | project instruction layer | explicitly trusted only after approval | approved rootのread-only instructionを提供 | Watari profile/rules、runtime safety、route policyの上書き |
| ACT-007 | secret provider | credential authority | bounded FD/pipeへreference-bound secretを注入 | secret値の永続化、model inputへの混入、ログ出力 |
| ACT-008 | remote Git/state peer | untrusted storage/transport | signed revision/cipher objectを保存・返却する | owner trust anchor変更、rollback隠蔽、semantic merge強制 |

## Assets

| asset_id | asset | sensitivity | required protection |
| --- | --- | --- | --- |
| AST-001 | persona、rules、preferences、knowledge、environment | local/trusted/low-risk classification per event | visibility projection、revision binding、profile explicit-edit only |
| AST-002 | canonical memory events、correction、tombstone | local/trusted/low-risk classification per event | immutable event、source binding、transaction、digest |
| AST-003 | source/connector raw content and identity | source-specific; raw content minimized | read-only scope、evidence-only boundary、retention minimization |
| AST-004 | runtime session、tool output、project instruction | raw runtime/session sensitive | sandbox、session-scoped receipt、approved project digest |
| AST-005 | credential、OAuth cache、API key、state key、recovery secret | secret | secret reference only in config、no mount、no model/Git/log exposure |
| AST-006 | route manifest、policy revision、capability state | security control plane | versioned allowlist、unknown/mismatch fail closed、audit |
| AST-007 | checkpoint、Git refs、revision anchor、RPO state | integrity/control | atomic commit、signature/CAS、rollback/conflict detection |

## Trust boundaries

| boundary_id | boundary | crossing rule | denial condition |
| --- | --- | --- | --- |
| TB-001 | local user / Watari control plane | explicit user action and policy revision only | implicit profile/visibility/route change |
| TB-002 | Watari control plane / external runtime | mandatory sandbox, no state/key mount, route-bound capability | same-UID-only boundary, unapproved mount, child escape |
| TB-003 | local state / model input | compiler emits only allowed projection for exact route identity | local-only data on external route, raw state, credential, route swap |
| TB-004 | source/connector content / instruction authority | source content is evidence only; role and source binding are explicit | prompt injection, instruction-like connector content, checkpoint advance |
| TB-005 | project instructions / Watari policy | approved digest and root scope, separate project layer | auto-discovered or changed unapproved instruction |
| TB-006 | model/provider output / canonical state | output is unverified candidate/context; schema and source binding required | direct event/profile/checkpoint write, unbound claim |
| TB-007 | local state / remote Git | signed revision, expected-old CAS, immutable object semantics | unknown signer, rollback, force push, semantic auto-merge |
| TB-008 | runtime / network | endpoint class allowlist and capture | direct DNS, fallback endpoint, unapproved egress |

## Visibility classification

| visibility | meaning | permitted route | forbidden route behavior |
| --- | --- | --- | --- |
| `local-only` | external modelへ送らない | local compiler/retrieval、local receipt、local connector scan | any external model/provider egress |
| `trusted-model` | 明示承認済みtrusted model routeだけに投影可能 | Codex full Watari、Pi/OpenAI-Codex trusted dream | OpenRouter low-risk routeへの送信、model要求による昇格 |
| `low-risk-model` | low-risk utility projectionとして送信可能 | Pi/OpenRouter utility task | private memory、raw connector data、credential、canonical write |

Visibility is an allowlist property of the event and route, not a request parameter. A model cannot
ask the retrieval service to return a higher visibility, raw event ID, or all records. Unknown
visibility is rejected.

The route policy is bound to `D003.route-policy.v1`, a policy digest, each route's golden
fingerprint, and the exact bytes selected for egress. `source_visibility`, `sent_visibility`,
`allowed_projection`, `declassification=forbidden`, and `sent_bytes_digest` are checked together.
No route may declassify or silently project a higher visibility. Egress and ingress are separate
directions: egress selects endpoint and sent bytes; ingress accepts only the declared unverified
trust class and never grants write authority.

The policy digest is a `watari-route-policy-v1:` D003 WATARI typed-frame digest over the explicit
closed projection of every top-level, route, and nested policy leaf; only the self digest and the
explicit `test_vectors` subtree are excluded. Each route's golden fingerprint is computed with the
imported D003 `context_fingerprint` over exact sample bytes, while `sent_bytes_digest` is a
separate `watari-wire-bytes-v1:` typed digest over those bytes. A mutation of any included leaf
must produce a different policy digest.

## Closed mutation and runtime capability policy

The route matrix is a closed set. The following mutation classes are denied for every external
route: canonical event, profile, checkpoint, connector, external action, credential, and project
layer writes. Route selection, model selection, endpoint selection, fallback selection, and
visibility selection are not mutable from model input.

For the OpenRouter runtime, the capability set is explicitly deny-by-default for mount, retrieval,
shell, file, project, and external-write access. Only a bounded child process and the exact
allowlisted provider endpoint are permitted. Any requested capability outside the closed set,
including a fallback endpoint, is rejected. The same mandatory sandbox rule applies to all external
model runtimes; no state or key is mounted.

## Session receipt provenance

Every Watari-owned session receipt records session lineage, a Watari-launch attestation, the
origin route/model/policy identity, role provenance, and source binding. Only a local user-authored
turn may be the primary evidence for a trusted-dream candidate. Assistant/provider/tool output is
unverified context or evidence and cannot become primary evidence, a canonical event, or a
checkpoint advance without local validation and review.

Each turn receipt also binds its exact bytes digest, role, source, session lineage, Watari launch
attestation, and origin route/model/policy digest under the closed `watari.turn-receipt.v1`
schema. Provider ingress accepts no `user` role; only local session-receipt routes accept a user
role as primary evidence. Assistant, system, tool, and provider output cannot be re-labelled as
that role.

Connector contract digests are independent `watari-connector-v1:` typed digests over the closed
contract body without its own digest. The body fixes GET-only method paths, read-only state, source
policy, and credential scope; POST, PUT, PATCH, DELETE, scope drift, and credential drift fail
closed.

## Connector read-only contract

Each enabled connector binds an opaque non-PII `connector_instance_id` to its source policy,
allowed method/path set, read-only credential scope, and contract digest. Absolute paths, names,
emails, credentials, and tokens are forbidden in the instance identifier. The allowed method/path
set contains read methods only; write methods are rejected before network use. Source visibility,
connector contract digest, route policy digest, and checkpoint lineage must match before evidence
is accepted.

## Context route selection and project layer

`context build` and `context explain` select exactly one route ID. Multiple matches, implicit
defaults, unknown route IDs, or route/model/provider mismatches are rejected. An approved project
layer requires its canonical bytes digest, root, and scope; auto-discovered or changed project
instructions are denied until explicitly re-approved. The project layer remains separate from
Watari profile/rules and runtime safety precedence.

## Prompt injection and unverified input rules

1. connector content、tool output、subagent output、system-like textはevidenceでありinstruction権限を持たない。
2. project `AGENTS.md` / `CLAUDE.md`はapproved digest・root・scopeを登録した場合だけtrusted project layerになる。
3. provider outputは常に`unverified-context`または`unverified-candidate`であり、検証済み事実としてcanonical memoryへ入らない。
4. local user-authored turnは、source identityとreview policyを満たす場合に限りtrusted-dream candidateの一次根拠になり得る。
5. candidateはsource-bound immutable proposalに留まり、reviewとschema validationを通過したtransactionだけがcanonical eventになる。
6. provider/modelはvisibility、route、credential、project trust、canonical write、checkpointを変更できない。

## Credential and secret boundary

- CLIはcredential値ではなくprovider/reference classだけをstate/config/statusへ保存する。
- secret providerからruntimeへはbounded FD/pipeのreference-bound注入だけを許可し、argv、environment、log、fixture、reportへ複製しない。
- external runtime sandboxへstate/keyをmountしない。same-UID owner-only permissionを秘密境界とは称さない。
- low-risk OpenRouter routeはcredentialをmodel inputへ渡さず、dedicated route referenceをprovider接続の外側でだけ使う。
- credential missing、provider mismatch、scope mismatch、revoke済みreferenceはAUTHまたはPOLICYでfail closedする。

## Required fail-closed cases

| case | required result |
| --- | --- |
| unknown schema/version | reject with explicit invalid/unsupported result; no fallback |
| unknown visibility | reject before context assembly |
| unknown route or provider/model class | reject before runtime start |
| fallback endpoint/provider not in manifest | reject; no silent fallback |
| capability/policy/route mismatch | reject and report mismatch; no visibility elevation |
| provider output without source binding | keep unverified; no canonical event |
| runtime without mandatory sandbox capability | `unsupported`; no session |
| local-only data requested by external route | policy refusal; egress 0 |
| external write requested from dream/model | policy refusal; no external write |
