"""実行状態ファイル(runs/<系統>/<配信日>[-<編>].json)の読み書き・壊れたファイルの退避・当日の状態の更新。

書式の正は specs/batch-runner/appendix.md「実行状態ファイル」。実行係だけが書く。
"""

import json
import os
import tempfile

from . import calendar as cal

STATUSES = ("pending", "retry_pending", "succeeded", "failed")
REQUIRED = ("app", "kind", "date", "status", "attempts", "notified")
_OPTIONAL_DEFAULTS = {
    "edition": None,
    "maxAttempts": None,
    "finalReason": None,
    "notifyReason": None,
    "lastHandoff": None,
    "warningNotified": False,
    "warningNotifyReason": None,
    "lastWarningHandoff": None,
}


class StateBroken(Exception):
    """実行状態ファイルが空・JSON として壊れている・必須項目が欠けている。"""


def ensure_private_dir(path):
    """フォルダを作り(親も含む)、作ったフォルダの権限を 700 にする。"""
    missing = []
    current = os.path.abspath(path)
    while not os.path.isdir(current):
        missing.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    for d in reversed(missing):
        try:
            os.mkdir(d, 0o700)
        except FileExistsError:
            pass
        os.chmod(d, 0o700)


def file_stem(date, edition):
    return f"{date}-{edition}" if edition else date


def path_for(data_dir, kind, date, edition):
    return os.path.join(data_dir, "runs", kind, file_stem(date, edition) + ".json")


def empty(app, kind, date, edition, max_attempts):
    data = {
        "app": app,
        "kind": kind,
        "date": date,
        "edition": edition,
        "maxAttempts": max_attempts,
        "status": "pending",
        "attempts": [],
        "notified": False,
    }
    for key, value in _OPTIONAL_DEFAULTS.items():
        data.setdefault(key, value)
    return data


def load(path, **identity):
    """無ければ未着手の空の状態、読めれば dict、壊れていれば StateBroken。"""
    if not os.path.exists(path):
        return empty(**identity)
    return read(path)


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise StateBroken(f"読めません: {type(e).__name__}: {e}") from e
    try:
        data = json.loads(text)
    except ValueError as e:
        raise StateBroken(f"JSON として壊れています: {e}") from e
    if not isinstance(data, dict):
        raise StateBroken("JSON のオブジェクトではありません")
    missing = [key for key in REQUIRED if key not in data]
    if missing:
        raise StateBroken(f"必須項目がありません: {', '.join(missing)}")
    if data["status"] not in STATUSES or not isinstance(data["attempts"], list) or not isinstance(data["notified"], bool):
        raise StateBroken("必須項目の値が不正です")
    for key, value in _OPTIONAL_DEFAULTS.items():
        if data.get(key) is None:
            data[key] = value
    return data


def quarantine(path, now):
    """壊れたファイルを <元の名前>.corrupt-<YYYYMMDD-HHMMSS> に退避し、退避先を返す。"""
    moved = f"{path}.corrupt-{cal.to_jst(now).strftime('%Y%m%d-%H%M%S')}"
    os.replace(path, moved)
    return moved


def save(path, data):
    """同じフォルダの一時ファイルに書いてから置き換える(フォルダ 700・ファイル 600)。"""
    folder = os.path.dirname(path)
    ensure_private_dir(folder)
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def add_attempt(data, attempt):
    record = dict(attempt)
    if record.get("manual"):
        record.pop("no", None)
    data["attempts"].append(record)


def set_status(data, status, final_reason=None):
    if status not in STATUSES:
        raise ValueError(status)
    data["status"] = status
    data["finalReason"] = final_reason if status == "failed" else None


def scheduled_attempts(data):
    return sum(1 for a in data["attempts"] if not a.get("manual"))


def last_attempt(data):
    return data["attempts"][-1] if data["attempts"] else None


def has_warnings(data):
    return any(a.get("warnings") for a in data["attempts"])
