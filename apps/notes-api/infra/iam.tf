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
