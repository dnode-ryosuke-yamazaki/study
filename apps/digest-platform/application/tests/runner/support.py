"""実行係のテストで共有する小道具(一時フォルダ・テスト用の登録表)。"""

import copy
import json
import os
import shutil
import tempfile
import unittest

DAILY = [0, 1, 2, 3, 4, 5, 6]


def publish_entry(app, weekdays=None, enabled=True, edition_by_weekday=None, max_attempts=4):
    return {
        "enabled": enabled,
        "weekdays": list(DAILY if weekdays is None else weekdays),
        "editionByWeekday": edition_by_weekday,
        "maxAttempts": max_attempts,
        "command": ["{node}", "{tsx}", f"../../{app}/application/batch/publish.ts"],
        "artifacts": [
            f"../../{app}/application/articles/{{date}}{{edition}}.json",
            f"out/{app}/{{date}}{{edition}}/index.html",
        ],
    }


def review_entry(app, day_of_month=1):
    return {
        "dayOfMonth": day_of_month,
        "maxAttempts": 1,
        "command": ["{node}", "{tsx}", f"../../{app}/application/batch/review.ts"],
        "artifacts": [f"../../{app}/application/reviews/{{yearMonth}}.md"],
    }


def all_enabled_registry():
    """5アプリとも記事公開を有効にし、月次見直しの日を埋めたテスト用の登録表。"""
    apps = {}
    for app, weekdays in (
        ("ai-dev-digest", DAILY),
        ("news-digest", DAILY),
        ("future-digest", [0]),
        ("research-digest", [6]),
        ("trend-digest", DAILY),
    ):
        apps[app] = {"publish": publish_entry(app, weekdays), "review": review_entry(app, 1)}
    return {"apps": apps}


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp(prefix="digest-runner-test-")
        self.addCleanup(self._cleanup_tmp)

    def _cleanup_tmp(self):
        for root, dirs, _files in os.walk(self.tmp):
            for d in dirs:
                try:
                    os.chmod(os.path.join(root, d), 0o700)
                except OSError:
                    pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def path(self, *parts):
        return os.path.join(self.tmp, *parts)

    def write_json(self, rel, data):
        p = self.path(rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return p

    def write_text(self, rel, text):
        p = self.path(rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p


def clone(data):
    return copy.deepcopy(data)
