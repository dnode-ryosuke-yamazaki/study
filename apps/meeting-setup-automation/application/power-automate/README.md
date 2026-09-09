# Power Automateフローの構築手順と設定内容

会議設定自動化が使うPower Automateフロー4本(探索フロー・作成フロー・予定詳細フロー・会議設定通知フロー)の、監視先フォルダ・アクションの入力・書き出すファイルの形・つまずく点をまとめる。**どのフローがどのフォルダを見ているかが分からないと障害時の切り分けができない**ため、フローを変更したら必ずこのファイルも直す。

**フロー定義そのものはこのリポジトリに置かない。** 定義ファイルにはテナント識別子・接続識別子が含まれるため。フローはテナント側のPower Automateで管理する。

- 仕様: [../../specs/meeting-scheduling/design.md#power-automateフローの役割](../../specs/meeting-scheduling/design.md#power-automateフローの役割)
- 台帳ファイルの決め方: [../../specs/meeting-scheduling/design.md#データ設計台帳ファイル](../../specs/meeting-scheduling/design.md#データ設計台帳ファイル)

## 前提条件 / 権限

| 項目 | 内容 |
|---|---|
| ライセンス | Power Automate for Office 365(標準コネクタのみ)。プレミアムコネクタ・カスタムコネクタ・素のHTTPアクション・HTTP要求受信トリガーは使えない(DLPとライセンスの両方で塞がれている) |
| コネクタ | OneDrive for Business(トリガーとファイル作成)、Office 365 Outlook(会議の時間を検索 (V2)・HTTP 要求を送信します・カレンダーの取得 (V2)・イベントの取得 (V4))、Microsoft Teams(メッセージを投稿する) |
| 接続 | 自分のアカウントで接続する。会議の開催者は接続アカウント本人になる |
| フォルダ | 個人OneDriveの `00_root/auto/meetingSetting/` 配下と `00_root/auto/teamsNotice/meetingSetting/`。同期クライアントで同じフォルダをこのMacへ下ろしておく |

## フローとフォルダの対応

| フロー | トリガー(監視するフォルダ) | 書き出すフォルダ | 書き出すファイル名 |
|---|---|---|---|
| 探索フロー | `meetingSetting/request/` にファイルが作成されたとき | `meetingSetting/candidates/` | 読んだ名前の `request-` を `candidates-` に置き換える |
| 作成フロー | `meetingSetting/selection/` にファイルが作成されたとき | `meetingSetting/result/` | 読んだ名前の `selection-` を `result-` に置き換える |
| 予定詳細フロー | `meetingSetting/detailRequest/` にファイルが作成されたとき | `meetingSetting/detail/` | 読んだ名前の `detail-request-` を `detail-` に置き換える |
| 会議設定通知フロー | `teamsNotice/meetingSetting/` にファイルが作成されたとき | (Teamsの自分専用チャネルへ投稿) | — |

**3本のいずれも、書き出すファイルの名前は読んだファイルの名前の先頭を置き換えただけで決める。** 試行番号(`-a1`/`-a2`)や再試行番号(`-r1`)を解釈する分岐をフローに持たせない。名前が食い違うとSkillは現れないファイルを待ち上限(既定5分)まで待つことになる。

ファイル名の式(探索フローの例):

```
replace(triggerOutputs()?['headers']['x-ms-file-name'], 'request-', 'candidates-')
```

## 共通: トリガーの中身をJSONにする

OneDriveの「ファイルが作成されたとき」トリガーは、ファイルの中身を**バイナリ(`application/octet-stream`)**で渡す。「JSON の解析」にそのまま繋ぐと次のエラーで失敗する。

```
BadRequest. The property 'content' must be of type JSON in the 'ParseJson' action inputs, but was of type 'application/octet-stream'.
```

「JSON の解析」のコンテンツ欄には次の式を入れて文字列へ変換する。

```
json(base64ToString(triggerBody()?['$content']))
```

## 共通: 失敗しても結果ファイルを書く

フローが失敗したときに結果ファイルを書かないと、Skillは待ち上限まで待つしかなく失敗の理由も伝わらない。**必ず失敗理由を入れた結果ファイルを書き出す作りにする**(実機で、これが無ければ5分待たされたところを50秒で検知できた)。

新しいデザイナーには「並列分岐の追加」が無い。失敗時の書き出しは次の手順で作る。

1. 本体のアクション(または条件ブロック)の**後ろ**に「ファイルの作成」アクションを置く
2. そのアクションの「設定」→「この後に実行する」で、**「成功しました」のチェックを外し**、「失敗しました」「スキップ済みである」「タイムアウトした」にチェックを入れる
3. 内容には `error` に失敗理由(`result('<本体のスコープ名>')` や `body('<アクション名>')?['error']?['message']` など)を入れたJSONを書く

正常時に書くファイルの `error` は空文字にする。Skillは `error` が空でなければ失敗として扱う。

## 探索フロー

### 読む(依頼ファイル `request-<依頼ID>-a<試行番号>.json`)

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

フローが読むのは `meeting.requiredAttendees` と `search` だけ。`filter`・`specified`・`agenda`・`attendees` はSkillだけが読む(フローはアジェンダを読まない)。

### アクション: 会議の時間を検索 (V2)

| 入力 | 値 |
|---|---|
| 必須出席者 | `join(body('JSON_の解析')?['meeting']?['requiredAttendees'], ';')` |
| 会議時間(分) | `meeting.durationMinutes` |
| 開始時刻 / 終了時刻 | `search.start` / `search.end`(オフセット付きのまま渡してよい) |
| 出席可能率の下限(最小出席率) | `search.minimumAttendeePercentage` |
| 最大候補数 | `search.maxCandidates` |
| 空きのみを返す(IsOrganizerOptional等) | 既定のまま |

**このアクションに時間帯・勤務時間・タイムゾーンのパラメータは無い。** 依頼で9:30〜18:30を渡しても8:00の枠が返り、Outlookの勤務時間の設定も結果に影響しない(実機確認E1)。時間帯・曜日・祝日の絞り込みはすべてSkill側で行う。

### 書く(候補ファイル `candidates-<依頼ID>-a<試行番号>.json`)

アクションの応答をそのまま `meetingTimeSuggestions` に入れ、`emptySuggestionsReason` と `error` を添える。

```json
{
  "requestId": "20260909-101500-ab3f",
  "attempt": 1,
  "meetingTimeSuggestions": [
    {
      "confidence": 100.0,
      "organizerAvailability": "free",
      "meetingTimeSlot": {
        "start": {"dateTime": "2026-09-10T01:00:00.0000000", "timeZone": "UTC"},
        "end": {"dateTime": "2026-09-10T02:00:00.0000000", "timeZone": "UTC"}
      },
      "attendeeAvailability": [
        {"attendee": {"emailAddress": {"address": "a@example.com"}}, "availability": "free"},
        {"attendee": {"emailAddress": {"address": "b@example.com"}}, "availability": "tentative"}
      ]
    }
  ],
  "emptySuggestionsReason": "",
  "error": ""
}
```

Skillが依存している応答の性質(実機確認E1で判明):

- **時刻はすべて世界標準時**で返る。Skillが日本時間へ変換する
- **`confidence: 100` は「全員空き」を意味しない。** 出席可能率の下限を100%にしても `availability` が `tentative` の出席者を含む枠が返る。Skillは `attendeeAvailability[].availability == "free"` と `organizerAvailability == "free"` の両方を見る
- **開催者は `attendeeAvailability` に含まれない。** 開催者の空きは `organizerAvailability` にある
- 候補0件のときは `emptySuggestionsReason` に理由が入る(例: `OrganizerUnavailable`)
- 応答は `maxCandidates` で打ち切られる。打ち切られた集合の外の枠はSkill側で絞り込みを緩めても現れない

## 作成フロー

### 読む(選択結果ファイル `selection-<依頼ID>.json` / `selection-<依頼ID>-r<再試行番号>.json`)

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

このファイルだけで会議を作れる(依頼ファイルを読みに行かない)。物理会議室(リソース)は含まれない。

### アクション: HTTP 要求を送信します(Office 365 Outlookコネクタのパススルー)

| 入力 | 値 |
|---|---|
| URI | `https://graph.microsoft.com/v1.0/me/events`(**1行で書く。改行が混入すると `411 Length Required` のHTMLが返り、Graphのエラーと区別できない**) |
| メソッド | POST |
| 本文 | 下記 |

```json
{
  "subject": "@{body('JSON_の解析')?['meeting']?['subject']}",
  "start": {"dateTime": "@{substring(body('JSON_の解析')?['meeting']?['start'], 0, 19)}", "timeZone": "Tokyo Standard Time"},
  "end": {"dateTime": "@{substring(body('JSON_の解析')?['meeting']?['end'], 0, 19)}", "timeZone": "Tokyo Standard Time"},
  "body": {"contentType": "HTML", "content": "@{body('JSON_の解析')?['meeting']?['bodyHtml']}"},
  "attendees": @{body('JSON_の解析')?['meeting']?['attendees']},
  "isOnlineMeeting": true,
  "onlineMeetingProvider": "teamsForBusiness"
}
```

- **台帳の日時はオフセット付き(`+09:00`)で書いてあり、フロー側で `substring(..., 0, 19)` により末尾を落として `timeZone` と組み合わせる。** Graphは日時にオフセットが付いた状態で `timeZone` を併記すると解釈が衝突する
- 出席者はGraphが受け取る形(`emailAddress` / `type`)で台帳に書いてあるため、フロー側で配列を組み替える処理は不要。人数が変わってもフローは無改修で済む
- このコネクタのパススルーで通っているのは `POST /me/events` だけ。読み取り(`GET`・クエリ付き・3階層のパス)はコネクタの検証で `400` になる。予定の取得には使わない

### 書く(作成結果ファイル `result-<依頼ID>.json` / `result-<依頼ID>-r<再試行番号>.json`)

```json
{
  "requestId": "20260909-101500-ab3f",
  "retry": 0,
  "error": "",
  "event": { "...Graphの応答をそのまま..." }
}
```

Skillは `event.id`・`subject`・`start`・`end`・`attendees`・`onlineMeeting.joinUrl`・`webLink`・`body.content` を読む。`event` で包まずに応答をそのまま書いた場合も読める。**会議本文(`body.content`)はそのまま渡す。** 会議オプション画面の直リンクはSkillが本文から取り出す(自前のアジェンダ本文を指定しても、Teamsは直リンクを本文に追記する。実機確認E3)。

## 予定詳細フロー

代替案1(仮の予定を含める)で、仮の予定を持つ参加者の予定の件名を取るためのフロー。**パススルーの「HTTP 要求を送信します」は使わない**(このコネクタでは予定の取得に使えない)。専用アクションの「カレンダーの取得 (V2)」と「イベントの取得 (V4)」を使う。

### 読む(予定詳細の依頼ファイル `detail-request-<依頼ID>.json`)

```json
{
  "requestId": "20260909-101500-ab3f",
  "attendees": ["b@example.com", "me@example.com"],
  "start": "2026-09-10T10:00:00+09:00",
  "end": "2026-09-12T16:00:00+09:00"
}
```

### アクション

1. **カレンダーの取得 (V2)** で開催者のカレンダー一覧を取る。一覧には**カレンダーの持ち主のメールアドレス**(`owner.address`)が含まれる
2. `attendees` の各メールアドレスについて、持ち主が一致するカレンダーを探す(「アレイのフィルター処理」)
   - 一致するカレンダーが無ければ、その参加者を `calendarFound: false`・`events: []` で書き出す(件名を取得できない扱い)
3. 一致したカレンダーごとに **イベントの取得 (V4)** を呼ぶ。`Calendar id` にそのカレンダーのIDを指定し、`Filter Query` で `start/dateTime ge '<start>' and end/dateTime le '<end>'`(依頼の範囲を世界標準時へ直したもの)を渡す。`Top Count` は50程度
4. 参加者ごとに予定を配列にして書き出す

**注意**: 「イベントの取得 (V4)」が返す主催者の欄には接続アカウントが入り、実際の主催者ではない。主催者の判定には使わない。繰り返し予定は回ごとに展開されない(Skill側で件名の取得対象から外す)。

### 書く(予定詳細ファイル `detail-<依頼ID>.json`)

```json
{
  "requestId": "20260909-101500-ab3f",
  "error": "",
  "attendees": [
    {
      "address": "b@example.com",
      "calendarFound": true,
      "events": [
        {
          "subject": "顧客MTG",
          "showAs": "tentative",
          "sensitivity": "normal",
          "isRecurring": false,
          "start": {"dateTime": "2026-09-10T01:00:00.0000000", "timeZone": "UTC"},
          "end": {"dateTime": "2026-09-10T02:00:00.0000000", "timeZone": "UTC"}
        }
      ]
    },
    {"address": "c@example.com", "calendarFound": false, "events": []}
  ]
}
```

Skillが読む項目は `subject`・`showAs`(`tentative` の予定だけを枠と突き合わせる)・`sensitivity`(`private`/`confidential` は件名を示さない)・`isRecurring` または `recurrence`/`seriesMasterId`/`type`(繰り返しは対象外)・`start`/`end`(世界標準時)。**予定の本文と出席者は書き出さない**(Skillも扱わない)。

件名が取れるのは、その参加者が開催者にカレンダーを共有していて、開催者のカレンダー一覧に入っている場合だけ。いま一覧に何が入っているかは「カレンダーの取得 (V2)」を1回テスト実行すれば確認できる。

## 会議設定通知フロー

`extend-teams-automation` SkillのB節の手順で、既存のTeams投稿フローを複製して作る。

1. 既存の投稿フロー(例: 「テスト投稿先」用)を「名前を付けて保存」で複製する
2. トリガー(OneDriveの「ファイルが作成されたとき」)のフォルダを `00_root/auto/teamsNotice/meetingSetting/` に変える
3. Teams「メッセージを投稿する」の投稿先を自分専用チャネルにする
4. 保存してオンにする
5. `~/.claude/config/project-profiles.json` の最上位 `user.teams.destinations` に「会議設定通知」が登録されていることを確認し、`teams-post` でテスト投稿して表示を目視確認する

**投稿先ごとに専用フォルダと専用フローが1組必要。** 既存フローの使い回しはできない(別のフォルダを見ている)。通知フォルダを台帳フォルダ(`meetingSetting/`)と分けているのは、通知フローが台帳ファイルを誤検知して投稿してしまうのを防ぐため。

## 構築でつまずく点(まとめ)

| つまずき | 対処 |
|---|---|
| 「JSON の解析」が `application/octet-stream` で失敗する | コンテンツ欄に `json(base64ToString(triggerBody()?['$content']))` |
| 失敗時の分岐を作りたいが「並列分岐の追加」が無い | 後ろにアクションを置き「この後に実行する」で失敗・スキップ・タイムアウトを指定 |
| 失敗時に結果ファイルが無くSkillが5分待つ | 失敗時の書き出しを必ず作る(`error` に理由) |
| 出席者の配列をフローで組み替えるのが面倒 | 台帳にGraphの形(`emailAddress`/`type`)で書いてあるのでそのまま渡す |
| 日時の解釈が衝突する | 台帳はオフセット付き。フローで `substring(..., 0, 19)` して `timeZone` と組み合わせる |
| Graph呼び出しが `411 Length Required` のHTMLを返す | URI欄の改行を取り除く |
| 候補が9時間ずれる | 応答は世界標準時。Skillが変換するのでフローでは触らない |
| 連続して依頼を出すと往復が10分以上に伸びる | フォルダ監視トリガーの検知間隔が絞られる。Skillは打ち切っても依頼IDで再開できる作り |
