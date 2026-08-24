"""状態ファイルの読み書きと二重起動の防止(タスク2)のテスト。"""

import json
import time
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import state


class 初回実行の判定(unittest.TestCase):
    """状態ファイルが無いこと(=初回)と、壊れていることを区別できることを検証する。

    区別を誤って初回扱いにすると、既処理分のVTT全件を再生成してTeamsへ再投稿して
    しまうため、破損は必ず中断側に倒す。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.状態ファイル = Path(self.一時ディレクトリ.name) / "state.json"
        self.addCleanup(self.一時ディレクトリ.cleanup)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#定期実行と未処理vttの検知
    def test_状態ファイルが無い場合は初回としてNoneが返ること(self):
        self.assertIsNone(state.読み込む(self.状態ファイル))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#エラーハンドリング
    def test_状態ファイルが壊れている場合は初期化せず専用の例外になること(self):
        self.状態ファイル.write_text("{壊れている", encoding="utf-8")
        with self.assertRaises(state.状態が壊れている):
            state.読み込む(self.状態ファイル)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#エラーハンドリング
    def test_JSONだが形式が想定と違う場合も破損として扱われること(self):
        self.状態ファイル.write_text('["リスト"]', encoding="utf-8")
        with self.assertRaises(state.状態が壊れている):
            state.読み込む(self.状態ファイル)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#エラーハンドリング
    def test_一時的な読み取り失敗は破損と区別されること(self):
        """OneDrive同期の実体化待ちなどの一時的失敗を破損と混同すると、
        手動復旧(state.jsonの修復・削除)へ誘導してしまう。次回に委ねる側に倒す。
        """
        壊れていないがアクセスできないファイル = Path(self.一時ディレクトリ.name) / "dir-as-file"
        壊れていないがアクセスできないファイル.mkdir()
        with self.assertRaises(state.状態を読めなかった):
            state.読み込む(壊れていないがアクセスできないファイル)


class 処理状態の記録(unittest.TestCase):
    """VTTごとの状態(処理済み・再試行待ち・対象外)を記録し読み直せることを検証する。"""

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.状態ファイル = Path(self.一時ディレクトリ.name) / "state.json"
        self.addCleanup(self.一時ディレクトリ.cleanup)
        self.日時 = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)

    def 保存して読み直す(self, 対象: state.状態) -> state.状態:
        state.保存する(対象, self.状態ファイル)
        読んだ状態 = state.読み込む(self.状態ファイル)
        assert 読んだ状態 is not None
        return 読んだ状態

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#新規トランスクリプトの検知-2
    def test_処理済みにしたVTTが保存後も処理済みと判定されること(self):
        対象 = state.状態()
        対象.処理済みにする("会議A.vtt", self.日時)
        読んだ状態 = self.保存して読み直す(対象)
        self.assertTrue(読んだ状態.処理済みか("会議A.vtt"))
        self.assertFalse(読んだ状態.処理済みか("会議B.vtt"))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の生成-4
    def test_生成失敗の記録で再試行回数が1ずつ増えること(self):
        対象 = state.状態()
        self.assertEqual(対象.生成失敗を記録する("会議A.vtt"), 1)
        self.assertEqual(対象.生成失敗を記録する("会議A.vtt"), 2)
        読んだ状態 = self.保存して読み直す(対象)
        self.assertEqual(読んだ状態.再試行回数("会議A.vtt"), 2)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の生成-5
    def test_対象外にしたVTTが保存後も対象外と判定されること(self):
        対象 = state.状態()
        対象.対象外にする("会議A.vtt", self.日時)
        読んだ状態 = self.保存して読み直す(対象)
        self.assertTrue(読んだ状態.対象外か("会議A.vtt"))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#エラーハンドリング
    def test_保存が一時ファイル経由で行われ壊れた中間状態を残さないこと(self):
        """アトミック書き込みの検証。保存後に一時ファイルが残っていないこと、
        保存結果が正しいJSONであることを確認する。
        """
        対象 = state.状態()
        対象.処理済みにする("会議A.vtt", self.日時)
        state.保存する(対象, self.状態ファイル)
        残ファイル = list(Path(self.一時ディレクトリ.name).iterdir())
        self.assertEqual([f.name for f in 残ファイル], ["state.json"])
        json.loads(self.状態ファイル.read_text(encoding="utf-8"))


class 二重起動の防止(unittest.TestCase):
    """前回の実行が動作中の間は次の実行が何もせず終えられることを検証する。

    1回の実行(生成タイムアウト15分×直列処理)が起動間隔10分を超えるのは正常系で
    あり、ロックが無いと同じVTTの二重生成と状態ファイルの競合が起こる。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.ロックファイル = Path(self.一時ディレクトリ.name) / "minutes.lock"
        self.addCleanup(self.一時ディレクトリ.cleanup)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#定期実行と未処理vttの検知
    def test_ロック保持中に取得しようとすると先行実行が動作中になること(self):
        with state.ロック(self.ロックファイル):
            with self.assertRaises(state.先行実行が動作中):
                with state.ロック(self.ロックファイル):
                    pass

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#定期実行と未処理vttの検知
    def test_解放したロックを再取得できること(self):
        with state.ロック(self.ロックファイル):
            pass
        with state.ロック(self.ロックファイル):
            pass

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#定期実行と未処理vttの検知
    def test_処理が進むたびに時刻を更新すれば長い実行でも奪われないこと(self):
        """未処理が溜まって1回の実行が30分を超えると、次の定期実行が
        「異常終了の残骸」と誤判定してロックを奪い、同じ会議の議事録を二重に
        作ってTeamsへ二重投稿してしまう。時刻の更新でこれを防ぐ。
        """
        import os

        with state.ロック(self.ロックファイル, 無効とみなす秒=1800) as 取得したロック:
            古い時刻 = time.time() - 3600
            os.utime(self.ロックファイル, (古い時刻, 古い時刻))
            取得したロック.時刻を更新する()
            with self.assertRaises(state.先行実行が動作中):
                with state.ロック(self.ロックファイル, 無効とみなす秒=1800):
                    pass

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#定期実行と未処理vttの検知
    def test_ロックが消えていても時刻の更新で失敗しないこと(self):
        """更新は付随的な処理なので、ここで例外を投げてバッチ全体を止めない。"""
        with state.ロック(self.ロックファイル) as 取得したロック:
            self.ロックファイル.unlink()
            with self.assertLogs(level="WARNING"):
                取得したロック.時刻を更新する()

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#定期実行と未処理vttの検知
    def test_古いロックは回収して取得し直せること(self):
        """前回の実行が異常終了してロックが残ると、回収がなければ以降ずっと
        起動できなくなるため、経過時間で無効とみなす。
        """
        self.ロックファイル.write_text("12345", encoding="utf-8")
        古い時刻 = time.time() - 3600
        import os

        os.utime(self.ロックファイル, (古い時刻, 古い時刻))
        with state.ロック(self.ロックファイル, 無効とみなす秒=1800):
            pass


if __name__ == "__main__":
    unittest.main()
