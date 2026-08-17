# Google OAuth セットアップ（複数のパソコンで会話を同期するための準備）

**この設定は、複数のパソコンで同じワタリを使う場合だけ必要です。**
1 台で使う分には不要で、未設定でもワタリはそのまま動きます（同期だけがスキップされます）。

ワタリは複数のパソコンで使うとき、各パソコンの会話（あなたとワタリの発話テキスト）を
**Google Drive のアプリ専用領域**（あなたの Drive の画面には表示されず、このアプリだけが
読み書きできる場所）を通じて同期します。これを使うには、Google の OAuth アプリ
（インストール型）を一度だけ登録する必要があります。認可コードは PKCE S256（認可のたびに
作る一時的な鍵で横取りを防ぐ標準方式）で保護します。発行された client ID / client secret は
`watari auth` に入力すれば保存され、以後は各パソコンで `watari auth`（または
`watari install` の承認ステップ）でログインするだけです。

## 登録手順（一度だけ）

1. **Google Cloud Console**（<https://console.cloud.google.com/>）でプロジェクトを作成または選択する。
2. **APIs & Services → Library → 「Google Drive API」を有効化（Enable）** する。
3. **OAuth consent screen**（同意画面）を設定する:
   - User type: **External**（Google Workspace をお使いなら **Internal** を推奨。
     理由は後述「Gmail / Google カレンダー / Google ドライブを接続する場合」を参照）。
   - Scopes: **`.../auth/drive.appdata`** を追加する（アプリ専用領域のみ。あなたの Drive の
     他のファイルには触れません）。`watari connect gmail|calendar|gdrive` を使う予定が
     あれば、後述の表のスコープも同じ画面で追加する（未追加でも会話の同期は動きます。
     使う分だけ足せば十分です）。
   - **Publishing status: 「本番（In production）」に発行**する。
     ⚠ **Testing のままは不可** — テストモードではログイン状態が **7 日で切れます**
     （refresh token の失効）。本番なら切れません。
   - アプリは「未確認（unverified）」表示になりますが、個人で使う分には承認して進めば
     使えます（Gmail / Google ドライブを使うときだけ後述の制限に注意）。
4. **Credentials → Create credentials → OAuth client ID**:
   - Application type: **Desktop app**（インストール型）。
   - 発行された **client ID** と **client secret** を控える。
5. **`watari auth` を実行して、client ID / client secret を入力する**（対話式。環境変数
   `WATARI_GOOGLE_CLIENT_ID` / `WATARI_GOOGLE_CLIENT_SECRET` があればそちらを使います）。
   入力値は設定ファイルに保存され、以後は自動で使われます。POSIX環境では設定フォルダを
   本人専用（700）、設定ファイルを本人だけが読み書き可能（600）に固定します。ファイルを
   手で編集する必要はありません。

## 各パソコンでのログイン

各パソコンで **`watari auth`** を一度実行します（`watari install` の「Google Drive 経由で
同期しますか？」の質問でも同じ承認が走ります）。承認するとブラウザが開き、
Google ログイン → 許可 → 完了で、以後は無人で同期されます。ログインが切れたときも
`watari auth` をもう一度実行するだけです。保存済みのOAuth client自体がGoogle側で削除されている
場合は、`watari auth` が検出して有効なclient ID / client secretの入力へ切り替えます。別のパソコンで
ワタリのGoogle連携が動いているなら、そこで使っている同じOAuth clientを再利用でき、新規作成は不要です。
Refresh Tokenはコピーせず、各パソコンのブラウザ認証で個別に発行します。

- 既定の権限は `drive.appdata`（アプリ専用領域）のみです。**あなたの Drive の他のファイルには
  一切アクセスしません**（`watari connect gmail|calendar|gdrive` で個別に増やすまでは、
  これだけです）。
- 同期領域に置かれるのは、あなたとワタリの発話テキストだけです（ツールの出力や秘密は
  入れません）。読み終えた分は自動で削除され、最長 90 日で消えます。
- 未設定（client ID が空）の間は同期はスキップされ、ワタリは 1 台のパソコンで普通に動きます。

## Gmail / Google カレンダー / Google ドライブを接続する場合

`watari connect gmail`（同様に `calendar` / `gdrive`）は、上の同期用とは別のログインを
増やしません。同じ Google の承認に、そのサービスに必要な権限を 1 つずつ追加するだけです
（既存の権限は失われません）。承認は `watari auth` と同じ Google アカウントで行ってください。
必要スコープ:

| サービス | スコープ | Google 上の分類 |
| --- | --- | --- |
| gmail | `.../auth/gmail.readonly` | **制限付き（restricted）** |
| calendar | `.../auth/calendar.readonly` | 機密（sensitive） |
| gdrive | `.../auth/drive.metadata.readonly` | **制限付き（restricted）** |

⚠ **gmail / gdrive は「制限付きスコープ」** — 同意画面が **External** かつ
**未確認（unverified）** のままだと、Google の審査（有償・年次更新のセキュリティ評価）を
通さない限り実質使えません（同意画面でブロックされるか、Test user 登録した本人以外は
承認できません）。使うのが自分ひとりだけなら、次のどちらかを選んでください:

- **Google Workspace アカウントなら、同意画面の User Type を Internal に切り替える**
  （**推奨**）。審査不要で、ログインは切れず、対象はドメイン内のユーザーだけになります。
  個人利用の実態に一番合います。
- 個人の Gmail アカウント（Workspace でない）しかない場合は Internal を選べないため、
  External のまま **Testing** にして自分を Test user に登録して使います（この場合は
  前述のとおりログイン状態が 7 日で切れるため、`watari auth` や `watari connect gmail`
  などでの再承認が定期的に必要です）。`drive.appdata` と `calendar.readonly` だけを
  使うなら、そのまま本番発行でも動きます（機密（sensitive）スコープは未確認でも
  「詳細設定」から本人が承認を続行できます。gmail / gdrive の制限付きスコープだけが
  この回避策を使えません）。
