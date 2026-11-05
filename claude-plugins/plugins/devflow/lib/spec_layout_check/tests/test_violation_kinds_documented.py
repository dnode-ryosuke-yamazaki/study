"""検査スクリプトが出す違反種別と、仕様に書いてある一覧が一致することの検査。

種別を1つ増やしたり名前を変えたりしたとき、仕様側(requirements.md の違反種別の
列挙と appendix.md の出力書式)への反映は目視頼りになりやすい。実際に、章の外の本文に
関する種別を作り直したあと、仕様に古い種別名が残ったままになった。両者を突き合わせて
機械で止める。

仕様: ~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers/
  requirements.md#機械検査-2、appendix.md#検査結果の出力書式
"""
import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_spec_layout
import checks

SPEC = Path(os.path.expanduser(
    "~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers"))

# 違反ではない補足行の種別。出力には出るが違反種別の一覧には載せない
SUPPLEMENT_KINDS = {check_spec_layout.KIND_VISIBLE_CHARS,
                    check_spec_layout.KIND_AGREED_LINES,
                    check_spec_layout.KIND_PROPOSED_LINES}


def implemented_kinds():
    """checks.py が持つ違反種別(旧形式を含む)。"""
    return {value for name, value in vars(checks).items()
            if name.startswith("KIND_") and isinstance(value, str)}


def kinds_in(text):
    """バッククォートで囲まれた語のうち、実装の種別名と一致するものを拾う。

    コードブロックの ``` をまたいで対にならないよう、1行ずつ見る。
    """
    quoted = set()
    for line in text.split("\n"):
        quoted |= set(re.findall(r"`([^`\n]+)`", line))
    return quoted & (implemented_kinds() | SUPPLEMENT_KINDS)


class 違反種別の一覧(unittest.TestCase):
    """実装が出す種別が、仕様の一覧に漏れなく載っていることを確かめる。"""

    def setUp(self):
        self.assertTrue(SPEC.exists(), "対象specが見つからない: %s" % SPEC)

    # 仕様: appendix.md#検査結果の出力書式
    def test_付録の一覧が実装の種別を漏れなく載せていること(self):
        """否定確認: 実装に種別を1つ足して付録に書かないと落ちる"""
        text = (SPEC / "appendix.md").read_text(encoding="utf-8")
        載っている = kinds_in(text)
        for kind in implemented_kinds():
            self.assertIn(kind, 載っている, "appendix.md に「%s」が無い" % kind)

    # 仕様: appendix.md#検査結果の出力書式
    def test_付録に実装に無い種別が残っていないこと(self):
        """否定確認: 廃止した種別名を付録に残すと落ちる"""
        text = (SPEC / "appendix.md").read_text(encoding="utf-8")
        違反種別の行 = [line for line in text.split("\n") if "違反種別:" in line]
        self.assertEqual(len(違反種別の行), 1, "違反種別の行が1行でない")
        for 語 in re.findall(r"`([^`\n]+)`", 違反種別の行[0]):
            self.assertIn(語, implemented_kinds() | SUPPLEMENT_KINDS,
                          "appendix.md の「%s」は実装に無い" % 語)

    # 仕様: requirements.md#機械検査-2
    def test_要件の違反種別の列挙が実装と一致すること(self):
        """否定確認: 要件から種別を1つ消すと落ちる"""
        text = (SPEC / "requirements.md").read_text(encoding="utf-8")
        列挙 = [line for line in text.split("\n") if "違反種別(" in line]
        self.assertEqual(len(列挙), 1, "違反種別を列挙した行が1行でない")
        書いてある = {語.strip() for 語 in
                 re.search(r"違反種別\(([^)]*)\)", 列挙[0]).group(1).split("/")}
        # 「旧形式」は違反ではなく状態なので要件の列挙には含めない
        期待 = implemented_kinds() - {checks.KIND_LEGACY}
        self.assertEqual(書いてある, 期待)


if __name__ == "__main__":
    unittest.main()
