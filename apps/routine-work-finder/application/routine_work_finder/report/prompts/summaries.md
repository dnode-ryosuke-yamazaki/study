## 頼むこと

材料の `items` は、その週に作業の時間が長かったアプリ名とウィンドウの題名の組です。各項目で何をしていたかの要約と具体例を作ってください。

- 具体例(`examples`)は、その項目の題名・カーソルのある部品の種類・時間帯と、同じ時間帯に重なる既存の作業の記録・メモから出せることだけで書くこと
- `titleKnown` が偽の項目は題名が取れなかった組なので、前後に使ったアプリ・既存の作業の記録・メモから推定し、`estimated` を真にして要約に「推定」と書くこと

## 材料の項目

- `items[].id`: 項目の番号。応答の `id` にこの番号を書き、渡した番号をすべて返す
- `items[].app`・`title`・`sheet`: アプリ名・ウィンドウの題名・Excel のシート名
- `items[].focusRole`: 組の中で最も長くカーソルがあった部品の種類(例: `AXTable` は表、`AXTextArea` は入力欄)
- `items[].totalMinutes`・`mainTimes`: 合計の分・主な時間帯(曜日と時刻)
- `items[].neighborApps`: 前後に使ったアプリ。`{"t": …, "excluded": true}` は記録しない設定で除外中だった時間で、中身は分からない
- `items[].overlappingRecords`・`memos`: 同じ時間帯に重なる既存の作業の記録とメモ

## 応答の形

```json
{
  "items": [
    {
      "id": "w1",
      "summary": "BL-057 の作業ページで実現性確認の結果を書いていた。",
      "estimated": false,
      "examples": [{ "t": "2026-10-05T13:20:00+09:00", "text": "…" }]
    }
  ]
}
```

- 必須: `id`・`summary`・`estimated`・`examples`
- `summary` は1〜2文で200字まで
- `examples` は3件まで。`t` はその週の中の日時(ISO 8601、時刻帯つき)
