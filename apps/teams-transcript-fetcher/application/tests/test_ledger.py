"""台帳の読み取りとバリデーション(tasks.md T7)のテスト。"""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import ledger


def 台帳の中身(**上書き) -> dict:
    """正常な台帳1件分の内容。テストごとに必要な項目だけ差し替える。"""
    中身 = {
        "meetingName": "定例会議.mp4",
        "siteUrl": "https://example.sharepoint.com/sites/Team",
        "driveId": "b!dummy-drive",
        "recordingId": "01ABCDEF",
        "recordingCreatedAt": "2026-08-19T10:30:00.000Z",
        "source": "channel",
        "issuedAt": "2026-08-19T10:31:12.345Z",
        "urls": ["https://example.com/one", "https://example.com/two"],
    }
    中身.update(上書き)
    return {キー: 値 for キー, 値 in 中身.items() if 値 is not ...}


class 台帳の読み取り(unittest.TestCase):
    """Power Automateが書いた台帳から、URLの発行に必要な情報が読めることを検証する。

    台帳はフローとバッチの受け渡し口であり、項目名がずれると例外ではなく
    「対象が見つからない」という静かな失敗になる。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.台帳フォルダ = Path(self.一時ディレクトリ.name)
        self.addCleanup(self.一時ディレクトリ.cleanup)

    def 台帳を置く(self, 名前: str, 中身) -> Path:
        パス = self.台帳フォルダ / 名前
        パス.write_text(
            中身 if isinstance(中身, str) else json.dumps(中身, ensure_ascii=False),
            encoding="utf-8",
        )
        return パス

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ファイルの項目名の取り決め
    def test_台帳から発行に必要な情報が読めること(self):
        self.台帳を置く("01ABCDEF.json", 台帳の中身())
        (台帳,) = ledger.台帳を読み込む(self.台帳フォルダ).有効
        self.assertEqual(台帳.会議名, "定例会議.mp4")
        self.assertEqual(台帳.サイトurl, "https://example.sharepoint.com/sites/Team")
        self.assertEqual(台帳.ドライブ識別子, "b!dummy-drive")
        self.assertEqual(台帳.録画の識別子, "01ABCDEF")
        self.assertEqual(台帳.由来, "channel")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#発行時刻の取り決め
    def test_録画の作成日時と発行時刻がutcの日時として読めること(self):
        self.台帳を置く("01ABCDEF.json", 台帳の中身())
        (台帳,) = ledger.台帳を読み込む(self.台帳フォルダ).有効
        self.assertEqual(
            台帳.録画の作成日時, datetime(2026, 8, 19, 10, 30, tzinfo=timezone.utc)
        )
        self.assertEqual(
            台帳.発行時刻,
            datetime(2026, 8, 19, 10, 31, 12, 345000, tzinfo=timezone.utc),
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ファイルの項目名の取り決め
    def test_urlの一覧が配列の順序どおりに読めること(self):
        """配列の添字が「一覧内の並び順」であり、トランスクリプトの識別に使う。"""
        self.台帳を置く("01ABCDEF.json", 台帳の中身())
        (台帳,) = ledger.台帳を読み込む(self.台帳フォルダ).有効
        self.assertEqual(
            台帳.url一覧, ["https://example.com/one", "https://example.com/two"]
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#台帳の作成power-automate側-5
    def test_urlを持たない台帳が読めること(self):
        """録画の作成時点でトランスクリプトが未生成だと、URLのない台帳が作られる。
        これを読み取りエラーにすると、その録画が永久に対象外になる。
        """
        self.台帳を置く("01ABCDEF.json", 台帳の中身(urls=[], issuedAt=...))
        (台帳,) = ledger.台帳を読み込む(self.台帳フォルダ).有効
        self.assertEqual(台帳.url一覧, [])
        self.assertIsNone(台帳.発行時刻)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-4
    def test_録画の作成日時がない場合はnoneになること(self):
        """後段(出力ファイル名の組み立て)が台帳ファイルの更新時刻で代用するため、
        欠けていることを区別できる必要がある。
        """
        self.台帳を置く("01ABCDEF.json", 台帳の中身(recordingCreatedAt=...))
        (台帳,) = ledger.台帳を読み込む(self.台帳フォルダ).有効
        self.assertIsNone(台帳.録画の作成日時)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-4
    def test_台帳ファイルの更新時刻が読めること(self):
        """録画の作成日時が欠けている場合の代用値として使う。"""
        パス = self.台帳を置く("01ABCDEF.json", 台帳の中身())
        (台帳,) = ledger.台帳を読み込む(self.台帳フォルダ).有効
        # 秒の小数はdatetimeへの変換で丸められるため、ミリ秒精度で比べる。
        self.assertAlmostEqual(台帳.更新時刻.timestamp(), パス.stat().st_mtime, places=3)


class 不正な台帳の扱い(unittest.TestCase):
    """壊れた台帳が処理を止めず、不正として仕分けられることを検証する。

    1件の不正で他の録画の処理が止まると、正常な会議のトランスクリプトまで
    取得できなくなる。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.台帳フォルダ = Path(self.一時ディレクトリ.name)
        self.addCleanup(self.一時ディレクトリ.cleanup)

    def 台帳を置く(self, 名前: str, 中身) -> Path:
        パス = self.台帳フォルダ / 名前
        パス.write_text(
            中身 if isinstance(中身, str) else json.dumps(中身, ensure_ascii=False),
            encoding="utf-8",
        )
        return パス

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#バリデーション
    def test_jsonとして解析できないファイルが不正として扱われること(self):
        self.台帳を置く("01ABCDEF.json", "{壊れている")
        結果 = ledger.台帳を読み込む(self.台帳フォルダ)
        self.assertEqual(結果.有効, [])
        self.assertEqual(len(結果.不正), 1)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#バリデーション
    def test_必須項目が欠けているファイルが不正として扱われること(self):
        for 欠ける項目 in ("meetingName", "siteUrl", "driveId", "recordingId"):
            with self.subTest(欠ける項目=欠ける項目):
                self.台帳を置く("01ABCDEF.json", 台帳の中身(**{欠ける項目: ...}))
                結果 = ledger.台帳を読み込む(self.台帳フォルダ)
                self.assertEqual(結果.有効, [])
                self.assertEqual(len(結果.不正), 1)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#バリデーション
    def test_不正な台帳に欠けている項目が分かること(self):
        """記録ファイルに原因を書くため、何が足りないのかを持ち出す必要がある。"""
        self.台帳を置く("01ABCDEF.json", 台帳の中身(siteUrl=...))
        (不正,) = ledger.台帳を読み込む(self.台帳フォルダ).不正
        self.assertIn("siteUrl", 不正.理由)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#バリデーション
    def test_1件が不正でも他の台帳は読めること(self):
        self.台帳を置く("01BROKEN.json", "{壊れている")
        self.台帳を置く("01ABCDEF.json", 台帳の中身())
        結果 = ledger.台帳を読み込む(self.台帳フォルダ)
        self.assertEqual([台帳.録画の識別子 for 台帳 in 結果.有効], ["01ABCDEF"])
        self.assertEqual(len(結果.不正), 1)


class 台帳置き場の走査(unittest.TestCase):
    """台帳置き場の列挙が、無関係なファイルや存在しないフォルダに耐えることを検証する。

    OneDriveの同期フォルダには一時ファイルや隠しファイルが現れることがあり、
    それらを台帳として読もうとすると毎回「不正」が積み上がる。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.台帳フォルダ = Path(self.一時ディレクトリ.name)
        self.addCleanup(self.一時ディレクトリ.cleanup)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#台帳の読み取りと使用するurlの一覧の決定バッチ
    def test_無関係な拡張子のファイルが無視されること(self):
        (self.台帳フォルダ / "メモ.txt").write_text("無関係", encoding="utf-8")
        (self.台帳フォルダ / ".DS_Store").write_text("無関係", encoding="utf-8")
        結果 = ledger.台帳を読み込む(self.台帳フォルダ)
        self.assertEqual(結果.有効, [])
        self.assertEqual(結果.不正, [])

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#台帳の読み取りと使用するurlの一覧の決定バッチ
    def test_台帳置き場が存在しない場合に区別できる形で返ること(self):
        """同期フォルダが見つからない場合は全体を中断する必要があるため、
        「台帳が0件」と「フォルダがない」を区別できなければならない。
        """
        with self.assertRaises(ledger.台帳置き場にアクセスできない):
            ledger.台帳を読み込む(self.台帳フォルダ / "存在しない")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#未取得の判定バッチ-3
    def test_読み取りが台帳ファイルを変更しないこと(self):
        """台帳に対して行うのは削除と退避のみ。読み取りで書き換えてはならない。"""
        パス = self.台帳フォルダ / "01ABCDEF.json"
        パス.write_text(json.dumps(台帳の中身(), ensure_ascii=False), encoding="utf-8")
        変更前 = パス.read_bytes()
        ledger.台帳を読み込む(self.台帳フォルダ)
        self.assertEqual(パス.read_bytes(), 変更前)


if __name__ == "__main__":
    unittest.main()
