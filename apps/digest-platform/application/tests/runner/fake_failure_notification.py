"""環境スモーク(batch-runner タスク21)用の偽の失敗通知。

failure-notification が未実装の間、実行係の引き渡し(handoff.py)から契約どおりの12項目を受け取り、
データフォルダの handoff-received.json に書き出して「通知した」を返す。Teams へは何も送らない。
契約の正は specs/batch-runner/appendix.md「失敗通知に渡す項目と返る項目」。

使い方(手元のターミナル。application を作業フォルダにして):

    PYTHONPATH="$PWD/tests/runner" DIGEST_HANDOFF_MODULE=fake_failure_notification \\
        python3 launchd/runner.py smoke publish --manual
"""

import datetime as dt
import json
import os

EXPECTED_KEYS = (
    "app",
    "kind",
    "date",
    "edition",
    "attempt",
    "maxAttempts",
    "manual",
    "failureKind",
    "finalReason",
    "failedAt",
    "alreadyNotified",
    "logPath",
)
FILE_NAME = "handoff-received.json"


def _data_dir(failure):
    configured = os.environ.get("DIGEST_DATA_DIR")
    if configured:
        return configured
    app = failure.get("app") or "unknown"
    return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "digest", app)


def judge_and_notify(failure):
    """受け取った12項目を記録して {"notified": True, "reason": "notified"} を返す。"""
    data_dir = _data_dir(failure)
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, FILE_NAME)
    try:
        with open(path, encoding="utf-8") as f:
            received = json.load(f)
        if not isinstance(received, list):
            received = [received]
    except (OSError, ValueError):
        received = []
    received.append(
        {
            "receivedAt": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds"),
            "missingKeys": [key for key in EXPECTED_KEYS if key not in failure],
            "extraKeys": [key for key in failure if key not in EXPECTED_KEYS],
            "failure": failure,
        }
    )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(received, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return {"notified": True, "reason": "notified"}
