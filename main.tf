# =====================================================
# KMS カスタマーマスターキー（CMK）の定義
# =====================================================
# DynamoDBテーブルの暗号化に使用するKMS CMKです。
# AWSが管理するキーではなく、自社で管理するキーを使用することで、
# より強力なセキュリティ制御とコンプライアンス対応が可能になります。
# =====================================================

# KMS CMKの作成
# このキーを使ってDynamoDBテーブルを暗号化します
resource "aws_kms_key" "dynamodb_key" {
  # キーの説明
  # AWSコンソールでキーを識別するために使用されます
  description             = "KMS key for DynamoDB tables encryption in ${var.environment} environment"
  
  # キーの削除待機期間（日数）
  # キーを削除する際、この期間は実際には削除されず、削除スケジュールがある状態になります
  # これにより、誤った削除から保護します
  deletion_window_in_days = 7
  
  # キーの無効化を許可するか
  # falseに設定すると、キーの削除を防ぐことができます
  enable_key_rotation     = true
  
  # タグの設定
  # AWSリソースを分類・管理するために使用します
  tags = {
    Name        = "dynamodb-notes-key"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# KMS キーのエイリアス設定
# キーを識別しやすくするために、人間が読みやすい名前をつけます
# この名前は「arn:aws:kms:region:account:alias/name」の形式で参照できます
resource "aws_kms_alias" "dynamodb_key_alias" {
  # エイリアスの名前
  # 「arn:aws:kms:region:account:alias/dynamodb-notes-key-dev」のように使用されます
  name            = "alias/dynamodb-notes-key-${var.environment}"
  
  # エイリアスが指す実際のKMS CMK
  target_key_id   = aws_kms_key.dynamodb_key.key_id
}

# =====================================================
# DynamoDB テーブル定義：notes
# =====================================================
# このテーブルは、ユーザーが作成したメモを管理します。
# - noteId：メモの一意識別子（パーティションキー）
# - userId：ユーザーの一意識別子（GSIで検索するためのキー）
# - その他のカラムは属性として動的に管理されます
# =====================================================

resource "aws_dynamodb_table" "notes" {
  # テーブルの名前を定義します
  # 環境名を含めることで、開発環境・本番環境で異なるテーブルを使用できます
  name           = "notes-table-${var.environment}"
  
  # 課金方式：オンデマンドモード
  # PAY_PER_REQUEST：実際の使用量に応じて課金（スタートアップ向け）
  # PROVISIONED：あらかじめ容量を確保する（大規模利用向け）
  billing_mode   = "PAY_PER_REQUEST"
  
  # ハッシュキー（パーティションキー）の定義
  # DynamoDBでは、このキーを使ってアイテムを一意に識別します
  # noteId は各メモの一意なID です
  hash_key       = "noteId"
  
  # ハッシュキーの属性定義
  # name：キーの名前（hash_keyで指定した値と一致）
  # type：データ型。S=String、N=Number、B=Binary
  attribute {
    name = "noteId"
    type = "S"  # String型
  }
  
  # グローバルセカンダリインデックス（GSI）の定義
  # このインデックスにより、userId でメモを検索することができます
  # （例：「ユーザーAの全メモを取得」という検索が高速になります）
  global_secondary_index {
    # インデックスの名前
    name            = "userId-index"
    
    # このインデックスのハッシュキー
    # userIdを指定することで、ユーザーごとのメモ検索が効率的になります
    hash_key        = "userId"
    
    # インデックスの射影型：このインデックスで返すカラム
    # ALL：テーブルのすべてのカラムを返す
    # KEYS_ONLY：キーのみを返す
    # INCLUDE：指定したカラムのみを返す
    projection_type = "ALL"
  }
  
  # GSIのスキーマ定義
  # GSIで使用するキーの属性情報を定義します
  attribute {
    name = "userId"
    type = "S"  # String型
  }
  
  # サーバーサイド暗号化（SSE）の設定
  # DynamoDBテーブルに保存されるデータを暗号化します
  # これにより、保存中のデータセキュリティを強化します
  server_side_encryption {
    # 暗号化を有効にするか
    enabled     = true
    
    # 暗号化に使用するKMS CMKを指定
    # カスタマーマスターキー（CMK）を使用することで、
    # AWS管理キー（デフォルト）よりも強力なセキュリティ制御が可能です
    kms_key_arn  = aws_kms_key.dynamodb_key.arn
  }
  
  # タグの設定
  # AWSリソースを分類・管理するために使用します
  tags = {
    Name        = "notes-table"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# =====================================================
# DynamoDB テーブルの説明
# =====================================================
# 
# 【データ構造の特徴】
# - noteId（パーティションキー）：メモの一意識別子
#   → このキーでメモを検索する場合が多い時に最適
# 
# - userId（グローバルセカンダリインデックス）
#   → 「特定ユーザーのメモをすべて取得」という検索を高速化
# 
# - その他のカラム（title, content, createdAt, tags）
#   → DynamoDBはスキーマレスなので、マイグレーション後に
#     自由に追加・削除できます
# 
# 【今後の拡張例】
# - TTL（Time To Live）の設定
#   → 一定期間後に自動的にアイテムを削除する機能
# - LSI（ローカルセカンダリインデックス）
#   → createdAtで時系列検索をしたい場合に追加
#
# =====================================================

# =====================================================
# DynamoDB テーブル定義：api_logs
# =====================================================
# このテーブルは、API利用履歴を管理します。
# - logId：ログの一意識別子（パーティションキー）
# - timestamp：ログ記録時刻（ソートキー）
# - noteId：関連するメモID（GSIで検索するためのキー）
# - userId：呼び出しユーザーID（GSIで検索するためのキー）
# - その他のカラムはAPI操作の詳細情報を動的に管理されます
# =====================================================

resource "aws_dynamodb_table" "api_logs" {
  # テーブルの名前を定義します
  # 環境名を含めることで、開発環境・本番環境で異なるテーブルを使用できます
  name           = "api-logs-table-${var.environment}"
  
  # 課金方式：オンデマンドモード
  # PAY_PER_REQUEST：実際の使用量に応じて課金
  billing_mode   = "PAY_PER_REQUEST"
  
  # ハッシュキー（パーティションキー）の定義
  # logId は各API呼び出しログの一意なID です
  hash_key       = "logId"
  
  # ソートキー（レンジキー）の定義
  # timestamp を使って時系列でログを検索・ソートします
  # 同じlogId内での複数のレコード（実際には logId は一意ですが）や
  # クエリ時に時間範囲で絞り込む際に効率的です
  range_key      = "timestamp"
  
  # ハッシュキーの属性定義
  attribute {
    name = "logId"
    type = "S"  # String型
  }
  
  # ソートキーの属性定義
  attribute {
    name = "timestamp"
    type = "S"  # String型（ISO8601形式など）
  }
  
  # グローバルセカンダリインデックス（GSI）の定義
  # noteIdでAPI呼び出し履歴を検索する場合に使用
  # （例：「特定メモに対するAPI操作をすべて取得」という検索が高速になります）
  global_secondary_index {
    name            = "noteId-index"
    hash_key        = "noteId"
    range_key       = "timestamp"
    projection_type = "ALL"
  }
  
  # グローバルセカンダリインデックス（GSI）の定義
  # userIdでAPI呼び出し履歴を検索する場合に使用
  # （例：「特定ユーザーのAPI操作をすべて取得」という検索が高速になります）
  global_secondary_index {
    name            = "userId-index"
    hash_key        = "userId"
    range_key       = "timestamp"
    projection_type = "ALL"
  }
  
  # GSI用のスキーマ定義
  # noteId属性の定義
  attribute {
    name = "noteId"
    type = "S"  # String型
  }
  
  # GSI用のスキーマ定義
  # userId属性の定義
  attribute {
    name = "userId"
    type = "S"  # String型
  }
  
  # サーバーサイド暗号化（SSE）の設定
  # DynamoDBテーブルに保存されるログデータを暗号化します
  # APIリクエスト/レスポンスボディなど機密情報を含むため、暗号化は必須です
  server_side_encryption {
    enabled     = true
    # notes テーブルと同じ KMS CMK を使用してコスト効率化
    kms_key_arn  = aws_kms_key.dynamodb_key.arn
  }
  
  # TTL（Time To Live）の設定
  # ログは一定期間で自動削除することで、ストレージコストを削減します
  # 90日後に自動的に削除されるように設定します
  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }
  
  # タグの設定
  # AWSリソースを分類・管理するために使用します
  tags = {
    Name        = "api-logs-table"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# =====================================================
# DynamoDB テーブルの説明（api_logs）
# =====================================================
# 
# 【データ構造の特徴】
# - logId（パーティションキー）：ログの一意識別子
#   → このキーでログレコードを直接取得
# 
# - timestamp（ソートキー）：ログ記録時刻
#   → 時系列でのクエリやソートに使用
#   → 実装時は ISO8601 形式（例：2024-01-15T10:30:45.123Z）を推奨
# 
# - noteId（GSI）：関連するメモID
#   → 「特定メモのAPI操作履歴」を高速に検索
#   → notes テーブルの noteId との関連付けに使用
# 
# - userId（GSI）：呼び出しユーザーID
#   → 「特定ユーザーのAPI操作履歴」を高速に検索
#   → notes テーブルの userId と同じキーを使用
# 
# - その他の属性（actionType, endpoint, method, requestBody等）
#   → DynamoDBはスキーマレスなので、API呼び出しの詳細情報を
#     自由に格納できます
#   → map型（JSON）やstring型で構造化されたデータを保存可能
# 
# 【TTL（Time To Live）について】
# - expiresAt 属性に UNIX タイムスタンプを設定することで、
#   DynamoDB が自動的にレコードを削除します
# - 実装例：現在時刻 + 7776000秒（90日）
# - これにより、ストレージコストを削減しつつ、短期間のログ保持を実現
# 
# 【リレーションのイメージ】
# - notes テーブルの各 noteId に対し、
#   api_logs テーブルに「どのメモに対して」「誰が」「どんなAPI操作を」
#   「いつ」「どうやったか」が蓄積されます
# - userId で複数ユーザーの操作を追跡
# - noteId でメモ毎の操作履歴を追跡
# - timestamp でスケーラブルな時系列クエリを実現
#
# =====================================================

# =====================================================
# IAM ロール：Lambda実行ロール
# =====================================================
# Lambda関数が使用するIAMロールです。
# CloudWatch Logs への書き込み権限などを持ちます。
resource "aws_iam_role" "lambda_execution_role" {
  # ロールの名前
  # Lambda関数の識別に使用します
  name = "lambda-execution-role-${var.environment}"
  
  # ロールの信頼ポリシー
  # Lambdaサービスがこのロールを引き受けることを許可します
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
  
  # タグの設定
  tags = {
    Name        = "lambda-execution-role"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# =====================================================
# IAM ポリシー：CloudWatch Logs への書き込み権限
# =====================================================
# Lambda関数がCloudWatch Logsにログを書き込むための権限です。
# これはAWSが提供する基本的なポリシーです。
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  # アタッチするIAMポリシーの名前
  # AWS管理ポリシーを使用します
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  
  # このポリシーをアタッチするIAMロール
  role       = aws_iam_role.lambda_execution_role.name
}

# =====================================================
# IAM ポリシー：DynamoDB への読み書き権限
# =====================================================
resource "aws_iam_role_policy" "lambda_dynamodb_policy" {
  name = "lambda-dynamodb-policy-${var.environment}"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.notes.arn,
          "${aws_dynamodb_table.notes.arn}/index/*",
          aws_dynamodb_table.api_logs.arn,
          "${aws_dynamodb_table.api_logs.arn}/index/*"
        ]
      }
    ]
  })
}

# =====================================================
# IAM ポリシー：KMS 暗号化キーへのアクセス権限
# =====================================================
# Lambda関数がDynamoDBの暗号化データを読み書きするために必要なKMS権限
resource "aws_iam_role_policy" "lambda_kms_policy" {
  name = "lambda-kms-policy-${var.environment}"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:Encrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey"
        ]
        Resource = aws_kms_key.dynamodb_key.arn
      }
    ]
  })
}

# =====================================================
# Lambda 関数：hello_world
# =====================================================
# シンプルなHello Worldを返すLambda関数です。
# イベント駆動アーキテクチャの基盤として機能します。
resource "aws_lambda_function" "hello_world" {
  # Lambda関数の名前
  # 関数を識別するための一意な名前です
  function_name = "hello-world-function-${var.environment}"
  
  # Lambda関数の実行時言語
  # Python 3.11で実装しています
  runtime       = "python3.11"
  
  # Lambda関数が実行するコードをZIP形式で指定
  # ここではinline_codeを使用してコードを直接指定
  filename      = "lambda_function.zip"
  
  # ZIPファイルのソースコード
  # アップロード時にこのファイルをハッシュ化して変更を検出
  source_code_hash = filebase64sha256("${path.module}/lambda_function.zip")
  
  # Lambda関数が使用するIAMロール
  role          = aws_iam_role.lambda_execution_role.arn
  
  # Lambda関数のハンドラー
  # 「ファイル名.関数名」の形式で指定します
  # lambda_function.py内のlambda_handlerという関数が呼び出されます
  handler       = "lambda_function.lambda_handler"
  
  # Lambda関数のタイムアウト時間（秒）
  # デフォルトの3秒では不足する場合があるため、30秒に設定
  timeout       = 30
  
  # Lambda関数のメモリサイズ（MB）
  # 128MB（最小）～ 10240MB（最大）
  # 一般的なAPI処理には512MBで十分です
  memory_size   = 512
  
  # Lambda関数の実行環境変数
  # アプリケーションコード内で $ENVIRONMENT 変数として参照可能
  environment {
    variables = {
      ENVIRONMENT = var.environment
    }
  }
  
  # タグの設定
  tags = {
    Name        = "hello-world-function"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# =====================================================
# CloudWatch Logs ロググループ
# =====================================================
# Lambda関数のログを保存するロググループです。
# Lambda実行時のログ出力先になります。
resource "aws_cloudwatch_log_group" "lambda_log_group" {
  # ロググループの名前
  # Lambda関数のログは自動的にここに出力されます
  # AWS命名規則：/aws/lambda/関数名
  name              = "/aws/lambda/hello-world-function-${var.environment}"
  
  # ログの保持期間（日数）
  # 30日でログを自動削除し、ストレージコストを削減します
  retention_in_days = 30
  
  # タグの設定
  tags = {
    Name        = "hello-world-log-group"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# =====================================================
# Lambda 関数の説明
# =====================================================
# 
# 【関数の特徴】
# - Hello Worldを返すシンプルなダミー関数
# - DynamoDBへのアクセスなし（初版）
# - Python 3.11で実装
# - CloudWatch Logsに自動的にログを出力
# 
# 【実行フロー】
# 1. API Gateway経由でリクエスト受信
# 2. Lambda関数が実行（lambda_handler関数）
# 3. レスポンス（Hello World）を返す
# 4. ログはCloudWatch Logsに記録
# 
# 【将来の拡張例】
# - DynamoDBのnotesテーブルへのアクセス
# - api_logsテーブルへのログ記録
# - APIリクエスト/レスポンスの検証
# - エラーハンドリングの強化
# - X-Ray トレーシングの統合
#
# =====================================================

# =====================================================
# API Gateway REST API
# =====================================================
# HTTPリクエストを受け付けてLambda関数に振り分けるAPI Gateway
resource "aws_api_gateway_rest_api" "notes_api" {
  name           = "notes-api-${var.environment}"
  description    = "Notes API - OpenAPI仕様に準拠したRESTful API"
  
  tags = {
    Name        = "notes-api"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# =====================================================
# API Gateway リソース：/notes
# =====================================================
resource "aws_api_gateway_resource" "notes" {
  rest_api_id = aws_api_gateway_rest_api.notes_api.id
  parent_id   = aws_api_gateway_rest_api.notes_api.root_resource_id
  path_part   = "notes"
}

# =====================================================
# API Gateway リソース：/notes/{noteId}
# =====================================================
resource "aws_api_gateway_resource" "notes_item" {
  rest_api_id = aws_api_gateway_rest_api.notes_api.id
  parent_id   = aws_api_gateway_resource.notes.id
  path_part   = "{noteId}"
}

# =====================================================
# API Gateway メソッド：GET /notes
# =====================================================
resource "aws_api_gateway_method" "notes_list" {
  rest_api_id   = aws_api_gateway_rest_api.notes_api.id
  resource_id   = aws_api_gateway_resource.notes.id
  http_method   = "GET"
  authorization = "NONE"
  
  request_parameters = {
    "method.request.querystring.userId" = true
  }
}

# =====================================================
# API Gateway メソッド：POST /notes
# =====================================================
resource "aws_api_gateway_method" "notes_create" {
  rest_api_id   = aws_api_gateway_rest_api.notes_api.id
  resource_id   = aws_api_gateway_resource.notes.id
  http_method   = "POST"
  authorization = "NONE"
}

# =====================================================
# API Gateway メソッド：GET /notes/{noteId}
# =====================================================
resource "aws_api_gateway_method" "notes_get" {
  rest_api_id   = aws_api_gateway_rest_api.notes_api.id
  resource_id   = aws_api_gateway_resource.notes_item.id
  http_method   = "GET"
  authorization = "NONE"
  
  request_parameters = {
    "method.request.path.noteId" = true
  }
}

# =====================================================
# API Gateway メソッド：PUT /notes/{noteId}
# =====================================================
resource "aws_api_gateway_method" "notes_update" {
  rest_api_id   = aws_api_gateway_rest_api.notes_api.id
  resource_id   = aws_api_gateway_resource.notes_item.id
  http_method   = "PUT"
  authorization = "NONE"
  
  request_parameters = {
    "method.request.path.noteId" = true
  }
}

# =====================================================
# API Gateway メソッド：DELETE /notes/{noteId}
# =====================================================
resource "aws_api_gateway_method" "notes_delete" {
  rest_api_id   = aws_api_gateway_rest_api.notes_api.id
  resource_id   = aws_api_gateway_resource.notes_item.id
  http_method   = "DELETE"
  authorization = "NONE"
  
  request_parameters = {
    "method.request.path.noteId" = true
  }
}

# =====================================================
# API Gateway 統合：Lambda との連携
# =====================================================
resource "aws_api_gateway_integration" "notes_list_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.notes_api.id
  resource_id             = aws_api_gateway_resource.notes.id
  http_method             = aws_api_gateway_method.notes_list.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.hello_world.invoke_arn
}

resource "aws_api_gateway_integration" "notes_create_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.notes_api.id
  resource_id             = aws_api_gateway_resource.notes.id
  http_method             = aws_api_gateway_method.notes_create.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.hello_world.invoke_arn
}

resource "aws_api_gateway_integration" "notes_get_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.notes_api.id
  resource_id             = aws_api_gateway_resource.notes_item.id
  http_method             = aws_api_gateway_method.notes_get.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.hello_world.invoke_arn
}

resource "aws_api_gateway_integration" "notes_update_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.notes_api.id
  resource_id             = aws_api_gateway_resource.notes_item.id
  http_method             = aws_api_gateway_method.notes_update.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.hello_world.invoke_arn
}

resource "aws_api_gateway_integration" "notes_delete_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.notes_api.id
  resource_id             = aws_api_gateway_resource.notes_item.id
  http_method             = aws_api_gateway_method.notes_delete.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.hello_world.invoke_arn
}

# =====================================================
# Lambda 権限：API Gatewayからの呼び出しを許可
# =====================================================
resource "aws_lambda_permission" "api_gateway_notes" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.hello_world.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.notes_api.execution_arn}/*/*"
}

# =====================================================
# API Gateway デプロイメント
# =====================================================
resource "aws_api_gateway_deployment" "notes" {
  depends_on = [
    aws_api_gateway_integration.notes_list_lambda,
    aws_api_gateway_integration.notes_create_lambda,
    aws_api_gateway_integration.notes_get_lambda,
    aws_api_gateway_integration.notes_update_lambda,
    aws_api_gateway_integration.notes_delete_lambda
  ]
  
  rest_api_id = aws_api_gateway_rest_api.notes_api.id
  
  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.notes.id,
      aws_api_gateway_resource.notes_item.id,
      aws_api_gateway_method.notes_list.id,
      aws_api_gateway_method.notes_create.id,
      aws_api_gateway_method.notes_get.id,
      aws_api_gateway_method.notes_update.id,
      aws_api_gateway_method.notes_delete.id,
      aws_api_gateway_integration.notes_list_lambda.id,
      aws_api_gateway_integration.notes_create_lambda.id,
      aws_api_gateway_integration.notes_get_lambda.id,
      aws_api_gateway_integration.notes_update_lambda.id,
      aws_api_gateway_integration.notes_delete_lambda.id,
    ]))
  }
  
  lifecycle {
    create_before_destroy = true
  }
}

# =====================================================
# API Gateway ステージ
# =====================================================
resource "aws_api_gateway_stage" "notes" {
  deployment_id = aws_api_gateway_deployment.notes.id
  rest_api_id   = aws_api_gateway_rest_api.notes_api.id
  stage_name    = var.environment
  
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway_log_group_notes.arn
    format = jsonencode({
      requestId          = "$context.requestId"
      ip                 = "$context.identity.sourceIp"
      requestTime        = "$context.requestTime"
      httpMethod         = "$context.httpMethod"
      resourcePath       = "$context.resourcePath"
      status             = "$context.status"
      protocol           = "$context.protocol"
      responseLength     = "$context.responseLength"
      integrationLatency = "$context.integration.latency"
    })
  }
  
  tags = {
    Name        = "notes-api-stage"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# =====================================================
# CloudWatch Logs ロググループ：API Gateway
# =====================================================
resource "aws_cloudwatch_log_group" "api_gateway_log_group_notes" {
  name              = "/aws/apigateway/notes-api-${var.environment}"
  retention_in_days = 30
  
  tags = {
    Name        = "api-gateway-notes-log-group"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}
