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
16. VS Code の拡張の知らせつきの依頼文(配列。1つ目の要素が `<ide_opened_file>…</ide_opened_file>` だけの文章、2つ目が人の打った文章)
17. VS Code の拡張の知らせつきの依頼文(文字列。`<ide_selection>…</ide_selection>` のあとに改行と人の打った文章が続く)
18. VS Code の拡張の知らせだけの行(配列。`<ide_opened_file>` の要素1つだけ。知らせを取り除くと本文が空になる)

`11111111-…/subagents/agent-a0000000000000002.jsonl`: サブエージェントへの指示文(`isSidechain: true`)。

実物の行の数の内訳(上の60ファイル): 人が打った依頼文(`origin.kind: human`)188、作業の終わりの知らせ102、スラッシュコマンド13、ローカルのコマンドの呼び出しと出力 各1。6〜9は appendix.md「会話の記録から依頼文を選ぶ条件」の表の条件をすべて満たす。

16〜18 は 2026-10-19 時点の実物(`~/.claude/projects/*/*.jsonl` で `<ide_` を含む利用者の発言の行)のタグの名前・閉じタグ・知らせの文面の型(`The user opened the file <パス> in the IDE. This may or may not be related to the current task.`、`The user selected the lines <n> to <m> from <パス>:` のあとに選んだ行と空行、同じ結びの一文)を残し、パスと本文を置き換えたもの。実物では知らせは配列の独立した要素として現れ(`<ide_opened_file>` 60、`<ide_selection>` 1)、文字列の本文の中に知らせが入る形(17)と知らせだけの行(18)は実物に無く、仕様の条件を確かめるために作ったもの。
