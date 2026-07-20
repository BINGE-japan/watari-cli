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

## 付記: freee の接続手順（公式仕様の要点）

freee は Linear/GitHub/Notion/Slack/Chatwork と違い「トークン1個を貼る」形にならない：
ユーザーが貼るのは freee アプリの Client ID/Secret だけで、実際の認可はブラウザの freee 画面で
行う。専用の3個目の auth_kind は増やさず、`auth_kind="oauth"`（貼り付けプロンプトを CLI 側が
挟まない経路）に `freee.verify()` 自身が「Client ID/Secret 入力→ブラウザ認可→トークン交換→
事業所選択→config 保存」まで一括で乗せる。gmail/calendar/gdrive と違い cloud.py の Google OAuth
を共有しないため、接続判定は `ServiceAdapter.connected`（サービス自前のフック）を汎用的に
持てるよう `connectors.py` を拡張した（サービス名の分岐は増やしていない）。

- 認可URL: `https://accounts.secure.freee.co.jp/public_api/authorize`。トークンURL:
  `https://accounts.secure.freee.co.jp/public_api/token`（交換は
  `grant_type=authorization_code`、更新は `grant_type=refresh_token`）。
- **アクセストークンは6時間（21600秒）、リフレッシュトークンは90日で使い捨て（1回使うと
  ローテーションし、同じ refresh_token は2度と使えない）**。そのため `freee.access_token()` は
  更新のたびに応答の新しい refresh_token を必ず config へ上書き保存してから access_token を
  返す（保存前に返すと、保存に失敗した回だけ新しい refresh_token を失い次回から認証不能になる）。
  invalid_grant/90日失効は「再接続が必要です（`watari connect freee`）」と明示するエラーにする。
- 認可フローは **loopback を第一候補**にする：127.0.0.1 の固定ポート 8787 で待ち受け、使用中なら
  空きポートへフォールバックする。ポートが確保できない、またはコールバックが来ないまま失敗した
  場合は `redirect_uri=urn:ietf:wg:oauth:2.0:oob`（画面に認可コードが表示される方式）に
  フォールバックし、その場合だけ認可コードの貼り付けプロンプトを出す。実際に使う redirect_uri は
  毎回具体的な文字列で表示する（アプリのコールバックURL欄をその値に置き換えて保存してもらう
  必要があるため）。
- 事業所(company_id)はトークン取得後に `GET /api/1/companies` を1回叩き、1件なら自動選択、
  複数なら `prompts.select` で選ばせて config に保存する。
- 読み取りは `GET /api/1/deals?company_id=<id>&start_issue_date=<sinceの日付>&limit=100` の
  単発取得（ページングは1ページで打ち切り）。取引先/勘定科目は一覧応答が ID しか返さないため、
  名称が拾えるときだけ表示し、拾えないときは ID または摘要にフォールバックする（明細の全文は
  書き写さない。正本は freee のまま）。

## 付記: Slack の接続手順（実画面に合わせる）

`Create app from manifest` の 2 画面目は「空欄に貼る」ではなく **Demo App の雛形 JSON が入った
エディタ**で、既定タブは JSON。したがって guide は「全選択して置き換える」と明示し、マニフェストは
YAML ではなく **JSON** で提示する（タブ切り替えの手間を消す）。作成後は `Install to Workspace` →
`Allow` を踏まないとトークンが出ない。貼らせるのは **User OAuth Token（xoxp-）**——bot の xoxb- では
`search.messages` が使えない。案内文の各段は実 UI のボタン名をそのまま書くこと。
