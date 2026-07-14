"""
Lambda 関数：Notes API

このLambda関数はメモ管理APIを提供します。
OpenAPI仕様に従ったRESTful APIを実装しています。
"""

import json
import logging
import os
import uuid
import yaml
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, List, Optional

import boto3
from boto3.dynamodb.conditions import Key

# ロギング設定
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DynamoDB クライアント初期化
dynamodb = boto3.resource('dynamodb')
environment = os.environ.get('ENVIRONMENT', 'yamazaki-dev')
notes_table = dynamodb.Table(f'notes-table-{environment}')
api_logs_table = dynamodb.Table(f'api-logs-table-{environment}')

# OpenAPI仕様をロード（スキーマ検証用）
OPENAPI_SPEC = {}
try:
    openapi_path = Path(__file__).parent.parent / 'openapi.yaml'
    with open(openapi_path, 'r', encoding='utf-8') as f:
        OPENAPI_SPEC = yaml.safe_load(f)
    logger.info("OpenAPI spec loaded successfully")
except Exception as e:
    logger.warning(f"Failed to load OpenAPI spec: {str(e)}. Proceeding with fallback validation.")


class DecimalEncoder(json.JSONEncoder):
    """DynamoDBのDecimal型をJSON化するためのエンコーダー"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


def log_api_call(
    note_id: Optional[str],
    user_id: Optional[str],
    action_type: str,
    endpoint: str,
    method: str,
    request_body: Optional[Dict],
    response_status: int
) -> None:
    """API呼び出しログをDynamoDBに記録"""
    try:
        timestamp = datetime.utcnow().isoformat() + "Z"
        log_id = str(uuid.uuid4())
        
        # TTL: 90日後に自動削除
        expires_at = int(datetime.utcnow().timestamp()) + (90 * 24 * 60 * 60)
        
        log_item = {
            'logId': log_id,
            'timestamp': timestamp,
            'actionType': action_type,
            'endpoint': endpoint,
            'method': method,
            'responseStatus': response_status,
            'expiresAt': expires_at
        }
        
        if note_id:
            log_item['noteId'] = note_id
        if user_id:
            log_item['userId'] = user_id
        if request_body:
            log_item['requestBody'] = json.dumps(request_body)
        
        api_logs_table.put_item(Item=log_item)
        logger.info(f"API call logged: {log_id}")
    except Exception as e:
        logger.error(f"Failed to log API call: {str(e)}")


def create_response(status_code: int, body: Any) -> Dict:
    """HTTPレスポンスを構築"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json; charset=utf-8',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        },
        'body': json.dumps(body, cls=DecimalEncoder, ensure_ascii=False)
    }


def create_error_response(status_code: int, error: str, message: str, details: Optional[Dict] = None) -> Dict:
    """エラーレスポンスを構築"""
    error_body = {
        'error': error,
        'message': message
    }
    if details:
        error_body['details'] = details
    return create_response(status_code, error_body)


def validate_create_note_request(body: Dict) -> Optional[Dict]:
    """メモ作成リクエストのバリデーション（OpenAPI仕様に基づく）"""
    # OpenAPI仕様から CreateNoteRequest の必須フィールドを取得
    try:
        create_note_schema = OPENAPI_SPEC.get('components', {}).get('schemas', {}).get('CreateNoteRequest', {})
        required_fields = create_note_schema.get('required', ['title', 'content'])
    except:
        required_fields = ['title', 'content']  # フォールバック
    
    # 必須フィールドのチェック（userId は query パラメータなので除外）
    for field in required_fields:
        if field not in body:
            return create_error_response(
                400,
                'BadRequest',
                f'必須フィールドが不足しています: {field}',
                {'field': field, 'reason': 'required'}
            )
    
    # maxLength 制約を OpenAPI仕様から取得・検証
    try:
        props = create_note_schema.get('properties', {})
        if 'title' in body and 'title' in props:
            max_length = props['title'].get('maxLength')
            if max_length and len(body['title']) > max_length:
                return create_error_response(
                    400,
                    'BadRequest',
                    f'タイトルは{max_length}文字以内にしてください',
                    {'field': 'title', 'reason': 'maxLength'}
                )
        if 'content' in body and 'content' in props:
            max_length = props['content'].get('maxLength')
            if max_length and len(body['content']) > max_length:
                return create_error_response(
                    400,
                    'BadRequest',
                    f'本文は{max_length}文字以内にしてください',
                    {'field': 'content', 'reason': 'maxLength'}
                )
    except:
        # フォールバック: ハードコード値でチェック
        if 'title' in body and len(body['title']) > 200:
            return create_error_response(400, 'BadRequest', 'タイトルは200文字以内にしてください', {'field': 'title', 'reason': 'maxLength'})
        if 'content' in body and len(body['content']) > 10000:
            return create_error_response(400, 'BadRequest', '本文は10000文字以内にしてください', {'field': 'content', 'reason': 'maxLength'})
    
    return None


def list_notes(event: Dict) -> Dict:
    """メモ一覧取得 (GET /notes?userId=xxx)"""
    try:
        query_params = event.get('queryStringParameters') or {}
        user_id = query_params.get('userId')
        
        if not user_id:
            return create_error_response(
                400,
                'BadRequest',
                'userIdパラメータは必須です',
                {'field': 'userId', 'reason': 'required'}
            )
        
        # GSIを使ってuserIdで検索
        response = notes_table.query(
            IndexName='userId-index',
            KeyConditionExpression=Key('userId').eq(user_id)
        )
        
        notes = response.get('Items', [])
        
        # API呼び出しログを記録
        log_api_call(
            note_id=None,
            user_id=user_id,
            action_type='LIST_NOTES',
            endpoint='/notes',
            method='GET',
            request_body=None,
            response_status=200
        )
        
        return create_response(200, {'notes': notes})
        
    except Exception as e:
        logger.error(f"Error in list_notes: {str(e)}")
        return create_error_response(
            500,
            'InternalServerError',
            'サーバー内部でエラーが発生しました'
        )


def create_note(event: Dict) -> Dict:
    """メモ作成 (POST /notes?userId=xxx)"""
    try:
        # query から userId を取得（OpenAPI仕様に準拠）
        query_params = event.get('queryStringParameters') or {}
        user_id = query_params.get('userId')
        
        if not user_id:
            return create_error_response(
                400,
                'BadRequest',
                'userIdパラメータは必須です',
                {'field': 'userId', 'reason': 'required'}
            )
        
        body = json.loads(event.get('body', '{}'))
        
        # バリデーション（body の title/content のみ）
        validation_error = validate_create_note_request(body)
        if validation_error:
            return validation_error
        
        # メモ作成
        note_id = f"note-{uuid.uuid4()}"
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        note_item = {
            'noteId': note_id,
            'userId': user_id,  # query パラメータから取得
            'title': body['title'],
            'content': body['content'],
            'tags': body.get('tags', []),
            'createdAt': timestamp,
            'updatedAt': timestamp
        }
        
        notes_table.put_item(Item=note_item)
        
        # API呼び出しログを記録
        log_api_call(
            note_id=note_id,
            user_id=user_id,  # query パラメータから取得した userId
            action_type='CREATE_NOTE',
            endpoint='/notes',
            method='POST',
            request_body=body,
            response_status=201
        )
        
        return create_response(201, note_item)
        
    except json.JSONDecodeError:
        return create_error_response(
            400,
            'BadRequest',
            'リクエストボディのJSON形式が不正です'
        )
    except Exception as e:
        logger.error(f"Error in create_note: {str(e)}")
        return create_error_response(
            500,
            'InternalServerError',
            'サーバー内部でエラーが発生しました'
        )


def get_note(event: Dict) -> Dict:
    """メモ取得 (GET /notes/{noteId})"""
    try:
        note_id = event['pathParameters']['noteId']
        
        response = notes_table.get_item(Key={'noteId': note_id})
        
        if 'Item' not in response:
            return create_error_response(
                404,
                'NotFound',
                '指定されたメモが見つかりません'
            )
        
        note = response['Item']
        
        # API呼び出しログを記録
        log_api_call(
            note_id=note_id,
            user_id=note.get('userId'),
            action_type='GET_NOTE',
            endpoint=f'/notes/{note_id}',
            method='GET',
            request_body=None,
            response_status=200
        )
        
        return create_response(200, note)
        
    except Exception as e:
        logger.error(f"Error in get_note: {str(e)}")
        return create_error_response(
            500,
            'InternalServerError',
            'サーバー内部でエラーが発生しました'
        )


def update_note(event: Dict) -> Dict:
    """メモ更新 (PUT /notes/{noteId})"""
    try:
        note_id = event['pathParameters']['noteId']
        body = json.loads(event.get('body', '{}'))
        
        # 既存メモの確認
        response = notes_table.get_item(Key={'noteId': note_id})
        if 'Item' not in response:
            return create_error_response(
                404,
                'NotFound',
                '指定されたメモが見つかりません'
            )
        
        # 更新式の構築
        update_expression = 'SET updatedAt = :updatedAt'
        expression_values = {':updatedAt': datetime.utcnow().isoformat() + "Z"}
        
        if 'title' in body:
            if len(body['title']) > 200:
                return create_error_response(
                    400,
                    'BadRequest',
                    'タイトルは200文字以内にしてください',
                    {'field': 'title', 'reason': 'maxLength'}
                )
            update_expression += ', title = :title'
            expression_values[':title'] = body['title']
        
        if 'content' in body:
            if len(body['content']) > 10000:
                return create_error_response(
                    400,
                    'BadRequest',
                    '本文は10000文字以内にしてください',
                    {'field': 'content', 'reason': 'maxLength'}
                )
            update_expression += ', content = :content'
            expression_values[':content'] = body['content']
        
        if 'tags' in body:
            update_expression += ', tags = :tags'
            expression_values[':tags'] = body['tags']
        
        # メモ更新
        response = notes_table.update_item(
            Key={'noteId': note_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
            ReturnValues='ALL_NEW'
        )
        
        updated_note = response['Attributes']
        
        # API呼び出しログを記録
        log_api_call(
            note_id=note_id,
            user_id=updated_note.get('userId'),
            action_type='UPDATE_NOTE',
            endpoint=f'/notes/{note_id}',
            method='PUT',
            request_body=body,
            response_status=200
        )
        
        return create_response(200, updated_note)
        
    except json.JSONDecodeError:
        return create_error_response(
            400,
            'BadRequest',
            'リクエストボディのJSON形式が不正です'
        )
    except Exception as e:
        logger.error(f"Error in update_note: {str(e)}")
        return create_error_response(
            500,
            'InternalServerError',
            'サーバー内部でエラーが発生しました'
        )


def delete_note(event: Dict) -> Dict:
    """メモ削除 (DELETE /notes/{noteId})"""
    try:
        note_id = event['pathParameters']['noteId']
        
        # 既存メモの確認
        response = notes_table.get_item(Key={'noteId': note_id})
        if 'Item' not in response:
            return create_error_response(
                404,
                'NotFound',
                '指定されたメモが見つかりません'
            )
        
        note = response['Item']
        
        # メモ削除
        notes_table.delete_item(Key={'noteId': note_id})
        
        # API呼び出しログを記録
        log_api_call(
            note_id=note_id,
            user_id=note.get('userId'),
            action_type='DELETE_NOTE',
            endpoint=f'/notes/{note_id}',
            method='DELETE',
            request_body=None,
            response_status=204
        )
        
        return create_response(204, {})
        
    except Exception as e:
        logger.error(f"Error in delete_note: {str(e)}")
        return create_error_response(
            500,
            'InternalServerError',
            'サーバー内部でエラーが発生しました'
        )


def lambda_handler(event: Dict, context: Any) -> Dict:
    """
    Lambda ハンドラー関数
    
    OpenAPI仕様に従ったRESTful APIのルーティングを行います。
    """
    logger.info(f"Event: {json.dumps(event)}")
    
    # HTTPメソッドとパスを取得
    http_method = event.get('httpMethod', '')
    path = event.get('path', '')
    
    # ルーティング
    if path == '/notes' and http_method == 'GET':
        return list_notes(event)
    elif path == '/notes' and http_method == 'POST':
        return create_note(event)
    elif path.startswith('/notes/') and http_method == 'GET':
        return get_note(event)
    elif path.startswith('/notes/') and http_method == 'PUT':
        return update_note(event)
    elif path.startswith('/notes/') and http_method == 'DELETE':
        return delete_note(event)
    else:
        return create_error_response(
            404,
            'NotFound',
            '指定されたエンドポイントが見つかりません'
        )
