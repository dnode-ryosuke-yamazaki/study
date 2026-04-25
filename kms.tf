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
