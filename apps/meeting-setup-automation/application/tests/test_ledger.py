"""台帳ファイルの名前と置き場所(design.md データ設計)のテスト。

依頼・候補・選択結果・作成結果・選択画面は、依頼IDを唯一の共有点として
対応付ける。名前の決め方がSkillとフローで食い違うと、Skillは現れないファイルを
待ち上限まで待つことになるため、名前の形をここで固定する。
"""

import json
import tempfile
import unittest
from pathlib import Path

import config
import ledger


class 台帳ファイルの名前(unittest.TestCase):

    def setUp(self):
        self.設定 = config.load(environ={config.台帳ルート環境変数: "/ledger"})

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#台帳ファイルの扱い-2
    def test_依頼と候補は依頼IDと試行番号を含む名前で用途別のフォルダに置かれること(self):
        self.assertEqual(
            ledger.依頼ファイル(self.設定, "20260909-101500-ab3f", 1),
            Path("/ledger/request/request-20260909-101500-ab3f-a1.json"),
        )
        self.assertEqual(
            ledger.候補ファイル(self.設定, "20260909-101500-ab3f", 2),
            Path("/ledger/candidates/candidates-20260909-101500-ab3f-a2.json"),
        )

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#データ設計台帳ファイル
    def test_選択結果と作成結果は再試行番号が0のとき接尾辞を付けず1以上のときだけ付けること(self):
        self.assertEqual(
            ledger.選択結果ファイル(self.設定, "X", 0),
            Path("/ledger/selection/selection-X.json"),
        )
        self.assertEqual(
            ledger.選択結果ファイル(self.設定, "X", 2),
            Path("/ledger/selection/selection-X-r2.json"),
        )
        self.assertEqual(ledger.作成結果ファイル(self.設定, "X", 0), Path("/ledger/result/result-X.json"))
        self.assertEqual(ledger.作成結果ファイル(self.設定, "X", 1), Path("/ledger/result/result-X-r1.json"))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#データ設計台帳ファイル
    def test_選択画面の名前(self):
        self.assertEqual(ledger.選択画面ファイル(self.設定, "X"), Path("/ledger/html/select-X.html"))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#power-automateフローの役割
    def test_フローが書くファイル名は読んだファイル名の先頭を置き換えただけで得られること(self):
        依頼 = ledger.依頼ファイル(self.設定, "X", 1).name
        self.assertEqual(依頼.replace("request-", "candidates-"), ledger.候補ファイル(self.設定, "X", 1).name)
        選択 = ledger.選択結果ファイル(self.設定, "X", 1).name
        self.assertEqual(選択.replace("selection-", "result-"), ledger.作成結果ファイル(self.設定, "X", 1).name)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#台帳ファイルの扱い-1
    def test_Skillが書くフォルダとフローが書くフォルダが重ならないこと(self):
        skill側 = {self.設定.依頼フォルダ, self.設定.選択結果フォルダ, self.設定.htmlフォルダ}
        フロー側 = {self.設定.候補フォルダ, self.設定.作成結果フォルダ}
        self.assertFalse(skill側 & フロー側)


class JSONの読み書き(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#エラーハンドリング
    def test_無いファイルと途中まで書かれたファイルはまだ来ていないものとしてNoneになること(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(ledger.read_json(Path(d, "none.json")))
            Path(d, "half.json").write_text('{"a": 1, "b": ', encoding="utf-8")
            self.assertIsNone(ledger.read_json(Path(d, "half.json")))

    def test_書いたJSONをそのまま読み戻せ親フォルダが無ければ作ること(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "sub", "x.json")
            ledger.write_json(path, {"依頼": "値", "n": 1})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"依頼": "値", "n": 1})
            self.assertEqual(ledger.read_json(path), {"依頼": "値", "n": 1})


if __name__ == "__main__":
    unittest.main()
