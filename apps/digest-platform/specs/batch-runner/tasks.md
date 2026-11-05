# batch-runner タスク

タスク 20件(claude 18 / copilot 2)

> TDDで進める。各タスクは 🔴 Red(失敗するテストを書く) → 🟢 Green(最小実装) → 🔵 Refactor の順で進める。

## 土台

### 1. apps/digest-platform/application に Python の実行係パッケージと unittest の骨組みを置く 【担当: claude】

以降のタスクのテストを `python3 -m unittest` で回せるようにする。

<details><summary>詳細を開く</summary>

- `application/launchd/digest_runner/__init__.py`・`application/tests/runner/__init__.py`・`application/tests/perf/__init__.py` を作る
- テストは `apps/digest-platform/application` を作業フォルダにして `python3 -m unittest discover -s tests/runner -t .` で回す(README に書く)
- Python は標準ライブラリだけ。`requirements.txt` は作らない
- 受け入れ: 空のテストが1件通る。`~/.claude/lib` を参照する import が無い

</details>

### 2. apps/digest-platform/application に package.json(tsx・vitest・typescript)を置き、vitest が動くようにする 【担当: claude】

Claude の呼び出し部品(TypeScript)のテストを回せるようにする。

<details><summary>詳細を開く</summary>

- `application/package.json` に `tsx`・`vitest`・`typescript` を devDependencies で書く(architecture.md「採用技術」で合意済みの OSS だけ。Next.js・mermaid は local-site-serving で足す)
- `npm install` はサンドボックスからできないため、手元のターミナルで実行するコマンドブロックを README に書き、ユーザーに渡す
- `npm test`(vitest run)・`npm run typecheck`(tsc --noEmit)を scripts に置く
- 受け入れ: 空のテストが1件通る(手元のターミナルで確認)

</details>

## 実行係(Python)

### 3. アプリ登録表 apps.json を置き、registry.py でアプリ×系統の登録を読んで未登録を失敗にする 【担当: claude】

実行係が起動すべきアプリと判定条件を1ファイルから引けるようにする。

<details><summary>詳細を開く</summary>

- 仕様: `requirements.md#定時起動-3`、design.md「起動前の判定」手順1、appendix「アプリ登録表」
- `apps.json` に5アプリの `publish`(research-digest=土曜・上限4、future-digest=日曜・上限4、ほかは月〜金・上限1)と `review`(`dayOfMonth: null`・上限1)を書く。`editionByWeekday` は各アプリの spec で埋める前提で `null`
- `registry.load(path)` が登録表を読み、`registry.get(app, kind)` が登録を返す。無いアプリ・無い系統・`review.dayOfMonth` が `null` は `Unregistered` 例外
- 必須項目の欠け・JSON の壊れは `RegistryBroken` 例外
- テスト: 正常1、未登録アプリ1、未登録系統1、壊れた登録表1

</details>

### 4. calendar.py で日本時間の配信日と曜日→編を決める 【担当: claude】

バッチを起動する前に、どの配信日・編の実行状態を見るかを実行係が自分で決められるようにする。

<details><summary>詳細を開く</summary>

- 仕様: design.md「起動前の判定」手順2、決定事項「配信日と編の決め方」
- `calendar.now_jst()` はサンドボックスの UTC に影響されず `Asia/Tokyo` の現在時刻を返す(`zoneinfo`)
- `calendar.resolve(registration, now)` が配信日(`YYYY-MM-DD`)と編(または `None`)を返す。`review` は編なし
- テスト: 正常1、UTC 深夜(JST 朝)で日付が JST 側になる1、編を持たないアプリ1、`editionByWeekday` に当日の曜日が無いとき編なし1

</details>

### 5. state.py で実行状態ファイルを読み書きし、壊れていたら退避して失敗確定で書き直す 【担当: claude】

試行回数・各回の結果・通知済みを後から確かめられるようにし、壊れたファイルで通知が繰り返されないようにする。

<details><summary>詳細を開く</summary>

- 仕様: `requirements.md#実行状態の記録-1,-3`、design.md「再実行の判定と失敗の引き渡し」手順6、appendix「実行状態ファイル」
- `state.load(path)` は無ければ `pending` の空の状態、読めれば dict、壊れていれば `StateBroken` 例外(`state.quarantine(path)` が `.corrupt-<日時>` に退避する)
- `state.save(path, data)` は一時ファイルに書いて置き換え、フォルダは 700・ファイルは 600
- `state.add_attempt(data, attempt)`・`state.set_status(data, status)` で当日の状態を更新する
- テスト: 正常の読み書き1、構造検証(JSON として読め必須項目を持つ)1、失敗形3(空・壊れた JSON・必須項目の欠け)、退避ファイルの名前1

</details>

### 6. lock.py でアプリ×系統のロックを mkdir で取り、60分より古いロックを回収する 【担当: claude】

同じアプリ×系統の二重起動を防ぎ、異常終了で残ったロックで翌日以降が止まらないようにする。

<details><summary>詳細を開く</summary>

- 仕様: `requirements.md#定時起動-4`、`requirements.md#時間の上限-3`、design.md「起動前の判定」手順3・8
- `lock.acquire(dir, stale_seconds=3600)` が真偽を返す。ロックフォルダには pid を書く。作成時刻が 60 分より前なら削除して取り直す
- `lock.release(dir)` はどの経路でも呼ばれる(`try/finally`)
- テスト: 取れる1、取れない(60分以内)1、回収して取れる(61分前)1、59分前は回収しない1

</details>

### 7. environment.py で node・claude・python3 の絶対パスを決め、PATH・TZ・CAバンドル・バッチへ渡す環境変数を組み立てる 【担当: claude】

launchd が PATH を引き継がなくてもバッチが node と claude を見つけ、社内プロキシを通れるようにする。

<details><summary>詳細を開く</summary>

- 仕様: `requirements.md#定時起動-5`、`requirements.md#Claude の呼び出し規約-1`、design.md「バッチの起動と成否の判定」手順1、appendix「バッチへ渡す環境変数」「実行ファイルの探し方」
- `environment.find_binaries(env)` は環境変数 → PATH → 既知の候補の順で探し、見つからなければ `BinaryNotFound` 例外
- `environment.ca_bundle()` は `~/Library/Application Support/ca-bundle/ca-bundle.pem` があればそれ、無ければ `/etc/ssl/cert.pem`
- `environment.build(env, context)` は親の環境から `ANTHROPIC_API_KEY` と名前に `TOKEN`・`SECRET`・`KEY` を含む変数を落とし、`DIGEST_*`・`PATH`・`TZ`・`NODE_EXTRA_CA_CERTS`・`SSL_CERT_FILE` を足す
- テスト: 正常1、環境変数の指定が優先1、見つからない1、認証に見える変数が落ちる1(否定確認: 落とす処理を消すと落ちる)、CAバンドルの2段1

</details>

### 8. launch.py でバッチを新しいプロセスグループで起動し、出力を詳細ログに流し、60分で打ち切る 【担当: claude】

バッチが終わらないときに次の再実行の時刻と重ならないようにし、出力を後から読めるようにする。

<details><summary>詳細を開く</summary>

- 仕様: `requirements.md#成否の判定-3,-5`、`requirements.md#時間の上限-1`、design.md「バッチの起動と成否の判定」手順2〜4、appendix「詳細ログの先頭と末尾」
- `launch.run(command, cwd, env, log_path, timeout_seconds=3600)` が終了コード・打ち切りかどうか・開始時刻・標準出力の最終行を返す。`start_new_session=True` で起動し、timeout で TERM → 5秒 → KILL をプロセスグループに送る
- 詳細ログの先頭にはパスと識別子だけを書き、環境変数の一覧は書かない
- テスト: 正常1、打ち切り(上限を2秒にして sleep する偽バッチ。子プロセスも残らない)1、構造検証(先頭に認証に見える値が無い。否定確認: 環境を丸ごと書く処理を入れると落ちる)1

</details>

### 9. judge.py で終了コード・成功マーカー・生成物の3点から成否と失敗の種類を決める 【担当: claude】

Claude のヘッドレス実行が終了コード0で失敗しても、成功と誤判定しないようにする。

<details><summary>詳細を開く</summary>

- 仕様: `requirements.md#成否の判定-1,-2,-4`、design.md「バッチの起動と成否の判定」手順5〜6、appendix「アプリ登録表」の `artifacts`
- `judge.evaluate(exit_code, last_line, artifacts, started_at, timed_out)` が結果(`succeeded`・`temporary_failure`・`permanent_failure`・`timeout`)と欠けた点の一覧を返す。生成物は存在し、更新時刻が起動時刻より後であること
- `judge.expand_artifacts(patterns, date, edition)` が `{date}` `{edition}` `{yearMonth}` を埋める
- テスト: 3点そろって成功1、各点が欠けて失敗3、終了コード2で永続1、古い生成物だけでは成功にならない1、終了コード0でマーカー無しの fixture(想像 fixture。環境スモークで実出力に置き換える)1

</details>

### 10. summary_log.py で要約ログに「実行開始」「実行終了」と失敗確定の RUN-FAILED を書く 【担当: claude】

日次ヘルスチェックが実行係の最終実行と失敗確定をログから読めるようにする。

<details><summary>詳細を開く</summary>

- 仕様: `requirements.md#成否の判定-6`、design.md「ログ」、appendix「要約ログの行」
- `summary_log.started(path, context)`・`summary_log.finished(path, result, attempt, status, log_path)`・`summary_log.warning(path, what, detail)`。行頭は ISO 8601(JST オフセット付き)
- `RUN-FAILED` は `status=failed` のときだけ付ける
- テスト: 構造検証(書いた行を `^\d{4}-\d{2}-\d{2}T[^ ]+ (INFO|WARNING) ` と `実行終了:` で読める)1、失敗確定で `RUN-FAILED` が付く1、再実行待ちでは付かない1(否定確認: 条件を外すと落ちる)

</details>

### 11. retention.py で runs・logs・claude-io の90日より古いファイルを消す 【担当: claude】

記録が無限に増えないようにしつつ、障害の調査に四半期分を残す。

<details><summary>詳細を開く</summary>

- 仕様: `requirements.md#ログと記録の保持-1`、design.md「起動前の判定」手順4
- `retention.sweep(data_dir, now, days=90)` が消したパスと消せなかったパスを返す。更新時刻で判定し、空になったフォルダも消す
- テスト: 91日前は消える1、89日前は残る1、消せないファイル(権限なし)があっても続行して一覧に載る1

</details>

### 12. handoff.py で失敗通知の判定関数へ9項目を渡し、通知したか・理由を実行状態ファイルに書く 【担当: claude】

失敗を確定したとき、通知するかの判定を失敗通知に委ねつつ、結果を後から確かめられるようにする。

<details><summary>詳細を開く</summary>

- 仕様: `requirements.md#失敗の引き渡し-1,-2`、design.md「再実行の判定と失敗の引き渡し」手順4〜5、appendix「失敗通知に渡す項目と返る項目」
- `handoff.build(context, state, failure_kind, log_path)` が9項目の dict を作り、`handoff.notify(judge_fn, failure)` が `{"notified", "reason"}` を返す。`judge_fn` は既定で `failure_notification.judge_and_notify` を遅延 import し、無ければ `notified=False, reason="notify_error"`
- failure-notification が実装されるまでは、同じ契約を持つ偽の関数をテストで渡す
- テスト: 契約(9項目が揃って渡る)1、結果が実行状態に書かれる1、関数が例外のとき `notify_error` 1

</details>

### 13. runner.py の入口で起動前の判定・起動・成否の判定・再実行の判定を組み合わせ、終了コードを返す 【担当: claude】

launchd と手元ターミナルのどちらから起動しても、同じ判定と記録で1回の実行が完結するようにする。

<details><summary>詳細を開く</summary>

- 仕様: `requirements.md#定時起動-3,-7`、`requirements.md#実行状態の記録-2`、`requirements.md#再実行-1〜-5`、design.md「起動前の判定」「バッチの起動と成否の判定」「再実行の判定と失敗の引き渡し」、appendix「実行係の手動実行」
- 引数は `<アプリ名> <系統> [--manual]`。`DIGEST_DATA_DIR` の既定は `~/Library/Application Support/digest/<アプリ名>/`
- 起動前の判定の経路ごとの結果(`already_succeeded`・`failed_final`・`locked`・`unregistered`)と、定時の失敗後の当日の状態(上限4/1・永続失敗・手動は数えない・月次見直しは1回)をここで決める
- 想定外の例外は要約ログと標準エラーに書き、ロックを外して終了コード2
- テスト: 成功1、成功済みで起動しない1、上限4のアプリの4回目まで起動・5回目は起動しない2、上限1は2回目を起動しない1、永続失敗で上限未満でも失敗確定1、手動の失敗が回数と状態を変えない1、月次見直しは1回で失敗確定1、手動で成功済みの日は起動しない1、壊れた実行状態で退避・失敗確定・引き渡し1。偽のバッチ(シェルスクリプト)と偽の判定関数を使う

</details>

## launchd と性能

### 14. make_plists.py でアプリ登録表から5アプリ×系統の plist を生成し、RunAtLoad を付けず時刻を正しく並べる 【担当: copilot】

運営者が手元で1コマンド実行するだけで、全ジョブの plist が登録できる形で揃うようにする。

<details><summary>詳細を開く</summary>

- 仕様: `requirements.md#定時起動-1,-6`、`requirements.md#実行時刻-1〜-4`、design.md「launchd ジョブの生成と登録」、appendix「plist」
- 引数: `--node <絶対パス> --claude <絶対パス> --python <絶対パス> [--out <フォルダ>]`。存在しないパス・`Versions/3.` のようにバージョン番号を含むパスは終了コード2で拒否
- `publish` は `weekdays` ごとに 06:30、`maxAttempts` が 2 以上なら 10:30・14:30・18:30 も並べる。`review` は `dayOfMonth` が `null` なら生成しない、あれば `Day`・07:30
- `EnvironmentVariables`・`StandardOutPath`・`ProcessType` は appendix のとおり。`RunAtLoad` は書かない
- 生成前に `plistlib.loads` で読み直して検査する
- 受け入れ条件(構造検証、各1件): 全 plist が `plistlib` で読める・`RunAtLoad` キーが無い(否定確認: 足すと落ちる)・research-digest に Weekday 6、future-digest に Weekday 0・06:30 が全 publish にある・10:30/14:30/18:30 が research/future にだけある・review は 07:30 の1つだけ・バージョン番号を含むパスを拒否する

</details>

### 15. tests/perf に、入口から起動コマンドの直前までが5秒以内であることを測る性能テストを置く 【担当: copilot】

launchd の起動からバッチの起動までを10秒以内に収める要件を、数値で確かめられるようにする。

<details><summary>詳細を開く</summary>

- 仕様: `requirements.md#非機能-1`、design.md「パフォーマンス」
- `tests/perf/test_startup.py`。登録表・実行状態ファイル(未着手)・90日分相当の古いファイル(300件)を一時フォルダに用意し、偽のバッチ(即終了)で `runner.py` を起動して「実行開始」の行が要約ログに書かれるまでを計測、5秒未満を合格とする
- 毎回の TDD では回さず、`python3 -m unittest discover -s tests/perf -t .` で単独に回す(README に書く)
- 受け入れ条件: テストが1件あり通る。閾値を 0.001 秒にすると落ちる(否定確認)

</details>

## Claude の呼び出し部品(TypeScript)

### 16. batch/claude.ts で claude -p を JSON 出力・ツール制限・10分の打ち切りで呼び、応答を成功・一時的な失敗・利用枠切れに分類する 【担当: claude】

5アプリのバッチが同じ約束で Claude を呼び、利用枠切れを再実行しない失敗として実行係に伝えられるようにする。

<details><summary>詳細を開く</summary>

- 仕様: `requirements.md#Claude の呼び出し規約-1〜-5`、`requirements.md#時間の上限-2`、design.md「Claude の呼び出し規約」手順1・3〜5・7、appendix「Claude の呼び出し」
- `callClaude({ prompt, materials, name }, options)` が `{ ok: true, text }` か `{ ok: false, kind: "temporary" | "quota" | "timeout" }` を返す。claude の実行ファイルは `DIGEST_CLAUDE_BIN`
- 指示文の末尾に成功マーカーの指示を付け足す。起動引数は `--output-format json --allowedTools WebSearch,WebFetch --disallowedTools "mcp__*,Bash,Edit,Write,NotebookEdit"`。子プロセスの環境から `ANTHROPIC_API_KEY` を外す
- 分類: 封筒が読めない→temporary、`is_error` 真かつ(429 または文言一致)→quota、その他の `is_error`→temporary、`is_error` 偽で最終行がマーカーでない→temporary
- テスト(vitest。`DIGEST_CLAUDE_BIN` に偽の claude スクリプトを指定): 正常1、打ち切り(上限を2秒に縮める)1、契約 fixture 2種(利用枠切れの封筒・通常失敗の封筒。想像 fixture。環境スモークで実応答に置き換える)+失敗形3(空・JSON でない・`is_error` 欠け)、構造検証(組み立てた指示文の末尾にマーカーの指示がある、起動引数に許可・不許可ツールがある)2

</details>

### 17. batch/claude.ts の控えとして、指示文と応答の封筒を claude-io に書く 【担当: claude】

要約が変だったときに、何を頼んで何が返ったかを後から確かめられるようにする。

<details><summary>詳細を開く</summary>

- 仕様: `requirements.md#Claude の呼び出し規約-6`、design.md「Claude の呼び出し規約」手順2・6、appendix「Claude の呼び出し」の控え
- `DIGEST_CLAUDE_IO_DIR` の下に `<試行番号>-<連番2桁>-prompt.txt` と `-response.json` を書く(フォルダ 700・ファイル 600)。打ち切りは `{"timeout": true}`
- テスト(vitest): 構造検証(両ファイルが所定の名前で存在し、response が JSON として読める)1、連番が呼び出しごとに増える1

</details>

### 18. batch/exit.ts でバッチの終わり方(成功マーカーと終了コード0・1・2)を共通部品にする 【担当: claude】

5アプリのバッチが同じ形で完遂・一時的な失敗・再試行しても直らない失敗を実行係に伝えられるようにする。

<details><summary>詳細を開く</summary>

- 仕様: `requirements.md#成否の判定-2`、design.md「Claude の呼び出し規約」手順8、決定事項「失敗の種類を実行係に伝える方法」、appendix「バッチの終わり方」
- `finishOk()` は標準出力の最終行に `DIGEST-BATCH-OK` を出して 0、`failTemporary(reason)` は理由を1行出して 1、`failPermanent(reason)` は 2
- テスト(vitest): 3経路の最終行と終了コード各1

</details>

## 文書と確認

### 19. apps/digest-platform/README.md にテスト・plist の生成と登録・手動実行・データフォルダの許可登録の手順を書く 【担当: claude】

運営者が手元のターミナルで登録・手動実行・結果の確認を、コピペできるコマンドで行えるようにする。

<details><summary>詳細を開く</summary>

- 仕様: `requirements.md#定時起動-7`、`requirements.md#実行状態の記録-4`、design.md「launchd ジョブの生成と登録」手順5、appendix「実行係の手動実行」
- 書くこと: `npm install`・`npm test`・`python3 -m unittest`・性能テストの回し方、`make_plists.py` の実行と `launchctl bootstrap gui/$(id -u) <plist>`・`bootout`・`kickstart -k` のコマンド、手動実行、要約ログ・詳細ログ・実行状態ファイルの場所、やり直したいときに実行状態ファイルを消す手順、`~/.claude/settings.json` の `permissions.additionalDirectories` に `~/Library/Application Support/digest` を足す手順
- 受け入れ条件: コマンドは絶対パス・プレースホルダなし(`<運営者>` は `$HOME` で書く)

</details>

### 20. launchd と手元ターミナルの2経路で実行係を1回ずつ通し、Claude の封筒の実応答を保存して fixture を置き換える(環境スモーク) 【担当: claude】

本番と同じ経路で起動し成果物が出ることと、仮置きした封筒の項目名・利用枠切れの文言を実機で確かめる。

<details><summary>詳細を開く</summary>

- 仕様: `requirements.md#定時起動-1,-2,-5`、`requirements.md#実行状態の記録-4`、`requirements.md#Claude の呼び出し規約-1`、`requirements.md#実行時刻-5`、design.md「テスト戦略」の環境スモーク行
- 5アプリのバッチはまだ無いため、登録表に検証用の `smoke` アプリ(偽のバッチ: `claude.ts` を1回呼んで記事ファイル1つを書く TypeScript)を一時的に足して通す。終わったら登録表から外す
- 保存する実応答: 正常の封筒1件(`tests/batch/fixtures/claude-ok.json`)。利用枠切れの封筒は実機で出せないため、`claude -p` のヘルプまたは公式ドキュメントで項目名を確かめ、確かめた範囲を fixture のコメントに書く
- スリープの追い実行は、定時を過ぎるまでスリープさせてから復帰して要約ログに1回だけ「実行開始」が出ることで確かめる
- 結果は下のチェックリストに書く

</details>

## 環境スモークの確認チェックリスト

- [ ] 本番と同じ経路(launchd / claude -p / 手元ターミナル)で起動する → 結果
- [ ] 成果物(ファイル・通知・ページ更新)が出る → 結果
- [ ] 失敗させたときの通知・ログが届く → 結果

