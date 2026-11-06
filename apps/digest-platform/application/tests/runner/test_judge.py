import datetime as dt
import os
import time
import unittest

from tests.runner.support import TempDirTestCase

from digest_runner import judge

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class 終了コードと成功マーカーと生成物による成否の判定(TempDirTestCase):
    """Claude のヘッドレス実行は失敗しても終了コード0を返すため、終了コード・最終行の成功マーカー・
    起動後に書かれた生成物の3点がそろったときだけ成功とし、欠けたら失敗の種類を決める。"""

    def setUp(self):
        super().setUp()
        self.started = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=30)
        self.article = self.write_text("articles/2026-11-07.json", "{}")
        self.page = self.write_text("out/2026-11-07/index.html", "<html></html>")

    def evaluate(self, exit_code=0, lines=("working", "DIGEST-BATCH-OK"), artifacts=None, timed_out=False):
        return judge.evaluate(exit_code, list(lines), artifacts or [self.article, self.page], self.started, timed_out)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-1
    def test_終了コード0と成功マーカーと起動後の生成物がそろえば成功になる(self):
        got = self.evaluate()
        self.assertEqual(got, {"result": "succeeded", "missing": [], "warnings": []})

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-1、apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-4
    def test_終了コードが1なら一時的な失敗になる(self):
        """否定確認: 終了コードの検査を消すと落ちる"""
        got = self.evaluate(exit_code=1)
        self.assertEqual(got["result"], "temporary_failure")
        self.assertEqual(got["missing"], ["exit_code"])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-1
    def test_最終行が成功マーカーでなければ一時的な失敗になる(self):
        """否定確認: 最終行の検査を「どこかの行にあれば」に緩めると落ちる"""
        got = self.evaluate(lines=["DIGEST-BATCH-OK", "error after marker"])
        self.assertEqual(got, {"result": "temporary_failure", "missing": ["marker"], "warnings": []})

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-1
    def test_生成物が無ければ一時的な失敗になり欠けたパスが記録される(self):
        os.unlink(self.page)
        got = self.evaluate()
        self.assertEqual(got["result"], "temporary_failure")
        self.assertEqual(got["missing"], ["artifact:" + self.page])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-1
    def test_起動より前に書かれた古い生成物だけでは成功にならない(self):
        """否定確認: 更新時刻と起動時刻の比較を外すと落ちる"""
        old = time.time() - 3600
        os.utime(self.article, (old, old))
        got = self.evaluate()
        self.assertEqual(got["result"], "temporary_failure")
        self.assertEqual(got["missing"], ["artifact:" + self.article])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-4
    def test_終了コード2は再試行しても直らない失敗になり打ち切りは打ち切りになる(self):
        """否定確認: 終了コード2の分岐を消すと落ちる"""
        self.assertEqual(self.evaluate(exit_code=2, lines=["quota"])["result"], "permanent_failure")
        timed = self.evaluate(exit_code=-15, lines=["working"], timed_out=True)
        self.assertEqual(timed["result"], "timeout")
        self.assertEqual(timed["missing"], ["exit_code", "marker"])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-8
    def test_成功マーカーの前に警告の行があれば成功のまま警告の種類が返る(self):
        """否定確認: 警告の行の読み取りを消すと落ちる"""
        got = self.evaluate(lines=["DIGEST-BATCH-WARN broadcast_failed", "DIGEST-BATCH-WARN other", "DIGEST-BATCH-OK"])
        self.assertEqual(got, {"result": "succeeded", "missing": [], "warnings": ["broadcast_failed", "other"]})
        failed = self.evaluate(exit_code=1, lines=["DIGEST-BATCH-WARN broadcast_failed", "boom"])
        self.assertEqual(failed["warnings"], [])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-2
    def test_終了コード0でマーカーの無いバッチの出力は失敗になる(self):
        """fixture はタスク16で実出力に置き換えるまでの想像 fixture"""
        with open(os.path.join(FIXTURES, "batch-no-marker.log"), encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertGreater(len(lines), 0)
        got = self.evaluate(exit_code=0, lines=lines)
        self.assertEqual(got["result"], "temporary_failure")
        self.assertIn("marker", got["missing"])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-2
    def test_出力が空のまま終了コード0で終わったバッチは失敗になる(self):
        got = self.evaluate(exit_code=0, lines=[])
        self.assertEqual(got["result"], "temporary_failure")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-1
    def test_生成物のパスは配信日と編と年月で埋まる(self):
        patterns = ["../a/articles/{date}{edition}.json", "out/a/{date}{edition}/index.html", "../a/reviews/{yearMonth}.md"]
        self.assertEqual(
            judge.expand_artifacts(patterns, "2026-11-07", "sci"),
            ["../a/articles/2026-11-07-sci.json", "out/a/2026-11-07-sci/index.html", "../a/reviews/2026-11.md"],
        )
        self.assertEqual(judge.expand_artifacts(patterns[:1], "2026-11-07", None), ["../a/articles/2026-11-07.json"])


if __name__ == "__main__":
    unittest.main()
