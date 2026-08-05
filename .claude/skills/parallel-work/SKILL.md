---
name: parallel-work
description: 2つ以上の機能開発・修正を並行して進めるときに使う、study固有の補足。git worktreeの基本手順(作成・環境構築・掃除・注意事項)は全プロジェクト共通の`~/.claude/skills/parallel-work/SKILL.md`を参照。ここにはstudy固有の重複検出手順(specs/フォルダ)と環境構築の詳細のみを書く。
---

> ワークフロー上の位置: 工程Skillから参照される知識Skill。並行作業を始めるとき・終えるときに、まず `~/.claude/skills/parallel-work/SKILL.md`(worktreeの基本手順)を参照し、そのうえでこのファイルのstudy固有部分を確認する

# study固有: 他セッションとの重複を避ける

新しいspecフォルダを作る前([/requirement](../requirement/SKILL.md)のStep0、[/fix](../fix/SKILL.md)のStep1)に、以下を確認する:

- **`git worktree list`で他に動いているworktreeを確認し、そのディレクトリの`apps/<アプリ名>/specs/`を直接`ls`・`cat`で覗く。**
- **`git log --all --oneline -- 'apps/*/specs/**'`で、他のブランチ(未マージ含む)が同じspecパスを触っていないか確認する。**
- 上記で判断がつかない場合は、ユーザーに「他に並行して進めている作業はありますか」と確認する
- 重複が疑わしい機能に気づいたら、新規specフォルダの作成を保留し、状況をユーザーに報告してから進め方を決める

自分の作業も、requirements.mdの下書きができた時点など早めに区切ってコミットしておくと、他セッションから見つけてもらいやすくなる。

# study固有: 作業環境の構築

worktree作成後、Git管理外のファイルを対象アプリからコピーする:

```bash
cd ../study-<機能名>
cp ../study/apps/<アプリ名>/infra/terraform.tfvars apps/<アプリ名>/infra/
# 依存関係のインストールは対象アプリのpackage.json等がある階層で行う
```

# study固有: 並行してよい作業の条件(具体例)

- 別アプリ同士(`apps/<アプリ名>/`が異なる)なら安全。同じアプリの別機能は、共有する`lib/`・共通モジュールを両方が変更しないか先に確認する
