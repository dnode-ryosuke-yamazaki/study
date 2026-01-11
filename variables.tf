
# =====================================================
# 変数の定義
# =====================================================
# Terraformの変数は設定値を一元管理するために使用します。
# これらの値は terraform.tfvars ファイルから読み込まれます。
# =====================================================

# 環境を表す変数
# 開発環境（dev）・ステージング環境（staging）・本番環境（prod）で
# リソースを分け、環境ごとに異なる設定を適用するときに使用します
variable "environment" {
  description = "環境を表す名前（例：yamazaki-dev, yamazaki-stg, yamazaki-prod）"
  type        = string
  default     = "yamazaki-dev"
  
  # 入力値の検証：許可する値を制限します
  # 誤った環境名が設定されるのを防ぎます
  validation {
    condition     = contains(["yamazaki-dev", "yamazaki-stg", "yamazaki-prod"], var.environment)
    error_message = "environmentはyamazaki-dev, yamazaki-stg, yamazaki-prodのいずれかである必要があります。"
  }
}