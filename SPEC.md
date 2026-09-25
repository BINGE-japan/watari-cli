# watari-cli 仕様（開発者向け・開発時に最初に読む）

**利用者向けの導入は `README.md` を参照。** このファイルは開発者・実装エージェント向けで、
watari-cli が **何を目指し・何を満たし・今どこまで来ているか** の正本。
毎回ゴールを口頭で説明しなくて済むよう、ここを読めば全体像と現在地が分かる状態を保つ。
（記憶エンジンのデータ仕様は `src/watari_cli/skill/SCHEMA.md`、人格と夢の手順は同 `SKILL.md`、
開発規律・安全境界は `AGENTS.md`。このファイルは「なぜ・何を・今どこ」を担う。
なお本ファイルは内部設計文書のため「夢」「カセット」等の内部用語をそのまま使う。
ユーザーが目にする文言での言い換えは末尾「ユーザー向け語彙（用語マップ）」に従うこと。）

## ゴール（north star）
「ワタリ」＝ユーザーの分身。**記録・伴走・リマインド**を、決まった動き方で続ける秘書。
それを **器（engine＝配布物）と カセット（user＝記憶・設定）に分離**した、配布可能な CLI にする。
- **Pi 上で動く**：どのモデルと話しても、その会話をワタリが夢に見る（判定はモデル、機械処理は CLI）。
- **記憶は持ち運べる**：個人データ（log/state）は git で運べるカセット（WATARI_HOME）。
- **器を他人に渡せば、その人が自分のワタリを育てられる**：＝ 開発者個人の固有物
  （認証情報・パス・サービス名・私的運用の前提）を engine に一切漏らさない。

## 満たすこと（要件）
- **記録**：会話から「後で効く事実」だけを自動で記憶へ移す（夢ループ）。
- **伴走**：state（現在地）を初期姿勢に、最初の一文から反映して話す。全 state を会話へ積まず、
  各入力の直後・モデル呼び出し前に常時 profile＋優先事項＋関連 fact/topic＋profile/topic catalog をローカル検索して
  一時注入する（上限16KB、モデル呼び出し追加なし、transcriptへ保存しない）。profile は always（毎回）と relevant（関連時）を明示分類し、always は5KB以内。区画別の容量予約で profile 肥大時も地図と関連情報を丸ごと失わない。
- **リマインド**：進行中(open_threads)・締切(deadline)・休眠(dormant)を画面専用の確認事項として提示する。
  確認事項はユーザー発言としてモデルへ渡さず、ユーザー自身が触れるまで会話へ持ち込まない。
- **決定論**：log＝正本（追記専用）→ state＝派生（log から再生成）。同じ log＋now なら必ず同じ state。
- **モデル非依存**：判定はランタイム上のモデル、機械処理は CLI。**記憶エンジンはモデルも MCP も呼ばない**。MCPの接続・実行はPi MCP Adapterへ委譲する。
  既存処理をPiの専用道具からも呼び、MCP化やserver移行を前提にしない。人格・承認境界は常時、
  作業固有の判断基準と手順はその作業時だけ読み込む。モデルの安全性への期待を理由に承認境界を削らない。
- **一般公開可能な汎用性**：特定の個人・会社・別製品・私的運用を条件分岐へ持ち込まない。
  接続サービスは共通adapter契約で扱い、ユーザー固有の事情は記憶フォルダ/configだけに置く。
- **観測を優先して回答**：質問では利用できる実ツールの情報を優先し、成功結果を evidence として登録する。
  未観測または推測表現を含む回答も隠さず、小さな警告行を末尾に添える
  （2026-07-24 にユーザー指示で緩和。回答が隠れると会話が進まないため）。
- **人間相手の送信は本人承認後だけ**：送信先・送信元・宛先・相手だけで意味が分かる完全な文面を
  先に提示し、その内容への明示承認後にだけ外部へ送る。SlackはWatari botへidentityを固定し、
  Piの対話画面で全文を再表示する決定論的な最終確認を通す。非対話実行や別botへの無断切替はfail closed。
- **性能モード**：`/performance` で fast / balanced（既定）/ butler を選び、このパソコンの config に保存する。
  fast は記憶4KB・関連3件・catalog無し・thinking off・成功toolを自動evidence化、balanced は現行の
  16KB関連検索とPi本来のthinking、butlerは全state一時注入・thinking high。モデル自体はPi側で選ぶ。
- **能動brief**：期限・予定・未返信・未読をread-onlyの実状態から共通signalへ変換し、重要度順に
  最大3件を画面専用で提示する。Piの会話メッセージには保存せず、モデルの入力へ参加させない。
  通知履歴はXDG stateにfingerprintだけを持ち、各サービスを正本のまま保つ。
- **本体の自動更新**：`git clone`→`uv tool install .` の導入元が clean な main のときだけ、
  `watari chat` 起動時に origin/main へ fast-forward・再インストール・再起動し、反映したcommit件名を表示する。
  dirty/diverged/非main/非uv-tool/オフラインは上書きせず現在版で起動する。
- **持ち運び**：記憶は WATARI_HOME（git リポ）。`watari install` で挿せば「その人のワタリ」。
- **ユーザーに生コマンドを手組みさせない**：`watari install` で watari の担当（記憶カセットの用意）が
  menu で完結し home も保存される。以後ユーザーは `watari chat` を打つだけ（`--home` も不要）。
  初回認証のCLI案内は「他のパソコンから引き継ぐ／初めて作る」の2分岐だけを短く示し、Google Cloudの
  詳細操作は公開ドキュメント1か所へ寄せる（ターミナルへ長い設定手順を展開しない）。`watari auth` /
  `watari connect` で外部サービスの画面操作を案内する部分は、英語UI上の名称と一致する英語表記に統一する。
  **モデル・認証は Pi の担当**（Pi が起動時に選ばせ・`/login` し・自分で覚える）。watari はそれを
  肩代わり・重複しない（watari ≠ Pi の分離。install で「どの AI で動かすか」は尋ねない）。
- **どのマシンでも同じワタリ（マルチマシン同期）**：記憶(カセット)は git で同期（読む前に pull・書いた後に
  push、union-merge）。会話は各マシンの chat が **クラウド中継所（Google Drive appDataFolder）**へ user＋
  assistant の発話だけ送り、どのマシンの夢もそれを読む＝A で話した分を B のワタリが覚える。生 transcript は
  git に入れない（履歴から消せず容量が単調増加するため）。install で「同期する／ローカルのみ」を選べる。
- **パソコンと実行層を区別する**：WSLは独立パソコンではなくWindows上の実行環境として扱い、現在の
  computer/runtimeを各入力前にモデルへ渡す。localhost・127.0.0.1・端末固有パスを含む記憶は作成元を保持し、
  現在のパソコンとの一致と到達可能性を確認できない限り、利用可能な場所として案内しない。

## スコープ（境界＝engine に入るか、カセットか）
- **engine（配布・`src/watari_cli/`）**：CLI・記憶エンジン・人格スキル・git 同期層・クラウド中継アダプタ。
  汎用・開発者個人に非依存。組み込み transcript は **Pi 一本**（runtime が Pi のため）。
- **カセット（user・WATARI_HOME / config.json）**：記憶(log/state)・connector 宣言・host record・秘密。
  ユーザー個人の Gmail / Obsidian 等の連携は**全部こちら**（各ユーザーが `watari connect` /
  `watari connector add` で宣言）。
  Linear など組み込みコネクタは `watari connect --legacy` が認証（config.json の connectors_auth）と
  宣言を一本化し、`watari connector read <name>` が決定論で読む（読み方をエージェントに書かせない）。
- **作らない**：`daily_report`（日報）/ `knowledge`（参照資料）は engine に移植しない。
  スケジューラも同梱しない（cron 等の外部に任せる。`docs/scheduled-organize.md`）。

## MCP標準接続とダッシュボード（現行main）
- `watari connect` はPi MCP Adapter 2.37.0以降の対話画面を開く。独自MCP transport/OAuth実装は持たない。
  Adapterは本人が `pi install npm:pi-mcp-adapter@2.37.0` で導入する。未導入時は案内のみで、自動installしない。
  `watari chat` は導入済みAdapterを追加読込する。接続専用Piはモデルへの入力を拒否し、MCP管理だけに使う。
- URL登録は本人が接続名・HTTPS URL・保存先を確認してから行う。クエリ・userinfo・変数を含むURLは拒否。
  共通設定 `~/.config/mcp/mcp.json` へ新規追加し、同名の別定義は上書きしない。新規定義はlazy・tool承認あり。
  OAuth/APIキーを新たに取得したり別領域へ転記したりしない。既存の共通設定は保持する。MCPの設定発見・認証・実行はAdapterの責任。
  MCP設定・認証は各パソコンのPi/共通MCP設定に置き、記憶フォルダへ同期しない。
  MCPサーバーは信頼したものを本人が選ぶ。stdioはローカルコード実行を伴い、Security v1の隔離を提供しない。
- 旧サービス接続は `watari connect <service> --legacy` に残す。ローカル資料（Obsidian/Claude Code/Codex）と
  `watari auth` の会話同期は既存の専用機能を維持。自動移行・認証情報転記・既存読取の削除は行わない。
  MCP追加だけで定期収集・記憶整理の対象にはしない。外部送信の事前承認・Slack専用送信の境界は変えない。
- `watari dashboard` / `/dashboard` / `watari_dashboard` は同梱の読取専用画面を開く。
  機能・記憶のまとめ・閉じた話題を含む記録と出典・MCP/旧接続・パソコンごとの読取位置・設定を表示する。
  会話から開いた場合は、その時点のモデル・provider・思考設定・有効な道具名も表示する（秘密や道具引数は渡さない）。
  記録は検索・ページングする。JSON出力も可能。認証設定は許可した項目だけを投影し秘密値は表示しない。
  本文と出典は本人の記憶そのものなので機微情報を含み得る。画面の記憶データをAIや外部へ送らない。
- 表示は外部API・Git・モデルを呼ばない。MCP設定/キャッシュはAdapter公開の読取APIを使用する。
  「登録済み」「過去に取得したツール一覧」「接続状態未確認」を区別し、保存済み設定から疎通成功を推測しない。
- HTTPは127.0.0.1の空きポートだけ。32byteランダムtokenをfragmentで渡し、APIは専用headerで認証する。
  Host/Originを検証、no-store/CSP/no-referrer、外部asset・HTML埋込・書込APIなし。APIアクセスログなし。
  固定の記憶/設定ファイルだけを読む。symlink・hardlink・特殊ファイル・未知version・破損を拒否する。
  1ファイル32MB、記録合計10万件・1件1MBを上限とし超過時は見えるエラー。中断保存の復旧やファイル修正はdashboardから行わない。
  起動時にhealth到達確認し、1時間未使用で終了。常駐サービス登録はしない。URLは当該PC専用で共有しない。
- これは非Securityのmain保守機能でありSecurity v1の完成・隔離・リリースを示さない。
  合成ファイル・模擬Pi・loopback HTTPで検証し、開発者の実サービス・秘密・記憶は使用しない。

## 現在地（status — 変わったら更新する）
- **スキルの段階的読取・Pi専用の記憶操作**：常時渡すSKILL.mdは人格・安全境界・作業別資料の案内に絞り、
  選別基準と保存・整理手順は同梱MEMORY.mdへ集約する。/remember・/organizeは手順を複製せず同資料を参照する。
  `pi/memory-tools.ts`は追加検索・話題別根拠取得・取得済み会話の選別準備・保存をPiの道具として公開する。
  `memory_operations.py`は既存extract/ingest/audit/Git同期を再利用し、batchからts/source/refsとadvance引数を生成する。
  AIから日時・作成元・cursorを受けず、各user UUIDの残す／見送る判断を必須とし、assistantは文脈専用とする。
  会話は40件目安・同時刻境界維持・32KBのbatchとし、範囲超過時は切り捨てず従来手順へ戻す。currentは直近の本人発話のみ、
  読み取り位置を進めない。native toolは一つの発話でkindごと一件までとし、同kindの黙った取りこぼしを拒否する。
  batch IDはプロセス内に最大8件・30分保持し、session/homeに束縛する。分岐変更・終了・再起動では失効する。
  同じIDで違う内容は拒否し、同じ内容の再送は保存済み結果または既存dedupで確認する。保存成功と検査・同期警告を分離する。
  検索は既存の順位付けを共用し、正確な話題名から閉じた項目を含む根拠を最大20件・32KBでページ取得できる。
  `WATARI_PYTHON`はlauncherが自身のPythonを渡し、shellなしの固定module・上限付きstdin/stdoutで呼ぶ。常駐server・MCPは追加しない。
  バックグラウンド整理にも同じ道具を渡し、その作業時だけMEMORY.mdを事前展開する。会話以外のサービスの整理は既存CLI手順を維持する。
  この入口は手順ミス削減用で、悪意あるローカルプロセスを認証する境界やSecurity v1のbrokerではない。
  モデルによる内容選別の正確さ・呼び忘れ・実環境での性能向上は自動保証しない。手順・包装・synthetic実行を試験対象とする。
- **0.1.1 信頼性修正**：親Gitリポジトリへの誤コミットを拒否。記憶の検査・更新・再生成・Git操作を
  メモリフォルダ単位のプロセス間ロックで直列化し、全出力を保存前に検証。中断した保存はversion 1の
  redo journalから再開する（journal・一時ファイルはGitに含めない）。通常のstatus/helpは副作用なし。
  同日更新の識別、ページ取得完了の確認、時刻のinstant比較、境界同時刻の保持、未知形式の拒否を追加。
  詳細な契約・互換性・残る実地検証は `docs/design/reliability-0.1.1.md` に記載。
  Slackは接続時にteam/bot/user IDを固定し、投稿前にauth.testで照合。旧設定での投稿は再接続まで拒否。
  Piのfastモードは成功toolを実際に自動evidence化し、巨大な識別子があっても容量上限を守る。
  開発用Gitガードは読み取り専用に変更し、未検証の変更を自動commit/pushしない。
  CIはLinux/macOSとPython 3.11/3.13、Pi 0.84.2の実hookを検査する。CI準備時のみ公開のPython/npm依存を
  ダウンロードする（製品の外部サービス・認証・ユーザー記憶には接続せず、テストは合成データのみ）。
- **実装済み・検証済み**：CLI 一式（status/host/scan(旧 dream。dream は隠し alias)/recall/ingest/
  audit/regen/init/install/auth/chat/performance/connect/connector）、記憶エンジン、人格スキル同梱（wheel）。
  クリーンルーム(Docker)で「素の環境に導入→カセット
  clone→recall に実記憶→Pi 上で人格＋記憶付きに起動」を実証。人格は原本に寄せて調整済み。
- **公開品質化（public-ux）済み**：
  - ユーザー可視の語彙を全面刷新（末尾の用語マップが正）。`watari dream` は `watari scan` に改名
    （dream は隠し alias として受理。表示は scan のみ）。自動整理のトリガ語は「記憶を整理して」
    （「夢を見て」も同義として受理するが、どの表示にも出さない）。
  - 同梱スラッシュコマンド（`src/watari_cli/skill/prompts/*.md`：/remember /organize /profile
    /forget /goal /watari-help）。`watari chat` が `--prompt-template` で Pi に登録する。
  - `watari brief` と同梱 `pi/briefing.ts`：記憶・Gmail・Google Calendar・Linearの現状態から
    deadline / upcoming event / unread / latest-inbound-without-later-send を抽出。起動時＋15分ごと、
    最大3件、同一fingerprintは24時間抑制。確認事項はPiの画面専用entryとして表示し、モデルの入力には
    含めない。旧版が会話メッセージとして保存した確認事項も後続のモデル入力から除外する。
    サービス更新と記憶取り込みcursorは一切動かさない。
  - `watari chat` 起動時の本体自動更新：PEP 610 `direct_url.json` から導入元checkoutを特定し、
    uv tool配下で実行中・clean main・origin/mainへfast-forward可能な場合だけfetch→merge→
    `uv tool install --force --refresh`→process再起動。checkoutが既に最新でも、取得フォルダとインストール済み
    ファイルの不一致を検出したら再インストールして反映漏れを修復する。失敗時はcheckoutを旧HEADへ戻し、
    次回再試行できる。更新後は旧/新SHAとcommit件名を最大10件表示。`--no-update`で1回だけ無効化できる。
  - 同梱 `pi/performance.ts` / `performance.mjs`：`/performance` の選択UI、モード共有、thinking切替、
    `watari performance --set` 経由のconfig永続化、フッター表示。balanced既定、fastはoff、butlerはhigh。
  - 同梱 `pi/memory-context.ts` / `memory-context.mjs`：各入力の `before_agent_start` で
    life/learning state をローカル読取する。factのprofile.modeをalways（毎回）/relevant（関連時検索）に分離し、balancedはalways profile最大5KB・優先thread最大3件・関連fact/topic最大6件・profile/fact/topic名catalogを区画別予算つき16KB以内、fastは4KB/1件/3件/catalog無し、butlerは全stateをsystem promptへ一時注入する。検索は題名・タグ・固有語を優先し、一般的な短い否定表現だけの誤一致を拒否する。always profileの5KB超過はauditで検出。モデル・network・subprocessを呼ばず、transcriptへ積まない。
    `pi/runtime-context.mjs` はWindows/Mac/Linuxとnative/WSLを分離して毎入力へ添え、WSLをWindowsパソコンとして扱う。
    会話同期とscanは発話元のmachine/computer/runtimeを運び、log refsからローカルURL・端末固有パスのoriginを
    stateへ残す。旧記録もMac/Windows固有cwdを安全に判別できる場合だけ補完する。
  - 同梱 `pi/verification-guard.ts`：質問ターンで成功したtool callを追跡し、balanced/butlerでは
    `watari_evidence` で登録する。fastでは成功toolを自動登録して余分なモデル1往復を省く。未確認または
    推測表現を含む最終回答は隠さず、小さな警告行を添える。
  - 同梱 `pi/file-links.ts`：毎回答のFiles欄は出さず、回答本文で実際に案内したローカルファイルの
    絶対パスだけをクリック可能にする。owner管理の通常ファイル・許可root・非symlink/hardlink・非秘密名を
    検証し、本人専用鍵のHMAC付き`watari-file` URLへ表示直前に置換する。Herdr pluginに加え、WSLでは
    `watari chat`起動時にWindowsの現在ユーザーへURL起動設定を登録し、固定の`wsl.exe`→内部コマンド
    （shell不使用）で再検証してExplorerに表示する。
  - `watari chat` はPi公式APIだけを使う同梱拡張 `pi/thinking-progress.ts` と `pi/compact-tools.ts` により、
    reasoning、effort、AI処理に必要な会話データを変えず、Thinking要約をチャット欄最下部の作業中1行へ
    順次差し替える。この要約は会話欄へ残さない。AIが作業前・途中に自然言語の本文を返した場合は
    ストリーミング中から通常の会話として表示し、確定後も保存するが、定型の進捗メッセージは強制しない。
    tool実行の呼び出し行と結果は通常表示から完全に隠し、Ctrl+OでPi本来の完全な呼び出しと結果へ展開する。
    同梱 `politeness-guard.ts` / `politeness.mjs` は保存前に明白なタメ口を決定論で書き換え、未知の違反は
    安全な敬語文へ fail closed する。モデルとPiのグローバル設定は
    ユーザー側のまま。thinkingだけは明示選択した性能モード中に限り fast=off / butler=high へ切り替える。
  - 焼き込みの Google OAuth クライアント（`_BUNDLED_CLIENT_ID` / `_BUNDLED_CLIENT_SECRET`）は
    削除。同期を使う利用者は自分の OAuth アプリを登録する（`docs/google-oauth-setup.md`）。
  - README は日本語正本（冒頭に英語要約）・ユーザー導線に全面改稿。設計記録は `docs/design/` へ隔離。
- **組み込みコネクタ（Linear / GitHub / Notion / Slack / Chatwork / freee / Gmail / Google カレンダー /
  Google ドライブ）**：`watari connect <name> --legacy` が
  案内→貼り付け→疎通確認→config 保存→ connector 宣言(scope既定cloud)まで一本道。`watari connector
  read <name> [--since TS] [--json]` が各サービスの決定論リーダーで統一形式 {ts,uuid,text,meta} を
  昇順で返す（HTTP は urllib のみ）。Linear は「自分が担当/作成した issue の updatedAt>since」
  （viewer クエリで疎通確認）。GitHub は Fine-grained PAT 認証・「自分が関与する issue/PR の
  updated>since」（`GET /user` で疎通確認、GitHubの必須条件に合わせ `is:issue` / `is:pull-request` を
  別々に検索し、各100件ずつ全ページを取得。不完全結果や検索上限超過はエラーとして前進しない）。Notion は
  Internal Integration Token 認証・「since 以降に編集されたページ」（`GET /users/me` で疎通確認、
  Search API に時刻フィルタが無いため `last_edited_time` 降順取得＋クライアント側フィルタ、
  next_cursorを辿って全ページを取得、本文は書き写さずタイトル＋ポインタのみ）。Slack は User OAuth
  Token（`xoxp-`、案内内のマニフェストから作成したアプリをインストールして発行）貼り付け・
  `search.messages` を `from:<@自分>` と自分へのメンションの2クエリで取得し ts で統合＋uuid dedup
  （`auth.test` で疎通確認、HTTP 200 でも body の ok を必ず検査、`after:` は日付粒度のため同日再取得は
  dedup 任せ）。同じSlack appにbot userを追加し、bot scopeは招待済みチャンネルだけへ送れる
  `chat:write`のみ（`chat:write.public`なし）。読み取り用xoxp-と投稿用xoxb-を別々に検証・保存し、
  `watari_slack_send`が送信元・送信先・宛先・全文をPi対話画面へ表示して本人が承認した1回だけ
  `chat.postMessage`を実行する。検索結果のpermalinkからthread_tsも保持し、既存スレッドへ正しく返信する。
  Chatwork は API トークン貼り付け・`GET /rooms` で since 以降に更新された部屋を最大
  10件に絞り各部屋のメッセージを取得（`GET /me` で疎通確認）。urllib transport は
  `connector_http.py` に共通化（重複回避）。freee は他と違い貼るのが Client ID/Secret で、
  `verify()` 自身が「入力→ブラウザ認可(loopback 優先、127.0.0.1:8787固定→空きポート→
  失敗時は oob `urn:ietf:wg:oauth:2.0:oob` にフォールバック)→トークン交換→事業所選択」まで
  完結する（auth_kind="oauth" の「貼り付けプロンプトなし」経路に乗せ、専用の3個目の auth_kind は
  増やさない。`ServiceAdapter.connected` にサービス自前の接続判定を持たせられるよう
  connectors.py を汎用化し、cloud.py の Google OAuth 前提から独立させた）。アクセストークンは
  6時間・リフレッシュトークンは90日で**使い捨て（ローテーション）**のため、更新のたびに新しい
  refresh_token を必ず config へ上書き保存してから access_token を返す。invalid_grant/90日失効は
  「再接続が必要です」と明示。事業所(company_id)は `GET /api/1/companies` を1回叩き、1件なら
  自動選択・複数なら選ばせて保存。読み取りは `GET /api/1/deals`
  （`start_issue_date=sinceの日付`, 1ページ=100件打ち切り）で、取引先/勘定科目は一覧応答が
  ID しか返さないため名称が拾えるときだけ表示（正本は freee のまま）。Gmail / Google カレンダー /
  Google ドライブは
  トークン貼り付けではなく、発話中継所（drive.appdata）用に確立済みの Google OAuth を
  **incremental scope**（`cloud.authorize(scopes)`、`include_granted_scopes=true`）で
  サービスごとに1スコープずつ拡張する方式（`cloud.granted_scopes()` が付与済み一覧を保持）。
  Gmail は `gmail.readonly`・`GET /users/me/messages`（`q=after:<since の epoch秒>`）→ 各
  メッセージを `format=metadata`（From/Subject/Date）+snippet で取得（続きのページをすべて取得し、本文は
  書き写さない）。カレンダーは `calendar.readonly`・primary カレンダーの `events.list
  (updatedMin=since, showDeleted=true)`。ドライブは `drive.metadata.readonly`・`files.list
  (q=modifiedTime>since, orderBy=modifiedTime)` でメタデータのみ。3つとも `watari connect` は
  貼り付けを求めずブラウザ承認のみ（未接続時に必要スコープだけを追加要求）。接続済み表示は
  保存済み設定だけで決めず、refresh token の実交換と各サービスのプロフィール用 API の読み取りに
  成功した場合に限る（削除済みclient・許可取消・対象API無効を接続済みと誤表示しない）。Gmail/ドライブは
  「制限付き(restricted)スコープ」のため External・未確認のままだと使えない場合がある
  （`docs/google-oauth-setup.md`、Google Workspace なら Internal 推奨）。
  Claude Code / Codex は他の組み込みコネクタと違い**認証そのものが不要**（ローカルの会話ログを
  読むだけ）なので auth_kind に第3の値 "local" を追加した：`watari connect claude-code` /
  `watari connect codex` は既定の置き場（`~/.claude/projects` / `~/.codex/sessions`）を自動検出し、
  見つかれば「◯◯ の会話ログを見つけました（<パス> / セッション<n>件）」と表示して保存、
  見つからなければパスの直接入力を促して検証・保存する。scope は他の組み込みコネクタの既定
  "cloud" と違い **"local"**（各マシンが自分のログを自分で夢に見る。cloud の「担当1台」ルール
  （＝cloud スコープの connector は同期グループ内のどれか1台だけが夢で読む取り決め。詳細は
  MEMORY.md）は当てはまらない）。読み取り行には Pi transcript と同じ `role`（"user"/"assistant"）を必ず持たせ、
  記憶の根拠にしてよいのは role=user のみ（assistant は文脈用）。Claude Code の本物のユーザー発話は
  `type=="user"` かつ `message.content` が文字列（配列除外）かつ `toolUseResult` 無し・
  isMeta/isCompactSummary/isSidechain 無し・timestamp 有り・合成行（`<system-reminder>` 等）でない
  行。Codex は `session_meta`（1ファイルに複数回現れうる）で cwd/session を逐次更新しつつ
  `event_msg`（payload.type が user_message/agent_message）を拾う——**Codex はセッション再開の
  たびに過去の全発話を新 session id・新 timestamp で丸ごと再記録する実バグがある**ため、
  セッションを (最初の発話ts, パス) で順序付けし、ファイル先頭から連続する「既出の
  (cwd,role,text)」プレフィックスをリプレイと判定して捨てる（novel な発話以降は同文でも残す）。
  パス/形式が未検証の CLI は REGISTRY に載せない（選べるのに使えない行を作らない）。
  一次情報が取れた時点で本実装のアダプタとして追加する。
- **マルチマシン同期（main にマージ済み）**：git 同期層／Drive appDataFolder 中継／chat の抽出スレッド／
  夢が共有ストリームを読む＋クラウド削除／chat 起動時の裏 dream。Google 認証は `watari auth` に集約
  （client_id/secret は env/対話で受け取り config.json に保存、install の承認も同経路）。chat起動時は
  保存済み認証から送信処理を用意し、ネットワーク検査は行わず、実送信時の失敗を通知する。
  失敗時の再認証案内は認証情報の欠落または明示的なOAuth拒否に限定し、通信障害・429/5xx・不明な応答は
  認証切れと断定しない。未送信発話はローカルキューへ残し、通信・認証の復旧後は同じchat内で再送する。
  待機は5秒から倍増し最大300秒、認証拒否・データ修復待ちは300秒。
  同じ障害種別の警告は復旧まで1回とし、実送信とキュー消去が成功した時だけ復旧を通知する。
  キューの大きさだけでは再認証を要求しない（完全未設定の利用者には警告もキューも作らない）。
  接続確認・再送は既存のGoogle OAuth/Drive経路のみを使い、診断用の外部送信や秘密の出力は追加しない。
  合成データによる回帰試験は `tests/test_relay_recovery.py`、既存の認証・送信契約は
  `tests/test_cloud.py` / `tests/test_relay.py` で検証する。
  Drive v3のmedia読み取りにstrong ETagがない場合、同一IDをv2で再読取する。本文取得の前後で
  file metadataのETag・versionが同じことを確認し、本文・file ETag・API版を一組として保持する。
  download用ETagとは区別し、条件付き更新もv2へ固定する。ETag欠落や競合時の無条件上書きは禁止する。
  同名データの重複は自動削除せず、再認証ではなくデータ修復が必要と通知する。
- **Obsidianの安全な固定読み取り（実装・テスト済み）**：旧カスタム指示に依存せず、設定済みvaultの
  Markdownだけをlocal connectorとして読む。読み取り先をvault内へ固定し、内部設定・派生まとめ・
  隠し領域・symlinkを除外、件数/文字数を境界時刻を落とさず制限する。
- **Google OAuth セキュリティ強化（実装・テスト済み）**：インストール型アプリのloopback認可へ
  PKCE S256（RFC 7636）を追加し、認可コードを横取りされても一時verifierなしでは交換できない。
  秘密を含むローカル設定はPOSIXでフォルダ700・ファイル600へ毎回補正し、緩いumaskや既存644を
  引き継がない。`watari auth` はtoken endpointの `deleted_client` を事前検出し、保存済みclientを
  再利用してブラウザで401になる代わりに、有効なclient ID / secretの入力へ切り替える。別のパソコンで
  動いている同一clientを再利用でき、新規作成は必須にしない。差し替え時は旧clientに属するrefresh tokenと
  scopeを破棄し、各パソコンで個別にブラウザ認証する。
- **未了（実地検証）**：Google OAuth アプリ登録（`docs/google-oauth-setup.md` の手順）→ 各マシンで
  `watari auth` → 2台間の会話同期を実機で確認する。コード・テストは整備済みで、実環境での通し確認が
  残タスク。client_id 未設定の間は同期はスキップされ、ローカルのみで普通に動く。

## 主要決定（蒸し返さない）
- ランタイムは **Pi 専用**。`watari chat` は Pi ランチャー。モデルは Pi 側で選ぶ（install は非依存）。
  性能モードはモデルを変えず、ユーザーが明示選択したときだけthinkingと記憶量・確認往復を変える。
- **敬語はユーザープリファレンスではなく製品不変条件**。ユーザーの入力口調を模倣せず、スキル指示に加えて
  Pi の表示・message_end ガードで明白な違反を保存・表示前に止める（モデルの遵守だけに依存しない）。
- **transcript は Pi 一本**、それ以外（他 AI CLI・メール・タスク・チャット等）は connector 宣言。
- **Obsidian は組み込みlocal connector**。vault内のMarkdownだけを読み、`.obsidian`・隠しフォルダ・
  `Journal/Watari`・symlinkを除外する。旧自由記述の `vault=<path>` は実在vaultに限り構造化パスへ移行し、
  自由記述をshellとして実行しない。
- **従来方式の接続は案内型 wizard**：`watari connect <service> --legacy` が「案内→貼り付け→その場で実 API
  疎通確認→config 保存→connector 宣言」を一本化する（生コマンドをユーザーに打たせない原則の延長）。
  第一弾は Linear（Personal API key）。読み取りは `watari connector read <name>` が決定論で行い、
  夢のエージェントはツール固有の API を知らなくてよい。カスタム connector（`connector add` の自由記述
  read 指示）は上級者向けの逃げ道としてそのまま残す。Slack/Gmail/Calendarを含む現在の対応範囲は上記の実装一覧を参照。
- **daily_report / knowledge は engine 非移植**（カセット or 別途）。
- **忘却は3層**：active(<45日) / dormant(45–90日・声かけ待ちの印) / sunk(≥90日・沈むが log に残る)。
  実時計ベース。取り込みカーソルは **per-machine の host record**（git 共有で衝突しない）。
- **環境識別**：同期互換のため既存 `machine_id` は変更しない。別フィールドの `computer` は
  windows/mac/linux、`runtime` はnative/wslとし、WSLはWindowsパソコンへ属する。ローカル資源の記憶は
  `refs.machine/computer/runtime` を作成元として保持し、現在環境との照合に使う。
- **マルチマシン同期**：記憶は **git**（消えない正本・履歴が価値）、生の発話素材は **クラウド中継所**
  （消せる・機械可読）と使い分ける。中継所は **Google Drive appDataFolder**（ユーザーの Drive に出ない・
  API で削除可）。中身は **user＋assistant の発話だけ**（tool 出力・thinking は入れない）。書き込みは
  **chat のラッパー（会話中に逐次）**で、LLM にはやらせない。夢は **chat 起動時に裏で自動実行**（夜間 cron は
  前提にしない）。消化済み＋90日超の中継発話は削除対象とし、条件付き更新ができない場合は保持して次回再試行する。確定設計は `docs/design/plan-transcript-sync.md`。
- 経緯：先行プロトタイプは撤去し、本リポジトリ（watari-cli）に一本化した。

## ユーザー向け語彙（用語マップ）

ユーザーが目にする文言（CLI 出力・ヘルプ・エラー・ウィザード・README・ワタリの発話）では、
内部用語を使わず次の語彙に統一する。エージェント（LLM）だけが読む内部指示（SCHEMA.md の仕様部・
docstring・コメント・本ファイル）は正確さ優先で従来語を使ってよい。

| 内部用語（ユーザーに出さない） | ユーザー向け正式語彙 |
|---|---|
| 夢 / dream / 夢を見て / 夢に流し込む | **記憶の整理**（動詞: 記憶を整理する）。ソースは「整理のときに読み込む」 |
| 後で効く・あとで効く | あとで役に立つ |
| カセット / cartridge | **記憶フォルダ**（あなた専用の記憶データ。git リポジトリとして持ち運べる） |
| 発話中継所 / 中継所 | **会話の同期**（Google Drive のアプリ専用領域を使った同期） |
| 担当1台だけが夢を見る | **接続したパソコンが読み取り担当**（他のパソコンでは同じサービスを接続しない） |
| 正本 / 派生 / 決定論 | 記録の原本 / 自動生成のまとめ /（言及しない） |
| カーソル | どこまで読んだかの記録（読み取り位置） |
| state / log（ユーザー向け行で） | 記憶のまとめ / 記憶の記録 |
| スラッグ | 小文字の英数字とハイフン（例: my-notes） |
| ランタイム | AI ランタイム（Pi）※初出時に「ワタリを動かす AI ツール」と一言注釈 |
| 組み込みコネクタ / 疎通確認 | 対応サービス / 接続テスト |
| ingest / regen / recall / audit / scan（説明文中） | 内部コマンド。ヘルプでは「ワタリが自動で使います」と明示 |
| マシン / パソコン の揺れ | ユーザー向けは「パソコン」に統一（host 記録の説明もパソコン） |

コマンド名：`watari dream` → **`watari scan`**（隠し alias で dream も受ける。表示は scan のみ）。
自動整理のプロンプトと SKILL のトリガ：「記憶を整理して」（「夢を見て」は同義として受理するが、
どの表示にも出さない）。

## 読む順
1. **このファイル**（何を・今どこ）→ 2. `AGENTS.md`（開発規律・安全境界）→
3. 作業に関係する資料だけ：`SCHEMA.md`（記憶の形式変更）、`SKILL.md`（人格・安全境界）、
   `MEMORY.md`（記憶の選別・保存・整理手順）。
（利用者向けの導入・使い方は `README.md`。）
