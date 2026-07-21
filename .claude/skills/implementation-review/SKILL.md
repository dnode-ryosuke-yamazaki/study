---
name: implementation-review
description: 実装完了後・PR作成前にコードをレビューするときに使う。仕様との整合・テスト・コード品質のチェックリスト、指摘の重要度基準、フィードバックテンプレートを含む。
---

> ワークフロー上の位置: [/implementation](../implementation/SKILL.md) → **/implementation-review(本Skill)** → 指摘あり: [/resolve](../resolve/SKILL.md) / 指摘なし: [/pr](../pr/SKILL.md)(実装PR)

> **次フェーズのモデル:** 基本は **Sonnet**(トークン消費を抑えるため下流工程は原則Sonnetで運用する)
> - 指摘あり → [/resolve](../resolve/SKILL.md) へ: 複雑なリファクタリング・アーキテクチャ変更など設計の再考が必要な場合のみ **Opus** を検討する
> - 指摘なし → [/pr](../pr/SKILL.md) へ: PR作成は機械的な作業のため **Sonnet** で十分

# 前提条件

- 実装が完了していること(テスト・lint・buildが通り、動作確認済み)。実装がまだなら[/implementation](../implementation/SKILL.md)または[/fix](../fix/SKILL.md)から始める
- 実装が承認済みの仕様(3点セット)または[/fix](../fix/SKILL.md)の判断(純粋なバグ・軽微な変更)に基づいていること。仕様なしで書かれた新機能のコードはレビューに進まず、[/requirement](../requirement/SKILL.md)で仕様から整える

# レビューの実施方法

レビューはcode-reviewerエージェント(`.claude/agents/code-reviewer.md`)を起動して行う。実装したメインスレッドの文脈から切り離し、新鮮な目でレビューするため。

- エージェントには対象のfeatureブランチと関連spec(`apps/<アプリ名>/specs/<機能名>/`)を伝えて起動する
- エージェントの報告(フィードバックテンプレート形式)は要約せずそのままユーザーに提示する

レビューの注意事項・チェックリスト・重要度基準・フィードバックテンプレートは[references/checklist.md](references/checklist.md)にあり、エージェントが直接読んで従う。**メインスレッドはこのファイルを読まない**(エージェントだけが使う内容を本体から分離し、二重読み込みを避けている)。エージェントを使えない状況でメインスレッドが直接レビューする場合のみ読み、同じ内容に従う。

# 完了時の次ステップ案内

- 🔴/🟡の指摘がある → [/resolve](../resolve/SKILL.md)で修正後、本Skillで再レビュー
- 指摘なし(🟢のみ) → [/pr](../pr/SKILL.md)で実装PRを作成する
