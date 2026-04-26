# Notes API

メモ管理APIのインフラ・アプリケーション構成リポジトリです。  
AWS Lambda + API Gateway + DynamoDB を Terraform で構築します。

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
.
├── application/
│   ├── openapi.yaml           # API仕様定義 (OpenAPI 3.0.3)
│   └── lambda/
│       ├── lambda_function.py # Lambda関数実装
│       └── package_lambda.sh  # デプロイZIP生成スクリプト
├── api_gateway.tf             # API Gateway定義
├── dynamodb.tf                # DynamoDBテーブル定義
├── iam.tf                     # IAMロール・ポリシー定義
├── kms.tf                     # KMS暗号化キー定義
├── lambda.tf                  # Lambda関数・CloudWatch定義
├── outputs.tf                 # 出力値定義
├── provider.tf                # AWSプロバイダー設定
├── variables.tf               # 変数定義
└── terraform.tfvars           # 変数値 (環境名など)
```

## 前提条件

- Terraform >= 1.0
- Python 3.11+
- AWS CLI（認証設定済み）
- `aws configure` でデプロイ先アカウントの認証情報を設定済みであること

## セットアップ

### 1. Lambda パッケージのビルド

```bash
cd application/lambda
bash package_lambda.sh
cd ../..
```

### 2. Terraform 初期化

```bash
terraform init
```

### 3. 環境名の設定（任意）

`terraform.tfvars` に環境名を指定します。

```hcl
environment = "yamazaki-dev"
```

指定しない場合は `variables.tf` のデフォルト値 (`yamazaki-dev`) が使用されます。

### 4. デプロイ

```bash
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

ベースURL: `terraform output -raw api_gateway_url`

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
BASE_URL=$(terraform output -raw api_gateway_url)

# メモ作成
curl -X POST "$BASE_URL?userId=user123" \
  -H 'Content-Type: application/json' \
  -d '{"title":"会議メモ","content":"本文"}'

# メモ一覧取得
curl "$BASE_URL?userId=user123"
```

## 環境の削除

```bash
terraform destroy
```

## 変数一覧

| 変数名 | 説明 | デフォルト値 | 許可値 |
|---|---|---|---|
| `environment` | 環境名（リソース名のサフィックスに使用） | `yamazaki-dev` | `yamazaki-dev` / `yamazaki-stg` / `yamazaki-prod` |
