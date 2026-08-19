"""URLの検証(T10)と応答の分類(T11)のテスト。"""

import builtins
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


class 証明書バンドルの自動解決(unittest.TestCase):
    """信頼ストアが空でも、バンドルを自分で探して読み込むことを検証する。

    macOSでpython.org版のPythonを使うと既定の信頼ストアが空になる。
    `SSL_CERT_FILE` を手で設定させる方式だと「ターミナルでは動くのにlaunchdでは
    動かない」という分かりにくい状態になるため、バッチ自身で探す。
    """

    def setUp(self):
        # モジュールに覚えさせた文脈を毎回捨てる(初回のみ組み立てる作りのため)。
        downloader._ssl文脈 = None
        self.addCleanup(setattr, downloader, "_ssl文脈", None)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#外部ライブラリの方針
    def test_この環境で証明書を読み込めること(self):
        self.assertGreater(
            downloader.ssl文脈を用意する().cert_store_stats()["x509_ca"], 0
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#パフォーマンス
    def test_2回目は組み立て直さないこと(self):
        """実行ごとに証明書を読み直す必要はない。"""
        self.assertIs(downloader.ssl文脈を用意する(), downloader.ssl文脈を用意する())

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#外部ライブラリの方針
    def test_certifiが無くても候補を探すこと(self):
        """certifi に依存しない。無ければOS側のバンドルを探す。"""
        本来のimport = builtins.__import__

        def certifiだけ失敗させる(名前, *引数, **キーワード引数):
            if 名前 == "certifi":
                raise ImportError("テストのため無いものとして扱う")
            return 本来のimport(名前, *引数, **キーワード引数)

        with mock.patch.object(builtins, "__import__", certifiだけ失敗させる):
            見つかったもの = downloader._証明書バンドルを探す()
        # この環境で見つかるかはOS依存なので、例外にならないことを固定する。
        self.assertTrue(見つかったもの is None or isinstance(見つかったもの, str))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-4-2
    def test_バンドルが見つからない場合にエラーログを出すこと(self):
        """黙って失敗させない。何をすればよいかをログに残す。"""
        with mock.patch.object(downloader, "_証明書バンドルを探す", return_value=None):
            with mock.patch.object(
                downloader.ssl, "create_default_context"
            ) as 文脈を作る:
                文脈を作る.return_value.cert_store_stats.return_value = {"x509_ca": 0}
                with self.assertLogs(level="ERROR") as ログ:
                    downloader.ssl文脈を用意する()
        self.assertIn("証明書のセットアップ", "\n".join(ログ.output))


class 待っても直らない失敗の区別(unittest.TestCase):
    """TLS証明書の検証エラーを、通常の通信エラーと区別できることを検証する。

    分類は一時的失敗のまま(URLを使い潰さない)。ただし待っても直らないため、
    記録ファイルに残して人が対処できるようにする必要がある。
    """

    def 取得する(self, 例外):
        with mock.patch("urllib.request.urlopen", side_effect=例外):
            return downloader.取得する(
                妥当なurl, タイムアウト秒=30, 許可するホスト接尾辞=許可する接尾辞
            )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-4
    def test_証明書の検証エラーが一時的失敗のまま設定の問題として印が付くこと(self):
        import ssl

        例外 = urllib.error.URLError(
            ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED")
        )
        結果 = self.取得する(例外)
        self.assertIsInstance(結果, downloader.一時的失敗)
        self.assertTrue(結果.設定の問題)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-4
    def test_通常の接続エラーには設定の問題の印が付かないこと(self):
        """毎回記録すると、一時的なネットワーク断で記録が埋まる。"""
        結果 = self.取得する(urllib.error.URLError("接続できない"))
        self.assertIsInstance(結果, downloader.一時的失敗)
        self.assertFalse(結果.設定の問題)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-4
    def test_タイムアウトには設定の問題の印が付かないこと(self):
        結果 = self.取得する(TimeoutError())
        self.assertFalse(結果.設定の問題)


if __name__ == "__main__":
    unittest.main()
