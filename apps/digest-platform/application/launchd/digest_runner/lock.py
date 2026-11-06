"""アプリ×系統のロック(mkdir で作るロックフォルダ lock/<系統>)。

ロックフォルダには持ち主の pid と作成時刻を owner.json に書く。持ち主のプロセスが生きておらず、
作成から75分(バッチの上限60分+判定と引き渡しの余裕15分)を過ぎたロックは回収する。
作成から24時間を過ぎたロックは pid によらず回収する(pid が別のプロセスに使い回されたときの保険)。
"""

import json
import os
import shutil
import time

from .state import ensure_private_dir

STALE_SECONDS = 75 * 60
MAX_AGE_SECONDS = 24 * 60 * 60
_OWNER = "owner.json"


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OverflowError, ValueError, TypeError):
        return False
    return True


def _try_create(lock_dir, now):
    try:
        os.mkdir(lock_dir, 0o700)
    except FileExistsError:
        return False
    with open(os.path.join(lock_dir, _OWNER), "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "createdAt": now}, f)
    return True


def _owner(lock_dir):
    try:
        with open(os.path.join(lock_dir, _OWNER), encoding="utf-8") as f:
            data = json.load(f)
        return int(data["pid"]), float(data["createdAt"])
    except (OSError, ValueError, KeyError, TypeError):
        try:
            return None, os.stat(lock_dir).st_mtime
        except OSError:
            return None, None


def acquire(lock_dir, stale_seconds=STALE_SECONDS, pid_alive=pid_alive, now=None, max_age_seconds=MAX_AGE_SECONDS):
    """ロックを取れたら真。持ち主の居ない古いロックは回収して取り直す。"""
    now = time.time() if now is None else now
    ensure_private_dir(os.path.dirname(lock_dir))
    if _try_create(lock_dir, now):
        return True
    pid, created = _owner(lock_dir)
    if created is None:
        return _try_create(lock_dir, now)
    age = now - created
    alive = pid is not None and pid_alive(pid)
    if age > max_age_seconds or (not alive and age > stale_seconds):
        shutil.rmtree(lock_dir, ignore_errors=True)
        return _try_create(lock_dir, now)
    return False


def release(lock_dir):
    shutil.rmtree(lock_dir, ignore_errors=True)
