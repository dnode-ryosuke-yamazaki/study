"""入口から起動コマンドの直前までの所要時間を測る性能テスト。

launchd が実行係を起動してからバッチを起動するまでを10秒以内に収める要件を、数値で確かめる。
一時フォルダに登録表・実行状態ファイル(未着手1件と、前日の「再実行待ち」1件。締めで偽の判定関数が1回呼ばれる)・
90日分相当の古いファイル(300件)を用意し、偽のバッチ(即終了)で runner.main を呼び、
要約ログに「実行開始」の行が書かれるまでを計測して5秒未満を合格とする。
"""

import datetime as dt
import os
import shutil
import sys
import time
import unittest

from digest_runner import state, summary_log

import runner
from tests.perf import support

JST = dt.timezone(dt.timedelta(hours=9))
APP = "research-digest"

STARTUP_LIMIT_SECONDS = 5.0


class StartupPerformanceTest(unittest.TestCase):
    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#非機能要件-1
    def test_登録表と実行状態と古いファイル300件がある状態でも実行開始の行が書かれるまで5秒未満で済む(self):
        """否定確認: STARTUP_LIMIT_SECONDS を 0.001 にすると落ちる"""
        root = support.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        data_dir = os.path.join(root, "data", APP)
        home = os.path.join(root, "home")

        batch = support.make_app_root(root)
        registry_path = support.make_registry(root, batch, app=APP, weekdays=(6,))
        # 配信曜日(土曜)の朝06:30以降の時刻。2024-01-13 は土曜日。
        now = dt.datetime(2024, 1, 13, 10, 0, tzinfo=JST)
        support.make_filler_files(data_dir, now, count=300)
        current_date = "2024-01-13"
        previous_date = "2024-01-06"

        # 今回の配信日: 未着手(pending)
        pending = state.empty(APP, "publish", current_date, None, 4)
        state.save(state.path_for(data_dir, "publish", current_date, None), pending)

        # 前日以前の配信日: 再実行待ちのまま残っている(起動前の締めで失敗確定になる)
        retry_pending = state.empty(APP, "publish", previous_date, None, 4)
        state.set_status(retry_pending, "retry_pending")
        state.save(state.path_for(data_dir, "publish", previous_date, None), retry_pending)

        notified_calls = []
        module_name = support.install_fake_judge_module(sys.modules, notified_calls)
        self.addCleanup(sys.modules.pop, module_name, None)

        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": home,
            "DIGEST_DATA_DIR": data_dir,
            "DIGEST_NODE_BIN": "/bin/sh",
            "DIGEST_CLAUDE_BIN": "/bin/sh",
            "DIGEST_PYTHON_BIN": sys.executable,
            "DIGEST_HANDOFF_MODULE": module_name,
        }

        measured = {}
        original_started = summary_log.started

        def timed_started(path, context, now=None):
            measured["started_at"] = time.monotonic()
            return original_started(path, context, now=now)

        summary_log.started = timed_started
        self.addCleanup(setattr, summary_log, "started", original_started)

        before = time.monotonic()
        result = runner.main(
            [APP, "publish"],
            env=env,
            clock=lambda: now,
            app_root=root,
            registry_path=registry_path,
            home=home,
        )

        self.assertIn("started_at", measured, "要約ログに「実行開始」の行が書かれていません")
        elapsed = measured["started_at"] - before

        self.assertEqual(result, 0)
        self.assertEqual(len(notified_calls), 1)
        batch_marker = os.path.join(root, "out", f"{current_date}.txt")
        self.assertTrue(os.path.exists(batch_marker), "偽のバッチが起動していません")
        self.assertLess(elapsed, STARTUP_LIMIT_SECONDS)
