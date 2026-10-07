# 操作の記録 付録

design.md の処理フローが使う書式だけを置く。手順・分岐は design.md が正。

## データフォルダの構成

```
~/Library/Application Support/routine-work-finder/      # 権限 700
├── bin/rwf-recorder           # 署名した記録係(launchd が起動する)
├── config.json                # 設定ファイル(操作スクリプトが書き、記録係が読む)
├── recorder-status.json       # 状態のファイル(記録係が5秒ごとに書き直す)
├── control.log                # 操作スクリプトのログ
├── records/<YYYY-MM-DD>.jsonl # 操作の記録(1行1回)
└── memos/<YYYY-MM-DD>.jsonl   # 面倒だった作業のメモ(1行1件)
```

- 同じフォルダに週次レポート係のファイル(`report-state.json`・`report.lock/`・`reports/`・`requests/`)も置かれる。形は [週次レポートの付録](../weekly-automation-report/appendix.md) の「週次レポート係が使うファイル」
- ファイルの権限: 600
- 日付は日本時間の日付。削除の対象はファイル名が `^\d{4}-\d{2}-\d{2}\.jsonl$` に合うものだけ
- 設定ファイルの書き換え: 同じフォルダの `config.json.tmp` に書いてから `config.json` へ名前を付け替える

## 設定ファイルの形

`config.json`

```json
{
  "version": 1,
  "endsAt": "2026-10-31T18:00:00+09:00",
  "stoppedAt": null,
  "excludedApps": [
    { "name": "パスワード", "bundleId": "com.apple.Passwords" },
    { "name": "キーチェーンアクセス", "bundleId": "com.apple.keychainaccess" },
    { "name": "システム設定", "bundleId": "com.apple.systempreferences" }
  ],
  "excludedTitleWords": []
}
```

- `endsAt`: 終わりの日時。止めたとき・未設定は `null`
- `stoppedAt`: 「記録を止めて」で止めた日時。始めたときに `null` に戻す。必須の項目ではなく、欠けていたら `null` とみなす
- `excludedApps[].bundleId`: 分からないときは `null`
- `excludedTitleWords`: 題名に含まれると除外することばの一覧(例: `["給与", "人事"]`)
- 必須の項目: `version`・`endsAt`・`excludedApps`・`excludedTitleWords`。欠け・型違いは記録しない側に倒す

## 状態のファイルの形

`recorder-status.json`

```json
{
  "version": 1,
  "updatedAt": "2026-10-06T10:15:05+09:00",
  "recording": true,
  "tickMillis": 42,
  "configError": null,
  "lastWriteError": null,
  "accessibilityGranted": true,
  "lastPurgeDate": "2026-10-06"
}
```

- `accessibilityGranted`: `AXIsProcessTrusted()` の値。false なら状態の確認で許可の案内を返す
- `configError`: 設定ファイルが読めなかったときの理由(例: `"invalidJson"` / `"missingField:endsAt"`)。読めた回は `null`
- 記録係が動いていないとみなす条件: `updatedAt` が今より30秒以上前

## 操作の記録の行の形

`records/<YYYY-MM-DD>.jsonl`。1行に1つの JSON。

通常の行:

```json
{"t":"2026-10-06T10:15:05+09:00","kind":"sample","app":"Microsoft Excel","bundleId":"com.microsoft.Excel","monitor":2,"idleSec":1.4,"locked":false,"mic":false,"displaySleepPrevented":false,"title":"見積_2026.xlsx","sheet":"集計","focusRole":"AXLayoutArea"}
```

- `title`: 前面ウィンドウの題名(先頭1,000字まで)
- `sheet`: Excel の選択シート名。無ければ項目を書かない
- `focusRole`: カーソルのある部品の role。subrole があれば `focusSubrole` も書く。取れなければ書かない
- `titleTruncated`: 題名が1,000字を超えて切り詰めたとき `true`
- 題名が取れなかったとき: `title` は書かず、行の一番上の項目として `"titleUnavailable": true` と `"titleReason": "<理由>"` を持つ。理由は下の「エラーの理由」の `noWindow` / `denied` / `timeout`。停止の行の `reason` とは別の名前にする

題名が取れなかった行:

```json
{"t":"2026-10-06T10:15:15+09:00","kind":"sample","app":"Microsoft Teams","bundleId":"com.microsoft.teams2","monitor":1,"idleSec":3.0,"locked":false,"mic":false,"displaySleepPrevented":false,"titleUnavailable":true,"titleReason":"timeout"}
```

除外中の行(アプリ名も題名も書かない):

```json
{"t":"2026-10-06T10:15:10+09:00","kind":"excluded"}
```

開始・停止の行:

```json
{"t":"2026-10-06T09:00:00+09:00","kind":"start"}
{"t":"2026-10-31T18:00:00+09:00","kind":"stop","reason":"endsAtPassed"}
```

- `stop` の `reason`: `endsAtPassed`(終わりの日時を過ぎた)/ `stopRequested`(止める依頼)/ `endsAtMissing`(`endsAt` と `stoppedAt` がどちらも `null`、または設定ファイルが無い)
- 停止の行は、記録のファイルの最後の行が停止の行でなく、今は記録しない状態(終わりの日時を過ぎた・止めた・終わりの日時が無い)の回に1回だけ書く。最後の行がすでに停止の行なら書かない
- 停止の行の `t`: `endsAtPassed` は「最後の行の時刻」と `endsAt` の遅い方、`stopRequested` は「最後の行の時刻」と `stoppedAt` の遅い方、`endsAtMissing` はその回の時刻(寄せる先の日時が無いため)。その時刻の日本時間の日付のファイルに書き足す
- 設定ファイルが読めない回は停止の行も通常の行も書かない。理由は状態のファイルの `configError` に書く
- 設定ファイルが無い回は「終わりの日時が無い」として扱い、`configError` は `null` にする(停止の行の条件に当たれば `endsAtMissing` の停止の行を書く)
- 周りの状態が取れなかった項目は `null`
- 読む側は、知らない `kind`・知らない項目を読み飛ばす。最終行が書きかけ(JSON として読めない)の場合も読み飛ばす
- 範囲を区切って読む側(`records.py`)は、範囲の直前の行(範囲より前のファイルの最後に読める行)で、範囲の始まりが記録している期間の内か外かを決める。直前の行が停止の行、または28日の保持で直前の行が無い場合は期間の外とする。期間の内で、直前の行から範囲内の最初の行までが30秒以上空いている場合は、範囲の始まりから最初の行までを記録が取れなかった時間とする。範囲の終わりは、範囲の最後の行が記録している期間の内(停止の行でない)で、範囲の終わりまで30秒以上空いている場合に、最後の行から範囲の終わりまでを記録が取れなかった時間とする。範囲の後の行は見ない

## メモのファイルの形

`memos/<YYYY-MM-DD>.jsonl`

```json
{"id":"20261006-101530-a1b2","t":"2026-10-06T10:15:30+09:00","text":"勤怠の通知メールを毎回手でフォルダに移している"}
```

- `id`: `<年月日>-<時分秒>-<16進4桁>`。形は `^\d{8}-\d{6}-[0-9a-f]{4}$`

## アクセシビリティの読み方

記録係が `AXUIElement` の属性を読む。他アプリを操作する命令(Apple Events)は送らない。前面ウィンドウの中は深く走査せず、下の属性だけを読む。

| 取るもの | 読み方 |
|---|---|
| 前面ウィンドウ | 前面アプリの pid から `AXUIElementCreateApplication` → `kAXFocusedWindowAttribute` |
| ウィンドウの題名 | 前面ウィンドウの `kAXTitleAttribute` |
| カーソルの部品の種類 | アプリ要素の `kAXFocusedUIElementAttribute` → `kAXRoleAttribute`(あれば `kAXSubroleAttribute`) |
| Excel のシート名 | 前面ウィンドウの `kAXChildrenAttribute` で子を取り、先頭40個までの `kAXRoleAttribute` から role が `AXTabGroup` のものを探し、`kAXTabsAttribute` の中で `kAXValueAttribute` が真のタブの `kAXTitleAttribute` |

- 読む属性は上の表の8つ(`kAXFocusedWindowAttribute`・`kAXTitleAttribute`・`kAXFocusedUIElementAttribute`・`kAXRoleAttribute`・`kAXSubroleAttribute`・`kAXChildrenAttribute`・`kAXTabsAttribute`・`kAXValueAttribute`)だけ。記録係のソースの構造検証はこの8つを許可リストにする
- `kAXSelectedTextAttribute` など、部品の中の文字を返す属性は読まない。`kAXValueAttribute` は、タブ群の中のタブが選ばれているか(真偽)を見る1か所だけで読み、入力欄・表など文字を持つ部品には読まない
- 1回の記録で上の問い合わせを合わせて1秒で打ち切る

## エラーの理由

題名が取れなかった行の `titleReason` に入れる値。

| 状況 | titleReason |
|---|---|
| 前面ウィンドウが取れない | `noWindow` |
| `AXIsProcessTrusted()` が false | `denied` |
| 1秒で終わらない | `timeout` |

## 周りの状態の取り方

| 項目 | 取り方 |
|---|---|
| 前面のアプリ | `NSWorkspace.shared.frontmostApplication` の `localizedName`・`bundleIdentifier` |
| モニター | `NSEvent.mouseLocation` を含む `NSScreen.screens` の位置(1から数える) |
| 入力からの秒数 | `CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: 全種類)` |
| 画面ロック | `CGSessionCopyCurrentDictionary()` の `CGSSessionScreenIsLocked` |
| マイク | 既定の入力デバイスの `kAudioDevicePropertyDeviceIsRunningSomewhere` |
| スリープの抑止 | `IOPMCopyAssertionsStatus` の `PreventUserIdleDisplaySleep` が1以上 |

## 署名と配置のコマンドの雛形

証明書は1回だけ、キーチェーンアクセスの「証明書アシスタント → 証明書を作成」で作る。

- 名前: `routine-work-finder code signing`
- 固有名の種類: 自己署名ルート
- 証明書のタイプ: コード署名

`install_recorder.sh` が行うこと:

```bash
cd /Users/ryosyamazaki/repo/study/apps/routine-work-finder/application/recorder
swift build -c release
mkdir -p "$HOME/Library/Application Support/routine-work-finder/bin"
cp .build/release/rwf-recorder "$HOME/Library/Application Support/routine-work-finder/bin/rwf-recorder"
codesign --force --sign "routine-work-finder code signing" --identifier com.example.routine-work-finder.recorder "$HOME/Library/Application Support/routine-work-finder/bin/rwf-recorder"
codesign --verify --verbose "$HOME/Library/Application Support/routine-work-finder/bin/rwf-recorder"
```

- スクリプトの変数名は ASCII だけにする(launchd から動く /bin/bash 3.2 の制約に合わせる)
- 署名のあと、システム設定の「プライバシーとセキュリティ → アクセシビリティ」の一覧に記録係(`bin/rwf-recorder`)を追加してオンにする(手元で行う)。署名していれば、作り直しても一覧の許可が残る見込み
- 続けて launchd のジョブを `launchctl bootout` → `bootstrap` で入れ直す(手元のターミナルで実行する)

## launchd の設定ファイルの形

`com.example.routine-work-finder-recorder.plist`。`__HOME__` はセットアップ時にホームディレクトリへ置き換える。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.example.routine-work-finder-recorder</string>
  <key>ProgramArguments</key>
  <array>
    <string>__HOME__/Library/Application Support/routine-work-finder/bin/rwf-recorder</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ProcessType</key>
  <string>Background</string>
  <key>StandardOutPath</key>
  <string>__HOME__/Library/Logs/routine-work-finder-recorder.log</string>
  <key>StandardErrorPath</key>
  <string>__HOME__/Library/Logs/routine-work-finder-recorder.log</string>
</dict>
</plist>
```

## 操作スクリプトの呼び方

Skill が呼ぶ形。結果は標準出力に JSON で返す。

```bash
cd /Users/ryosyamazaki/repo/study/apps/routine-work-finder/application
python3 -m routine_work_finder.control start --until 2026-10-31T18:00:00+09:00
python3 -m routine_work_finder.control stop
python3 -m routine_work_finder.control status
python3 -m routine_work_finder.control exclude-app add --input-file "$TMPDIR/rwf-input-20261009-174012.json"
python3 -m routine_work_finder.control exclude-app remove --input-file "$TMPDIR/rwf-input-20261009-174013.json"
python3 -m routine_work_finder.control exclude-word add --input-file "$TMPDIR/rwf-input-20261009-174014.json"
python3 -m routine_work_finder.control exclude-word remove --input-file "$TMPDIR/rwf-input-20261009-174015.json"
python3 -m routine_work_finder.control exclude-list
python3 -m routine_work_finder.control exclude-add --request-file "$TMPDIR/rwf-request-20261009-174016.txt" --bundle-ids-file "$TMPDIR/rwf-input-20261009-174016.json"
python3 -m routine_work_finder.control memo add --input-file "$TMPDIR/rwf-input-20261009-174017.json"
python3 -m routine_work_finder.control memo list
python3 -m routine_work_finder.control memo delete --id 20261006-101530-a1b2
```

入力ファイルの決まり:

- 自由に書かれた文(依頼文・メモの文・ことば・アプリ名)は、どれもシェルのコマンド文字列に入れない。Skill は Bash で `echo $TMPDIR` などで実際の値を確かめ、Write ツールにその絶対パスを渡して、ユーザー単位の一時フォルダ(`$TMPDIR`)に入力ファイルを書き、操作スクリプトにはサブコマンド名とファイルのパスだけを渡す。権限は `$TMPDIR` に任せる
- 終わりの日時(`--until`)・メモの番号(`--id`)など形の決まった値は、操作スクリプトが形を確かめる前提で引数で渡す
- 操作スクリプトは入力ファイルを読み終えたら自分で消す。`$TMPDIR` はユーザー単位の一時フォルダで、セッションをまたいで残り、再起動や OS の定期掃除で消える。データフォルダに書けない(`dataFolderUnwritable`)ときだけは消さずに残し、手元のターミナルでそのまま使えるようにする
- 入力ファイルの中身:

| サブコマンド | 引数 | 入力ファイルの中身 |
|---|---|---|
| `exclude-app add` | `--input-file` | `{"name": "1Password", "bundleId": "com.1password.1password"}`(`bundleId` は分からなければ `null`) |
| `exclude-app remove` | `--input-file` | `{"name": "1Password"}` |
| `exclude-word add` / `remove` | `--input-file` | `{"word": "給与"}` |
| `memo add` | `--input-file` | `{"text": "勤怠の通知メールを毎回手でフォルダに移している"}` |
| `exclude-add` | `--request-file` | 週次レポートからコピーされた依頼文そのもの(下の「依頼文の形」。JSON にしない) |
| `exclude-add` | `--bundle-ids-file`(任意) | `{"家計簿": "com.example.kakeibo"}`(Skill が `/Applications` で分かったアプリだけ) |

結果の形:

```json
{"ok": true, "message": "10月31日 18:00 まで記録します", "notices": ["システム設定のアクセシビリティで記録係をオンにしてください"], "data": {}}
```

- 断ったとき: `{"ok": false, "error": "pastEndsAt" / "missingEndsAt" / "emptyWord" / "notFound" / "emptyText" / "tooLong" / "configUnreadable" / "badRequest" / "dataFolderUnwritable" / "badInputFile", "message": "…"}`
- `dataFolderUnwritable`: その操作が書く場所(設定・メモのファイル、weekly-automation-report の作り直しで書く `requests/`)と `control.log` に書けない(データフォルダがまだ無いときは作れない。`Operation not permitted` など)ため、何も書かずに返したとき。入力ファイルを読む前に確かめ、入力ファイルは消さずに残し、結果に `"inputFile": "<入力ファイルの絶対パス>"`(`exclude-add` で `--bundle-ids-file` もあれば `"bundleIdsFile"` も)を入れる。`control.log` が書けないときもこの返し方にする。Skill は `cd <application の絶対パス>` と、同じサブコマンドにそのパスを渡す行だけのコマンドブロックを渡す(自由な文を書かず、ブロックの中で入力ファイルを作らない)。weekly-automation-report の作り直しの依頼もこの返し方に従う(作り直しは入力ファイルが無く、週は `data.week` で返す。weekly-automation-report の付録)
- `badInputFile`: 入力ファイルが無い・読めない、または `--input-file`・`--bundle-ids-file` の JSON の形が違うとき。`--request-file` の依頼文の1行目が決まり文句でないときは `badRequest`
- `configUnreadable`: `config.json` があるが読めない・形が違うため、設定ファイルの書き換え(始める・止める・除外の追加と削除)を断ったとき
- `exclude-add --request-file`(記録しない候補のまとめての追加)は、依頼文をファイルから読む。Skill は依頼文を分けずに入力ファイルに書く。手を加えるのは、1行目が決まり文句で始まらない(スラッシュコマンドの引数として渡り、コマンド名が外れた)ときに `/routine-work-finder ` を前に戻すことだけ。`--bundle-ids-file` には Skill が `/Applications` で分かったアプリのバンドルIDだけを書く。分からないアプリは名前だけで足し、`bundleId` は `null`
- 結果の `data`: `{"added": {"words": ["給与明細"], "apps": ["家計簿"]}, "alreadyExists": {"words": [], "apps": []}, "skippedLines": ["サイト: 給与システム"], "excludedApps": [...], "excludedTitleWords": [...]}`。`skippedLines` は「ことば: 」「アプリ: 」で始まらないなどで除いた行(空の行は含めない)。足したあとの一覧を `excludedApps`・`excludedTitleWords` で返す
- `badRequest`: 1行目が決まり文句 `/routine-work-finder 記録しないものに次を足してください。` でないため、何も足さずに断ったとき

週次レポートからコピーされる依頼文の形(操作スクリプトが受け取り、1行目を確かめて残りの行を分ける)。weekly-automation-report と共有する fixture `application/tests/fixtures/exclusion_request.txt` がこの形の正で、週次レポート側の組み立てと突き合わせ、操作スクリプトの契約テストが `exclude-add --request-file <fixture のパス>` で fixture をそのまま読む:

```
/routine-work-finder 記録しないものに次を足してください。
ことば: 給与明細
アプリ: 家計簿
```

- fixture の中身はこの3行で、末尾に改行を1つ置く。fixture は activity-recording のタスク14で作り、weekly-automation-report の週次レポート側のテストもこれを使う

## ログの書式

```
2026-10-06T10:15:05+09:00 INFO recording started
2026-10-06T10:20:10+09:00 WARN title unavailable reason=denied
2026-10-07T00:00:05+09:00 INFO purge removed=3
2026-10-09T17:40:12+09:00 INFO exclude added words=2 apps=1 alreadyExists=1 skipped=0
```

- 1行に1件。日時・レベル(INFO / WARN / ERROR)・英語の短い文と `キー=値`
- 題名・シート名・メモの文は書かない。記録しないアプリ・ことばの追加・削除は件数だけを書き、値(ことば・アプリ名)は書かない
