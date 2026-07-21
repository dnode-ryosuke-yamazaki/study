---
name: resolve
description: /spec-reviewや/implementation-review、またはPR上で受けたレビュー指摘を修正するときに使う。重要度順の対応、対応結果の報告テンプレートを扱う。
---

> ワークフロー上の位置: [/spec-review](../spec-review/SKILL.md) / [/implementation-review](../implementation-review/SKILL.md) → **/resolve(本Skill)** → 指摘元のレビューを再実行 → [/pr](../pr/SKILL.md)

> **次フェーズのモデル(レビュー再実行):** 基本は **Sonnet**。複数の指摘に関連する修正・ビジネスルール全体の見直しなど、根拠の再構築が必要な場合のみ **Opus** を検討する

# 前提条件

- 対応対象のレビュー指摘([/spec-review](../spec-review/SKILL.md)・[/implementation-review](../implementation-review/SKILL.md)・PR上のコメント)があること。指摘を受けていない修正は[/fix](../fix/SKILL.md)(既存機能の改修)から始める

# 修正の進め方

- 重要度の高い順(🔴→🟡)に1件ずつ対応する。🟢(対応任意)は対応するかどうかを先に宣言してから進める
- 指摘に同意できない・修正すると別の問題が起きる場合は、黙って見送らず理由を添えてユーザーに確認する
- 実装コードの修正はTDDのサイクルを守る。挙動が変わる修正は、先にテストを直す/追加してから実装を変える([/implementation](../implementation/SKILL.md)参照)
- 仕様(3点セット)に影響する修正は、仕様書側も同じ変更で更新する(確認範囲は[/fix](../fix/SKILL.md)のStep2を参照)
- 指摘されていない箇所のついで修正はしない(気づいた問題は別の指摘・別のタスクとして報告する)

# 対応結果の報告テンプレート

```markdown
## 指摘対応の結果

| # | 重要度 | 指摘 | 対応 | 内容 |
|---|---|---|---|---|
| 1 | 🔴 must | ... | ✅修正 | 何をどう直したか |
| 2 | 🟢 info | ... | ⏭見送り | 見送りの理由(ユーザー合意済みであること) |
```

対応の区分: **✅修正** / **💬回答**(修正せず理由を説明) / **⏭見送り**(ユーザー合意のうえ対応しない)

# 完了時の次ステップ案内

全件対応したら、指摘元のレビュー([/spec-review](../spec-review/SKILL.md)または[/implementation-review](../implementation-review/SKILL.md))を再実行して🔴/🟡が解消したことを確認し、[/pr](../pr/SKILL.md)へ進むことを案内する。
