# Claude Code の会話の記録(本文と作業フォルダを置き換えたもの)

このMacの `~/.claude/projects/<フォルダ>/<sessionId>.jsonl`(2026-10-16 時点で更新の新しい60ファイル)と `<sessionId>/subagents/agent-*.jsonl` の実物から、行の種類ごとに項目の並び・値の型・判定に使う値(`type`・`toolUseResult` の有無・`message.content` の形・`isMeta`・`isSidechain`・`isCompactSummary`・`entrypoint`・`origin`・`timestamp` の書式)だけを残し、本文・作業フォルダ・ID・日時を置き換えたもの。作業フォルダは `/Users/example/repo/sample`、日時は 2026-W41 の中(UTC の `Z` 付き)。

`-Users-example-repo-sample/11111111-…jsonl` の行(上から):

1. 人が打った依頼文(文字列)。200字を超え、メールアドレスとトークンらしい文字列を含む(どちらも作り物)
2. Claude の返答(`type: assistant`)
3. ツールの結果(`toolUseResult` あり、`tool_result` の要素だけの配列)
4. 補助の印(`isMeta: true`)
5. 人が打った依頼文(画像と文章2つの配列)
6. スラッシュコマンドで打った依頼(`<command-message>`・`<command-name>`・`<command-args>` で包まれた文字列。`origin.kind: human`)
7. ローカルのコマンドの呼び出し(`<command-name>` で始まる文字列。`origin` なし)
8. ローカルのコマンドの出力(`<local-command-stdout>` で包まれた文字列。`origin` なし)
9. バックグラウンドの作業の終わりの知らせ(`<task-notification>` で包まれた文字列。中に `<output-file>` のパスと `<result>` の結果を持つ。`origin.kind: task-notification`)
10. 会話の要約(`isCompactSummary: true`)
11. ヘッドレス(`entrypoint: sdk-cli`)
12. 日曜 23:59:59.999(日本時間)の依頼文(週の範囲の外)
13. 月曜 0:00(日本時間)の依頼文(週の範囲の内)
14. 添付(`type: attachment`)
15. 会話の題名(`type: ai-title`)

`11111111-…/subagents/agent-a0000000000000002.jsonl`: サブエージェントへの指示文(`isSidechain: true`)。

実物の行の数の内訳(上の60ファイル): 人が打った依頼文(`origin.kind: human`)188、作業の終わりの知らせ102、スラッシュコマンド13、ローカルのコマンドの呼び出しと出力 各1。6〜9は appendix.md「会話の記録から依頼文を選ぶ条件」の表の条件をすべて満たす。
