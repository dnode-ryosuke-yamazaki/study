"""性能テスト(tests/perf)専用の小道具。tests/runner/ の道具は参考にするだけで、ここでは使わない。"""

import datetime as dt
import json
import os
import tempfile

JST = dt.timezone(dt.timedelta(hours=9))
FAKE_MODULE = "fake_failure_notification_for_perf_test"

BATCH = """#!/bin/sh
mkdir -p out
: > "out/$DIGEST_DATE$EDITION_SUFFIX.txt"
echo DIGEST-BATCH-OK
exit 0
"""


def make_app_root(root):
    """即終了する偽のバッチを置き、その絶対パスを返す。find_tsx が見るダミーの tsx も用意する。"""
    os.makedirs(os.path.join(root, "node_modules", ".bin"))
    tsx = os.path.join(root, "node_modules", ".bin", "tsx")
    open(tsx, "w").close()
    os.chmod(tsx, 0o755)
    batch = os.path.join(root, "batch.sh")
    with open(batch, "w") as f:
        f.write(BATCH.replace("$EDITION_SUFFIX", '${DIGEST_EDITION:+-$DIGEST_EDITION}'))
    os.chmod(batch, 0o755)
    return batch


def make_registry(root, batch, app="research-digest", weekdays=(6,)):
    """記事公開だけを有効にした登録表を書き、パスを返す。"""
    data = {
        "apps": {
            app: {
                "publish": {
                    "enabled": True,
                    "weekdays": list(weekdays),
                    "editionByWeekday": None,
                    "maxAttempts": 4,
                    "command": ["/bin/sh", batch],
                    "artifacts": ["out/{date}{edition}.txt"],
                }
            }
        }
    }
    path = os.path.join(root, "launchd", "apps.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def make_filler_files(data_dir, now, count=300, age_days=100):
    """90日分相当の古いファイルを runs/logs/claude-io の publish 配下に count 件作る。

    古さはテストが実行係に渡す時刻 now を基準にする(実行係の掃除は clock の時刻で90日を数えるため、
    実時刻を基準にすると固定した now より未来のファイルになり、掃除の対象にならない)。
    """
    old_time = now.timestamp() - age_days * 86400
    per_dir = count // 3
    for target in ("runs", "logs", "claude-io"):
        folder = os.path.join(data_dir, target, "publish")
        os.makedirs(folder, exist_ok=True)
        for i in range(per_dir):
            path = os.path.join(folder, f"old-{i:04d}.json")
            with open(path, "w") as f:
                f.write("{}")
            os.utime(path, (old_time, old_time))


def install_fake_judge_module(sys_modules, notified_calls, result=None):
    """判定関数(契約どおりの戻り値)を偽のモジュールとして登録する。"""
    import types

    module = types.ModuleType(FAKE_MODULE)

    def judge_and_notify(failure):
        notified_calls.append(dict(failure))
        return dict(result or {"notified": True, "reason": "notified"})

    module.judge_and_notify = judge_and_notify
    sys_modules[FAKE_MODULE] = module
    return FAKE_MODULE


def mkdtemp():
    return tempfile.mkdtemp(prefix="digest-perf-test-")
