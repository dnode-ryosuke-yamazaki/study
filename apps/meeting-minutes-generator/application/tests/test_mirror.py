"""議事録のローカル控え(タスク16・17)のテスト。

同期フォルダは許可の無いプロセスから読めないため、下流のツールは控えを読む。
仕様: requirements.md#議事録のローカル控え / design.md#控えのバックフィル
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
import writer


class 控えフォルダの解決(unittest.TestCase):
    """控えが同期フォルダの外(状態フォルダの配下)に導かれることを検証する。"""

    def setUp(self):
        for 変数 in (config.状態フォルダ環境変数, config.控えフォルダ環境変数):
            os.environ.pop(変数, None)
            self.addCleanup(os.environ.pop, 変数, None)

    # 仕様: requirements.md#議事録のローカル控え [1]
    def test_状態フォルダの配下に導かれること(self):
        設定 = config.load(状態フォルダ=Path("/tmp/状態"))
        self.assertEqual(設定.控えフォルダ, Path("/tmp/状態/minutes"))

    # 仕様: requirements.md#議事録のローカル控え [1]
    def test_既定の控えが同期フォルダの外にあること(self):
        設定 = config.load()
        self.assertNotIn("CloudStorage", str(設定.控えフォルダ))
        self.assertEqual(
            設定.控えフォルダ,
            Path.home() / "Library/Application Support/meeting-minutes-generator/minutes",
        )

    def test_環境変数で差し替えられること(self):
        os.environ[config.控えフォルダ環境変数] = "/tmp/別の控え"
        self.assertEqual(config.load().控えフォルダ, Path("/tmp/別の控え"))


class 控えの書き出し(unittest.TestCase):
    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        根 = Path(self.一時ディレクトリ.name)
        self.議事録フォルダ = 根 / "minutes"
        self.控えフォルダ = 根 / "mirror"
        self.addCleanup(self.一時ディレクトリ.cleanup)

    # 仕様: requirements.md#議事録のローカル控え [2][5]
    def test_OneDrive側と同じ名前で同じ内容が控えに書かれること(self):
        結果 = writer.議事録を保存する(
            "## TODO\n\n- 手順書をレビューする(担当者候補: 佐藤)\n",
            "会議__20260824T1000__01.vtt",
            self.議事録フォルダ,
            控えフォルダ=self.控えフォルダ,
        )
        self.assertEqual(結果.保存先.name, "会議__20260824T1000__01.md")
        self.assertEqual(結果.控え.name, 結果.保存先.name)
        self.assertEqual(
            結果.控え.read_text(encoding="utf-8"), 結果.保存先.read_text(encoding="utf-8")
        )

    # 仕様: requirements.md#議事録のローカル控え [2]
    def test_OneDrive側で連番が付いた場合は控えも同じ連番になること(self):
        writer.議事録を保存する("1回目", "会議__01.vtt", self.議事録フォルダ, 控えフォルダ=self.控えフォルダ)
        結果 = writer.議事録を保存する(
            "2回目", "会議__01.vtt", self.議事録フォルダ, 控えフォルダ=self.控えフォルダ
        )
        self.assertEqual(結果.保存先.name, "会議__01-2.md")
        self.assertEqual(結果.控え.name, "会議__01-2.md")
        self.assertEqual(結果.控え.read_text(encoding="utf-8"), "2回目")

    # 仕様: requirements.md#議事録のローカル控え [6]
    def test_控えに同じ名前がある場合は上書きされること(self):
        self.控えフォルダ.mkdir(parents=True)
        (self.控えフォルダ / "会議__01.md").write_text("古い控え", encoding="utf-8")
        結果 = writer.議事録を保存する(
            "新しい議事録", "会議__01.vtt", self.議事録フォルダ, 控えフォルダ=self.控えフォルダ
        )
        self.assertEqual(結果.控え.read_text(encoding="utf-8"), "新しい議事録")

    # 仕様: requirements.md#議事録のローカル控え [3]
    def test_控えの書き出しに失敗しても議事録は保存され例外にならないこと(self):
        元の書き込み = Path.write_text

        def 控えだけ失敗する(自身, *引数, **名前付き):
            if "mirror" in str(自身):
                raise OSError(1, "operation not permitted")
            return 元の書き込み(自身, *引数, **名前付き)

        with mock.patch.object(Path, "write_text", 控えだけ失敗する):
            結果 = writer.議事録を保存する(
                "本文", "会議__01.vtt", self.議事録フォルダ, 控えフォルダ=self.控えフォルダ
            )
        self.assertTrue(結果.保存先.exists())
        self.assertIsNone(結果.控え)
        self.assertIsNotNone(結果.控えの失敗)

    def test_控えフォルダを渡さない場合は控えを書かないこと(self):
        結果 = writer.議事録を保存する("本文", "会議__01.vtt", self.議事録フォルダ)
        self.assertTrue(結果.保存先.exists())
        self.assertIsNone(結果.控え)
        self.assertIsNone(結果.控えの失敗)


class 控えのバックフィル(unittest.TestCase):
    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        根 = Path(self.一時ディレクトリ.name)
        self.議事録フォルダ = 根 / "minutes"
        self.控えフォルダ = 根 / "mirror"
        self.議事録フォルダ.mkdir(parents=True)
        self.addCleanup(self.一時ディレクトリ.cleanup)

    # 仕様: requirements.md#議事録のローカル控え [4]
    def test_控えに無い議事録だけが写されること(self):
        (self.議事録フォルダ / "A__01.md").write_text("Aの本文", encoding="utf-8")
        (self.議事録フォルダ / "B__01.md").write_text("Bの本文", encoding="utf-8")
        self.控えフォルダ.mkdir(parents=True)
        (self.控えフォルダ / "B__01.md").write_text("既にある控え", encoding="utf-8")

        結果 = writer.控えをバックフィルする(self.議事録フォルダ, self.控えフォルダ)

        self.assertEqual(結果.写した件数, 1)
        self.assertEqual((self.控えフォルダ / "A__01.md").read_text(encoding="utf-8"), "Aの本文")
        # 既にある控えは触らない(通常の保存で書いた控えを上書きしないため)
        self.assertEqual(
            (self.控えフォルダ / "B__01.md").read_text(encoding="utf-8"), "既にある控え"
        )

    # 仕様: design.md#控えのバックフィル 手順2
    def test_議事録フォルダを読めない場合は読めなかったこととして返ること(self):
        with mock.patch.object(Path, "iterdir", side_effect=PermissionError(1, "denied")):
            結果 = writer.控えをバックフィルする(self.議事録フォルダ, self.控えフォルダ)
        self.assertTrue(結果.読めなかった)
        self.assertEqual(結果.写した件数, 0)

    def test_議事録フォルダが無い場合も例外にならないこと(self):
        結果 = writer.控えをバックフィルする(self.議事録フォルダ / "無い", self.控えフォルダ)
        self.assertEqual(結果.写した件数, 0)
        self.assertFalse(結果.読めなかった)

    # 仕様: design.md#控えのバックフィル 手順4
    def test_個別の議事録が読めない場合はその1件を飛ばすこと(self):
        (self.議事録フォルダ / "A__01.md").write_text("Aの本文", encoding="utf-8")
        (self.議事録フォルダ / "B__01.md").write_text("Bの本文", encoding="utf-8")
        元の読み取り = Path.read_text

        def Aだけ失敗する(自身, *引数, **名前付き):
            if 自身.name == "A__01.md":
                raise OSError(1, "operation not permitted")
            return 元の読み取り(自身, *引数, **名前付き)

        with mock.patch.object(Path, "read_text", Aだけ失敗する):
            結果 = writer.控えをバックフィルする(self.議事録フォルダ, self.控えフォルダ)

        self.assertEqual(結果.写した件数, 1)
        self.assertEqual(結果.飛ばした件数, 1)
        self.assertTrue((self.控えフォルダ / "B__01.md").exists())
        self.assertFalse((self.控えフォルダ / "A__01.md").exists())


if __name__ == "__main__":
    unittest.main()
