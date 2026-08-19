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
                "host": {
                    "apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
                    "connectionName": "shared_sharepointonline",
                    "operationId": "HttpRequest",
                },
                "authentication": "@parameters('$authentication')",
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
                "host": {
                    "apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
                    "connectionName": "shared_sharepointonline",
                    "operationId": "CreateFile",
                },
                "authentication": "@parameters('$authentication')",
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

    トリガー = {
        "ファイルが作成されたとき_(プロパティのみ)": {
            "recurrence": {"frequency": "Minute", "interval": 1},
            "type": "OpenApiConnection",
            "inputs": {
                "parameters": {
                    "dataset": "https://example.sharepoint.com/sites/Team",
                    "table": "Documents",
                    "folderPath": "/Shared Documents",
                },
                "host": {
                    "apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
                    "connectionName": "shared_sharepointonline",
                    "operationId": "GetOnNewFileItems",
                },
                "authentication": "@parameters('$authentication')",
            },
        }
    }
    return {
        "properties": {
            "displayName": "トランスクリプト取得",
            "definition": {"triggers": トリガー, "actions": 外側},
        }
    }


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


class フロー2の生成(unittest.TestCase):
    """フロー①の定義からフロー②(ダウンロードURLの発行)を作れることを検証する。

    新規に書き起こすのではなくフロー①を土台にする。接続・HTTP呼び出し・URL一覧の
    取り出しがそのまま使えるため間違いが少ない。
    """

    def setUp(self):
        self.フロー2, self.変更点 = patch.フロー2を作る(
            元の定義を作る(条件で囲む=True, ハードコードした呼び出しあり=False),
            作業サイト=台帳の保存先サイト,
            要求フォルダ="/Documents/00_root/auto/transcript/request",
            urlフォルダ="/Documents/00_root/auto/transcript/url",
            フロー名="トランスクリプトURL発行",
        )
        self.アクション = self.フロー2["properties"]["definition"]["actions"]

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ダウンロードurlの発行power-automate-フロー②フェーズ2
    def test_トリガーが要求置き場を監視すること(self):
        トリガー = next(iter(self.フロー2["properties"]["definition"]["triggers"].values()))
        self.assertEqual(
            トリガー["inputs"]["parameters"]["folderPath"],
            "/Documents/00_root/auto/transcript/request",
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ダウンロードurlの発行power-automate-フロー②フェーズ2
    def test_要求の中身を読んで解析すること(self):
        """トリガー(プロパティのみ)は中身をくれないため、読む処理が必要。"""
        self.assertIn(patch.アクション_要求の中身, self.アクション)
        self.assertEqual(self.アクション[patch.アクション_要求の解析]["type"], "ParseJson")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ファイルの項目名の取り決め
    def test_解析の形が要求の項目名と一致すること(self):
        形 = self.アクション[patch.アクション_要求の解析]["inputs"]["schema"]["properties"]
        for 項目 in ("siteUrl", "driveId", "recordingId", "createdAt"):
            with self.subTest(項目=項目):
                self.assertIn(項目, 形)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ダウンロードurlの発行power-automate-フロー②フェーズ2
    def test_一覧取得が要求の識別子を使うこと(self):
        """要求だけで発行できるようにしてあるので、台帳を読む必要がない。"""
        uri = self.アクション[patch.アクション_一覧取得]["inputs"]["parameters"][
            "parameters/uri"
        ]
        self.assertIn(patch.アクション_要求の解析, uri)
        self.assertNotIn("triggerOutputs", uri)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ダウンロードurlの発行要求-4
    def test_一覧全件を配列にすること(self):
        self.assertEqual(self.アクション[patch.アクション_url一覧]["type"], "Select")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ダウンロードurlの発行power-automate-フロー②フェーズ2
    def test_一覧が空のときはurlファイルを作らないこと(self):
        """台帳が残り、次回また要求される。空のURLファイルを作ると
        「発行済みだが取得できない」という紛らわしい状態になる。
        """
        条件 = self.アクション[patch.アクション_条件]
        self.assertEqual(条件["type"], "If")
        self.assertIn(patch.アクション_ファイルの作成, 条件["actions"])
        self.assertEqual(条件["else"]["actions"], {})

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#識別子とファイル名の規則唯一の定義
    def test_urlファイルの名前が録画の識別子になること(self):
        パラメータ = self.アクション[patch.アクション_条件]["actions"][
            patch.アクション_ファイルの作成
        ]["inputs"]["parameters"]
        self.assertIn(patch.アクション_要求の解析, パラメータ["name"])
        self.assertTrue(パラメータ["name"].endswith(".json"))
        self.assertEqual(パラメータ["folderPath"], "/Documents/00_root/auto/transcript/url")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ダウンロードurlの発行power-automate-フロー②フェーズ2
    def test_処理後に要求を削除すること(self):
        削除 = self.アクション[patch.アクション_要求の削除]
        self.assertEqual(削除["inputs"]["host"]["operationId"], "DeleteFile")
        self.assertIn(patch.アクション_条件, 削除["runAfter"])

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ダウンロードurlの発行要求-5
    def test_条件が失敗したら要求を削除しないこと(self):
        """削除してしまうと、その録画は要求済み扱いのまま永久に再要求されない。
        残しておけばバッチが滞留として退避し、対象が解放される。
        """
        self.assertEqual(
            self.アクション[patch.アクション_要求の削除]["runAfter"][patch.アクション_条件],
            ["Succeeded"],
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ダウンロードurlの発行power-automate-フロー②フェーズ2
    def test_接続の設定がフロー1から引き継がれること(self):
        """新しい接続を作らせないため、コネクタの指定をそのまま使う。"""
        ホスト = self.アクション[patch.アクション_一覧取得]["inputs"]["host"]
        self.assertIn("sharepointonline", ホスト["connectionName"])

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ダウンロードurlの発行power-automate-フロー②フェーズ2
    def test_台帳を作るアクションが残っていないこと(self):
        """フロー②は台帳を作らない。フロー①の残骸が動くと台帳が二重にできる。"""
        self.assertNotIn(patch.アクション_変数を初期化, self.アクション)
        条件の中 = self.アクション[patch.アクション_条件]["actions"]
        # 「台帳を組み立てる」という名前はURLファイルの内容作成に流用している。
        中身 = 条件の中[patch.アクション_台帳]["inputs"]
        self.assertNotIn("meetingName", 中身)
        self.assertIn("urls", 中身)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ダウンロードurlの発行power-automate-フロー②フェーズ2
    def test_条件の中のアクションが条件の外を参照しないこと(self):
        """Power Automateでは条件の中のアクションは条件の中しか参照できない。

        外を参照するとインポート時に「must belong to same level」で拒否される。
        実際にこれでインポートが失敗した(2026-08-19)。
        """
        条件の中 = self.アクション[patch.アクション_条件]["actions"]
        for 名前, 中身 in 条件の中.items():
            with self.subTest(アクション=名前):
                for 参照先 in (中身.get("runAfter") or {}):
                    self.assertIn(
                        参照先,
                        条件の中,
                        f"{名前} が条件の外の {参照先} を参照している",
                    )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#ダウンロードurlの発行power-automate-フロー②フェーズ2
    def test_条件の外のアクションが条件の中を参照しないこと(self):
        """逆方向も同じ制約。こちらも「same level」で拒否される。"""
        条件の中 = set(self.アクション[patch.アクション_条件]["actions"])
        for 名前, 中身 in self.アクション.items():
            if 名前 == patch.アクション_条件:
                continue
            with self.subTest(アクション=名前):
                for 参照先 in (中身.get("runAfter") or {}):
                    self.assertNotIn(参照先, 条件の中)

    def test_フロー名が指定したものになること(self):
        self.assertEqual(self.フロー2["properties"]["displayName"], "トランスクリプトURL発行")


if __name__ == "__main__":
    unittest.main()
