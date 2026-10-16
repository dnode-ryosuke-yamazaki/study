# JIRA の応答(実応答で差し替え待ち)

**このフォルダの fixture は、Atlassian の公式ドキュメント(REST API v3 の `GET /rest/api/3/myself` と `GET /rest/api/3/search/jql` の応答例)の形に合わせて作ったもので、実応答ではない。** 作成時(2026-10-16)にサンドボックスから JIRA へ通信できなかったため。手元のターミナルで実応答を `tests/fixtures/_raw/` に取ったら、人名・メール・URL・アカウントID を置き換えてここに置き換え、テストが通るかを確かめる(通らなければ実装か仕様が実物と違う)。

- `myself.json`: `GET /rest/api/3/myself` の応答。自分のアカウントIDは `5b10a2844c20165700ede21g`(公式ドキュメントの例の値)
- `search_changelog.json`: `GET /rest/api/3/search/jql`(`fields=summary`、`expand=changelog`)の応答。対象の週は 2026-W41(2026-10-05 月 0時〜2026-10-09 金 17時、日本時間)。変更履歴は新しい順に並ぶ
  - SAG-123: 金曜17時ちょうどの自分の変更(範囲外)・他の人の変更・範囲内の自分の変更(項目2つ)・日曜23時50分の自分の変更(検索の日付を広げたために入る範囲外)
  - SAG-130: 金曜16時59分59秒と月曜0時ちょうどの自分の変更(どちらも範囲内)。変更後の値が空の項目を含む
  - SAG-131: 自動化(`accountType: app`)による変更だけ
- `search_empty.json`: 該当するチケットが無いときの応答
- 人名は「利用者A」「利用者B」、サイトは `example.atlassian.net`、メールは `example.com` に置き換えている
