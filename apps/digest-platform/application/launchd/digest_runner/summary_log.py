"""アプリ×系統ごとの要約ログ runner-<系統>.log の書き出し。

行頭は日本時間のオフセット付き ISO 8601。日次ヘルスチェックは RUN-SUCCEEDED の行の時刻を
最終成功時刻として読み、RUN-FAILED を失敗の印として読む(書式は appendix「要約ログの行」)。
"""

import os

from . import calendar as cal
from .state import ensure_private_dir

SUCCEEDED_MARK = "RUN-SUCCEEDED"
FAILED_MARK = "RUN-FAILED"
_RUNNER_FAILURES = ("unregistered", "runner_error")
_STARTED = " INFO 実行開始: "


def _dash(value):
    return "-" if value is None or value == "" else str(value)


def _append(path, text, now=None):
    moment = cal.to_jst(now) if now is not None else cal.now_jst()
    ensure_private_dir(os.path.dirname(path))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, f"{moment.isoformat(timespec='seconds')} {text}\n".encode())
    finally:
        os.close(fd)


def started(path, context, now=None):
    """バッチを起動する回の「実行開始」。context は app・kind・date・edition・attempt(定時の番号か manual)。"""
    _append(
        path,
        f"INFO 実行開始: app={context['app']} kind={context['kind']} date={_dash(context['date'])}"
        f" edition={_dash(context.get('edition'))} attempt={_dash(context['attempt'])}",
        now,
    )


def finished(path, result, date, edition, attempt, status, log_path, became_failed=False, now=None):
    """起動ごとの「実行終了」。became_failed は、この起動で当日の状態が失敗確定に変わったこと。"""
    marks = []
    if result == "succeeded":
        marks.append(SUCCEEDED_MARK)
    if (became_failed and result != "renotified") or result in _RUNNER_FAILURES:
        marks.append(FAILED_MARK)
    mark_text = "".join(" " + m for m in marks)
    _append(
        path,
        f"INFO 実行終了: result={result} date={_dash(date)} edition={_dash(edition)} attempt={_dash(attempt)}"
        f" status={_dash(status)}{mark_text} log={_dash(log_path)}",
        now,
    )


def warning(path, what, detail, failed=False, now=None):
    _append(path, f"WARNING {what}: {detail}" + (" " + FAILED_MARK if failed else ""), now)


def first_started_date(path):
    """要約ログの最初の「実行開始」の行の配信日(date= の値)。「実行開始」が1行も無ければ None。"""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if _STARTED in line:
                    return _field(line, "date")
    except FileNotFoundError:
        pass
    return None


def _field(line, name):
    for token in line.split():
        key, sep, value = token.partition("=")
        if sep and key == name:
            return None if value == "-" else value
    return None
