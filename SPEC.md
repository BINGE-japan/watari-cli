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
  binge の Gmail / Linear / Obsidian 等の連携は**全部こちら**（`watari connector add` で宣言）。
- **作らない**：`daily_report`（日報）/ `knowledge`（参照資料）は engine に移植しない。
  スケジューラも同梱しない（cron 等の外部に任せる。`docs/headless-dream.md`）。

## 現在地（status — 変わったら更新する）
- **実装済み・検証済み**：CLI 一式（status/host/dream/recall/ingest/audit/regen/init/install/auth/
  chat/connector）、記憶エンジン、人格スキル同梱（wheel）。クリーンルーム(Docker)で「素の環境に導入→カセット
  clone→recall に実記憶→Pi 上で人格＋記憶付きに起動」を実証。人格は原本に寄せて調整済み。
- **マルチマシン同期（main にマージ済み）**：git 同期層／Drive appDataFolder 中継／chat の抽出スレッド／
  夢が共有ストリームを読む＋クラウド削除／chat 起動時の裏 dream。Google 認証は `watari auth` に集約
  （client_id/secret は env/対話で受け取り config.json に保存、install の承認も同経路）。122 テスト＋packaging green。
- **未了（本物で動かす）**：Google OAuth アプリの登録（binge 手動・`docs/google-oauth-setup.md`）→ 各マシンで
  `watari auth` → A↔B の会話同期を実地確認。client_id 未設定の間は同期はスキップされ、ローカルのみで普通に動く。

## 主要決定（蒸し返さない）
- ランタイムは **Pi 専用**。`watari chat` は Pi ランチャー。モデルは Pi 側で選ぶ（install は非依存）。
- **transcript は Pi 一本**、それ以外（他 AI CLI・メール・タスク・チャット等）は connector 宣言。
- **Obsidian は connector**（専用フラグを廃止し宣言制へ一本化）。
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
