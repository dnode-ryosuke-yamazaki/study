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
