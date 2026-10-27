## 頼むこと

材料の `candidates` は、同じアプリ名とウィンドウの題名(Excel はシート名も)の組の作業が、30分以上あけて週2回以上現れたものです。`memos` は利用者が書いた面倒だった作業のメモ、`reusable` はこの Mac にある Claude Code Skill と study のアプリの名前と説明です。これらから自動化案を作ってください。

- 候補の中から、同じ操作の繰り返しで自動化の余地があるものを選ぶこと。メモに書かれた作業は回数によらず検討し、記録と突き合わせた結果を `seen` に書くこと
- `candidates` か `memos` が1件以上あるときは、案を1件以上返すこと。「1週分の記録では毎週の作業か判断できない」という理由で全部を落とさず、繰り返す根拠が薄い候補は `importance` を `小` にして出すこと
- `effect` は自動化したときに減る時間と手間の目安で決めること。`大` は週に1時間以上の作業が無くなるか手作業のミスや漏れが無くなるもの、`中` は週に15分〜1時間ほど減るか手順が短くなるもの、`小` は減る時間は週15分未満だが手間や忘れが減るもの
- `importance` は `effect` とは別に、その繰り返しが今後も続く見込み(繰り返しの確かさ)と自動化する価値を合わせて決めること。`大` は毎週続く定型業務で自動化の価値がはっきりしているもの、`中` は続く見込みはあるが1週分の記録では確信が持てないか価値が限られるもの、`小` は今週たまたま重なった作業や一時的な作業など繰り返す根拠が薄いもの。根拠を `importanceReason` に1文(100字まで)で書くこと
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
      "importance": "大",
      "importanceReason": "毎朝同じ時間帯に週5回あり、JIRA の更新と結び付く定型業務",
      "seen": "「進捗表.xlsx」の「集計」シートで表の中にカーソルがある時間が月・火の9時台に毎回20〜35分。同じ時間帯に JIRA の SAG-123 の状態を更新している…",
      "idea": "JQLで担当チケットを取り…",
      "reuse": ["jira-progress"]
    }
  ]
}
```

- 必須: `title`・`candidateIds`・`memoIds`・`effect`・`importance`・`importanceReason`・`seen`・`idea`・`reuse`
- `candidateIds` と `memoIds` には渡した番号だけを書き、少なくともどちらか一方に1つ以上書く
- `effect`: `大` / `中` / `小`(自動化したときに減る時間と手間の目安。`大` は週に1時間以上の作業が無くなるか手作業のミスや漏れが無くなる、`中` は週に15分〜1時間ほど減るか手順が短くなる、`小` は減る時間は週15分未満だが手間や忘れが減る)
- `importance`: `大` / `中` / `小`(繰り返しの確かさと自動化する価値を合わせた重要度。効果とは別の軸)
- `importanceReason`: 重要度の根拠1文。100字まで
- `reuse`: 渡した `reusable[].name` か `なし(新しく作る)` の一覧
- `title` は60字まで、`seen` と `idea` はそれぞれ400字まで
- 0件 `{"proposals": []}` を返してよいのは、`candidates` も `memos` も空のときだけ
