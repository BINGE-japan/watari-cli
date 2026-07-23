# 秘書・プランナー製品の機能調査（2026-07）

watari-cli の一般公開機能を決めるための調査。ベンダー自身の説明は「搭載機能」の根拠として扱い、
評価の根拠には独立した Product Hunt レビューを併記した。G2 / Capterra は bot challenge で本文を
取得できなかったため、取得できたふりをせず対象外とした。

## 観測した製品（地域を限定しない）

- **Motion** — タスクの優先順位・期限・所要時間から予定を組み直し、期限遅延リスクを事前警告。
  <https://www.usemotion.com/>
- **Reclaim** — habits、tasks、smart meetings、calendar sync、buffer time、planner、time tracking。
  <https://www.reclaim.ai/>
- **Sunsama** — タスクと会議を一日の現実的な計画に統合し、開始・終了の planning ritual を重視。
  Product Hunt は 4.7/5（21 reviews）で、daily planning、time blocking、focus、外部連携が反復して
 評価され、価格が主な不満。
  <https://www.sunsama.com/> / <https://www.producthunt.com/products/sunsama/reviews>
- **Akiflow（Italy）** — 複数ツールのタスクを universal inbox に集約し、カレンダーと一体で計画。
  Product Hunt は 4.6/5（18 reviews）で、quick capture、task/calendar integration、keyboard操作、
 速度が評価され、複雑さ・mobile・価格が不満。
  <https://akiflow.com/> / <https://www.producthunt.com/products/akiflow/reviews>
- **Morgen** — 複数カレンダーとタスクを統合し、未完了タスク・期限遅延リスク・予定変更を能動通知。
  レビューでは calendar integration、intuitive design、task management、meeting scheduling が反復。
  <https://www.morgen.so/> / <https://www.producthunt.com/products/morgen/reviews>
- **Shortwave** — 重要メール/to-do の抽出、AI filter、返信下書き、メール検索、予定作成。
  <https://www.shortwave.com/>
- **Lindy** — inbox triage、返信下書き、重要メール通知、会議調整、会議前brief、会議後action item、
  follow-up。承認を組み込めることも明示。
  <https://www.lindy.ai/>
- **Fyxer** — inbox organizer、返信下書き、meeting notes、scheduling。画面上で To Respond / FYI 等に
  分類する設計。
  <https://www.fyxer.com/>
- **Tiimo（Denmark）** — 視覚的な一日計画、focus timer、task breakdown、端末間同期。2025 App Store
  Awards の iPhone App of the Year を掲示。
  <https://www.tiimoapp.com/>

## 反復して評価・採用される機能

1. **情報源を一つの今日画面へ集約** — task + calendar + inbox。
2. **期限の直前ではなく、遅延リスクを先に知らせる**。
3. **未完了・未返信・重要メールを人が掘りに行く前に出す**。
4. **通知を大量に出さず、今日実行可能な量へ絞る**。
5. **自動変更より preview / approval / user control**。
6. **会議の前後を支援** — 事前brief、notes、action items、follow-up。
7. **高速なcaptureと低摩擦UI**。高機能化による複雑さと価格は一貫した不満。

## watari-cli への採用

- `watari brief`: 記憶・Gmail・Calendar・Linearの実状態を共通signalへ変換し、重要度順に3件だけ表示。
- 24時間cooldownと状態fingerprintで通知疲れを防ぐ。
- サービスは read-only。未返信は「返信が必要」と推測せず、最新が相手で以後の送信が無いという
  観測事実として出す。
- Pi起動時と起動中15分ごとに更新し、`/brief` で手動再確認。
- 質問回答は観測証拠を登録しない限り表示しない。確認不能ならfail closed。

## 次候補

1. 会議前brief（予定に関係するメール・記憶へのポインタだけを集約）
2. 一日のcapacityと期限から「遅れそう」を算出（自動で予定を書き換えず提案のみ）
3. メール返信下書き（必ずpreview、送信はユーザー承認後）
4. `/snooze` と重要送信者ルール

タスク・メール・カレンダーをwatari-cli自身の正本にせず、各サービスを正本のまま扱う。
