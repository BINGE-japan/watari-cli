# Watari CLI 実装 Issue DAG

Status: execution baseline / implementation not started
Date: 2026-07-17
Parent specification: [watari-cli-implementation-plan.md](watari-cli-implementation-plan.md)

この文書は、Watari CLIを廉価モデルへ一件ずつ実装委任するための実行台帳である。
親仕様と矛盾する場合は親仕様を優先し、このDAGを修正してから実装を再開する。
どのticketも、現行`~/.claude`、ライブ記憶、scheduler、external serviceを変更する許可ではない。

## 1. 運用規則

### Review class

| Class | 実装 | merge条件 |
| --- | --- | --- |
| L | contract確定後なら廉価モデルへ委任可 | 自動test、diff review、scope検査 |
| H | 廉価モデルはfixture、失敗test、bounded implementationを補助可 | 高信頼reviewerが設計・security invariant・failure evidenceを承認 |
| O | 実機観測またはユーザー判断を含む | 人が観測結果または選択を記録。モデルの推測で閉じない |
| C | cutover/external writeを含む | bingeの個別承認、runbook、二者確認、rollback条件を満たす |

reviewerは当該ticketのauthorと別にする。H/O/Cを、廉価モデルの自己申告だけでclosedにしない。

### すべてのticketに共通するprompt contract

1. issue ID、親仕様の節、base commit SHA、dependencyのmerge SHAをpromptへ明記する。
2. 表の`変更範囲`以外を編集しない。必要になった場合は停止し、DAG変更を先にreviewする。
3. 最初に指定testを失敗させ、最小実装で通す。既存testの削除、skip、期待値緩和は禁止する。
4. production codeは原則1 module、testは原則1 file、総差分は目安300行以内とする。
5. 既定ではlive data、credential、個人path、実service、通常のAI configを使わず、fixtureはsynthetic
   だけにする。例外はO/C ticketの`Authority`欄にcredential、source、write対象、approval IDを固定する。
6. networkは`NET-*`と明記したO/C qualification以外で禁止する。credential値は人が注入し、モデル、
   prompt、test artifactへ渡さない。
7. 完了報告に`git diff --check`、指定test、全体test、`git status --short`、diff statを添付する。
8. generated artifact、cache、secret、transcriptをcommitしない。L/H codeのrollbackはcommit revert、
   O qualificationはcredential revoke/temporary resource cleanup、Cはrunbook固有abort/recoveryとする。
   content-free evidenceはticketで指定したprivate audit storeだけへ保存する。
9. unknown schema/version/stateはfail closedとし、silent fallbackを追加しない。
10. model出力を事実や合格証拠にしない。test artifactと観測値だけを証拠にする。

### READY gate

廉価モデルへ渡す前に、issueへ次がすべて埋まっていなければならない。

- exact base/dependency SHA、変更可能pathの実在、担当reviewer
- frozen input/output schema revision、未解決ADRなし
- exact test path/case ID、実行command、期待exit/output fixture
- network/credential/live-read/external-writeのallowlistまたは全てnone
- artifact allowlist、cleanup/rollback command、最大diff budget

表の行は実装順のbaselineであり、READY blockがない行をそのままモデルへ渡さない。

### 標準test command

将来の`watari-cli` repositoryでは次を標準化する。

```text
uv run pytest <ticket-specific-test> -q
uv run pytest -q
uv build
uv run python scripts/smoke_install.py dist/
```

donor componentに関係するticketでは、別jobとして`new-watari`の`vp run test`も実行する。
test名は下表のIDをmarkerまたはcase名に含め、requirements traceから逆引きできるようにする。

## 2. Critical path

```text
B000
  -> D001-D012
  -> B001-B004
  -> S001-S004
  -> K001-K005 + G001-G005
  -> S005-S016
  -> C001-C009 + Z001-Z002 + A001 + R001
  -> source/runtime adapters
  -> A008-A011 + M001-M006 + I001
  -> G006-G011 + L001-L010 + I002-I004
  -> X001-X018
  -> Q001-Q017
```

同じ段の独立ticketは並列実装できる。dependencyに未完了ticketが1件でもあれば開始しない。

### B000 repository bootstrap / C

Depends: none。Authorityはapproval ID、owner、exact repository名、`private` visibility、default branchに
限定する。binge承認後に空のprivate `watari-cli` repositoryを作り、`AGENTS.md`、`README.md`、
`.gitignore`、この計画とDAGのdigest付きbaselineだけを移送する。code、live state、credential、donor
historyはcopyしない。remote visibility、default branch、initial commitを観測して記録する。以後の
design ticketはこのrepositoryだけを変更する。

## 3. Design freeze tickets

| ID / class | Depends | 変更範囲 | 先行test・観測 | DoD |
| --- | --- | --- | --- | --- |
| D001 / O | B000 | `docs/requirements.md`, `docs/decisions.md` | `T-REQ-TRACE` lint | 全ユーザー要求、非目標、`MATRIX-PRIVATE`/`MATRIX-PUBLIC-1.0`、OpenRouter utility/trusted選択、mandatory sandbox、未決事項ownerをID化。好みはbingeへ一問ずつ確認 |
| D002 / H | D001 | `docs/cli-contract.md`, `tests/contracts/test_cli_schema.py` | `T-CLI-SCHEMA`, `T-EXIT-STABLE` | command、JSON schema、exit code、read/write分類、failure semanticsを固定 |
| D003 / H | D001 | `docs/data-contract.md`, `tests/fixtures/canonical/`, `tests/unit/test_canonical_vectors.py` | `T-CANON-*` golden vectors | logical eventのRFC 8785互換bytes、NFC/LF/time/number、digest、event ID、fingerprintを固定。physical loose/packは未確定のまま |
| D004 / H | D003 | `docs/adr/004-transaction.md`, `tests/contracts/test_transaction_model.py` | state-machine model test | PREPAREDからCOMPLETEまでのstate、signed commit境界、recovery、atomic ref条件を固定 |
| D005 / H | D001 | `docs/threat-model.md`, `docs/adr/005-data-routes.md` | `T-ROUTE-MATRIX` policy lint | actor、asset、trust boundary、visibility、route manifest、secret保証範囲、prompt injection境界を固定 |
| D006 / H | D002,D005 | `docs/runtime-contract.md`, `tests/contracts/interfaces/test_runtime.py` | fake runtime conformance fails | runtime/model/auth/context/project-layer capability contractを固定 |
| D007 / H | D002,D005 | `docs/source-contract.md`, `tests/contracts/interfaces/test_source.py` | fake source conformance fails | source identity/role/lineage/snapshot/checkpoint proposal contractを固定 |
| D008 / H | D002,D005 | `docs/connector-contract.md`, `tests/contracts/interfaces/test_connector.py` | fake connector conformance fails | connector read/write scope、classification、pagination、coordinator contractを固定 |
| D009 / H | D005,D006 | `docs/retrieval-contract.md`, `tests/contracts/interfaces/test_retrieval.py` | fake retrieval conformance fails | route-bound search/get/explain、project trust、audit、write-proposal境界を固定 |
| D010 / H | D003,D004,D005 | `docs/adr/010-crypto-qualification.md`, `tests/security/spec/test_crypto_matrix.py` | synthetic attack matrix | 外部crypto、signing、trust anchor、rollback、recovery、rotationの比較手順とreject条件を固定 |
| D011 / H | D003,B000 | `tests/performance/storage_harness.py`, `docs/adr/011-object-layout.md` | synthetic dry harness | WSL2 10k/100k create/status/clone/pull/rebuild/backupの測定法・budget・metrics schemaを固定し、layout decisionは`proposed`のまま |
| D012 / H | D003,D004,D005 | `docs/migration.md`, `docs/acceptance.md`, `tests/migration/spec/test_invariants.py` | migration invariant lint | lossless capsule、scope manifest、visibility review、quarantine、fixed time、stop attestationを固定 |

Gate D: D001-D012のrequirements-to-test traceが100%で、全CLI commandが実装ticket/contract testへ対応し、
`open` decisionが実装既定値に紛れていない。

### CLI coverage lock

| Command group | Implementation ticket |
| --- | --- |
| `--help`, `--version` | B002 |
| `init --state-only` empty state | S015 |
| state restore | G011 |
| full `init`, `setup` | R018 |
| `where`, `status` | S003 |
| `doctor` | S004 |
| `verify`, rebuild | S016 |
| bare `watari`, `chat` | R019 |
| `profile` | C001 |
| `context`, memory read | C007 |
| `remember`, candidate review, correct/forget/restore | C008 |
| `source` | A010 |
| `runtime`, `model` | R017 |
| `auth` | K005 |
| `project` | C009 |
| `dream`, auto dream | M004-M006 |
| `sync`, `conflict`, `device`, `backup` | G010 |
| `migrate claude` | L007 |

D002の`T-CLI-SCHEMA`はこの対応をmachine-readable manifestから検査し、未割当commandを許さない。

## 4. Package and repository tickets

| ID / class | Depends | 変更範囲 | 先行test・観測 | DoD |
| --- | --- | --- | --- | --- |
| B001 / L | D001,D002 | `src/watari_cli/__init__.py`, `tests/__init__.py`, root tooling files | `T-REPO-SHAPE` | B000 repo内へsrc layout、Python support、test rootを作成。repository作成責務を持たない |
| B002 / L | B001 | `pyproject.toml`, `src/watari_cli/cli/__init__.py`, `tests/packaging/test_entrypoint.py` | `T-PKG-HELP`, `T-PKG-VERSION` | PEP 621、build backend、`watari` entrypoint、help/versionがnetwork/home writeなしで動く |
| B003 / L | B002 | CI files, `scripts/smoke_install.py`, `tests/packaging/` | empty-env wheel smoke | wheel/sdist build、isolated install/uninstall、lint/test jobが固定commandで再現 |
| B004 / H | B001 | `docs/donor-components.lock.json`, `tests/donor/test_manifest.py` | donor SHA/hash verification | donor commit、module hash、port対象test、採否理由を固定。donor baselineとproduct coverageを分離 |
| B005 / L | B002,D002 | `src/watari_cli/cli/router.py`, `tests/contracts/test_cli_router.py` | machine-readable manifest/unknown/lazy-load cases | 全commandをmanifestからlazy dispatchするrouterを作り、未実装commandは明示unsupported、silent no-opなし |
| B006 / L | B003 | `scripts/lint_issue_dag.py`, `tests/packaging/test_issue_dag.py` | duplicate/missing/cycle/unreachable/bad-authority fixtures | ID unique、dependency存在、cycle/unreachable 0、critical-gate reachability、O/C AuthorityをCI検査 |

Gate B: exact wheelを空環境へinstallし、`watari --help/--version`以外のhome差分がない。

## 5. State root, cryptography, and canonical state

| ID / class | Depends | 変更範囲 | 先行test・観測 | DoD |
| --- | --- | --- | --- | --- |
| S001 / H | B002,D005 | `src/watari_cli/state/paths.py`, `tests/security/test_state_root.py` | `T-ROOT-SYMLINK`, `T-ROOT-MODE`, `T-ROOT-FS-CAPS` | WATARI_HOME resolution、owner/mode、symlink拒否、rename/fsync/lock probe、unsafe mount fail-closed |
| S002 / L | S001,D003 | `src/watari_cli/state/manifest.py`, `tests/unit/test_state_manifest.py` | `T-MANIFEST-*` | strict schema、unknown key拒否、schema/app/device metadata、secret-free serialization |
| S003 / L | S002,D002 | `src/watari_cli/cli/{where,status}.py`, `tests/contracts/test_status.py` | `T-WHERE-READONLY`, `T-STATUS-JSON`, Git index hash | `GIT_OPTIONAL_LOCKS=0`相当でhuman/JSON出力、所在/revision/pending/errorを表示し、worktree/index/ref hash不変 |
| S004 / L | S001,S002 | `src/watari_cli/cli/doctor.py`, `tests/integration/test_doctor.py` | `T-DOCTOR-CAPS`, `T-DOCTOR-DEEP-READONLY` | dependency/filesystem/runtime capabilityをread-only観測し、unsupportedを理由付き表示。`--deep`も修復・loginを実行しない |
| K001 / H | S001,S002,D005 | `src/watari_cli/config/local.py`, `tests/security/test_local_config.py` | mode/schema/symlink/unknown-key cases | device-local nonsecret config、source/runtime IDs、timezone、secret refsをstrict owner-only storeへ保存 |
| K002 / H | K001,D005 | `src/watari_cli/security/secrets.py`, `tests/security/test_secret_provider.py` | fake locked/missing/rotate/revoke/leak cases | 1Password/keychain provider interface、strict refs、shell展開なし、bounded FD/pipe注入、redacted errorsを実装 |
| K003 / O | K002 | private audit store only | `NET-SECRET-PROVIDER-QUAL`; Authority: human-injected synthetic secret, no live source/write | exact `op`/keychain versionでget/status/revoke/cleanupを観測し、credential値を保存しない |
| K004 / H | K001,D005 | `src/watari_cli/models/routes.py`, `tests/security/test_route_registry.py` | exact endpoint/fallback/ZDR/budget schema | versioned model-route registry、policy digest、capability state、unknown/mismatch fail-closed |
| K005 / H | K002,K004,D002 | `src/watari_cli/cli/auth.py`, `tests/contracts/test_auth_cli.py` | login/status/refresh/logout/revoke fake provider | auth lifecycleとsecret refsだけを扱い、global credential copy、argv/env/log leakを拒否 |
| G001 / O | D010,D011,B003,S001 | private audit store only | crypto候補×loose/packの10k/100k/tamper/wrong-key benchmark; no credential/network | audited external crypto候補とphysical layoutを同じharnessで観測し、suite/layout候補を選定 |
| G002 / H | G001,D010 | `src/watari_cli/security/codec.py`, `tests/security/test_crypto_codec.py` | tamper/wrong-key/size/allowlist vectors | 選定済みexternal implementationのbounded wrapperを実装し、allowlisted metadata以外のsemantic plaintextを拒否 |
| G003 / O | G002,D011 | private audit store only + `docs/adr/011-object-layout.md` decision | exact artifact crypto qualification; synthetic 100k state | wrong key、tamper、100k storage、cleanupを再確認し、codec versionとloose/pack layout ADRを確定 |
| G004 / H | G002,K002,D004 | `src/watari_cli/security/trust.py`, `tests/security/test_trust_anchor.py` | signer/rollback/revoke/rotation vectors | owner/device keys、signed revision、highest accepted revision、recovery record CAS、signing revokeとrecipient rotationを実装 |
| G005 / O | G003,G004,K003 | private audit store only | Authority: human-injected synthetic recovery refs; temporary remote | lost device/key、unknown signer、rollback、revoke、new device restoreを実機確認しtemporary資源を破棄 |
| S005 / H | S002,D004 | `src/watari_cli/state/generation.py`, `tests/unit/test_generation.py` | incomplete/private generation cases | next generationをprivate directoryへ構築し、未検証generationをcurrentにしない |
| S006 / H | S005,D004 | `src/watari_cli/state/journal.py`, `tests/fault/test_journal.py` | journal transition/crash vectors | PREPAREDからCOMPLETEのstrict journalとfsync順序を実装 |
| S007 / H | S006,G004 | `src/watari_cli/state/git_commit.py`, `tests/fault/test_git_ref_cas.py` | commit failure/ref race/kill cases | temporary index/tree、signed commit、expected-old-OID `update-ref` CASを実装 |
| S008 / H | S007 | `src/watari_cli/state/recovery.py`, `tests/fault/test_materialize_recovery.py` | 各遷移直前直後kill matrix | refを権威にmaterialize/recoverし、old/newどちらか一方へ収束 |
| S009 / H | S008,G003,D003,D011 | `src/watari_cli/state/events.py`, `tests/unit/test_event_store.py` | canonical/dedup/conflict/selected-layout vectors | G003で確定したlayoutへimmutable logical eventを格納し、ID検証、correction/tombstone、same-ID conflict quarantine |
| S010 / H | S009 | `src/watari_cli/profile/store.py`, `tests/unit/test_profile_store.py` | concurrent same-key update | explicit profile events、history、conflict、dream writer拒否を実装 |
| S011 / H | S009 | `src/watari_cli/dream/checkpoints.py`, `tests/unit/test_checkpoints.py` | lineage/required/quarantine cases | device/connector/lineage別checkpoint、completion key、event commit先行、max merge禁止 |
| S012 / L | S009,B004 | `src/watari_cli/memory/compat.py`, `tests/migration/test_compat_projector.py` | fixed-time legacy vectors | Heat/Freshness/30日/45日をpolicy化し、同event set/policy/evaluation timeで同digest |
| S013 / H | S010,S011,S012 | `src/watari_cli/state/derived.py`, `tests/integration/test_rebuild.py` | cache delete/rebuild/100k fixture | cacheをcanonical eventsから決定論的に再生成し、Gitへ入れない |
| S014 / H | S013,G004 | `src/watari_cli/state/verify.py`, `tests/integration/test_verify.py` | corruption/signature/fixed-time cases | `verify --at`でrevision/event/derived/checkpoint/signature digestをread-only検証 |
| S015 / H | S001,S002,S008,S009,G004,K001,K002,D002 | `src/watari_cli/cli/init_state.py`, `tests/integration/test_init_state.py` | empty/noninteractive/failure/genesis cases | `init --state-only`でtransaction経由の空state/genesisだけを作り、remote restoreやruntime setupを行わない |
| S016 / L | S013,S014,D002 | `src/watari_cli/cli/verify_rebuild.py`, `tests/contracts/test_verify_rebuild_cli.py` | root verify/memory rebuild/verify/fixed-time cases | root `verify`とmemory rebuild/verifyをhuman/JSONで実装し、rebuildだけcache write、verifyは完全read-only |

Gate S: synthetic stateだけでtamper、rollback、kill、disk-full、concurrent writer、unsafe filesystemを通過する。

## 6. Profile, context, and in-session memory

| ID / class | Depends | 変更範囲 | 先行test・観測 | DoD |
| --- | --- | --- | --- | --- |
| C001 / L | S010,D002 | `src/watari_cli/cli/profile.py`, `tests/contracts/test_profile_cli.py` | show/edit/validate/history cases | profile変更はexplicit commandだけ、schema invalidはcommitなし、history/revision表示 |
| C002 / H | D005,S009,K004 | `src/watari_cli/context/policy.py`, `tests/security/test_visibility.py` | local/trusted/low-risk deny matrix | exact route identityとvisibilityをserver-side enforceし、model要求で昇格不可 |
| C003 / H | K001,D009 | `src/watari_cli/context/projects.py`, `tests/security/test_project_trust.py` | untrusted/changed/auto-discovered AGENTS cases | project root/instruction digestを明示trust/revokeし、未承認自動発見を拒否またはmanaged clean cwdへ隔離 |
| C004 / H | C001,C002,C003,S014,D003 | `src/watari_cli/context/compiler.py`, `tests/unit/test_context_compiler.py` | budget/order/canonical/effective fingerprint | bounded context、semantic precedence、project/runtime layer、採否理由、policy/revisions込み2種fingerprintを決定論生成 |
| C005 / H | C004,D009,Z002 | `src/watari_cli/context/retrieval.py`, `tests/security/test_retrieval_service.py` | raw-ID/all-data/route-swap/same-UID cases | route/revision固定capability、search/get/explain projection、ID/bytes audit、直接writeなし、sandbox外path非公開 |
| C006 / H | C002,S009 | `src/watari_cli/memory/candidates.py`, `tests/unit/test_candidates.py` | accept/reject/source-binding | manual/session proposalをimmutable candidateへ限定し、review decisionなしでevent化しない |
| C007 / L | C001,C004,C005,S014,D002 | `src/watari_cli/cli/context_memory_read.py`, `tests/contracts/test_context_memory_read_cli.py` | build/explain/list/search/show/verify cases | context/memory read commandsをversioned human/JSONで実装し、read前後hash不変 |
| C008 / H | C006,S009,D002 | `src/watari_cli/cli/memory_write.py`, `tests/contracts/test_memory_write_cli.py` | remember/candidate/correct/forget/restore cases | source-bound review、correction/tombstone/restoreをtransaction経由で実装し、直接object改変なし |
| C009 / L | C003,D002 | `src/watari_cli/cli/project.py`, `tests/contracts/test_project_cli.py` | list/trust/inspect/revoke cases | project trust lifecycleとeffective digest差分を表示し、変更時は再承認要求 |

Gate C: 100k synthetic eventでもbudget内、local-only egress 0、同一inputのfingerprint一致、untrusted project
instruction適用0、global AI config差分0。外部model runtimeはsame-UID permissionに依存せずZ001-Z002を通す。

### Runtime sandbox tickets

外部modelを起動するsupported runtimeは、same-UID trustを安全境界にせず次を必須にする。

| ID / class | Depends | 変更範囲 | 先行test・観測 | DoD |
| --- | --- | --- | --- | --- |
| Z001 / H | D005,D006 | `docs/sandbox-contract.md`, `tests/contracts/test_sandbox_contract.py` | mount/network/process/capability deny matrix | state/key非mount、approved project read、route-bound retrieval FD/socket、network allowlist、resource/cleanup contractを固定 |
| Z002 / H | Z001,B004 | `src/watari_cli/security/sandbox.py`, `tests/security/test_sandbox.py` | fake bwrap/netns/broker escape cases | donor isolation部品をmanifest経由で移植し、direct DNS/network、state/key/path escape、child残留を拒否 |
| Z003 / O | Z002,R003,K003 | private audit store only | Codex sandbox exact-artifact qualification; Authority: human auth, synthetic prompt | mount/network capture、retrieval capability、Ctrl-C/cleanupを実測 |
| Z004 / O | Z002,R006,K003 | private audit store only | Pi/Codex sandbox exact-artifact qualification; Authority: human auth, synthetic prompt | mount/network/output/resource/cleanupを実測 |
| Z005 / O | Z002,R009,K003 | private audit store only | Pi/OpenRouter sandbox exact-artifact qualification; Authority: dedicated key, synthetic prompt | exact endpoint以外egress 0、state/key非可視、budget/cleanupを実測 |
| Z006 / O | Z002,R012,K003 | private audit store only | Claude sandbox exact-artifact qualification; Authority: configured human auth, synthetic prompt | configured auth/context/session経路のmount/network/cleanupを実測 |
| Z007 / O | Z002,R015,K003 | private audit store only | OpenCode sandbox exact-artifact qualification; Authority: configured human auth, synthetic prompt | configured versionのpermission/mount/network/cleanupを実測 |

## 7. Runtime and source adapters

| ID / class | Depends | 変更範囲 | 先行test・観測 | DoD |
| --- | --- | --- | --- | --- |
| R001 / L | D006,C004,C005,K004 | `src/watari_cli/runtimes/base.py`, fake runtime, `tests/contracts/test_runtime_base.py` | PTY/structured/session/tool fake cases | detect/qualify/chat/structured/session receipt/tools/explainのcontractとsecret-free capability report |
| A001 / L | D007,S011 | `src/watari_cli/sources/base.py`, fake source, `tests/contracts/test_source_base.py` | pagination/drift/dedup fake cases | stable identity、incremental scan、role、lineage、checkpoint proposal、unknown format fail-closed |
| A002 / H | A001,B004 | `src/watari_cli/sources/claude.py`, `tests/contracts/test_source_claude.py` | donor synthetic fixtures | Claude Windows/WSL形式をstrict parseし、user/assistant/tool/systemを区別。live pathを開かない |
| A003 / H | A001,B004 | `src/watari_cli/sources/codex.py`, `tests/contracts/test_source_codex.py` | donor synthetic fixtures | Codex JSONL drift、turn identity、partial record、symlink escapeを処理 |
| A004 / H | A001,B004 | `src/watari_cli/sources/pi.py`, `tests/contracts/test_source_pi.py` | session-v3 fixtures | high-trust Piだけsource化し、OpenRouter/no-session/unknown rootsを拒否 |
| A005 / O | A001 | private audit store only | local clean-root OpenCode source-format observation; no auth | official install/config/session format/versionを観測しsynthetic fixtureを作る。未観測fieldは推測しない |
| A006 / H | A005,A001 | `src/watari_cli/sources/opencode.py`, `tests/contracts/test_source_opencode.py` | frozen A005 fixtures | observed formatだけstrict parseし、unknown versionはunsupported |
| A007 / O | A006 | private audit store only | exact artifact clean-root source qualification | generated sessionのidentity/append/driftを再観測しadapter rangeを固定 |
| A008 / H | A001,K001 | `src/watari_cli/sources/registry.py`, `tests/unit/test_source_registry.py` | configured/disabled/unknown/duplicate cases | device-local source registry、required/optional、owner/coordinator、adapter versionをstrict管理 |
| A009 / H | A002,A003,A004,A008 | `src/watari_cli/sources/scanner.py`, `tests/integration/test_source_scan.py` | multi-source snapshot/drift/partial cases | configured sourceのstable snapshot、incremental scan、dedup、partial result、checkpoint proposalを統合 |
| A010 / L | A008,A009,D002 | `src/watari_cli/cli/source.py`, `tests/contracts/test_source_cli.py` | list/add/inspect/test/disable/remove cases | source lifecycleをhuman/JSON表示し、testはsynthetic/read-only、unknownを有効化しない |
| A011 / H | A001,R001 | `src/watari_cli/sources/watari_session.py`, `tests/security/test_watari_session_source.py` | route/role/dedup/provider-output cases | Watari-owned owner-only session receiptをscanし、user turnだけ一次根拠、provider outputはunverified context、native logとdedup |
| R002 / O | R001 | private audit store only | local Codex flags/config/session observation; no auth request | exact version、CODEX_HOME、instruction/project discovery、PTY/JSONL/session pathを記録しfixture化 |
| R003 / H | R002,R001,C003,C004,K005,Z002 | `src/watari_cli/runtimes/codex.py`, `tests/integration/test_runtime_codex.py` | frozen R002 fake executable/fixtures | sandbox内dedicated CODEX_HOME、approved project layer、explicit context、PTY/exit/session receiptを実装 |
| R004 / O | R003,Z003,K003 | private audit store only | `NET-CODEX-QUAL`; Authority: human auth, synthetic prompt, no live source/write | exact artifactでauth/context/session/sandbox/network captureを検証しqualified rangeを登録 |
| R005 / O | R001 | private audit store only | local Pi/OpenAI-Codex config/CLI observation; no provider request | exact Pi/version/flags/state paths/structured I/Oをfixture化 |
| R006 / H | R005,R001,C002,K004,K005,Z002 | `src/watari_cli/runtimes/pi_codex.py`, `tests/integration/test_runtime_pi_codex.py` | frozen fake provider fixtures | sandbox内trusted route、bounded stdin/output、isolated state、session receipt、exact route enforcementを実装 |
| R007 / O | R006,Z004,K003 | private audit store only | `NET-PI-CODEX-QUAL`; Authority: human auth, fixed synthetic request | provider/model/context/egress/auth/sandboxをexact artifactで検証しcleanup |
| R008 / O | R001,D001 | private audit store only | OpenRouter metadata/privacy/price/endpoint observation; no model call | exact candidate model/provider、fallback、ZDR/retention、credit/spend/request boundsを記録 |
| R009 / H | R008,R001,C002,K004,K005,Z002 | `src/watari_cli/runtimes/pi_openrouter.py`, `tests/security/test_runtime_openrouter.py` | frozen metadata/fake provider | sandbox内low-risk projection、exact endpoint、fallback off、budget、dedicated secret ref、local session receiptを実装 |
| R010 / O | R009,Z005,K003 | private audit store only | `NET-OPENROUTER-QUAL`; Authority: dedicated key, fixed synthetic request | exact artifact/routeでprivacy metadata、request/network capture、credit/spend/cleanupを検証。utility/trusted区分を表示 |
| R011 / O | R001 | private audit store only | local Claude flags/config/session observation; no auth request | safe/bare、CLAUDE_CONFIG_DIR、customization isolation、PTY/JSONL/sessionをOAuth/API-key別に記録 |
| R012 / H | R011,R001,C003,C004,K005,Z002 | `src/watari_cli/runtimes/claude.py`, `tests/integration/test_runtime_claude.py` | frozen R011 fake executable/fixtures | sandbox内の観測済み経路だけexplicit context、global customization無効、session receipt、fail-closedを実装 |
| R013 / O | R012,Z006,K003 | private audit store only | `NET-CLAUDE-QUAL`; Authority: human auth, synthetic prompt | configured auth経路だけexact artifactでcontext/auth/session/sandboxを検証しcleanup |
| R014 / O | A005,R001 | private audit store only | clean-root OpenCode runtime observation; authなし | official config root、permission、PTY/structured/context/session behaviorをfixture化 |
| R015 / H | R014,R001,C003,C004,K005,Z002 | `src/watari_cli/runtimes/opencode.py`, `tests/integration/test_runtime_opencode.py` | frozen R014 fixtures | sandbox内で観測済みversionだけconfig isolation/context/PTY/session receiptを実装 |
| R016 / O | R015,Z007,A007,K003 | private audit store only | `NET-OPENCODE-RUNTIME-QUAL`; Authority: configured human auth, synthetic prompt | exact artifactでauth/context/session/permission/sandboxを検証しcleanup |
| R017 / L | R001,A008,K001,K004,K005,S015,D002 | `src/watari_cli/cli/runtime_model.py`, `tests/contracts/test_runtime_model_cli.py` | fake list/add/default/test/disable/remove | generic runtime/model registryとnoninteractive setupを実装し、live qualificationなしでもunsupported状態を管理 |
| R018 / L | R017,A010,S015,G011 | `src/watari_cli/cli/setup.py`, `tests/integration/test_setup_wizard.py` | scripted empty/restore/setup/cancel/resume | bare `watari init`がempty S015またはrestore G011後にruntime/model/source/timezoneを段階設定し、`--state-only`も維持。secret値を保存せずpartial activationしない |
| R019 / H | R017,C004,C005,A011,M006 | `src/watari_cli/application/chat.py`, `tests/integration/test_chat_dispatch.py` | fake PTY/Ctrl-C/context/auto-dream/receipt cases | bare `watari`/`watari chat`がfirst-launch dream後にselected runtimeへcontext/retrieval/receiptを渡し、裸CLIへ影響しない |

Gate R/A: private pilot必須はA002-A004/A008-A011、R003-R010、R017-R019で、R004/R007/R010の
live synthetic qualificationを含む。public `supported`表示はD001のmatrixに入り、clean E2Eを通ったadapterだけにする。

## 8. Dream pipeline and synchronization

| ID / class | Depends | 変更範囲 | 先行test・観測 | DoD |
| --- | --- | --- | --- | --- |
| M001 / H | A009,S009,C002 | `src/watari_cli/dream/candidates.py`, `tests/unit/test_candidate_manifest.py` | role/evidence/prompt-injection cases | scan resultからuser-authored/verified activity中心のcontent-bound manifestを作り、system/unverified tool/subagentを根拠にしない |
| M002 / H | M001,R001,K004 | `src/watari_cli/dream/decisions.py`, `tests/security/test_decision_validation.py` | schema/source-binding/injection | structured outputをstrict validateし、candidate外ID、profile change、external actionを拒否 |
| M003 / H | M002,S007,S008,S011,S013,G004 | `src/watari_cli/dream/apply.py`, `tests/fault/test_dream_apply.py` | model/Git/kill/disk-full matrix | events、checkpoints、dream manifestを同じsigned commitへ入れ、failureでcheckpoint不変 |
| M004 / L | M003,D002 | `src/watari_cli/cli/dream.py`, `tests/contracts/test_dream_cli.py` | dry-run/history/partial exit 60 | dry-run変更0、source別success/failure、history、pendingをhuman/JSON表示 |
| M005 / H | M001,M002,M003,A009,R001 | `src/watari_cli/application/dream.py`, `tests/integration/test_dream_orchestrator.py` | no-source/partial/model-failure/retry cases | registry→snapshot→scan→route→validate→applyをsource別に統合し、failureを成功扱いしない |
| M006 / H | M004,M005,R017 | `src/watari_cli/dream/auto.py`, `tests/integration/test_auto_dream.py` | concurrency/DST/timezone/offline | `watari`起動時だけ判定、device-due required key、同日/同時1回、失敗時再試行、daemonなし |
| G006 / H | G004,S007,K002 | `src/watari_cli/sync/git.py`, `tests/integration/test_sync_git.py` | two-clone/ahead/behind/diverge | signed revision conditional pull/push、force pushなし、RPO/divergence表示 |
| G007 / H | G006,K002 | `src/watari_cli/sync/anchor.py`, `tests/fault/test_anchor_update.py` | push/re-fetch/anchor-CAS各kill点、two-device race | push→remote再取得検証→old-anchor条件付きrecovery record更新を実装し、失敗時`anchor stale`で新push停止 |
| G008 / H | G006,S010,S011 | `src/watari_cli/sync/conflicts.py`, `tests/security/test_sync_conflicts.py` | profile/checkpoint/coordinator epoch attacks | immutable set merge、semantic conflict quarantine、owner-signed coordinator transfer、offline shared-source拒否 |
| G009 / H | G007,G008 | `src/watari_cli/sync/backup.py`, `tests/integration/test_backup_restore.py` | lost key/device/remote/rollback drill | encrypted backup create/verify/restore、minimum trusted revision、別端末digest一致、revoked recipient除外 |
| G010 / L | G006,G008,G009,D002 | `src/watari_cli/cli/sync_device_backup.py`, `tests/contracts/test_sync_device_backup_cli.py` | sync/conflict/device/backup command cases | 全sync/device/backup CLIをversioned出力で実装し、force/implicit conflict resolutionを提供しない |
| G011 / H | G005,G009,S008,S014,K002,D002 | `src/watari_cli/cli/restore_state.py`, `tests/integration/test_restore_state.py` | clone/bundle/min-revision/tamper/materialize/verify cases | remote/bundleをtemporary rootへ取得し、trust anchor→decrypt→materialize→strict verify後だけcurrentへ切替える |
| I001 / H | A002,A003,A004,A009,A011,R003,R006,M004,M005,C005 | `tests/e2e/test_session_dream_retrieval.py` | synthetic runtime session→scan→dream→other runtime retrieval | concrete Claude/Codex/Pi sourceとfake/implemented runtimeを通し、user turnが別runtimeから同revisionで取得できる |

Gate M/G: model failure、capacity、invalid JSON、tamper、rollback、2-device conflictのどれも記憶欠損やcheckpoint先行を起こさない。

## 9. Legacy migration

| ID / class | Depends | 変更範囲 | 先行test・観測 | DoD |
| --- | --- | --- | --- | --- |
| L001 / H | D012,B004 | `src/watari_cli/migration/inspect.py`, `tests/migration/test_inspect.py` | synthetic symlink/permission/dirty Git/scope cases | CLAUDE/persona/design/schema/knowledge/schedule/log/state/cursor/evidenceをscope manifest化し、writer riskとcredential候補をread-only報告 |
| L002 / H | L001,G002,G004,K002 | `src/watari_cli/migration/snapshot.py`, `tests/migration/test_snapshot.py` | writer-stop precondition、source-before/after hash、wrong signer | 全legacy writer停止を前提にscope raw bytesをauthoritative lossless capsuleへcopyし、signed manifestを作る。source write 0 |
| L003 / H | L002,D003 | `src/watari_cli/migration/plan.py`, `tests/migration/test_plan.py` | legacy-line mapping/active-quarantine vectors | 全raw digestをevent/quarantineへmapし、host path除去、default local-only、fixed evaluation time、active row quarantine停止 |
| L004 / H | L003,D005 | `src/watari_cli/migration/review.py`, `tests/migration/test_review_artifact.py` | stale digest/partial/low-risk elevation cases | profile/visibility/quarantine decisionをsnapshot+event-set digestへ署名可能にし、trustedだけ明示昇格、low-risk自動昇格なし |
| L005 / H | L004,S009,S010,S011,S012 | `src/watari_cli/migration/importer.py`, `tests/migration/test_import.py` | idempotency/interruption/conflict | approved reviewからcopy-on-write generationへimportし、unresolved active quarantineを拒否 |
| L006 / H | L005,S014,G006,C004 | `src/watari_cli/migration/verify.py`, `tests/migration/test_verify.py` | count/digest/parity/checkpoint/context cases | capsule completeness、全行mapping、fixed-time derived parity、checkpoint、Git revision、trusted context parityを照合 |
| L007 / L | L001,L002,L003,L004,L005,L006,D002 | `src/watari_cli/cli/migrate.py`, `tests/contracts/test_migrate_cli.py` | inspect/snapshot/plan/import-dry/apply/verify cases | migration全CLI、default dry-run、explicit target、content-free report、stable exit codesを実装 |
| L008 / H | L006,G004 | `src/watari_cli/migration/stop_attestation.py`, `tests/security/test_stop_attestation.py` | digest/revision/expiry/replay/mutated-source cases | final capsule、target revision、legacy writer停止、expiryをowner署名し、一回消費できるgateを実装 |
| L009 / H | L001,G002,G004 | `src/watari_cli/migration/shadow.py`, `tests/migration/test_shadow_capsule.py` | repeat-scan stable/changed/writer-active cases | writer稼働中でもscan前後hash一致範囲だけ非権威rehearsal capsule化し、final import対象としては必ず拒否 |
| L010 / H | L009,L003,L004,S009,S014 | `src/watari_cli/migration/rehearsal.py`, `tests/migration/test_rehearsal_import.py` | state-ID/current-pointer/canary refusal cases | shadow capsuleを別state IDの`rehearsal_only=true` generationへだけimportし、production current/attestation/canaryで拒否 |
| I002 / H | L008,M003 | `src/watari_cli/application/dream_cutover_guard.py`, `tests/integration/test_first_production_dream_gate.py` | missing/stale/replayed attestation | migrated stateの最初のproduction dreamだけvalid stop attestationを必須にし、target/source変更時は拒否 |
| I003 / H | B005,S003,S004,S016,R018,R019,C001,C007,C008,C009,A010,R017,K005,M004,G010,L007,X011 | `src/watari_cli/cli/router.py`, `tests/e2e/test_cli_dispatch.py` | exact wheel全command subprocess/status aggregation | machine manifestの全commandが実moduleへ到達し、runtime/source/dream/sync/migration statusを統合、未配線0 |
| I004 / H | I002,M004,M005,M006,R019 | `src/watari_cli/application/dream.py`, `tests/e2e/test_cutover_guard_wiring.py` | manual/auto/chat missing-stale-replay cases | manual dream、auto dream、chat pre-dreamの全共通入口がmigrated stateでguardを必須実行 |

Gate L: synthetic treeでlossless、idempotent、read-only、rollback可能。`event + approved quarantine = legacy全行`、
active derived rowの未解決quarantine 0。live rootのshadow/final snapshot/applyはQ009/Q011以外で行わない。

## 10. External connectors and optional actions

| ID / class | Depends | 変更範囲 | 先行test・観測 | DoD |
| --- | --- | --- | --- | --- |
| X001 / H | D008,A001,C002,K002 | `src/watari_cli/connectors/base.py`, fake HTTP, `tests/contracts/test_connector_base.py` | pagination/429/timeout/auth/injection | read scope、classification、credential reference、identity、checkpoint、retry、required/optional contract |
| X002 / H | X001 | `src/watari_cli/connectors/obsidian.py`, `tests/contracts/test_connector_obsidian.py` | synthetic vault/symlink/large file | explicit rootsだけread、frontmatter/content identity、symlink escape拒否、no write |
| X003 / H | X001 | `src/watari_cli/connectors/linear.py`, `tests/contracts/test_connector_linear.py` | frozen fake API pagination/rate/edit/delete | least-privilege read contract、updated/deleted identity、retry、write method不在を実装 |
| X004 / O | X003,K003 | private audit store only | `NET-LINEAR-READ-QUAL`; Authority: human read token, fixed synthetic/approved test issue, no write | exact scope/pagination/rate/token revokeを観測しcleanup |
| X005 / H | X001 | `src/watari_cli/connectors/gmail.py`, `tests/contracts/test_connector_gmail.py` | frozen fake Gmail pagination/sent/token-expiry | Gmail read-only instance、message/thread identity、raw retention最小化を実装 |
| X006 / O | X005,K003 | private audit store only | `NET-GMAIL-READ-QUAL`; Authority: human read token, approved mailbox query, no write | exact scope/pagination/sent identity/revokeを観測しcontentを保存しない |
| X007 / H | X001 | `src/watari_cli/connectors/calendar.py`, `tests/contracts/test_connector_calendar.py` | frozen fake Calendar pagination/edit/delete | Calendar read-only instance、event/recurrence identity、raw retention最小化を実装 |
| X008 / O | X007,K003 | private audit store only | `NET-CALENDAR-READ-QUAL`; Authority: human read token, approved calendar query, no write | exact scope/pagination/recurrence/revokeを観測しcontentを保存しない |
| X009 / H | X001 | `src/watari_cli/connectors/slack.py`, `tests/contracts/test_connector_slack.py` | frozen fake channel/thread/edit/delete API | least-privilege read、channel/thread identity、prompt injection隔離を実装 |
| X010 / O | X009,K003 | private audit store only | `NET-SLACK-READ-QUAL`; Authority: human read token, approved channels, no write | exact scope/pagination/edit/delete/revokeを観測しcontentを保存しない |
| X011 / H | X002,X003,X005,X007,X009,A008,A009,M001,M003,M005,S003,S011,S013,G008,C002 | `src/watari_cli/connectors/bridge.py`, `tests/integration/test_connector_dream_bridge.py` | connector→candidate→signed event/checkpoint/status partial/quarantine/coordinator cases | configured connectorをsource eventへ変換し、event/checkpoint同一commit、classification/visibility/coordinator/partial/statusをE2E接続 |
| X012 / H | X002,M003 | `src/watari_cli/actions/journal.py`, `tests/integration/test_journal_action.py` | fake vault write failure/duplicate/authorization | optional Journal writerをmemory transactionから分離し、explicit authorization/audit/idempotencyを実装 |
| X013 / C | X012 | private audit store only | Authority: approved test noteへのexternal write、approval ID必須 | exact targetへ1件write/verify/cleanupし、memory failureと独立することを確認 |
| X014 / H | X003,X005,X009,X017,C006 | `src/watari_cli/actions/external_completion.py`, `tests/integration/test_external_completion.py` | fake Gmail/Linear/Slack sequence | 実source確認→current task→write専用adapter→memory candidate→再確認を別transactionで実装 |
| X015 / C | X014,X004,X006,X010,X018 | private audit store only | Authority: individually approved external writes、approval ID/targets固定 | exact test objectsで順序・監査・部分失敗・revokeを確認し、dream modelへwrite authorityを渡さない |
| X016 / H | K002,D008 | `src/watari_cli/actions/writers.py`, `tests/contracts/test_action_writer.py` | read-ref reuse/write-scope/authorization/revoke fake cases | write専用secret ref、scope、per-action authorization、idempotency/audit contractをread connectorから分離 |
| X017 / H | X016,X003 | `src/watari_cli/actions/linear_writer.py`, `tests/contracts/test_linear_writer.py` | fake comment/state/current-workflow/partial cases | Linear comment/status updateをwrite専用credentialで実装し、workflow名をread adapterの現在値から解決、read token流用拒否 |
| X018 / C | X017,K003 | private audit store only | Authority: approved test issue/comment/state、dedicated write token、approval ID | exact test issueでwrite/verify/revoke/cleanupを行い、token scopeとauditを確認 |

Gate X: connectorごとに独立release gateを持つ。read credentialからwrite scopeを推測せず、dream modelにwrite authorityを渡さない。

## 11. Release, clean-room, and cutover

| ID / class | Depends | 変更範囲 | 先行test・観測 | DoD |
| --- | --- | --- | --- | --- |
| Q001 / H | S014,M005,G009,L006,I001,Z003,Z004,Z005 | `tests/security/test_release_security.py` | route/sandbox/path/injection/tamper/rollback matrix | release security invariantsを1 suiteへ固定し、認識対象credential/semantic plaintext leakを検査 |
| Q002 / H | S008,M003,G007 | `tests/fault/test_release_faults.py` | kill/disk-full/read-only-fs/network/CAS matrix | 全transaction/anchor境界でold/new収束、checkpoint先行0、recoverabilityをCI化 |
| Q003 / H | D011,S013,C004,M005,G009 | `tests/performance/test_release_scale.py` | 10k/100k create/status/clone/rebuild/context/backup | storage ADRのbudgetを満たし、回帰閾値を固定。超過時はrelease停止 |
| Q004 / H | B003,S015,L006 | `tests/packaging/test_upgrade_matrix.py` | install/uninstall/schema-upgrade/downgrade refusal | supported version間upgrade、copy-on-write migration、unsupported downgrade fail-closedをCI化 |
| Q005 / H | Q001,Q002,Q003,Q004,I003,B006 | release workflow, `docs/release.md`, SBOM config | reproducible-build/CLI-dispatch comparison | signed tag/wheel/checksum/provenance、SBOM、dependency audit、recognized-credential scan、all-command smokeを実装 |
| Q006 / O | Q005 | private audit store only | two clean builders + pre-registered release key | reproducible artifact、signature/checksum/provenanceを配布元と別trust sourceで検証 |
| Q007 / H | Q006,R019,I001,I003,G011,L006,K003,Z003,Z004,Z005 | `scripts/clean_room_acceptance.py`, `docs/clean-room.md` | disposable clean user/VM scripted rehearsal | home diff、verified install、all-command dispatch、separate Git auth、secret injection、read-only restore、disposable destructive state、runtime/sandbox matrix、uninstallを自動化 |
| Q008 / C | Q007,L001,D001 | private audit store only; product repoにはschema/synthetic例だけ | Authority: live feature inventory read-only、approval ID | 現行機能とbehavior差分の分類draftを作る。即時ingest→candidate review変更も含め、実装証拠またはwaiver候補を列挙するがまだ署名しない |
| Q009 / C | Q007,Q008,L007,L009,L010,R004,R007,R010,I001,G005 | private audit store only | Authority: approved live roots read-only、human-injected auth、networkはqualification allowlistのみ | live shadow scan→rehearsal-only state→clean PC read-only restore/fixed-time verify/context comparison。live source前後digest不変 |
| Q010 / C | Q007,R004,R007,R010,M006,G005,G009,I001 | private audit store only | Authority: separate state ID/key/temporary remote、synthetic prompt、no BINGE state | disposable stateでdream/auto/two-device/conflict/tamper/rollback/lost-keyを実施し全資源cleanup |
| Q011 / C | Q009,Q010,L002,L007 | private audit store only | Authority: approved legacy roots read、all legacy canonical writers stopped、final capsule write | final stable/delta authoritative capsuleを取得し、旧writer停止を継続。まだtarget import/canaryを行わない |
| Q012 / C | Q008,Q009,Q011 | private audit store only | Authority: final capsule digest、binge署名 | 各feature行をcompletion/evidence digestまたは署名済みwaiverへ結び付け、final capsuleでfeature-bearing fileが変化した場合は再review。未分類0 |
| Q013 / C | Q011,Q012,L008,I004,G007 | private audit store only | Authority: final capsule read、new target write、legacy writer stopped | final review/import/sync/strict verify後、target revisionへboundしたone-shot stop attestationを作る。旧writerは再開しない |
| Q014 / C | Q013,R019,I004,M006 | private audit store only | Authority: one approved canary batch、new target write、external actionなし | attestationを消費してtarget canary、journal/memory/checkpoint/push/writer count=1を確認。source runtimeだけ再開可 |
| Q015 / C | Q014,G009 | private audit store only | Authority: user-defined duration、production read/dream/sync/backup、external actionなし | observation window中のdream、sync、backup、writer count、legacy停止、error budgetを監視し、期間満了と未解決incident 0を記録 |
| Q016 / O | Q015,Q006,Q007,D001 | `docs/public-release-matrix.md`, public artifact inspection report | clean supported-runtime E2E、license/package/privacy decision | public matrix、experimental区分、package name、license、BINGE固有data不在を判定する。registry writeは行わない |
| Q017 / C | Q016 | private release audit store | Authority: exact artifact digest、registry、package name/version、approval ID | signed artifactを指定registryへ1回publishし、公開内容/digestを再取得検証する。Claude解約はQ015後の別ユーザー操作 |

Q013/Q014だけがproduction canonical stateへ新規書込みを行う。開始前にbingeがapproval ID、対象root、停止時刻、canary batch、
recovery authorityを明示し、legacy canonical writer停止を独立確認する。

## 12. Ticket completion record

各issueには次の機械可読なcompletion blockを残す。

```yaml
issue: S003
base_sha: "<sha>"
dependency_shas: ["<sha>"]
changed_paths: []
tests:
  - command: "uv run pytest tests/contracts/test_status.py -q"
    exit: 0
full_suite:
  command: "uv run pytest -q"
  exit: 0
network_used: false
live_data_used: false
credential_access: none
live_source_read: false
external_write: false
network_scope: []
approval_id: null
review_class: L
reviewer: "<independent reviewer>"
cleanup_or_rollback: "git revert <sha>"
artifact_digests: {}
known_limits: []
```

`network_used`または`live_data_used`がticket contractと矛盾した場合は成果を破棄し、credential
rotationとleak reviewを先に行う。completion block、CI、reviewの三つが揃うまでdependencyを満たした
扱いにしない。
