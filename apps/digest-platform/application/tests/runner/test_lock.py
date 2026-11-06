import json
import os
import time
import unittest

from tests.runner.support import TempDirTestCase

from digest_runner import lock

NOW = 1_800_000_000.0


class 同じアプリと系統の二重起動の防止(TempDirTestCase):
    """手動実行と定時の回、追い実行が重なっても同じアプリ×系統のバッチを二重に動かさない。
    異常終了で残ったロックで翌日以降が止まらないよう、持ち主が居ない古いロックは回収する。"""

    def lock_dir(self):
        return self.path("data", "lock", "publish")

    def leave_lock(self, pid, minutes_ago):
        d = self.lock_dir()
        os.makedirs(d)
        with open(os.path.join(d, "owner.json"), "w") as f:
            json.dump({"pid": pid, "createdAt": NOW - minutes_ago * 60}, f)

    def acquire(self, alive):
        return lock.acquire(self.lock_dir(), pid_alive=lambda pid: alive, now=NOW)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-4
    def test_ロックが無ければ取れて持ち主のプロセス番号が書かれ外すと消える(self):
        self.assertTrue(lock.acquire(self.lock_dir()))
        with open(os.path.join(self.lock_dir(), "owner.json")) as f:
            owner = json.load(f)
        self.assertEqual(owner["pid"], os.getpid())
        self.assertLess(abs(owner["createdAt"] - time.time()), 5)
        lock.release(self.lock_dir())
        self.assertFalse(os.path.exists(self.lock_dir()))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-4
    def test_持ち主のプロセスが生きているロックがあれば取れない(self):
        self.leave_lock(4242, minutes_ago=1)
        self.assertFalse(self.acquire(alive=True))
        self.assertTrue(os.path.isdir(self.lock_dir()))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-4、apps/digest-platform/specs/batch-runner/requirements.md#時間の上限-3
    def test_持ち主が居らず作成から76分たったロックは回収して取れる(self):
        """否定確認: 回収の条件の75分を77分に変えると落ちる"""
        self.leave_lock(4242, minutes_ago=76)
        self.assertTrue(self.acquire(alive=False))
        with open(os.path.join(self.lock_dir(), "owner.json")) as f:
            self.assertEqual(json.load(f)["pid"], os.getpid())

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#時間の上限-3
    def test_持ち主が居なくても作成から74分のロックは回収しない(self):
        """否定確認: 作成時刻との比較を外すと落ちる"""
        self.leave_lock(4242, minutes_ago=74)
        self.assertFalse(self.acquire(alive=False))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#時間の上限-3
    def test_持ち主が生きていれば作成から76分でも回収しない(self):
        """否定確認: プロセスの生死の条件を外すと落ちる"""
        self.leave_lock(4242, minutes_ago=76)
        self.assertFalse(self.acquire(alive=True))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#時間の上限-3
    def test_作成から25時間たったロックは持ち主が生きていても回収する(self):
        """否定確認: 24時間の無条件の回収を消すと落ちる"""
        self.leave_lock(4242, minutes_ago=25 * 60)
        self.assertTrue(self.acquire(alive=True))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#時間の上限-3
    def test_持ち主の記録が読めないロックはフォルダの更新時刻で古さを決める(self):
        os.makedirs(self.lock_dir())
        os.utime(self.lock_dir(), (NOW - 80 * 60, NOW - 80 * 60))
        self.assertTrue(self.acquire(alive=True))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#時間の上限-3
    def test_プロセスの生死は既定では実在のプロセス番号で確かめる(self):
        self.assertTrue(lock.pid_alive(os.getpid()))
        self.assertFalse(lock.pid_alive(2 ** 22 + 12345))


if __name__ == "__main__":
    unittest.main()
