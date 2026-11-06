"""仕様書Markdownの走査のテスト。

検査は文書の意味を読まず、見出し・畳みのタグ・図の囲み・行末の目印という字句だけを
見る。走査が見落とすと以降の照合がすべて素通りになるため、位置(行番号)まで含めて
取れていることを確かめる。

仕様: ~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers/
  requirements.md#出所の目印-4、requirements.md#機械検査-5、
  design.md#見出しの抽出と読み手の判定、design.md#出所の目印の照合
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import markdown_scan

SAMPLE = """# タイトル

ステータス: 実装中 ／ 優先度: 高

章に属さない1行目。
章に属さない2行目。

## 機能要件

### ある機能

機能の1行概要 〔提案〕

<details><summary>詳細を開く</summary>

- [1] 詳細の項目 〔論理〕

</details>

### 別の機能

図つきの処理 〔合意〕

```mermaid
flowchart LR
    a --> b
```

図の説明1行。

<details><summary>詳細を開く</summary>

- [1] もう一つの項目

</details>

## 用語

> 読み手: AI

用語の要点 〔提案〕

<details><summary>詳細を開く</summary>
本文がsummaryの直後から始まっている。
</details>

## スコープ外

- 対象外のこと 〔合意〕
- 目印のない行
- 両方ついている行 〔合意〕 〔提案〕
"""

DECISIONS = """# 設計

リード文。

## 決定事項

| 論点 | 選んだ案 | 採らなかった案 | 理由 | 影響範囲 | 出所 |
|---|---|---|---|---|---|
| 置き場 | lib 配下 | skills 配下 | 両方から呼べる | lib | 合意 |
| 出力 | タブ区切り | JSON | そのまま貼れる | 出力 | 提案 |
"""


class 見出しと本文範囲の走査(unittest.TestCase):
    """どこからどこまでがその見出しの本文かを取り出せることを確かめる。"""

    def setUp(self):
        self.scan = markdown_scan.scan(SAMPLE)

    # 仕様: design.md#見出しの抽出と読み手の判定 手順1
    def test_見出しが階層つきで出現順に取れること(self):
        levels = [(h.level, h.text) for h in self.scan.headings]
        self.assertEqual(levels, [
            (2, "機能要件"), (3, "ある機能"), (3, "別の機能"),
            (2, "用語"), (2, "スコープ外")])

    # 仕様: design.md#見出しの抽出と読み手の判定 手順5
    def test_本文の範囲が次の同格以上の見出しの手前で終わること(self):
        ある機能 = self.scan.headings[1]
        self.assertEqual(self.scan.line_text(ある機能.body_start).strip(), "")
        self.assertIn("機能の1行概要", "\n".join(
            self.scan.body_lines(ある機能)))
        self.assertNotIn("図つきの処理", "\n".join(self.scan.body_lines(ある機能)))

    # 仕様: requirements.md#見出しの固定セットと読み手-3
    def test_章の外の行がラベル行も含めて取れること(self):
        """走査は見つけた行を全部返し、ラベル1行を許すかどうかは checks が決める。"""
        self.assertEqual([t for _, t in self.scan.outside_section_lines],
                         ["ステータス: 実装中 ／ 優先度: 高",
                          "章に属さない1行目。", "章に属さない2行目。"])

    # 仕様: requirements.md#見出しの固定セットと読み手-3
    def test_引用で書いたステータス行がラベルとして認められないこと(self):
        """否定確認: STATUS_LINE が引用を許すと一致してしまい落ちる"""
        self.assertIsNone(markdown_scan.STATUS_LINE.match("> ステータス: 実装中"))
        self.assertIsNotNone(markdown_scan.STATUS_LINE.match("ステータス: 実装中"))

    # 仕様: requirements.md#出所の目印-4
    def test_推測マーカーが行末にあっても出所の目印を読めること(self):
        """否定確認: TRAILING_NOTE の読み飛ばしを外すと目印0個になって落ちる"""
        self.assertEqual(
            markdown_scan.source_marks("- 推測で決めた方針 〔提案〕【推測】"), ["提案"])
        self.assertEqual(
            markdown_scan.source_marks("- 推測で決めた方針 【推測】〔提案〕"), ["提案"])

    # 仕様: requirements.md#出所の目印-4
    def test_目印の後ろに句点や補足があれば読まないこと(self):
        """行末のトークンだけを見る。付け方が違えば「出所なし」にして書き手に直させる。"""
        for 行 in ("- 決めたこと 〔合意〕。", "- 決めたこと 〔合意〕(2026-09-25)",
                  "- 決めたこと `〔合意〕`"):
            self.assertEqual(markdown_scan.source_marks(行), [], 行)

    # 仕様: requirements.md#出所の目印-4
    def test_推測マーカーだけの行は出所なしになること(self):
        """読み飛ばした結果トークンが無ければ、目印は0個(出所なし)。"""
        self.assertEqual(markdown_scan.source_marks("- 目印を付け忘れた行 【推測】"), [])
        self.assertEqual(
            markdown_scan.source_marks("- 入れ子 【推測: なぜなら〔合意〕だから】"), [])

    # 仕様: requirements.md#見出しの固定セットと読み手-3
    def test_章の外に本文が無ければ空で返ること(self):
        scan = markdown_scan.scan("# タイトル\n\n## 最初の見出し\n\n本文\n")
        self.assertEqual(scan.outside_section_lines, [])

    # 仕様: requirements.md#見出しの固定セットと読み手-5
    def test_見出し直後の読み手宣言が読めること(self):
        用語 = [h for h in self.scan.headings if h.text == "用語"][0]
        self.assertEqual(用語.declaration, "AI")
        機能要件 = self.scan.headings[0]
        self.assertIsNone(機能要件.declaration)

    # 仕様: requirements.md#要点と畳み-1
    def test_畳みの範囲が開始行と終了行で取れること(self):
        self.assertEqual(len(self.scan.detail_ranges), 3)
        first = self.scan.detail_ranges[0]
        self.assertIn("<details><summary>", self.scan.line_text(first.start))
        self.assertIn("</details>", self.scan.line_text(first.end))
        self.assertTrue(self.scan.in_details(first.start + 2))
        self.assertFalse(self.scan.in_details(first.start - 1))

    # 仕様: requirements.md#要点と畳み-5
    def test_summary直後が空行かどうかを行ごとに判定できること(self):
        """否定確認: 直後の行の中身を見ずに常に空行扱いにすると落ちる"""
        空行あり, _, 空行なし = self.scan.detail_ranges
        self.assertTrue(空行あり.blank_after_summary)
        self.assertFalse(空行なし.blank_after_summary)

    # 仕様: requirements.md#要点と畳み-4
    def test_Mermaidの範囲が取れて図の直後の行が分かること(self):
        self.assertEqual(len(self.scan.mermaid_ranges), 1)
        図 = self.scan.mermaid_ranges[0]
        self.assertTrue(self.scan.in_mermaid(図.start + 1))
        self.assertFalse(self.scan.in_mermaid(図.end + 1))


class 出所の目印の走査(unittest.TestCase):
    """承認者が読む行に付ける目印を、行末のトークンだけから数えられることを確かめる。"""

    # 仕様: requirements.md#出所の目印-4
    def test_行末の目印が1つなら1と数えること(self):
        self.assertEqual(markdown_scan.source_marks("- 対象外のこと 〔合意〕"), ["合意"])
        self.assertEqual(markdown_scan.source_marks("機能の1行概要 〔提案〕"), ["提案"])

    # 仕様: requirements.md#出所の目印-4
    def test_目印が無ければ空で返ること(self):
        self.assertEqual(markdown_scan.source_marks("- 目印のない行"), [])

    # 仕様: requirements.md#出所の目印-4
    def test_行末に両方あれば2つ数えること(self):
        self.assertEqual(
            markdown_scan.source_marks("- 両方ついている行 〔合意〕 〔提案〕"),
            ["合意", "提案"])

    # 仕様: requirements.md#出所の目印-4
    def test_リスク種別の目印を挟んでも前後どちらでも数えること(self):
        """否定確認: 行末の1トークンだけを見る実装にすると前置きの目印を見落として落ちる"""
        self.assertEqual(markdown_scan.source_marks("- [1] … 〔非機能〕 〔提案〕"), ["提案"])
        self.assertEqual(markdown_scan.source_marks("- [1] … 〔提案〕 〔非機能〕"), ["提案"])

    # 仕様: requirements.md#出所の目印-4
    def test_行の途中に書かれた目印の字形は数えないこと(self):
        line = "- 目印 `〔合意〕` の意味を説明する行 〔提案〕"
        self.assertEqual(markdown_scan.source_marks(line), ["提案"])
        self.assertEqual(markdown_scan.source_marks("`〔合意〕` とは会話で決めたこと"), [])


class 決定事項の表の走査(unittest.TestCase):
    """設計の分かれ道を並べた表から、出所の列を取り出せることを確かめる。"""

    # 仕様: requirements.md#出所の目印-3
    def test_出所列のある表から行ごとの値が取れること(self):
        table = markdown_scan.scan(DECISIONS).find_table("決定事項")
        self.assertIn("出所", table.header)
        self.assertEqual([value for _, value in table.column("出所")], ["合意", "提案"])

    # 仕様: requirements.md#出所の目印-3
    def test_出所列が無ければ列なしと分かること(self):
        without = DECISIONS.replace(" | 出所 |", " |").replace("|---|---|---|---|---|---|",
                                                               "|---|---|---|---|---|")
        without = without.replace(" | 合意 |", " |").replace(" | 提案 |", " |")
        table = markdown_scan.scan(without).find_table("決定事項")
        self.assertNotIn("出所", table.header)

    # 仕様: requirements.md#決定事項の表-3
    def test_表が無ければNoneで返ること(self):
        scan = markdown_scan.scan("# 設計\n\n章に属さない本文。\n\n## 決定事項\n\n決定事項なし\n")
        self.assertIsNone(scan.find_table("決定事項"))


if __name__ == "__main__":
    unittest.main()
