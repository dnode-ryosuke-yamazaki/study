---
name: pr
description: PRを作成するときに使う。仕様承認PR(3点セット)と実装PRの2種類のテンプレート、仕様承認ゲートの運用、作成前チェック(impl-pr-reviewer・CI)を扱う。
---

> ワークフロー上の位置: [/spec-review](../spec-review/SKILL.md) → **仕様承認PR** → 承認後 [/implementation](../implementation/SKILL.md) … [/implementation-review](../implementation-review/SKILL.md) → **実装PR** → ユーザーがGitHub UIでマージ → 本番反映確認・ブランチ掃除(手動)

> **次フェーズのモデル:** 基本は **Sonnet**(トークン消費を抑えるため下流工程は原則Sonnetで運用する)
> - 仕様承認PR → [/implementation](../implementation/SKILL.md) へ: 複雑なロジック・複数の状態管理を伴う実装のみ **Opus** を検討する。なお後続の[/implementation-review](../implementation-review/SKILL.md)は安全網として原則Opusを使うため、ここは無理にOpusを選ばなくてよい
> - 実装PR → マージ後の本番反映確認へ: 確認作業は機械的なため **Sonnet** で十分

# 前提条件

- **仕様承認PR**: [/spec-review](../spec-review/SKILL.md)で指摘なし(🟢のみ)の結果を得ていること。レビュー未実施なら/spec-reviewから始める
- **実装PR**: [/implementation-review](../implementation-review/SKILL.md)で指摘なし(🟢のみ)の結果を得ていること。レビュー未実施なら/implementation-reviewから始める

# 共通ルール

- 作業は必ず`feature/<機能名>`ブランチで行い、mainに直接pushしない(マージ後の後続作業も同様に新しいブランチを切る)。複数の機能を並行して進める場合は[parallel-work](../parallel-work/SKILL.md)(worktree)を使い、ブランチの切り替えはしない
- ブランチの作成・コミットはローカルのgit操作のみで完結するため、ユーザーへの確認なしで進めてよい
- **push・PR作成・CI確認はサンドボックスから直接実行できないことが多い**(GitHubへの通信がブロックされる環境があるため。詳細は[doc/claude-code-sandbox-limitations.md](../../../doc/claude-code-sandbox-limitations.md))。ネットワーク制限のない環境ではこちらで`git push`・`gh pr create`・`gh pr checks`を直接実行してよいが、失敗する場合は以下の手順でユーザーに引き継ぐ:
  1. コミットまで済ませ、実行してほしいコマンドを提示する: `git push -u origin feature/<機能名>`
  2. 続けて、本文テンプレート(下記)で下書きしたタイトル・本文を埋め込んだPR作成コマンドを提示する:
     ```
     gh pr create --title "<タイトル>" --body "$(cat <<'EOF'
     <本文>
     EOF
     )"
     ```
     `gh`が使えない場合は、pushすると表示されるcompare URL、またはGitHub Web UIからPRを作成してもらう
  3. CI確認は`gh pr checks <PR番号>`をユーザーに実行してもらう(またはGitHub Web UIのChecksタブで確認してもらう)
  4. 実行後、作成されたPRのURLとCI結果をユーザーから報告してもらってから次のステップに進む
- ユーザーへの報告にはPR番号だけでなく完全なURLを明記する。URLは装飾なしの単独行に置く(`**`や括弧・日本語をURLに連結するとリンク検出が巻き込んで開けなくなる)
- mainへのマージはユーザーがGitHub UI上でdiffを確認して行う(こちらからマージしない)

# 仕様承認PR(仕様承認ゲート)

3点セット(requirements.md/design.md/tasks.md)を作成したら一旦PRを出し、ユーザーの確認・承認を得るまでコード(テストを含む)は書き始めない。

この段階ではrequirements.mdの先頭(タイトル直下)に`> ステータス: 仕様確認中(未実装)`という行を入れる。これは「テスト不要」という恒久的な判断ではなく、「まだ実装していないだけ」という一時的な状態を表す。実装(🔴Redのテスト)に着手し、仕様項目に対応するテストが書けたらこの行を削除する。

本文テンプレート:

```markdown
## 概要
(何のための機能か1〜2行)

## 作成・更新したspec
- apps/<アプリ名>/specs/<機能名>/(requirements.md / design.md / tasks.md)

## 判断に迷った点・レビューしてほしい点
- (仕様の分かれ道になった判断と、その根拠)

## 次のステップ
承認・マージ後、/implementation でTDD実装に着手します(承認までコードは書きません)。
```

# 実装PR

PR作成前にimpl-pr-reviewerエージェント(`.claude/agents/impl-pr-reviewer.md`)でチェックし、❌を解消してから作成する(承認ステータスマーカーの削除漏れ・CIの横断チェック)。

requirements.md/design.mdの各仕様項目にテストが紐づいているかを目視で確認する([/implementation](../implementation/SKILL.md)参照)。テストが不要と判断した項目がある場合は、その理由をPR本文か関連spec内に残す。

本文テンプレート:

```markdown
## 概要
(何を実装・修正したか1〜2行)

## 関連spec
- apps/<アプリ名>/specs/<機能名>/requirements.md

## 変更内容
- (主な変更点の箇条書き)

## テスト
- (該当アプリのテストコマンド): ✅ n件パス

## 動作確認
- (実際に確認した内容)
```

# 完了時の次ステップ案内

- 仕様承認PR → 作成されたPRのURLを確認し、ユーザーの承認・マージ後に[/implementation](../implementation/SKILL.md)へ進むことを案内する
- 実装PR → 作成されたPRのURLを確認し、ユーザーのマージ後に本番反映の確認(該当アプリのデプロイ手順に従う)と、不要になったブランチ・worktreeの掃除(`git worktree remove`・`git branch -d`)を行うことを案内する
