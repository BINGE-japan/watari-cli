---
description: 記憶の整理を今すぐ実行する（前回の続きから会話と接続サービスを読み、役立つことだけ覚える）
---
記憶を整理してください。

SKILL の「記憶の整理」の手順をそのまま実行してください:
1. `watari scan --json` で候補を得る（messages[] の role:"user" だけが記憶の根拠。assistant は文脈用）。
2. あとで役に立つものだけを SCHEMA の行仕様で JSON 配列にする（0 件なら []）。
3. `watari ingest --rows <file>` を実行する。readable が true かつ max_ts が null でないストアの分だけ `--advance-pi <ts>` / `--advance-cloud <machine>=<ts>` を付ける（条件を満たさないストアの分は付けない）。
4. `watari connector list` にあるサービスも `watari connector read <name> --json` で読み、同様に判定して `--advance-ext <name>=<最新ts>` を付ける（読めなかったサービスの分は付けない）。
5. `watari audit` で検査し、直せる指摘（まとめの食い違い等）は `watari regen` で直す。
6. 終わったら 1 行で報告する（例: 「整理しました。新しく 3 件覚えました。」）。どこかの工程が失敗した場合は、成功したことにせず、失敗した工程を 1 行で伝える。
