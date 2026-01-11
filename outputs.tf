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
