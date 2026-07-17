# Watari CLI decisions

Status: D001 design freeze
Issue: D001
Base/dependency SHA: `6c9ddc922a86de2ee510e1b3a92f7b739eba8fa7`

この文書はD001で確定した選択と、確定していない選択を分離して記録する。ここにない設計を
推測で確定しない。`open`は実装既定値ではなく、owner判断または後続qualification待ちを意味する。

## Frozen decisions

| id | decision | status | owner | rationale | consequences | trace |
| --- | --- | --- | --- | --- | --- | --- |
| DEC-001 | product repositoryは`BINGE-japan/watari-cli`、visibilityはprivate、default branchは`main`とする | frozen | binge | B000で指定されたrepository identityを確定するため | design ticketはこのrepositoryを変更対象とし、public化は別gate | `B000`, `D001`, `Q005`, `Q016` |
| DEC-002 | app code repositoryとuser state repositoryを分離する | frozen | product | code/schema/default policyと個人profile/memory/checkpointの境界を保つため | code repoに個人state、credential、runtime sessionを置かない | `ADR-001`, `RQ-010`, `RQ-011`, `Q005` |
| DEC-003 | v0.x supportはUbuntu 24.04 / WSL2に限定する | frozen | binge | Linux固有のlock/namespaceを含むため | macOS/native Windowsは別support gate。Python 3.11以上、Git、uvを前提とする | `ADR-009`, `Q007`, `Q016` |
| DEC-004 | private pilotの必須matrixはCodex full Watari、Pi/OpenAI-Codex trusted dream、Pi/OpenRouter low-risk utilityとする | frozen | binge | private pilotで必要なruntime・routeを明示し、qualification対象を限定するため | OpenRouterはutility task routeとして扱い、dream/canonical writerにしない | `MX-001`, `MX-002`, `MX-003`, `P13`, `Q007` |
| DEC-005 | OpenRouter low-risk utilityへprivate memoryやconnector raw dataを送らず、完全なWatariとは称さない。local user turnだけがtrusted dream候補になり、provider outputは未検証contextである | frozen | binge | data classification境界とWatari identityを維持し、provider出力を事実として扱わないため | OpenRouter自身はdream/canonical writerではなく、trusted data送信には別の明示承認済みroute decisionが必要 | `ADR-005`, `NM-004`, `RQ-009`, `MX-003`, `C002`, `Z005`, `M001`, `M002` |
| DEC-006 | 外部model runtimeはmandatory sandboxを通過しなければsupportedにしない | frozen | security | same-UID permissionを秘密境界とせず、state/key、egress、retrieval、processを制御するため | `SB-001`..`SB-007`とZ001/Z002、およびruntime qualificationを必須化する | `ADR-006`, `SB-001`, `SB-007`, `Z001`, `Z002`, `Q001`, `Q007` |

## Open decisions

| id | decision | status | owner | reason it remains open | close gate | trace |
| --- | --- | --- | --- | --- | --- | --- |
| DEC-OPEN-001 | public package/distribution name | open | binge | public distribution名はP15でユーザーが決定する | `Q016` before `Q017` | `RQ-011`, `Q016`, `P15` |
| DEC-OPEN-002 | public license | open | binge | licenseはpublic化時にユーザーが決定する | `Q016` before `Q017` | `Q016`, `P15` |
| DEC-OPEN-003 | trusted OpenRouter routeを将来の完全なWatariとして認めるか | open | binge | private pilotのlow-risk utility境界を変更する判断は未承認 | owner decision plus route/security qualification before public claim | `DEC-005`, `MX-003`, `P0`, `Q016` |
| DEC-OPEN-004 | `MATRIX-PUBLIC-1.0`でsupportedとするruntime/sourceの最終集合 | open | binge + qualification reviewer | public supportはclean conformance/E2E後にのみ決める | `Q007`, `Q016` | `MX-006`, `MX-007`, `MX-008`, `MX-009` |
| DEC-OPEN-005 | crypto suite、署名、鍵回復、physical loose/pack layout | open | high-trust reviewer | D001では未観測で、P2b/D010/D011/G001/G003の実測前に確定しない | P2b qualification and `G003` | `D010`, `D011`, `G001`, `G003` |
| DEC-OPEN-006 | private/public matrixの未qualified source/connectorの最終採用 | open | binge + qualification reviewer | connectorごとのread qualificationとrelease gateが未完了 | connector qualification and `Q016` | `RQ-005`, `MX-005`, `MX-007`, `X001`, `X011` |

## Decision constraints

| id | constraint | status | trace |
| --- | --- | --- | --- |
| CON-001 | `open` decisionを実装既定値へ暗黙に落とさない | frozen | `Gate D`, `T-REQ-TRACE-005`, `B006` |
| CON-002 | 未観測runtime・暗号方式はqualification合格まで`unsupported`または`open`とする | frozen | `R001`, `Q016`, `D010`, `D011` |
| CON-003 | D001の変更可能pathは`docs/requirements.md`と`docs/decisions.md`だけ | frozen | `D001`, `AGENTS.md` |
| CON-004 | network、live data、credential、external writeはD001で使用しない | frozen | `AGENTS.md`, `D001` |
