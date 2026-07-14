# 0001. 複数アプリを収容するモノレポ構成への移行

## ステータス

Accepted (2026-07-14)

## コンテキスト

これまでこのリポジトリは「notes-api」1アプリを作る前提でディレクトリ階層を組んでおり、Terraform一式（`*.tf`, `terraform.tfvars` など）をリポジトリ直下に、アプリケーションコードを `application/` に配置していた。

一方で、会社から支給されるリポジトリはこの1つに限定されており、今後追加する別のアプリ（別のTerraformインフラ・別のLambda/クライアントSDKなど）も同じリポジトリ内に置かざるを得ない。直下フラットな構成のままでは、アプリが増えるたびに `*.tf` ファイル名の衝突や、どのコードがどのアプリに属するかの判別が困難になる。

## 決定

リポジトリを以下のレイアウトに変更する。

```
.
├── apps/
│   └── <app-name>/
│       ├── infra/          # そのアプリのTerraform一式。terraform init/plan/apply はこのディレクトリ内で実行する
│       └── application/    # そのアプリのアプリケーションコード（Lambda実装、クライアントSDK、OpenAPI仕様等）
├── doc/
│   └── adr/                 # 本ファイルを含む Architecture Decision Record
└── README.md                 # リポジトリ全体の概要とアプリ一覧
```

- 既存の notes-api 一式（ルート直下の `*.tf` と `application/`）は `apps/notes-api/infra/` と `apps/notes-api/application/` にそのまま移動した。コードの中身・Terraformリソース定義は変更していない。
- 各アプリの `infra/` はそれぞれ独立した Terraform 実行単位（ワーキングディレクトリ）とする。State（`terraform.tfstate`）やプロバイダキャッシュ（`.terraform/`）もアプリごとに `apps/<app-name>/infra/` 配下に閉じる。リモートバックエンドを導入する場合もアプリ単位で分離する。
- 新しいアプリを追加する際は `apps/<app-name>/` を新設し、同じ `infra/` + `application/` の型に従う。共通の全体像・アプリ一覧はルートの `README.md` に記載し、各アプリの詳細はアプリごとの `README.md`（例: `apps/notes-api/README.md`）に記載する。
- リポジトリ横断の構成方針・大きな意思決定は `doc/adr/` にADRとして追加していく。

## 影響

- Terraformコマンドはリポジトリ直下ではなく `apps/<app-name>/infra/` 内で実行する運用に変わる。既存の手元環境（ローカルState・`.terraform/` ディレクトリ）は本移行と合わせて同じ相対位置に移動済みだが、各自の環境で `terraform init` を再実行し、パスの整合性を確認すること。
- `.gitignore` の Lambda ビルド成果物パスを `application/lambda/...` から `apps/*/application/lambda/...` に変更し、今後追加されるアプリにも同じパターンが適用されるようにした。`.terraform/` や `*.tfstate*` 等はパス非依存のパターンのため変更不要。
- 将来的に複数アプリで共通利用するコード・設定が出てきた場合は、`packages/` 等の共有ディレクトリを別途ADRで検討する（現時点では未導入）。
