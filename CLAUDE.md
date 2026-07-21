# study リポジトリ運用ルール

会社支給の制約で複数アプリを1つのリポジトリに収容するモノレポ。全体構成は[README.md](README.md)を参照。

## 開発ワークフロー

このプロジェクトの開発作業(機能追加・既存機能の修正・仕様作成・レビュー・PR作成)は `.claude/skills/` 配下のSkillとして手順化されている。作業を始める前に [.claude/skills/README.md](.claude/skills/README.md) の一覧・遷移図を確認すること。

- 入口: 新しい機能・アプリ → `/requirement`、既存機能のバグ・小規模改修 → `/fix`、方針の壁打ち → `/consult`
- **要件定義より前にコードを書かない。** 3点セット(requirements.md/design.md/tasks.md)の仕様承認PRがマージされるまで実装(テストを含む)には着手しない
- 2つ以上の機能を並行して進める場合は `git checkout`/`git switch` によるブランチの往復ではなく、`.claude/skills/parallel-work/SKILL.md` の手順で git worktree を使う(`.claude/hooks/enforce-worktree.sh` が強制する)

## specs/ フォルダ規約

機能ごとの仕様3点セットは、対象アプリの配下に置く:

```
apps/<app-name>/
├── infra/                          # 既存(Terraform)
├── application/                    # 既存(アプリケーションコード)
└── specs/
    ├── architecture.md             # アプリ全体像(機能マップ・採用技術・関連ADR)。任意
    └── <feature-name>/
        ├── requirements.md
        ├── design.md                # 分岐のない単純な機能では省略可
        └── tasks.md
```

- 1機能(1ユーザーストーリー)= 1 `specs/<feature-name>/` フォルダが原則。既存機能の修正か新規機能かの判断基準は `.claude/skills/requirement/SKILL.md` のStep0を参照
- `apps/<app-name>/specs/architecture.md` の作成基準・書き方は `.claude/skills/architecture-workflow/SKILL.md` を参照
- 複数アプリにまたがる技術選定(DB・ホスティング・認証基盤など)は `doc/adr/` にADRとして残す。1アプリ内に閉じた設計判断はarchitecture.md/design.mdに書き、ADRにはしない

## コマンド(テスト・lint・build)

このリポジトリはアプリごとに技術スタックが異なりうるため、リポジトリ全体で共通のテスト・lint・buildコマンドは存在しない。各アプリのコマンドは `apps/<app-name>/README.md` に定義する(未整備のアプリでは、Skillの手順内にある `npm test` 等の記述はプレースホルダとして読み替える、またはその場でコマンドが無い旨を確認する)。

現状:
- `apps/notes-api/application/client/typescript-sdk/`: `npm run lint` / `npm run format` (テストコマンド未整備)
- `apps/notes-api/application/lambda/`: Python 3.11のLambda関数。テストフレームワーク未導入

## Claude Codeサンドボックスの制限

VSCode拡張(FleetView)経由でのBashツール実行には制限がある。詳細と回避策は [doc/claude-code-sandbox-limitations.md](doc/claude-code-sandbox-limitations.md) を参照(ネットワークアクセス不可、`.claude/`直下へのBash経由書き込み不可など)。`git push`・PR作成など外部ネットワークを要する操作は、ユーザーに手元のターミナルでの実行を依頼する。
