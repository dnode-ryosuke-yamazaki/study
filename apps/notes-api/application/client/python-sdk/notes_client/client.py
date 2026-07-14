"""
Notes API Client Implementation

このモジュールは、Notes APIに対するHTTPクライアントの実装を提供します。
OpenAPI 3.0.3仕様に基づいたNotes APIのエンドポイントをすべてサポートしています。
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib import error, parse, request

# ============================================================================
# 例外クラス
# ============================================================================


@dataclass
class ApiError(Exception):
    """APIエラーレスポンスを表現する例外クラス"""
    status_code: int
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        return f"{self.status_code} {self.error}: {self.message}"


# ============================================================================
# APIクライアントクラス
# ============================================================================


class NotesClient:
    """Notes API client generated from the OpenAPI contract shape.

    base_url examples:
      - https://xxxxx.execute-api.ap-northeast-1.amazonaws.com/yamazaki-dev
      - https://xxxxx.execute-api.ap-northeast-1.amazonaws.com/yamazaki-stg
    """

    def __init__(self, base_url: str, timeout: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def list_notes(self, user_id: str) -> Dict[str, Any]:
        """メモ一覧を取得する
        
        Args:
            user_id: ユーザーID
            
        Returns:
            {'notes': [Note]}の形式で、ユーザーが所有するメモのリストを返す
        """
        return self._request("GET", "/notes", query={"userId": user_id})

    def create_note(self, user_id: str, title: str, content: str, tags: Optional[list[str]] = None) -> Dict[str, Any]:
        """新規メモを作成する
        
        Args:
            user_id: ユーザーID
            title: メモのタイトル（最大200文字）
            content: メモの本文（最大10000文字）
            tags: メモに付与するタグの配列（オプション）
            
        Returns:
            作成されたNote オブジェクトを返す
        """
        payload: Dict[str, Any] = {
            "title": title,
            "content": content,
        }
        if tags is not None:
            payload["tags"] = tags
        return self._request("POST", "/notes", query={"userId": user_id}, body=payload)

    def get_note(self, note_id: str) -> Dict[str, Any]:
        """指定されたIDのメモを取得する
        
        Args:
            note_id: メモID
            
        Returns:
            Note オブジェクトを返す
        """
        return self._request("GET", f"/notes/{parse.quote(note_id)}")

    def update_note(
        self,
        note_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """指定されたIDのメモを更新する
        
        Args:
            note_id: メモID
            title: 新しいタイトル（オプション）
            content: 新しい本文（オプション）
            tags: 新しいタグ配列（オプション）
            
        Returns:
            更新されたNote オブジェクトを返す
            
        Raises:
            ValueError: 更新内容が1つも指定されていない場合
        """
        payload: Dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if content is not None:
            payload["content"] = content
        if tags is not None:
            payload["tags"] = tags

        if not payload:
            raise ValueError("At least one field must be provided for update")

        return self._request("PUT", f"/notes/{parse.quote(note_id)}", body=payload)

    def delete_note(self, note_id: str) -> None:
        """指定されたIDのメモを削除する
        
        Args:
            note_id: メモID
        """
        self._request("DELETE", f"/notes/{parse.quote(note_id)}", expected_status=(204,))

    # ========================================================================
    # プライベートメソッド（内部処理）
    # ========================================================================

    def _request(
        self,
        method: str,
        path: str,
        query: Optional[Dict[str, str]] = None,
        body: Optional[Dict[str, Any]] = None,
        expected_status: tuple[int, ...] = (200, 201),
    ) -> Dict[str, Any]:
        """HTTPリクエストを実行する（内部メソッド）
        
        Args:
            method: HTTPメソッド（GET, POST, PUT, DELETE）
            path: APIパス（例: /notes/{noteId}）
            query: クエリパラメータ
            body: リクエストボディ
            expected_status: 成功とみなすHTTPステータスコード
            
        Returns:
            レスポンスボディをJSON解析した辞書を返す
            
        Raises:
            ApiError: APIがエラーを返した場合
            ConnectionError: ネットワーク接続エラーの場合
        """
        url = f"{self.base_url}{path}"
        if query:
            url += f"?{parse.urlencode(query)}"

        # ヘッダー構築
        headers = {
            "Accept": "application/json",
        }
        data: Optional[bytes] = None

        # リクエストボディをJSON形式でエンコード
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")

        # URLオープンリクエスト生成
        req = request.Request(url=url, method=method, headers=headers, data=data)

        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                if resp.status not in expected_status:
                    self._raise_api_error(resp.status, raw)
                if not raw:
                    return {}
                return json.loads(raw)
        # HTTPエラーレスポンスをハンドル
        except error.HTTPError as http_err:
            raw = http_err.read().decode("utf-8", errors="replace") if http_err.fp else ""
            self._raise_api_error(http_err.code, raw)
        # ネットワーク接続エラーをハンドル
        except error.URLError as url_err:
            raise ConnectionError(f"Failed to connect to API: {url_err.reason}") from url_err

        return {}

    def _raise_api_error(self, status_code: int, raw_body: str) -> None:
        """APIエラーレスポンスを例外に変換する（内部メソッド）
        
        Args:
            status_code: HTTPステータスコード
            raw_body: レスポンスボディ（JSON形式の文字列）
            
        Raises:
            ApiError: 常に送出される
        """
        # レスポンスボディがJSON形式の場合、パースしてApiErrorとして送出
        if raw_body:
            try:
                parsed = json.loads(raw_body)
                raise ApiError(
                    status_code=status_code,
                    error=parsed.get("error", "ApiError"),
                    message=parsed.get("message", "Unknown API error"),
                    details=parsed.get("details"),
                )
            except json.JSONDecodeError:
                pass

        # JSON形式でない場合は、ボディをそのままメッセージとして使用
        raise ApiError(
            status_code=status_code,
            error="ApiError",
            message=raw_body or "Unknown API error",
            details=None,
        )
