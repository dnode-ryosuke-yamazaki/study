# study リポジトリ

複数アプリケーションを収容するモノレポです。会社支給のリポジトリという制約上、新規アプリもこのリポジトリ内に追加していきます。

構成方針の詳細・理由は [doc/adr/0001-multi-app-monorepo-layout.md](doc/adr/0001-multi-app-monorepo-layout.md) を参照してください。

## ディレクトリ構成

```
.
├── apps/
│   └── <app-name>/
│       ├── infra/          # Terraform一式（terraform initはここで実行）
│       └── application/    # アプリケーションコード（Lambda, クライアントSDK等）
├── doc/
│   └── adr/                 # Architecture Decision Record
└── README.md
```

## アプリ一覧

| アプリ | 内容 | 詳細 |
|---|---|---|
| notes-api | メモ管理API (AWS Lambda + API Gateway + DynamoDB) | [apps/notes-api/README.md](apps/notes-api/README.md) |

## 新しいアプリを追加するときは

1. `apps/<app-name>/infra/` にTerraform一式、`apps/<app-name>/application/` にアプリケーションコードを配置する
2. `apps/<app-name>/README.md` にセットアップ手順を記載する
3. 上記の「アプリ一覧」表に追加する
4. 構成方針自体を変える場合は `doc/adr/` に新しいADRを追加する

詳細は [doc/adr/0001-multi-app-monorepo-layout.md](doc/adr/0001-multi-app-monorepo-layout.md) を参照してください。
