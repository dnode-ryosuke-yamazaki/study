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

# 既存の lib ディレクトリを削除
if [ -d "lib" ]; then
  rm -rf lib
fi

# Python依存パッケージをインストール（PyYAML）
echo "Python依存パッケージをインストールしています..."
python3 -m pip install -q -t . pyyaml 2>/dev/null || echo "Warning: PyYAMLをインストール出来ませんでした。フォールバック検証を使用します"

# lambda_function.py と openapi.yaml をZIPファイルに圧縮
echo "lambda_function.py と openapi.yaml を ZIP ファイルに圧縮します"
zip -r -q lambda_function.zip lambda_function.py ../openapi.yaml yaml/

# オプション：lib ディレクトリ内のファイルもZIPに追加（pip install の依存）
if [ -d "yaml" ]; then
  zip -r -q lambda_function.zip yaml/
fi

echo "==================================================="
echo "パッケージング完了"
echo "==================================================="
echo "生成されたファイル："
ls -lh lambda_function.zip
echo ""
echo "次のコマンドで Terraform 適用を実行できます："
echo "  cd .. && terraform plan"
echo "  cd .. && terraform apply"
