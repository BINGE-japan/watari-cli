# Watari CLI requirements

Status: D001 design freeze
Issue: D001
Base/dependency SHA: `6c9ddc922a86de2ee510e1b3a92f7b739eba8fa7`
Source: `docs/baseline/implementation-plan.md`, `docs/baseline/issue-dag.md`

この文書は、Watari CLIの要求、非目標、受入条件、runtime/source matrix、sandbox要件を
machine-readableなIDで管理する。未qualifiedな能力はsupportedと表示しない。要求の意味を
変更する判断は`docs/decisions.md`へ記録する。

## Trace schema

各行は次の列を持つ。`trace`は後続ticketまたはtest IDを1つ以上含まなければならない。
`status`が`open`の行は実装既定値として扱わない。

| field | rule |
| --- | --- |
| `id` | 文書内で一意の`RQ-*`, `NM-*`, `AC-*`, `SB-*`, `MX-*` |
| `kind` | `requirement`, `non-goal`, `acceptance`, `sandbox`, `matrix` |
| `status` | `frozen`または`open` |
| `trace` | 後続test IDと実装ticket IDのカンマ区切り。空欄禁止 |
| `owner` | 未決事項は所有者を明示 |

## User requirements

| id | kind | requirement | acceptance | status | owner | trace |
| --- | --- | --- | --- | --- | --- | --- |
| RQ-001 | requirement | install/init後も`~/.claude`、`~/.codex`、`~/.pi`、project files、shell startup、schedulerを無断変更せず、裸のAI CLIへWatari contextを注入しない | clean-room home diffと裸CLI試験でWatari固有差分・context注入が0 | frozen | product | `AC-001`, `Q007`, `P13`, `B002`, `R019` |
| RQ-002 | requirement | `watari`または`watari chat`から起動したsessionだけがcanonical contextを受け取る | Watari経由sessionにはcontextがあり、裸CLIにはない | frozen | product | `AC-002`, `R019`, `I003`, `Q007` |
| RQ-003 | requirement | `watari init`がruntime、対話model、dream model、source connector、state Git、timezoneを設定し、接続テスト結果を保存する | init結果とcapabilityをstate/statusで再表示できる | frozen | product | `AC-003`, `R018`, `S015`, `K001`, `K005` |
| RQ-004 | requirement | Watari起動のsupported session streamをrole識別して走査し、前回成功位置以降だけをdream対象にする | user/assistant/tool/system role、unsupported、未接続、失敗、checkpointをsource別に表示する | frozen | product | `AC-004`, `A001`, `M001`, `M005`, `M006`, `S011` |
| RQ-005 | requirement | 明示的に有効化したread-only connectorだけを走査する | connectorごとの最終成功、遅延、失敗、partial状態を`status`で表示し、write methodを持たない | frozen | product | `AC-005`, `X001`, `X002`, `X003`, `X005`, `X007`, `X009`, `X011` |
| RQ-006 | requirement | `watari dream`がdry-run、source指定、history、failure表示を提供する | dry-runは変更0、model failure時はcheckpointを進めず、partial failureを成功扱いしない | frozen | product | `AC-006`, `M003`, `M004`, `M005`, `M006`, `Q002` |
| RQ-007 | requirement | user timezoneの最終成功日でfirst-launch auto dreamを判定する | 同日・同時2 processは1回、失敗は再試行、daemonは作らない | frozen | product | `AC-007`, `M006`, `P11`, `Q002` |
| RQ-008 | requirement | profileは明示的な`show/edit/validate/history`だけで変更する | dreamがpersona/rulesを書き換えず、invalid profileはcommitされない | frozen | product | `AC-008`, `C001`, `S010`, `M002`, `M003` |
| RQ-009 | requirement | 全adapterが同じcanonical profile revision・memory revisionを参照し、同じroute policyでは同じcanonical context fingerprintを受け取る | visibility projection差分はeffective fingerprintと機能差として説明する | frozen | product | `AC-009`, `C002`, `C004`, `C005`, `R001`, `I001` |
| RQ-010 | requirement | clean PCでappとstateを復元する | profile、memory event set、derived view、checkpointのdigestが一致する | frozen | product | `AC-010`, `G009`, `G011`, `L006`, `Q007` |
| RQ-011 | requirement | restore指定なしのinitはユーザー専用の空state、device identity、recovery手順を作る | BINGEのprofile、memory、key、pathを含まない | frozen | product | `AC-011`, `S015`, `G005`, `Q007`, `Q005` |
| RQ-012 | requirement | profile、memory、context、dream、source、sync、model送信範囲の所在と根拠を説明する | `where/status/context explain/memory explain/dream show`がhuman/JSONでversioned出力する | frozen | product | `AC-012`, `S003`, `S004`, `C007`, `M004`, `G010`, `I003` |
| RQ-013 | requirement | `watari remember`またはsession candidateで得た深い事実を即時取り込みできるが、review完了前にcanonical event化しない | candidateはsource-bound immutable proposalとして保存され、review後だけ`C006`/`C008`経由でcanonical eventになる | frozen | product | `AC-013`, `C006`, `C008`, `C001`, `S009` |
| RQ-014 | requirement | multi-device syncでimmutable event set、profile/checkpoint conflict、tamper、rollback、RPOを扱う | 2台のsync/conflict/tamper/rollback試験で暗黙merge・force push・checkpoint先行を拒否し、RPOを表示する | frozen | security | `AC-014`, `G006`, `G007`, `G008`, `G009`, `G010`, `Q001` |
| RQ-015 | requirement | legacyのpersona、rules、knowledge、memory、checkpointをlossless capsuleからreview・importし、fixed-time parityとfinal delta/cutoverを経ても旧sourceへ書かない | capsule completeness、review、copy-on-write import、fixed-time parity、final delta、stop attestation、旧source hash不変を確認する | frozen | migration | `AC-015`, `L001`, `L002`, `L003`, `L004`, `L005`, `L006`, `L007`, `L008`, `L009`, `L010`, `Q009`, `Q010`, `Q011`, `Q012`, `Q013`, `Q014`, `Q015` |
| RQ-016 | requirement | Journalとexternal-completionを含む現行featureはcutover前にqualified implementationまたはsnapshot digest付きwaiverへ分類する | feature parity manifestの全featureがimplementation/evidence digestまたはowner waiverへ結び付き、未分類0でcutoverを停止する | frozen | binge | `AC-016`, `Q008`, `Q012`, `X012`, `X013`, `X014`, `X015`, `X016`, `X017`, `X018` |

## Non-goals

| id | kind | non-goal | acceptance boundary | status | owner | trace |
| --- | --- | --- | --- | --- | --- | --- |
| NM-001 | non-goal | installだけでdaemon、cron、systemd、Windows Task Schedulerを作らない | install/initのscheduler差分0 | frozen | product | `AC-001`, `Q007`, `M006` |
| NM-002 | non-goal | dreamからemail、Slack、Linear等へ外部writeしない | dream transactionに外部write権限・write adapterがない | frozen | security | `AC-006`, `M002`, `X016`, `X017`, `Q001` |
| NM-003 | non-goal | 接続可能なあらゆるserviceを実装済みと称さない | 未qualified connectorはunsupported表示 | frozen | product | `AC-005`, `X001`, `X011`, `Q001` |
| NM-004 | non-goal | cheap modelへ全記憶・全connector dataを無条件送信しない | visibility/route deny matrixとegress captureで許可外送信0 | frozen | security | `AC-009`, `C002`, `Z001`, `Z002`, `Q001` |
| NM-005 | non-goal | model出力を検証せずcanonical stateへ直接書かせない | schema validation、source binding、reviewまたはtransactionを必須化 | frozen | security | `AC-006`, `M002`, `M003`, `C006`, `C008` |
| NM-006 | non-goal | 既に開いている他社CLI sessionへの後付け注入をv1保証に含めない | Watari起動session以外をsupported sessionとして扱わない | frozen | product | `AC-002`, `R001`, `R019` |

## Acceptance criteria

| id | kind | observable result | status | owner | trace |
| --- | --- | --- | --- | --- | --- |
| AC-001 | acceptance | install/init前後のhome、global AI config、project、shell、scheduler差分が許可範囲外で0 | frozen | reviewer | `Q007`, `Q001`, `B002`, `R019` |
| AC-002 | acceptance | `watari`/`watari chat`経由だけがWatari contextを受け取り、裸CLIには現れない | frozen | reviewer | `R019`, `I001`, `I003` |
| AC-003 | acceptance | initが指定されたruntime/model/source/state/timezoneと接続結果を保存・再表示する | frozen | reviewer | `R018`, `S015`, `K001`, `K005` |
| AC-004 | acceptance | supported session streamをrole・lineage・checkpoint付きでincremental scanする | frozen | reviewer | `A001`, `M001`, `M005`, `S011` |
| AC-005 | acceptance | enabled read-only connectorだけがscanされ、partial/error/checkpointが可視化される | frozen | reviewer | `X001`, `X011`, `S011`, `S003` |
| AC-006 | acceptance | dry-run無変更、structured decision strict validation、failure時checkpoint不変、atomic apply | frozen | reviewer | `M002`, `M003`, `M004`, `M005`, `Q002` |
| AC-007 | acceptance | timezone/DST/concurrency/offlineを含むfirst-launch once semantics | frozen | reviewer | `M006`, `P11`, `Q002` |
| AC-008 | acceptance | profile変更はexplicit commandのみで、dreamからprofile/rulesを変更できない | frozen | reviewer | `C001`, `S010`, `M002` |
| AC-009 | acceptance | canonical/effective fingerprint、visibility、route、project layer、retrieval boundaryを説明できる | frozen | reviewer | `C002`, `C003`, `C004`, `C005`, `R001`, `Z001`, `Z002` |
| AC-010 | acceptance | clean PC restore後のprofile/memory/derived/checkpoint digestが一致する | frozen | reviewer | `G009`, `G011`, `L006`, `Q007` |
| AC-011 | acceptance | restore指定なしの新規stateにBINGE固有情報がない | frozen | reviewer | `S015`, `Q005`, `Q007` |
| AC-012 | acceptance | where/status/explain/show系commandが保存先・根拠・同期・送信範囲を表示する | frozen | reviewer | `S003`, `S004`, `C007`, `M004`, `G010`, `I003` |
| AC-013 | acceptance | remember/session candidateの候補がreviewなしでcanonical stateへ到達せず、review後のeventだけがsource bindingを持つ | frozen | reviewer | `C006`, `C008`, `C001`, `S009` |
| AC-014 | acceptance | 2台stateでsync、conflict、tamper、rollbackを検出・拒否し、RPOとrecovery状態を表示する | frozen | reviewer | `G006`, `G007`, `G008`, `G009`, `G010`, `Q001` |
| AC-015 | acceptance | legacy capsuleがlosslessで、review済みimportとfixed-time parityが一致し、final delta/cutover中も旧source writeが0 | frozen | reviewer | `L001`, `L002`, `L003`, `L004`, `L005`, `L006`, `L007`, `L008`, `L009`, `L010`, `Q009`, `Q010`, `Q011`, `Q012`, `Q013`, `Q014`, `Q015` |
| AC-016 | acceptance | Journal/external-completionを含む全現行featureがqualified evidence digestまたはsnapshot digest付きwaiverに分類され、未分類が0 | frozen | reviewer | `Q008`, `Q012`, `X012`, `X013`, `X014`, `X015`, `X016`, `X017`, `X018` |

## Runtime/source matrices

`support`はqualificationとclean E2Eが完了するまで`unsupported`から変更しない。matrixの
未確定欄は未決定であり、実装既定値ではない。

| id | matrix | capability | required runtime/source | data class | required test/gate | support | trace |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MX-001 | MATRIX-PRIVATE | interactive Watari chat | Codex CLI | trusted Watari | `R003`, `R004`, `R019`, `Z003`, `I001`, `Q007` | required | `RQ-002`, `RQ-004`, `AC-002` |
| MX-002 | MATRIX-PRIVATE | trusted dream | Pi + OpenAI-Codex | trusted-model | `R005`, `R006`, `R007`, `Z004`, `I001`, `Q007` | required | `RQ-004`, `RQ-006`, `AC-006` |
| MX-003 | MATRIX-PRIVATE | low-risk utility task | Pi + OpenRouter | low-risk-model only; private memory/connector raw data prohibited | `R008`, `R009`, `R010`, `Z005`, `I001`, `Q007` | required utility; OpenRouter is neither dream writer nor canonical writer and is not full Watari | `RQ-004`, `RQ-009`, `NM-004`, `AC-009` |
| MX-004 | MATRIX-PRIVATE | Watari session receipt source | Claude, Codex, high-trust Pi runtime sessions; Watari session receipt | trusted route policy | `A002`, `A003`, `A004`, `A008`, `A009`, `A010`, `A011`, `I001`, `Q007` | required source matrix | `RQ-002`, `RQ-004`, `AC-002`, `AC-004` |
| MX-005 | MATRIX-PRIVATE | enabled read-only connectors | explicitly enabled connector instances only | connector classification policy | `X001`, `X002`, `X003`, `X005`, `X007`, `X009`, `X011`, `M005`, `Q007` | separate required source matrix; only when enabled | `RQ-005`, `AC-005` |
| MX-006 | MATRIX-PUBLIC-1.0 | public supported runtime | runtime must pass clean context injection, session capture, auth isolation, dream/retrieval E2E | route-specific | `Q007`, `Q016`, `I001` | open until qualified | `RQ-009`, `AC-009`, `AC-010` |
| MX-007 | MATRIX-PUBLIC-1.0 | public supported source/connector | source/connector must have independent contract and release gate | source policy | `X001`, `X011`, `Q007`, `Q016` | open until qualified | `RQ-005`, `AC-005` |
| MX-008 | MATRIX-PUBLIC-1.0 | Claude adapter | synthetic conformance and configured-runtime qualification required before public support | route-specific | `R011`, `R012`, `R013`, `Z006`, `Q016` | unsupported until qualified | `RQ-009`, `AC-009` |
| MX-009 | MATRIX-PUBLIC-1.0 | OpenCode adapter | official distribution, config, structured/session behavior and sandbox qualification required | route-specific | `R014`, `R015`, `R016`, `Z007`, `Q016` | unsupported until qualified | `RQ-009`, `AC-009` |

## Mandatory sandbox contract

| id | kind | invariant | verification | status | owner | trace |
| --- | --- | --- | --- | --- | --- | --- |
| SB-001 | sandbox | external runtimeへstate/keyをmountしない | mount inspectionでstate/key visibility 0 | frozen | security | `Z001`, `Z002`, `Z003`, `Z004`, `Z005`, `Z006`, `Z007` |
| SB-002 | sandbox | approved project layerだけをread-onlyで提供する | untrusted/changed/auto-discovered instruction deny test | frozen | security | `C003`, `Z001`, `Q001` |
| SB-003 | sandbox | retrievalをsession-scoped、route-bound capabilityに限定する | route swap、raw ID、全件取得、sandbox外pathを拒否 | frozen | security | `C005`, `Z001`, `Z002`, `R001` |
| SB-004 | sandbox | networkはrouteごとのallowlistだけを許可する | network captureでdirect DNS・許可外egress 0 | frozen | security | `Z001`, `Z002`, `Z005`, `Q001` |
| SB-005 | sandbox | process、resource、Ctrl-C、cleanupを管理しchild残留を許さない | kill/Ctrl-C/cleanup qualification | frozen | security | `Z001`, `Z002`, `Z003`, `Z004`, `Q002` |
| SB-006 | sandbox | same-UID owner permissionを秘密境界と称さない | sandbox escape・same-UID matrix | frozen | security | `Z001`, `Z002`, `C005`, `Q001` |
| SB-007 | sandbox | sandbox要件に合格しないruntimeはsupportedにしない | capability reportが`unsupported`でfail closed | frozen | security | `Z001`, `Z002`, `R001`, `Q007`, `Q016` |

## D001 trace checks

| check_id | check | required result | source of truth |
| --- | --- | --- | --- |
| T-REQ-TRACE-001 | all requirement/non-goal/acceptance/sandbox/matrix IDs are unique | pass; duplicate count 0 | all tables above |
| T-REQ-TRACE-002 | every trace cell is non-empty and references a local ID, baseline implementation-plan ID, or baseline DAG ID; phase/ADR references are valid baseline references and are not unknown | pass; empty/unknown trace count 0; source of truth is local IDs + `docs/baseline/implementation-plan.md` + `docs/baseline/issue-dag.md` | all tables above + both baseline documents |
| T-REQ-TRACE-003 | required matrix IDs exist | `MX-001`..`MX-009` exist, both matrix names present, private session-receipt and enabled-connector rows are separate | runtime/source matrices |
| T-REQ-TRACE-004 | required sandbox IDs exist | `SB-001`..`SB-007` exist | mandatory sandbox contract |
| T-REQ-TRACE-005 | required decision IDs are represented | `DEC-001`..`DEC-006` exist in `docs/decisions.md`; open decisions remain explicit | `docs/decisions.md` |
| T-REQ-TRACE-006 | every requirement and non-goal has acceptance/trace coverage | no row without acceptance and trace | requirements/non-goals tables |
