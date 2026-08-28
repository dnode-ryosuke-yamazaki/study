"""設定の読み込み(tasks.md T1)のテスト。"""

import logging
import os
import unittest
from pathlib import Path
from unittest import mock

import config


class 既定のしきい値と上限(unittest.TestCase):
    """バッチの打ち切り・期限判定を決める設定値が、仕様どおりの既定値であることを検証する。

    どの値も仕様で根拠付きに決められている。ずれると「いつ諦めるか」「いつ人手に
    委ねるか」が変わり、取りこぼしや無駄なPower Automate実行に直結する。
    """

    def setUp(self):
        self.設定 = config.load()

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#処理の順序と上限-2
    def test_1回の実行で取得を試みる上限が20件であること(self):
        self.assertEqual(self.設定.処理上限件数, 20)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#パフォーマンス
    def test_ダウンロードのタイムアウトが30秒であること(self):
        self.assertEqual(self.設定.タイムアウト秒, 30)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-5
    def test_恒久的失敗の上限が3回であること(self):
        self.assertEqual(self.設定.恒久的失敗の上限, 3)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-8
    def test_進捗のない発行要求の上限が10回であること(self):
        self.assertEqual(self.設定.進捗なし発行要求の上限, 10)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-8
    def test_進捗のない発行要求の上限が実行間隔との積で約50分に相当すること(self):
        """要件[8]は上限を「実行間隔との積が生成の遅れを上回る」ことで定めている。

        上限値と実行間隔を別々に変えると根拠が崩れるため、積として検証する。
        """
        実行間隔分 = self.設定.実行間隔秒 / 60
        self.assertEqual(実行間隔分 * self.設定.進捗なし発行要求の上限, 50)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#処理結果の記録-4
    def test_台帳の長期滞留のしきい値が7日であること(self):
        self.assertEqual(self.設定.長期滞留しきい値日, 7)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ダウンロードurlの発行要求-5
    def test_未処理の要求を退避するしきい値が30分であること(self):
        self.assertEqual(self.設定.要求滞留しきい値分, 30)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#使用するダウンロードurlの決定バッチ
    def test_ダウンロードurlの期限しきい値が設定値として存在すること(self):
        """実測前の暫定値。実機の観測結果で調整する前提のため、値の妥当性ではなく
        「設定として外に出ていること」を固定する。
        """
        self.assertGreater(self.設定.url期限しきい値分, 0)


class 作業フォルダ配下のパスの導出(unittest.TestCase):
    """Power Automateとの受け渡しに使う各フォルダのパスが、作業フォルダ1つから導かれることを検証する。

    受け渡し場所がずれるとフローとバッチが噛み合わなくなるため、
    個別に設定させず作業フォルダからの導出に固定する。
    """

    def setUp(self):
        self.作業フォルダ = Path("/tmp/dummy-work")
        self.設定 = config.load(作業フォルダ=self.作業フォルダ)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#作業フォルダの構成
    def test_台帳置き場が作業フォルダ配下に導出されること(self):
        self.assertEqual(self.設定.台帳フォルダ, self.作業フォルダ / "ledger")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#作業フォルダの構成
    def test_要求置き場が作業フォルダ配下に導出されること(self):
        self.assertEqual(self.設定.要求フォルダ, self.作業フォルダ / "request")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#作業フォルダの構成
    def test_url置き場が作業フォルダ配下に導出されること(self):
        self.assertEqual(self.設定.urlフォルダ, self.作業フォルダ / "url")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#作業フォルダの構成
    def test_出力置き場が作業フォルダ配下に導出されること(self):
        self.assertEqual(self.設定.出力フォルダ, self.作業フォルダ / "vtt")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#作業フォルダの構成
    def test_退避先が作業フォルダ配下に導出されること(self):
        self.assertEqual(self.設定.退避フォルダ, self.作業フォルダ / "invalid")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#処理結果の記録-2
    def test_記録ファイルが作業フォルダ配下に導出されること(self):
        """記録ファイルは「PCの前にいなくても確認できる」ことが要件なので、
        同期されるOneDrive側(=作業フォルダ配下)に置く必要がある。
        """
        self.assertEqual(self.設定.記録ファイル, self.作業フォルダ / "_status.md")


class 同期対象外に置く状態の場所(unittest.TestCase):
    """取得済み記録・ロック・ログが、OneDriveの同期フォルダの外に置かれることを検証する。

    同期フォルダに置くとOneDriveが競合ファイルを作り、状態が二重化して
    取得済み判定が壊れる。「作業フォルダの配下でないこと」が要件そのもの。
    """

    def setUp(self):
        self.作業フォルダ = Path("/tmp/dummy-work")
        self.設定 = config.load(作業フォルダ=self.作業フォルダ)

    def assert_作業フォルダの外にあること(self, パス: Path):
        self.assertFalse(
            パス.is_relative_to(self.作業フォルダ),
            f"{パス} が作業フォルダ配下にある(同期されると状態が壊れる)",
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#状態管理-1
    def test_取得済み記録が作業フォルダの外に置かれること(self):
        self.assert_作業フォルダの外にあること(self.設定.状態ファイル)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#状態管理
    def test_ロックが作業フォルダの外に置かれること(self):
        self.assert_作業フォルダの外にあること(self.設定.ロックファイル)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ログ
    def test_ログが作業フォルダの外に置かれること(self):
        self.assert_作業フォルダの外にあること(self.設定.ログファイル)


class 既定のログレベル(unittest.TestCase):
    """ログの既定レベルがDEBUGであることを検証する。

    仕様は「検証が難しい前提を実機のログで観測する」方針を採っており、
    観測に使う項目がDEBUGで出る。既定がINFOだと観測自体が成立しない。
    """

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ログ
    def test_既定のログレベルがdebugであること(self):
        self.assertEqual(config.load().ログレベル, logging.DEBUG)


class 作業フォルダの上書き(unittest.TestCase):
    """作業フォルダを外から差し替えられることを検証する。

    テストが実物の同期フォルダに触れないようにするため、および
    環境ごとにOneDriveの同期先名が異なるために必要。
    """

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#作業フォルダの構成
    def test_環境変数で作業フォルダを上書きできること(self):
        with mock.patch.dict(os.environ, {"TRANSCRIPT_FETCHER_WORK_DIR": "/tmp/from-env"}):
            self.assertEqual(config.load().作業フォルダ, Path("/tmp/from-env"))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#作業フォルダの構成
    def test_引数の作業フォルダが環境変数より優先されること(self):
        with mock.patch.dict(os.environ, {"TRANSCRIPT_FETCHER_WORK_DIR": "/tmp/from-env"}):
            設定 = config.load(作業フォルダ=Path("/tmp/from-arg"))
        self.assertEqual(設定.作業フォルダ, Path("/tmp/from-arg"))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#実行環境-6
    def test_既定の作業フォルダがauto直下ではなくtranscript配下であること(self):
        """`00_root/auto/` 直下に置くとTeams投稿用のPower Automateフローが
        ファイル作成を検知して意図しない投稿が起きるため、サブフォルダに置く。
        """
        with mock.patch.dict(os.environ, {}, clear=True):
            既定 = config.load().作業フォルダ
        self.assertEqual(既定.name, "transcript")
        self.assertEqual(既定.parent.name, "auto")


class 監視のしきい値(unittest.TestCase):
    """同期停滞の検知・復旧・通知を決める設定値が、仕様どおりの既定値であることを検証する。

    どの値も仕様で根拠付きに決められている。ずれると誤検知(不要な再起動)や
    検知漏れ(停滞の放置)に直結する。
    """

    def setUp(self):
        self.設定 = config.load()

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#停滞判定の閾値-1
    def test_停滞判定のしきい値が45分であること(self):
        self.assertEqual(self.設定.停滞判定しきい値分, 45)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#スリープ復帰直後の誤検知防止-1
    def test_実行の中断とみなす間隔が15分であること(self):
        self.assertEqual(self.設定.実行中断とみなす間隔分, 15)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#スリープ復帰直後の誤検知防止-2
    def test_復帰後の猶予が45分であること(self):
        self.assertEqual(self.設定.復帰後の猶予分, 45)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#スリープ復帰直後の誤検知防止-2
    def test_復帰後の猶予が停滞判定のしきい値と揃っていること(self):
        """猶予が閾値より短いと、復帰直後の判定が実質的に素通りになる。
        要件は値を「停滞判定の閾値と揃える」ことで定めているため、関係として検証する。
        """
        self.assertEqual(self.設定.復帰後の猶予分, self.設定.停滞判定しきい値分)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#再起動の回数制限-4
    def test_復旧確認のしきい値が30分であること(self):
        self.assertEqual(self.設定.復旧確認しきい値分, 30)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#再起動の回数制限-3
    def test_再起動が直近24時間で2回までであること(self):
        self.assertEqual(self.設定.再起動の24時間上限, 2)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#通知の抑止と限界-1
    def test_再通知の間隔が24時間であること(self):
        self.assertEqual(self.設定.再通知間隔時間, 24)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#同期停滞の判定バッチ毎サイクルの冒頭
    def test_疎通確認のタイムアウトが5秒であること(self):
        self.assertEqual(self.設定.疎通タイムアウト秒, 5)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#onedriveの再起動と復旧確認バッチ
    def test_onedriveの通常終了を待つ時間が30秒であること(self):
        self.assertEqual(self.設定.通常終了を待つ秒, 30)


class 監視で使うパスの導出(unittest.TestCase):
    """監視で使うファイルの置き場が、仕様どおりの場所に導かれることを検証する。

    ハートビートは「取得バッチが監視しているのと同じ同期経路」にあることが
    検知の前提であり、監視記録は「停滞中でも読み書きできる」ことが要件のため、
    それぞれ置き場所そのものが仕様になっている。
    """

    def setUp(self):
        self.作業フォルダ = Path("/tmp/dummy-root/auto/transcript")
        self.設定 = config.load(作業フォルダ=self.作業フォルダ)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#ハートビートの書き込み-2
    def test_ハートビートファイルが作業フォルダ直下に導出されること(self):
        self.assertEqual(
            self.設定.ハートビートファイル, self.作業フォルダ / "_heartbeat.txt"
        )

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#監視通知-1
    def test_監視通知フォルダが作業フォルダの親のteamsnotice配下に導出されること(self):
        self.assertEqual(
            self.設定.監視通知フォルダ,
            self.作業フォルダ.parent / "teamsNotice" / "monitoring",
        )

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#記録-2
    def test_監視記録ファイルが作業フォルダの外に置かれること(self):
        """同期停滞の最中でも読み書きできる必要があるため、同期フォルダの外が要件。"""
        self.assertFalse(
            self.設定.監視記録ファイル.is_relative_to(self.作業フォルダ),
            f"{self.設定.監視記録ファイル} が作業フォルダ配下にある(停滞中に読み書きできない)",
        )
        self.assertEqual(self.設定.監視記録ファイル.name, "monitoring.json")


if __name__ == "__main__":
    unittest.main()
