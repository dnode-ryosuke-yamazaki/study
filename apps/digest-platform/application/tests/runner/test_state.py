import datetime as dt
import json
import os
import stat
import unittest

from tests.runner.support import TempDirTestCase

from digest_runner import state

JST = dt.timezone(dt.timedelta(hours=9))
IDENTITY = dict(app="research-digest", kind="publish", date="2026-11-07", edition=None, max_attempts=4)


def an_attempt(no=1, manual=False, result="temporary_failure"):
    return {
        "no": None if manual else no,
        "manual": manual,
        "startedAt": "2026-11-07T06:30:02+09:00",
        "endedAt": "2026-11-07T06:41:10+09:00",
        "result": result,
        "missing": ["marker"] if result != "succeeded" else [],
        "warnings": [],
        "logPath": "/x/logs/publish/2026-11-07-1.log",
    }


class 実行状態ファイルの読み書き(TempDirTestCase):
    """配信日・編ごとの試行回数・各回の結果・通知済みを、後から運営者が確かめられる形で残す。
    書き込みの途中で落ちても壊れたファイルを残さず、他人に読まれない権限で置く。"""

    def state_path(self):
        return state.path_for(self.path("digest", "research-digest"), "publish", "2026-11-07", None)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-1
    def test_無いファイルを読むと未着手の空の記録になり書いて読み直すと同じ内容に戻る(self):
        path = self.state_path()
        data = state.load(path, **IDENTITY)
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["attempts"], [])
        self.assertIs(data["notified"], False)
        state.add_attempt(data, an_attempt(1))
        state.set_status(data, "retry_pending")
        state.save(path, data)
        again = state.load(path, **IDENTITY)
        self.assertEqual(again, data)
        self.assertEqual(state.scheduled_attempts(again), 1)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-1
    def test_書いたファイルはJSONとして読め必須項目と通知の印を失敗用と警告用で別に持つ(self):
        """否定確認: save で必須項目の1つを落として書くと落ちる"""
        path = self.state_path()
        data = state.load(path, **IDENTITY)
        state.add_attempt(data, an_attempt(1, result="succeeded"))
        state.set_status(data, "succeeded")
        state.save(path, data)
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        for key in ("app", "kind", "date", "edition", "maxAttempts", "status", "attempts", "finalReason",
                    "notified", "notifyReason", "lastHandoff",
                    "warningNotified", "warningNotifyReason", "lastWarningHandoff"):
            self.assertIn(key, raw)
        self.assertEqual(raw["status"], "succeeded")
        self.assertEqual(raw["attempts"][0]["result"], "succeeded")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode), 0o700)
        self.assertEqual([n for n in os.listdir(os.path.dirname(path)) if n != os.path.basename(path)], [])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-3
    def test_空のファイルは壊れた記録になる(self):
        path = self.state_path()
        os.makedirs(os.path.dirname(path))
        open(path, "w").close()
        with self.assertRaises(state.StateBroken):
            state.load(path, **IDENTITY)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-3
    def test_JSONとして壊れたファイルは壊れた記録になる(self):
        path = self.state_path()
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as f:
            f.write('{"app": "research-digest", "status": ')
        with self.assertRaises(state.StateBroken):
            state.load(path, **IDENTITY)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-3
    def test_必須項目が欠けたファイルは壊れた記録になる(self):
        """否定確認: 必須項目の検査を消すと落ちる"""
        path = self.state_path()
        os.makedirs(os.path.dirname(path))
        data = state.empty(**IDENTITY)
        del data["notified"]
        with open(path, "w") as f:
            json.dump(data, f)
        with self.assertRaises(state.StateBroken):
            state.load(path, **IDENTITY)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-3
    def test_壊れた記録は元の名前に退避の印と日時を付けて同じフォルダに移す(self):
        """否定確認: 日時の書式を変えると落ちる"""
        path = self.state_path()
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as f:
            f.write("{")
        moved = state.quarantine(path, dt.datetime(2026, 11, 7, 6, 30, 5, tzinfo=JST))
        self.assertEqual(moved, path + ".corrupt-20261107-063005")
        self.assertFalse(os.path.exists(path))
        with open(moved) as f:
            self.assertEqual(f.read(), "{")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-1
    def test_警告側の項目が無い古いファイルは警告を通知していないものとして読む(self):
        path = self.state_path()
        data = state.empty(**IDENTITY)
        for key in ("warningNotified", "warningNotifyReason", "lastHandoff", "lastWarningHandoff"):
            del data[key]
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as f:
            json.dump(data, f)
        got = state.load(path, **IDENTITY)
        self.assertIs(got["warningNotified"], False)
        self.assertIsNone(got["warningNotifyReason"])
        self.assertIsNone(got["lastHandoff"])
        self.assertIsNone(got["lastWarningHandoff"])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-1
    def test_定時の試行回数には手動実行を数えず失敗確定には理由が付く(self):
        data = state.empty(**IDENTITY)
        state.add_attempt(data, an_attempt(1))
        state.add_attempt(data, an_attempt(manual=True))
        self.assertEqual(state.scheduled_attempts(data), 1)
        self.assertNotIn("no", data["attempts"][1])
        state.set_status(data, "failed", final_reason="exhausted")
        self.assertEqual((data["status"], data["finalReason"]), ("failed", "exhausted"))
        state.set_status(data, "succeeded")
        self.assertIsNone(data["finalReason"])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-1
    def test_編のある記録は配信日と編を名前に持つ(self):
        p = state.path_for("/d", "publish", "2026-11-07", "sci")
        self.assertEqual(p, "/d/runs/publish/2026-11-07-sci.json")


if __name__ == "__main__":
    unittest.main()
