# study リポジトリ

複数アプリケーションを収容するモノレポです。会社支給のリポジトリという制約上、新規アプリもこのリポジトリ内に追加していきます。

構成方針の詳細・理由は [doc/adr/0001-multi-app-monorepo-layout.md](doc/adr/0001-multi-app-monorepo-layout.md) を参照してください。

## ディレクトリ構成

```
.
├── apps/
│   └── <app-name>/
│       ├── infra/           # Terraform一式（terraform initはここで実行）
│       ├── application/     # アプリケーションコード（Lambda, クライアントSDK等）
│       └── specs/           # 機能ごとの仕様3点セット
│           ├── architecture.md  # アプリ全体像（機能マップ・採用技術・関連ADR）
│           ├── adr/             # このアプリ内で完結する設計判断の記録（任意）
│           └── <feature-name>/  # requirements.md / design.md / tasks.md
├── specs/
│   └── <feature-name>/      # 特定のappsに属さない横断的なCI/tooling機能の仕様
├── doc/
│   └── adr/                 # 複数アプリにまたがる技術選定・方針のADR
├── CLAUDE.md                # リポジトリ運用ルール（AGENTS.mdはこれへのシンボリックリンク）
└── README.md
```

specs/ の詳しい配置規約は [CLAUDE.md](CLAUDE.md#specs-フォルダ規約) を参照してください。

## アプリ一覧

| アプリ | 内容 | 詳細 | アーキテクチャ |
|---|---|---|---|
| notes-api | メモ管理API (AWS Lambda + API Gateway + DynamoDB) | [apps/notes-api/README.md](apps/notes-api/README.md) | - |
| teams-transcript-fetcher | Teams会議のトランスクリプト自動収集バッチ (Python + launchd + Power Automate連携) | [apps/teams-transcript-fetcher/README.md](apps/teams-transcript-fetcher/README.md) | [apps/teams-transcript-fetcher/specs/architecture.md](apps/teams-transcript-fetcher/specs/architecture.md) |
| meeting-minutes-generator | 会議トランスクリプトからの議事録自動生成バッチ (Python + launchd + claude CLI + Power Automate連携) | [apps/meeting-minutes-generator/README.md](apps/meeting-minutes-generator/README.md) | [apps/meeting-minutes-generator/specs/architecture.md](apps/meeting-minutes-generator/specs/architecture.md) |
| meeting-setup-automation | 空き時間からの会議候補提示とTeams会議の自動作成 (Claude Code Skill + Power Automate連携) | - | [apps/meeting-setup-automation/specs/architecture.md](apps/meeting-setup-automation/specs/architecture.md) |

## 新しいアプリを追加するときは

1. `apps/<app-name>/infra/` にTerraform一式、`apps/<app-name>/application/` にアプリケーションコードを配置する
2. `apps/<app-name>/README.md` にセットアップ手順と、テスト・lint・buildのコマンドを記載する
3. `apps/<app-name>/specs/` を作成する
4. 上記の「アプリ一覧」表に追加する
5. 構成方針自体を変える場合は `doc/adr/` に新しいADRを追加する

詳細は [doc/adr/0001-multi-app-monorepo-layout.md](doc/adr/0001-multi-app-monorepo-layout.md) を参照してください。
