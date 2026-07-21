---
name: spec-review
description: 仕様3点セット(requirements.md/design.md/tasks.md)を承認PRに出す前にレビューするときに使う。チェックリスト・指摘の重要度基準・フィードバックテンプレートを含む。
---

> ワークフロー上の位置: [/design](../design/SKILL.md) → **/spec-review(本Skill)** → 指摘あり: [/resolve](../resolve/SKILL.md) / 指摘なし: [/pr](../pr/SKILL.md)(仕様承認PR)

> **次フェーズのモデル:** 基本は **Sonnet**(トークン消費を抑えるため下流工程は原則Sonnetで運用する)
> - 指摘あり → [/resolve](../resolve/SKILL.md) へ: 複数ルール間の矛盾・根本的な設計変更など、根拠の再構築が必要な指摘に限り **Opus** を検討する
> - 指摘なし → [/pr](../pr/SKILL.md) へ: 実装フェーズも **Sonnet** が基本。複雑なロジック・複数の状態管理を伴う実装のみ **Opus** を検討する

# 前提条件

- 対象の`apps/<アプリ名>/specs/<機能名>/requirements.md`が存在すること。なければ[/requirement](../requirement/SKILL.md)から始める
- design.md/tasks.mdが存在すること(分岐のない単純な機能でrequirements.mdのみと判断した場合を除く。判断基準は[/design](../design/SKILL.md))。未作成なら[/design](../design/SKILL.md)から始める

# レビューの実施方法

レビューはspec-reviewerエージェント(`.claude/agents/spec-reviewer.md`)を起動して行う。仕様を書いたメインスレッドの文脈から切り離し、新鮮な目でレビューするため。

- エージェントには対象の`apps/<アプリ名>/specs/<機能名>/`を伝えて起動する
- エージェントの報告(フィードバックテンプレート形式)は要約せずそのままユーザーに提示する

レビューの注意事項・チェックリスト・重要度基準・フィードバックテンプレートは[references/checklist.md](references/checklist.md)にあり、エージェントが直接読んで従う。**メインスレッドはこのファイルを読まない**(エージェントだけが使う内容を本体から分離し、二重読み込みを避けている)。エージェントを使えない状況でメインスレッドが直接レビューする場合のみ読み、同じ内容に従う。

# 完了時の次ステップ案内

- 🔴/🟡の指摘がある → [/resolve](../resolve/SKILL.md)で修正後、本Skillで再レビュー
- 指摘なし(🟢のみ) → [/pr](../pr/SKILL.md)で仕様承認PRを作成し、ユーザーの承認を得る
