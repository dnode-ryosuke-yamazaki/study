# =====================================================
# 出力値の定義
# =====================================================
# Terraformの apply実行後に表示される値です。
# アプリケーションが接続するために必要な情報を出力します。
# =====================================================

# notesテーブルの名前を出力
# アプリケーションがこの名前を使ってテーブルにアクセスします
output "notes_table_name" {
  description = "作成されたDynamoDBのnotesテーブル名"
  value       = aws_dynamodb_table.notes.name
}

# notesテーブルのARNを出力
# ARN（Amazon Resource Name）は、AWSリソースの一意識別子です。
# IAMポリシーを設定する際に使用します。
output "notes_table_arn" {
  description = "notesテーブルのARN（Amazon Resource Name）"
  value       = aws_dynamodb_table.notes.arn
}

# テーブルのストリーム ARN を出力
# DynamoDB Streamsを使ってテーブルの更新をリアルタイムで追跡する場合に使用します
output "notes_table_stream_arn" {
  description = "notesテーブルのストリームARN"
  value       = aws_dynamodb_table.notes.stream_arn
}

# GSI（グローバルセカンダリインデックス）の名前を出力
# アプリケーションでuserIdで検索する際に使用します
output "notes_gsi_name" {
  description = "userId検索用のグローバルセカンダリインデックス名"
  value       = [for gsi in aws_dynamodb_table.notes.global_secondary_index : gsi.name if gsi.hash_key == "userId"][0]
}

# KMS CMK（カスタマーマスターキー）のARNを出力
# DynamoDBテーブル暗号化に使用するキーの識別子です。
# IAMポリシーやアプリケーション設定でこのARNを参照する際に使用します。
output "kms_key_arn" {
  description = "DynamoDBテーブル暗号化用のKMS CMK ARN"
  value       = aws_kms_key.dynamodb_key.arn
}

# KMS CMKのキーIDを出力
# キーを直接参照する場合に使用します。
# ARNよりも短いID形式です。
output "kms_key_id" {
  description = "DynamoDBテーブル暗号化用のKMS CMK ID"
  value       = aws_kms_key.dynamodb_key.key_id
}

# KMS キーのエイリアスを出力
# 人間が読みやすい形式でキーを識別する場合に使用します。
# AWSコンソールやCLIコマンドでこのエイリアス名を指定することで、キーを簡単に参照できます。
output "kms_key_alias" {
  description = "DynamoDBテーブル暗号化用のKMS キーエイリアス"
  value       = aws_kms_alias.dynamodb_key_alias.name
}

# =====================================================
# API ログテーブルの出力値
# =====================================================

# api_logsテーブルの名前を出力
# アプリケーションがこの名前を使ってAPI操作履歴をテーブルにアクセスします
output "api_logs_table_name" {
  description = "作成されたDynamoDBのapi_logsテーブル名"
  value       = aws_dynamodb_table.api_logs.name
}

# api_logsテーブルのARNを出力
# IAMポリシーを設定する際に使用します。
output "api_logs_table_arn" {
  description = "api_logsテーブルのARN（Amazon Resource Name）"
  value       = aws_dynamodb_table.api_logs.arn
}

# api_logsテーブルのストリーム ARN を出力
# DynamoDB Streamsを使ってテーブルの更新をリアルタイムで追跡する場合に使用します
output "api_logs_table_stream_arn" {
  description = "api_logsテーブルのストリームARN"
  value       = aws_dynamodb_table.api_logs.stream_arn
}

# noteIdでのAPI操作履歴検索用GSIの名前を出力
# アプリケーションで特定メモのAPI操作履歴を検索する際に使用します
output "api_logs_noteId_gsi_name" {
  description = "noteId検索用のグローバルセカンダリインデックス名"
  value       = [for gsi in aws_dynamodb_table.api_logs.global_secondary_index : gsi.name if gsi.hash_key == "noteId"][0]
}

# userIdでのAPI操作履歴検索用GSIの名前を出力
# アプリケーションで特定ユーザーのAPI操作履歴を検索する際に使用します
output "api_logs_userId_gsi_name" {
  description = "userId検索用のグローバルセカンダリインデックス名"
  value       = [for gsi in aws_dynamodb_table.api_logs.global_secondary_index : gsi.name if gsi.hash_key == "userId"][0]
}

# =====================================================
# Lambda 関数の出力値
# =====================================================

# Lambda関数のARNを出力
# API GatewayやIAMポリシーで関数を参照する際に使用します
output "lambda_function_arn" {
  description = "Hello World Lambda関数のARN"
  value       = aws_lambda_function.hello_world.arn
}

# Lambda関数の名前を出力
# AWS CLIやコンソールで関数を実行する際に使用します
output "lambda_function_name" {
  description = "Hello World Lambda関数の名前"
  value       = aws_lambda_function.hello_world.function_name
}

# Lambda関数の最新バージョンを出力
# デプロイメント時のバージョン追跡に使用します
output "lambda_function_version" {
  description = "Hello World Lambda関数の最新バージョン"
  value       = aws_lambda_function.hello_world.version
}

# Lambda実行ロールのARNを出力
# 他のリソースがLambda関数に権限を付与する際に使用します
output "lambda_execution_role_arn" {
  description = "Lambda実行ロールのARN"
  value       = aws_iam_role.lambda_execution_role.arn
}

# CloudWatch Logsロググループの名前を出力
# ログを確認する際に使用します
output "lambda_log_group_name" {
  description = "Lambda関数のCloudWatch Logsロググループ名"
  value       = aws_cloudwatch_log_group.lambda_log_group.name
}

# =====================================================
# API Gateway の出力値
# =====================================================

# API GatewayのURL（完全なエンドポイント）を出力
# このURLにHTTPリクエストを送信することでLambda関数が実行されます
# 例：https://xxxxx.execute-api.ap-northeast-1.amazonaws.com/dev/notes
output "api_gateway_url" {
  description = "API GatewayのエンドポイントURL"
  value       = "${aws_api_gateway_stage.notes.invoke_url}/notes"
}

# API GatewayのARNを出力
# 他のAWSリソースからAPI Gatewayを参照する際に使用します
output "api_gateway_arn" {
  description = "API GatewayのARN"
  value       = aws_api_gateway_rest_api.notes_api.arn
}

# API Gateway ロググループの名前を出力
# API Gatewayのアクセスログを確認する際に使用します
output "api_gateway_log_group_name" {
  description = "API GatewayのCloudWatch Logsロググループ名"
  value       = aws_cloudwatch_log_group.api_gateway_log_group_notes.name
}

# =====================================================
# 出力値の定義
# =====================================================

# Notes API Gateway の出力値
output "notes_api_gateway_url" {
  description = "Notes API GatewayのエンドポイントURL"
  value       = aws_api_gateway_stage.notes.invoke_url
}

output "notes_api_endpoints" {
  description = "Notes APIの各エンドポイント"
  value = {
    list_notes   = "${aws_api_gateway_stage.notes.invoke_url}/notes?userId=USER_ID"
    create_note  = "${aws_api_gateway_stage.notes.invoke_url}/notes"
    get_note     = "${aws_api_gateway_stage.notes.invoke_url}/notes/NOTE_ID"
    update_note  = "${aws_api_gateway_stage.notes.invoke_url}/notes/NOTE_ID"
    delete_note  = "${aws_api_gateway_stage.notes.invoke_url}/notes/NOTE_ID"
  }
}

# DynamoDB テーブルの出力値
output "dynamodb_notes_table_name" {
  description = "DynamoDB notesテーブル名"
  value       = aws_dynamodb_table.notes.name
}

output "dynamodb_api_logs_table_name" {
  description = "DynamoDB api_logsテーブル名"
  value       = aws_dynamodb_table.api_logs.name
}
