"""判定条件の説明文が、実装と同じ世代で全箇所そろっていることの検査。

判定ロジックを実装で変えたあと、その条件を説明している文は仕様側の複数の場所に
散らばっているため、1か所だけ直して残りが古い世代のまま残る事故が繰り返し起きた
(旧形式の判定で3世代の記述が同居した)。違反種別のような短い名前は
`test_violation_kinds_documented.py` が突き合わせられるが、条件の説明文は
そのままでは突き合わせられないので、条件を表す語が全箇所にそろっているかを見張る。

仕様: ~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers/
  requirements.md#機械検査-3、requirements.md#見出しの固定セットと読み手-6、
  appendix.md#検査スクリプトが見る文字面、design.md#結果の出力
"""
import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import checks

ROOT = Path(__file__).resolve().parents[3]
LAYOUT = ROOT / "quality-standards" / "base" / "spec-layout.md"
SPEC = Path(os.path.expanduser(
    "~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers"))

# 旧形式と判定する3条件。説明文はどれか1語でも欠ければ古い世代とみなす
LEGACY_CONDITIONS = (
    # ①畳みが1つも無い
    ("畳みが1つも無", "`<details>` が1つも無", "折りたたみが1つも無"),
    # ②畳むべきAIの見出しが1つ以上ある
    ("畳むべきAIの見出し",),
    # ③出所の目印が1つも無い
    ("目印が1つも無", "目印も1つも無"),
)

# 旧形式の判定を説明している箇所。行を特定する文字列で押さえ、
# 見つからなければ(書き換え・削除されれば)落として読み直しを促す
LEGACY_EXPLANATIONS = (
    (SPEC / "requirements.md", ("- [3] ", "旧形式")),
    (SPEC / "appendix.md", ("| 旧形式の判定 |",)),
    (SPEC / "design.md", ("| 旧形式の判定 |",)),
    (SPEC / "design.md", ("そのファイルの違反はすべて捨てて",)),
    (SPEC / "design.md", ("対象specが旧形式", "その工程の中で")),
    (SPEC / "tasks.md", ("のファイルは違反を捨てて",)),
    (ROOT / "skills" / "fix" / "SKILL.md", ("対象specが**旧形式**",)),
)

# ステータスのラベルの3つの値。区分け表のファイル1か所だけで定義する
STATUS_VALUES = ("仕様確認中(未実装)", "実装中", "リリース済み")

# 終了コード2(旧形式)を /spec-review がどう扱うか。書きかけを🔴で書き手に戻す
EXIT2_CONDITIONS = (("書きかけ",), ("🔴", "修正必須"))
EXIT2_EXPLANATIONS = (
    (ROOT / "skills" / "spec-review" / "SKILL.md", ("| 2 |",)),
    (SPEC / "design.md", ("終了コードが「旧形式」の場合",)),
    (SPEC / "requirements.md", ("- [3] ", "旧形式")),
    (SPEC / "tasks.md", ("終了コードごとの扱い",)),
)


def 行を取る(path, 目印):
    """目印の語をすべて含む行を返す。"""
    return [line for line in path.read_text(encoding="utf-8").split("\n")
            if all(語 in line for 語 in 目印)]


class 旧形式の判定の説明(unittest.TestCase):
    """実装の3条件が、仕様側の全箇所にそろっていることを確かめる。"""

    def test_説明している箇所が全部見つかること(self):
        """否定確認: 説明を1か所消すと落ちる"""
        for path, 目印 in LEGACY_EXPLANATIONS:
            self.assertEqual(len(行を取る(path, 目印)), 1,
                             "%s に「%s」の行が1行だけ無い" % (path.name, "+".join(目印)))

    def test_全箇所が3条件をそろえていること(self):
        """否定確認: どれか1か所から「AI」の語を消すと落ちる"""
        for path, 目印 in LEGACY_EXPLANATIONS:
            行 = 行を取る(path, 目印)[0]
            for 語群 in LEGACY_CONDITIONS:
                self.assertTrue(any(語 in 行 for 語 in 語群),
                                "%s の「%s」の行に %s が無い: %s"
                                % (path.name, "+".join(目印), " / ".join(語群), 行.strip()))


    def test_説明の箇所数が仕様のテスト戦略と一致すること(self):
        """否定確認: テスト戦略の「7か所」を別の数に書き換えると落ちる"""
        行 = 行を取る(SPEC / "design.md", ("| 機械検査-3 |",))
        self.assertEqual(len(行), 1, "design.md のテスト戦略に機械検査-3 の行が無い")
        self.assertIn("仕様の%dか所" % len(LEGACY_EXPLANATIONS), 行[0].replace(" ", ""),
                      "テスト戦略の箇所数が %d でない: %s"
                      % (len(LEGACY_EXPLANATIONS), 行[0].strip()))


class 終了コード2の扱い(unittest.TestCase):
    """書きかけを🔴で戻す扱いが、説明している全箇所でそろっていることを確かめる。"""

    def test_説明している箇所が全部見つかること(self):
        """否定確認: 説明を1か所消すと落ちる"""
        for path, 目印 in EXIT2_EXPLANATIONS:
            self.assertEqual(len(行を取る(path, 目印)), 1,
                             "%s に「%s」の行が1行だけ無い" % (path.name, "+".join(目印)))

    def test_前世代の言い方が残っていないこと(self):
        """否定確認: どこかに「旧形式のみ」と書き戻すと落ちる

        終了コード2は「旧形式のファイルだけ」ではなく「違反が無く旧形式のファイルが
        ある」状態を指す。違反0の新形式ファイルと混ざっていても2になる。
        """
        # tests/ を走査先に入れない: この検査自身が禁止する言い方を書いており、
        # 自分に一致してしまう(範囲を広げるときは除外の仕組みから作ること)
        場所 = [ROOT / "lib" / "spec_layout_check" / "scripts",
              ROOT / "skills", ROOT / "quality-standards", SPEC]
        候補 = [path for 元 in 場所 for path in sorted(元.rglob("*"))
              if path.is_file() and path.suffix in (".py", ".md")]
        self.assertTrue(候補, "走査対象のファイルが1つも見つからない")
        残り = [str(path) for path in 候補
              if "旧形式のみ" in path.read_text(encoding="utf-8")]
        self.assertEqual(残り, [], "前世代の言い方が残っている: %s" % 残り)

    def test_全箇所が同じ扱いを書いていること(self):
        """否定確認: どれか1か所を🟢(情報)に戻すと落ちる"""
        for path, 目印 in EXIT2_EXPLANATIONS:
            行 = 行を取る(path, 目印)[0]
            for 語群 in EXIT2_CONDITIONS:
                self.assertTrue(any(語 in 行 for 語 in 語群),
                                "%s の「%s」の行に %s が無い: %s"
                                % (path.name, "+".join(目印), " / ".join(語群), 行.strip()))


class architecture_mdの検査の起動(unittest.TestCase):
    """specフォルダの外にある architecture.md を検査する手順が残っていることを確かめる。"""

    # architecture.md は specフォルダではなく1階層上の specs/ に置くため、
    # specフォルダを渡す検査では対象に入らない。別に1回起動する手順が要る
    起動を書く手順書 = ("architecture-workflow", "spec-review")

    def test_別に起動する手順が書かれていること(self):
        """否定確認: どちらかの手順書から architecture.md の起動を消すと落ちる"""
        for name in self.起動を書く手順書:
            text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("architecture.md のあるフォルダ", text,
                          "%s に architecture.md を渡す起動の説明が無い" % name)

    def test_設計の対象の説明が1階層上を指していること(self):
        """否定確認: design.md の対象を「同階層の architecture.md」に戻すと落ちる"""
        for f in ("requirements.md", "design.md"):
            text = (SPEC / f).read_text(encoding="utf-8")
            self.assertNotIn("同階層の architecture.md", text,
                             "%s に architecture.md が同階層にある前提の記述が残っている" % f)
            self.assertIn("1階層上", text, "%s に architecture.md の置き場の説明が無い" % f)


class 廃止見出しの名前(unittest.TestCase):
    """実装が違反にする見出し名と、要件に書いた見出し名が一致することを確かめる。"""

    def test_要件と実装で廃止見出しが一致すること(self):
        """否定確認: 実装に「概要」を足すと落ちる"""
        text = (SPEC / "requirements.md").read_text(encoding="utf-8")
        書いてある = re.search(r"廃止した見出し\(([^)]*)\)", text)
        self.assertIsNotNone(書いてある, "requirements.md に廃止した見出しの記述が無い")
        名前 = {語.strip() for 語 in 書いてある.group(1).split("・")}
        self.assertEqual(名前, set(checks.ABOLISHED_HEADINGS))


class ステータスのラベルの値(unittest.TestCase):
    """ラベルの3つの値と遷移が、区分け表のファイル1か所で定義されていることを確かめる。"""

    def setUp(self):
        self.layout = LAYOUT.read_text(encoding="utf-8")

    def test_3つの値と書き換える工程が定義されていること(self):
        """否定確認: 終端の「リリース済み」の行を消すと落ちる"""
        for 値 in STATUS_VALUES:
            行 = [line for line in self.layout.split("\n")
                  if line.startswith("| " + 値 + " |")]
            self.assertEqual(len(行), 1, "spec-layout.md に「%s」の行が1行だけ無い" % 値)
        for 工程 in ("/requirement", "/implementation", "/pr"):
            self.assertIn(工程, self.layout, "書き換える工程 %s が書かれていない" % 工程)

    def test_ラベルの定義が他のファイルに重複していないこと(self):
        """否定確認: 同じ遷移表をSKILL.mdやappendix.mdへ写すと落ちる"""
        候補 = [path for 場所 in ("skills", "agents", "quality-standards")
              for path in sorted((ROOT / 場所).rglob("*.md"))] + sorted(SPEC.glob("*.md"))
        self.assertTrue(候補, "走査対象のファイルが1つも見つからない")
        重複 = []
        for path in 候補:
            text = path.read_text(encoding="utf-8")
            if path.samefile(LAYOUT):
                continue
            if all(("| " + 値 + " |") in text for 値 in STATUS_VALUES):
                重複.append(path.name)
        self.assertEqual(重複, [], "ラベルの定義が写されている: %s" % 重複)

    def test_機能マップの3段階と対応が付いていること(self):
        """否定確認: 対応先の「仕様のみ(未実装)」を消すと落ちる"""
        for 段階 in ("仕様のみ(未実装)", "実装中", "リリース済み"):
            self.assertIn(段階, self.layout,
                          "機能マップの状態列の値「%s」との対応が無い" % 段階)


if __name__ == "__main__":
    unittest.main()
