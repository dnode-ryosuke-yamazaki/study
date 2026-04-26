"""
Notes API Client Package

このパッケージは、OpenAPI仕様に準拠したNotes APIに対応したクライアントを提供します。
Python環境での利用を想定しています。
"""

from .client import ApiError, NotesClient

__all__ = ["NotesClient", "ApiError"]
