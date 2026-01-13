#!/bin/bash

# =====================================================
# Lambda 関数デプロイメント用スクリプト
# =====================================================
# このスクリプトは lambda_function.py を ZIP ファイルにパッケージ化します。
# Terraform apply 実行前に、このスクリプトを実行してください。
# 
# 使用方法：
#   bash package_lambda.sh

set -e

# スクリプトの実行ディレクトリを取得
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

echo "==================================================="
echo "Lambda 関数のパッケージング開始"
echo "==================================================="

# 既存の ZIP ファイルを削除
if [ -f "lambda_function.zip" ]; then
  echo "既存の lambda_function.zip を削除します"
  rm -f lambda_function.zip
fi

# Python コードを ZIP ファイルにパッケージ化
echo "lambda_function.py を ZIP ファイルに圧縮します"
zip -q lambda_function.zip lambda_function.py

echo "==================================================="
echo "パッケージング完了"
echo "==================================================="
echo "生成されたファイル："
ls -lh lambda_function.zip
echo ""
echo "次のコマンドで Terraform 適用を実行できます："
echo "  terraform plan"
echo "  terraform apply"
