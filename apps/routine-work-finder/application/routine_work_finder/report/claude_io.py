"""Claude とのやり取りの控え(design.md「Claudeとのやり取りの控えを残す」、appendix.md「Claudeとのやり取りの控えの形」)。

Claude を呼ぶたびに、送った指示文と材料・受け取った応答の本文(検査する前)・成否を、データフォルダの
claude-io/<作成日時>-<週の名前>/ に残す。自動化案が0件になった週などに人が読んで原因を調べるためのもので、
週次レポート係はあとから読まない。フォルダは700、ファイルは600。

- 書けないときはその作成回の残りをあきらめ、ログに WARN を書いて呼び出しとレポートの作成を続ける
- 起動のたびに、フォルダ名の先頭の日付(日本時間)が今日の28日前より前の作成回をまるごと消す。消せなければ次の起動で消す
- ログに材料と応答の中身は書かない(控えにだけ残す)
"""

import errno
import json
import logging
import os
import re
import shutil
import stat
from datetime import datetime
from pathlib import Path

from routine_work_finder import weeks

LOGGER = logging.getLogger("routine_work_finder.report")
RETENTION_DAYS = weeks.RETENTION_DAYS
DIR_MODE = 0o700
FILE_MODE = 0o600
# 作成回のフォルダの名前。先頭の8桁が作った日(日本時間)。同じ名前があれば末尾に -2・-3 の連番
FOLDER_NAME = re.compile(r"^(?P<day>\d{8})-\d{6}-\d{4}-W\d{2}(-\d+)?$")
MAX_SEQUENCE = 1000


def _write_file(path, text):
    """権限600で書く(テストで差し替えて書けない場合を作る)"""
    with open(path, "w", encoding="utf-8", opener=lambda name, flags: os.open(name, flags, FILE_MODE)) as file:
        file.write(text)
    os.chmod(path, FILE_MODE)


class ExchangeStore:
    """1つの作成回の控え。folder が None のときは何も書かない(控えをあきらめた・テストで控えを使わない)"""

    def __init__(self, folder, now, logger=None):
        self.folder = folder
        self.now = now
        self.logger = logger or LOGGER
        self.prompts_written = set()

    @classmethod
    def disabled(cls):
        return cls(None, None)

    @classmethod
    def open(cls, root, week_name, kind, partial, period_end, now, logger=None):
        """作成回のフォルダを作り、build.json を書く(手順1)。作れなければ WARN を書いて無効な控えを返す"""
        logger = logger or LOGGER
        started = weeks.to_tokyo(now())
        base_name = f"{started.strftime('%Y%m%d-%H%M%S')}-{week_name}"
        store = cls(None, now, logger)
        try:
            Path(root).mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
            os.chmod(root, DIR_MODE)
            folder = _unique_folder(Path(root), base_name)
            folder.mkdir(mode=DIR_MODE)
            os.chmod(folder, DIR_MODE)
        except OSError as error:
            logger.warning("claude-io write failed file=%s errno=%s", base_name, error.errno)
            return store
        store.folder = folder
        build = {"week": week_name, "kind": kind, "partial": partial, "startedAt": started.isoformat(),
                 "periodEnd": weeks.to_tokyo(period_end).isoformat()}
        if store._write("build.json", json.dumps(build, ensure_ascii=False)):
            logger.info("claude-io dir=%s", folder)
        return store

    def save_prompt(self, name, text):
        """指示文は呼び出しの種類ごとに1つ(手順2)"""
        if name in self.prompts_written:
            return
        self.prompts_written.add(name)
        self._write(f"{name}.prompt.md", text)

    def save_materials(self, name, attempt, stdin_text):
        """呼ぶ前に、標準入力に渡す文字列をそのまま(手順3)"""
        self._write(f"{name}-{attempt}.materials.json", stdin_text)

    def save_response(self, name, attempt, output):
        """受け取った直後に、検査する前の本文をそのまま(手順4)。本文が無い呼び出しでは呼ばない"""
        self._write(f"{name}-{attempt}.response.txt", output)

    def save_result(self, name, attempt, ok, reason, detail, seconds, chars):
        """成否・失敗の分類と詳細・所要秒数・材料の字数・終了日時(手順4)"""
        if self.folder is None:
            return
        finished = weeks.to_tokyo(self.now()).isoformat()
        result = {"ok": ok, "reason": reason, "detail": detail, "seconds": seconds, "chars": chars, "finishedAt": finished}
        self._write(f"{name}-{attempt}.result.json", json.dumps(result, ensure_ascii=False))

    def _write(self, file_name, text):
        """書けなければ WARN を書き、この作成回の残りはあきらめる(手順5)。書けたら True"""
        if self.folder is None:
            return False
        try:
            _write_file(self.folder / file_name, text)
        except OSError as error:
            self.logger.warning("claude-io write failed file=%s errno=%s", file_name, error.errno)
            self.folder = None
            return False
        return True


def _unique_folder(root, base_name):
    """同じ名前があれば末尾に -2・-3 の連番を付ける"""
    candidate = root / base_name
    sequence = 1
    while candidate.exists() or candidate.is_symlink():
        sequence += 1
        if sequence > MAX_SEQUENCE:
            raise OSError(errno.EEXIST, "同じ名前のフォルダが多すぎます")
        candidate = root / f"{base_name}-{sequence}"
    return candidate


def purge_old(root, now, logger=None):
    """28日を過ぎた作成回のフォルダを消す(手順6)。消した数と消せなかった数を返し、ログに書く"""
    logger = logger or LOGGER
    root = Path(root)
    today = weeks.to_tokyo(now).date()
    purged = failed = 0
    try:
        entries = sorted(root.iterdir()) if root.is_dir() else []
    except OSError as error:
        # claude-io/ 自体が読めなくても起動は止めない(手順6・エラーハンドリング)
        logger.warning("claude-io purge failed dir=%s errno=%s", root.name, error.errno)
        entries = []
    if entries:
        for path in entries:
            match = FOLDER_NAME.match(path.name)
            if match is None:
                continue
            try:
                info = path.lstat()
            except OSError as error:
                # claude-io/ の一覧は読めても中に入れない(権限0400など)と項目の種類が取れない。
                # 消せなかった数に入れて起動は止めない(Python の版によって is_symlink が例外を投げるか黙って False を返すかが違うため lstat で確かめる)
                failed += 1
                logger.warning("claude-io purge failed dir=%s errno=%s", path.name, error.errno)
                continue
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                continue
            try:
                day = datetime.strptime(match.group("day"), "%Y%m%d").date()
            except ValueError:
                continue
            if (today - day).days <= RETENTION_DAYS:
                continue
            try:
                shutil.rmtree(path)
                purged += 1
            except OSError as error:
                failed += 1
                logger.warning("claude-io purge failed dir=%s errno=%s", path.name, error.errno)
    logger.info("claude-io purged=%d failed=%d", purged, failed)
    return purged, failed
