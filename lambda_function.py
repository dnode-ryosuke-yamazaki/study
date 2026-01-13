"""
Lambda 関数：Hello World

このLambda関数はシンプルなHello Worldレスポンスを返します。
初版はダミー関数で、DynamoDBへのアクセスなし。
将来的には実際のビジネスロジックを実装予定です。
"""

import json
import logging
import os
from datetime import datetime

# ロギング設定
# ロガーを取得し、ログレベルをINFOに設定
# これにより、INFO以上のレベルのログ（INFO、WARNING、ERROR、CRITICAL）が出力されます
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda ハンドラー関数
    
    このエントリーポイント関数はAWS Lambdaから直接呼び出されます。
    リクエストイベントを受け取り、処理を実行してHTTPレスポンスを返します。
    
    Args:
        event (dict): Lambda トリガーから渡されるイベント。
                      API Gatewayの場合はリクエスト情報を含みます。
        context (LambdaContext): Lambda実行コンテキスト。
                                関数の実行情報（リクエストID、関数名など）を提供します。
    
    Returns:
        dict: HTTPレスポンス辞書
            - statusCode (int): HTTPステータスコード（200: 成功）
            - headers (dict): レスポンスヘッダー（Content-Typeなど）
            - body (str): レスポンスボディ（JSON文字列形式）
    """
    
    # ロギング：関数が呼び出されたことを記録
    logger.info("Lambda function invoked")
    logger.info(f"Event: {json.dumps(event)}")
    
    # 環境変数から環境名を取得
    environment = os.environ.get("ENVIRONMENT", "unknown")
    logger.info(f"Environment: {environment}")
    
    # 現在の時刻を取得（ISO8601形式）
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    # レスポンスボディを構築
    response_body = {
        "message": "Hello World from Lambda!",
        "timestamp": timestamp,
        "environment": environment,
        "requestId": context.aws_request_id,
        "functionName": context.function_name,
        "functionVersion": context.function_version,
    }
    
    # ログにレスポンスを記録
    logger.info(f"Response: {json.dumps(response_body)}")
    
    # HTTPレスポンスを構築
    response = {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
        },
        "body": json.dumps(response_body),
    }
    
    return response
