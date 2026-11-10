---
status: approved
approved_date: 2026-11-10
version: "1.0"
---

# 失敗通知 タスク

タスク 11件(claude 9 / copilot 2)

> TDDで進める。各タスクは 🔴 Red(失敗するテストを書く) → 🟢 Green(最小実装) → 🔵 Refactor の順で進める。

テストは `apps/digest-platform/application` を作業フォルダにして `python3 -m unittest discover -s tests/failure_notification -t .`(性能は `-s tests/perf`)。

## 失敗の通知

### 1. 失敗通知が受け取った12項目のそろいと型を確かめる 【担当: claude】

実行係の不具合で契約に合わない項目が来たとき、黙って通知せず「通知の失敗」として記録させるため。

<details><summary>詳細を開く</summary>

- `application/launchd/failure_notification/__init__.py` に `judge_and_notify(failure)` の入口と入力の確かめを作る(design.md「バリデーション」)
- 12項目のキーの欠け・系統と確定の理由の値の誤り・真偽値でない・失敗日時が ISO 8601 として読めない、で例外。多いキーは無視する
- 例外のメッセージに値を入れない(項目名だけ)
- テスト: `tests/failure_notification/test_validation.py`。`tests/failure_notification/__init__.py` で `launchd/` を `sys.path` に足す(`tests/runner/__init__.py` と同じ書き方)

</details>

### 2. 通知済みなら見送り、それ以外はすべて通知する判定を作る 【担当: claude】

同じ配信日・編の失敗と警告をそれぞれ1回だけ届け、確定済みの失敗は回数で見送らないようにするため。

<details><summary>詳細を開く</summary>

- 「既に通知済みか」が真なら書き出しを呼ばずに `{"notified": false, "reason": "already_notified"}`
- 偽なら確定の理由8種・試行回数・上限回数によらず本文を組み立てて書き出しを呼び、結果を `notified` / `write_failed` に変えて返す
- 書き出しの部品はテストで差し替えられるよう、引数(既定は本物)で受ける
- 受け入れ条件(テスト戦略): 通知の判定-1〜5・通知のタイミング-1・3。`tests/failure_notification/test_judge.py`

</details>

### 3. 監視スレッドに載せる本文(件名と4要素)を組み立てる 【担当: claude】

運営者がログを開かなくても何が失敗したか分かり、エラーの中身や鍵が Teams に流れないようにするため。

<details><summary>詳細を開く</summary>

- `application/launchd/failure_notification/message.py` の `build_message(failure)` が appendix.md「本文」の HTML断片を返す
- 件名の【失敗】/【警告】、系統の日本語名、編の有無、警告の定型句、日本時間の「年-月-日 時:分」、ホームフォルダの `~` への置き換え、`html.escape`
- 受け入れ条件(構造検証): 通知の本文と投稿-1・2・3・5、本文に載せないもの-1。`tests/failure_notification/test_message.py`

</details>

### 4. 投稿先「Digest監視」を引いて投稿用ファイルを書き出し、失敗したらその場で最大3回やり直す 【担当: claude】

teams-post と同じ規則で書き出して Power Automate のフローがそのまま監視スレッドへ投稿できるようにし、一瞬の書き込みの失敗でも通知が翌日以降にずれ込まないようにするため。

<details><summary>詳細を開く</summary>

- `application/launchd/failure_notification/writer.py` の `write_post(content, profiles_path=None, now=None)` が `True` / `False` を返す
- `~/.claude/config/project-profiles.json` の `user.teams.destinations["Digest監視"].folder_path` を読む。無い・壊れている・キーが無いは `False`
- 書き出しの前に `setiopolicy_np(IOPOL_TYPE_VFS_MATERIALIZE_DATALESS_FILES, IOPOL_SCOPE_PROCESS, IOPOL_MATERIALIZE_DATALESS_FILES_ON)` を ctypes で呼ぶ(失敗しても続ける。teams-transcript-fetcher の materialize と同じ値)
- 投稿先フォルダに `post-<YYYYMMDD-HHMMSS>.txt` を `open(..., "x")` で作り、本文を1回の書き込みで書いて閉じる。名前が埋まっていれば(`FileExistsError`)`-2`〜`-1000` を試す。フォルダは作らない。作ったあとの書き込みで失敗したら、そのファイルを消してからやり直す
- 書き込みの失敗は10秒おきに最大3回まで試す(待ちは引数で差し替えられるようにし、テストは0秒で回す)。投稿先の設定が引けない・フォルダが無いときは試し直さない
- 3回とも失敗したら標準エラーに `failure-notification: write_failed <例外の種類>` を1行。パスは出さない
- 受け入れ条件(契約): 通知の本文と投稿-6。`tests/failure_notification/test_writer.py`(一時フォルダと一時の設定ファイルで。設定ファイルは `project-profiles.example.json` の destinations の形に合わせる)

</details>

### 5. 本物の判定関数を実行係の引き渡しに通す契約テストを書く 【担当: claude】

batch-runner の `handoff.notify` が判定関数の返り値と例外を契約どおりに扱えることを、偽の関数でなく本物で確かめるため。

<details><summary>詳細を開く</summary>

- `handoff.build` で作った12項目を `handoff.notify(handoff.resolve_judge_fn({}), failure)` に通し、通知した・通知済み・書き出し失敗の3つが受け入れられる
- 契約に合わない入力5形(キーの欠け・型の誤り・系統の値の誤り・確定の理由の値の誤り・失敗日時が読めない)が `notify_error` になる
- 書き出し先は一時の設定ファイルを向ける(本物の投稿先に書かない)
- 受け入れ条件(契約): 通知の判定-6。`tests/failure_notification/test_contract.py`

</details>

### 6. 失敗通知が Claude と外部通信を呼ばないことを確かめる構造検証を書く 【担当: copilot】

非機能要件「通知の判定と本文の組み立てで Claude を呼ばない(0回)」が、あとの変更で崩れたら気づけるようにするため。

<details><summary>詳細を開く</summary>

- `application/launchd/failure_notification/` の全 `.py` を `ast` で読み、`subprocess`・`urllib`・`http`・`socket` の import が無いこと、文字列 `claude` を引数に持つ呼び出しが無いことを確かめる
- 受け入れ条件(構造検証): 非機能要件-2。`tests/failure_notification/test_no_external_calls.py`。`python3 -m unittest discover -s tests/failure_notification -t .` で通る

</details>

### 7. 1件の通知の書き出しまでの所要時間を測る性能テストを書く 【担当: copilot】

非機能要件「失敗の確定から投稿用ファイルの書き出しまで1分以内」を数値で確かめるため。

<details><summary>詳細を開く</summary>

- 一時フォルダを投稿先にした一時の設定ファイルを作り、`judge_and_notify` を1回呼んで返るまでが40秒以内(要件の2/3)で、ファイルが1つできること
- 置き場所は `tests/perf/test_notify_latency.py`(既存の `tests/perf/support.py` の書き方に合わせる)
- 受け入れ条件(性能): 非機能要件-1。`python3 -m unittest discover -s tests/perf -t .` で通る

</details>

## ヘルスチェックの宣言

### 8. アプリ登録表から日次ヘルスチェックの宣言の条目を作る 【担当: claude】

plist と同じ登録表から宣言を作り、起動時刻と点検の時刻の一覧がずれないようにするため。

<details><summary>詳細を開く</summary>

- `application/launchd/make_health_declarations.py` の `build_entries(registry)` と、引数なしの実行で条目を標準出力に出す入口
- 識別名と時刻は `make_plists.py` の `label()`・`PUBLISH_FIRST`・`PUBLISH_RETRIES`・`REVIEW_TIME`・`ALL_WEEKDAYS` を使う
- 書式は appendix.md「宣言の条目」
- 受け入れ条件(構造検証): ヘルスチェックの宣言への追加-1(生成の部分)・2・3。`tests/failure_notification/test_health_declarations.py`(テスト用の登録表で、有効・無効・週1回・見直しの日の有無を並べる)

</details>

### 9. 宣言の条目を控えを残して宣言ファイルへ反映する 【担当: claude】

アプリを有効・無効にするたびに流しても同じ結果になり、無効にしたアプリの条目も消えるようにするため。

<details><summary>詳細を開く</summary>

- `--apply` で宣言ファイルを `.bak-<YYYYMMDD-HHMMSS>` に複製し、`label` が `com.example.digest-` で始まる条目を取り除いて作った条目を足し、書き戻す
- 宣言ファイルが無い・JSON として読めないときは書き換えずに終了コード1
- 宣言ファイルのパスはテストで差し替えられるよう引数で受ける(既定は `~/.claude/config/automation-health-check.json`)
- 受け入れ条件(構造検証): 2回流して同じ内容になる、他の条目と `_comment` などのキーが残る、控えができる。`tests/failure_notification/test_health_declarations.py`

</details>

## 手順書と環境スモーク

### 10. digest-platform の README と architecture.md を失敗通知の運用に合わせる 【担当: claude】

運営者がアプリを有効にするときに、宣言の反映・判定の手動実行・Confluence のカタログ更新を漏らさないようにするため。

<details><summary>詳細を開く</summary>

- README「アプリを有効にするとき」の手順4を、`make_health_declarations.py --apply` → 日次ヘルスチェックの判定を手で1回回す → Confluence の定期実行カタログに同じジョブを載せる、に置き換える。「failure-notification を実装するまではどのアプリも有効にしない」の段落を、監視スレッドの投稿先「Digest監視」を用意してから有効にする、に書き換える
- README に監視スレッドの用意(extend-teams-automation の「特定スレッドへの返信」方式で、表示名「Digest監視」として登録する)の節を足す
- README「テスト」に `tests/failure_notification` の実行コマンドを足す
- architecture.md の機能マップの failure-notification の状態を実装の進み具合に合わせる

</details>

### 11. launchd 経由の実行係から監視スレッドに失敗の通知が届くことを確かめる 【担当: claude】

本番と同じ起動経路で、判定関数の読み込み・投稿先の解決・OneDrive への書き出し・Power Automate の投稿までが通ることを確かめるため。

<details><summary>詳細を開く</summary>

- 前提: 運営者が監視スレッドと投稿先「Digest監視」を用意済み
- launchd に登録した環境スモーク用のアプリのジョブを即時起動し、手動実行の失敗を起こす(`DIGEST_HANDOFF_MODULE` は付けない)。監視スレッドに【失敗】の返信が届き、実行状態ファイルの「通知済み」が真になる。書きかけのファイル(空や途中で切れた本文)が投稿されていないことを見る
- `make_health_declarations.py --apply` を環境スモーク用の登録表で流し、日次ヘルスチェックの判定を手で1回回して新しい条目が読める。終わったら宣言を元に戻す
- 受け入れ条件(環境スモーク): 通知の本文と投稿-4・ヘルスチェックの宣言への追加-1。結果は下の確認チェックリストに書く

</details>

## 確認チェックリスト(環境スモーク)

- [ ] 本番と同じ経路(launchd)で実行係を起動し、失敗通知が読み込まれる → 結果
- [ ] 監視スレッドに【失敗】の返信が届き、実行状態ファイルの通知済みが真になる → 結果
- [ ] 投稿先フォルダを外したときに書き出し失敗が要約ログ(WARNING と `RUN-FAILED`)と launchd の標準エラーに残る → 結果
- [ ] 宣言の反映後、日次ヘルスチェックの判定を手で回して新しい条目が読める → 結果
- [ ] アプリを有効にしたとき、Confluence の定期実行カタログに同じジョブが載っている → 結果
