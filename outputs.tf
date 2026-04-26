# =====================================================
# 最小構成の出力値
# =====================================================
# 外部利用で実際に参照しやすい値だけを公開します。

output "api_gateway_url" {
  description = "Notes APIのベースURL"
  value       = "${aws_api_gateway_stage.notes.invoke_url}/notes"
}

output "notes_table_name" {
  description = "DynamoDB notesテーブル名"
  value       = aws_dynamodb_table.notes.name
}

output "api_logs_table_name" {
  description = "DynamoDB api_logsテーブル名"
  value       = aws_dynamodb_table.api_logs.name
}

output "lambda_function_name" {
  description = "Lambda関数名"
  value       = aws_lambda_function.hello_world.function_name
}
