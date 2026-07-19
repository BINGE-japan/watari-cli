# 実装計画: マルチマシン同期（transcript クラウド化＋カセット git 同期層）

2026-07-19、binge とワタリ（別セッション）で確定した設計。**ここに書かれた決定は再議論しない**。
経緯の要点だけ末尾に付す。実装中に矛盾を見つけたら、代替案を並べず一点だけ binge に確認する。

## 確定した全体像

```
[各マシン] watari chat（Pi の親プロセス）
   ├─ ローカル Pi transcript（生・使い捨て・従来通り）
   └─ chat 内の監視スレッドが差分を抽出
        → Google Drive appDataFolder へ追記（マシン別ファイル）      … 素材の中継所
[任意のマシン] 夢（chat 起動時に裏で自動実行）
   └─ appDataFolder の全マシン分＋コネクト済みツールを1つの dream カーソルで消費
        → カセット git の log へ蒸留（従来通り）→ state 再生成
```

- カセット git は「蒸留済みの記憶」専用に保つ。**生 transcript は git に入れない**
  （git は履歴から blob を消せず、削除 commit しても容量が一方通行で増えるため。実験検証済み）。
- クラウド置き場は消せる・機械可読・無人で読める。人間可読性は不要。

## 決定事項（変更不可）

1. **置き場 = Google Drive appDataFolder**。マシンごとに `transcripts/<machine-id>.jsonl`。
   ユーザーの Drive UI には見えない。TTL: dream カーソルより古い分は夢の後に API 削除（上限 90 日の保険付き）。
2. **中身 = user 発話＋assistant 本文**。tool 出力・thinking は入れない
   （夢の判定は「文脈が要る発話は前後の assistant 発話を確認してよい」ため assistant 本文が必要）。
   行形式: `{ts, turn_id, machine, cwd, role: "user"|"assistant", text}` の JSONL。
3. **書き込み主体 = watari chat のラッパー（Python）**。LLM には一切やらせない。
   - chat は Pi の親プロセス。監視スレッドがローカル session ファイルをバイトオフセットで tail する。
   - 発火はファイル更新イベント（watchdog/inotify）＋数秒デバウンス＝実質ターン終了時送信。
     イベントが使えない環境は数十秒ポーリングにフォールバック。
   - 終了時（SIGTERM/SIGINT 含む）に最終 flush。送信失敗はローカルキューに繰り越し、次の flush か次回 chat で再送。
4. **認証 = Google OAuth（インストール型アプリフロー）**。install wizard に承認ステップを追加。
   クライアント ID は watari-cli 同梱。リフレッシュトークンはユーザー設定に保存。
   OAuth アプリ（Cloud プロジェクト）の登録は binge が手動で行う——手順書を `docs/google-oauth-setup.md` に書くこと。
   公開ステータスは「本番・未確認」（テストモードは 7 日でトークン失効するため不可）。
5. **カセット git 同期層**: 読む前（chat/dream/recall の頭）に `commit(未追記があれば)→pull`、
   書いた後（ingest）に `commit→pull→push`。offline は commit のみで繰り越し。log は union-merge、state は派生（gitignore 維持）。
   install wizard に「remote を設定する／ローカルのみ（同期・バックアップ無しと警告）」の選択を追加。
6. **夢**: 共有ストリーム全マシン分＋ローカル Pi store を、カセット内の単一 dream カーソルで消費。
   マシン別の抽出カーソルは host record に置く。**chat 起動時に裏で自動実行**（起動をブロックしない）。
   ユーザー PC の夜間自動実行は前提にしない（デスクトップ側ルーティンは実際ほぼ動いていなかった）。
7. **やらないこと**: 生 transcript の git 保存／夜間 cron 前提の設計／exe.dev 依存（Hermes 専用に保つ）／
   モデルへの毎ターン事務作業の指示。「カセット」「ゲーム機」の語をコード・UX に出さない（従来通り）。

## 実装順（各ステップでテストを通してから次へ）

1. **同期層（git）**: 5 の pull/push を chat/dream/recall/ingest に組み込む。install wizard の remote 選択。
2. **クラウド置き場アダプタ**: appDataFolder への append/list/read/delete。OAuth フロー＋トークン保存。
   置き場はインターフェースを切って appDataFolder を第一実装とする（将来の別バックエンドの余地。ただし今は作らない）。
3. **chat ラッパーの抽出スレッド**: tail→フィルタ→追記。デバウンス・フォールバック・終了 flush・再送キュー。
4. **夢の読み口**: 共有ストリームを dream の source に追加（カーソル規律は既存ストア群と同じ:
   読めなかったマシン分は据え置き）。消化済み分のクラウド削除。
5. **chat 起動時の裏 dream**: 非ブロッキング起動。二重起動ガード。
6. **SPEC.md 更新**（この設計を反映。同一変更内で）と README の該当箇所。

## 受け入れ条件

- マシン A で会話 → A のクラウドファイルに数秒〜数十秒で発話が現れる（chat は止めない・遅くしない）。
- A の会話を B の `watari dream` が読み、log に蒸留される（A に触らずに）。
- ネット断で chat しても壊れず、復帰後の flush で追いつく。
- 生 transcript・トークン類がカセット git の履歴に一切入らない。
- 全テスト green。オリジナルワタリ（~/.claude/skills/watari）には触れない。

## 経緯（参考・1 段落）

git に生を置く案は「削除 commit しても履歴の blob が残り容量が単調増加する」ため棄却（10MB 実験で確認）。
exe.dev VM 案は「ワタリが手元 PC を見られない」ため棄却、VM は Hermes 専用に保つ。
user 発話のみの同期案は「assistant 文脈が無いと蒸留できない」ため assistant 本文込みに拡張。
ターン終了フック・セッション終了フック・起動時一括抽出はいずれも取りこぼすため、
「chat が Pi の親プロセスである」ことを利用した会話中の逐次抽出に確定した。
