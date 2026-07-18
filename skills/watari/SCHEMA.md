# ワタリの記憶スキーマ

ジャンル別フォルダ（life / learning）。各ジャンルに `log.jsonl`（=正本・追記専用）と
`state.json`（=派生・log ＋再生成時刻 now から再生成）。取り込みカーソルは `memory/cursors.json` に一元化（ストア別に分割）。

ジャンルは kind で一意に決まる：`study` → learning、`fact` / `interest` / `thread` → life。
科目（english, web, math, tech-history, …）はジャンルではなく、learning の log 行が持つ `domain` フィールド（開集合・データ）。
（2026-06-10 に旧 english / web ジャンルを learning へ統合。経緯と理由は DESIGN.md 末尾。）

## 原則
- 書き込みは log.jsonl だけ（追記、消さない）。state.json は「log ＋ 再生成時刻 now」から再生成する純粋な派生物。
  → 書き手が複数（毎晩のルーティン／その場のワタリ）いても全員 log に足すだけ。state は決定的に再生成され競合しない。
- 決定性・冪等性：同じ log ＋ 同じ now を入力すれば、必ず同じ state が出る。state は「事実（log）」と「いつ再生成したか（now）」だけの関数。
- 取り込みは「前回処理した時刻（カーソル）以降の差分」だけ。冪等。
- 痕跡は log に混ぜない：log は事実の正本。対象0件など「走ったが事実は無い」記録は log に書かず、cursors.json の `last_run` に残す。
- 決定論部分（発話の選別・dedup・カーソル前進・state の畳み込み・監査）の正本実装は `skills/watari/scripts/`（extract.py / ingest.py / regen_state.py / audit.py。WSL の python3 で実行、Windows からは `wsl.exe -e python3 …`）。LLM の仕事は「何を記憶するか」の判定と summary/note/mastery/heat の中身だけで、機械処理を手でなぞらない。

## log.jsonl（1 行 = 1 事実。行き先のジャンルは kind で決まる）
```
{"ts":"<UTC ISO ...Z>","source":"transcript|slack|gmail|calendar|linear|obsidian|watari","kind":"fact|study|interest|thread",
 "domain":"<study行のみ・必須>","topic":"<study/interest/thread 行は必須>","summary":"<経緯・根拠。時系列可>",
 "mastery":1..3 (study必須),"heat":0..3 (interest任意),"note":"<state用・現在形1〜2文。study必須/interest・thread推奨>",
 "related":["domain/topic",...] (study任意),"freshness":"<ts>" (study任意・接触時刻の上書き),
 "profile":{"key":"...","value":"..."} (fact任意),"status":"closed" (thread任意),"deadline":"<UTC ISO ...Z>" (thread任意・未来なら age によらず active 固定),
 "tags":["..."],"refs":{"cwd":"...","session":"...","uuid":"..."}}
```
- **判定は行を書く時点で行い、行に記録する**：state はこれらの値を機械的に畳むだけで、内容の判断を後段でやり直さない（2026-07-02 スクリプト化。それ以前の行は旧仕様のままでよい——現在地は reconcile 快照行が持つ）。
- `domain`（learning 行のみ・必須）：小文字 ASCII ケバブケース・最も広い安定名。フレームワーク名や流行語は domain にしない（vue は domain ではなく web 内の topic）。追記前に learning/state.json の既存 domains キーを読み、収まるものには必ず寄せる。新設は既存のどれにも収まらない時のみ。
- `ts` は UTC（…Z）で保存。比較は必ず instant（時刻）として行い、JST と混ぜない。
- `refs.uuid` は元 transcript メッセージの uuid（dedup の鍵）。`refs.session` は session id。
- 記憶の根拠は原則 binge 本人（user 発話）。ワタリ(assistant)の発言は binge が採用/同意した事実の確認にのみ使う。
  サブエージェント(isSidechain)・ツール出力・メタ行は無視する。

## 本物の発話の選別（重要 — tool_result 誤取り込みの防止）
Claude Code の transcript では tool 実行結果も `type:"user"` で記録される。本物の binge 発話だけを取る条件は **すべて満たす行**に限定する：
- `type == "user"`
- `message.content` が**文字列**（text のみ。配列＝tool_result ブロックは除外）
- `toolUseResult` キーを**持たない**
そのうえで次は除外：`isMeta:true` / `isCompactSummary:true` / `type:"summary"` / `isSidechain:true` / スラッシュコマンド由来の合成 user 行 / `timestamp` の無い制御行。
- 時刻フィールド名は `timestamp`（UTC・…Z）。`ts` ではない（`ts` は log 側の名前）。

### Codex セッションの選別（第3の transcript ストア）
binge は Codex CLI 側からもワタリと話す（`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`）。Codex 形式は Claude Code と違い、
本物の binge 発話は **`type=="event_msg"` かつ `payload.type=="user_message"`** の行だけに現れる（発話本文は `payload.message`）。
AGENTS.md 注入・`<skill>` 注入・環境コンテキストは `response_item` 側に出るため、この条件で自然に除外される
（実装は watari_lib.is_genuine_codex_user_message / extract.scan_codex_store）。per-message uuid が無いため
dedup 鍵は合成 uuid `codex:<session_id>:<timestamp>`。時刻は同じく top-level `timestamp`（UTC …Z）。

## 学習の根拠は binge の発話痕跡（説明された≠学習した）
- topic・mastery として記録してよいのは、その話題が **binge 自身の発話に現れた**ものだけ。ワタリが説明しただけで binge の反応（質問・言い換え・続きの計算・相づち）が無い内容は、mastery を問わず記録しない。
- transcript には「ワタリが喋った全文」が残るが、それは「binge が読んで身につけた範囲」ではない。両者を取り違えない。
- **「ちょっと待って」＋言及**：binge が「ちょっと待って」等で直前メッセージの特定箇所に言及・引用したら、その言及箇所より後ろは binge 未読（ワタリがペースを超えた過剰説明の合図）。言及箇所以降のワタリの説明を学習の根拠にしない。

## dedup（live 追記と夜間の二重計上を防ぐ）
- ワタリがその場で log に足す行は `source:"watari"`、`refs` に `session` と元メッセージ `uuid` を残す。
- dedup の単位は（`refs.uuid`, `kind`）。同一発話から複数 kind（life の thread と fact、learning の study 等）を書くのは正当。
- 追記は必ず ingest.py 経由（検証・dedup・カーソル前進・state 再生成が一括で走る。同 (uuid, kind) は黙ってスキップされる）。
- 補填行（state からの還元・移行時の topic アンカー等）は合成 uuid `reconcile:<domain>/<slug>` を正当な dedup 鍵として使ってよい（元発話が特定できない場合は refs.session 省略可）。
- Obsidian vault 由来の行（`source:"obsidian"`）は合成 uuid `obsidian:<vault相対パス>@<処理対象更新日YYYY-MM-DD>` を dedup 鍵とする（更新日を含めるのは、後日加筆されたノートから新しい行を書けるようにするため。同一更新分の再処理は dedup される）。`refs.cwd` にノートの vault 相対パスを残す。
- Linear 由来の行（`source:"linear"`）は合成 uuid `linear:<issue識別子（例 ABC-123）>@<処理対象更新日YYYY-MM-DD>` を dedup 鍵とする（考え方は obsidian と同じ：issue が後日動いたら新しい行を書け、同一更新分の再処理は dedup される）。issue の中身は log に写さず、binge の活動・予定として効く要点だけを書く（中身の正本は Linear）。
- 同一プロジェクトが Windows / WSL の両ストアに二重に現れることがある。**近接 ts ＋ 同一 `refs.cwd` の同義行は1件に畳む**（先に拾った方を残す）。

## state.json（現在地・派生物。ジャンルの性質で形が違う）
### life（日常・興味・人物像 — 定着度の概念は無い）
```
{
  "updated": "<ts>",
  "profile": { "...安定した人物像・好み（変わりにくい）..." },
  "interests": { "<topic>": { "last": "<ts>", "heat": 0, "note": "..." } },
  "open_threads": [ { "topic": "...", "note": "...", "last": "<ts>", "deadline": "<ts>"(任意), "dormant": true(dormant 層のみ), "dormant_days": <int>(dormant 層のみ) } ]
}
```

### learning（学習 — 定着度・次が意味を持つ。domain 別にネスト）
```
{
  "updated": "<ts>",
  "domains": { "<domain>": { "topics": { "<topic>": { "mastery": 1, "freshness": "<ts>", "last": "<ts>", "note": "...", "related": ["<domain>/<topic>"] } } } }
}
```
- `freshness` は最終接触時刻（復習要否の判断に使う）。
- `related` の要素は常に `domain/topic` の修飾形式（同一 domain 内の参照も修飾する）。
- 部分参照してよい（話題の domain だけ読む）。肥大したら state を domain 別ファイルに分割できる（state は派生物なので log の移行は不要）。
- 別名修復：`learning/aliases.json`（任意・無ければ空とみなす）に `{"<誤domain>":"<正domain>"}` を置けば、再生成時に正規名へ写してから畳む。state = f(log, aliases, now) で決定性は保たれる。

## log → state の畳み込み仕様（決定論の核）
実装の正本は scripts/regen_state.py。log を ts 昇順（同時刻は refs.uuid 順）に畳み、再生成時刻 now を入力に取る。kind → state フィールドの写像と算出規則：

### kind → フィールド
- `interest` → life.interests
- `thread` → life.open_threads
- `fact` → `profile:{key,value}` を持つ行だけが life.profile に畳まれる（key ごと最新値が勝つ）。昇格の判断（複数回の再確認や本人の明示で載せる・単発の観察は載せない）は行を書く時点の責務。profile 無しの fact は log にのみ残る文脈。
- `study` → learning.domains[domain].topics（domain 欠落の learning 行は不正行として畳み込みからスキップする）
（痕跡・非事実は log に積まない。走ったが事実0件などの記録は cursors.json の `last_run` が受け皿。かつて `event` kind を痕跡用に置いたが、scripts は受け付けず全面廃止した。）

### life.interests の heat（量子化、0–3）
- `base_heat` = `heat` を持つ最新 interest 行の値（無ければ1）。出現頻度＋本人の熱量語（「ハマってる」「面白い」「やりたい」等）のスコア化は行を書く時点で行い、結果を `heat` に記録する。
- 減衰：`effective_heat = max(0, base_heat − floor((now − last) / 30日))`。
- `effective_heat == 0` になったら interests から落ちる（痕跡は log が持つ。state には残さない）。
- heat の意味：0 冷め / 1 関心 / 2 熱中 / 3 没頭。

### interest（life・熱）と study（learning・理解）の線引き
- 同一話題が life.interests（関心の熱）と learning（理解の到達点）の両方に存在してよい。
- ただし理解の中身（何をどこまで分かったか）は learning にのみ書く。life.interests の note は関心の痕跡に留める。
- study 行は heat に算入しない（学習中の話題への接触は learning の freshness が持つ）。

### life.open_threads（経過日数で3層。しきい値は watari_lib.py の DORMANT_DAYS=45 / SINK_DAYS=90）
- 開く条件：binge が「やりかけ・保留・気になっている」と示した進行中の事項（`kind:thread`）。
- `last` からの実経過日数 age（暦時間）で3層に分ける：
  - **active**（`age < DORMANT_DAYS`）：通常どおり open_threads に載る（印なし）。
  - **dormant**（`DORMANT_DAYS <= age < SINK_DAYS`）：**まだ open_threads に載る**が、その dict に `"dormant": true` と `"dormant_days": <age>` を付ける（＝「声かけ待ち」。ワタリが「最近どうなってる？」と確認するトリガ）。
  - **sunk**（`age >= SINK_DAYS`）：state から沈める（log には残り復元可能。従来の自動クローズと同じで、しきい値が後ろに延びただけ）。
- `status:"closed"` は age によらず即クローズ（従来どおり）。
- **deadline（項目ごとの寿命）**：thread 行に任意の `deadline`（UTC ISO …Z）を付けられる。畳み込みは最新の非 null 値を record に持ち越し、`deadline` が **now より未来**なら age によらず active 固定（dormant/sunk にしない）。active/dormant の出力 dict には `deadline` も載る。deadline が無ければ上の age 規則に従う。

### life.profile
- `profile:{key,value}` 行の key ごと最新値。恒常的と判断できるものだけ key を付けて書く（profile は変わりにくい人物像のみ。単発の観察には付けない）。

### learning の mastery（1–3、降格しない）
- `1` = 紹介され、binge 自身がその話題に発話で触れた（質問・言い換え・相づち・続きの操作など、読んで反応した痕跡がある）。ワタリが説明しただけ・binge が未読のものは記録しない（説明された≠学習した）。
- `2` = binge が**自分の言葉・成果物で再構成**した（user 発話に本人の英文・コード・自分の言葉での説明/言い換えが現れた）
- `3` = 時間を空けて（別セッションで）**再現・想起できた**
- mastery は行を書く時点で判定して行に記録し、state は最大値を取る（時間で下げない＝定着）。`freshness` は max(行の freshness または ts)、`note` は note を持つ最新行の値、`related` は全行の和集合（初出順）。復習要否は freshness で判断する。

## state は「地図＋初期姿勢」
常時 state を抱えはしないが、ワタリは呼ばれたら該当ジャンルの state を読み、最初の一文から反映する
（学習話題なら learning の該当 domain だけ読めば足りる。例：domain=english なら口語優先・「説明→本人が書く→レビュー」を一文目から）。詳細が要るときだけ log を読みに行く。
state の note/tags/related は log を引くための手がかり（地図）でもある。

## note の記述規約（現在形・絶対・簡潔 — log 行の note を書く時点で守る）
state は毎ターン読まれる hot path。性能（読む側のトークン効率と指示の鋭さ）のため、次を絶対ルールとする。
- **現在形・絶対形のみ**：profile / interests / open_threads / topics.note 等は「今効く指示・現在地」だけを断定で書く。
  **時系列叙述を禁止**——「以前は X だったが今は Y」「YYYY-MM-DD に〜事故→こう直した」式は書かない。
  経緯・理由・事件・日付つきの一回性の出来事は log.jsonl に置く（state.note は log を引く手がかり＝地図に徹する）。
- **希釈を避ける（二重持ちの禁止）**：CLAUDE.md が既に持つ普遍ルール（敬語・確認してから・非迎合・人物評の禁止 等）を state に再掲しない。
  state は CLAUDE.md にない binge 固有の差分だけを持つ。
- **簡潔**：note は原則1〜2文の指示。深さ・履歴・根拠は log を引く。
- **生成の含意**：state の note は log 行の `note` フィールドから機械的に写される（最新行優先）。
  だから現在形化は log 行の `note` を書く時点の責務。`summary` は経緯・根拠・時系列を持ってよい（log は正本、note は state 用の蒸留）。

## cursors.json（ストア別に分割）
```
{
  "transcripts_win": "<最後に処理した Windows store メッセージの UTC ts>",
  "transcripts_wsl": "<最後に処理した WSL store メッセージの UTC ts>",
  "transcripts_codex": "<最後に処理した Codex セッションの UTC ts>",
  "slack": "<ts>",
  "gmail": "<ts>",
  "calendar": "<ts>",
  "linear": "<最後に処理した issue の更新時刻（UTC ts）>",
  "obsidian": "<最後に処理した vault ノートの更新時刻（UTC ts）>",
  "last_run": "<このルーティンが最後に走った UTC ts>"
}
```
- transcript ストアは **Windows・WSL・Codex で別カーソル**（`transcripts_win` / `transcripts_wsl` / `transcripts_codex`）。各ストアを読めた分だけ、そのカーソルを前進。
- **読めない回（I/O error 等）はそのストアのカーソルを前進させずスキップ**（例：WSL 停止中に Win 側だけ前進して WSL 発話を永久取りこぼす事故を防ぐ。Codex も同じ扱い）。
- `null` は **−∞**（=全件が新しい）とみなす。
- 各カーソルは「**実際に処理した最後の `timestamp`**」に厳密に進める（未処理区間を飛び越えない）。
- `last_run` は痕跡用。log に非事実行を積まないための受け皿。
- カーソルの前進は ingest.py の `--advance-*` だけが行う（「実際に処理した最後の timestamp」を渡す。後退は拒否される）。
  transcript/obsidian は専用フラグ（`--advance-wsl/win/obsidian`）、外部ソース（slack/gmail/calendar/linear）は
  `--advance-ext <name>=<ts>`（対応キーの正本は watari_lib.py の EXT_STORES）。読めなかった・新着が無かったソースは渡さない（据え置き）。
- `obsidian` カーソルの対象は binge の Obsidian vault（`C:\Users\BINGE\Workspace\MyDocs`、WSL からは `/mnt/c/Users/BINGE/Workspace/MyDocs`。パス定数の正本は watari_lib.py の VAULT）。ノートは binge 本人の産出物なので、自分の言葉でまとめた内容は mastery 2 の根拠になり得る。知識の中身は log に写さず、到達状態とノートへのポインタ（refs.cwd）だけを書く（ノートの中身の正本は vault）。

## 1回の処理上限（初回・差分大の決定論化）
1回で処理する件数は次の**小さい方**で固定（実装は extract.py。変えるときは本ファイルと watari_lib.py の定数を揃える）：
- メッセージ **N = 300000 件**、または
- **最古の未処理メッセージ**から最大 **30 日ぶん**（1回の処理量の上限。毎日走る前提で超過分は truncated として次回に回す。窓の起点をカーソルでなく最古の未処理にするのは、カーソル以降に30日超の空白があっても取りこぼさない＝カーソルを永久停滞させないため）。
処理した最後の timestamp までカーソルを進め、残りは次回に回す。

## state 再生成と監査
`python3 scripts/regen_state.py` が log から state を作り直す（`--now` 指定で決定的・冪等。`--check` は書き込まず現 state と比較）。
`python3 scripts/audit.py` が形式・(uuid,kind) 重複・state と log の乖離・宙に浮いた related を検査する（`--coverage` で log に一度も現れないセッションの一覧も出す）。
同じ log ＋ 同じ now なら必ず同じ state（log が唯一の正本）。2026-07-02 に全 state 項目を reconcile 行として log へ快照済み。
