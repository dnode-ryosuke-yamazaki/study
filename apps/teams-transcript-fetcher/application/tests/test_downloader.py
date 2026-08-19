"""URLの検証(T10)と応答の分類(T11)のテスト。"""

import unittest
import urllib.error
from unittest import mock

import downloader

許可する接尾辞 = (".sharepoint.com", ".svc.ms")
妥当なurl = "https://example.sharepoint.com/dl?tempauth=xxx"


class アクセス先urlの検証(unittest.TestCase):
    """台帳やURLファイルに書かれたURLを、アクセスする前に検証することを検証する。

    これらのファイルの内容は外部から与えられた文字列として扱う。検証しないと、
    書き換えられたファイルによって想定外のホストへ通信させられる。
    """

    def 検証する(self, url: str):
        return downloader.urlを検証する(url, 許可する接尾辞)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#セキュリティ
    def test_想定どおりのurlが受理されること(self):
        self.assertIsNone(self.検証する(妥当なurl))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#バリデーション
    def test_httpsでないurlが拒否されること(self):
        with self.assertRaises(downloader.urlが不正):
            self.検証する("http://example.sharepoint.com/dl")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#バリデーション
    def test_許可していないホストのurlが拒否されること(self):
        with self.assertRaises(downloader.urlが不正):
            self.検証する("https://attacker.example.com/dl")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#バリデーション
    def test_許可ホストを名前の一部に含むだけのホストが拒否されること(self):
        """`evil-sharepoint.com` のように接尾辞の直前が区切りでない場合を弾く。
        単純な文字列一致だと通ってしまう。
        """
        with self.assertRaises(downloader.urlが不正):
            self.検証する("https://evil-sharepoint.com/dl")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#バリデーション
    def test_urlとして解釈できない文字列が拒否されること(self):
        with self.assertRaises(downloader.urlが不正):
            self.検証する("これはURLではない")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ログ
    def test_拒否したホスト名がログに残ること(self):
        """実際のホストが未確認のため、拒否した事実から正しい許可リストが分かる。"""
        with self.assertLogs(level="WARNING") as ログ:
            with self.assertRaises(downloader.urlが不正):
                self.検証する("https://attacker.example.com/dl")
        self.assertIn("attacker.example.com", "\n".join(ログ.output))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#セキュリティ
    def test_ログにurl全体が出力されないこと(self):
        """URLは実質ベアラトークンなので、ホスト名までに留める。"""
        with self.assertLogs(level="WARNING") as ログ:
            with self.assertRaises(downloader.urlが不正):
                self.検証する("https://attacker.example.com/dl?tempauth=SECRET")
        self.assertNotIn("SECRET", "\n".join(ログ.output))


def 応答を模す(本文: bytes):
    """urlopen が返すレスポンスの代わり。"""
    応答 = mock.MagicMock()
    応答.read.return_value = 本文
    応答.__enter__.return_value = 応答
    応答.__exit__.return_value = False
    return 応答


class 応答の分類(unittest.TestCase):
    """取得結果を「成功」「恒久的失敗」「一時的失敗」に分けることを検証する。

    恒久的失敗は同じURLで二度と成功しないためリトライせず、一時的失敗は次回の
    定期実行に任せる。この区別を誤ると、無駄な通信か取りこぼしのどちらかになる。
    """

    def 取得する(self):
        return downloader.取得する(
            妥当なurl, タイムアウト秒=30, 許可するホスト接尾辞=許可する接尾辞
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-2
    def test_webvttの識別行で始まる応答が成功として扱われること(self):
        with mock.patch("urllib.request.urlopen", return_value=応答を模す(b"WEBVTT\n\n00:00")):
            結果 = self.取得する()
        self.assertIsInstance(結果, downloader.成功)
        self.assertEqual(結果.本文, b"WEBVTT\n\n00:00")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-2
    def test_本文がwebvttでない場合はステータスが成功でも恒久的失敗になること(self):
        """期限切れのURLがエラーページを本文として返し、ステータスだけ成功に
        なる場合がある。これを保存すると取得済みとして記録され台帳も消えるため、
        復旧できない誤りになる。
        """
        with mock.patch(
            "urllib.request.urlopen", return_value=応答を模す(b"<html>Access denied</html>")
        ):
            結果 = self.取得する()
        self.assertIsInstance(結果, downloader.恒久的失敗)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-7
    def test_先頭のbomが取り除かれて成功になること(self):
        """BOM付きで返ってきても、保存はBOMなしにする必要がある。"""
        with mock.patch(
            "urllib.request.urlopen", return_value=応答を模す(b"\xef\xbb\xbfWEBVTT\n")
        ):
            結果 = self.取得する()
        self.assertIsInstance(結果, downloader.成功)
        self.assertEqual(結果.本文, b"WEBVTT\n")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-1
    def test_401と403と404が恒久的失敗になること(self):
        for ステータス in (401, 403, 404):
            with self.subTest(ステータス=ステータス):
                例外 = urllib.error.HTTPError(妥当なurl, ステータス, "", {}, None)
                with mock.patch("urllib.request.urlopen", side_effect=例外):
                    結果 = self.取得する()
                self.assertIsInstance(結果, downloader.恒久的失敗)
                self.assertEqual(結果.ステータス, ステータス)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-4
    def test_5xxが一時的失敗になること(self):
        for ステータス in (500, 503):
            with self.subTest(ステータス=ステータス):
                例外 = urllib.error.HTTPError(妥当なurl, ステータス, "", {}, None)
                with mock.patch("urllib.request.urlopen", side_effect=例外):
                    結果 = self.取得する()
                self.assertIsInstance(結果, downloader.一時的失敗)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-4
    def test_接続エラーが一時的失敗になること(self):
        例外 = urllib.error.URLError("接続できない")
        with mock.patch("urllib.request.urlopen", side_effect=例外):
            結果 = self.取得する()
        self.assertIsInstance(結果, downloader.一時的失敗)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-4
    def test_タイムアウトが一時的失敗になること(self):
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError()):
            結果 = self.取得する()
        self.assertIsInstance(結果, downloader.一時的失敗)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-2
    def test_検証を通らないurlは通信せず恒久的失敗になること(self):
        with mock.patch("urllib.request.urlopen") as 呼び出し:
            結果 = downloader.取得する(
                "https://attacker.example.com/dl",
                タイムアウト秒=30,
                許可するホスト接尾辞=許可する接尾辞,
            )
        self.assertIsInstance(結果, downloader.恒久的失敗)
        呼び出し.assert_not_called()

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#実行環境-2
    def test_認証情報を付けずにアクセスすること(self):
        """ダウンロードURLは事前認証済みで、認証ヘッダを付けると失敗する。"""
        with mock.patch(
            "urllib.request.urlopen", return_value=応答を模す(b"WEBVTT\n")
        ) as 呼び出し:
            self.取得する()
        渡された要求 = 呼び出し.call_args.args[0]
        self.assertNotIn("Authorization", dict(渡された要求.header_items()))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#パフォーマンス
    def test_タイムアウトが渡されること(self):
        with mock.patch(
            "urllib.request.urlopen", return_value=応答を模す(b"WEBVTT\n")
        ) as 呼び出し:
            self.取得する()
        self.assertEqual(呼び出し.call_args.kwargs["timeout"], 30)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#セキュリティ
    def test_失敗の理由にurlが含まれないこと(self):
        """理由は記録ファイルとログに出るため、URLを混ぜてはならない。"""
        例外 = urllib.error.HTTPError(妥当なurl, 403, "Forbidden", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=例外):
            結果 = self.取得する()
        self.assertNotIn("tempauth", 結果.理由)


if __name__ == "__main__":
    unittest.main()
