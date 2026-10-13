# 空き時間からの会議候補提示とTeams会議の自動作成 付録

## 概要

design.md の処理フローとデータ設計が使う書式(設定値・サブコマンド・台帳ファイルの形・選択結果の1行・ログ)だけを置く。手順・分岐・判断は design.md が正。

## 設定値の一覧

`application/config.py` が1箇所に集約して持つ値。環境変数があればそれを優先し、無ければ既定値を使う。ビューアURLとサーバー相対パスは個人のテナントを含むためリポジトリに置かず、作業フォルダの `settings.json` か環境変数から読む。

### 置き場所

| 項目 | 既定値 | 環境変数 |
|---|---|---|
| 台帳ルート | `~/Library/CloudStorage/OneDrive-Deloitte(O365D)/00_root/auto/meetingSetting/` | `MEETING_SETUP_LEDGER_ROOT` |
| 通知フォルダ | `~/Library/CloudStorage/OneDrive-Deloitte(O365D)/00_root/auto/teamsNotice/meetingSetting/` | `MEETING_SETUP_NOTICE_DIR` |
| 作業フォルダ | `~/Library/Application Support/meeting-setup-automation/` | `MEETING_SETUP_WORK_DIR` |
| ビューアURL | `settings.json` の `output_web_viewer` | `MEETING_SETUP_WEB_VIEWER` |
| サーバー相対パス | `settings.json` の `output_web_dir` | `MEETING_SETUP_WEB_DIR` |

台帳ルートの下のフォルダ: `request/`(依頼)・`candidates/`(候補)・`organizerEventsRequest/`(開催者の予定の依頼)・`organizerEvents/`(開催者の予定)・`selection/`(選択結果)・`result/`(作成結果)・`html/`(候補選択画面)。作業フォルダの下: `roster.json`(メンバー名簿)・`settings.json`(ビューア設定)・`meeting-setup.log`(ログ)。

### 待ち時間

| 項目 | 既定値 | 環境変数 | 適用先 |
|---|---|---|---|
| 候補待ち上限秒 | 300 | `MEETING_SETUP_CANDIDATES_TIMEOUT_SEC` | 試行番号1の候補・代替案2の候補・開催者の予定の待ち |
| 作成結果待ち上限秒 | 300 | `MEETING_SETUP_RESULT_TIMEOUT_SEC` | 作成結果の待ち |
| 確認間隔秒 | 5(下限1) | `MEETING_SETUP_POLL_INTERVAL_SEC` | すべての待ち |
| 同期猶予秒 | 30 | `MEETING_SETUP_SYNC_GRACE_SEC` | 選択画面を書き出してから通知するまで |

### 探索条件

| 項目 | 値 | 根拠 |
|---|---|---|
| 既定の探索期間 | 当日から14日 | requirements.md 候補探索の既定条件 [1] |
| 既定の時間帯 | 09:30〜17:30 | 同 [1] |
| 既定の候補件数 | 5 | 同 [1] |
| 既定の対象曜日 | 月〜金(`0,1,2,3,4`) | 同 [2] |
| 既定の出席可能率の下限 | 100 | 同 [3] |
| 一部不在を許す依頼の出席可能率の下限 | 50(`request.py`) | 同 [3] |
| フローに返させる最大件数 | 50 | design.md 決定事項「探索条件の判断の置き場所」 |
| 代替案2の探索期間 | 当日から21日 | requirements.md 候補が0件のときの代替案の提示 [1] |
| 代替案2の時間帯 | 09:30〜18:30 | 同 [1] |
| 所要時間の下限 | 5分 | requirements.md 依頼内容の受け付け条件 [1] |
| 探索期間の終了日の上限 | 当日から21日(代替案2の期間と同じ値) | 同 [3] |

## サブコマンドの表(手順の担い手)

チャットでのやり取りは `~/.claude/skills/meeting-setup/SKILL.md` の手順が、ファイルの読み書きと判定は `main.py` のサブコマンドが担う。

| 手順 | 担い手 |
|---|---|
| 件名・参加者・所要時間・アジェンダの聞き取り、依頼内容の提示と確認、選択結果の貼り付けの受け取り、再試行の確認、コマンドの出力のチャットへの表示、相談の文面の伝達 | SKILL.md(チャットの手順) |
| 名前の解決・入力値の確認・依頼の書き出し | `main.py submit`(`--dry-run` で書き出さずに依頼の内容だけを返す) |
| 候補の待ち・絞り込み・開催者の予定のみ重なる枠の分離・開催者の予定の依頼の書き出しと到着待ち・予定と枠の突き合わせ・代替案の提示・選択画面の書き出し・同期の猶予待ち・ビューアURLの組み立て・通知の書き出し。および選択済みの依頼を再開したときの作成結果の待ちと完了の通知、作成失敗を検知したときの失敗理由の提示 | `main.py resume` |
| 貼られた選択結果の突き合わせ・選択結果の書き出し・作成結果の待ち・直リンクの取り出し・完了の通知 | `main.py select` |
| 失敗した作成の再試行(再試行番号を増やした選択結果の書き出し以降) | `main.py retry-create` |

`main.py resume` は依頼IDだけを受け取り、design.md「状態管理」の判定に従ってその依頼の続きを進める。打ち切った後の再開も、依頼の直後の待ちも同じサブコマンドで行う。判定が「作成失敗」なら完了として報告せず、失敗理由と再試行の案内を出して終わり、再試行そのものは `retry-create` に委ねる。

## 台帳ファイルの書式

### フォルダとファイル名

| 種類 | 置き場所 | 書く側 | 読む側 | ファイル名 |
|---|---|---|---|---|
| 依頼 | `auto/meetingSetting/request/` | Skill | 探索フロー | `request-<依頼ID>-a<試行番号>.json` |
| 候補 | `auto/meetingSetting/candidates/` | 探索フロー | Skill | `candidates-<依頼ID>-a<試行番号>.json` |
| 開催者の予定の依頼 | `auto/meetingSetting/organizerEventsRequest/` | Skill | 開催者予定フロー | `organizer-events-request-<依頼ID>.json` |
| 開催者の予定 | `auto/meetingSetting/organizerEvents/` | 開催者予定フロー | Skill | `organizer-events-<依頼ID>.json` |
| 選択結果 | `auto/meetingSetting/selection/` | Skill | 作成フロー | `selection-<依頼ID>.json`(再試行は `selection-<依頼ID>-r<再試行番号>.json`) |
| 作成結果 | `auto/meetingSetting/result/` | 作成フロー | Skill | `result-<依頼ID>.json`(再試行は `result-<依頼ID>-r<再試行番号>.json`) |
| 候補選択画面 | `auto/meetingSetting/html/` | Skill | ブラウザ | `select-<依頼ID>.html` |
| 通知 | `auto/teamsNotice/meetingSetting/` | Skill | 会議設定通知フロー | `meeting-<書き出し時刻>.txt`(同じ秒に2件目以降は `meeting-<書き出し時刻>-<連番>.txt`) |

- フローが書き出すファイルの名前は、読んだファイルの名前の先頭を置き換えて決める。探索フローは `request-` を `candidates-` に、開催者予定フローは `organizer-events-request-` を `organizer-events-` に、作成フローは `selection-` を `result-` に置き換える。フローは番号を解釈しない
- 選択結果と作成結果の再試行番号が0のときは接尾辞を付けず、1以上のときだけ `-r<再試行番号>` を付ける
- 開催者の予定の依頼と開催者の予定は依頼1件につき1ファイルで、試行番号・再試行番号を持たない

### IDと日時の形式

| 項目 | 形式 | 例 |
|---|---|---|
| 依頼ID | `<年月日>-<時分秒>-<英数字4文字>`(起動時刻+乱数。`^\d{8}-\d{6}-[0-9a-z]{4}$`) | `20260909-101500-ab3f` |
| 試行番号 | 初回が1、代替案2の依頼が2(それ以上は増えない) | `a1` / `a2` |
| 再試行番号 | 初回の作成が0、会議の作成をやり直すたびに1増える | `r1` |
| Skillが書く日時 | ISO 8601、日本時間のオフセット付き | `2026-09-10T10:00:00+09:00` |
| 開催者の予定の依頼の範囲 | ISO 8601、UTC(`Z` 付き) | `2026-09-10T00:00:00Z` |
| フローが書く日時 | `dateTime` と `timeZone` の組(`timeZone` は `UTC`) | `{"dateTime": "2026-09-10T01:00:00.0000000", "timeZone": "UTC"}` |

### 通知ファイルのHTML断片

会議設定通知フローは中身をそのまま Teams の投稿本文に渡し、Teams は本文を HTML として描画する。Skill はチャットに出すプレーンテキストを次の規則で HTML 断片に組み替えて書く。

- 件名・参加者名など値はすべて HTML エスケープする
- 改行は `<br>`、URL は `<a href="…">…</a>`、行頭の字下げ(半角空白)は `&nbsp;` にする
- 素のテキストのまま書くと全行が1行に潰れ、URL がクリックできず、山括弧を含む値がタグとみなされて消える

```html
【会議候補が出そろいました】<br>件名: 定例<br>候補: 2件<br>開催者の予定のみ重なる枠: 1件(自分の予定を調整すれば開けられる枠)<br>・09/11(木) 14:00〜15:00 — 社内レビュー 14:00〜15:00(仮)<br>選択画面: <a href="https://example.sharepoint.com/...">https://example.sharepoint.com/...</a><br>開けない場合は数十秒待って再読込してください
```

### 依頼ファイルの形

`request-<依頼ID>-a<試行番号>.json`。フローが読むのは `meeting.requiredAttendees`・`meeting.durationMinutes`・`search` だけで、`filter`・`specified`・`agenda`・`attendees` は Skill だけが読む。

```json
{
  "requestId": "20260909-101500-ab3f",
  "attempt": 1,
  "meeting": {
    "subject": "定例",
    "durationMinutes": 60,
    "requiredAttendees": ["a@example.com", "b@example.com"],
    "attendees": [{"emailAddress": {"address": "a@example.com", "name": "A"}, "type": "required"}],
    "agenda": "- 進捗\n- 課題"
  },
  "search": {
    "start": "2026-09-09T00:00:00+09:00",
    "end": "2026-09-23T23:59:59+09:00",
    "minimumAttendeePercentage": 100,
    "maxCandidates": 50
  },
  "filter": {"timeWindowStart": "09:30", "timeWindowEnd": "17:30", "weekdays": [0, 1, 2, 3, 4], "requireAllFree": true, "maxResults": 5},
  "specified": []
}
```

- `specified` の値: `period`(期間)・`timeWindow`(時間帯)・`maxResults`(候補件数)・`weekdays`(曜日)・`allFree`(全員空き)。開催者が明示的に指定した項目だけを入れる
- `search.minimumAttendeePercentage` は全員空きを求める依頼で 100、一部不在を許す依頼で 50

### 候補ファイルの形

`candidates-<依頼ID>-a<試行番号>.json`。「会議の時間を検索 (V2)」の応答をそのまま `meetingTimeSuggestions` に入れる。

```json
{
  "requestId": "20260909-101500-ab3f",
  "attempt": 1,
  "meetingTimeSuggestions": [
    {
      "confidence": 100.0,
      "organizerAvailability": "tentative",
      "meetingTimeSlot": {
        "start": {"dateTime": "2026-09-10T01:00:00.0000000", "timeZone": "UTC"},
        "end": {"dateTime": "2026-09-10T02:00:00.0000000", "timeZone": "UTC"}
      },
      "attendeeAvailability": [
        {"attendee": {"emailAddress": {"address": "a@example.com"}}, "availability": "free"},
        {"attendee": {"emailAddress": {"address": "b@example.com"}}, "availability": "free"}
      ]
    }
  ],
  "emptySuggestionsReason": "",
  "error": ""
}
```

- 時刻は世界標準時。Skill が日本時間に変換する
- 開催者は `attendeeAvailability` に含まれず、空き状況は `organizerAvailability` にある。値は前後の空白を除き小文字に揃えて読み、`free`・`tentative` 以外(`busy`・`oof`・`workingElsewhere`・`unknown`)は「空きでも仮でもない」として扱う
- `confidence: 100` は全員空きを意味しない。Skill は `attendeeAvailability[].availability` と `organizerAvailability` の両方を見る
- `error` が空でなければ失敗として扱う。候補0件のときは `emptySuggestionsReason` に理由が入る(例: `OrganizerUnavailable`)

### 開催者の予定の依頼ファイルの形

`organizer-events-request-<依頼ID>.json`。範囲は開催者の予定のみ重なる枠の最小の開始から最大の終了まで(UTC)。

```json
{
  "requestId": "20260909-101500-ab3f",
  "rangeStart": "2026-09-10T01:00:00Z",
  "rangeEnd": "2026-09-19T08:30:00Z"
}
```

### 開催者の予定ファイルの形

`organizer-events-<依頼ID>.json`。「カレンダー ビューの取得 (V3)」で開催者自身の既定カレンダーを範囲で読んだ結果。繰り返し予定は回ごとに展開された状態で入る。本文・出席者・場所は書かない。

```json
{
  "requestId": "20260909-101500-ab3f",
  "error": "",
  "events": [
    {
      "subject": "社内レビュー",
      "showAs": "tentative",
      "sensitivity": "normal",
      "start": {"dateTime": "2026-09-11T05:00:00.0000000", "timeZone": "UTC"},
      "end": {"dateTime": "2026-09-11T06:00:00.0000000", "timeZone": "UTC"}
    }
  ]
}
```

- `showAs` の値: `free` / `tentative` / `busy` / `oof` / `workingElsewhere` / `unknown`。Skill は `free` の予定を表示しない
- `sensitivity` の値: `normal` / `personal` / `private` / `confidential`。`private`・`confidential` は件名の代わりに「非公開の予定」と示す
- `error` が空でなければ失敗として扱い、件名なしで枠を提示する
- 種別の表示語: `tentative`→仮、`busy`→予約済み、`oof`→外出中、`workingElsewhere`→他の場所で作業中、それ以外→不明

### 選択結果ファイルの形

`selection-<依頼ID>.json` / `selection-<依頼ID>-r<再試行番号>.json`。このファイルだけで会議を作れる(作成フローは依頼ファイルを読みに行かない)。物理会議室(リソース)は含めない。

```json
{
  "requestId": "20260909-101500-ab3f",
  "retry": 0,
  "meeting": {
    "subject": "定例",
    "start": "2026-09-10T10:00:00+09:00",
    "end": "2026-09-10T11:00:00+09:00",
    "timeZone": "Tokyo Standard Time",
    "bodyHtml": "<h3>アジェンダ</h3><ul><li>進捗</li><li>課題</li></ul>",
    "attendees": [{"emailAddress": {"address": "a@example.com", "name": "A"}, "type": "required"}],
    "isOnlineMeeting": true,
    "onlineMeetingProvider": "teamsForBusiness"
  }
}
```

- アジェンダが無い依頼の `bodyHtml` は `<h3>アジェンダ</h3><p>アジェンダは未定です(依頼時に指定がありませんでした)</p>`
- 作成フローは `start`・`end` の先頭19文字(オフセットを落とした値)を `timeZone` と組み合わせて Graph に渡す

### 作成結果ファイルの形

`result-<依頼ID>.json` / `result-<依頼ID>-r<再試行番号>.json`。`POST /me/events` の応答をそのまま `event` に入れる。

```json
{
  "requestId": "20260909-101500-ab3f",
  "retry": 0,
  "error": "",
  "event": {
    "id": "AAMk...",
    "subject": "定例",
    "start": {"dateTime": "2026-09-10T10:00:00.0000000", "timeZone": "Tokyo Standard Time"},
    "end": {"dateTime": "2026-09-10T11:00:00.0000000", "timeZone": "Tokyo Standard Time"},
    "attendees": [{"emailAddress": {"address": "a@example.com", "name": "A"}, "type": "required"}],
    "onlineMeeting": {"joinUrl": "https://teams.microsoft.com/l/meetup-join/..."},
    "webLink": "https://outlook.office365.com/owa/?itemid=...",
    "body": {"contentType": "html", "content": "<html>...https://teams.microsoft.com/meetingOptions/?organizerId=...</html>"}
  }
}
```

- Skill が読むのは `event.id`・`subject`・`start`・`end`・`attendees`・`onlineMeeting.joinUrl`・`webLink`・`body.content`。`event` で包まずに応答をそのまま書いた場合も読める
- 会議オプション画面の直リンクは `body.content` の中の `https://teams.microsoft.com/meetingOptions/...` を Skill が取り出す

## 選択結果のコピー1行の書式

選択画面の「選択結果をコピー」ボタンがクリップボードへ入れる1行。開催者がチャットに貼ると `main.py select` が読み取る。

```
MEETING-SELECT <依頼ID> a<試行番号> #<候補番号> <開始> <終了>
```

例:

```
MEETING-SELECT 20260909-101500-ab3f a1 #2 2026-09-11T14:00:00+09:00 2026-09-11T15:00:00+09:00
```

- 目印の語 `MEETING-SELECT` を先頭に置き、貼られた内容が選択結果かどうかを取り違えずに判定する
- 試行番号はその枠が入っていた候補ファイルの試行番号(候補・代替案1・開催者の予定のみ重なる枠は 1、代替案2は 2)。カードごとに `data-attempt` で持つ
- 候補番号は画面に並べた順の1からの連番(区画をまたいで通し採番)。表示用で、突き合わせには使わない
- 開始・終了は日本時間のオフセット付き。`select` は候補ファイルの枠を日本時間に変換したうえで時点として比較する
- カードの `data-` 属性: `data-request`(依頼ID)・`data-attempt`・`data-number`・`data-start`・`data-end`。ラジオボタンは全区画共通の `name="candidate"`

## ログの表

| 項目 | 値 |
|---|---|
| 出力先 | 標準出力(開催者がその場で読む)と `~/Library/Application Support/meeting-setup-automation/meeting-setup.log`(追記) |
| ローテーション | 5世代 |
| 書式 | 1行1件。日時・レベル・日本語の短い文と `キー=値` |
| 出さないもの | メールアドレス・アジェンダ本文・参加URL・会議本文・予定の件名(開催者自身の予定を含む) |

| タイミング | 内容 | レベル |
|---|---|---|
| 依頼の書き出し | 依頼ID・試行番号・参加者の人数・探索条件 | INFO |
| 名前の解決に失敗 | 解決できなかった名前の件数・うち複数人が該当した件数 | WARNING |
| 待ちの開始・進捗 | 依頼ID・待っている対象・経過時間 | INFO |
| 候補の絞り込み | 依頼ID・受け取った枠の件数・採用した件数・開催者の予定のみ重なる枠の件数・除外の内訳 | INFO |
| 開催者の予定の依頼の書き出し | 依頼ID・範囲の開始と終了・対象の枠の件数 | INFO |
| 開催者の予定の突き合わせ | 依頼ID・受け取った予定の件数・枠ごとに重なった予定の件数 | INFO |
| 開催者の予定を取得できない | 依頼ID・理由(待ち上限・フローの失敗理由・依頼の書き出し失敗) | WARNING |
| 代替案の提示 | 依頼ID・代替案1の件数・代替案2の件数・代替案2を作ったかどうか | INFO |
| どちらの代替案も0件 | 依頼ID・試した条件・開催者の予定のみ重なる枠の件数 | WARNING |
| 選択画面の書き出し | 依頼ID・候補件数 | INFO |
| 選択結果の読み取りに失敗 | 依頼ID(読み取れた場合)・失敗の種類 | WARNING |
| 選択結果の書き出し | 依頼ID・候補番号 | INFO |
| 会議の作成完了 | 依頼ID・会議の識別子 | INFO |
| 直リンクを取り出せない | 依頼ID | WARNING |
| フローからの失敗理由 | 依頼ID・失敗理由 | ERROR |
| 待ち上限で打ち切り | 依頼ID・待っていた対象・経過時間 | WARNING |
| 台帳ファイルの書き出し失敗 | 依頼ID・種類 | ERROR |
| 想定外の例外 | トレースバック | ERROR |
