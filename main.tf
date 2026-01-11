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
