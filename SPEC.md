# watari-cli 仕様（最初に読む）

このファイルは watari-cli が **何を目指し・何を満たし・今どこまで来ているか** の正本。
毎回ゴールを口頭で説明しなくて済むよう、ここを読めば全体像と現在地が分かる状態を保つ。
（記憶エンジンのデータ仕様は `src/watari_cli/skill/SCHEMA.md`、人格と夢の手順は同 `SKILL.md`、
開発規律・安全境界は `AGENTS.md`。このファイルは「なぜ・何を・今どこ」を担う。）

## ゴール（north star）
「ワタリ」＝ユーザーの分身。**記録・伴走・リマインド**を、決まった動き方で続ける秘書。
それを **器（engine＝配布物）と カセット（user＝記憶・設定）に分離**した、配布可能な CLI にする。
- **Pi 上で動く**：どのモデルと話しても、その会話をワタリが夢に見る（判定はモデル、機械処理は CLI）。
- **記憶は持ち運べる**：個人データ（log/state）は git で運べるカセット（WATARI_HOME）。
- **器を他人に渡せば、その人が自分のワタリを育てられる**：＝ binge 固有物を engine に一切漏らさない。

## 満たすこと（要件）
- **記録**：会話から「後で効く事実」だけを自動で記憶へ移す（夢ループ）。
- **伴走**：state（現在地）を初期姿勢に、最初の一文から反映して話す。
- **リマインド**：進行中(open_threads)・締切(deadline)・休眠(dormant)の声かけ。
- **決定論**：log＝正本（追記専用）→ state＝派生（log から再生成）。同じ log＋now なら必ず同じ state。
- **モデル非依存**：判定はランタイム上のモデル、機械処理は CLI。**CLI はモデルも MCP も呼ばない**。
- **持ち運び**：記憶は WATARI_HOME（git リポ）。`watari install` で挿せば「その人のワタリ」。
- **ユーザーに生コマンドを手組みさせない**：`watari install` で watari の担当（記憶カセットの用意）が
  menu で完結し home も保存される。以後ユーザーは `watari chat` を打つだけ（`--home` も不要）。
  **モデル・認証は Pi の担当**（Pi が起動時に選ばせ・`/login` し・自分で覚える）。watari はそれを
  肩代わり・重複しない（watari ≠ Pi の分離。install で「どの AI で動かすか」は尋ねない）。
- **どのマシンでも同じワタリ（マルチマシン同期）**：記憶(カセット)は git で同期（読む前に pull・書いた後に
  push、union-merge）。会話は各マシンの chat が **クラウド中継所（Google Drive appDataFolder）**へ user＋
  assistant の発話だけ送り、どのマシンの夢もそれを読む＝A で話した分を B のワタリが覚える。生 transcript は
  git に入れない（履歴から消せず容量が単調増加するため）。install で「同期する／ローカルのみ」を選べる。

## スコープ（境界＝engine に入るか、カセットか）
- **engine（配布・`src/watari_cli/`）**：CLI・記憶エンジン・人格スキル・git 同期層・クラウド中継アダプタ。
  汎用・binge 非依存。組み込み transcript は **Pi 一本**（runtime が Pi のため）。
- **カセット（user・WATARI_HOME / config.json）**：記憶(log/state)・connector 宣言・host record・秘密。
  binge の Gmail / Obsidian 等の連携は**全部こちら**（`watari connector add` で自由記述宣言）。
  Linear など組み込みコネクタは `watari connect` が認証（config.json の connectors_auth）と
  宣言を一本化し、`watari connector read <name>` が決定論で読む（読み方をエージェントに書かせない）。
- **作らない**：`daily_report`（日報）/ `knowledge`（参照資料）は engine に移植しない。
  スケジューラも同梱しない（cron 等の外部に任せる。`docs/headless-dream.md`）。

## 現在地（status — 変わったら更新する）
- **実装済み・検証済み**：CLI 一式（status/host/dream/recall/ingest/audit/regen/init/install/auth/
  chat/connect/connector）、記憶エンジン、人格スキル同梱（wheel）。クリーンルーム(Docker)で「素の環境に導入→カセット
  clone→recall に実記憶→Pi 上で人格＋記憶付きに起動」を実証。人格は原本に寄せて調整済み。
- **組み込みコネクタ（Linear / GitHub / Notion / Slack / Chatwork / Gmail / Google カレンダー /
  Google ドライブ）**：`watari connect <name>` が
  案内→貼り付け→疎通確認→config 保存→ connector 宣言(scope既定cloud)まで一本道。`watari connector
  read <name> [--since TS] [--json]` が各サービスの決定論リーダーで統一形式 {ts,uuid,text,meta} を
  昇順で返す（HTTP は urllib のみ）。Linear は「自分が担当/作成した issue の updatedAt>since」
  （viewer クエリで疎通確認）。GitHub は Fine-grained PAT 認証・「自分が関与する issue/PR の
  updated>since」（`GET /user` で疎通確認、Search API は1ページ(per_page=100)打ち切り）。Notion は
  Internal Integration Token 認証・「since 以降に編集されたページ」（`GET /users/me` で疎通確認、
  Search API に時刻フィルタが無いため `last_edited_time` 昇順取得＋クライアント側フィルタ、
  1リクエスト(page_size=100)打ち切り、本文は書き写さずタイトル＋ポインタのみ）。Slack は User OAuth
  Token（`xoxp-`、案内内のマニフェストから作成したアプリをインストールして発行）貼り付け・
  `search.messages` を `from:<@自分>` と自分へのメンションの2クエリで取得し ts で統合＋uuid dedup
  （`auth.test` で疎通確認、HTTP 200 でも body の ok を必ず検査、`after:` は日付粒度のため同日再取得は
  dedup 任せ）。Chatwork は API トークン貼り付け・`GET /rooms` で since 以降に更新された部屋を最大
  10件に絞り各部屋のメッセージを取得（`GET /me` で疎通確認）。urllib transport は
  `connector_http.py` に共通化（重複回避）。Gmail / Google カレンダー / Google ドライブは
  トークン貼り付けではなく、発話中継所（drive.appdata）用に確立済みの Google OAuth を
  **incremental scope**（`cloud.authorize(scopes)`、`include_granted_scopes=true`）で
  サービスごとに1スコープずつ拡張する方式（`cloud.granted_scopes()` が付与済み一覧を保持）。
  Gmail は `gmail.readonly`・`GET /users/me/messages`（`q=after:<since の epoch秒>`）→ 各
  メッセージを `format=metadata`（From/Subject/Date）+snippet で取得（50件/回打ち切り、本文は
  書き写さない）。カレンダーは `calendar.readonly`・primary カレンダーの `events.list
  (updatedMin=since, showDeleted=true)`。ドライブは `drive.metadata.readonly`・`files.list
  (q=modifiedTime>since, orderBy=modifiedTime)` でメタデータのみ。3つとも `watari connect` は
  貼り付けを求めずブラウザ承認のみ（未接続時に必要スコープだけを追加要求）。Gmail/ドライブは
  「制限付き(restricted)スコープ」のため External・未確認のままだと使えない場合がある
  （`docs/google-oauth-setup.md`、Google Workspace なら Internal 推奨）。
- **マルチマシン同期（main にマージ済み）**：git 同期層／Drive appDataFolder 中継／chat の抽出スレッド／
  夢が共有ストリームを読む＋クラウド削除／chat 起動時の裏 dream。Google 認証は `watari auth` に集約
  （client_id/secret は env/対話で受け取り config.json に保存、install の承認も同経路）。196 テスト＋packaging green。
- **未了（本物で動かす）**：Google OAuth アプリの登録（binge 手動・`docs/google-oauth-setup.md`）→ 各マシンで
  `watari auth` → A↔B の会話同期を実地確認。client_id 未設定の間は同期はスキップされ、ローカルのみで普通に動く。

## 主要決定（蒸し返さない）
- ランタイムは **Pi 専用**。`watari chat` は Pi ランチャー。モデルは Pi 側で選ぶ（install は非依存）。
- **transcript は Pi 一本**、それ以外（他 AI CLI・メール・タスク・チャット等）は connector 宣言。
- **Obsidian は connector**（専用フラグを廃止し宣言制へ一本化）。
- **組み込みコネクタは案内型 wizard**：`watari connect <service>` が「案内→貼り付け→その場で実 API
  疎通確認→config 保存→connector 宣言」を一本化する（生コマンドをユーザーに打たせない原則の延長）。
  第一弾は Linear（Personal API key）。読み取りは `watari connector read <name>` が決定論で行い、
  夢のエージェントはツール固有の API を知らなくてよい。カスタム connector（`connector add` の自由記述
  read 指示）は上級者向けの逃げ道としてそのまま残す。slack/gmail/calendar は今回やらない（枠だけ）。
- **daily_report / knowledge は engine 非移植**（カセット or 別途）。
- **忘却は3層**：active(<45日) / dormant(45–90日・声かけ待ちの印) / sunk(≥90日・沈むが log に残る)。
  実時計ベース。取り込みカーソルは **per-machine の host record**（git 共有で衝突しない）。
- **マルチマシン同期**：記憶は **git**（消えない正本・履歴が価値）、生の発話素材は **クラウド中継所**
  （消せる・機械可読）と使い分ける。中継所は **Google Drive appDataFolder**（ユーザーの Drive に出ない・
  API で削除可）。中身は **user＋assistant の発話だけ**（tool 出力・thinking は入れない）。書き込みは
  **chat のラッパー（会話中に逐次）**で、LLM にはやらせない。夢は **chat 起動時に裏で自動実行**（夜間 cron は
  前提にしない）。消化済み＋90日超の中継発話は削除。確定設計は `docs/plan-transcript-sync.md`。
- 経緯：`new-watari` の作り込みは撤去し、watari-cli に一本化した。

## 読む順
1. **このファイル**（何を・今どこ）→ 2. `AGENTS.md`（開発規律・安全境界）→
3. `SCHEMA.md`（記憶のデータ仕様）/ `SKILL.md`（人格・夢の手順）。
