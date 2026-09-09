"""設定モジュール(tasks.md 1)のテスト。

台帳フォルダ・通知フォルダ・作業フォルダの位置、待ち時間の上限、既定の探索条件は
いずれも仕様で根拠付きに決められた値なので、既定値と環境変数による差し替えを固定する。
"""

import json
import os
import tempfile
import unittest
from datetime import time
from pathlib import Path
from unittest import mock

import config


class 台帳と通知と作業のフォルダ(unittest.TestCase):
    """依頼・候補・選択結果・作成結果が用途ごとに別のフォルダへ分かれ、通知フォルダが
    台帳から分かれていることを検証する。同じファイルを双方から書かない・通知フローが
    台帳を誤検知しないための土台。
    """

    def setUp(self):
        self.設定 = config.load(environ={})

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#台帳ファイルの扱い-1
    def test_台帳の7種類のフォルダが台帳ルートの直下に用途別に分かれていること(self):
        root = self.設定.台帳ルート
        self.assertEqual(self.設定.依頼フォルダ, root / "request")
        self.assertEqual(self.設定.候補フォルダ, root / "candidates")
        self.assertEqual(self.設定.予定詳細依頼フォルダ, root / "detailRequest")
        self.assertEqual(self.設定.予定詳細フォルダ, root / "detail")
        self.assertEqual(self.設定.選択結果フォルダ, root / "selection")
        self.assertEqual(self.設定.作成結果フォルダ, root / "result")
        self.assertEqual(self.設定.htmlフォルダ, root / "html")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#台帳ファイルの扱い-1
    def test_台帳ルートの既定がOneDrive同期フォルダのmeetingSettingであること(self):
        self.assertEqual(self.設定.台帳ルート.name, "meetingSetting")
        self.assertIn("OneDrive", str(self.設定.台帳ルート))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#台帳ファイルの扱い-4
    def test_通知フォルダが台帳ルートの外にあること(self):
        通知 = self.設定.通知フォルダ
        self.assertNotIn(self.設定.台帳ルート, 通知.parents)
        self.assertEqual(通知.name, "meetingSetting")
        self.assertEqual(通知.parent.name, "teamsNotice")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-1
    def test_作業フォルダが同期フォルダの外のApplication_Support配下であること(self):
        self.assertEqual(
            self.設定.作業フォルダ,
            Path.home() / "Library/Application Support/meeting-setup-automation",
        )
        self.assertEqual(self.設定.名簿ファイル, self.設定.作業フォルダ / "roster.json")
        self.assertEqual(self.設定.ログファイル, self.設定.作業フォルダ / "meeting-setup.log")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#1-設定モジュールconfigpy
    def test_環境変数で台帳ルートと通知フォルダと作業フォルダを差し替えられること(self):
        設定 = config.load(
            environ={
                config.台帳ルート環境変数: "/tmp/x/ledger",
                config.通知フォルダ環境変数: "/tmp/x/notice",
                config.作業フォルダ環境変数: "/tmp/x/work",
            }
        )
        self.assertEqual(設定.台帳ルート, Path("/tmp/x/ledger"))
        self.assertEqual(設定.依頼フォルダ, Path("/tmp/x/ledger/request"))
        self.assertEqual(設定.通知フォルダ, Path("/tmp/x/notice"))
        self.assertEqual(設定.作業フォルダ, Path("/tmp/x/work"))


class 待ち時間の上限と間隔(unittest.TestCase):
    """3つの待ちの上限が別々の設定値として存在し、既定がいずれも5分であることを検証する。
    実測で別の値になりうるため、1つの値を共用しない。
    """

    def setUp(self):
        self.設定 = config.load(environ={})

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち時間の上限-1
    def test_候補と予定詳細と作成結果の待ち上限の既定がいずれも5分であること(self):
        self.assertEqual(self.設定.候補待ち上限秒, 300)
        self.assertEqual(self.設定.予定詳細待ち上限秒, 300)
        self.assertEqual(self.設定.作成結果待ち上限秒, 300)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち時間の上限-2
    def test_3つの待ち上限を環境変数で別々に上書きできること(self):
        設定 = config.load(
            environ={
                config.候補待ち上限環境変数: "10",
                config.予定詳細待ち上限環境変数: "20",
                config.作成結果待ち上限環境変数: "30",
            }
        )
        self.assertEqual(設定.候補待ち上限秒, 10)
        self.assertEqual(設定.予定詳細待ち上限秒, 20)
        self.assertEqual(設定.作成結果待ち上限秒, 30)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#往復の待ち合わせと打ち切り
    def test_確認間隔の既定が5秒で同期の猶予の既定が30秒であること(self):
        self.assertEqual(self.設定.確認間隔秒, 5)
        self.assertEqual(self.設定.同期猶予秒, 30)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#1-設定モジュールconfigpy
    def test_確認間隔と同期の猶予を環境変数で上書きできること(self):
        設定 = config.load(
            environ={config.確認間隔環境変数: "1", config.同期猶予環境変数: "0"}
        )
        self.assertEqual(設定.確認間隔秒, 1)
        self.assertEqual(設定.同期猶予秒, 0)

    def test_環境変数が数値として読めない場合は設定エラーになること(self):
        with self.assertRaises(config.設定エラー):
            config.load(environ={config.確認間隔環境変数: "five"})


class 既定の探索条件と代替案の条件(unittest.TestCase):
    """依頼で指定がない項目に使う既定値と、候補が0件のときに広げる条件を固定する。"""

    def setUp(self):
        self.設定 = config.load(environ={})

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補探索の既定条件-1
    def test_既定の期間が2週間で時間帯が9時30分から17時30分で候補件数が5件であること(self):
        self.assertEqual(self.設定.既定の探索期間日数, 14)
        self.assertEqual(self.設定.既定の時間帯開始, time(9, 30))
        self.assertEqual(self.設定.既定の時間帯終了, time(17, 30))
        self.assertEqual(self.設定.既定の候補件数, 5)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#依頼ファイルの区分
    def test_出席可能率の下限の既定が100でフローに返させる最大件数が50件であること(self):
        self.assertEqual(self.設定.既定の出席可能率下限, 100)
        self.assertEqual(self.設定.フローに返させる最大件数, 50)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補探索の既定条件-2
    def test_既定の対象曜日が月曜から金曜であること(self):
        self.assertEqual(self.設定.既定の対象曜日, (0, 1, 2, 3, 4))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-1
    def test_代替案2の期間が3週間で時間帯が9時30分から18時30分であること(self):
        self.assertEqual(self.設定.代替案の探索期間日数, 21)
        self.assertEqual(self.設定.代替案の時間帯開始, time(9, 30))
        self.assertEqual(self.設定.代替案の時間帯終了, time(18, 30))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#依頼内容の受け付け条件-3
    def test_探索期間の終了日の上限が代替案の期間と同じ3週間であること(self):
        self.assertEqual(self.設定.探索期間の上限日数, self.設定.代替案の探索期間日数)


class 選択画面のビューア設定(unittest.TestCase):
    """選択画面をブラウザで開く形式のURLを組み立てるための設定を、作業フォルダの設定ファイルと
    環境変数から読めることを検証する。個人のテナントURLをリポジトリに置かないための設計。
    """

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-6
    def test_作業フォルダのsettingsjsonからビューアURLとサーバー相対パスを読むこと(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "settings.json").write_text(
                json.dumps(
                    {
                        "output_web_viewer": "https://example-my.sharepoint.com/personal/u/_layouts/15/onedrive.aspx",
                        "output_web_dir": "/personal/u/Documents/00_root/auto/meetingSetting/html",
                    }
                ),
                encoding="utf-8",
            )
            設定 = config.load(environ={config.作業フォルダ環境変数: d})
        self.assertEqual(
            設定.ビューアurl,
            "https://example-my.sharepoint.com/personal/u/_layouts/15/onedrive.aspx",
        )
        self.assertEqual(設定.サーバー相対パス, "/personal/u/Documents/00_root/auto/meetingSetting/html")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#1-設定モジュールconfigpy
    def test_環境変数が設定ファイルより優先されること(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "settings.json").write_text(
                json.dumps({"output_web_viewer": "https://file/", "output_web_dir": "/file"}),
                encoding="utf-8",
            )
            設定 = config.load(
                environ={
                    config.作業フォルダ環境変数: d,
                    config.ビューアurl環境変数: "https://env/",
                    config.サーバー相対パス環境変数: "/env",
                }
            )
        self.assertEqual(設定.ビューアurl, "https://env/")
        self.assertEqual(設定.サーバー相対パス, "/env")

    def test_設定ファイルも環境変数も無い場合はビューア設定が空であること(self):
        with tempfile.TemporaryDirectory() as d:
            設定 = config.load(environ={config.作業フォルダ環境変数: d})
        self.assertIsNone(設定.ビューアurl)
        self.assertIsNone(設定.サーバー相対パス)


if __name__ == "__main__":
    unittest.main()
