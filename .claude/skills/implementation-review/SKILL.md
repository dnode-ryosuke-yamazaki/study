---
name: implementation-review
description: 実装完了後・PR作成前にコードをレビューするときに使う。仕様との整合・テスト・コード品質のチェックリスト、指摘の重要度基準、フィードバックテンプレートを含む。プロジェクトが独自の`.claude/skills/implementation-review/SKILL.md`を持つ場合はそちらを優先する。
---

> ワークフロー上の位置: [/implementation](../implementation/SKILL.md) → **/implementation-review(本Skill)** → 指摘あり: [/resolve](../resolve/SKILL.md) / 指摘なし: [/pr](../pr/SKILL.md)(実装PR)。全体フロー・モデル対応表は[dev-flow.md](../../dev-flow.md)を参照

# 前提条件

- 実装が完了していること(テスト・lint・buildが通り、動作確認済み)。実装がまだなら[/implementation](../implementation/SKILL.md)または[/fix](../fix/SKILL.md)から始める
- 実装が承認済みの仕様(3点セット)または[/fix](../fix/SKILL.md)の判断(純粋なバグ・軽微な変更)に基づいていること。仕様なしで書かれた新機能のコードはレビューに進まず、[/requirement](../requirement/SKILL.md)で仕様から整える
- **未取り込みの委任worktreeが残っていないこと**(agent-routingの担当マーク方式を使っている場合)。委任ブランチの命名規則に一致するworktreeが残っていれば、code-reviewerを起動する前に[/implementation](../implementation/SKILL.md)の「委任結果の取り込み」と「委任1件ごとの消費の記録」を済ませる。「委任1件ごとの消費の記録」の前に、[/design](../design/SKILL.md)の「クレジット残量の記録」の手順1〜3で記録を有効にする前処理を行う(取り込みが別セッション・別の日でも、リセット日を越えた記録に消費を積まないため)。実消費は委任worktreeの`copilot-usage.json`から読み取り、読み取れなければ暫定計上(セッション上限ぶん)のまま進む。プラン値の貼り付けはユーザーに求めない(貼り付けがあれば任意の補正として受け付ける)。変更が一切なく`copilot-usage.json`も無い場合はCopilot CLIを起動したかどうかをユーザーに確認し、実行を待つかclaude引き取りに切り替えるかを決める

# レビューの実施方法

レビューはcode-reviewerエージェント(Agentツールの`subagent_type`は`code-reviewer`。定義は`.claude/agents/code-reviewer.md`)を起動して行う。実装したメインスレッドの文脈から切り離し、新鮮な目でレビューするため。

- エージェントには対象のfeatureブランチと関連spec(ローカルミラーパス)を伝えて起動する
- エージェントの報告(フィードバックテンプレート形式)は要約せずそのままユーザーに提示する
- エージェントの既定モデルはOpus([dev-flow.md](../../dev-flow.md)のモデル対応表参照)。文言修正のみなど明らかに軽微な変更に限り、起動時に`model: sonnet`で上書きしてよい

レビューの注意事項・チェックリスト・重要度基準・フィードバックテンプレートは[quality-standards/base/implementation-review.md](../../quality-standards/base/implementation-review.md)にあり、エージェントが直接読んで従う(会社標準・プロジェクト固有の追加項目があればcompany層・project層も合成する。合成ルールは[quality-standards/README.md](../../quality-standards/README.md))。**メインスレッドはこれらのファイルを読まない**(エージェントだけが使う内容を本体から分離し、二重読み込みを避けている)。エージェントを使えない状況でメインスレッドが直接レビューする場合のみ読み、同じ内容に従う。

# 完了時の次ステップ案内

- 🔴/🟡の指摘がある → [/resolve](../resolve/SKILL.md)で修正後、本Skillで再レビュー
- 指摘なし(🟢のみ) → [/pr](../pr/SKILL.md)で実装PRを作成する
