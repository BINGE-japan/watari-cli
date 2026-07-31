---
description: 記憶の整理を今すぐ実行する（前回の続きから会話と接続サービスを読み、役立つことだけ覚える）
---
記憶を整理してください。

SKILL の「記憶の整理」の手順をそのまま実行してください:
1. `watari_scan` で候補を得る（messages[] の role:"user" だけが記憶の根拠。assistant は文脈用）。
2. あとで役に立つものだけを SCHEMA の行仕様で JSON 配列にする（0 件なら []）。
3. `watari_ingest` の rows に配列を渡す。readable が true かつ max_ts が null でない分だけ advancePi / advanceCloud に時刻を渡す（条件を満たさない分は渡さない）。
4. `watari_connector_list` にある対応サービスも `watari_connector_read` で読み、同様に判定して advanceExt に `<name>=<最新ts>` を渡す（読めなかったサービスの分は渡さない）。
5. `watari_audit` で検査し、直せる指摘（まとめの食い違い等）は `watari_regen` で直す。
6. 終わったら 1 行で報告する（例: 「整理しました。新しく 3 件覚えました。」）。どこかの工程が失敗した場合は、成功したことにせず、失敗した工程を 1 行で伝える。
