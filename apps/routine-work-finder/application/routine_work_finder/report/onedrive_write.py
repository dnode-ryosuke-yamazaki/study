"""OneDrive の同期フォルダへの書き込みの対処(design.md「OneDrive への保存のしかた」)。

launchd から起動したプロセスは、同期フォルダの未実体化(dataless)のファイル・フォルダを実体化できず、
読み書きが EDEADLK(Resource deadlock avoided)で失敗する例がある。既存アプリの対処を写して使う。

- 実体化の許可(allow_dataless_materialization)の写した元:
  teams-transcript-fetcher の studyリポジトリ apps/teams-transcript-fetcher/application/materialize.py
  (実体化を許可する)と、その写しの ~/.claude/skills/read-aloud-player/scripts/read_aloud_player/materialize.py
  (allow_dataless_materialization)
- 読んで書く複製(copy_file)の写した元:
  ~/.claude/skills/read-aloud-player/scripts/read_aloud_player/saving.py の _copy_bytes と place_file
  (OS の高速複製を使わずに中身を読んで書き、途中のファイルに書いてから名前を付ける)。
  途中のファイルの名前は appendix.md「週次レポート係が使うファイル」に合わせて <名前>.part にする
"""

import ctypes
import ctypes.util
import logging
import os
import shutil
from pathlib import Path

LOGGER = logging.getLogger("routine_work_finder.report")

#: <sys/resource.h> の定数。Python の標準モジュールには含まれないため直接持つ
IOPOL_TYPE_VFS_MATERIALIZE_DATALESS_FILES = 3
IOPOL_SCOPE_PROCESS = 0
IOPOL_MATERIALIZE_DATALESS_FILES_ON = 2
COPY_CHUNK = 1024 * 1024


def _load_libc():
    return ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)


def allow_dataless_materialization(loader=_load_libc):
    """自分のプロセスに未実体化のファイルの実体化を許可する。失敗しても例外にせず偽を返す(起動は止めない)"""
    try:
        libc = loader()
        result = libc.setiopolicy_np(
            IOPOL_TYPE_VFS_MATERIALIZE_DATALESS_FILES, IOPOL_SCOPE_PROCESS, IOPOL_MATERIALIZE_DATALESS_FILES_ON)
    except OSError as error:
        LOGGER.warning("materialize allowed=false reason=%s", type(error).__name__)
        return False
    if result != 0:
        LOGGER.warning("materialize allowed=false result=%s errno=%s", result, ctypes.get_errno())
        return False
    LOGGER.info("materialize allowed=true")
    return True


def copy_file(source, dest):
    """source の中身を読んで dest.part に書き、dest へ名前を付け替える。同じ名前があれば置き換える。
    失敗したら途中のファイルを消して OSError を返す"""
    source, dest = Path(source), Path(dest)
    part = dest.with_name(dest.name + ".part")
    try:
        with open(source, "rb") as reader, open(part, "wb") as writer:
            shutil.copyfileobj(reader, writer, COPY_CHUNK)
        os.replace(part, dest)
    except OSError:
        try:
            part.unlink(missing_ok=True)
        except OSError:
            LOGGER.warning("onedrive part-file not removed")
        raise
