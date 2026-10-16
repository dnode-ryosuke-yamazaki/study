# Confluence の応答(実応答で差し替え待ち)

**このフォルダの fixture は、Atlassian の公式ドキュメント(REST API の `GET /wiki/rest/api/user/current` と `GET /wiki/rest/api/content/search` の応答例)の形に合わせて作ったもので、実応答ではない。** 作成時(2026-10-16)にサンドボックスから Confluence へ通信できなかったため。手元のターミナルで実応答を `tests/fixtures/_raw/` に取ったら、人名・メール・URL・アカウントID を置き換えてここに置き換え、テストが通るかを確かめる。

- `current_user.json`: `GET /wiki/rest/api/user/current` の応答。自分のアカウントIDは `5b10a2844c20165700ede21g`
- `search_version.json`: `GET /wiki/rest/api/content/search`(`expand=version`)の応答。対象の週は 2026-W41。`version.when` は UTC
  - 1001: 自分が火曜10時23分(日本時間)に直したページ(範囲内)
  - 1002: 最後の版が他の人のページ(対象外)
  - 1003: 自分が金曜17時ちょうどに直したページ(範囲外)
  - 1004: 自分が月曜0時ちょうどに直したページ(範囲内)
- `search_empty.json`: 該当するページが無いときの応答
- 人名は「利用者A」「利用者B」、サイトは `example.atlassian.net` に置き換えている
