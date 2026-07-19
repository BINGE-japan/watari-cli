# Google OAuth セットアップ（発話中継所 = Drive appDataFolder）

watari-cli はマルチマシン同期のため、各マシンの会話（user＋assistant 発話）を **Google Drive の
appDataFolder** に中継する（ユーザーの Drive UI には出ない・アプリ専用・API で削除可）。これを使うには
Google の OAuth アプリ（インストール型）が1つ必要。**この登録は手動**で、`watari-cli` に client_id /
client_secret を同梱すれば、以後は各ユーザーが `watari install` の承認ステップでログインするだけ。

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
5. **watari-cli に入れる**（どちらか）:
   - 環境変数: `WATARI_GOOGLE_CLIENT_ID` / `WATARI_GOOGLE_CLIENT_SECRET` を設定する、または
   - `src/watari_cli/cloud.py` の `_CLIENT_ID` / `_CLIENT_SECRET` の既定値に埋めて同梱する
     （インストール型では client secret は機密ではない＝配布してよい）。

## 各マシンでのログイン

`watari install`（または未認証で再実行）すると、`client_id/secret` が設定済みなら承認するか聞かれる。
承認するとブラウザが開き、Google ログイン→許可→ローカルにリダイレクトされて **refresh token** が
`config.json` に保存される。以降は無人で access token を更新して Drive に読み書きする。

- スコープは `drive.appdata` のみ。**あなたの Drive の他のファイルには一切アクセスしない**。
- 中継所に置くのは user＋assistant の発話テキストだけ（tool 出力・秘密は入れない）。夢で消化した分は
  API で削除され、90 日を上限に自動で消える。
- 未設定（client_id 空）の間は同期はスキップされ、watari-cli はローカルのみで普通に動く。
