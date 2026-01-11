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
  value       = aws_dynamodb_table.notes.global_secondary_index[0].name
}
