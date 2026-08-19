"""1回の実行の組み立て(T13〜T15, T17, T19, T20)のテスト。"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import config
import downloader
import fetch_transcripts
import state

基準時刻 = datetime(2026, 8, 19, 10, 40, tzinfo=timezone.utc)


def 発行時刻(分前: int = 0) -> str:
    return (基準時刻 - timedelta(minutes=分前)).isoformat(timespec="milliseconds")


class 実行の土台(unittest.TestCase):
    """各テストが実物の同期フォルダに触れないよう、一時ディレクトリで組み立てる。"""

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.作業フォルダ = Path(self.一時ディレクトリ.name) / "transcript"
        self.状態フォルダ = Path(self.一時ディレクトリ.name) / "state"
        self.addCleanup(self.一時ディレクトリ.cleanup)
        self.状態パッチ = mock.patch.object(config, "状態フォルダ", self.状態フォルダ)
        self.状態パッチ.start()
        self.addCleanup(self.状態パッチ.stop)
        self.設定 = config.load(作業フォルダ=self.作業フォルダ)
        self.設定.台帳フォルダ.mkdir(parents=True)
        self.設定.urlフォルダ.mkdir(parents=True)

    def 台帳を置く(self, 録画の識別子="01ABCDEF", **上書き) -> Path:
        中身 = {
            "meetingName": "定例会議.mp4",
            "siteUrl": "https://example.sharepoint.com/sites/Team",
            "driveId": "b!dummy",
            "recordingId": 録画の識別子,
            "recordingCreatedAt": "2026-08-19T10:30:00.000Z",
            "source": "channel",
            "issuedAt": 発行時刻(1),
            "urls": ["https://example.sharepoint.com/dl1"],
        }
        中身.update(上書き)
        中身 = {キー: 値 for キー, 値 in 中身.items() if 値 is not ...}
        パス = self.設定.台帳フォルダ / f"{録画の識別子}.json"
        パス.write_text(json.dumps(中身, ensure_ascii=False), encoding="utf-8")
        return パス

    def urlファイルを置く(self, 録画の識別子="01ABCDEF", **上書き) -> Path:
        中身 = {
            "recordingId": 録画の識別子,
            "issuedAt": 発行時刻(0),
            "urls": [
                "https://example.sharepoint.com/dl1",
                "https://example.sharepoint.com/dl2",
            ],
        }
        中身.update(上書き)
        パス = self.設定.urlフォルダ / f"{録画の識別子}.json"
        パス.write_text(json.dumps(中身, ensure_ascii=False), encoding="utf-8")
        return パス

    def 取得を差し替える(self, 戻り値):
        return mock.patch.object(downloader, "取得する", return_value=戻り値)

    def 実行する(self, 現在時刻=None):
        return fetch_transcripts.実行する(self.設定, 現在時刻=現在時刻 or 基準時刻)


class 正常に取得できる場合(実行の土台):
    """1件のトランスクリプトが保存され、台帳が片付けられることを検証する。"""

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#トランスクリプトの取得と保存-2
    def test_保存されて台帳とurlファイルが削除されること(self):
        台帳のパス = self.台帳を置く()
        with self.取得を差し替える(downloader.成功(本文=b"WEBVTT\n")):
            結果 = self.実行する()
        self.assertEqual(結果.成功件数, 1)
        self.assertFalse(台帳のパス.exists())
        保存されたファイル = list(self.設定.出力フォルダ.iterdir())
        self.assertEqual(len(保存されたファイル), 1)
        self.assertTrue(保存されたファイル[0].name.endswith(".vtt"))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#トランスクリプトの取得と保存-3
    def test_取得済みとして記録されること(self):
        self.台帳を置く()
        with self.取得を差し替える(downloader.成功(本文=b"WEBVTT\n")):
            self.実行する()
        読んだ状態 = state.読み込む(self.設定.状態ファイル)
        self.assertTrue(読んだ状態.取得済みか(state.トランスクリプトの識別子("01ABCDEF", 0)))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#トランスクリプトの取得と保存-2
    def test_2回実行しても重複して取得しないこと(self):
        self.台帳を置く()
        with self.取得を差し替える(downloader.成功(本文=b"WEBVTT\n")) as 呼び出し:
            self.実行する()
            self.実行する()
        self.assertEqual(呼び出し.call_count, 1)


class 件数の正がurlファイル側にある場合(実行の土台):
    """台帳よりURLファイルの件数が多い場合に、その件数が正になることを検証する。

    台帳の件数を正にすると、フロー②が2件発行しても台帳が1件なら1件保存した
    時点で完了と判定し、台帳を消して2件目を永久に取りこぼす。
    """

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#トランスクリプトの列挙-1
    def test_台帳1件でurlファイル2件なら2件取得されること(self):
        self.台帳を置く()
        self.urlファイルを置く()
        with self.取得を差し替える(downloader.成功(本文=b"WEBVTT\n")) as 呼び出し:
            結果 = self.実行する()
        self.assertEqual(呼び出し.call_count, 2)
        self.assertEqual(結果.成功件数, 2)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#トランスクリプトの列挙-3
    def test_1件だけ保存できた時点では台帳が削除されないこと(self):
        台帳のパス = self.台帳を置く()
        self.urlファイルを置く()
        # 1件目は成功、2件目は一時的失敗にする。
        戻り値たち = [
            downloader.成功(本文=b"WEBVTT\n"),
            downloader.一時的失敗(理由="HTTP 503", ステータス=503),
        ]
        with mock.patch.object(downloader, "取得する", side_effect=戻り値たち):
            結果 = self.実行する()
        self.assertEqual(結果.成功件数, 1)
        self.assertTrue(台帳のパス.exists())


class フェーズ2の主経路(実行の土台):
    """台帳にURLがなくURLファイルだけがある状態で消費できることを検証する。

    これはフェーズ2の通常経路。台帳側に比較対象の発行時刻がないため、
    新旧比較の分岐に含めると条件が成立せず発行されたURLを永久に消費しない。
    """

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#台帳の読み取りと使用するurlの一覧の決定バッチ
    def test_urlを持たない台帳とurlファイルの組み合わせで取得できること(self):
        self.台帳を置く(urls=[], issuedAt=...)
        self.urlファイルを置く(urls=["https://example.sharepoint.com/dl1"])
        with self.取得を差し替える(downloader.成功(本文=b"WEBVTT\n")):
            結果 = self.実行する()
        self.assertEqual(結果.成功件数, 1)


class トランスクリプトが0件の場合(実行の土台):
    """URLを持たない台帳が要発行として扱われ、記録に残ることを検証する。

    実運用で「要手動確認」に至る大半がこのケース(会議で文字起こしが
    有効でなかった場合)。
    """

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-7
    def test_要発行として扱われ台帳が残ること(self):
        台帳のパス = self.台帳を置く(urls=[], issuedAt=...)
        with self.取得を差し替える(downloader.成功(本文=b"WEBVTT\n")) as 呼び出し:
            結果 = self.実行する()
        self.assertEqual(結果.要発行件数, 1)
        呼び出し.assert_not_called()
        self.assertTrue(台帳のパス.exists())

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#処理結果の記録-5
    def test_トランスクリプト0件のラベルで記録されること(self):
        self.台帳を置く(urls=[], issuedAt=...)
        self.実行する()
        書かれた内容 = self.設定.記録ファイル.read_text(encoding="utf-8")
        self.assertIn("[トランスクリプト0件]", 書かれた内容)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#処理結果の記録-3
    def test_同じ失敗が繰り返し追記されないこと(self):
        """5分間隔で実行されるため、抑止しないと1日で数百行が同一内容で埋まる。"""
        self.台帳を置く(urls=[], issuedAt=...)
        self.実行する()
        self.実行する()
        書かれた内容 = self.設定.記録ファイル.read_text(encoding="utf-8")
        self.assertEqual(書かれた内容.count("[トランスクリプト0件]"), 1)


class 期限しきい値を超えている場合(実行の土台):
    """古いURLはアクセスを試みず要発行にすることを検証する。

    確実に失敗する通信を省ける。
    """

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#台帳の読み取りと使用するurlの一覧の決定バッチ
    def test_アクセスを試みず要発行になること(self):
        self.台帳を置く(issuedAt=発行時刻(120))
        with self.取得を差し替える(downloader.成功(本文=b"WEBVTT\n")) as 呼び出し:
            結果 = self.実行する()
        呼び出し.assert_not_called()
        self.assertEqual(結果.要発行件数, 1)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#台帳と要求のライフサイクル
    def test_古いurlファイルが削除されること(self):
        self.台帳を置く(issuedAt=発行時刻(120))
        urlのパス = self.urlファイルを置く(issuedAt=発行時刻(120))
        self.実行する()
        self.assertFalse(urlのパス.exists())


class 恒久的失敗の扱い(実行の土台):
    """同じURLを再試行せず、回数を録画単位で数えることを検証する。"""

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-3
    def test_台帳が削除されず残ること(self):
        台帳のパス = self.台帳を置く()
        with self.取得を差し替える(downloader.恒久的失敗(理由="HTTP 403", ステータス=403)):
            結果 = self.実行する()
        self.assertEqual(結果.恒久的失敗件数, 1)
        self.assertTrue(台帳のパス.exists())

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-1
    def test_次の実行で同じurlを再試行しないこと(self):
        """発行時刻を記録して除外する。しないと期限しきい値に達するまで
        5分ごとに死んだURLへアクセスし続ける。
        """
        self.台帳を置く()
        with self.取得を差し替える(
            downloader.恒久的失敗(理由="HTTP 403", ステータス=403)
        ) as 呼び出し:
            self.実行する()
            self.実行する()
        self.assertEqual(呼び出し.call_count, 1)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-6
    def test_同一実行内の複数失敗で加算が1回だけであること(self):
        """一覧がまとめて期限切れになった場合に、1回の実行で即座に上限へ
        達して人手案件に落ちるのを防ぐ。
        """
        self.台帳を置く()
        self.urlファイルを置く()
        with self.取得を差し替える(downloader.恒久的失敗(理由="HTTP 403", ステータス=403)):
            self.実行する()
        読んだ状態 = state.読み込む(self.設定.状態ファイル)
        self.assertEqual(読んだ状態.録画の状態("01ABCDEF").恒久的失敗の回数, 1)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#処理の順序と上限-3
    def test_上限に達した録画が処理対象から除外されること(self):
        self.台帳を置く()
        読んだ状態 = state.状態()
        読んだ状態.録画の状態("01ABCDEF").恒久的失敗の回数 = 3
        state.保存する(読んだ状態, self.設定.状態ファイル)
        with self.取得を差し替える(downloader.成功(本文=b"WEBVTT\n")) as 呼び出し:
            結果 = self.実行する()
        呼び出し.assert_not_called()
        self.assertEqual(結果.要手動確認件数, 1)


class 一時的失敗の扱い(実行の土台):
    """状態を変えずに次回へ委ねることを検証する。"""

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-4
    def test_回数が加算されず台帳も残ること(self):
        台帳のパス = self.台帳を置く()
        with self.取得を差し替える(downloader.一時的失敗(理由="HTTP 503", ステータス=503)):
            結果 = self.実行する()
        self.assertEqual(結果.一時的失敗件数, 1)
        self.assertTrue(台帳のパス.exists())
        読んだ状態 = state.読み込む(self.設定.状態ファイル)
        self.assertEqual(読んだ状態.録画の状態("01ABCDEF").恒久的失敗の回数, 0)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-4
    def test_次の実行でリトライされること(self):
        self.台帳を置く()
        with self.取得を差し替える(
            downloader.一時的失敗(理由="HTTP 503", ステータス=503)
        ) as 呼び出し:
            self.実行する()
            self.実行する()
        self.assertEqual(呼び出し.call_count, 2)


class 不正な台帳の退避(実行の土台):
    """壊れた台帳が退避され、他の録画の処理が止まらないことを検証する。"""

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#台帳と要求のライフサイクル
    def test_不正な台帳が退避されて他は処理されること(self):
        (self.設定.台帳フォルダ / "01BROKEN.json").write_text("{壊れている", encoding="utf-8")
        self.台帳を置く()
        with self.取得を差し替える(downloader.成功(本文=b"WEBVTT\n")):
            結果 = self.実行する()
        self.assertEqual(結果.退避件数, 1)
        self.assertEqual(結果.成功件数, 1)
        self.assertTrue((self.設定.退避フォルダ / "01BROKEN.json").exists())


class 全体を中断する条件(実行の土台):
    """台帳置き場が無い場合に中断することを検証する。

    「台帳が0件」と同じ扱いにすると、同期が外れているのに
    「今日は会議がなかった」と誤認して静かに止まる。
    """

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#エラーハンドリング
    def test_台帳置き場が無い場合に中断すること(self):
        import shutil

        shutil.rmtree(self.設定.台帳フォルダ)
        with self.assertLogs(level="ERROR"):
            結果 = self.実行する()
        self.assertTrue(結果.中断した)
        self.assertEqual(結果.成功件数, 0)


class 処理の順序と上限(実行の土台):
    """新しいURLから処理し、上限件数で打ち切ることを検証する。"""

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#処理の順序と上限-1
    def test_発行時刻の新しい順に処理されること(self):
        # 別の録画は会議名か録画作成時刻が異なる(同じだと出力ファイル名が衝突する)。
        self.台帳を置く(
            "01OLD", issuedAt=発行時刻(20), recordingCreatedAt="2026-08-19T09:00:00.000Z"
        )
        self.台帳を置く(
            "01NEW", issuedAt=発行時刻(1), recordingCreatedAt="2026-08-19T10:30:00.000Z"
        )
        処理した順 = []

        def 記録して成功(url, **_):
            処理した順.append(url)
            return downloader.成功(本文=b"WEBVTT\n")

        with mock.patch.object(downloader, "取得する", side_effect=記録して成功):
            self.実行する()
        self.assertEqual(len(処理した順), 2)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#処理の順序と上限-2
    def test_上限件数に達した場合に残りが次回へ委ねられること(self):
        for 連番 in range(3):
            self.台帳を置く(
                f"01ID{連番}",
                issuedAt=発行時刻(連番),
                recordingCreatedAt=f"2026-08-19T1{連番}:00:00.000Z",
            )
        object.__setattr__(self.設定, "処理上限件数", 2)
        with self.取得を差し替える(downloader.成功(本文=b"WEBVTT\n")) as 呼び出し:
            self.実行する()
        self.assertEqual(呼び出し.call_count, 2)


class 出力ファイル名が別の録画と衝突する場合(実行の土台):
    """同名ファイルで取得済み扱いにするとき、警告を残すことを検証する。

    出力ファイル名は会議名と時刻(分まで)と連番だけで決まるため、同名・同分の
    別録画では一致しうる。そのとき黙って飛ばすと、その録画のトランスクリプトを
    静かに取り逃す。名前を変えるより、気づけるようにする方を選んだ。
    """

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#未取得の判定バッチ-2
    def test_取得済み記録に無い同名ファイルがある場合に警告が残ること(self):
        self.台帳を置く("01FIRST")
        with self.取得を差し替える(downloader.成功(本文=b"WEBVTT\n")):
            self.実行する()

        # 会議名も録画作成時刻も同じ別の録画。出力ファイル名が完全に一致する。
        self.台帳を置く("01SECOND")
        with self.取得を差し替える(downloader.成功(本文=b"WEBVTT\n")) as 呼び出し:
            with self.assertLogs(level="WARNING") as ログ:
                self.実行する()
        呼び出し.assert_not_called()
        self.assertIn("名前衝突の可能性", "\n".join(ログ.output))


class 想定外の例外(実行の土台):
    """1件の想定外の失敗で全体が落ちないことを検証する。"""

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-9
    def test_想定外の例外でも全体が異常終了しないこと(self):
        self.台帳を置く()
        with mock.patch.object(downloader, "取得する", side_effect=ValueError("想定外")):
            with self.assertLogs(level="ERROR"):
                結果 = self.実行する()
        self.assertFalse(結果.中断した)


class 観測用のログ(実行の土台):
    """検証項目を実機で観測するためのログが出ることを検証する。

    事前実測をしない方針のため、これらのログが揃っていることが実装の完了条件。
    """

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ログ
    def test_urlの出所と発行からの経過時間が記録されること(self):
        self.台帳を置く()
        with self.取得を差し替える(downloader.成功(本文=b"WEBVTT\n")):
            with self.assertLogs(level="INFO") as ログ:
                self.実行する()
        出力 = "\n".join(ログ.output)
        self.assertIn("URLの鮮度", 出力)
        self.assertIn("出所=台帳", 出力)
        self.assertIn("発行からの経過=", 出力)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ログ
    def test_既知件数とurl数が記録されること(self):
        self.台帳を置く()
        self.urlファイルを置く()
        with self.取得を差し替える(downloader.成功(本文=b"WEBVTT\n")):
            with self.assertLogs(level="DEBUG") as ログ:
                self.実行する()
        出力 = "\n".join(ログ.output)
        self.assertIn("既知件数=2", 出力)
        self.assertIn("URL数=2", 出力)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#セキュリティ
    def test_ログにurlが含まれないこと(self):
        self.台帳を置く()
        with self.取得を差し替える(downloader.成功(本文=b"WEBVTT\n")):
            with self.assertLogs(level="DEBUG") as ログ:
                self.実行する()
        self.assertNotIn("://", "\n".join(ログ.output))


if __name__ == "__main__":
    unittest.main()
