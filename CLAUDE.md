# study リポジトリ運用ルール

会社支給の制約で複数アプリを1つのリポジトリに収容するモノレポ。全体構成は[README.md](README.md)を参照。

## 開発ワークフロー

このプロジェクトの開発作業(機能追加・既存機能の修正・仕様作成・レビュー・PR作成)は `.claude/skills/` 配下のSkillとして手順化されている。作業を始める前に [.claude/skills/README.md](.claude/skills/README.md) の一覧・遷移図を確認すること。

- 入口: 新しい機能・アプリ → `/requirement`、既存機能のバグ・小規模改修 → `/fix`、方針の壁打ち → `/consult`
- **要件定義より前にコードを書かない。** 3点セット(requirements.md/design.md/tasks.md)の仕様承認PRがマージされるまで実装(テストを含む)には着手しない。例外は仕様に影響しない純粋なバグ修正・軽微な変更のみ(`/fix` の「仕様承認の要否」で判断し、承認ゲートなしで修正してよい)
- 2つ以上の機能を並行して進める場合は `git checkout`/`git switch` によるブランチの往復ではなく、git worktree を使う。基本手順は `~/.claude/skills/parallel-work/SKILL.md`(全プロジェクト共通、`~/.claude/hooks/enforce-worktree.sh` が強制)、study固有の重複検出・環境構築は `.claude/skills/parallel-work/SKILL.md` を参照

## specs/ フォルダ規約

機能ごとの仕様3点セットは、対象アプリの配下に置く:

```
apps/<app-name>/
├── infra/                          # 既存(Terraform)
├── application/                    # 既存(アプリケーションコード)
└── specs/
    ├── architecture.md             # アプリ全体像(機能マップ・採用技術・関連ADR)。任意
    ├── adr/                        # このアプリ内で完結する設計判断の記録。アプリごとに0001から採番。任意
    └── <feature-name>/
        ├── requirements.md
        ├── design.md                # 分岐のない単純な機能では省略可
        └── tasks.md
```

- 1機能(1ユーザーストーリー)= 1 `specs/<feature-name>/` フォルダが原則。既存機能の修正か新規機能かの判断基準は `.claude/skills/requirement/SKILL.md` のStep0を参照
- `apps/<app-name>/specs/architecture.md` の作成基準・書き方は `.claude/skills/architecture-workflow/SKILL.md` を参照
- **仕様書(requirements.md/design.md/architecture.md)には常に今の正しい仕様だけを現在形で書く。** 変更の経緯・履歴・移設マーカー・内輪の呼称・合意日付は書かず、書き換えるときはあたかも最初からその仕様だったかのように書き直す(詳細は `.claude/skills/requirement/SKILL.md` の「仕様書は『最新仕様のみ』を書く」)
- 経緯・決定理由を残す必要がある場合は仕様書に書かずADRに分離する。**複数アプリにまたがる技術選定・方針**(DB・ホスティング・認証基盤・CI基盤など)は `doc/adr/`(リポジトリ全体で連番)、**1アプリ内で完結する設計判断**は `apps/<app-name>/specs/adr/`(アプリごとに0001から採番)に置く。仕様書からは必要ならリンクだけを張る
- 特定の`apps/<app-name>/`に属さない、リポジトリ横断のCI/tooling機能(例: JIRA連携などの`.github/workflows/`)の仕様3点セットは、上記構成の例外としてリポジトリ直下`specs/<feature-name>/`に置く(例: `doc/adr/0002-jira-automation-via-github-actions.md`)

## コマンド(テスト・lint・build)

アプリごとのコマンドの探し方は `~/.claude/CLAUDE.md`(全プロジェクト共通)の「モノレポ・サブプロジェクトのコマンド確認」を参照(`apps/<app-name>/README.md` にコマンドを定義する)。

study固有の現状:
- `apps/notes-api/application/client/typescript-sdk/`: `npm run lint` / `npm run format` (テストコマンド未整備)
- `apps/notes-api/application/lambda/`: Python 3.11のLambda関数。テストフレームワーク未導入

## Claude Codeサンドボックスの制限

VSCode拡張(FleetView)経由でのBashツール実行には制限がある。これはstudy固有ではなくこの環境自体の制約であり、制限一覧・回避策・許可プロンプトを減らす運用方針は `~/.claude/CLAUDE.md` / `~/.claude/sandbox-limitations.md`(全プロジェクト共通)を参照する。新しい制限に気づいたら `record-sandbox-limitation` スキルで同ファイルに追記する(このリポジトリ固有のファイルは持たない)。
