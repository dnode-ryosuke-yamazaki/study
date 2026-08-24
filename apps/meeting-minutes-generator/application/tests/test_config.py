"""設定値とパスの解決(タスク1)のテスト。"""

import unittest
from pathlib import Path
from unittest import mock

import config


class 作業フォルダの決定(unittest.TestCase):
    """入出力フォルダの導出元になる作業フォルダを、テストや同期先名の異なる環境で
    差し替えられることを検証する。実物のOneDrive同期フォルダにテストが触れると
    Power Automateフローが検知して誤投稿につながるため、差し替え手段が必須。
    """

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#関連するファイル抜粋
    def test_引数で渡した作業フォルダが最優先で使われること(self):
        設定 = config.load(作業フォルダ=Path("/tmp/minutes-test"))
        self.assertEqual(設定.作業フォルダ, Path("/tmp/minutes-test"))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#関連するファイル抜粋
    def test_環境変数で作業フォルダを差し替えられること(self):
        with mock.patch.dict(
            "os.environ", {config.作業フォルダ環境変数: "/tmp/minutes-env"}
        ):
            設定 = config.load()
        self.assertEqual(設定.作業フォルダ, Path("/tmp/minutes-env"))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#onedriveフォルダの使い方-1
    def test_環境変数が無い場合はOneDriveのauto配下が既定になること(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            設定 = config.load()
        self.assertTrue(str(設定.作業フォルダ).endswith("00_root/auto"))


class 入出力フォルダの導出(unittest.TestCase):
    """各フォルダが作業フォルダから一意に導出されることを検証する。

    個別設定にすると、上流(teams-transcript-fetcher)との受け渡し場所や
    Power Automateフローの検知フォルダとずれる事故が起こるため。
    """

    def setUp(self):
        self.設定 = config.load(作業フォルダ=Path("/tmp/auto"))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#新規トランスクリプトの検知-1
    def test_入力フォルダが上流の成果物フォルダであること(self):
        self.assertEqual(self.設定.入力フォルダ, Path("/tmp/auto/transcript/vtt"))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の生成-3
    def test_議事録フォルダがauto配下の専用サブフォルダであること(self):
        self.assertEqual(self.設定.議事録フォルダ, Path("/tmp/auto/minutes"))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#teamsへの共有-1
    def test_投稿フォルダがteamsNotice配下の専用サブフォルダであること(self):
        self.assertEqual(self.設定.投稿フォルダ, Path("/tmp/auto/teamsNotice/minutesNotice"))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#状態管理
    def test_状態ファイルとロックが同期フォルダの外に置かれること(self):
        self.assertNotIn("/tmp/auto", str(self.設定.状態ファイル))
        self.assertNotIn("/tmp/auto", str(self.設定.ロックファイル))
        self.assertEqual(self.設定.状態ファイル.parent, self.設定.ロックファイル.parent)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#関連するファイル抜粋
    def test_環境変数で状態フォルダも差し替えられること(self):
        """テスト・手元実行が実物の状態ファイルを汚すと、実運用の初回判定
        (初回=既存VTTを生成しない)が壊れるため、状態側にも差し替え手段を持つ。
        """
        with mock.patch.dict(
            "os.environ", {config.状態フォルダ環境変数: "/tmp/minutes-state"}
        ):
            設定 = config.load(作業フォルダ=Path("/tmp/auto"))
        self.assertEqual(設定.状態ファイル, Path("/tmp/minutes-state/state.json"))


class 仕様で決められた既定値(unittest.TestCase):
    """仕様承認PRで確定した数値が設定に反映されていることを検証する。"""

    def setUp(self):
        self.設定 = config.load(作業フォルダ=Path("/tmp/auto"))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#定期実行と未処理vttの検知
    def test_実行間隔が10分であること(self):
        self.assertEqual(self.設定.実行間隔秒, 600)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#議事録の生成
    def test_生成タイムアウトが15分であること(self):
        self.assertEqual(self.設定.生成タイムアウト秒, 900)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の生成-5
    def test_再試行上限が3回であること(self):
        self.assertEqual(self.設定.再試行上限, 3)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#定期実行と未処理vttの検知
    def test_古いロックを無効とみなす時間が30分であること(self):
        self.assertEqual(self.設定.ロックを無効とみなす秒, 1800)


class デイリー系の判定語(unittest.TestCase):
    """会議種別の判定に使う語を設定として持ち、環境変数で変えられることを検証する。"""

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#会議種別による構成の切り替え-1
    def test_既定の判定語にデイリーとdailyが含まれること(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            判定語 = config.load(作業フォルダ=Path("/tmp/x"), 状態フォルダ=Path("/tmp/y")).デイリー判定語
        self.assertIn("デイリー", 判定語)
        self.assertIn("daily", 判定語)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#会議種別による構成の切り替え-1
    def test_環境変数でカンマ区切りの判定語に差し替えられること(self):
        with mock.patch.dict(
            "os.environ", {config.判定語環境変数: "定例, スタンドアップ"}, clear=True
        ):
            判定語 = config.load(作業フォルダ=Path("/tmp/x"), 状態フォルダ=Path("/tmp/y")).デイリー判定語
        self.assertEqual(判定語, ("定例", "スタンドアップ"))


class 議事録全文へのリンクの設定(unittest.TestCase):
    """Teams投稿に載せるリンクの組み立て元を設定として持つことを検証する。

    共有ストレージのファイルを直接指すURLはダウンロードになるため、
    ビューアで開く形式のURLを組み立てる必要がある。
    """

    def setUp(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.設定 = config.load(作業フォルダ=Path("/tmp/x"), 状態フォルダ=Path("/tmp/y"))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録全文へのリンク-2
    def test_既定でビューアURLと作業フォルダのWebパスを持つこと(self):
        self.assertIn("sharepoint.com", self.設定.ビューアURL)
        self.assertTrue(self.設定.作業フォルダのWebパス.startswith("/"))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録全文へのリンク-2
    def test_議事録フォルダのWebパスが作業フォルダから導かれること(self):
        self.assertEqual(
            self.設定.議事録フォルダのWebパス, f"{self.設定.作業フォルダのWebパス}/minutes"
        )

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録全文へのリンク-2
    def test_環境変数でビューアURLとWebパスを差し替えられること(self):
        with mock.patch.dict(
            "os.environ",
            {
                config.ビューア環境変数: "https://example.sharepoint.com/_layouts/15/onedrive.aspx",
                config.Webパス環境変数: "/personal/me/Documents/auto/",
            },
            clear=True,
        ):
            設定 = config.load(作業フォルダ=Path("/tmp/x"), 状態フォルダ=Path("/tmp/y"))
        self.assertEqual(
            設定.ビューアURL, "https://example.sharepoint.com/_layouts/15/onedrive.aspx"
        )
        # 前後のスラッシュは吸収する(アドレスバーからのコピーを想定)
        self.assertEqual(設定.議事録フォルダのWebパス, "/personal/me/Documents/auto/minutes")


if __name__ == "__main__":
    unittest.main()
