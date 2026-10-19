"""週次レポート係を起動する launchd の設定ファイルの構造検証。

金曜17時になったときと、作り直しの依頼のフォルダに依頼が置かれたときに週次レポート係が起動する。
Python の更新で番号付きのフォルダが消えてもバッチが無言で止まらないよう、Python は Versions/Current を指す。
"""

import plistlib
import unittest
from pathlib import Path

APPLICATION_DIR = Path(__file__).resolve().parent.parent
PLIST_PATH = APPLICATION_DIR / "launchd" / "com.example.routine-work-finder-report.plist"
PYTHON_PATH = "/Library/Frameworks/Python.framework/Versions/Current/bin/python3"
REQUESTS_FOLDER = "__HOME__/Library/Application Support/routine-work-finder/requests"
FRIDAY = 5


class ReportLaunchdPlistTests(unittest.TestCase):
    """週次レポート係の launchd の設定ファイル"""

    def load(self):
        with PLIST_PATH.open("rb") as file:
            return plistlib.load(file)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートを出す時刻-1
    def test_毎週金曜17時0分に起動する指定がある(self):
        """否定確認: 起動の曜日を木曜(4)に変えると落ちる"""
        plist = self.load()
        self.assertEqual(plist["Label"], "com.example.routine-work-finder-report")
        self.assertEqual(plist["StartCalendarInterval"], {"Weekday": FRIDAY, "Hour": 17, "Minute": 0})

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートを出す時刻-1
    def test_作り直しの依頼のフォルダの変化でも起動し読み込んだだけでは起動しない(self):
        """否定確認: 監視するフォルダを requests から reports に変えると落ちる。RunAtLoad を true にしても落ちる"""
        plist = self.load()
        self.assertEqual(plist["WatchPaths"], [REQUESTS_FOLDER])
        self.assertIs(plist["RunAtLoad"], False)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートを出す時刻-1
    def test_Pythonは番号を直書きせずCurrentを指して週次レポート係の入口を動かす(self):
        """否定確認: Python のパスを Versions/3.15 に変えると落ちる"""
        plist = self.load()
        self.assertEqual(plist["ProgramArguments"], [PYTHON_PATH, "-m", "routine_work_finder.report.run_report"])
        self.assertEqual(plist["WorkingDirectory"], "__HOME__/repo/study/apps/routine-work-finder/application")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートを出す時刻-1
    def test_ログはホームのログのフォルダの週次レポート係のファイルに書く(self):
        plist = self.load()
        log = "__HOME__/Library/Logs/routine-work-finder-report.log"
        self.assertEqual(plist["StandardOutPath"], log)
        self.assertEqual(plist["StandardErrorPath"], log)


if __name__ == "__main__":
    unittest.main()
