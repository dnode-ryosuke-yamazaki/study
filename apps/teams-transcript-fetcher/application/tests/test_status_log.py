"""処理結果の記録(T18)のテスト。"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import status_log


def 行を作る(**上書き) -> status_log.記録する行:
    引数 = {
        "ラベル": status_log.ラベル_期限切れ,
        "会議名": "定例会議",
        "時刻の表示": "2026-08-19 10:30",
        "詳細": "有効なダウンロードURLがない",
    }
    引数.update(上書き)
    return status_log.記録する行(**引数)


class 記録ファイルへの追記(unittest.TestCase):
    """失敗した対象が記録ファイルに残ることを検証する。

    Teamsへの通知はDLPで使えないため、この記録が唯一の「気づける手段」になる。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.記録ファイル = Path(self.一時ディレクトリ.name) / "vtt" / "_status.md"
        self.addCleanup(self.一時ディレクトリ.cleanup)
        self.実行日時 = datetime(2026, 8, 19, 10, 35, tzinfo=timezone.utc)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#処理結果の記録-1
    def test_会議名と時刻と失敗の理由が追記されること(self):
        status_log.追記する(self.記録ファイル, [行を作る()], self.実行日時)
        書かれた内容 = self.記録ファイル.read_text(encoding="utf-8")
        self.assertIn("定例会議", 書かれた内容)
        self.assertIn("2026-08-19 10:30", 書かれた内容)
        self.assertIn("有効なダウンロードURLがない", 書かれた内容)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#処理結果の記録-5
    def test_原因を区別するラベルが含まれること(self):
        for ラベル in (
            status_log.ラベル_トランスクリプト0件,
            status_log.ラベル_件数不足,
            status_log.ラベル_取得失敗,
        ):
            with self.subTest(ラベル=ラベル):
                記録ファイル = self.記録ファイル.with_name(f"{ラベル}.md")
                status_log.追記する(記録ファイル, [行を作る(ラベル=ラベル)], self.実行日時)
                self.assertIn(f"[{ラベル}]", 記録ファイル.read_text(encoding="utf-8"))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#処理結果の記録
    def test_既存の内容が書き換えられず末尾に追記されること(self):
        status_log.追記する(self.記録ファイル, [行を作る(会議名="1回目")], self.実行日時)
        status_log.追記する(self.記録ファイル, [行を作る(会議名="2回目")], self.実行日時)
        書かれた内容 = self.記録ファイル.read_text(encoding="utf-8")
        self.assertLess(書かれた内容.index("1回目"), 書かれた内容.index("2回目"))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#処理結果の記録
    def test_追記するものが無い場合はファイルに触れないこと(self):
        """不要なOneDrive同期を発生させないため。"""
        追記した = status_log.追記する(self.記録ファイル, [], self.実行日時)
        self.assertFalse(追記した)
        self.assertFalse(self.記録ファイル.exists())

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#処理結果の記録-2
    def test_置き場が無ければ作られること(self):
        status_log.追記する(self.記録ファイル, [行を作る()], self.実行日時)
        self.assertTrue(self.記録ファイル.exists())

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#処理結果の記録
    def test_初回だけ見出しが書かれること(self):
        status_log.追記する(self.記録ファイル, [行を作る()], self.実行日時)
        status_log.追記する(self.記録ファイル, [行を作る()], self.実行日時)
        self.assertEqual(self.記録ファイル.read_text(encoding="utf-8").count("# "), 1)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#セキュリティ
    def test_記録内容にurlが含まれないこと(self):
        """記録ファイルはOneDrive上に置かれ、URLは実質ベアラトークンのため。

        `HTTP 403` のようなステータス表記は問題ないので、URLの目印である
        スキーム区切り(`://`)が現れないことで判定する。
        """
        status_log.追記する(
            self.記録ファイル,
            [行を作る(詳細="HTTP 403(期限切れと判断)")],
            self.実行日時,
        )
        self.assertNotIn("://", self.記録ファイル.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
