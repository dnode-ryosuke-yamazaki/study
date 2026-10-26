# routine-work-finder

自分の定型業務を洗い出す材料として、このMacでどのアプリを何にどれだけ使ったかを、チャットで決めた終わりの日時まで記録する。記録係(Swift の常駐プログラム)が5秒ごとに、前面のアプリと周りの状態、前面ウィンドウの題名(Excel はシート名も)・カーソルのある部品の種類を1行ずつ残す。画面の撮影・キー入力の中身・画面の中の文字は記録しない。

週次レポート係(Python)が毎週金曜17時を過ぎると、その週の記録と既存の作業の記録(JIRA・Confluence の自分の更新、Claude Code の依頼文、会議の議事録)・メモから、時間の使い方と自動化案・記録しない候補を載せた週次レポートのHTMLを作り、OneDrive に置いて Teams で知らせる。チャットで頼めば作り直す。

- 全体像・機能マップ: [specs/architecture.md](specs/architecture.md)
- 仕様: [specs/activity-recording/](specs/activity-recording/)(操作の記録)・[specs/weekly-automation-report/](specs/weekly-automation-report/)(週次レポート)
- チャット向けの手順(SKILL.md): `~/.claude/skills/routine-work-finder/SKILL.md`(このリポジトリの外。処理はここの `application/` を絶対パスで呼ぶ)

## 前提条件 / 権限

| 項目 | 内容 |
|---|---|
| 実行環境 | macOS 14 以降。Command Line Tools(Swift 6 系。Xcode は不要)。Python 3.11 以降(標準ライブラリのみ。追加ライブラリなし) |
| 署名の証明書 | ログインキーチェーンの自己署名の証明書 `routine-work-finder code signing`(コード署名)。管理者権限は要らない(下記セットアップ1) |
| アクセシビリティ | 記録係(`~/Library/Application Support/routine-work-finder/bin/rwf-recorder`)を「システム設定 → プライバシーとセキュリティ → アクセシビリティ」の一覧に追加してオンにする。題名・シート名・部品の種類を読むために使う |
| 画面収録 | **使わない**。一覧に追加しない |
| 常駐 | 記録係は launchd(`com.example.routine-work-finder-recorder`)でログイン時に起動し、落ちたら起動し直す。終わりの日時が無い・過ぎた間は何も記録せず、状態のファイルだけを書き直して待つ |
| 週次レポート係 | launchd(`com.example.routine-work-finder-report`)で毎週金曜17時と、作り直しの依頼のフォルダ(データフォルダの `requests/`)に依頼ファイルが置かれたときに起動する。金曜17時をスリープ中に過ごしても、次に起動したときにその週を作る。`claude -p`・PJプロファイル(`~/.claude/config/project-profiles.json`)・Teams 通知(`~/.claude/config/automation.json` の `routine-work-finder`)を使う |
| 使ってよい期間 | クライアント業務に就いていない期間だけ。終わりの日時を決めない記録は始めない |

データフォルダは `~/Library/Application Support/routine-work-finder/`(権限700、ファイルは600)。同期フォルダ(OneDrive・iCloud など)には置かない。記録・メモは28日を過ぎると記録係が自動で消す。

## 開発コマンド

記録係(Swift):

```
cd application/recorder
/bin/zsh scripts/swift_test.sh
```

- `swift test` を、Swift Testing のマクロ部品の場所を明示して呼ぶ。Command Line Tools の `swift test` はマクロ部品の場所を渡し忘れて不定期にビルドが失敗するため、直接 `swift test` は使わない
- 性能テスト(毎回は回さない。全体の動作確認と PR 作成前に回す): `/bin/zsh scripts/swift_test.sh --filter RecorderCorePerfTests`
- Claude Code のサンドボックスでは `swift build` / `swift test` が動かない。その中では `/bin/zsh scripts/swiftc_test.sh`(性能テストは `--perf`)で、`swiftc` で直接コンパイルして同じテストを回す

操作スクリプト(Python)と構造検証(記録係のソースの走査・launchd の設定ファイルの検査):

```
cd application
python3 -m unittest discover -s tests -t .
```

週次レポート係の性能テスト(毎回は回さない。全体の動作確認と PR 作成前に回す。Claude・Teams・OneDrive は偽物で、6万行の1週分を作る):

```
cd application
python3 -m unittest discover -s tests/perf
```

テストや手元の試しで実物のデータフォルダに触れないよう、環境変数 `RWF_DATA_DIR` でデータフォルダを差し替えられる(例: `RWF_DATA_DIR=/tmp/rwf-test python3 -m routine_work_finder.control status`)。lint・build のコマンドは未整備。

## セットアップ

### 1. 署名の証明書を作る(1回だけ)

キーチェーンアクセスを開き、メニュー「キーチェーンアクセス → 証明書アシスタント → 証明書を作成…」で次のとおり作る。

- 名前: `routine-work-finder code signing`
- 固有名の種類: 自己署名ルート
- 証明書のタイプ: コード署名

### 2. 記録係をビルドして署名し、置く

```
cd /Users/ryosyamazaki/repo/study/apps/routine-work-finder/application
/bin/bash scripts/install_recorder.sh
```

記録係を `~/Library/Application Support/routine-work-finder/bin/rwf-recorder` に置いて署名を確かめ、launchd の設定ファイルを `~/Library/LaunchAgents/com.example.routine-work-finder-recorder.plist` に置く。

### 3. アクセシビリティの一覧でオンにする(1回だけ)

「システム設定 → プライバシーとセキュリティ → アクセシビリティ」で「+」を押し、Cmd+Shift+G で `~/Library/Application Support/routine-work-finder/bin/rwf-recorder` を指定して追加し、オンにする。

一覧への追加とオンは本人の権限で行える。一方、オンにした記録係をオフにする・一覧から外すには、このMacでは管理者権限を求められる(本人では行えない)。記録を止めたいときは、下記「解除」の 1・2(記録を止める・launchd から外す)で止まる。

### 4. launchd に登録する

```
launchctl bootout gui/$(id -u)/com.example.routine-work-finder-recorder
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.routine-work-finder-recorder.plist
```

1行目は登録し直すとき用で、初回は `No such process` と出るが問題ない。

### 5. 動いていることを確かめる

チャットで「記録の状態は?」と聞くか、次を実行する。`recorderRunning` と `accessibilityGranted` が `true` なら準備ができている。

```
cd /Users/ryosyamazaki/repo/study/apps/routine-work-finder/application
python3 -m routine_work_finder.control status
```

### 作り直したとき

手順2と4だけをやり直す。同じ証明書・同じ識別子で署名し直すので、**アクセシビリティの一覧は触らなくてよい**(許可が残る)。

### 6. 週次レポート係を launchd に登録する

```
cd /Users/ryosyamazaki/repo/study/apps/routine-work-finder/application
mkdir -p ~/Library/LaunchAgents
sed "s|__HOME__|$HOME|g" launchd/com.example.routine-work-finder-report.plist > ~/Library/LaunchAgents/com.example.routine-work-finder-report.plist
plutil -lint ~/Library/LaunchAgents/com.example.routine-work-finder-report.plist
launchctl bootout gui/$(id -u)/com.example.routine-work-finder-report
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.routine-work-finder-report.plist
```

`bootout` の行は登録し直すとき用で、初回は `No such process` と出るが問題ない。登録しただけでは起動しない(金曜17時か作り直しの依頼で起動する)。

手で1回動かすときは、チャットで「定型業務レポートを作り直して」と頼むか、次を実行する(対象の週を決めて依頼ファイルを置き、launchd が拾って作る)。

```
cd /Users/ryosyamazaki/repo/study/apps/routine-work-finder/application
python3 -m routine_work_finder.control remake --week last
```

## 使い方

チャットで頼む(記録の操作Skill)。

| 頼み方の例 | すること |
|---|---|
| 「10月31日18時まで記録して」 | 終わりの日時を決めて記録を始める(記録中に頼むと終わりの日時を置き換える) |
| 「記録を止めて」 | 終わりの日時より前でも止める |
| 「記録の状態は?」 | 記録中か・終わりの日時・今日の記録時間・直近で記録が取れなかった時間帯・記録係が動いているか・許可があるか |
| 「1Password を記録しないアプリに足して」「『給与』を記録しないことばに足して」 | 次の記録から外す(過去の記録は書き換えない) |
| 「記録しないものの一覧を見せて」 | 今の一覧 |
| 「メモ: 勤怠メールを毎回手で移している」「今週のメモを見せて」 | 面倒だった作業のメモ |
| 「定型業務レポートを作り直して」「先週の定型業務レポートを作り直して」「2026-W41 の定型業務レポートを作り直して」 | 週次レポートを作り直す(週の指定は「今週」「先週」「最新の週」か `YYYY-Www`。指定なしは金曜17時を過ぎた最新の週)。記録が残っている28日以内の週だけ |
| 「マイクを会議とみなさないで」「マイクを会議とみなして」「マイクの設定は?」 | 週次レポートでマイクが使用中の時間を会議として数えるかを切り替える・確かめる(既定は会議とみなす)。次に作るレポートから効き、作り直せば記録が残っている過去の週にも効く。記録係のマイクの記録は変わらない |
| 週次レポートの「記録しない候補」でコピーした依頼文を貼る | 選んだ候補を記録しないものに足す |

マイクの設定は、手元のターミナルでは次のように切り替える(操作の記録の設定ファイルの `micAsMeeting` に書く)。

```
cd /Users/ryosyamazaki/repo/study/apps/routine-work-finder/application
python3 -m routine_work_finder.control mic-meeting off
python3 -m routine_work_finder.control mic-meeting on
python3 -m routine_work_finder.control mic-meeting show
```

記録しないアプリの初期値は、macOS の「パスワード」・キーチェーンアクセス・システム設定の3つ。チャットのセッションによっては Bash からデータフォルダに書けないことがあり、その場合 Skill は同じ操作を手元のターミナルで実行するコマンドを渡す。

記録している間は、ログアウトしない・アクセシビリティの許可を外さない。この2つをしたときの動き(ログインし直したあとの再開・許可が無いことの表示)は実機で確かめていない。ログアウトしたあとは、チャットで「記録の状態は?」と聞いて、記録係が動いているかを確かめる。

週次レポートは OneDrive の `00_root/auto/routineWorkFinder/<週の名前>.html` に置き、Teams(スプリントレポート)にブラウザで開けるリンクを送る。データフォルダの `reports/` にも控えを残す。

操作スクリプトの呼び方と結果の形は [specs/activity-recording/appendix.md](specs/activity-recording/appendix.md) の「操作スクリプトの呼び方」、作り直し(`remake`)・マイクの設定(`mic-meeting`)と週次レポート係のファイルの形は [specs/weekly-automation-report/appendix.md](specs/weekly-automation-report/appendix.md)。

## 解除

1. チャットで「記録を止めて」と頼む
2. launchd から外す

   ```
   launchctl bootout gui/$(id -u)/com.example.routine-work-finder-recorder
   launchctl bootout gui/$(id -u)/com.example.routine-work-finder-report
   ```

3. 自動起動もやめるなら、`~/Library/LaunchAgents/com.example.routine-work-finder-recorder.plist` と `~/Library/LaunchAgents/com.example.routine-work-finder-report.plist` を消す。週次レポートの通知もやめるなら `~/.claude/config/automation.json` の `routine-work-finder` と、ヘルスチェックの宣言(`~/.claude/config/automation-health-check.json`)の `com.example.routine-work-finder-report` も外す
4. アクセシビリティの一覧から `rwf-recorder` を外す(管理者権限を求められる。本人で行えなければ外さなくてよい。記録係は 2 で止まっている)
5. 記録・メモも消すなら、データフォルダ `~/Library/Application Support/routine-work-finder/` を消す(**元に戻せない**。週次レポートの作り直しにも使えなくなる)
6. 証明書が要らなくなったら、キーチェーンアクセスで `routine-work-finder code signing` を消す

**会社のセキュリティ監視に検知された場合**(監視の担当から連絡が来た・警告が出た)は、その場で 1 と 2 を行い、以降の利用を止める。

## ログ

| ファイル | 中身 |
|---|---|
| `~/Library/Logs/routine-work-finder-recorder.log` | 記録係のログ(launchd の標準出力・標準エラー)。記録の開始・停止、設定が読めない理由、題名が取れない理由(変わったときだけ)、古い記録の削除の件数、書き込みの失敗 |
| `~/Library/Application Support/routine-work-finder/control.log` | 操作スクリプトのログ。開始・停止・除外の追加と削除(件数だけ)・メモの追加と削除 |
| `~/Library/Logs/routine-work-finder-report.log` | 週次レポート係のログ。起動の契機と週、読んだ行数と4区分の時間、読めなかった記録とその理由、Claude の呼び出しごとの成否・秒数・字数、保存と通知の結果、全体の所要秒数(`done seconds=`) |
| `~/Library/Application Support/routine-work-finder/report-state.json` | 週次レポート係の状態。定期の作成で作った週と結果(`generated`・`insufficient`・`claudeFailed`・`saveFailed`・`failed`・`noRecords`)・通知できたか。作り直しは書かない |
| `~/Library/Application Support/routine-work-finder/reports/` | 週次レポートのHTMLの控え(1週1ファイル。自動では消さない) |
| `~/Library/Application Support/routine-work-finder/recorder-status.json` | 記録係が5秒ごとに書き直す状態(最後に動いた日時・記録中か・1回の所要ミリ秒・設定が読めなかった理由・最後の書き込みエラー・アクセシビリティの許可) |

どのログにも、題名・シート名・メモの文・記録しないことば・アプリ名・依頼文・Claude の応答の中身は書かない。
