"""読み手の区分け表を読み込む処理のテスト。

検査は「どの見出しを誰が読むか」を区分け表だけから決める。表が壊れていることに
気づかないまま検査を続けると、全部の見出しを素通りさせて「違反なし」を返してしまう
ため、読めない表は例外で止める。

仕様: ~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers/
  requirements.md#見出しの固定セットと読み手-4、requirements.md#読み手の区分け-1、
  design.md#区分け表の読み込み
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import layout_rules

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_TABLE = REPO_ROOT / "quality-standards" / "base" / "spec-layout.md"

MINIMAL = """# 見出し

## 読み手の区分け

| ファイル | 見出し | 読み手 | 本文の見え方 | 要点に書くもの |
|---|---|---|---|---|
| requirements.md | ユーザーストーリー | 人 | 見える | — |
| requirements.md | 機能要件 | AI | `###` ごとに1行概要が見える・[n] は畳む | 機能の1行概要 |
| design.md | エラーハンドリング | AI | 要点が見える・本文は畳む | 止める条件 |
| design.md | 処理フロー | AI | `###` ごとに図と1行要点が見える・手順は畳む | 処理の1行概要 |
| design.md | バリデーション / ログ | AI | 要点が見える・本文は畳む | 内容の1行要約 |
| appendix.md | (全体) | AI | 要点なし・畳まない | — |
| architecture.md | 上記以外 | AI | 要点が見える・本文は畳む | 内容の1行要約 |
"""


class 区分け表の読み込み(unittest.TestCase):
    """仕様書に書かれた読み手の割り当てを、検査が使える形に読み取れることを確かめる。"""

    # 仕様: requirements.md#見出しの固定セットと読み手-4
    def test_実際の区分け表を読むと主要な見出しの読み手が取れること(self):
        rules = layout_rules.load_layout_rules(str(REAL_TABLE))
        self.assertEqual(rules.rule_for("requirements.md", "機能要件").reader, "AI")
        self.assertEqual(rules.rule_for("requirements.md", "スコープ外").reader, "人")
        self.assertEqual(rules.rule_for("design.md", "決定事項").reader, "人")

    # 仕様: requirements.md#見出しの固定セットと読み手-4
    def test_スラッシュ区切りでまとめた見出しが1つずつに展開されること(self):
        rules = layout_rules.parse_layout_table(MINIMAL)
        for heading in ("バリデーション", "ログ"):
            rule = rules.rule_for("design.md", heading)
            self.assertIsNotNone(rule, heading)
            self.assertEqual(rule.reader, "AI")

    # 仕様: requirements.md#要点と畳み-3
    def test_見え方から畳みの単位が三通りに解釈されること(self):
        """否定確認: fold_unit の判定から `###` の条件を外すと落ちる"""
        rules = layout_rules.parse_layout_table(MINIMAL)
        self.assertEqual(rules.rule_for("requirements.md", "機能要件").fold_unit, "###")
        self.assertEqual(rules.rule_for("design.md", "エラーハンドリング").fold_unit, "##")
        self.assertEqual(rules.rule_for("requirements.md", "ユーザーストーリー").fold_unit, "##")

    # 仕様: requirements.md#要点と畳み-1、requirements.md#要点と畳み-6
    def test_見え方から本文を畳むかどうかが決まること(self):
        rules = layout_rules.parse_layout_table(MINIMAL)
        self.assertTrue(rules.rule_for("requirements.md", "機能要件").folded)
        self.assertFalse(rules.rule_for("requirements.md", "ユーザーストーリー").folded)
        self.assertFalse(rules.rule_for("appendix.md", "(全体)").checked)

    # 仕様: requirements.md#要点と畳み-4、requirements.md#読み手の区分け-3
    def test_見え方から図が見えてよい見出しが分かること(self):
        rules = layout_rules.parse_layout_table(MINIMAL)
        self.assertTrue(rules.rule_for("design.md", "処理フロー").figure_visible)
        self.assertFalse(rules.rule_for("design.md", "エラーハンドリング").figure_visible)

    # 仕様: requirements.md#見出しの固定セットと読み手-4
    def test_区分け表に無い見出しはファイル既定の規定に落ちること(self):
        rules = layout_rules.parse_layout_table(MINIMAL)
        self.assertEqual(rules.rule_for("architecture.md", "用語集").reader, "AI")
        self.assertIsNone(rules.rule_for("requirements.md", "用語集"))

    # 仕様: design.md#区分け表の読み込み 手順4
    def test_表が1つも無ければ読めない表として例外になること(self):
        with self.assertRaises(layout_rules.LayoutTableError):
            layout_rules.parse_layout_table("# 見出し\n\n表はありません。\n")

    # 仕様: design.md#区分け表の読み込み 手順4
    def test_必須の列が欠けていれば例外になること(self):
        broken = MINIMAL.replace("| ファイル | 見出し | 読み手 | 本文の見え方 | 要点に書くもの |",
                                 "| ファイル | 見出し | 本文の見え方 | 要点に書くもの |")
        with self.assertRaises(layout_rules.LayoutTableError):
            layout_rules.parse_layout_table(broken)

    # 仕様: requirements.md#読み手の区分け-1
    def test_読み手が人とAI以外の値なら例外になること(self):
        """否定確認: 読み手の値の検証を外すと「両方」を素通りして落ちない"""
        broken = MINIMAL.replace("| requirements.md | 機能要件 | AI |",
                                 "| requirements.md | 機能要件 | 両方 |")
        with self.assertRaises(layout_rules.LayoutTableError):
            layout_rules.parse_layout_table(broken)


if __name__ == "__main__":
    unittest.main()
