---
description: いま言ったことをワタリの記憶に確実に残す
argument-hint: "<覚えてほしいこと>"
---
次の内容を記憶に残してください: $@

手順（この順で確実に。途中経過は表示しない）:
1. `watari recall` で既存の記憶を確認する（同じ話題があれば、その topic / domain / key に必ず寄せる。名前違いの新設はしない）。
2. 内容を SCHEMA.md の行仕様どおりの JSON 配列にして一時ファイルに書く（ts は現在時刻の UTC、source は "watari"。決めごと・事実は kind:"fact"、進行中の事柄は kind:"thread"、学習内容は kind:"study" で domain/topic/mastery/note を必ず入れる）。
3. `watari ingest --rows <一時ファイル>` で書き込む。検証エラー（exit 2）なら行を直して再実行する。
4. 成功したら「覚えました: <一言で内容>」と 1 行で報告する。失敗したままにしない。
