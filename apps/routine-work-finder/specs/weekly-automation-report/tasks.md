# 定型業務の週次レポート タスク

タスク 16件(claude 16 / copilot 0)

> TDDで進める。各タスクは 🔴 Red(失敗するテストを書く) → 🟢 Green(最小実装) → 🔵 Refactor の順で進める。

全件を claude 担当にした理由: 委任用アカウントのクレジット残量の記録が、月次リセット日(2026-10-01)を過ぎて無効になっている(リセット日到達)。

操作の記録(activity-recording)のタスク12(記録を期間で読む共通の処理)が終わってから着手する。置き場所は、特に書かない限り `apps/routine-work-finder/application/` の下(以下このフォルダからの相対パス)。テストはこのフォルダで `python3 -m unittest discover -s tests -t .`、性能テストは `tests/perf/` を別に回す。

## 時間の集計

### 1. 記録の行を作業・会議・離席・記録しないアプリに分け、離席を最後の入力まで遡る処理を作る 【担当: claude】

週の合計の4区分を、離席の判定のルールどおりに数えられるようにする。

<details><summary>詳細を開く</summary>

- `routine_work_finder/report/aggregate.py` の行の区分と遡り。手順は design.md「時間を集計する」1〜4
- テスト: 時間の集計-1(判定の順と合計、合計の和が行数×5秒と等しいことを境界値の列挙で)、-2、-3、離席の判定-1(299・300・301秒と遡り)、-2(ロック・空きは4区分に入らない)、-3(マイク・スリープの抑止は直さない)

</details>

### 2. 作業の時間をアプリと中身の組にまとめ、上位10件・主な時間帯・取れなかった時間を出す処理を作る 【担当: claude】

時間の使い方の上位10件と、記録の状態に出す取れなかった時間をそろえる。

<details><summary>詳細を開く</summary>

- `aggregate.py` の組・作業のまとまり(30分で区切る)・主な時間帯(長いまとまり2つ)・取れなかった時間。手順は design.md「時間を集計する」5〜7・9・10
- テスト: 時間の集計-4(11件目を落とす)、-5、-6(空き29秒・30秒・止めていた期間・起動し直しの前の空き・中身の取れなかった時間)、作業の要約-2

</details>

### 3. 作業のまとまりを数えて自動化案の候補を選ぶ処理を作る 【担当: claude】

週2回以上の繰り返しを、テストで確かめられる条件で候補にする。

<details><summary>詳細を開く</summary>

- `aggregate.py` の候補の選び出し。手順は design.md「時間を集計する」8
- テスト: 自動化案-1(まとまり1つ・2つ・29分あけた2回)、自動化案を作る条件-2

</details>

## 既存の作業の記録

### 4. 全PJのサイトから JIRA の自分の更新と Confluence の自分の編集を読む処理を作る 【担当: claude】

チケットとページの作業を、作業の要約と自動化案の材料に加える。

<details><summary>詳細を開く</summary>

- `routine_work_finder/report/sources_atlassian.py`。PJプロファイルの全PJからサイトを集めて1つにまとめ、`~/.claude/lib/atlassian_rest` で読む。検索の形は appendix.md「JIRA と Confluence の検索の形」
- 実装の最初に、手元で REST を1回呼んで検索と変更履歴の応答を保存し、人名・メール・URL を置き換えて `tests/fixtures/jira/`・`tests/fixtures/confluence/` に置く(サンドボックスから通らなければ手元のターミナルで取ってもらう)
- テスト: 既存の作業の記録の取り込み-1・-2 の契約(正常・空・欠損・型違い・時間切れ、変更履歴の並べ直し)、-5 のうちサイトの一部だけ失敗

</details>

### 5. Claude Code の会話の記録から人が打った依頼文を選んで伏せ字にする処理を作る 【担当: claude】

依頼文の冒頭を、ツールの結果や認証情報を混ぜずに材料に加える。

<details><summary>詳細を開く</summary>

- `routine_work_finder/report/sources_claude_code.py`。選ぶ条件と伏せ字の規則は appendix.md
- fixture: 実際の会話のファイルから条件の判定に使う項目と行の形だけを残し、本文と作業フォルダを置き換えて `tests/fixtures/claude_code/` に置く(種類ごとに1行以上: 依頼文・ツールの結果・補助の印・要約・ヘッドレス・サブエージェント)
- テスト: 既存の作業の記録の取り込み-3 の契約(正常と失敗形3つ)、社外へ送るもの-1 のうち伏せ字

</details>

### 6. 議事録の控えから題名と要約を読む処理を作る 【担当: claude】

その週の会議の要点を、作業の要約の材料に加える。

<details><summary>詳細を開く</summary>

- `routine_work_finder/report/sources_minutes.py`。ファイル名の日時で週を絞り、「要約」の見出しの先頭500字を取る
- fixture: 実際の控えの見出しの並びとファイル名の形を残し、本文を置き換えて `tests/fixtures/minutes/` に置く
- テスト: 既存の作業の記録の取り込み-4 の契約(正常・要約の見出しが無い・日時が読めない)、-5(1つが失敗しても残りで作る)

</details>

## Claude による自動化案と作業の要約

### 7. Claude に渡す材料を送ってよいものだけで字数の上限内に組み立てる処理と、既存の仕組みの一覧を作る 【担当: claude】

社外へ送るものを絞ったうえで、1回の呼び出しに収まる材料を作る。

<details><summary>詳細を開く</summary>

- `routine_work_finder/report/materials.py`。材料の形は appendix.md「Claude に渡す材料の形」。手順は design.md「Claude に自動化案と作業の要約を作らせる」1〜4・7
- 既存の仕組みの一覧: `~/.claude/skills/*/SKILL.md` の冒頭の名前と説明、study の各アプリの architecture.md の概要の1段落目
- テスト: 作業の要約-6、社外へ送るもの-1(項目の種類の突き合わせ)、-2、自動化案-4、120,000字を超えたときの減らし方(半分ずつ・500字で候補を減らす)

</details>

### 8. 自動化案と作業の要約の指示文を書き、claude -p の呼び出し・応答の検査・3回までの呼び直しを作る 【担当: claude】

Claude の応答を検査を通ったものだけ使い、失敗が続いたら時間の集計だけでレポートを出せるようにする。

<details><summary>詳細を開く</summary>

- `routine_work_finder/report/prompts/`(骨子は appendix.md「指示文の骨子」)と `claude_calls.py`。`~/.claude/lib/claude_headless.py` の `run_headless` を600秒の打ち切りで使う
- 応答の検査は design.md「バリデーション」と appendix.md「Claude の応答の形」。並べ替えと5件までの絞り込み、作業の要約から自動化案へのリンク
- テストは `run_headless` を偽物に差し替えて書く
- テスト: 自動化案-2、-3 の構造検証、-5、-8(2回失敗のあと成功・3回失敗・要約側の3回失敗で両方出さない)、作業の要約-1・-3・-5 の構造検証、-4、自動化案を作る条件-1

</details>

## HTML と配信

### 9. 週次レポートのHTMLのひな形と流し込みを作る(4つの状態と依頼文のコピー) 【担当: claude】

モックと同じ並びのレポートを、どの状態の週でも崩れずに出せるようにする。

<details><summary>詳細を開く</summary>

- `routine_work_finder/templates/report.html` と `report/render_html.py`。配置と見た目は `specs/weekly-automation-report/mock.html` に合わせる(モック用の操作の欄は持たない)
- コピーの3段構えは会議設定の自動化の `templates/select.html` の `copySelection()` と同じ形にする。依頼文の形は appendix.md
- テスト: バックログに積む依頼文-1(script を取り出して `node --check`、1件以上あること、ボタンの無効の初期状態)、-2、-4(手で選ぶ欄、コピーの関数を壊すと落ちる)、自動化案-6、-7、レポートの作成と通知-6、エスケープ(題名に `</script>` を入れても壊れない)

</details>

### 10. HTML をローカルの控えと OneDrive に保存し、Teams に通知する処理を作る 【担当: claude】

launchd から OneDrive へ確実に書き、開けるリンクを Teams で届ける。

<details><summary>詳細を開く</summary>

- `report/onedrive_write.py`(teams-transcript-fetcher の `materialize.py` の実体化の許可と、read-aloud-player の読んで書く複製の写し。写した元をコメントに書く)と `report/publish.py`
- ビューア形式のリンクは `build_viewer_url` と同じ形。通知の本文は appendix.md「Teams の通知の本文」
- 保存の失敗は10秒あけて3回まで。それでも失敗したら控えの場所を通知する
- テスト: レポートの作成と通知-3 の週の名前(年をまたぐ週)、-4 の構造検証(HTML 断片のタグの対応とエスケープ)、保存の書き直しと失敗の通知

</details>

## 組み上げ

### 11. 対象の週の決定・二重作成の防止・ロック・作り直しの依頼の処理で週次レポート係を組み上げる 【担当: claude】

定期の起動と作り直しの依頼を、同じ手順で重ならずに処理できるようにする。

<details><summary>詳細を開く</summary>

- `report/run_report.py`。手順は design.md「週次レポートを作って届ける」「作り直しの依頼を受けて作り直す」4〜6。状態のファイルと依頼ファイルの形は appendix.md
- ロックは2時間より古いものを捨てる。思わぬ例外は Teams に知らせ、ロックを必ず外す
- ログは appendix.md「ログの書式」
- テスト: レポートの作成と通知-1(金曜16:59・17:00・翌月曜)、-5、レポートの作り直し-1、同じ週を二度作らない、ロックが取れないときに何もしない、既存の作業の記録の取り込み-5

</details>

### 12. 操作スクリプトと記録の操作Skillに作り直しの依頼を足す 【担当: claude】

チャットで「定型業務レポートを作り直して」と頼めるようにする。

<details><summary>詳細を開く</summary>

- `routine_work_finder/control.py` の `remake` と `~/.claude/skills/routine-work-finder/SKILL.md` の作り直しの頼み方(Write/Edit ツールで書く)
- 手順は design.md「作り直しの依頼を受けて作り直す」1〜3
- テスト: レポートの作り直し-2(週の指定なし・作った週が無い)、-3(27日前・28日前・29日前・記録のファイルが無い)

</details>

### 13. 週次レポート係の launchd の設定ファイルを作り、automation.json に通知のトリガーを足す 【担当: claude】

金曜17時と作り直しの依頼で起動し、通知が自分宛てに届くようにする。

<details><summary>詳細を開く</summary>

- `launchd/com.example.routine-work-finder-report.plist`(形は appendix.md)
- `~/.claude/config/automation.json` の `triggers` に `routine-work-finder` を、既存のトリガーと同じ形で足す(git 管理外。書き換える前に今の内容を読み、利用者に差分を見せる)
- テスト: レポートを出す時刻-1 の構造検証(plistlib で読め、金曜17時と依頼のフォルダの監視があり、Python が `Versions/Current` を指す)

</details>

### 14. 1週間分の規模で所要時間と Claude の呼び出し回数を確かめる性能テストを作る 【担当: claude】

30分以内・10回以下の約束を、毎回同じ値になる量で確かめる。

<details><summary>詳細を開く</summary>

- `tests/perf/`。Claude を偽物に差し替え、6万行・本文1,500件の fixture を作って回す
- 非機能-1: 集計・材料の組み立て・HTML の作成が15分以下(実際は数秒の見込み)
- 非機能-2: 成功時の呼び出し回数が2回

</details>

### 15. README に週次レポート係を足し、Skill のカタログ(Confluence)に記録の操作Skillを載せる 【担当: claude】

週次レポート係の登録・解除と、新しい Skill の存在を後から辿れるようにする。

<details><summary>詳細を開く</summary>

- `apps/routine-work-finder/README.md` に、週次レポート係の launchd への登録・解除・手で1回動かすコマンド・ログを足す
- Skill のカタログ(dxgarage の個人 Confluence、pageId 2480930855)に `routine-work-finder` の行を足し、冒頭の件数と日付を直す(`~/.claude/skill-authoring.md`)。保存の直前にページを取り直す

</details>

### 16. launchd から週次レポートを1回作り、環境スモークと初回の実データの確認をする 【担当: claude】

本番と同じ起動経路でレポートが届き、ビューアからコピーできることを確かめてから完了にする。

<details><summary>詳細を開く</summary>

- 利用者に、手元のターミナルで週次レポート係を launchd に登録してもらい、記録が5時間以上ある週で作り直しを頼む(依頼のフォルダの変化で起動する)
- 確かめること: 自動化案-3(launchd から `claude -p` が呼べ検査を通る)、レポートの作成と通知-3・-4、バックログに積む依頼文-3(ビューア形式で開いてコピー)
- レポートの作成と通知-2: 金曜17時をスリープ中に過ごし、起きたあとにその週が作られることを次の金曜に確かめる
- 非機能-1: ログの全体の所要秒数が1,800以下
- 下の確認チェックリストを埋める

</details>

## 確認チェックリスト

- [ ] 本番と同じ経路(launchd の金曜17時と依頼のフォルダの監視、`claude -p`)で起動する → 結果
- [ ] 成果物(OneDrive のHTML・Teams の通知)が出る → 結果
- [ ] 失敗させたとき(Claude を3回失敗させる・OneDrive に書けなくする)の通知とログが届く → 結果
