import datetime as dt
import os
import unittest

from tests.runner.support import TempDirTestCase

from digest_runner import retention

JST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime(2026, 11, 7, 6, 30, tzinfo=JST)


class 九十日より古い記録の掃除(TempDirTestCase):
    """実行ごとのログ・Claude の控え・実行状態ファイルが無限に増えないようにしつつ、
    障害の調査に四半期分を残す。要約ログと読者データは消さない。"""

    def aged(self, rel, days):
        p = self.write_text(rel, "x")
        t = NOW.timestamp() - days * 86400
        os.utime(p, (t, t))
        return p

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#ログと記録の保持-1
    def test_最後の更新から91日たった記録とログと控えは消え空になったフォルダも消える(self):
        """否定確認: 日数の比較を外すと89日の側が、空フォルダの片付けを消すとフォルダの側が落ちる"""
        runs = self.aged("runs/publish/2026-08-01.json", 91)
        logs = self.aged("logs/publish/2026-08-01-1.log", 91)
        io = self.aged("claude-io/publish/2026-08-01/1-01-prompt.txt", 91)
        summary = self.aged("runner-publish.log", 400)
        reader = self.aged("reader/bookmarks.json", 400)
        deleted, failed = retention.sweep(self.tmp, NOW)
        self.assertEqual(sorted(deleted), sorted([runs, logs, io]))
        self.assertEqual(failed, [])
        self.assertFalse(os.path.exists(self.path("claude-io", "publish", "2026-08-01")))
        self.assertTrue(os.path.isdir(self.path("claude-io")))
        self.assertTrue(os.path.exists(summary))
        self.assertTrue(os.path.exists(reader))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#ログと記録の保持-1
    def test_最後の更新から89日の記録は残る(self):
        kept = self.aged("runs/publish/2026-08-10.json", 89)
        empty_dir = self.path("claude-io", "publish", "2026-11-07")
        os.makedirs(empty_dir)
        deleted, failed = retention.sweep(self.tmp, NOW)
        self.assertEqual((deleted, failed), ([], []))
        self.assertTrue(os.path.exists(kept))
        self.assertTrue(os.path.isdir(empty_dir), "作ったばかりの空のフォルダは消さない")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#ログと記録の保持-1
    def test_消せないファイルがあっても続けて消し消せなかったパスが一覧に載る(self):
        """否定確認: 消せなかったときの例外の受け止めを外すと落ちる"""
        stuck = self.aged("logs/publish/locked/2026-08-01-1.log", 91)
        other = self.aged("runs/publish/2026-08-01.json", 91)
        os.chmod(os.path.dirname(stuck), 0o500)
        deleted, failed = retention.sweep(self.tmp, NOW)
        self.assertEqual(deleted, [other])
        self.assertEqual(failed, [stuck])
        self.assertTrue(os.path.exists(stuck))


if __name__ == "__main__":
    unittest.main()
