"""フロー定義の書き換えスクリプト(T22)のテスト。

実際のエクスポートには固有の識別子が含まれるため、テストは形だけを真似た
最小の定義で行う。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "power-automate"))

import patch_flow_definition as patch  # noqa: E402

台帳の保存先サイト = "https://example-my.sharepoint.com/personal/dummy"
台帳フォルダ = "/Documents/00_root/auto/transcript/ledger"


def 元の定義を作る(*, 条件で囲む: bool, ハードコードした呼び出しあり: bool) -> dict:
    """エクスポートされた定義の形だけを真似たもの。"""
    アクション = {
        patch.アクション_一覧取得: {
            "type": "OpenApiConnection",
            "runAfter": {},
            "inputs": {
                "parameters": {
                    "dataset": "https://example.sharepoint.com/sites/Team",
                    "parameters/method": "GET",
                    "parameters/uri": (
                        "_api/v2.1/drives/b!DUMMYDRIVE/items/"
                        f"@{{body('{patch.アクション_driveitemid取得}')?['id']}}"
                        "/media/transcripts"
                    ),
                }
            },
        },
        patch.アクション_作成: {
            "type": "Compose",
            "runAfter": {patch.アクション_一覧取得: ["Succeeded"]},
            "inputs": (
                f"@body('{patch.アクション_一覧取得}')?['value'][0]"
                "?['temporaryDownloadUrl']"
            ),
        },
        patch.アクション_ファイルの作成: {
            "type": "OpenApiConnection",
            "runAfter": {patch.アクション_作成: ["Succeeded"]},
            "inputs": {
                "parameters": {
                    "dataset": "https://example.sharepoint.com/sites/Team",
                    "folderPath": "/Shared Documents/テストチャネル/temporaryDownloadUrl",
                    "name": "@{triggerBody()?['{Name}']}.txt",
                    "body": f"@outputs('{patch.アクション_作成}')",
                }
            },
        },
    }
    if ハードコードした呼び出しあり:
        アクション[patch.アクション_driveid取得] = {"type": "OpenApiConnection", "inputs": {}}
        アクション[patch.アクション_driveitemid取得] = {
            "type": "OpenApiConnection",
            "inputs": {},
        }

    外側 = {patch.アクション_変数を初期化: {"type": "InitializeVariable", "inputs": {}}}
    if 条件で囲む:
        外側[patch.アクション_条件] = {"type": "If", "actions": アクション, "else": {"actions": {}}}
    else:
        外側.update(アクション)

    return {"properties": {"definition": {"actions": 外側}}}


class 一覧全件を取り出す変更(unittest.TestCase):
    """先頭1件だけを取る作りから、一覧全件を配列にする作りへ変わることを検証する。

    元のフローは `value[0]` で先頭しか見ておらず、1つの会議に複数の
    トランスクリプトがある場合に取りこぼす。
    """

    def setUp(self):
        self.書き換え後, _ = patch.書き換える(
            元の定義を作る(条件で囲む=True, ハードコードした呼び出しあり=False),
            由来="channel",
            台帳の保存先サイト=台帳の保存先サイト,
            台帳フォルダ=台帳フォルダ,
        )
        self.入れ物 = patch._アクションの入れ物を探す(self.書き換え後)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#既存フローに見つかった制約
    def test_先頭1件だけを取り出すアクションが削除されること(self):
        self.assertNotIn(patch.アクション_作成, self.入れ物)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#トランスクリプトの列挙-2
    def test_一覧全件を配列にするアクションが追加されること(self):
        追加された = self.入れ物[patch.アクション_url一覧]
        self.assertEqual(追加された["type"], "Select")
        self.assertIn("temporaryDownloadUrl", 追加された["inputs"]["select"])

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#台帳の作成power-automate側-5
    def test_一覧の取得が失敗しても後続へ進むこと(self):
        """一覧が空でも台帳を作る必要がある。ここで止まるとその録画が
        永久に対象外になる。
        """
        条件 = self.入れ物[patch.アクション_url一覧]["runAfter"][patch.アクション_一覧取得]
        self.assertIn("Failed", 条件)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#台帳の作成power-automate側-5
    def test_一覧が空の場合に空配列へ落ちること(self):
        self.assertIn("coalesce", self.入れ物[patch.アクション_url一覧]["inputs"]["from"])


class 台帳の内容と保存先の変更(unittest.TestCase):
    """保存内容が台帳になり、保存先が個人OneDriveへ変わることを検証する。

    項目名がバッチ側とずれると、例外ではなく「対象が見つからない」という
    静かな失敗になる。
    """

    def setUp(self):
        self.書き換え後, _ = patch.書き換える(
            元の定義を作る(条件で囲む=True, ハードコードした呼び出しあり=False),
            由来="channel",
            台帳の保存先サイト=台帳の保存先サイト,
            台帳フォルダ=台帳フォルダ,
        )
        self.入れ物 = patch._アクションの入れ物を探す(self.書き換え後)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ファイルの項目名の取り決め
    def test_台帳の必須項目がすべて含まれること(self):
        中身 = self.入れ物[patch.アクション_台帳]["inputs"]
        for 項目 in ("meetingName", "siteUrl", "driveId", "recordingId"):
            with self.subTest(項目=項目):
                self.assertTrue(中身.get(項目))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ファイルの項目名の取り決め
    def test_台帳に発行時刻とurl一覧と由来が含まれること(self):
        中身 = self.入れ物[patch.アクション_台帳]["inputs"]
        self.assertIn("utcNow", 中身["issuedAt"])
        self.assertIn(patch.アクション_url一覧, 中身["urls"])
        self.assertEqual(中身["source"], "channel")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#台帳の作成power-automate側-4
    def test_保存先が指定した個人onedriveの台帳置き場になること(self):
        パラメータ = self.入れ物[patch.アクション_ファイルの作成]["inputs"]["parameters"]
        self.assertEqual(パラメータ["dataset"], 台帳の保存先サイト)
        self.assertEqual(パラメータ["folderPath"], 台帳フォルダ)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#識別子とファイル名の規則唯一の定義
    def test_ファイル名が録画の識別子とjson拡張子になること(self):
        名前 = self.入れ物[patch.アクション_ファイルの作成]["inputs"]["parameters"]["name"]
        self.assertTrue(名前.endswith(".json"))
        self.assertNotEqual(名前, ".json", "識別子が空だとファイル名が拡張子だけになる")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ファイルの項目名の取り決め
    def test_保存する本文が台帳の文字列になること(self):
        本文 = self.入れ物[patch.アクション_ファイルの作成]["inputs"]["parameters"]["body"]
        self.assertIn(patch.アクション_台帳, 本文)


class 識別子の取り方をフローごとに保つ(unittest.TestCase):
    """元のフローが動いていた識別子の取り方を変えないことを検証する。

    個人OneDriveのトリガーは {DriveId} / {DriveItemId} を提供せず、これらを
    使うと空文字になる(2026-08-19に実機で確認)。元の通常会議用フローが
    ファイル名から項目を検索していたのはそのためだった。**簡素化して壊した
    ことがあるので、動いていた方式を保つ。**
    """

    def _書き換える(self, *, 項目検索あり: bool, 由来: str):
        return patch.書き換える(
            元の定義を作る(条件で囲む=True, ハードコードした呼び出しあり=項目検索あり),
            由来=由来,
            台帳の保存先サイト=台帳の保存先サイト,
            台帳フォルダ=台帳フォルダ,
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#既存フローに見つかった制約
    def test_項目検索の呼び出しがあれば保たれること(self):
        """通常会議用フロー。この呼び出しの結果が録画の識別子になる。"""
        書き換え後, _ = self._書き換える(項目検索あり=True, 由来="personal")
        入れ物 = patch._アクションの入れ物を探す(書き換え後)
        self.assertIn(patch.アクション_driveitemid取得, 入れ物)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#既存フローに見つかった制約
    def test_結果を使っていない呼び出しだけが削除されること(self):
        書き換え後, _ = self._書き換える(項目検索あり=True, 由来="personal")
        入れ物 = patch._アクションの入れ物を探す(書き換え後)
        self.assertNotIn(patch.アクション_driveid取得, 入れ物)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ファイルの項目名の取り決め
    def test_項目検索方式では検索結果が録画の識別子になること(self):
        書き換え後, _ = self._書き換える(項目検索あり=True, 由来="personal")
        入れ物 = patch._アクションの入れ物を探す(書き換え後)
        中身 = 入れ物[patch.アクション_台帳]["inputs"]
        self.assertIn(patch.アクション_driveitemid取得, 中身["recordingId"])
        # トリガーの値は参照しない(個人OneDriveのトリガーは提供しないため)。
        self.assertNotIn("triggerOutputs", 中身["recordingId"])

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ファイルの項目名の取り決め
    def test_項目検索方式ではドライブ識別子が元の定義から読み取られること(self):
        """値そのものはリポジトリに書かず、元の定義から取り出す。"""
        書き換え後, _ = self._書き換える(項目検索あり=True, 由来="personal")
        入れ物 = patch._アクションの入れ物を探す(書き換え後)
        self.assertEqual(入れ物[patch.アクション_台帳]["inputs"]["driveId"], "b!DUMMYDRIVE")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ファイルの項目名の取り決め
    def test_項目検索方式では一覧取得のuriを変更しないこと(self):
        """元のURIが動いていたので触らない。"""
        元の定義 = 元の定義を作る(条件で囲む=True, ハードコードした呼び出しあり=True)
        元のuri = patch._アクションの入れ物を探す(元の定義)[patch.アクション_一覧取得][
            "inputs"
        ]["parameters"]["parameters/uri"]
        書き換え後, _ = patch.書き換える(
            元の定義,
            由来="personal",
            台帳の保存先サイト=台帳の保存先サイト,
            台帳フォルダ=台帳フォルダ,
        )
        入れ物 = patch._アクションの入れ物を探す(書き換え後)
        self.assertEqual(
            入れ物[patch.アクション_一覧取得]["inputs"]["parameters"]["parameters/uri"],
            元のuri,
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ファイルの項目名の取り決め
    def test_トリガー方式では識別子がトリガーの値になること(self):
        """チャネル会議用フロー。元のフローがこの方式で動いていた。"""
        書き換え後, _ = self._書き換える(項目検索あり=False, 由来="channel")
        入れ物 = patch._アクションの入れ物を探す(書き換え後)
        中身 = 入れ物[patch.アクション_台帳]["inputs"]
        self.assertIn("DriveId", 中身["driveId"])
        self.assertIn("DriveItemId", 中身["recordingId"])

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ファイルの項目名の取り決め
    def test_ファイル名が方式ごとの識別子から作られること(self):
        for 項目検索あり, 含まれるべき in ((True, patch.アクション_driveitemid取得), (False, "DriveItemId")):
            with self.subTest(項目検索あり=項目検索あり):
                書き換え後, _ = self._書き換える(
                    項目検索あり=項目検索あり, 由来="personal" if 項目検索あり else "channel"
                )
                入れ物 = patch._アクションの入れ物を探す(書き換え後)
                名前 = 入れ物[patch.アクション_ファイルの作成]["inputs"]["parameters"]["name"]
                self.assertIn(含まれるべき, 名前)
                self.assertTrue(名前.endswith(".json"))


class 条件で囲まれていない定義(unittest.TestCase):
    """アクションが条件の中に無い形でも書き換えられることを検証する。

    フローの作り方によって入れ物の位置が変わるため。
    """

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#録画の検知と台帳の作成power-automate-フロー①
    def test_条件がなくても書き換えられること(self):
        書き換え後, _ = patch.書き換える(
            元の定義を作る(条件で囲む=False, ハードコードした呼び出しあり=False),
            由来="personal",
            台帳の保存先サイト=台帳の保存先サイト,
            台帳フォルダ=台帳フォルダ,
        )
        入れ物 = patch._アクションの入れ物を探す(書き換え後)
        self.assertIn(patch.アクション_台帳, 入れ物)


class 想定と違う定義(unittest.TestCase):
    """想定したアクションが無い場合に、黙って壊れた定義を出さないことを検証する。

    気づかずインポートすると、動かない理由を追うのに時間がかかる。
    """

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/tasks.md
    def test_必要なアクションが無い場合に中断すること(self):
        定義 = 元の定義を作る(条件で囲む=True, ハードコードした呼び出しあり=False)
        del 定義["properties"]["definition"]["actions"][patch.アクション_条件]["actions"][
            patch.アクション_ファイルの作成
        ]
        with self.assertRaises(SystemExit):
            patch.書き換える(
                定義,
                由来="channel",
                台帳の保存先サイト=台帳の保存先サイト,
                台帳フォルダ=台帳フォルダ,
            )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/tasks.md
    def test_元の定義が変更されないこと(self):
        """元のエクスポートを壊さないため、書き換えは複製に対して行う。"""
        定義 = 元の定義を作る(条件で囲む=True, ハードコードした呼び出しあり=False)
        変更前の入れ物 = sorted(patch._アクションの入れ物を探す(定義))
        patch.書き換える(
            定義,
            由来="channel",
            台帳の保存先サイト=台帳の保存先サイト,
            台帳フォルダ=台帳フォルダ,
        )
        self.assertEqual(sorted(patch._アクションの入れ物を探す(定義)), 変更前の入れ物)


if __name__ == "__main__":
    unittest.main()
