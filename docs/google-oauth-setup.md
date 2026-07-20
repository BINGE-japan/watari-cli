# Google OAuth セットアップ（発話中継所 = Drive appDataFolder）

watari-cli はマルチマシン同期のため、各マシンの会話（user＋assistant 発話）を **Google Drive の
appDataFolder** に中継する（ユーザーの Drive UI には出ない・アプリ専用・API で削除可）。これを使うには
Google の OAuth アプリ（インストール型）が1つ必要。**この登録は手動**（下記）。発行した client_id /
client_secret は `watari auth` に渡せば `config.json` に保存され、以後は各マシンで `watari auth`
（または `watari install` の承認ステップ）でログインするだけ。

## 登録手順（一度だけ・binge が実施）

1. **Google Cloud Console**（<https://console.cloud.google.com/>）でプロジェクトを作成/選択。
2. **APIs & Services → Library → 「Google Drive API」を Enable**。
3. **OAuth consent screen**:
   - User type: **External**（Google Workspace なら **Internal** を推奨。理由は下記「組み込み
     コネクタ（gmail/calendar/gdrive）を使う場合」を参照）。
   - Scopes: **`.../auth/drive.appdata`** を追加（アプリ専用フォルダのみ。Drive 全体は触らない）。
     `watari connect gmail|calendar|gdrive` を使うなら、それぞれ下記のスコープも同じ画面で
     追加する（未追加でも `drive.appdata` だけで発話中継所は動く。使う分だけ足せばよい）:
     - Gmail: `.../auth/gmail.readonly`
     - Google カレンダー: `.../auth/calendar.readonly`
     - Google ドライブ（メタデータのみ）: `.../auth/drive.metadata.readonly`
   - **Publishing status: 「本番（In production）」に発行**する。
     ⚠ **Testing のままは不可**——テストモードの refresh token は **7 日で失効**する。本番なら失効しない。
   - アプリは「未確認（unverified）」表示になるが、個人利用/少人数なら承認して進めば使える
     （ただし gmail/drive を使うときは次項の制限に注意）。
4. **Credentials → Create credentials → OAuth client ID**:
   - Application type: **Desktop app**（インストール型。loopback リダイレクトを使う）。
   - 発行された **client ID** と **client secret** を控える。
5. **watari-cli に渡す**：`watari auth` を実行し、client ID / client secret を入力する（対話。
   環境変数 `WATARI_GOOGLE_CLIENT_ID` / `WATARI_GOOGLE_CLIENT_SECRET` があればそれを採用）。入力値は
   `~/.config/watari/config.json` の `google` セクションに保存され、以後は無人で使われる。手で埋める
   必要はない。**全ユーザーに配布**したいときだけ `src/watari_cli/cloud.py` の `_BUNDLED_CLIENT_ID` /
   `_BUNDLED_CLIENT_SECRET` に焼き込む（インストール型では client secret は機密でない＝配布可）。

## 各マシンでのログイン

各マシンで **`watari auth`** を一度実行する（`watari install` の「Google Drive と同期しますか？」でも
同じ承認が走る）。client_id/secret が未保存なら初回だけ入力を求め、以後は保存値を使う。承認すると
ブラウザが開き、Google ログイン→許可→ローカルにリダイレクトされて **refresh token** が `config.json`
に保存される。以降は無人で access token を更新して Drive に読み書きする（token 失効時も `watari auth`
で再ログインするだけ）。

- 既定のスコープは `drive.appdata` のみ。**あなたの Drive の他のファイルには一切アクセスしない**
  （`watari connect gmail|calendar|gdrive` で個別に増やすまでは、これだけ）。
- 中継所に置くのは user＋assistant の発話テキストだけ（tool 出力・秘密は入れない）。夢で消化した分は
  API で削除され、90 日を上限に自動で消える。
- 未設定（client_id 空）の間は同期はスキップされ、watari-cli はローカルのみで普通に動く。

## 組み込みコネクタ（gmail / calendar / gdrive）を使う場合

`watari connect gmail`（同様に `calendar` / `gdrive`）は、上の発話中継所とは**別トークンを発行
せず**、同じ Google 認可を **incremental scope**（`include_granted_scopes=true`）で拡張する。
未接続のサービスに繋ぐたびに、そのサービスに要る1スコープだけを追加でブラウザ承認すればよい
（`drive.appdata` を含む既存の権限は失われない）。必要スコープ:

| コネクタ | スコープ | 分類 |
| --- | --- | --- |
| gmail | `.../auth/gmail.readonly` | **制限付き（restricted）** |
| calendar | `.../auth/calendar.readonly` | 機密（sensitive） |
| gdrive | `.../auth/drive.metadata.readonly` | **制限付き（restricted）** |

⚠ **gmail / gdrive は「制限付きスコープ」**——OAuth consent screen が **External** かつ
**未確認（unverified）** のままだと、Google の審査（CASA によるセキュリティ評価。有償・年次更新）を
通さない限り実質使えない（同意画面で明示的にブロックされるか、テストユーザー登録した本人以外は
承認できない）。個人の binge しか使わないなら、次のどちらかを選ぶ:

- **Google Workspace アカウントなら、consent screen の User Type を Internal に切り替える**
  （**推奨**）。審査不要・トークンは失効せず・ドメイン内のユーザーだけが対象になる。個人利用の
  実態に一番合う。
- 個人の Gmail アカウント（Workspace でない）しかない場合は Internal を選べないため、External の
  まま **Testing** で自分を Test user に登録して使う（この場合は前述のとおり refresh token が
  7 日で失効するため、`watari auth` / `watari connect gmail` 等での再承認が定期的に要る）。
  `drive.appdata`・`calendar.readonly` だけを使うなら、そのまま Production 発行でも動く
  （sensitive scope は unverified でも「詳細設定」から本人が承認を続行できる。gmail/drive の
  restricted scope だけがこの回避策を塞がれている）。
