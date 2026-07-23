# Watari CLI

> **English summary** — Watari is a personal AI companion that gradually learns about you
> from your everyday conversations. It runs on Pi (an open-source AI agent runtime, fetched
> automatically) and keeps your memory in a small git repository that you own.
> Documentation below is in Japanese; to get started run `watari install`, then `watari chat`.

## ワタリとは

ワタリは、会話から「あとで役に立つこと」（決めごと・予定・好み・学んだことなど）を
少しずつ覚えていく相棒です。`watari chat` で話しかけるだけで、大事なことは自動で記憶に残り、
次の会話では最初のひとことからそれを踏まえて話します。記憶はあなた専用の「記憶フォルダ」
（git リポジトリ）に保存され、プログラム本体とは分かれているので、パソコンを替えても持ち運べます。

## 必要なもの

- **uv**（Python ツールを入れる道具）。未導入なら:
  `curl -LsSf https://astral.sh/uv/install.sh | sh`
  （Windows は <https://docs.astral.sh/uv/> を参照。Python 3.11 以上が必要ですが、
  無ければ uv が自動で用意します）
- **Node.js 22.19 以上**。ワタリを動かす AI ランタイム（Pi）の動作に必要です。
  `node --version` で確認し、古い・未導入なら <https://nodejs.org/> の LTS 版を
  インストールしてください。
- **Pi 自体のインストールは不要です。** `watari chat` が PATH 上の `pi` を使い、
  無ければ `npx -y @earendil-works/pi-coding-agent` で自動取得します。

## はじめかた

1. このリポジトリを取得して中に入る:

        git clone <このリポジトリの URL>
        cd watari-cli

2. インストール:

        uv tool install .

3. 初回セットアップ（対話式。記憶フォルダの場所を決めて保存します）:

        watari install

4. ワタリと話す:

        watari chat

以後は `watari chat` を打つだけです。記憶フォルダの場所は保存済みなので、
毎回指定する必要はありません。

## 本体の自動更新

`watari chat` の起動時に、最初に取得した watari-cli フォルダの `origin/main` を確認します。
新しい変更があり、安全に早送りできる場合は、本体を自動で更新・再インストールしてから起動し、
反映した変更を画面に表示します。

- 対象は、上記手順どおり `git clone` → `uv tool install .` で導入した環境です。
- watari-cli フォルダに未コミットの変更がある場合や、履歴が分岐している場合は上書きしません。
- ネットワークに接続できない場合は、更新せず現在の版で起動します。
- 今回だけ確認しない場合は `watari chat --no-update` を使えます。

この機能を含まない既存版から最初に移行するときだけ、watari-cli フォルダで
`git checkout main && git pull --ff-only && uv tool install --force --refresh .` を一度実行してください。
以後は `watari chat` だけで更新されます。

## 何が起きるか（記憶のしくみとプライバシー）

- 記憶は `watari install` で決めた場所の記憶フォルダに保存されます。中身はただの
  テキストファイルで、いつでも自分で確認・修正・削除できます。
- 覚えるのは会話の全文ではなく「あとで役に立つこと」だけです。ワタリは `watari chat` の
  起動時に、前回の続きから会話を自動で読み返して（記憶の整理）、役立つことだけを記憶に
  追記します。会話の中で「記憶を整理して」と頼む、または `/organize` と打てば
  その場でも実行できます。
- パスワードやトークンなどの秘密そのものは覚えません。
- 記憶が記憶フォルダの外へ自動で送られることはありません（複数のパソコンで使う設定を
  自分で行った場合のみ、あなたの git リポジトリと Google Drive のアプリ専用領域を使います。
  詳しくは後述）。
- 記憶フォルダは git リポジトリなので、プライベートな git リポジトリを同期先に設定すれば
  そのままバックアップになります（`watari install` 中に設定できます。あとからでも可能です）。

## コマンド一覧

よく使うコマンド:

| コマンド | はたらき |
|---|---|
| `watari install` | 初回セットアップ（記憶フォルダの用意と設定の保存） |
| `watari chat` | ワタリと話す（Pi を起動します） |
| `watari connect` | 外部サービスと接続（Gmail・カレンダー・Slack など） |
| `watari brief` | 期限・予定・未返信・未読を実状態から最大3件に絞って確認 |
| `watari status` | 記憶の様子を確認 |
| `watari auth` | Google にログイン（複数のパソコンで会話を同期する場合だけ） |

内部コマンド（ワタリが自動で使います。手で打つ必要はありません）:
`scan` / `recall` / `ingest` / `audit` / `regen` / `init` / `host` / `connector`

詳しくは `watari --help`、各コマンドは `watari <コマンド> --help` を参照してください。

## サービス接続（watari connect）

`watari connect <サービス名>` で、外部サービスの動きをワタリに読ませられます。
接続すると、次の記憶の整理から自動で読み込まれます。Gmail・Google カレンダー・Linearは、
`watari chat` の起動中に期限・近い予定・未返信・未読も読み取り専用で確認し、重要なものを最大3件だけ
知らせます。同じ状態は24時間繰り返しません。

対応サービス: Linear・GitHub・Notion・Slack・Chatwork・freee・Gmail・Google カレンダー・
Google ドライブ・Claude Code・Codex。引数なしの `watari connect` で選択メニューが出ます。

- 多くのサービスは、画面の案内に従ってトークンを 1 つ貼るだけです。貼った内容は
  その場で接続テストをしてから保存されます。
- **Gmail・Google カレンダー・Google ドライブ**は貼り付け不要で、ブラウザでの承認だけです。
  先に Google OAuth アプリの用意（[docs/google-oauth-setup.md](docs/google-oauth-setup.md)）と
  `watari auth` が必要です。承認は `watari auth` と同じ Google アカウントで行ってください。
- **freee** は Client ID / Secret を貼ってからブラウザで承認します（画面の案内どおりで完結します）。
- **Claude Code・Codex** はトークン不要です。パソコン上の会話ログを自動で見つけて
  （見つからなければフォルダの場所を聞いて）読みます。これらの CLI を使っていない場合、
  この接続は不要です。
- 一覧にないツール（参照ノートのフォルダ・Obsidian の保管庫など）は、上級者向けに
  `watari connector add` で読み方を自由記述で登録できます。`watari connector list` で
  登録済みの一覧を確認できます。

## 複数のパソコンで使う

1 台で使う分にはこの節は不要です。複数のパソコンで同じワタリを使いたい場合だけ設定します。

手順:

1. Google OAuth アプリを一度だけ用意する —
   [docs/google-oauth-setup.md](docs/google-oauth-setup.md)（会話の同期に
   Google Drive のアプリ専用領域を使うためです）。
2. 記憶フォルダの同期用に、空のプライベート git リポジトリを 1 つ用意する
   （例: GitHub のプライベートリポジトリ）。
3. 各パソコンで `watari auth` で Google にログインし、`watari install` で
   同じ git リポジトリを指定する。

これだけで、記憶は git を通じて、会話は Google Drive のアプリ専用領域を通じて同期されます。
パソコン A で話したことを、パソコン B のワタリが覚えます。

しくみの補足（読み飛ばして大丈夫です）:

- 同期されるのは、あなたとワタリの発話テキストだけです（ツールの出力は含めません）。
- 会話の生データは git には入れません（git の履歴は後から消せないためです）。
  Google Drive 側は読み終えた分から自動で削除され、最長 90 日で消えます。
- Gmail などの接続サービスは、**接続したパソコンが読み取り担当**になります。
  他のパソコンでは同じサービスを接続しないでください。

## 自動で記憶を整理する（cron など）

`watari chat` を起動するたびに整理は自動で走るので、通常は設定不要です。
パソコンを使わない夜間などにも整理させたい場合は
[docs/scheduled-organize.md](docs/scheduled-organize.md) を参照してください。

## スラッシュコマンド（会話の中で使う）

`watari chat` の会話中に、次のコマンドが使えます。

| コマンド | はたらき |
|---|---|
| `/remember <覚えてほしいこと>` | いま言ったことを確実に記憶に残す |
| `/organize` | 記憶の整理を今すぐ実行する |
| `/profile` | いまワタリが覚えているあなたのことを、平易な言葉で要約する |
| `/forget <話題>` | 指定した話題を記憶から外す |
| `/goal <目標>` | この会話の目標を決めて、達成まで見失わずに進める |
| `/watari-help` | ワタリの使い方をやさしく説明する |

## モデルの切り替え・ログイン（Pi 側）

どの AI モデルで話すかは、ワタリではなく Pi（ワタリを動かす AI ランタイム）の設定です。
会話中に `/model` でモデルを切り替え、`/login` で各プロバイダにログインできます。
詳しくは Pi のドキュメントを参照してください。

相性の良い Pi パッケージ: **pi-codex-goal** — 目標を常時追跡する `/goal` の拡張です。

## トラブルシュート

- 「まだセットアップされていません」と出る → `watari install` を実行してください。
- `watari chat` で Pi が起動しない → `node --version` が 22.19 以上か確認してください。
  未導入・古い場合は <https://nodejs.org/> の LTS 版を。
  `npx -y @earendil-works/pi-coding-agent` が通るかでも確認できます。
- 「会話の同期にログインし直しが必要です」と出る → `watari auth` を再実行してください。
- 接続したサービスの認証が切れた → `watari connect <サービス名>` をもう一度実行してください。
- 「記憶の同期に失敗しました（オフライン？）」と出る → 変更は保存済みです。
  ネットワーク復帰後の実行時に自動で再試行されます。

## 開発者向け

プロジェクトの目的・スコープ・現在地は [SPEC.md](SPEC.md)、記憶のデータ仕様は
[src/watari_cli/skill/SCHEMA.md](src/watari_cli/skill/SCHEMA.md)、開発規律・安全境界は
[AGENTS.md](AGENTS.md) にあります。過去の設計記録は [docs/design/](docs/design/) 配下です。

このリポジトリには製品コードとテストだけが含まれます。ユーザーデータ・認証情報・
実行時の状態は、決してここにコミットされません。
