import datetime as dt
import os
import re
import stat
import unittest

from tests.runner.support import TempDirTestCase

from digest_runner import summary_log

LINE = re.compile(r"^\d{4}-\d{2}-\d{2}T[^ ]+ (INFO|WARNING) ")
JST = dt.timezone(dt.timedelta(hours=9))


class 日次ヘルスチェックが読む要約ログ(TempDirTestCase):
    """日次ヘルスチェックは要約ログの行頭の時刻と印で、最終成功時刻(RUN-SUCCEEDED)と失敗(RUN-FAILED)を読む。
    何も公開していない起動で最終成功時刻が進んだり、再実行待ちの途中で失敗が鳴ったりしないようにする。"""

    def setUp(self):
        super().setUp()
        self.log = self.path("digest", "research-digest", "runner-publish.log")

    def lines(self):
        with open(self.log, encoding="utf-8") as f:
            return f.read().splitlines()

    def finish(self, result, status="retry_pending", became_failed=False, attempt=1):
        summary_log.finished(self.log, result, "2026-11-07", None, attempt, status, "/x/1.log", became_failed=became_failed)
        return self.lines()[-1]

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-6
    def test_書いた行はすべて行頭の時刻と種別と印で読める(self):
        """否定確認: 行頭の時刻に日本時間のオフセットを付けないと落ちる"""
        summary_log.started(self.log, dict(app="research-digest", kind="publish", date="2026-11-07", edition=None, attempt=1))
        self.finish("succeeded", status="succeeded")
        self.finish("temporary_failure", status="failed", became_failed=True, attempt=4)
        summary_log.warning(self.log, "失敗通知の失敗", "RuntimeError: boom", failed=True)
        lines = self.lines()
        self.assertEqual(len(lines), 4)
        for line in lines:
            self.assertRegex(line, LINE)
            stamp = dt.datetime.fromisoformat(line.split(" ", 1)[0])
            self.assertEqual(stamp.utcoffset(), dt.timedelta(hours=9))
        self.assertEqual(lines[0].split(" ", 1)[1],
                         "INFO 実行開始: app=research-digest kind=publish date=2026-11-07 edition=- attempt=1")
        self.assertEqual([l for l in lines if "RUN-SUCCEEDED" in l], [lines[1]])
        self.assertEqual([l for l in lines if "RUN-FAILED" in l], lines[2:])
        self.assertEqual(stat.S_IMODE(os.stat(self.log).st_mode), 0o600)
        self.assertTrue(summary_log.has_started(self.log))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-6
    def test_バッチが成功した起動の実行終了の行に成功の印が付く(self):
        line = self.finish("succeeded", status="succeeded")
        self.assertEqual(line.split(" ", 1)[1],
                         "INFO 実行終了: result=succeeded date=2026-11-07 edition=- attempt=1 status=succeeded RUN-SUCCEEDED log=/x/1.log")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-6
    def test_既に成功済みとロック中の起動には成功の印が付かない(self):
        """否定確認: 成功の印の条件を「当日の状態が成功」に変えると落ちる"""
        self.assertNotIn("RUN-SUCCEEDED", self.finish("already_succeeded", status="succeeded", attempt=None))
        summary_log.finished(self.log, "locked", None, None, None, None, None)
        self.assertEqual(self.lines()[-1].split(" ", 1)[1],
                         "INFO 実行終了: result=locked date=- edition=- attempt=- status=- log=-")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-6
    def test_その起動で失敗確定になった実行終了の行に失敗の印が付く(self):
        line = self.finish("temporary_failure", status="failed", became_failed=True, attempt=4)
        self.assertEqual(line.split(" ", 1)[1],
                         "INFO 実行終了: result=temporary_failure date=2026-11-07 edition=- attempt=4 status=failed RUN-FAILED log=/x/1.log")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-6
    def test_再実行待ちと既に失敗確定の日と手動の失敗と渡し直しには失敗の印が付かない(self):
        """否定確認: 失敗の印の条件を「当日の状態が失敗確定」に変える、または渡し直しの除外を外すと落ちる"""
        self.assertNotIn("RUN-FAILED", self.finish("temporary_failure", status="retry_pending"))
        self.assertNotIn("RUN-FAILED", self.finish("failed_final", status="failed", attempt=None))
        self.assertNotIn("RUN-FAILED", self.finish("temporary_failure", status="failed", attempt="manual"))
        self.assertNotIn("RUN-FAILED", self.finish("renotified", status="failed", became_failed=True))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-6、apps/digest-platform/specs/batch-runner/requirements.md#再実行-9
    def test_記録の無い回を締めた行に失敗の印が付く(self):
        self.assertIn("RUN-FAILED", self.finish("missed", status="failed", became_failed=True, attempt=0))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-6、apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-3
    def test_壊れた記録を書き直した行に失敗の印が付く(self):
        self.assertIn("RUN-FAILED", self.finish("corrupt_state", status="failed", became_failed=True, attempt=0))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-7
    def test_未登録で終わった起動の行に失敗の印が付く(self):
        """否定確認: 実行係自身の失敗に印を付ける処理を消すと落ちる"""
        summary_log.finished(self.log, "unregistered", None, None, None, None, None)
        self.assertIn("result=unregistered", self.lines()[-1])
        self.assertIn("RUN-FAILED", self.lines()[-1])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-7
    def test_実行係のエラーで終わった起動の行に失敗の印が付く(self):
        summary_log.finished(self.log, "runner_error", "2026-11-07", None, 1, "pending", None)
        self.assertIn("RUN-FAILED", self.lines()[-1])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#失敗の引き渡し-2
    def test_通知に失敗した警告の行に失敗の印が付き通知と無関係の警告には付かない(self):
        summary_log.warning(self.log, "失敗通知の書き出し失敗", "app=research-digest date=2026-11-07", failed=True)
        summary_log.warning(self.log, "古い記録を消せません", "/x/old.log")
        lines = self.lines()
        self.assertTrue(lines[0].endswith("WARNING 失敗通知の書き出し失敗: app=research-digest date=2026-11-07 RUN-FAILED"))
        self.assertTrue(lines[1].endswith("WARNING 古い記録を消せません: /x/old.log"))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-9
    def test_一度もバッチを起動していなければ実行開始の行が無いと分かる(self):
        self.assertFalse(summary_log.has_started(self.log))
        summary_log.finished(self.log, "locked", None, None, None, None, None)
        self.assertFalse(summary_log.has_started(self.log))
        summary_log.started(self.log, dict(app="a", kind="publish", date="2026-11-07", edition="sci", attempt="manual"))
        self.assertTrue(summary_log.has_started(self.log))
        self.assertTrue(self.lines()[-1].endswith("edition=sci attempt=manual"))


if __name__ == "__main__":
    unittest.main()
