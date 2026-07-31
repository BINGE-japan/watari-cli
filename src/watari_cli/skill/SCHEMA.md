# ワタリの記憶スキーマ

ジャンル別フォルダ（life / learning）。各ジャンルに `log.jsonl`（=正本・追記専用）と
`state.json`（=派生・log ＋再生成時刻 now から再生成）。取り込みカーソルは**マシンごとの host 記録**（`memory/hosts/<machine-id>.json` の `cursors`）にストア別に持つ（記憶は git で全マシン共有されるため）。

ジャンルは kind で一意に決まる：`study` → learning、`fact` / `interest` / `thread` → life。
科目（english, web, math, tech-history, …）はジャンルではなく、learning の log 行が持つ `domain` フィールド（開集合・データ）。

## 原則
- 書き込みは log.jsonl だけ（追記、消さない）。state.json は「log ＋ 再生成時刻 now」から再生成する純粋な派生物。
  → 書き手が複数（定期的な記憶の整理／その場のワタリ）いても全員 log に足すだけ。state は決定的に再生成され競合しない。
- 決定性・冪等性：同じ log ＋ 同じ now を入力すれば、必ず同じ state が出る。state は「事実（log）」と「いつ再生成したか（now）」だけの関数。
- 取り込みは「前回処理した時刻（カーソル）以降の差分」だけ。冪等。
- 痕跡は log に混ぜない：log は事実の正本。対象0件など「走ったが事実は無い」記録は log に書かず、カーソルの `last_run`（host 記録内）に残す。
- 決定論部分（発話の選別・dedup・カーソル前進・state の畳み込み・監査）は同梱エンジンが実装し、`watari` CLI（`watari scan` / `watari ingest` / `watari regen` / `watari audit`）が担う。LLM の仕事は「何を記憶するか」の判定と summary/note/mastery/heat の中身だけで、機械処理を手でなぞらない。

## log.jsonl（1 行 = 1 事実。行き先のジャンルは kind で決まる）
```
{"ts":"<UTC ISO ...Z>","source":"transcript|watari|<接続サービス名>","kind":"fact|study|interest|thread",
 "domain":"<study行のみ・必須>","topic":"<study/interest/thread 行は必須>","summary":"<経緯・根拠。時系列可>",
 "mastery":1..3 (study必須),"heat":0..3 (interest任意),"note":"<state用・現在形1〜2文。study必須/interest・thread推奨>",
 "related":["domain/topic",...] (study任意),"freshness":"<ts>" (study任意・接触時刻の上書き),
 "profile":{"key":"...","value":"...","mode":"always|relevant"} (fact任意。旧行はmode省略可),"status":"closed" (thread任意),"deadline":"<UTC ISO ...Z>" (thread任意・未来なら age によらず active 固定),
 "tags":["..."],"refs":{"cwd":"...","session":"...","uuid":"..."}}
```
- **判定は行を書く時点で行い、行に記録する**：state はこれらの値を機械的に畳むだけで、内容の判断を後段でやり直さない。
- `source` は**開集合**（接続サービス名等の小文字スラッグ）。組み込みは `transcript`（Pi の会話由来）と `watari`（ワタリがその場で足す行）。接続サービス由来の行は、宣言した connector の name をそのまま source に使う（例: transcript, slack, gmail, obsidian, linear, claude-code, watari, ...）。
- `domain`（learning 行のみ・必須）：小文字 ASCII ケバブケース・最も広い安定名。フレームワーク名や流行語は domain にしない（vue は domain ではなく web 内の topic）。追記前に learning/state.json の既存 domains キーを読み、収まるものには必ず寄せる。新設は既存のどれにも収まらない時のみ（その回の `watari ingest` にだけ `--allow-new-domain` を付けて通す）。
- `ts` は UTC（…Z）で保存。比較は必ず instant（時刻）として行い、JST と混ぜない。
- `profile.mode`：`always`＝どの話題でも毎回効く人物像・応答の好み、`relevant`＝職歴・事業・ツール・個別運用など話題に応じて検索すればよい事実。新しい profile 行は必ずどちらかを明示する。mode が無い旧行だけは互換性のため `always` とみなす。
- `refs.uuid` は元 transcript メッセージの uuid（dedup の鍵）。`refs.session` は session id。
- 記憶の根拠は原則ユーザー本人（user 発話）。ワタリ(assistant)の発言はユーザーが採用/同意した事実の確認にのみ使う。
  サブエージェント(isSidechain)・ツール出力・メタ行は無視する。

## 本物の発話の選別（Pi セッション）
watari chat の runtime は Pi。Pi のセッションは `~/.pi/agent/sessions/<作業ディレクトリ>/*.jsonl`（JSONL）で、
先頭行が `{"type":"session","id":<session uuid>,"cwd":<作業ディレクトリ>}` のヘッダ。本物のユーザー発話だけを取る
条件（**すべて満たす行**）：
- `type == "message"`
- `message.role == "user"`
- `timestamp` を持つ（UTC・…Z。`ts` ではない＝`ts` は log 側の名前）

tool 結果は `role:"toolResult"`、bash 実行や注入は別 type（`bashExecution` / `custom` / `custom_message` / `label` 等）に
出るため、role だけで自然に選別できる（Claude Code のような `type:"user"` への tool 結果混入が無く、判定は単純）。
`message.content` は文字列でも、テキスト/画像ブロックの配列でもよい（判定側がそのまま読む）。session id と cwd は
ヘッダ行から取り、各行の安定 `id`（8桁hex）を使って dedup 鍵は合成 uuid `pi:<session_id>:<id>`（id が無い版では
`pi:<session_id>:<timestamp>`）。この選別は同梱エンジンが実装する（`watari scan` が適用済みの結果を返す）。

## 学習の根拠はユーザーの発話痕跡（説明された≠学習した）
- topic・mastery として記録してよいのは、その話題が **ユーザー自身の発話に現れた**ものだけ。ワタリが説明しただけでユーザーの反応（質問・言い換え・続きの計算・相づち）が無い内容は、mastery を問わず記録しない。
- transcript には「ワタリが喋った全文」が残るが、それは「ユーザーが読んで身につけた範囲」ではない。両者を取り違えない。
- **「ちょっと待って」＋言及**：ユーザーが「ちょっと待って」等で直前メッセージの特定箇所に言及・引用したら、その言及箇所より後ろはユーザー未読（ワタリがペースを超えた過剰説明の合図）。言及箇所以降のワタリの説明を学習の根拠にしない。

## dedup（live 追記と夜間の二重計上を防ぐ）
- ワタリがその場で log に足す行は `source:"watari"`、`refs` に `session` と元メッセージ `uuid` を残す。
- dedup の単位は（`refs.uuid`, `kind`）。同一発話から複数 kind（life の thread と fact、learning の study 等）を書くのは正当。
- 追記は必ず `watari ingest` 経由（検証・dedup・カーソル前進・state 再生成が一括で走る。同 (uuid, kind) は黙ってスキップされる）。
- 補填行（state からの還元・移行時の topic アンカー等）は合成 uuid `reconcile:<domain>/<slug>` を正当な dedup 鍵として使ってよい（元発話が特定できない場合は refs.session 省略可）。
- Obsidian vault 由来の行（`source:"obsidian"`）は合成 uuid `obsidian:<vault相対パス>@<処理対象更新日YYYY-MM-DD>` を dedup 鍵とする（更新日を含めるのは、後日加筆されたノートから新しい行を書けるようにするため。同一更新分の再処理は dedup される）。`refs.cwd` にノートの vault 相対パスを残す。
- Linear 由来の行（`source:"linear"`）は合成 uuid `linear:<issue識別子（例 ABC-123）>@<処理対象更新日YYYY-MM-DD>` を dedup 鍵とする（考え方は obsidian と同じ：issue が後日動いたら新しい行を書け、同一更新分の再処理は dedup される）。issue の中身は log に写さず、ユーザーの活動・予定として効く要点だけを書く（中身の正本は Linear）。
- 同一発話が複数ソース（Pi transcript と connector 等）に二重に現れることがある。**近接 ts ＋ 同一 `refs.cwd` の同義行は1件に畳む**（先に拾った方を残す）。

## state.json（現在地・派生物。ジャンルの性質で形が違う）
### life（日常・興味・人物像 — 定着度の概念は無い）
```
{
  "updated": "<ts>",
  "profile": { "...毎回の応答に効く人物像・好み..." },
  "facts": { "<key>": { "last": "<ts>", "note": "...", "tags": ["..."](任意) } },
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
実装の正本は `watari regen`（同梱エンジン）。log を ts 昇順（同時刻は refs.uuid 順）に畳み、再生成時刻 now を入力に取る。kind → state フィールドの写像と算出規則：

### kind → フィールド
- `interest` → life.interests
- `thread` → life.open_threads
- `fact` → `profile:{key,value,mode}` を持つ行は key ごと最新値が勝つ。mode=`always` は life.profile、mode=`relevant` は life.facts に畳まれる。昇格と mode の判断（毎回答に必要か、話題に応じて検索すればよいか）は行を書く時点の責務。profile 無しの fact は log にのみ残る文脈。
- `study` → learning.domains[domain].topics（domain 欠落の learning 行は不正行として畳み込みからスキップする）
（痕跡・非事実は log に積まない。走ったが事実0件などの記録はカーソルの `last_run`（host 記録内）が受け皿。kind は fact / study / interest / thread の4種のみ。）

### life.interests の heat（量子化、0–3）
- `base_heat` = `heat` を持つ最新 interest 行の値（無ければ1）。出現頻度＋本人の熱量語（「ハマってる」「面白い」「やりたい」等）のスコア化は行を書く時点で行い、結果を `heat` に記録する。
- 減衰：`effective_heat = max(0, base_heat − floor((now − last) / 30日))`。
- `effective_heat == 0` になったら interests から落ちる（痕跡は log が持つ。state には残さない）。
- heat の意味：0 冷め / 1 関心 / 2 熱中 / 3 没頭。

### interest（life・熱）と study（learning・理解）の線引き
- 同一話題が life.interests（関心の熱）と learning（理解の到達点）の両方に存在してよい。
- ただし理解の中身（何をどこまで分かったか）は learning にのみ書く。life.interests の note は関心の痕跡に留める。
- study 行は heat に算入しない（学習中の話題への接触は learning の freshness が持つ）。

### life.open_threads（経過日数で3層。しきい値は DORMANT_DAYS=45 / SINK_DAYS=90——同梱エンジンの定数）
- 開く条件：ユーザーが「やりかけ・保留・気になっている」と示した進行中の事項（`kind:thread`）。
- `last` からの実経過日数 age（暦時間）で3層に分ける：
  - **active**（`age < DORMANT_DAYS`）：通常どおり open_threads に載る（印なし）。
  - **dormant**（`DORMANT_DAYS <= age < SINK_DAYS`）：**まだ open_threads に載る**が、その dict に `"dormant": true` と `"dormant_days": <age>` を付ける（＝「声かけ待ち」。ワタリが「こちらは最近いかがですか？」と確認するトリガ。発話例の正本は SKILL.md）。
  - **sunk**（`age >= SINK_DAYS`）：state から沈める（log には残り復元可能。従来の自動クローズと同じで、しきい値が後ろに延びただけ）。
- `status:"closed"` は age によらず即クローズ（従来どおり）。
- **deadline（項目ごとの寿命）**：thread 行に任意の `deadline`（UTC ISO …Z）を付けられる。畳み込みは最新の非 null 値を record に持ち越し、`deadline` が **now より未来**なら age によらず active 固定（dormant/sunk にしない）。active/dormant の出力 dict には `deadline` も載る。deadline が無ければ上の age 規則に従う。

### life.profile / life.facts
- `profile:{key,value,mode}` 行の key ごと最新値。mode=`always` は life.profile、mode=`relevant` は life.facts。同じ key の新しい行で mode を変えれば、履歴を残したまま両者を移動できる。
- `always` は「変わりにくい」だけでは足りず、**どの話題でも毎回の回答へ効く**ことが条件。応答形式、確認境界、呼び方などに限定し、合計 5KB 以内を保つ。監査は超過を問題として報告する。
- 職歴、会社・事業、使用ツール、個別プロジェクト、特定サービスの運用は、安定事実でも原則 `relevant`。単発の観察には profile 自体を付けない。

### learning の mastery（1–3、降格しない）
- `1` = 紹介され、ユーザー自身がその話題に発話で触れた（質問・言い換え・相づち・続きの操作など、読んで反応した痕跡がある）。ワタリが説明しただけ・ユーザーが未読のものは記録しない（説明された≠学習した）。
- `2` = ユーザーが**自分の言葉・成果物で再構成**した（user 発話に本人の英文・コード・自分の言葉での説明/言い換えが現れた）
- `3` = 時間を空けて（別セッションで）**再現・想起できた**
- mastery は行を書く時点で判定して行に記録し、state は最大値を取る（時間で下げない＝定着）。`freshness` は max(行の freshness または ts)、`note` は note を持つ最新行の値、`related` は全行の和集合（初出順）。復習要否は freshness で判断する。

## state は「地図＋初期姿勢」
`watari chat` の Pi extension は**各ユーザー入力の直後・モデル呼び出し前**に life/learning state を
ローカルで読み、選択中の性能モードに応じて system prompt へ一時注入する（session transcript には保存しない）：
- **fast（爆速）**：常時 profile、優先 open_threads 最大1件、関連項目最大3件。catalog無し、全体4KB。
- **balanced（標準・既定）**：常時 profile（最大5KB）、優先 open_threads 最大3件、関連項目最大6件、profile/facts/thread/interest/study の題名catalog。全体16KB。各区画に容量を先に確保し、profile の肥大で attention・matches・catalog が丸ごと消えないようにする。容量超過時は各区画内で縮め、profile を省略した場合もcatalogにkeyを残す。
- **butler（スーパー執事）**：life/learning state 全体。上限を設けず現在の記憶全体を渡す。

検索はファイル読み取り＋決定的な文字列照合だけで、モデル・ネットワーク・外部サービスを呼ばない。題名・タグ・固有語を優先し、一般的な否定語など短い断片の一致だけでは関連項目に採用しない。
fast/balanced は全 state を会話へ積み続けず、入力ごとに現在の関連 domain/topic を最初の一文から反映する。
balanced の catalog に候補があるのに関連項目へ詳細が出ず、回答がその詳細に依存するときだけ log を読みに行く。
state の note/related は検索と log を引くための手がかり（地図）でもある。

## note の記述規約（現在形・絶対・簡潔 — log 行の note を書く時点で守る）
state は毎ターン読まれる hot path。性能（読む側のトークン効率と指示の鋭さ）のため、次を絶対ルールとする。
- **現在形・絶対形のみ**：profile / facts / interests / open_threads / topics.note 等は「今効く指示・現在地」だけを断定で書く。
  **時系列叙述を禁止**——「以前は X だったが今は Y」「YYYY-MM-DD に〜事故→こう直した」式は書かない。
  経緯・理由・事件・日付つきの一回性の出来事は log.jsonl に置く（state.note は log を引く手がかり＝地図に徹する）。
- **希釈を避ける（二重持ちの禁止）**：SKILL.md が既に持つ普遍ルール（人格セクションの敬語・確認してから・一元管理 等）を state に再掲しない。
  state は SKILL.md にないユーザー固有の差分だけを持つ。
- **簡潔**：note は原則1〜2文の指示。深さ・履歴・根拠は log を引く。
- **生成の含意**：state の note は log 行の `note` フィールドから機械的に写される（最新行優先）。
  だから現在形化は log 行の `note` を書く時点の責務。`summary` は経緯・根拠・時系列を持ってよい（log は正本、note は state 用の蒸留）。

## カーソル（マシンごとの host 記録に格納・ストア別）
記憶（WATARI_HOME）は git で全マシンに同期される。単一の共有 `cursors.json` だと、複数マシンが各々
カーソルを進めたとき衝突する。そこでカーソルは**マシンごとの host 記録**（`hosts/<machine-id>.json` の
`cursors`）に持つ——各マシンは自分のファイルだけを書くので衝突せず、git で
相互に読める。キーとストア別の意味：
```
{
  "transcripts_pi": "<最後に処理した Pi セッションメッセージの UTC ts。--advance-pi で前進>",
  "cloud_<machine-id>": "<そのマシンから同期された発話ストリームを最後に処理した UTC ts。--advance-cloud <machine>=<ts> で前進（読めた cloud ストアごとに動的に追加される）>",
  "last_run": "<記憶の整理が最後に走った UTC ts>",
  "<connector名>": "<宣言した connector ごとに --advance-ext で動的に追加されるカーソル（例 obsidian ならノート更新時刻、linear なら issue の更新時刻、gmail なら受信時刻 等。意味は各 connector の read 指示が決める）>"
}
```
- 組み込み transcript は **Pi 一本**（`transcripts_pi`）。watari chat の runtime が Pi なので、ワタリと話した内容はすべて Pi のセッションに残る。複数マシンで使う場合は、他マシンの発話が同期されて `cloud_<machine-id>` ストアとして届く（`watari scan --json` の `stores.cloud_<machine>`。1台だけの運用ならストアは pi のみ）。他の AI CLI・ツールは connector として宣言する（下の「connector」節）。
- **読めない回（I/O error 等）はカーソルを前進させずスキップ**（読めた分だけ前進。一時的な I/O 断で未読区間を飛び越えて取りこぼす事故を防ぐ）。
- `null` は **−∞**（=全件が新しい）とみなす。
- 各カーソルは「**実際に処理した最後の `timestamp`**」に厳密に進める（未処理区間を飛び越えない）。
- `last_run` は痕跡用。log に非事実行を積まないための受け皿。
- カーソルの前進は `watari ingest` の advance フラグだけが行う（「実際に処理した最後の timestamp」を渡す。後退は拒否される）。
  組み込み transcript(Pi) は専用フラグ `--advance-pi <ts>`、他マシンの発話ストリームは `--advance-cloud <machine>=<ts>`
  （読めた cloud ストアごとに 1 つ）、外部ソース(connector)は
  `--advance-ext <name>=<ts>`。**--advance-ext の許可名は固定リストではなく、ユーザーが宣言した connector 名**（config の `connectors`。下の
  「connector」節。obsidian 等もここで宣言して渡す）。未宣言の名前はエラー。いずれのフラグも、`readable` が false・`max_ts` が null・
  読めなかった・新着が無かったストアの分は渡さない（据え置き＝取りこぼし防止）。connector のカーソルは
  他のキーと同じくマシンごとの host 記録に載る（host 記録の cursors は任意キーを許すので、宣言名がそのままキーになる）。
- 旧 `cursors.json` からの移行：旧 `<home>/cursors.json` があれば、読み取り（status / scan / ingest）は
  その位置を**メモリ上で**引き継ぐ。host 記録への永続化は実際に前進が起きたときに
  一度だけ行い、読み取り専用パスは何も書かない（既存のカーソル位置は次の前進が丸ごと書き戻すので失われない）。
  旧 `cursors.json` が存在する環境では読み取り互換のため残してよい（本仕様の正本は host 記録側）。
- **cloud スコープの connector（メール等）の扱い**：カーソルは他と同じくマシンごとの host 記録に置くが、cloud 源は本来
  どのマシンから取り込んでも同じ位置であるべき（マシン間で共有すべき性質）。多重取り込みを避けるため、**cloud connector は
  「接続したマシンが読み取り担当」**——接続情報を持つマシンだけが記憶の整理で読む（他のマシンでは同じサービスを接続しない）。local スコープは各マシンが自分で読む。
- Obsidian を使うなら connector として宣言する（`watari connector add --name obsidian --scope local`）。ノートはユーザー本人の産出物なので、自分の言葉でまとめた内容は mastery 2 の根拠になり得る。知識の中身は log に写さず、到達状態とノートへのポインタ（refs.cwd）だけを書く（ノートの中身の正本は vault）。カーソルは他 connector と同じく `--advance-ext obsidian=<最新ts>`。

## connector（記憶の整理のときに読み込むソースの宣言）
transcript 以外のソース（メール・タスク・チャット等）は、`config.json` の `connectors` に**宣言される**。
対応サービス（`watari connect` で接続したもの）は `watari connector read <name> --json`（`--since` 省略で
カーソルの続きから）で読める。カスタム宣言のソースは、その `read` 指示に従ってエージェント（Pi 上の MCP 等）が
自分のツールで読む。CLI が担うのはカーソルの追跡と ingest（薄い宣言機構であってプラグインエンジンではない）。
- 宣言：`watari connector add --name <slug> --scope cloud|local --read "<cursor 以降どう読むか>"`。一覧は `watari connector list`。
- 各エントリ＝`{"name":<小文字スラッグ>, "scope":"cloud"|"local", "read":<自由記述の読み方指示>}`。同名は上書き（二重管理を避ける）。
- `scope`：`local`＝そのマシン固有のソース（各マシンが自分の整理で読む）。`cloud`＝どのマシンから読んでも同じ位置になるソース
  （メール等）。**cloud は「接続したマシンが読み取り担当」**（多重取り込み防止。接続情報を持つマシンだけが読む）。
- カーソルは `--advance-ext <name>=<最新ts>` で前進（マシンごとの host 記録に格納。`--advance-ext` の許可名はここで宣言した名前に限る）。
- EXAMPLE（宣言の形。ツール実装は含まない）：
  ```json
  {"connectors": [
    {"name": "mail",  "scope": "cloud", "read": "cursor(前回ts)以降に届いた自分宛メールを新しい順に読み、要点＋ポインタだけ判定する"},
    {"name": "tasks", "scope": "cloud", "read": "cursor 以降に更新されたタスク/issue を読み、状態変化と締切だけ拾う（中身は写さない）"}
  ]}
  ```

## 1回の処理上限（初回・差分大の決定論化）
1回で処理する件数は次の**小さい方**で固定（`watari scan` が自動で適用する。あなたが数える必要はない）：
- メッセージ **N = 300000 件**、または
- **最古の未処理メッセージ**から最大 **30 日ぶん**（1回の処理量の上限。整理が定期的に走る前提で、超過分は truncated として次回に回す。窓の起点をカーソルでなく最古の未処理にするのは、カーソル以降に30日超の空白があっても取りこぼさない＝カーソルを永久停滞させないため）。
処理した最後の timestamp までカーソルを進め、残りは次回に回す。

## state 再生成と監査
`watari regen` が log から state を作り直す（`--now` 指定で決定的・冪等。`--check` は書き込まず現 state と比較）。
`watari audit` が形式・(uuid,kind) 重複・state と log の乖離・宙に浮いた related を検査する（`--coverage` で log に一度も現れないセッションの一覧も出す）。
同じ log ＋ 同じ now なら必ず同じ state（log が唯一の正本）。
