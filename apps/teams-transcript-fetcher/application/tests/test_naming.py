"""識別子の規則と出力ファイル名の組み立て(tasks.md T2〜T6)のテスト。"""

import unittest
from datetime import datetime, timezone

import naming


class 録画の識別子とファイル名の対応(unittest.TestCase):
    """台帳とURLファイルの名前が、録画の識別子1つから導かれることを検証する。

    この規則はPower Automateフロー①・フロー②・バッチの3者が共有する唯一の
    取り決めであり、ずれても例外は出ず「URLが見つからない」だけで静かに壊れる。
    """

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#識別子とファイル名の規則唯一の定義
    def test_台帳のファイル名が録画の識別子から組み立てられること(self):
        self.assertEqual(naming.台帳ファイル名("01ABCDEF"), "01ABCDEF.json")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#識別子とファイル名の規則唯一の定義
    def test_urlファイルの名前が録画の識別子から組み立てられること(self):
        self.assertEqual(naming.urlファイル名("01ABCDEF"), "01ABCDEF.json")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#識別子とファイル名の規則唯一の定義
    def test_台帳のファイル名から録画の識別子が取り出せること(self):
        self.assertEqual(naming.台帳ファイル名から識別子("01ABCDEF.json"), "01ABCDEF")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#識別子とファイル名の規則唯一の定義
    def test_同じ録画の台帳とurlファイルが識別子を介して対応すること(self):
        """3者の共有点は録画の識別子だけである、という設計が満たされていることを固定する。"""
        識別子 = "01ABCDEF"
        取り出した識別子 = naming.台帳ファイル名から識別子(naming.台帳ファイル名(識別子))
        self.assertEqual(naming.urlファイル名(取り出した識別子), naming.urlファイル名(識別子))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#識別子とファイル名の規則唯一の定義
    def test_識別子が加工されずそのまま使われること(self):
        """規則は「加工せずそのまま使う」。大文字小文字や記号を勝手に正規化すると
        フロー側が作った名前と一致しなくなる。
        """
        識別子 = "01aB-cD_eF"
        self.assertTrue(naming.台帳ファイル名(識別子).startswith(識別子))


class 出力ファイル名の基本形(unittest.TestCase):
    """保存するトランスクリプトのファイル名が、会議名・時刻・連番から組み立てられることを検証する。

    定例会議は同じ会議名が繰り返されるため時刻が必要で、1つの録画に複数の
    トランスクリプトがあると会議名も時刻も同一になるため連番が必要になる。
    """

    def setUp(self):
        self.時刻 = datetime(2026, 8, 19, 10, 30, tzinfo=timezone.utc)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-1
    def test_会議名から録画の拡張子が除去されること(self):
        名前 = naming.出力ファイル名("定例会議.mp4", self.時刻, 1)
        self.assertTrue(名前.startswith("定例会議__"))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-1
    def test_中継ファイル由来の拡張子も除去されること(self):
        """既存フローは `<会議名>.mp4.txt` という名前でファイルを作っていたため、
        移行期の名前でも会議名だけが残るようにする。
        """
        名前 = naming.出力ファイル名("定例会議.mp4.txt", self.時刻, 1)
        self.assertTrue(名前.startswith("定例会議__"))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-3
    def test_時刻が分までの固定書式で含まれること(self):
        self.assertIn("20260819T1030", naming.出力ファイル名("定例会議", self.時刻, 1))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-5
    def test_連番が2桁で含まれること(self):
        self.assertIn("__01", naming.出力ファイル名("定例会議", self.時刻, 1))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-5
    def test_同じ会議名と時刻でも連番が違えば別のファイル名になること(self):
        """1つの録画に複数のトランスクリプトがある場合、会議名も時刻も同一になる。
        連番がないと互いに上書きしてしまう。
        """
        self.assertNotEqual(
            naming.出力ファイル名("定例会議", self.時刻, 1),
            naming.出力ファイル名("定例会議", self.時刻, 2),
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-5
    def test_トランスクリプトが1件でも連番が付くこと(self):
        """件数は後から増えうるため、1件目を連番なしで保存すると2件目が現れた
        ときに命名規則が変わり、既存ファイルとの整合が崩れる。
        """
        self.assertIn("__01", naming.出力ファイル名("定例会議", self.時刻, 1))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-3
    def test_トランスクリプトの拡張子が付くこと(self):
        self.assertTrue(naming.出力ファイル名("定例会議", self.時刻, 1).endswith(".vtt"))


class 出力ファイル名に使う時刻の決定(unittest.TestCase):
    """ファイル名に使う時刻が、録画の作成日時を優先し、無ければ台帳の更新時刻になることを検証する。

    会議の開始時刻そのものは取得できない。録画は会議終了直後に生成されるため、
    同名の定例会議を区別する目的にはどちらでも足りる。
    """

    def setUp(self):
        self.録画の作成日時 = datetime(2026, 8, 19, 10, 30, tzinfo=timezone.utc)
        self.台帳の更新時刻 = datetime(2026, 8, 19, 11, 45, tzinfo=timezone.utc)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-4
    def test_録画の作成日時があればそれが使われること(self):
        self.assertEqual(
            naming.ファイル名の時刻を決める(self.録画の作成日時, self.台帳の更新時刻),
            self.録画の作成日時,
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-4
    def test_録画の作成日時が台帳から得られない場合は台帳の更新時刻で代用されること(self):
        self.assertEqual(
            naming.ファイル名の時刻を決める(None, self.台帳の更新時刻),
            self.台帳の更新時刻,
        )


class 出力ファイル名で使えない文字の処理(unittest.TestCase):
    """会議名に含まれる使用不可文字が置換され、パスとして解釈されないことを検証する。

    会議名は利用者が自由に付けるため、SharePoint/OneDriveのファイル名制約を
    満たさない文字が入りうる。また会議名由来の名前はパストラバーサルの経路にもなる。
    """

    def setUp(self):
        self.時刻 = datetime(2026, 8, 19, 10, 30, tzinfo=timezone.utc)

    def 会議名部分(self, 会議名: str) -> str:
        return naming.出力ファイル名(会議名, self.時刻, 1).split("__")[0]

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-2
    def test_使用できない文字が置換されること(self):
        for 文字 in '"*:<>?/\\|':
            with self.subTest(文字=文字):
                self.assertNotIn(文字, self.会議名部分(f"会議{文字}名"))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-2
    def test_絵文字が置換されること(self):
        self.assertNotIn("🎉", self.会議名部分("打ち上げ🎉"))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-2
    def test_先頭と末尾の空白が除去されること(self):
        self.assertEqual(self.会議名部分("  定例会議  "), "定例会議")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-2
    def test_末尾のピリオドが除去されること(self):
        self.assertEqual(self.会議名部分("定例会議..."), "定例会議")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-2
    def test_置換の結果が空になる場合は既定の名前が使われること(self):
        """会議名が記号だけだった場合に、拡張子だけのファイル名になるのを防ぐ。"""
        self.assertNotEqual(self.会議名部分("///"), "")

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#セキュリティ
    def test_パス区切り文字と親ディレクトリ参照が結果に残らないこと(self):
        """出力置き場の外に書き出せないことを保証する(パストラバーサル対策)。"""
        名前 = naming.出力ファイル名("../../etc/passwd", self.時刻, 1)
        self.assertNotIn("/", 名前)
        self.assertNotIn("\\", 名前)
        self.assertNotIn("..", 名前)


class 出力ファイル名の長さ制限(unittest.TestCase):
    """名前が長すぎる場合に会議名側だけが切り詰められることを検証する。

    OneDriveのファイル名長とパス長の制限に対し、同期フォルダの深い階層に
    置かれても収まる余裕を持たせる。時刻と連番を落とすと衝突防止が壊れる。
    """

    def setUp(self):
        self.時刻 = datetime(2026, 8, 19, 10, 30, tzinfo=timezone.utc)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-6
    def test_上限を超える場合に会議名側が切り詰められること(self):
        名前 = naming.出力ファイル名("あ" * 200, self.時刻, 1)
        self.assertLessEqual(len(名前), naming.ファイル名の長さ上限)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-6
    def test_切り詰めても時刻と連番と拡張子が残ること(self):
        名前 = naming.出力ファイル名("あ" * 200, self.時刻, 7)
        self.assertIn("20260819T1030", 名前)
        self.assertIn("__07", 名前)
        self.assertTrue(名前.endswith(".vtt"))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-6
    def test_上限ちょうどの場合は切り詰められないこと(self):
        """境界値。上限を1文字でも下回る扱いにすると、不要に名前が削られる。"""
        接尾辞 = (
            f"{naming.区切り}20260819T1030"
            f"{naming.区切り}01{naming.トランスクリプトの拡張子}"
        )
        会議名 = "あ" * (naming.ファイル名の長さ上限 - len(接尾辞))
        名前 = naming.出力ファイル名(会議名, self.時刻, 1)
        self.assertEqual(len(名前), naming.ファイル名の長さ上限)
        self.assertTrue(名前.startswith(会議名))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#ファイル名-2
    def test_切り詰めた結果の末尾に空白やピリオドが残らないこと(self):
        """切り詰めで末尾が空白やピリオドになると、再びファイル名制約に触れる。"""
        会議名 = "あ" * 150 + " . . ."
        名前 = naming.出力ファイル名(会議名, self.時刻, 1)
        会議名部分 = 名前.split("__")[0]
        self.assertEqual(会議名部分, 会議名部分.rstrip(" ."))


if __name__ == "__main__":
    unittest.main()
