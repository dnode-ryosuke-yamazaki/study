"""トランスクリプトの書き出し。

**一時ファイルへ書いてから所定の名前へ移す。** 同期フォルダに直接書くと、書き込み
途中の不完全なファイルがOneDriveにアップロードされうる。名前の変更を最後に行うことで、
同期対象になるのは完成したファイルだけになる(design.md#エラーハンドリング 6)。

対応する仕様:
- requirements.md#ファイル名 [7]
- design.md#トランスクリプトの取得と保存 手順6・7
- design.md#セキュリティ(出力先が出力置き場の配下であることの確認)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class 書き出し先が不正(Exception):
    """出力置き場の外へ書き出そうとした。パストラバーサルへの防御。"""


@dataclass(frozen=True)
class 書き出した:
    パス: Path
    バイト数: int


@dataclass(frozen=True)
class 既にあった:
    """同名ファイルが既にある。上書きせずスキップし、取得済みとして扱う。

    仕様: requirements.md#未取得の判定(バッチ) [2]
    """

    パス: Path


書き出し結果 = 書き出した | 既にあった


def 書き出す(本文: bytes, 出力フォルダ: Path, ファイル名: str) -> 書き出し結果:
    """本文をそのまま書き出す。

    本文はバイト列のまま扱う。文字列に変換して書き戻すと改行の変換が入りうるため、
    **応答の改行をそのまま保持する**にはバイト列で通すのが確実。BOMの除去は
    取得側(downloader)で済んでいる。
    """
    出力先 = (出力フォルダ / ファイル名).resolve()
    解決した出力フォルダ = 出力フォルダ.resolve()

    if not 出力先.is_relative_to(解決した出力フォルダ):
        # ファイル名の組み立てでパス区切りは除去しているが、最後の砦として確認する。
        raise 書き出し先が不正(f"出力置き場の外を指している: {ファイル名!r}")

    if 出力先.exists():
        logger.debug("同名ファイルが既にあるためスキップする: %s", 出力先.name)
        return 既にあった(パス=出力先)

    解決した出力フォルダ.mkdir(parents=True, exist_ok=True)
    一時ファイル = 出力先.with_name(出力先.name + ".tmp")
    try:
        一時ファイル.write_bytes(本文)
        os.replace(一時ファイル, 出力先)
    finally:
        一時ファイル.unlink(missing_ok=True)

    logger.info("トランスクリプトを保存した: %s(%dバイト)", 出力先.name, len(本文))
    return 書き出した(パス=出力先, バイト数=len(本文))
