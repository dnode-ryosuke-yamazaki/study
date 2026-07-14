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
  filename      = "${path.module}/application/lambda/lambda_function.zip"
  
  # ZIPファイルのソースコード
  # アップロード時にこのファイルをハッシュ化して変更を検出
  source_code_hash = filebase64sha256("${path.module}/application/lambda/lambda_function.zip")
  
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
# CloudWatch Logs ロググループ：Lambda
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
# Lambda 権限：API Gatewayからの呼び出しを許可
# =====================================================
resource "aws_lambda_permission" "api_gateway_notes" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.hello_world.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.notes_api.execution_arn}/*/*"
}
