## 頼むこと

材料の `candidates` は、同じアプリ名とウィンドウの題名(Excel はシート名も)の組の作業が、30分以上あけて週2回以上現れたものです。`memos` は利用者が書いた面倒だった作業のメモ、`reusable` はこの Mac にある Claude Code Skill と study のアプリの名前と説明です。これらから自動化案を作ってください。

- 候補の中から、同じ操作の繰り返しで自動化の余地があるものを選ぶこと。メモに書かれた作業は回数によらず検討し、記録と突き合わせた結果を `seen` に書くこと
- `reuse` は `reusable` の名前から選び、無ければ `なし(新しく作る)` とすること

## 材料の項目

- `candidates[].id`: 候補の番号。案に結び付けるときは `candidateIds` にこの番号を書く
- `candidates[].app`・`title`・`sheet`: アプリ名・ウィンドウの題名・Excel のシート名
- `candidates[].focusRole`: 組の中で最も長くカーソルがあった部品の種類(例: `AXTable` は表、`AXTextArea` は入力欄)
- `candidates[].sessions`・`totalMinutes`・`when`: 作業のまとまりの数・合計の分・まとまりごとの曜日と時刻
- `candidates[].overlappingRecords`: 同じ時間帯に重なる既存の作業の記録(`jira`・`confluence`・`claudeCode`・`minutes`)
- `memos[].id`: メモの番号。案に結び付けるときは `memoIds` にこの番号を書く

## 応答の形

```json
{
  "proposals": [
    {
      "title": "JIRAの状態を進捗表へ転記する作業",
      "candidateIds": ["c1", "c4"],
      "memoIds": [],
      "effect": "大",
      "seen": "「進捗表.xlsx」の「集計」シートで表の中にカーソルがある時間が月・火の9時台に毎回20〜35分。同じ時間帯に JIRA の SAG-123 の状態を更新している…",
      "idea": "JQLで担当チケットを取り…",
      "reuse": ["jira-progress"]
    }
  ]
}
```

- 必須: `title`・`candidateIds`・`memoIds`・`effect`・`seen`・`idea`・`reuse`
- `candidateIds` と `memoIds` には渡した番号だけを書き、少なくともどちらか一方に1つ以上書く
- `effect`: `大` / `中` / `小`
- `reuse`: 渡した `reusable[].name` か `なし(新しく作る)` の一覧
- `title` は60字まで、`seen` と `idea` はそれぞれ400字まで
- 0件のときは `{"proposals": []}`
