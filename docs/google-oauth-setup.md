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
   - User type: **External**。
   - Scopes: **`.../auth/drive.appdata`** だけを追加（アプリ専用フォルダのみ。Drive 全体は触らない）。
   - **Publishing status: 「本番（In production）」に発行**する。
     ⚠ **Testing のままは不可**——テストモードの refresh token は **7 日で失効**する。本番なら失効しない。
   - アプリは「未確認（unverified）」表示になるが、個人利用/少人数なら承認して進めば使える。
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

- スコープは `drive.appdata` のみ。**あなたの Drive の他のファイルには一切アクセスしない**。
- 中継所に置くのは user＋assistant の発話テキストだけ（tool 出力・秘密は入れない）。夢で消化した分は
  API で削除され、90 日を上限に自動で消える。
- 未設定（client_id 空）の間は同期はスキップされ、watari-cli はローカルのみで普通に動く。
