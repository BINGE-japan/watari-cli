# Watari CLI 製品化・移行実装計画

Status: design baseline / implementation not started
Date: 2026-07-17
Target: private pilot first, public package only after clean-room acceptance

この文書は Watari CLI の実装順序と合格条件の正本である。現行 Watari、
`new-watari`、ライブ記憶、AI の設定、スケジューラを変更する許可ではない。

## 1. 結論

Watari CLI は、Claude 用スキルをそのままパッケージ化するのではなく、次の4領域を
分離したローカルファースト CLI として新設する。

```text
watari-cli             公開可能なアプリ本体
$WATARI_HOME/state     ユーザー固有の profile・記憶・同期状態（Git）
$WATARI_HOME/runtime   AI CLI のセッション・一時物（Git 対象外）
Secret Store           OAuth・API key・暗号鍵（Git 対象外）
```

`watari` を実行した時だけ Watari が起動し、通常の `codex`、`claude`、
`opencode`、シェル、各プロジェクトには影響を与えない。すべてのランタイムが同じcanonical
profile revisionとmemory revisionを参照し、routeに許可されたcontext fingerprintを渡すことで
同一性を検証する。
モデルごとの応答文の一致は同一性の条件にしない。

実装は新しい private repository `watari-cli` で行う。`new-watari` は移行研究と
検証済み部品の履歴として保持し、直接リネームして製品リポジトリにはしない。
ライブ記憶 Git は最終カットオーバーまで唯一の正本のままにする。

## 2. ユーザー要求と受け入れ条件

| 要求 | 検証可能な受け入れ条件 |
| --- | --- |
| 普段は影響しない | install/init 後も `~/.claude`、`~/.codex`、`~/.pi`、project files、shell startup files、scheduler に無断変更がない。裸の各AI CLIの起動時に Watari context が入らない |
| `watari` でだけ現れる | `watari` または `watari chat` から起動したセッションだけが canonical context を受け取る |
| 初回にAIとツールを設定 | `watari init` が runtime、対話モデル、dreamモデル、source connector、state Git、timezoneを設定し、接続テスト結果を保存する |
| 全AI会話を夢で見る | `watari`から起動したsupported session streamのuser/assistant/tool/system roleを識別して走査し、前回成功位置以降だけを処理する。記憶の根拠にできるroleは別policyで制限し、未対応・未接続・失敗を成功と表示しない。low-risk routeを完全なWatariと呼ぶかはdecision gateで明示する |
| 接続ツールも夢で見る | 明示的に有効化された read-only connector だけを走査し、最終成功・遅延・失敗を `watari status` に表示する |
| `watari dream` | dry-run、source指定、履歴確認ができ、モデル失敗時に checkpoint を進めない |
| 1日最初の起動で自動dream | ユーザーtimezoneにおける最終成功日で判定し、同日2回・同時2プロセスでも1回だけ実行する |
| profileを編集 | profileは明示的な `show/edit/validate/history` でのみ変更でき、dreamは人格・規則を勝手に変更しない |
| 全ランタイムで同じWatari | 全adapterが同じcanonical revisionを参照し、同じroute policyなら同じcontext fingerprintを受け取る。visibilityの異なるrouteを同一機能と称さず、runtime固有の追加情報は別レイヤーとして表示する |
| 別PCで復元 | clean PCでアプリとstateを復元し、profile、memory event set、derived view、checkpointのdigestが一致する |
| 他ユーザーも導入できる | restore指定なしの`watari init`は、そのユーザー専用の空state、device identity、recovery手順を作る。BINGEのprofile・記憶・鍵・pathを含まない |
| どこに何があるか分かる | `where/status/context explain/memory explain/dream show` が、保存先・根拠・同期状態・モデル送信範囲を表示する |

### 非目標

- installしただけで常駐daemon、cron、systemd、Windows Task Schedulerを作らない。
- dreamからメール送信、Slack投稿、Linear更新などの外部書き込みをしない。
- 「接続可能なあらゆるサービス」を実装済みと称さない。
- 安価なモデルへ全記憶・全connectorデータを無条件に送らない。
- AIモデルの出力を検証せず直接canonical stateへ書かせない。
- 既に開いている他社CLIセッションへの後付け注入をv1の保証に含めない。

### 現行機能の移行先

| 現行機能 | Watari CLIでの移行先 |
| --- | --- |
| `/watari` のpull-only起動 | `watari` / `watari chat` |
| 関連stateを読み、必要時にlog詳細を読む | bounded initial context + Watariセッション専用のread-only memory retrieval tool |
| 毎夜の会話整理 | `watari dream` + first-launch auto dream |
| その場の重要事実のingest | `watari remember`、またはセッション専用toolが作る未確定candidateを明示review後にcommit |
| 中央目録 | `watari where/status/source list`。孤立stateを`doctor`で検出 |
| Obsidian日報 | core memoryとは分けたoptional Journal plugin。外部writeなので明示設定・個別監査対象 |
| 外部action完了時のGmail確認・Linear更新 | dreamから分離した将来のaction workflow plugin。read-only connector完成後に別authorizationで実装 |

## 3. 観測済みの現状

### 現行 Watari

- 人格は `~/.claude/CLAUDE.md`、Watari仕様は
  `~/.claude/skills/watari/`、記憶はその配下のprivate Gitにある。
- 記憶は `life` / `learning` の追記型 `log.jsonl` が正本、`state.json` が
  派生物、`cursors.json` が共有checkpointである。
- current policy には heat、freshness、30日減衰、45日thread closeがある。
- Claude Desktop Routineがproduction writerで、ライブ記憶は観測中にも変化し得る。
- `watari` shell command は存在しない。

### `new-watari`

- 本計画作成開始時のGitは`b5f5260`でclean/pushedだった。現在は本計画、issue DAG、READMEリンクが
  未commitのstaging差分であり、製品実装はまだない。既存の契約テストはPython 121件とshell/Pi
  契約を含めて合格した。
- `pyproject.toml` は `package = false`、version `0.0.0`、console entry pointと
  build-systemがなく、installable packageではない。
- 再利用候補は strict transcript adapters、atomic MemoryEngine、native-v3 writer、
  secret redaction、model policy、egress controlsである。
- profile管理、OpenCode adapter、一般ユーザー向けinit、複数PC同期、復元、外部tool
  connector、auto dreamは未実装である。
- native-v3は移行ライターとして強固だが、公開CLIの通常dreamとしては承認フローと
  単一ホスト前提が過剰または不一致な箇所がある。部品単位で採否を決める。

### 実機CLI（2026-07-17観測）

| Runtime | 観測 | 計画上の扱い |
| --- | --- | --- |
| Codex CLI | 0.144.4。`CODEX_HOME`、`model_instructions_file`、JSONL出力、isolated configが利用可能。project `AGENTS.md` は別レイヤーとして自動発見され得る | adapter qualificationを行い、Watari専用`CODEX_HOME`と明示context fileを使う |
| Claude Code | 2.1.212。`CLAUDE_CONFIG_DIR`、`--safe-mode` / `--bare`、system prompt、stream JSONがある。`--bare`は通常OAuthを読まない | OAuth/API key別に実機qualificationし、暗黙のglobal customizationを無効化できた経路だけ対応 |
| OpenCode | このマシンには未導入 | 公式CLI・保存形式・config isolationを実機観測するまでunsupported |
| Pi | package-local 0.80.7のみ、global commandなし | optional runtime。versionを固定し、stateは`$WATARI_HOME/runtime/pi`に隔離 |

各CLIは更新で契約が変わり得る。対応可否は名前ではなくversioned capability testで決める。

## 4. 固定する設計判断

### ADR-001: アプリとユーザーstateを分離する

`watari-cli`にはコード、schema、default policy、synthetic fixtureだけを置く。
個人profile、記憶、connector checkpointはユーザーごとのstate Gitに置く。
credential、OAuth cache、raw runtime session、一時ファイルはstate Gitに入れない。

### ADR-002: Watari所有物は `$WATARI_HOME` に集約する

既定値はXDG準拠のユーザーデータ領域とし、`WATARI_HOME`で完全に上書きできる。

```text
$WATARI_HOME/
  config/              端末ローカル・非秘密設定
  state/               canonical state Git
  runtime/             runtime別config/auth/session（Git対象外）
  cache/               derived views・検索index（再生成可能）
  locks/               local writer locks
  tmp/                 owner-only temporary artifacts
```

アプリ自身は `.bashrc` や各AIのglobal configを編集しない。PATH追加はpackage managerの
責務であり、Watari CLIのinit処理には含めない。

`WATARI_HOME` は場所を指定できるだけで、安全性要件を緩和しない。初期化時にowner、mode、
symlink、atomic rename、file/directory fsync、advisory lockを実測し、満たさないfilesystemでは
write operationをfail closedにする。active state Git worktree/refs/index、credential、runtime、lock、
transaction generation/journal/tmpは、owner-private semanticsを満たすローカルfilesystemから出さない。
Windows mount等へ許可できるのは受動的な暗号化exportまたはbare backupだけで、active stateにはしない。
root自体または構成要素がsymlink、他user所有、group/world readableの場合も拒否する。

### ADR-003: 複数PCでは不変のlogical eventを正本にする

現行の巨大なJSONLと共有cursorを複数PCへそのまま拡張しない。

logical eventは不変にするが、物理表現をこの時点で1 event 1 fileへ固定しない。D003でbenchmark
contractとbudgetを先に固定し、crypto候補が観測できたP2bでWSL2上の10k/100k eventについて
create/status/clone/pull/rebuild/backup時間、repository size、inode数、merge性、corruption blast radiusを
実測する。合格すればloose encrypted object、不合格ならimmutable encrypted pack segmentを採用する。
event IDと意味論はどちらでも同じにする。

```text
state/
  bootstrap.json                 # allowlist済み非秘密metadata
  revision-head.json             # signed revision/cipher-object参照
  objects/<opaque-id>.enc         # loose object または immutable pack segment
```

- logical eventとcommitted object/segmentは書き換えない。
- 訂正は `correction`、論理削除は `tombstone` の追加イベントにする。
- 同じsource event ID・同じpayloadはdedupする。
- 同じsource event ID・異なるpayloadはquarantineし、自動選択しない。
- 同じprofile keyの並行更新はlast-write-winsにせずconflictにする。
- checkpointはdevice、connector、source lineage別にする。
- derived viewと検索indexはGitに入れず、event setから再生成する。
- Git force pushと暗黙のsemantic mergeを禁止する。

### ADR-004: 現行の記憶意味論は互換policyとして固定する

パッケージ移行とmemory policy再設計を同時に行わない。legacy raw bytesは暗号化migration
capsuleに損失なく保持し、canonical eventにはhost固有path等を除いた意味情報を移す。
固定時刻で現行stateと一致するcompatibility projectorを持つ。

Heat、Freshness、30日/45日規則はv1移行中に変更しない。`memory explain`で採用理由と
期限を可視化した後、利用観測を根拠に別ADRとschema migrationで変更する。

### ADR-005: 同じ記憶と、モデルへ送る記憶を分ける

canonical stateは共通でも、各memory/profile eventに送信範囲を持たせる。

```text
local-only       外部モデルへ送らない
trusted-model    明示的に信頼したmodel routeだけ
low-risk-model   安価routeへ送ってよい投影
```

context compilerはruntime/model policyに許可された投影だけを組み立てる。
OpenRouter routeへprivate memoryやconnector raw dataを送らない、という現行境界を
defaultとして維持する。境界変更にはユーザー操作とpolicy revisionを必要とする。

このdefaultのOpenRouter low-risk routeは完全なWatariではなく、安価なutility routeである。
「全モデルで同じWatari」に含めるには、(a) low-risk utilityのまま対象外とする、または
(b) OpenRouter上のexact providerへ`trusted-model` dataを送ることを明示承認したtrusted routeを
別に作る、のどちらかをP0でbingeが決める。low-risk sessionをローカルdream対象にする場合も、
user-authored turnだけを一次根拠にし、provider出力を検証済み事実として扱わない。

### ADR-006: runtimeはWatari本体ではなくadapterである

`watari --runtime codex`等でWatari専用環境からruntimeを起動する。Watariの人格、記憶、
dream、同期はruntimeのglobal memoryに依存しない。

project固有の `AGENTS.md` / `CLAUDE.md` はWatari人格とは別の `project instructions`
レイヤーとして扱い、context explanationに明示する。優先順位は以下で固定する。

```text
runtime/system safety
  > Watari explicit profile/rules
  > current user request
  > trusted project instructions
  > retrieved memory context
  > connector content（evidence only、instruction権限なし）
```

この順序はWatariが生成する共通bundle内の意味上の順序であり、runtime自身のsystem/developer
precedenceを書き換えられるという意味ではない。adapterは共通bundleを欠落なく渡し、runtime
固有の実効precedenceとproject instructionの追加を `context explain` に表示する。Watari
bundleが暗黙に無視・置換されるruntimeだけをunsupportedにする。

project instructionsはpathだけで信頼しない。初回利用時にcanonical bytes/digest、root、適用範囲を
登録し、変更時は再承認する。runtimeが未登録の`AGENTS.md`等を自動発見して無効化できない場合は、
managed clean cwdから起動して承認済みproject layerだけを明示注入する。effective project layerと
runtime固有system layerのdigestをcontext manifest/explainへ含め、canonical Watari fingerprintと
effective-session fingerprintを分けて表示する。private/trusted/low-riskを問わず外部model runtimeには
state/keyをmountしないsandbox、route-bound capability、network captureを要求し、合格しないruntimeは
supportedにしない。同じUnix UIDにowner-only permissionだけで秘密境界ができるとは称さない。

初期contextだけで全記憶を渡さない。Watari CLIはセッション中だけ有効なlocal retrieval
serviceを提供し、runtime adapterはread-onlyの `memory.search`、`memory.get`、
`memory.explain` を明示的に接続する。MCP等を使う場合もWatari起動時の一時設定に限定し、
各AIのglobal configへ登録しない。書き込みtoolはcanonical stateへ直接書かず、
source-bound candidateを作るだけにする。

retrieval serviceはsession作成時に固定したruntime/model route identity、visibility policy、
profile/memory revisionをserver側で検証し、検索ごとに同じprojectionを強制する。modelからの
visibility変更、raw event ID指定、全件取得を許さない。通信はowner-onlyのsession-scoped
socket/tokenに限定し、監査logには返したevent IDとbyte数だけを残す。

### ADR-007: dreamは読取・判断・追記だけを行う

dreamはsourceをread-onlyで取得し、モデルには候補選択と要約だけをさせる。profile/rules、
外部サービス、source transcriptを変更しない。モデル出力はschema validationと
source bindingを通過した不変eventだけになる。

### ADR-008: 暗号は独自実装しない

private Gitはアクセス制御であって暗号化ではない。public 1.0までに、`age`またはSOPS等の
既存実装を使うclient-side encryptionをqualificationする。方式選定は次を実測してから
確定する。

- 複数PCの鍵配布と復旧
- 不変eventのmerge性
- profile conflict検出
- remote改変・ciphertext破損・rollback検出
- backupとkey rotation

暗号方式、署名、鍵管理、purgeは安価モデル単独の実装・承認対象にしない。

### ADR-009: v0.xの対応環境を限定する

private pilotは Ubuntu 24.04 / WSL2、Python 3.11以上、Git、uvを必須とする。
Linux固有のlock/namespaceを含むため、macOSとnative Windowsは別support gateとする。

## 5. canonical data contract

### State manifest

remoteの`bootstrap.json`は復号前検証に必要なallowlist metadataだけを持つ。timezone、policy、device名、
connector、key referenceは入れない。signed `revision-head.json`と共にunknown keyを拒否する。

```json
{
  "schema_version": 1,
  "state_id": "opaque random id",
  "crypto_suite": "qualified-suite-id",
  "owner_root_key_fingerprint": "public fingerprint",
  "genesis_digest": "domain-separated digest"
}
```

timezone、memory policy、minimum CLI、device/connector configurationは暗号化state manifestへ置き、
device-local secret referenceは`$WATARI_HOME/config`だけへ置く。

### Memory event envelope

payloadにはlegacy rowまたは将来のversioned memory recordを格納する。source raw text、
credential、absolute host pathは格納しない。

必須field:

- schema version
- event ID
- event type (`memory`, `correction`, `tombstone`)
- recorded/observed UTC timestamp
- payload schema and canonical payload
- visibility (`local-only`, `trusted-model`, `low-risk-model`)
- source connector ID、stable source event digest、dream run ID
- creator (`manual`, `migration`, `dream`) とmodel policy digest
- supersedes target（該当時）

canonical serializationは次で固定する。

- RFC 8785互換canonical JSON、UTF-8、BOMなし、末尾LFなし
- stringは格納前にUnicode NFCへ正規化し、改行はLFへ統一
- timestampはUTC RFC 3339の固定精度へ正規化
- 浮動小数を禁止し、金額等はdecimal string、countはintegerに限定
- digestはdomain separator付きSHA-256
- event IDはschema、connector instance、stable source ID、event type、payload digestから導出
- context fingerprintは実際に送るcontext bytesとpolicy/revision manifestから導出

実装言語・端末をまたぐgolden vectorsをchecked-in synthetic fixtureとして持つ。remoteへ平文で
置く識別子はciphertext digestまたはkeyed HMACとし、plaintext content digestは暗号化payload内に
限定する。

### Profile events

profileは最低限、次を別keyspaceに分ける。

- persona: 名前、話し方、自己定義
- rules: 常時守るユーザー規則
- preferences: 可変の好み
- knowledge: ユーザーが明示的に持たせる補助知識
- environment: 端末・開発環境の非秘密事実

dreamはprofile eventsを書けない。`profile edit`だけがrevisionを作る。

### Checkpoint

checkpointは「最後に走った時刻」だけでなく、connector instance、device、source lineage、
最後にcommittedとなったstable event setを表す。source scan成功だけでは前進せず、対応する
memory eventsとdream runがatomic commitされた時だけ前進する。

auto dreamの完了keyは
`(device, connector instance, source lineage, local date, policy revision)` とする。shared
connectorのcoordinator成功はそのshared sourceだけを満たし、別端末のlocal transcriptを
完了扱いにしない。quarantine、identity conflict、required candidate未決定があるsourceは
checkpointを前進させない。

### Derived views

`life`、`learning`、search index、context working setはcacheである。削除しても
canonical eventsから再生成できなければならない。同じevent set、policy version、
evaluation timeなら同じdigestになる。

## 6. CLI contract

すべてのread commandはファイルを変更しない。すべてのwrite commandは変更予定、対象state、
commit結果を表示する。`--json`はversioned schemaで、human outputの文言変更から独立させる。

```text
watari --help
watari --version

watari init [--restore <remote-or-bundle>] [--state-only] [--non-interactive]
watari setup [--non-interactive]
watari where
watari status [--json]
watari doctor [--deep] [--json]
watari verify [--strict] [--json]

watari chat [--runtime <id>] [--model <id>] [--no-auto-dream]
watari                         # watari chat の短縮形

watari profile show|edit|validate|history
watari context build|explain [--runtime <id>] [--json]

watari memory list|search|show|explain
watari memory correct|forget|restore
watari memory rebuild|verify
watari remember <text>
watari memory candidates list|show|accept|reject

watari source list|add|inspect|test|disable|remove
watari runtime list|add|set-default|test|disable|remove
watari model list|add|set-default|test|disable|remove
watari auth list|login|status|refresh|logout|revoke
watari project list|trust|inspect|revoke

watari dream [--dry-run] [--source <id>] [--since <timestamp>]
watari dream history|show

watari sync status|pull|push
watari conflict list|show|resolve
watari device list|register|trust|revoke|set-coordinator
watari backup create|verify|restore

watari migrate claude inspect|snapshot|plan
watari migrate claude import --dry-run
watari migrate claude import --apply
watari migrate claude verify
```

### Stable exit codes

| Code | Meaning |
| --- | --- |
| 0 | success |
| 2 | CLI usage error |
| 10 | not initialized |
| 11 | config/schema invalid |
| 12 | dependency/runtime unavailable or unsupported |
| 20 | connector auth/availability failure |
| 21 | source drift/unknown format/identity conflict |
| 30 | Git dirty/diverged/conflict |
| 40 | state integrity/verification failure |
| 50 | policy/security refusal |
| 60 | partial dream; failed sources remain pending |

### `watari status` minimum output

- app version、state schema、`WATARI_HOME`
- state Git branch/commit/dirty/ahead/behind/encryption
- profile revision、memory revision、event count、derived cache status
- runtime/modelごとのconfigured/qualified/auth status
- sourceごとのscope、device、last success、pending、last error
- last dream、partial/complete、次回auto dream判定
- sync pending/conflict、unfinished transaction、quarantine count
- secretsは値ではなくproviderとreferenceの存在だけ

## 7. Dream contract

### Pipeline

```text
discover configured sources
  -> snapshot and stable identity
  -> incremental scan from committed checkpoint
  -> normalize genuine user/activity events
  -> reject prompt instructions from connector content
  -> classify by data policy and redact recognized credentials
  -> build content-bound candidate manifest
  -> call qualified dream model route
  -> validate structured decisions and source bindings
  -> create immutable memory/profile-independent events
  -> atomic local transaction with per-source checkpoints
  -> regenerate and verify derived views
  -> local Git commit
  -> optional explicit sync
```

「全会話を読む」は全eventを記憶へ保存する意味ではない。source adapterはuser、assistant、
tool call、tool result、system/metaを区別し、候補判定に必要なbounded contextだけを一時的に
組み立てる。人物・学習記憶の一次根拠はuser-authored eventとverified connector activityに
限定する。assistant応答はユーザーが採用した判断の文脈、tool resultは別途検証済みの事実に
限って補助根拠にできる。system/meta、未検証tool output、subagent outputは記憶の根拠にしない。

### Failure semantics

- dry-runはstate、checkpoint、cache、Git、sourceを変更しない。
- unknown source format、source drift、duplicate identity conflictは当該sourceを停止する。
- timeout、capacity、invalid JSON、policy refusalではcheckpointを進めない。
- source単位でatomicに成功/失敗を分け、partial runはexit 60とする。
- `required=true` sourceの失敗はauto dreamを成功日にしない。
- auto dream失敗時も既存記憶でchatは起動できるが、stale warningを表示する。
- process kill、disk full、Git failure後も旧stateか新stateのどちらか一方に復旧する。
- Git push失敗はlocal commitを失敗扱いにせず `sync pending` とする。

canonical transaction boundaryはmutable worktreeではなく、検証済みのsigned Git commitとする。
writerはprivate transaction directoryで次generationを構築し、次のjournal stateを通る。

```text
PREPARED
  -> COMMIT_CREATED
  -> REF_UPDATED（expected old OIDを条件にatomic update-ref）
  -> WORKTREE_MATERIALIZED
  -> COMPLETE
```

checkpoint、memory/profile events、dream manifestは同じcommitへ入れる。ref更新前のkillでは旧commit、
更新後のkillでは新commitを正本とし、起動時にjournalからworktree/cacheを再materializeする。
commit作成失敗ではrefを更新しない。各遷移直前直後をfault-injection testにする。

### Auto dream

- `watari` 起動時だけ判定し、daemonやshell hookを使わない。
- IANA timezoneと、現在deviceにdueなrequired sourceごとの完了keyで判定する。
- local single-writer lockを取得し、同時起動の片方は結果を待つか既存結果を再利用する。
- offlineやprovider capacityを成功として記録しない。次回起動で再試行する。
- `--no-auto-dream` はその起動だけskipし、checkpointを変更しない。

## 8. Runtime adapter contract

全adapterは以下を実装する。

- `detect()` executable path/versionを観測
- `qualify()` supported flags、auth isolation、context injection、session captureをsynthetic入力で検証
- `launch_interactive()` PTY、cwd、Ctrl-C、exit codeを透過
- `run_structured()` dream用のbounded input/output、timeout、schema output
- `session_source()` 後続dreamが読めるWatari専用session rootを返す
- `memory_tools()` session-scoped read-only retrieval serviceをruntime固有の方法で接続する
- `explain()` 実際のargv/env/context fingerprintを秘密なしで返す

network model routeはmodel名だけでqualifiedとしない。model ID、provider endpoint、fallback無効、
retention/ZDR設定、request上限、credential scope、provider側credit/spend capを1つのversioned route
manifestとして固定する。manifestと実requestが一致しない場合はfail closedとし、live dataを送る前に
synthetic probeとcaptured egress metadataで確認する。

context本文をargvへ載せない。owner-only一時fileまたはstdinを使い、runtimeが公式に対応する
最も強いinstruction surfaceへ渡す。

auth adapterは`login/status/refresh/logout/revoke`とsecret-reference解決を持つ。1Password/OS keychainの
値は人が実行時に注入し、shell展開、argv、diagnostic、AI promptへ載せない。既存global credentialを
Watari rootへcopyせず、runtime固有OAuthを使う場合も保存path、mode、expiry、revocationをqualification
する。同一UID processからの読取を防ぐ保証が必要なrouteは、state/keyをmountしないsandboxとnetwork
captureまで合格させる。

### Codex adapter gate

- Watari専用 `CODEX_HOME` を使い、通常の `~/.codex` を読まない。
- explicit `model_instructions_file` とstrict configを使えることをversionごとに検証する。
- target projectの `AGENTS.md` はproject layerとして別途表示する。
- Codexのauth/sessionがWatari runtime root外へ漏れないことを確認する。

Codex公式manual上、`CODEX_HOME`はconfig/auth/log/sessionのrootであり、project instructionsは
project rootから自動発見される。この差をadapterが隠さず説明する。

### Claude adapter gate

- `CLAUDE_CONFIG_DIR`をWatari runtime rootへ向ける。
- global `CLAUDE.md`、hooks、plugins、MCPを無効にした状態で、明示Watari contextだけを
  注入できる経路を実機確認する。
- `--bare`はAPI key経路、`--safe-mode`はOAuthを含む候補として別qualificationにする。
- settings validation failureがsilentになり得るnon-interactive modeでは、事前validatorを持つ。

Claude公式CLIは`CLAUDE_CONFIG_DIR`、system prompt、stream JSON、safe/bare modeを提供するが、
Watariは組合せを実測するまでsupportedとしない。

### Pi adapter gate

- versionをallowlistし、package installをexplicitにする。
- state、OAuth、sessionは`$WATARI_HOME/runtime/pi`だけに置く。
- private inputを扱うrouteとOpenRouter low-risk routeを分離する。
- `new-watari`のisolation、egress、model policy契約を再利用候補とする。

### OpenCode adapter gate

- official distribution、config root override、interactive/structured mode、session format、permission
  behaviorをclean fixtureで観測する。
- このqualificationが完了するまでCLI表示は `unsupported: not qualified` とする。

## 9. Connector contract

connectorはruntime adapterと分離する。各connectorは次を宣言する。

- source ID、owner device/shared coordinator
- read scopeとdata classification
- credential referenceとrevocation方法
- stable event identity、pagination、checkpoint、retention
- required/optional
- raw dataを送信できるmodel class
- prompt injection boundary
- rate limit、retry、partial failure

実装順は次とする。

1. Claude/Codex/Pi local transcripts（既存adapterを移植）
2. OpenCode local transcripts（qualification後）
3. local filesystem / Obsidian read-only
4. Linear read-only
5. Gmail / Calendar read-only
6. Slack read-only

shared connectorの自動dream coordinatorは1台だけにする。端末固有transcriptは各端末が担当する。
Git remoteを分散lockとして使わない。

coordinatorは自動failoverしない。shared connector実行前に最新trusted remote revisionと署名付き
coordinator epochを確認し、offline時はshared sourceを処理しない。移譲時は全端末のsync、
旧coordinator revoke、epoch更新、new coordinator trustを1つのowner-signed revisionで行う。
古いepoch、quarantine範囲を越えるcheckpoint、divergent lineageのmax mergeを拒否する。

connector contentはevidenceでありinstructionではない。メールやSlack本文に書かれた命令で、
profile変更、credential読取、外部action、policy変更を起こしてはならない。

## 10. Git、同期、暗号、削除

### Git semantics

- dream/profile/migration成功時にlocal commitを作る。
- remote pushはprivate pilot初期値では明示操作。auto-syncは別設定とする。
- pullはremote検証後に行い、unknown signer、rollback、profile conflictを拒否する。
- divergence時にJSONL unionやcursor自動mergeを行わない。
- immutable eventsの集合merge後、profile/checkpoint conflictを明示解決する。
- force pushをCLIから提供しない。

remote rollback検出はciphertextやGit HEADだけに依存しない。state revision manifestをapproved
device keyで署名し、各端末はhighest accepted revisionをowner-only領域に保持する。新端末restore用の
`state_id`、owner root public-key fingerprint、genesis digest、minimum accepted revision/hashは
1Password等のremote外recovery recordから供給する。remote HEADがtrust anchorの正当な子孫で
あることを検証できないrestoreはstrict modeで停止する。

pushとrecovery record更新は、(1) signed revisionをconditional push、(2) remoteから再取得して検証、
(3) old anchorを条件にrecovery recordをCAS更新、の順にする。3が失敗した場合はremoteを巻き戻さず
`anchor stale`とRPOを表示し、修復まで新しいpushを止める。各境界のkillと複数端末CAS競合を試験する。

device revokeは将来の署名拒否と復号範囲縮小を分ける。revoke後はactive recipient/keyをrotationし、
recovery recordとactive device setを更新する。失われた端末が既に取得した過去の平文・鍵・ciphertextは
回収できないことを明示する。

複数PCで「同じWatari」と呼べるのはlast verified sync revisionまでである。未push local commitが
ある間は `status` にdivergence windowを表示し、端末故障時のRPO（復旧可能時点）は最終pushまでと
明記する。chat前pull、dream後pushはユーザーが選べるpolicyとし、失敗を黙らせない。

### Secrets

- 1Password secret reference、OS keychain、runtime固有OAuth cacheをprovider contractで扱う。
- state remoteに許す平文はschema/crypto suite、opaque state ID、owner public-key fingerprint、signed
  monotonic revision/cipher-object参照、およびGit object/commit metadataの明示allowlistだけとする。
  profile、memory、checkpoint、dream/device contentは暗号文にし、type/date/hostをfilenameへ出さない。
  tracked artifact、diagnostic report、dream manifest、argv、stdout/stderrに認識対象の平文credentialを
  出さない。未知形式、自然文password、一般PIIやGit metadataの完全秘匿まで保証するとは称さない。
- `.env`やprocess environmentは同一ユーザーに対する強い秘密境界と称さない。

### Forget / purge

- `memory forget`はtombstoneによる論理削除で、Git履歴やbackupから消えたとは表示しない。
- `memory restore`はtombstoneをsupersedeする。
- `purge`はremote history、backup、暗号鍵rotationを含む別の破壊的手順とし、v1通常CLIから
  安易に実行しない。

## 11. Legacy migration contract

### `migrate claude inspect`

移行元path、Git HEAD/dirty、tracked files、file hash、row count、UUID set、schema、cursor、
writer/schedulerの観測可能範囲をread-onlyで報告する。最低でもglobal `CLAUDE.md`、Watari
`SKILL.md` / `DESIGN.md` / memory `SCHEMA.md`、`knowledge/`、memory logs/state/cursors、検出した
scheduled consolidation定義、旧state比較証拠をscope manifestへ列挙する。移行元の内容を変更しない。

### `migrate claude snapshot`

全legacy writerを人が停止した後に実行する。scan前後の全hashが一致しない場合は失敗する。
snapshotはscope manifest内のlegacy raw bytesをlosslessに保つ暗号化migration capsuleで、manifest、
source digest、row count、profile候補、policy donor候補、旧state比較証拠、除外一覧を持つ。
credential store、runtime session、cacheは含めず、存在と除外理由だけを記録する。

### `migrate claude plan`

```text
CLAUDE.mdのユーザー固有人格・規則 -> profile候補
Watari SKILL/DESIGN/SCHEMAの機械規則 -> app policy / compatibility docs
memory log rows                    -> immutable memory events
cursors                            -> connector checkpoints
knowledge                          -> profile knowledge候補
credentials/sessions/cache         -> excluded
project固有CLAUDE.md/AGENTS.md      -> global profileへ移さない
```

profile抽出は自動applyせず、人が差分を承認する。

### `migrate claude import`

- defaultはdry-run。
- snapshotから新stateを作り、legacy sourceへ書かない。
- migration IDで冪等にする。
- 全legacy rowをlossless capsule内で保持し、未知rowを黙って捨てない。
- canonical eventではabsolute cwd/session等をlogical connector URIまたはopaque digestへ変換し、
  raw host pathやcredential候補を格納しない。credential候補rowはquarantineする。
- `legacy line digest -> canonical event ID / quarantine reason` の全件mappingを作る。
- 正確なlegacy再出力はcanonical eventではなくretained migration capsuleを必要とする。
- imported visibilityは既定で`local-only`とし、reviewed migration approvalで選んだeventだけを
  `trusted-model`へ昇格する。`low-risk-model`へ自動昇格しない。
- visibility reviewはsource snapshot digest、event set digest、承認者、承認時刻へ署名で結び付ける。
- active legacy derived stateへ寄与するrowがquarantineされた場合はmigration未完了とし、人がredacted
  canonical mappingまたは`local-only`受入を承認するまでapplyしない。quarantineを除外してparityを
  合格させない。
- apply前に空stateまたはexplicit target generationを要求する。

### `migrate claude verify`

- 全legacy rowのUUID・line digest・canonical eventまたはquarantine reasonの対応
- 固定時刻で旧derived stateとcompatibility viewのsemantic/hash parity
- checkpoint対応と後退の不存在
- profile revisionと承認差分
- signed visibility review後、trusted routeで旧Watariと新Watariのbounded context parity
- excluded file一覧
- state Gitにsecret/raw runtime sessionがないこと
- snapshot前後のlegacy source hash不変

### Rollback

- 最初の新writer書込み前は新stateを破棄し、legacy writerを継続できる。
- 新writer書込み後はcursorを巻き戻してlegacy writerを再開しない。
- 障害時は全writerを止め、最後の検証済みsnapshotとimmutable eventsから復旧する。
- legacy形式への逆exportは別途実装・検証しない限り可能と称さない。

## 12. Packaging and repository plan

### Repository

```text
watari-cli/
  AGENTS.md
  README.md
  LICENSE                 # public化時にユーザー決定
  pyproject.toml
  uv.lock
  src/watari_cli/
    cli/
    state/
    profile/
    memory/
    context/
    dream/
    runtimes/
    connectors/
    sync/
    migration/
    security/
  tests/
    unit/
    contract/
    integration/
    security/
    packaging/
    migration/
    fixtures/             # synthetic only
  docs/
    donor-components.lock.json
    requirements.md
    cli-contract.md
    data-contract.md
    threat-model.md
    migration.md
    acceptance.md
    adr/
```

Python packageはPEP 621を使い、`[project.scripts] watari = "watari_cli.cli:main"`を定義する。
build backend、wheel/sdist、version、Python supportを明示する。coreはPython中心とし、Pi/Node、
Codex、Claude、OpenCode、age/SOPSはoptional external capabilitiesとしてdoctorが検査する。

`uv tool install`はpackage commandをisolated environmentへ入れ、executableをPATH用binへ
配置できる。private pilotはtested commitからwheelをbuildし、checksumを固定して別PCへ
installする。branch tipや未固定latestを受入試験に使わない。

### Versioning

- app: semantic version
- state schema: integer generation
- event/profile/checkpoint/context JSON: individual schema version
- runtime/connector capability: adapter contract versionとqualified version range
- migration: migration IDとsource manifest digest

state migrationはcopy-on-writeで新generationを作り、verify後にcurrent pointerをatomicに切替える。

`donor-components.lock.json` は `new-watari` のdonor commit、移植module、source hash、対応test、
採用/不採用理由を固定する。Python product CI、optional Node/Pi integration、donor repo regressionを
別jobにする。componentを移植したphaseで対応contract testをproduct repoへportし、単なるP1
skeletonで既存121件がproduct testになったとは扱わない。

## 13. 実装フェーズとゲート

### P0 設計凍結

成果物: requirements traceability、CLI/data/dream/runtime/connector contract、threat model、ADR、
acceptance tests、private/public runtime matrix、physical event storage benchmark contract/budget。
DoD: 全要求がテストIDへ対応し、OpenRouterをlow-risk utilityのままにするかtrusted Watari routeも
認めるかをbingeが決定し、10k/100k storage benchmarkの測定法と合格budgetを固定し、unknown decisionが
ADR `open`として可視化されている。physical layoutはcrypto候補込みのP2b観測まで未決定にする。
禁止: live書込み、Heat/Freshness変更、実装開始。

### P1 package skeleton

成果物: installable wheel/sdist、console entry point、`--help`、`--version`、CI。
DoD: exact wheelをempty environmentへinstallでき、help/versionがnetwork・home writeなしで動く。
product wheel smoke testが合格し、donor repoの既存121件とshell/Pi contractsは独立したbaseline jobで
引き続き合格する。移植していないdonor testをproduct coverageとは数えない。
禁止: packagingと大規模module rename/refactorを同じchangeに入れない。

### P2 state root and observability

成果物: `where/status/doctor`の未初期化/初期化済み表示、state manifest、read-only inspection。
DoD: `WATARI_HOME`隔離、owner-only directories、symlink/unsafe mount拒否、atomic rename/fsync/lockの
capability probe、Git optional index write抑止、read command前後hash不変、versioned JSON output。

### P2b encryption, signing, and trust-anchor qualification

成果物: external crypto implementationの選定記録、storage codec、device signing、owner trust anchor、
secret-reference provider、1Password等へ置くrecovery record schema、rollback検出、key loss/rotation drill。
DoD: synthetic stateだけを使い、allowlist済み認証metadata+ciphertextだけのremote、wrong key、unknown
signer、改変、remote rollback、lost device、recovery recordからの新端末restoreを破壊試験で確認する。
crypto候補込み100k benchmarkを通し、loose object/pack segmentのphysical ADRをここで確定する。
Gate: security/high-trust reviewerが方式とtest evidenceを承認するまでP3以降のpersistent `.enc` formatを
固定しない。独自暗号を実装しない。

### P3 immutable state and compatibility projector

成果物: event store、profile event store、checkpoint store、derived cache、legacy-v1 projector。
DoD: P2bのqualified codecを用い、current synthetic logから明示したevaluation timestampで旧stateと
同一digest、correction/tombstone/conflict test。`.enc`拡張子の平文fixtureを許可しない。
禁止: P2b完了前のlive personal data、credential、production state利用。

### P4 profile, canonical context, and retrieval

成果物: `profile`、`context build/explain`、budget、visibility projection、fingerprint、
session-scoped read-only retrieval service、manual remember/candidate review。
DoD: 同じinputで同じfingerprint、巨大memoryでもbudget内、採用/除外理由を説明、raw log全注入なし、
global AI config無変更、write proposalがcanonical stateへ直結しない。
禁止: P2bとvisibility policyのqualification完了前のlive personal data利用。

### P5 source adapter framework

成果物: source contract、Claude/Codex/Pi adapter移植、OpenCode qualification harness。
DoD: stable identity、incremental checkpoint、source drift、unknown format、symlink escape、dedupの契約試験。
禁止: adapter qualification中はsynthetic transcriptだけを使い、live rootはP8以後の明示gateまで開かない。

### P6 dream pipeline

成果物: `dream`、dry-run、history、structured decision、transaction recovery、Git commit。
DoD: dry-run無変更、model failure時checkpoint不変、kill/disk-full回復、secret/raw input非永続化、冪等。
Gate: mock modelで全failure testを通した後、model ID、exact provider endpoint、fallback無効、retention/ZDR、
request bounds、dedicated credential scope、credit/spend capを固定したrouteだけsynthetic live probeを許可する。
個人dataはrouteごとのegress qualification完了まで使用しない。

### P7 sync and backup

成果物: `sync`、P2bでqualified済みの暗号・署名codecを使うbackup/restore、device registration/conflict。
DoD: temporary bare remoteで2台試験、remote tamper/rollback検知、profile conflict、lost key drill、
認識対象credentialとplain memoryがremote/tracked artifactに不在。
Gate: crypto/sync専門レビューと破壊試験。安価モデルだけで承認しない。

### P8 legacy migration

成果物: inspect/snapshot/plan/import/verify。
DoD: synthetic legacy treeでlossless/idempotent、read-only source hash不変、fixed-now parity、rollback。
Gate: live rootは別途明示承認までread-only。

### P9 runtime adapters and setup

成果物: state-only init、setup wizard、runtime/model/auth/project commands、Codex/Claude/Pi/OpenCode adapters、
bare `watari`/`watari chat` dispatcher。
DoD: fake runtimeで同一fingerprint、login/status/refresh/logout/revoke、PTY/Ctrl-C/exit code、global config隔離、
approved project layerだけ適用、state/key非mountのsandbox、route別network capture、unsupported version
fail closed。generic setupはlive provider qualificationを
待たず実装し、capabilityは観測後に登録する。

### P10a external read connectors

成果物: connector SDKとObsidian/Linear/Gmail/Calendar/Slack read-only adapters。
DoD: fake HTTPでpagination/429/timeout/token expiry、least privilege、checkpoint atomicity、
prompt-injection test、status visibility。connectorごとに個別release gateを持つ。

### P10b current optional outputs and action workflows

成果物: optional Obsidian Journal writer、明示的なexternal-completion workflow、connectorごとの
write authorization、read connectorとは別のwrite adapter/credential。dream本体とは別transaction・
別audit logにする。
DoD: Journal失敗がmemory commitを壊さない、送信済み等の外部完了報告では実source確認、
current task確認、許可されたexternal update、memory ingest、全成果物再確認の順序を固定する。
runtimeから呼ぶ場合はWatari session専用toolと毎回のuser authorizationを要求する。
禁止: read connector credentialからwrite scopeを推測する、dream modelへexternal write authorityを渡す。

### P11 auto dream

成果物: first-launch daily trigger、timezone、required/optional source policy。
DoD: same day once、concurrent once、midnight/DST/timezone test、offline retry、manual dream排他。

### P12 hardening and release candidate

成果物: dependency audit、SBOM、secret scan、signed tag/checksum、performance/crash matrix、upgrade test。
DoD: 100k-message synthetic fixtureでcontext budget維持、concurrent writer/disk full/kill試験、
reproducible artifact、support matrix。

### P13 clean-room acceptance

新規Ubuntu 24.04/WSL2または別PCで実施する。

1. `.claude`、`.codex`、`.pi`、`WATARI_HOME`不在とhome baselineを記録する。
2. 事前登録したrelease signing public key/provenanceを使い、signed tag、exact commit、wheel、checksumを
   検証してinstallする。同じ配布元から得たchecksumだけを信頼根にしない。
3. install前後のhome diffで、package manager以外の副作用がないことを確認する。
4. Git認証は1Password SSH agent等から別途供給し、private keyを`WATARI_HOME`へcopyしない。
5. productionとは別のstate ID、key、remote、recovery recordでdisposable synthetic stateを作る。
6. synthetic会話、dream、auto dream、2台sync、conflict、tamper、rollback、lost-key drillをdisposable
   stateだけで実施し、credentialをrevokeしてtemporary remoteを破棄する。
7. 1Password等からBINGE state keyとout-of-band recovery recordを供給し、minimum trusted revisionを
   検証してread-only restoreする。このstateへsynthetic eventを書かない。
8. provider secretsだけを人が1Password/各provider loginから注入し、値をモデル・artifactへ渡さない。
9. migration時に固定したrevision evaluation timeを`watari verify --at <timestamp> --strict`へ渡し、
   profile、memory event set、derived view、checkpoint digestを比較する。
10. private BINGE pilotの必須matrixとしてCodex CLI chat、Pi/OpenAI-Codex trusted dream、
   Pi/OpenRouter low-risk utilityをsynthetic promptでqualificationする。OpenRouterを完全なWatariにする
   場合はP0で承認した別trusted-route contractも検証する。
11. OpenCode/Claude adapterはpublic 1.0前にsynthetic conformanceを必須とし、live authはconfigured runtime
   だけで検証する。未導入runtimeをprivate pilotの合否条件に混ぜない。
12. supported runtime間でcanonical/effective context fingerprintを比較する。
13. BINGE stateのrestore/verify/runtime-read試験前後でcanonical digest不変を確認する。
14. 裸の各AI CLIにはWatariが現れないことを確認する。
15. app uninstall後もstateが残り、再installで復元できることを確認する。
16. state、diagnostics、test artifactにGit private key、provider token、plaintext export、認識対象credentialが
   ないことを検査する。

合格記録にはapp commit/artifact signature/checksum/provenance、state revision、profile revision、
memory digest、runtime別context fingerprint、source別checkpoint、recognized-credential scan、home diff、
rollback結果を残す。

### P14 BINGE cutover

1. live sourceをread-onlyでshadow scanし、scan前後hashが一致した範囲だけ非権威rehearsal capsuleへ
   取り込み、migration/restore/verify rehearsalを行う。
2. clean PCでrehearsal stateのrestore/verifyを完了する。
3. 現行feature parity manifestをsnapshot digestへ結び付け、各機能を「実装・qualification済み」または
   「bingeが署名して廃止/延期」のどちらかにする。未分類機能があれば停止する。
4. final cutover開始時にlegacy canonical memory writerを停止し、そのまま永久に停止する。stable delta取得に
   必要な間だけsource runtimeも停止する。
5. final stable/delta snapshotを取得し、import、sync、target側strict verifyを行う。
6. legacy writer停止状態、final capsule digest、target revision、確認時刻/有効期限をowner-signed one-shot
   attestationとして残す。最初のproduction dreamは一致するattestationを機械的に要求し、消費記録を残す。
7. targetだけでmanual canary dreamを行い、成功後はWatari経由のsource runtimeだけ再開できる。
8. journal、memory、checkpoint、Git sync、writer count=1を確認する。
9. canary由来event/checkpointが0、attestation未消費、target HEADがfinal imported revisionと一致、legacy
   sourceがfinal snapshot以後不変の場合だけ、target generation/remote ref/recovery anchorをabandonedとして
   隔離した後にlegacy canonical writer再開可否を人が決める。canary write後は自動rollbackしない。
10. bingeが事前に決めたobservation window中、dream、sync、backup、writer count、legacy停止を監視し、
   期間完了後もCLIをsole writerとしてrollback evidenceを保持する。
11. Claude解約は最後に行う。

### P15 public release

- generic onboarding、documentation、support matrix、privacy modelを整える。
- publicで`supported`と表示するruntimeはclean environmentでcontext injection、session capture、auth
  isolation、dream/retrieval E2Eを合格させる。experimental adapterはminimum matrixから外して明記する。
- distribution名、商標、licenseをユーザーが決定する。
- BINGE profile/state/fixture/pathがartifactにないことを検査する。
- public registryはprivate pilotとclean-room acceptanceの後にのみ使う。

## 14. Test strategy

### Test layers

- unit: pure schema、fold、budget、dedup、exit mapping
- contract: runtime/source/connector/model/secret interfaces
- integration: subprocess、PTY、Git bare remote、fake HTTP、encrypted state
- migration: synthetic current/legacy trees、fixed-now parity、idempotency
- security: path traversal、symlink、prompt injection、secret leak、tamper、rollback
- fault injection: kill point、disk full、read-only fs、network loss、concurrent writer
- packaging: wheel content、isolated install、uninstall、upgrade/downgrade
- clean-room: 別OS user/VM/PCでのend-to-end

production transcript、credential、個人メール等をfixtureとしてcommitしない。live検証はhash、count、
opaque ID、pass/failだけを永続化し、内容をtest artifactへ残さない。

### Global invariants

1. Canonical state writerは常に1 transactionだけ。
2. Source checkpointは対応event commitより先に進まない。
3. Model outputは直接state writeにならない。
4. Read commandは状態を変更しない。
5. Unknown schema/source/runtime versionはfail closed。
6. `local-only` dataは全network captureで送信0件。
7. SecretはGit、argv、log、report、fixtureへ出ない。
8. Same canonical inputs produce the same context fingerprint。
9. Install alone produces no Watari behavior outside `watari` invocation。
10. Migration never writes the legacy source。

## 15. 安価モデルによる実装運用

安価モデルは利用できるが、この文書全体を一括で渡して実装させない。各phaseをさらに
小さなissueへ分割し、1issue 1目的 1commitで進める。

実際の依存関係、変更範囲、test、review classは
[`watari-cli-issue-dag.md`](watari-cli-issue-dag.md)を実装キューの正本とする。

各実装ticketに必ず含める。

- 要求ID、対象phase、前提commit
- 変更可能fileと変更禁止file
- input/output schema、exit code、failure semantics
- 先に追加する失敗test名
- network、live memory、credential、external service使用禁止
- 実行するtest commandと期待結果
- artifactに含めてはいけない内容
- rollback方法

目安はproduction module 1個、test file 1個、差分300行程度までとする。test削除、skip追加、
期待値の都合のよい変更、scope外refactorは禁止する。

### 安価モデルに任せやすい作業

- parser、human/JSON output、pure schema validation
- deterministic conversion、fixture、unit test
- docs、help text、mock runtime/connector
- bounded adapter glue（contract確定後）

### 独立した高信頼レビューが必須の作業

- canonical data schemaとtransaction
- encryption、signature、secret broker、egress
- multi-device sync/conflict/rollback
- migration snapshot/import/apply
- model data-classification boundary
- clean-room acceptanceとproduction cutover

各phaseのmerge gateでは、そのphaseのproduct testsに加え、donor regression jobとして既存
`new-watari`の121件とshell契約を回帰実行する。安価モデルが「完了」と述べたことは証拠にせず、
CI結果、diff、artifact、clean-room observationを証拠にする。

## 16. 実装開始前に閉じるゲート

P1開始前に決めるもの:

- private repo名と将来のdistribution名を同一にするか
- v0.x supportをWSL2/Ubuntuだけに限定すること
- app code repoとuser state repoを分けること
- `MATRIX-PRIVATE`と`MATRIX-PUBLIC-1.0`の必須runtime/source
- OpenRouterをlow-risk utilityだけにするか、明示承認したtrusted Watari routeも設けるか

P2b完了前に実測して決めるもの:

- crypto候補込みでのloose objectとimmutable pack segmentの100k-event benchmark結果

P2b開始時に実測して決めるもの:

- age/SOPS等の暗号・署名・鍵回復方式
- state remoteのrollback detectionとapproved device方式
- shared connector coordinatorの選出/移譲手順

P9開始前に実測して決めるもの:

- 各runtime versionのcontext injection、config isolation、session extraction
- subscription OAuthとAPI keyの対応範囲
- model/providerごとのdata classification
- auth providerごとのlogin/status/refresh/logout/revokeとcredential cleanup

P14開始前に人が決めるもの:

- live writer停止時刻
- migration profile差分
- snapshot digestに結び付いたfeature parity manifest
- canary batch
- recovery authorityとretention期間
- Claude解約時点

これらを推測で埋めない。未観測のruntimeや暗号方式は、qualification testが合格するまで
`unsupported`のままにする。

## 17. Definition of Done

Watari CLI 1.0は、次をすべて満たした時だけ完成とする。

- exact artifactからclean PCへinstallできる。
- install aloneにWatari固有のglobal副作用がない。
- `watari`だけがWatariを起動する。
- profile/memory/contextの所在と根拠をCLIで説明できる。
- supported runtime全てが同じcanonical revisionを参照し、同じroute policyでは同じcanonical context
  fingerprintが渡る。異なるvisibility projectionはeffective fingerprintと機能差を明示する。
- source/connectorごとの差分dream、失敗、checkpointが可視化される。
- profileはexplicit editだけ、dreamはreversible immutable memory eventsだけを書く。
- two-device sync、conflict、tamper、rollback、lost-key recoveryを通過する。
- legacy migrationがlossless、idempotent、source read-onlyである。
- BINGE Watariを別PCに復元し、canonical digestが一致する。
- cheap model routeへ許可外dataが送信されない。
- cutover後にwriterが一つだけで、rollback evidenceが残る。
- public artifactにBINGE固有profile、記憶、path、credentialが存在しない。

## 18. 参照した公式仕様

- uv tool installはPython CLIをisolated environmentに入れ、commandをPATH用binへ配置する:
  <https://docs.astral.sh/uv/guides/tools/>
- Codexのconfig/auth/session root、project instruction discovery、CLI controls:
  <https://developers.openai.com/codex/codex-manual.md>
- Claude Codeの`CLAUDE_CONFIG_DIR`:
  <https://code.claude.com/docs/en/env-vars>
- Claude Code CLI / headless controls:
  <https://code.claude.com/docs/en/cli-reference>

OpenCodeはこのマシンに存在せず、検索結果だけでadapter contractを確定していない。
実装phaseのclean qualificationを正本とする。
