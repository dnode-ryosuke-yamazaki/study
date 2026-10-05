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
├── pages/<YYYY-MM-DD>.jsonl   # Chrome のページの本文(1行1ページ)
└── memos/<YYYY-MM-DD>.jsonl   # 面倒だった作業のメモ(1行1件)
```

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
  "chromeJsNoticeShownAt": null,
  "excludedApps": [
    { "name": "パスワード", "bundleId": "com.apple.Passwords" },
    { "name": "キーチェーンアクセス", "bundleId": "com.apple.keychainaccess" },
    { "name": "システム設定", "bundleId": "com.apple.systempreferences" }
  ],
  "excludedSitePrefixes": []
}
```

- `endsAt`: 終わりの日時。止めたとき・未設定は `null`
- `stoppedAt`: 「記録を止めて」で止めた日時。始めたときに `null` に戻す
- `chromeJsNoticeShownAt`: Chrome の JavaScript の許可をオフに戻す案内をした日時。始めたときに `null` に戻す
- `excludedApps[].bundleId`: 分からないときは `null`
- 必須の項目: `version`・`endsAt`・`excludedApps`・`excludedSitePrefixes`。欠け・型違いは記録しない側に倒す

## 状態のファイルの形

`recorder-status.json`

```json
{
  "version": 1,
  "updatedAt": "2026-10-06T10:15:05+09:00",
  "recording": true,
  "tickMillis": 212,
  "configError": null,
  "lastWriteError": null,
  "permissions": {
    "Google Chrome": "granted",
    "Google Chrome JavaScript": "granted",
    "Microsoft Excel": "unknown",
    "Microsoft PowerPoint": "unknown",
    "Finder": "denied"
  },
  "lastPurgeDate": "2026-10-06"
}
```

- `permissions` の値: `granted`(問い合わせが通った)/ `denied`(許可なしのエラー)/ `unknown`(まだ尋ねていない)
- 記録係が動いていないとみなす条件: `updatedAt` が今より30秒以上前

## 操作の記録の行の形

`records/<YYYY-MM-DD>.jsonl`。1行に1つの JSON。

通常の行:

```json
{"t":"2026-10-06T10:15:05+09:00","kind":"sample","app":"Google Chrome","bundleId":"com.google.Chrome","monitor":2,"idleSec":1.4,"locked":false,"mic":false,"displaySleepPrevented":false,"content":{"title":"BL-057 - Confluence","url":"https://example.atlassian.net/wiki/spaces/X/pages/1"}}
```

`content` の中身(アプリごと):

| アプリ | content |
|---|---|
| Google Chrome | `{"title": 題名, "url": URL}` |
| Microsoft Excel | `{"workbook": ブック名, "sheet": シート名, "selection": "$C$5:$D$8"}` |
| Microsoft PowerPoint | `{"presentation": 資料名}` |
| Finder | `{"folder": "/Users/…/Documents/"}` |
| 4つ以外 | 項目なし(`content` を書かない) |
| 取れなかった | `{"unavailable": true, "reason": "timeout" / "denied" / "jsDisabled" / "error", "code": エラー番号}` |

除外中の行(アプリ名も書かない):

```json
{"t":"2026-10-06T10:15:10+09:00","kind":"excluded"}
```

開始・停止の行:

```json
{"t":"2026-10-06T09:00:00+09:00","kind":"start"}
{"t":"2026-10-31T18:00:05+09:00","kind":"stop","reason":"endsAtPassed"}
```

- `stop` の `reason`: `endsAtPassed`(終わりの日時を過ぎた)/ `stopRequested`(止める依頼)/ `configError`(設定が読めない)
- 周りの状態が取れなかった項目は `null`
- 読む側は、知らない `kind`・知らない項目を読み飛ばす。最終行が書きかけ(JSON として読めない)の場合も読み飛ばす

## 本文のファイルの形

`pages/<YYYY-MM-DD>.jsonl`

```json
{"t":"2026-10-06T10:15:30+09:00","title":"BL-057 - Confluence","url":"https://example.atlassian.net/wiki/spaces/X/pages/1","sha256":"9f2c…","truncated":false,"body":"ページの本文…"}
```

- `body`: 先頭20,000字まで(Swift の `String` の文字数で数える)
- `truncated`: 20,000字を超えて切り詰めたとき `true`

## メモのファイルの形

`memos/<YYYY-MM-DD>.jsonl`

```json
{"id":"20261006-101530-a1b2","t":"2026-10-06T10:15:30+09:00","text":"勤怠の通知メールを毎回手でフォルダに移している"}
```

- `id`: `<年月日>-<時分秒>-<16進4桁>`。形は `^\d{8}-\d{6}-[0-9a-f]{4}$`

## アプリへの問い合わせの文

記録係が `NSAppleScript` で実行する決まった文。`<N>` は打ち切りの秒数(1)。

```applescript
with timeout of <N> seconds
  tell application "Google Chrome" to return {title of active tab of front window, URL of active tab of front window}
end timeout
```

```applescript
with timeout of <N> seconds
  tell application "Google Chrome" to tell active tab of front window to execute javascript "document.body.innerText"
end timeout
```

```applescript
with timeout of <N> seconds
  tell application "Microsoft Excel" to return {name of active workbook, name of active sheet, get address of selection}
end timeout
```

```applescript
with timeout of <N> seconds
  tell application "Microsoft PowerPoint" to return name of active presentation
end timeout
```

```applescript
with timeout of <N> seconds
  tell application "Finder" to return POSIX path of (target of front Finder window as alias)
end timeout
```

エラー番号と理由の対応:

| エラー番号 | reason |
|---|---|
| -1712 | `timeout` |
| -1743 | `denied` |
| Chrome の「JavaScript の実行が無効」の応答 | `jsDisabled`(番号と文言は実装時に実機で取ったものを使う) |
| それ以外 | `error` |

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
- 署名のあと、launchd のジョブを `launchctl bootout` → `bootstrap` で入れ直す(手元のターミナルで実行する)

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
python3 -m routine_work_finder.control exclude-app add --name "1Password" --bundle-id com.1password.1password
python3 -m routine_work_finder.control exclude-app remove --name "1Password"
python3 -m routine_work_finder.control exclude-site add --prefix https://example.com/hr/
python3 -m routine_work_finder.control exclude-site remove --prefix https://example.com/hr/
python3 -m routine_work_finder.control exclude-list
python3 -m routine_work_finder.control memo add --text "勤怠の通知メールを毎回手でフォルダに移している"
python3 -m routine_work_finder.control memo list
python3 -m routine_work_finder.control memo delete --id 20261006-101530-a1b2
```

結果の形:

```json
{"ok": true, "message": "10月31日 18:00 まで記録します", "notices": ["Chrome を前面にすると許可のダイアログが出ます"], "data": {}}
```

- 断ったとき: `{"ok": false, "error": "pastEndsAt" / "missingEndsAt" / "invalidPrefix" / "notFound" / "emptyText" / "tooLong", "message": "…"}`

## ログの書式

```
2026-10-06T10:15:05+09:00 INFO recording started
2026-10-06T10:20:10+09:00 WARN Microsoft Excel unavailable reason=denied code=-1743
2026-10-07T00:00:05+09:00 INFO purge removed=3
```

- 1行に1件。日時・レベル(INFO / WARN / ERROR)・英語の短い文と `キー=値`
- 本文・題名・URL・メモの文は書かない
