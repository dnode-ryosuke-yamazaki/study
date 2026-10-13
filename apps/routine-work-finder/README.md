# routine-work-finder

自分の定型業務を洗い出す材料として、このMacでどのアプリを何にどれだけ使ったかを、チャットで決めた終わりの日時まで記録する。記録係(Swift の常駐プログラム)が5秒ごとに、前面のアプリと周りの状態、前面ウィンドウの題名(Excel はシート名も)・カーソルのある部品の種類を1行ずつ残す。画面の撮影・キー入力の中身・画面の中の文字は記録しない。

- 全体像・機能マップ: [specs/architecture.md](specs/architecture.md)
- 仕様: [specs/activity-recording/](specs/activity-recording/)(操作の記録)・[specs/weekly-automation-report/](specs/weekly-automation-report/)(週次レポート。未実装)
- チャット向けの手順(SKILL.md): `~/.claude/skills/routine-work-finder/SKILL.md`(このリポジトリの外。処理はここの `application/` を絶対パスで呼ぶ)

## 前提条件 / 権限

| 項目 | 内容 |
|---|---|
| 実行環境 | macOS 14 以降。Command Line Tools(Swift 6 系。Xcode は不要)。Python 3.11 以降(標準ライブラリのみ。追加ライブラリなし) |
| 署名の証明書 | ログインキーチェーンの自己署名の証明書 `routine-work-finder code signing`(コード署名)。管理者権限は要らない(下記セットアップ1) |
| アクセシビリティ | 記録係(`~/Library/Application Support/routine-work-finder/bin/rwf-recorder`)を「システム設定 → プライバシーとセキュリティ → アクセシビリティ」の一覧に追加してオンにする。題名・シート名・部品の種類を読むために使う |
| 画面収録 | **使わない**。一覧に追加しない |
| 常駐 | 記録係は launchd(`com.example.routine-work-finder-recorder`)でログイン時に起動し、落ちたら起動し直す。終わりの日時が無い・過ぎた間は何も記録せず、状態のファイルだけを書き直して待つ |
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

記録しないアプリの初期値は、macOS の「パスワード」・キーチェーンアクセス・システム設定の3つ。チャットのセッションによっては Bash からデータフォルダに書けないことがあり、その場合 Skill は同じ操作を手元のターミナルで実行するコマンドを渡す。

操作スクリプトの呼び方と結果の形は [specs/activity-recording/appendix.md](specs/activity-recording/appendix.md) の「操作スクリプトの呼び方」。

## 解除

1. チャットで「記録を止めて」と頼む
2. launchd から外す

   ```
   launchctl bootout gui/$(id -u)/com.example.routine-work-finder-recorder
   ```

3. 自動起動もやめるなら、`~/Library/LaunchAgents/com.example.routine-work-finder-recorder.plist` を消す
4. アクセシビリティの一覧から `rwf-recorder` を外す
5. 記録・メモも消すなら、データフォルダ `~/Library/Application Support/routine-work-finder/` を消す(**元に戻せない**。週次レポートの作り直しにも使えなくなる)
6. 証明書が要らなくなったら、キーチェーンアクセスで `routine-work-finder code signing` を消す

**会社のセキュリティ監視に検知された場合**(監視の担当から連絡が来た・警告が出た)は、その場で 1 と 2 を行い、以降の利用を止める。

## ログ

| ファイル | 中身 |
|---|---|
| `~/Library/Logs/routine-work-finder-recorder.log` | 記録係のログ(launchd の標準出力・標準エラー)。記録の開始・停止、設定が読めない理由、題名が取れない理由(変わったときだけ)、古い記録の削除の件数、書き込みの失敗 |
| `~/Library/Application Support/routine-work-finder/control.log` | 操作スクリプトのログ。開始・停止・除外の追加と削除(件数だけ)・メモの追加と削除 |
| `~/Library/Application Support/routine-work-finder/recorder-status.json` | 記録係が5秒ごとに書き直す状態(最後に動いた日時・記録中か・1回の所要ミリ秒・設定が読めなかった理由・最後の書き込みエラー・アクセシビリティの許可) |

どのログにも、題名・シート名・メモの文・記録しないことば・アプリ名は書かない。
