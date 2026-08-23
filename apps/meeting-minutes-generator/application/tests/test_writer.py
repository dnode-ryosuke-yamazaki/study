"""議事録・投稿用ファイルの書き出し(タスク5)のテスト。"""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import writer


class 議事録の保存(unittest.TestCase):
    """議事録Markdownが元のVTTと対応の分かる名前で保存されることを検証する。"""

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.議事録フォルダ = Path(self.一時ディレクトリ.name)
        self.addCleanup(self.一時ディレクトリ.cleanup)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#議事録の保存
    def test_VTTファイル名の拡張子をmdに変えた名前で保存されること(self):
        保存先 = writer.議事録を保存する("# 議事録", "2026-08-24 定例.vtt", self.議事録フォルダ)
        self.assertEqual(保存先.name, "2026-08-24 定例.md")
        self.assertEqual(保存先.read_text(encoding="utf-8"), "# 議事録")

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#議事録の保存
    def test_同名ファイルがある場合は上書きせず連番付きで保存されること(self):
        """再生成や同名会議の再録画で、既存の議事録を黙って失わないための挙動。"""
        一つ目 = writer.議事録を保存する("1回目", "定例.vtt", self.議事録フォルダ)
        二つ目 = writer.議事録を保存する("2回目", "定例.vtt", self.議事録フォルダ)
        self.assertEqual(一つ目.read_text(encoding="utf-8"), "1回目")
        self.assertEqual(二つ目.name, "定例-2.md")
        self.assertEqual(二つ目.read_text(encoding="utf-8"), "2回目")

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#議事録の保存
    def test_保存先フォルダが無ければ作られること(self):
        保存先フォルダ = self.議事録フォルダ / "minutes"
        writer.議事録を保存する("# 議事録", "定例.vtt", 保存先フォルダ)
        self.assertTrue(保存先フォルダ.is_dir())


class 投稿用ファイルの書き出し(unittest.TestCase):
    """Teams投稿用ファイルが毎回一意な名前で書き出されることを検証する。

    OneDriveの「ファイル作成時」トリガーは新規作成のみ検知し上書きでは発火しない
    ため、名前の一意性が投稿の成立条件になる。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.投稿フォルダ = Path(self.一時ディレクトリ.name)
        self.addCleanup(self.一時ディレクトリ.cleanup)
        self.日時 = datetime(2026, 8, 24, 10, 30, 45)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#onedriveフォルダの使い方-2
    def test_日時から一意なファイル名が組み立てられること(self):
        書き出し先 = writer.投稿用に書き出す("<p>要約</p>", self.投稿フォルダ, self.日時)
        self.assertEqual(書き出し先.name, "minutes-20260824-103045.txt")
        self.assertEqual(書き出し先.read_text(encoding="utf-8"), "<p>要約</p>")

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#onedriveフォルダの使い方-2
    def test_同じ秒に書き出しても名前が衝突せず両方残ること(self):
        一つ目 = writer.投稿用に書き出す("1件目", self.投稿フォルダ, self.日時)
        二つ目 = writer.投稿用に書き出す("2件目", self.投稿フォルダ, self.日時)
        self.assertNotEqual(一つ目.name, 二つ目.name)
        self.assertEqual(一つ目.read_text(encoding="utf-8"), "1件目")
        self.assertEqual(二つ目.read_text(encoding="utf-8"), "2件目")


if __name__ == "__main__":
    unittest.main()
