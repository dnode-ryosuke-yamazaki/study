"""OneDrive の同期フォルダへの書き込み。

launchd から同期フォルダへ書くと Resource deadlock avoided で失敗する例があるため、既存アプリの対処
(起動時の実体化の許可と、中身を読んで書く複製を .part に書いてから名前を付け替える)に従っていることを確かめる。
実際の OneDrive には書かず、一時フォルダで確かめる。
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from routine_work_finder.report import onedrive_write


class FakeLibc:
    def __init__(self, result=0):
        self.result = result
        self.calls = []

    def setiopolicy_np(self, *args):
        self.calls.append(args)
        return self.result


class MaterializationTests(unittest.TestCase):
    """起動時に、自分のプロセスに同期フォルダの未実体化のファイルの実体化を許可する"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-3
    def test_実体化の許可を自分のプロセスに設定できたら真を返す(self):
        """否定確認: 範囲をスレッドにすると落ちる"""
        libc = FakeLibc(0)
        self.assertTrue(onedrive_write.allow_dataless_materialization(loader=lambda: libc))
        # 未実体化のファイルの実体化(3)・プロセス全体(0)・許可する(2)
        self.assertEqual(libc.calls, [(3, 0, 2)])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-3
    def test_許可を設定できなくても例外にせず偽を返す(self):
        """否定確認: 設定の戻り値を見ずに真を返すと落ちる"""
        self.assertFalse(onedrive_write.allow_dataless_materialization(loader=lambda: FakeLibc(-1)))

        def broken_loader():
            raise OSError("libc を読めない")
        self.assertFalse(onedrive_write.allow_dataless_materialization(loader=broken_loader))


class CopyTests(unittest.TestCase):
    """控えのファイルを、中身を読んで書く複製で .part に書いてから名前を付け替える"""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        self.source = self.folder / "local.html"
        self.source.write_bytes("<p>週次レポート</p>\n".encode("utf-8") * 1000)
        self.dest_dir = self.folder / "onedrive"
        self.dest_dir.mkdir()
        self.dest = self.dest_dir / "2026-W41.html"

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-3
    def test_同じ中身が週の名前で置かれ途中のファイルは残らない(self):
        """否定確認: 名前を付け替えずに .part のまま残すと落ちる"""
        onedrive_write.copy_file(self.source, self.dest)
        self.assertEqual(self.dest.read_bytes(), self.source.read_bytes())
        self.assertEqual(sorted(path.name for path in self.dest_dir.iterdir()), ["2026-W41.html"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-3
    def test_同じ名前のファイルがあれば上書きする(self):
        """否定確認: 既にある名前を避けて別の名前で置くと落ちる"""
        self.dest.write_text("古いレポート", encoding="utf-8")
        onedrive_write.copy_file(self.source, self.dest)
        self.assertEqual(self.dest.read_bytes(), self.source.read_bytes())

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-3
    def test_OSの高速複製を使わずに中身を読んで書く(self):
        """否定確認: shutil.copyfile で複製すると落ちる"""
        def forbidden(*args, **kwargs):
            raise AssertionError("高速複製を使った")
        with mock.patch("shutil.copyfile", forbidden), mock.patch("shutil.copy2", forbidden), \
                mock.patch("shutil.copy", forbidden), mock.patch("shutil._fastcopy_fcopyfile", forbidden, create=True):
            onedrive_write.copy_file(self.source, self.dest)
        self.assertEqual(self.dest.read_bytes(), self.source.read_bytes())

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-3
    def test_名前を付け替えられないときは途中のファイルを消して例外を返す(self):
        """否定確認: 失敗したときに途中のファイルを消さないと落ちる"""
        self.dest.mkdir()
        with self.assertRaises(OSError):
            onedrive_write.copy_file(self.source, self.dest)
        self.assertEqual(sorted(path.name for path in self.dest_dir.iterdir()), ["2026-W41.html"])
        self.assertTrue(self.dest.is_dir())


if __name__ == "__main__":
    unittest.main()
