# 実装計画: 組み込みコネクタ（watari connect / connector read）

2026-07-20 確定。動機: 現行の connector は「ユーザーが read 指示を書き、認証も自前」で、
watari-cli の原則（コマンド一発・必要な選択は選択肢で・呪文をユーザーに打たせない）に反する。
`watari auth` が Google 認証を畳んだのと同じ形で、コネクタ接続と読み取りを CLI が内蔵する。

## 設計（変更不可）

1. **`watari connect <service>`**: 案内型 wizard。
   - サービスごとに「どのページを開き・何を作り・何を貼るか」を短い日本語で案内し、貼られた
     認証情報を**その場で実 API 呼び出しして疎通確認**してから config.json に保存する。
   - 成功したら connector 宣言（既存の connectors 設定）も自動登録/更新する。scope は既定 cloud。
   - `watari connect`（引数なし）は対応サービスの選択メニュー。
2. **`watari connector read <name> [--since TS] [--json]`**: 決定論リーダー。
   - カーソル以降の差分を統一形式 `{ts, uuid, text, meta}` の JSON 配列で返す（dream の
     messages[] と同じ思想。夢のエージェントは API を知らなくてよい）。
   - 認証エラー・ネットワーク断は明確なエラーで返し、呼び出し側（夢）はカーソル据え置き。
   - カーソル前進は従来どおり `watari ingest --advance-ext <name>=<ts>` のみが行う。
3. **第一弾サービス = linear**:
   - 認証: Personal API key（案内先 https://linear.app/settings/account/security → API keys。
     入力後に viewer クエリで疎通確認）。config.json の `connectors_auth.linear` に保存。
   - read: GraphQL で「自分が担当 or 作成した issue の updatedAt > since」を取得し、
     issue の現在値（identifier/title/state/dueDate/updatedAt/直近コメント要約）を text に整形。
   - uuid は `linear:<identifier>@<更新日YYYY-MM-DD>`（既存 SCHEMA の慣例と同一）。
4. **custom コネクタは残す**: 既存の `watari connector add --read "..."`（自由な read 指示）は
   上級者向けの逃げ道としてそのまま。`connector list` は組み込み/カスタムを区別して表示。
5. **SKILL.md の夢手順 4 を更新**: 「組み込みコネクタは `watari connector read <name>` で読む。
   カスタムは従来どおり read 指示に従う」。cloud スコープは担当1台ルール従来どおり。
6. **やらないこと（今回）**: slack/gmail/calendar の実装（枠だけ用意し「未対応。今後追加」と
   表示）。MCP 対応。Pi 拡張化。

## 受け入れ条件
- `watari connect linear` → キーを貼る → 「✓ 接続しました（<viewer名> として認証）」まで一本道。
- `watari connector read linear --since <過去ts> --json` が実データを統一形式で返す。
- 認証情報がカセット git に入らない（config.json のみ）。テスト追加・全 green。
- SKILL/README/SPEC の該当箇所更新。

## 付記: Slack の接続手順（実画面に合わせる）

`Create app from manifest` の 2 画面目は「空欄に貼る」ではなく **Demo App の雛形 JSON が入った
エディタ**で、既定タブは JSON。したがって guide は「全選択して置き換える」と明示し、マニフェストは
YAML ではなく **JSON** で提示する（タブ切り替えの手間を消す）。作成後は `Install to Workspace` →
`Allow` を踏まないとトークンが出ない。貼らせるのは **User OAuth Token（xoxp-）**——bot の xoxb- では
`search.messages` が使えない。案内文の各段は実 UI のボタン名をそのまま書くこと。
