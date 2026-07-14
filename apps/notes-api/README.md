# Notes API

メモ管理APIのインフラ・アプリケーション構成です。  
AWS Lambda + API Gateway + DynamoDB を Terraform で構築します。

このアプリはモノレポ内の `apps/notes-api/` に配置されています。複数アプリの収容方針については [doc/adr/0001-multi-app-monorepo-layout.md](../../doc/adr/0001-multi-app-monorepo-layout.md) を参照してください。

## 概要

| 項目 | 内容 |
|---|---|
| クラウド | AWS (ap-northeast-1) |
| IaC | Terraform ~> 5.0 |
| ランタイム | Python 3.11 |
| API仕様 | OpenAPI 3.0.3 |

## アーキテクチャ

```
クライアント
    ↓
API Gateway (REST API)
    ↓
Lambda (lambda_function.py)
    ↓
DynamoDB
  ├── notes-table        # メモデータ
  └── api-logs-table     # API呼び出し履歴
```

暗号化: KMS CMK によるDynamoDBテーブル暗号化  
ログ: CloudWatch Logs (Lambda / API Gateway)

## ディレクトリ構成

```
apps/notes-api/
├── infra/                      # Terraform一式（このアプリのルート）
│   ├── api_gateway.tf          # API Gateway定義
│   ├── dynamodb.tf             # DynamoDBテーブル定義
│   ├── iam.tf                  # IAMロール・ポリシー定義
│   ├── kms.tf                  # KMS暗号化キー定義
│   ├── lambda.tf               # Lambda関数・CloudWatch定義
│   ├── outputs.tf              # 出力値定義
│   ├── provider.tf             # AWSプロバイダー設定
│   ├── variables.tf            # 変数定義
│   └── terraform.tfvars        # 変数値（環境名など）
└── application/
    ├── openapi.yaml            # API仕様定義 (OpenAPI 3.0.3)
    ├── lambda/
    │   ├── lambda_function.py  # Lambda関数実装
    │   └── package_lambda.sh   # デプロイZIP生成スクリプト
    └── client/
        ├── python-sdk/
        └── typescript-sdk/
```

## 前提条件

- Terraform >= 1.0
- Python 3.11+
- AWS CLI（認証設定済み）
- `aws configure` でデプロイ先アカウントの認証情報を設定済みであること

## セットアップ

リポジトリルートからの相対パスで記載しています。

### 1. Lambda パッケージのビルド

```bash
cd apps/notes-api/application/lambda
bash package_lambda.sh
cd -
```

### 2. Terraform 初期化

Terraformコマンドは必ず `apps/notes-api/infra/` の中で実行します。

```bash
cd apps/notes-api/infra
terraform init
```

### 3. 環境名の設定（任意）

`apps/notes-api/infra/terraform.tfvars` に環境名を指定します。

```hcl
environment = "yamazaki-dev"
```

指定しない場合は `variables.tf` のデフォルト値 (`yamazaki-dev`) が使用されます。

### 4. デプロイ

```bash
# apps/notes-api/infra/ の中で実行
terraform plan
terraform apply
```

apply 完了後、以下の出力値が表示されます。

```
api_gateway_url    = "https://xxxxx.execute-api.ap-northeast-1.amazonaws.com/{env}/notes"
notes_table_name   = "notes-table-{env}"
api_logs_table_name = "api-logs-table-{env}"
lambda_function_name = "hello-world-function-{env}"
```

## API エンドポイント

ベースURL: `terraform output -raw api_gateway_url`（`apps/notes-api/infra/` 内で実行）

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/notes?userId={userId}` | メモ一覧取得 |
| POST | `/notes?userId={userId}` | メモ作成 |
| GET | `/notes/{noteId}` | メモ取得 |
| PUT | `/notes/{noteId}` | メモ更新 |
| DELETE | `/notes/{noteId}` | メモ削除 |

詳細は [application/openapi.yaml](application/openapi.yaml) を参照してください。

## 使用例

```bash
BASE_URL=$(terraform output -raw api_gateway_url)  # apps/notes-api/infra/ 内で実行

# メモ作成
curl -X POST "$BASE_URL?userId=user123" \
  -H 'Content-Type: application/json' \
  -d '{"title":"会議メモ","content":"本文"}'

# メモ一覧取得
curl "$BASE_URL?userId=user123"
```

## APIクライアント（言語別）

クライアントの違いが分かるように、言語ごとにフォルダを分離しています。

- Python SDK: `application/client/python-sdk/notes_client/`
- TypeScript SDK (React向け): `application/client/typescript-sdk/`

### Python SDK

- 実装: `application/client/python-sdk/notes_client/client.py`
- エントリポイント: `application/client/python-sdk/notes_client/__init__.py`

利用例:

```python
from notes_client import NotesClient

# api_gateway_url は .../{env}/notes 形式なので末尾 /notes を除去して渡す
client = NotesClient(base_url="https://xxxxx.execute-api.ap-northeast-1.amazonaws.com/yamazaki-dev")

created = client.create_note(
  user_id="user123",
  title="会議メモ",
  content="本文",
  tags=["仕事", "重要"],
)

notes = client.list_notes(user_id="user123")
one = client.get_note(created["noteId"])
updated = client.update_note(created["noteId"], title="会議メモ(更新)")
client.delete_note(created["noteId"])
```

### TypeScript SDK（React向け）

- 実装: `application/client/typescript-sdk/notesApiClient.ts`
- エクスポート: `application/client/typescript-sdk/index.ts`

利用例:

```ts
import { NotesApiClient } from "./application/client/typescript-sdk";

const client = new NotesApiClient({
  baseUrl: "https://xxxxx.execute-api.ap-northeast-1.amazonaws.com/yamazaki-dev",
});

const created = await client.createNote("user123", {
  title: "会議メモ",
  content: "本文",
  tags: ["仕事", "重要"],
});

const notes = await client.listNotes("user123");
const one = await client.getNote(created.noteId);
const updated = await client.updateNote(created.noteId, { title: "会議メモ(更新)" });
await client.deleteNote(created.noteId);
```

## 環境の削除

```bash
# apps/notes-api/infra/ の中で実行
terraform destroy
```

## 変数一覧

| 変数名 | 説明 | デフォルト値 | 許可値 |
|---|---|---|---|
| `environment` | 環境名（リソース名のサフィックスに使用） | `yamazaki-dev` | `yamazaki-dev` / `yamazaki-stg` / `yamazaki-prod` |
