---
name: record-sandbox-limitation
description: Use whenever a Claude Code sandbox/permission restriction blocks an attempted operation in this repo (network access, blocked file read/write, blocked command, etc.) and the cause has been confirmed. Appends a dated entry to doc/claude-code-sandbox-limitations.md so the finding isn't rediscovered later. Trigger phrases include "サンドボックスの制限を記録して", "これも制限事項に追記して", "制限リストに入れて". Do not use for limitations that are still unconfirmed or for one-off user preferences unrelated to sandboxing.
---

> ワークフロー上の位置: 工程Skillから参照されない独立した知識Skill。サンドボックス制限が判明した任意のタイミングで単独起動する(ワークフロー工程ではない)

# サンドボックス制限の記録

`doc/claude-code-sandbox-limitations.md` に、新たに判明したサンドボックス制限を追記するスキル。

## 手順

1. **対象ファイルを読む** — `doc/claude-code-sandbox-limitations.md` を読み、既存の構成(見出し、番号付けのスタイル、日本語の文体)を確認する。ファイルが存在しない場合はユーザーに確認する(このスキルは追記専用で、初回作成は想定していない)。

2. **重複チェック** — 今回の制限が既存の項目(「確認済みの制限事項」「試したが効果がなかった対処」)と実質的に同じでないか確認する。同じであれば新規追加せず、ユーザーにその旨を伝える。

3. **記録する内容を確認する** — 会話の中で以下が揃っているか確認し、不明な点はユーザーに聞く。
   - 何をしようとしたか(具体的なコマンド・操作)
   - 実際に出たエラー・拒否メッセージ(あれば原文のまま引用)
   - 原因として考えられる制限の種類(ネットワーク / ファイル読み取り / ファイル書き込み / プロセス / その他)
   - 回避を試みた場合、その方法と結果(成功・失敗)

4. **「確認済みの制限事項」に追記** — 既存の番号付きリストの末尾に新しい項目を追加する。フォーマットは既存項目に合わせる(見出し + 短い説明 + 該当すればエラーメッセージの引用)。

5. **回避策を試して失敗した場合** — 「試したが効果がなかった対処」相当のセクションがあれば、そこにも追記する。セクションがまだ無ければ新設してよい。

6. **検証日を更新** — ファイル先頭付近の検証日の記載(例: `検証日: 2026-07-15〜16`)を、今回の日付を含む範囲に更新する。

7. **確認して終了** — 追記した差分をユーザーに簡潔に示す。コミット・pushは行わない(別途明示的に依頼されない限り)。

## 注意

- 推測や未確認の内容は書かない。実際に試して確認できたことだけを記録する。
- 既存の文体(日本語、見出し構成)を崩さない。
- このファイル自体も含め `.claude/skills/` への書き込みはBashツール(`mkdir`/シェル経由)ではブロックされる場合がある。Writeツール/Editツールを使えば書き込めることを確認済み。
