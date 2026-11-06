---
name: resolve
description: /spec-reviewや/implementation-review、またはPR上で受けたレビュー指摘を修正するときに使う。重要度順の対応、対応結果の報告テンプレートを扱う。プロジェクトが独自の`.claude/skills/resolve/SKILL.md`を持つ場合はそちらを優先する。
---

> ワークフロー上の位置: [/spec-review](../spec-review/SKILL.md) / [/implementation-review](../implementation-review/SKILL.md) / PR上のレビューコメント → **/resolve(本Skill)** → 指摘元のレビューを再実行 → 元の工程の次ステップへ。全体フロー・モデル対応表は[dev-flow.md](../../dev-flow.md)を参照

# 前提条件

- 対応対象のレビュー指摘([/spec-review](../spec-review/SKILL.md)・[/implementation-review](../implementation-review/SKILL.md)・PR上のコメント)があること。指摘を受けていない修正は[/fix](../fix/SKILL.md)(既存機能の改修)から始める

# 修正の進め方

- 重要度の高い順(🔴→🟡)に1件ずつ対応する。🟢(対応任意)は対応するかどうかを先に宣言してから進める
- 指摘に同意できない・修正すると別の問題が起きる場合は、黙って見送らず理由を添えてユーザーに確認する
- 実装コードの修正はTDDのサイクルを守る。挙動が変わる修正は、先にテストを直す/追加してから実装を変える([/implementation](../implementation/SKILL.md)参照)
- 仕様(3点セット)に影響する修正は、仕様書側も同じ変更で更新する(確認範囲は[/fix](../fix/SKILL.md)のStep2を参照)。直すファイルのフロントマターが `in-review` なら `draft` に戻し、`approved` なら `draft` に戻して `approved_date` を消し `version` を小数点以下1つ上げる(値の遷移の正は[dev-flow.mdの「承認状態のフロントマター」](../../dev-flow.md#承認状態のフロントマター))
- **判定条件・分岐の条件を変えたら、その条件を説明している文を全部開いて読み直す。** 実装だけ直して説明文が古い世代のまま残ると、次に読む人が古い条件を正として扱う。条件を表す語(「旧形式」のような判定名)で `grep -rn <語> <specフォルダ> .claude/skills` を掛け、ヒットした行を1つずつ最新の条件に揃える。読み直す先は design.md の処理フロー・決定事項の表・appendix.md・requirements.md の対応する `[n]`・その条件を書いている SKILL.md の5か所。**違反種別のような短い名前は機械で突き合わせられるが、条件の説明文は突き合わせられないので、この読み直しを省かない**
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

全件対応したら、指摘元のレビュー([/spec-review](../spec-review/SKILL.md)または[/implementation-review](../implementation-review/SKILL.md))を再実行して🔴/🟡が解消したことを確認する。

[/spec-review](../spec-review/SKILL.md)への対応で、次セッションへの[/implementation](../implementation/SKILL.md)引き継ぎプロンプトを用意する場合は、その前に対象tasks.mdの先頭に`> 実装中: session ...`マーカーが既に付いていないか確認する(他セッションが同じspecへ実装着手済みの可能性があるため)。マーカーがあれば、そのまま次セッションへ引き継がず、まずユーザーに状況を確認する。
