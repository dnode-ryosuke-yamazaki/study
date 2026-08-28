"""未実体化ファイルの実体化許可と判別(T29)のテスト。

実際のI/Oポリシー変更やdatalessファイルはテストで再現できないため、
ctypes・os.statの境界を差し替えて検証する。
"""

import os
import unittest
from pathlib import Path
from unittest import mock

import materialize


class 実体化の許可(unittest.TestCase):
    """起動時のI/Oポリシー設定が、失敗してもバッチを止めないことを検証する。"""

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#実行環境-4
    def test_許可の設定が成功すること(self):
        libc = mock.Mock()
        libc.setiopolicy_np.return_value = 0
        with mock.patch.object(materialize.ctypes, "CDLL", return_value=libc):
            self.assertTrue(materialize.実体化を許可する())
        libc.setiopolicy_np.assert_called_once_with(
            materialize.IOPOL_TYPE_VFS_MATERIALIZE_DATALESS_FILES,
            materialize.IOPOL_SCOPE_PROCESS,
            materialize.IOPOL_MATERIALIZE_DATALESS_FILES_ON,
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#エラーハンドリング
    def test_設定が失敗しても例外にならないこと(self):
        """設定が効かなくても読み取りは持ち越しで守られるため、中断してはならない。"""
        libc = mock.Mock()
        libc.setiopolicy_np.return_value = -1
        with mock.patch.object(materialize.ctypes, "CDLL", return_value=libc):
            with self.assertLogs(level="WARNING"):
                self.assertFalse(materialize.実体化を許可する())

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#エラーハンドリング
    def test_ライブラリを読み込めなくても例外にならないこと(self):
        with mock.patch.object(
            materialize.ctypes, "CDLL", side_effect=OSError("libc not found")
        ):
            with self.assertLogs(level="WARNING"):
                self.assertFalse(materialize.実体化を許可する())


class 未実体化の判別(unittest.TestCase):
    """SF_DATALESSフラグの有無を正しく返すことを検証する。"""

    def _statの結果(self, st_flags: int) -> mock.Mock:
        結果 = mock.Mock()
        結果.st_flags = st_flags
        return 結果

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#エラーハンドリング
    def test_datalessフラグが立っているファイルを未実体化と判別すること(self):
        with mock.patch.object(
            os, "stat", return_value=self._statの結果(materialize.SF_DATALESS)
        ):
            self.assertTrue(materialize.未実体化か(Path("dummy.json")))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#エラーハンドリング
    def test_フラグが無いファイルは未実体化ではないこと(self):
        with mock.patch.object(os, "stat", return_value=self._statの結果(0)):
            self.assertFalse(materialize.未実体化か(Path("dummy.json")))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#エラーハンドリング
    def test_statが失敗しても例外にならないこと(self):
        """判別はログを充実させるための補助であり、失敗が処理を止めてはならない。"""
        with mock.patch.object(os, "stat", side_effect=OSError("gone")):
            self.assertFalse(materialize.未実体化か(Path("dummy.json")))


if __name__ == "__main__":
    unittest.main()
