"""未実体化(dataless)ファイルの実体化許可と判別。

OneDriveのFiles On-Demandで届いたファイルには、中身をまだ持たない
「未実体化(dataless)」の状態がある。通常のプロセスは読み取りが実体化
(内容のダウンロード)を引き起こすが、**launchdから起動されたプロセスは
既定でこれが働かず、読み取りが EDEADLK で即座に失敗する**(実機で発生。
2026-08-27)。起動時に自プロセスへ実体化を許可することで、OneDriveの
自動ダウンロード(「常にこのデバイス上に保持」)に頼らず自力で読めるようにする。

対応する仕様: requirements.md#実行環境 [4] / design.md#エラーハンドリング 8
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

#: <sys/resource.h> の定数。Pythonの標準モジュールには含まれないため直接持つ。
IOPOL_TYPE_VFS_MATERIALIZE_DATALESS_FILES = 3
IOPOL_SCOPE_PROCESS = 0
IOPOL_MATERIALIZE_DATALESS_FILES_ON = 2

#: <sys/stat.h> の SF_DATALESS。未実体化ファイルの st_flags に立つ。
SF_DATALESS = 0x40000000


def 実体化を許可する() -> bool:
    """未実体化ファイルの読み取りが実体化を引き起こすことを自プロセスに許可する。

    **失敗しても例外にしない。** 許可が効かなくても、読み取れないファイルは
    持ち越しで守られる(design.md#エラーハンドリング 8)ため、起動を止める
    ほどの失敗ではない。
    """
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        結果 = libc.setiopolicy_np(
            IOPOL_TYPE_VFS_MATERIALIZE_DATALESS_FILES,
            IOPOL_SCOPE_PROCESS,
            IOPOL_MATERIALIZE_DATALESS_FILES_ON,
        )
    except OSError as 例外:
        logger.warning("実体化の許可を設定できない(libcを読み込めない): %s", 例外)
        return False
    if 結果 != 0:
        logger.warning(
            "実体化の許可を設定できない: setiopolicy_np=%d errno=%d",
            結果,
            ctypes.get_errno(),
        )
        return False
    logger.debug("未実体化ファイルの実体化を自プロセスに許可した")
    return True


def 未実体化か(パス: Path) -> bool:
    """ファイルが未実体化(dataless)かどうかを返す。

    判別はログを充実させるための補助であり、判別の失敗が処理を止めては
    ならない。statに失敗した場合は False を返す。
    """
    try:
        情報 = os.stat(パス)
    except OSError:
        return False
    return bool(getattr(情報, "st_flags", 0) & SF_DATALESS)
