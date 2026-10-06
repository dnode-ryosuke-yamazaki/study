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
- `stoppedAt`: 「記録を止めて」で止めた日時。始めたときに `null` に戻す
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
- 題名が取れなかったとき: `title` の代わりに `{"titleUnavailable": true, "reason": "noWindow" / "denied" / "timeout"}`

除外中の行(アプリ名も題名も書かない):

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
| Excel のシート名 | 前面ウィンドウの子(先頭40個まで)から role が `AXTabGroup` のものを探し、`kAXTabsAttribute` の中で `kAXValueAttribute` が真のタブの `kAXTitleAttribute` |

- `kAXValueAttribute`・`kAXSelectedTextAttribute` など、部品の中の文字を返す属性は読まない
- 1回の記録で上の問い合わせを合わせて1秒で打ち切る

## エラーの理由

| 状況 | reason |
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
python3 -m routine_work_finder.control exclude-app add --name "1Password" --bundle-id com.1password.1password
python3 -m routine_work_finder.control exclude-app remove --name "1Password"
python3 -m routine_work_finder.control exclude-word add --word 給与
python3 -m routine_work_finder.control exclude-word remove --word 給与
python3 -m routine_work_finder.control exclude-list
python3 -m routine_work_finder.control memo add --text "勤怠の通知メールを毎回手でフォルダに移している"
python3 -m routine_work_finder.control memo list
python3 -m routine_work_finder.control memo delete --id 20261006-101530-a1b2
```

結果の形:

```json
{"ok": true, "message": "10月31日 18:00 まで記録します", "notices": ["システム設定のアクセシビリティで記録係をオンにしてください"], "data": {}}
```

- 断ったとき: `{"ok": false, "error": "pastEndsAt" / "missingEndsAt" / "emptyWord" / "notFound" / "emptyText" / "tooLong", "message": "…"}`

## ログの書式

```
2026-10-06T10:15:05+09:00 INFO recording started
2026-10-06T10:20:10+09:00 WARN title unavailable reason=denied
2026-10-07T00:00:05+09:00 INFO purge removed=3
```

- 1行に1件。日時・レベル(INFO / WARN / ERROR)・英語の短い文と `キー=値`
- 題名・シート名・メモの文は書かない
