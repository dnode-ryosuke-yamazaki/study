"""失敗通知の判定関数の偽物と、実行状態ファイルを用意する小道具。

偽の判定関数は failure-notification の契約(appendix「失敗通知に渡す項目と返る項目」)と同じ形で
12項目を受け取り {"notified", "reason"} を返す。failure-notification の実装後に実関数で置き換える。
"""

import datetime as dt
import os

from digest_runner import state

JST = dt.timezone(dt.timedelta(hours=9))
FAILURE_KEYS = {
    "app", "kind", "date", "edition", "attempt", "maxAttempts", "manual",
    "failureKind", "finalReason", "failedAt", "alreadyNotified", "logPath",
}


class FakeJudge:
    def __init__(self, *results):
        self.calls = []
        self.results = list(results) or [{"notified": True, "reason": "notified"}]

    def __call__(self, failure):
        self.calls.append(dict(failure))
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, BaseException):
            raise result
        return dict(result)


def attempt(no=1, manual=False, result="temporary_failure", ended="2026-11-07T06:41:10+09:00", log="/d/logs/publish/2026-11-07-1.log", warnings=()):
    a = {
        "no": no, "manual": manual, "startedAt": ended, "endedAt": ended, "result": result,
        "missing": [] if result == "succeeded" else ["marker"], "warnings": list(warnings), "logPath": log,
    }
    if manual:
        del a["no"]
    return a


def put_state(data_dir, date, status, attempts=(), app="research-digest", kind="publish", edition=None, max_attempts=4, **extra):
    data = state.empty(app, kind, date, edition, max_attempts)
    for a in attempts:
        state.add_attempt(data, a)
    data["status"] = status
    data.update(extra)
    path = state.path_for(data_dir, kind, date, edition)
    state.save(path, data)
    return path


def read_state(path):
    return state.read(path)
