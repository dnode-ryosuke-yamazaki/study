"""入口から起動コマンドの直前までの所要時間を測る性能テスト。

launchd が実行係を起動してからバッチを起動するまでを10秒以内に収める要件を、数値で確かめる。
一時フォルダに登録表・実行状態ファイル(未着手1件と、前日の「再実行待ち」1件。締めで偽の判定関数が1回呼ばれる)・
90日分相当の古いファイル(300件)を用意し、偽のバッチ(即終了)で runner.main を呼び、
要約ログに「実行開始」の行が書かれるまでを計測して5秒未満を合格とする。
"""

import unittest

STARTUP_LIMIT_SECONDS = 5.0


class StartupPerformanceTest(unittest.TestCase):
    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#非機能要件-1
    def test_登録表と実行状態と古いファイル300件がある状態でも実行開始の行が書かれるまで5秒未満で済む(self):
        """否定確認: STARTUP_LIMIT_SECONDS を 0.001 にすると落ちる"""
        self.fail(
            "未実装(タスク15、担当: copilot): 一時フォルダの土台を用意し、偽のバッチで runner.main を呼んで"
            "「実行開始」が要約ログに書かれるまでの秒数を測り、STARTUP_LIMIT_SECONDS 未満を確かめる"
        )
