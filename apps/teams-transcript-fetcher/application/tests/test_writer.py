"""トランスクリプトの書き出し(T12)のテスト。"""

import tempfile
import unittest
from pathlib import Path

import writer


class 出力の書き出し(unittest.TestCase):
    """取得した本文が、そのままの内容で出力置き場に保存されることを検証する。

    トランスクリプトは日本語を含むため、文字コードの変換が入ると化ける。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.出力フォルダ = Path(self.一時ディレクトリ.name) / "vtt"
        self.addCleanup(self.一時ディレクトリ.cleanup)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-7
    def test_utf8でbomなしで書き出されること(self):
        本文 = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nこんにちは\n".encode("utf-8")
        結果 = writer.書き出す(本文, self.出力フォルダ, "会議__20260819T1030__01.vtt")
        書かれた内容 = 結果.パス.read_bytes()
        self.assertEqual(書かれた内容, 本文)
        self.assertFalse(書かれた内容.startswith(b"\xef\xbb\xbf"))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#トランスクリプトの取得と保存バッチ
    def test_改行がそのまま保持されること(self):
        """WEBVTTは改行で意味が決まる形式なので、変換されると壊れる。"""
        本文 = b"WEBVTT\r\n\r\n00:00:01.000 --> 00:00:02.000\r\nhello\r\n"
        結果 = writer.書き出す(本文, self.出力フォルダ, "会議__20260819T1030__01.vtt")
        self.assertEqual(結果.パス.read_bytes(), 本文)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#トランスクリプトの取得と保存バッチ
    def test_書き出しに成功するとパスとバイト数が返ること(self):
        結果 = writer.書き出す(b"WEBVTT\n", self.出力フォルダ, "会議__20260819T1030__01.vtt")
        self.assertIsInstance(結果, writer.書き出した)
        self.assertEqual(結果.バイト数, len(b"WEBVTT\n"))
        self.assertTrue(結果.パス.exists())

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#エラーハンドリング
    def test_書き出し後に一時ファイルが残らないこと(self):
        """一時ファイルが残ると、それもOneDriveに同期されてしまう。"""
        writer.書き出す(b"WEBVTT\n", self.出力フォルダ, "会議__20260819T1030__01.vtt")
        残ったファイル = sorted(パス.name for パス in self.出力フォルダ.iterdir())
        self.assertEqual(残ったファイル, ["会議__20260819T1030__01.vtt"])

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#トランスクリプトの取得と保存バッチ
    def test_出力置き場が無ければ作られること(self):
        writer.書き出す(b"WEBVTT\n", self.出力フォルダ, "会議__20260819T1030__01.vtt")
        self.assertTrue(self.出力フォルダ.is_dir())


class 同名ファイルがある場合(unittest.TestCase):
    """既にあるファイルを上書きしないことを検証する。

    取得済み記録が失われた場合の二重取得を、ここで受け止める設計になっている。
    上書きすると、すでに正しく保存したファイルを壊しうる。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.出力フォルダ = Path(self.一時ディレクトリ.name) / "vtt"
        self.出力フォルダ.mkdir(parents=True)
        self.addCleanup(self.一時ディレクトリ.cleanup)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#未取得の判定バッチ-2
    def test_同名ファイルがある場合は上書きせずスキップとして扱われること(self):
        ファイル名 = "会議__20260819T1030__01.vtt"
        (self.出力フォルダ / ファイル名).write_bytes("WEBVTT\n先に保存したもの\n".encode("utf-8"))

        結果 = writer.書き出す("WEBVTT\n新しい内容\n".encode("utf-8"), self.出力フォルダ, ファイル名)

        self.assertIsInstance(結果, writer.既にあった)
        self.assertEqual(
            (self.出力フォルダ / ファイル名).read_bytes(), "WEBVTT\n先に保存したもの\n".encode("utf-8")
        )


class 出力置き場の外への書き出し(unittest.TestCase):
    """出力置き場の外に書き出せないことを検証する。

    出力ファイル名は会議名由来なのでパストラバーサルの経路になりうる。
    ファイル名の組み立て側でも除去しているが、ここが最後の砦になる。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.出力フォルダ = Path(self.一時ディレクトリ.name) / "vtt"
        self.addCleanup(self.一時ディレクトリ.cleanup)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#セキュリティ
    def test_親ディレクトリを指すファイル名が拒否されること(self):
        with self.assertRaises(writer.書き出し先が不正):
            writer.書き出す(b"WEBVTT\n", self.出力フォルダ, "../外に出る.vtt")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#セキュリティ
    def test_絶対パスのファイル名が拒否されること(self):
        with self.assertRaises(writer.書き出し先が不正):
            writer.書き出す(b"WEBVTT\n", self.出力フォルダ, "/tmp/外に出る.vtt")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#セキュリティ
    def test_拒否された場合にファイルが作られないこと(self):
        with self.assertRaises(writer.書き出し先が不正):
            writer.書き出す(b"WEBVTT\n", self.出力フォルダ, "../外に出る.vtt")
        self.assertFalse((self.出力フォルダ.parent / "外に出る.vtt").exists())


if __name__ == "__main__":
    unittest.main()
