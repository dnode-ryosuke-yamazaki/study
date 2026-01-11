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
  description             = "KMS key for DynamoDB notes table encryption in ${var.environment} environment"
  
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
