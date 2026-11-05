"""要点・畳み・出所の目印の照合と、人が読む量の集計のテスト。

この検査が見落とすと、承認者は「見えている行を読めば足りる」という前提のまま
畳み忘れや目印の付け忘れに気づけない。違反の種類ごとに、見本の文書で1件ずつ
検出できることを確かめる。

仕様: ~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers/
  requirements.md#要点と畳み、requirements.md#出所の目印、requirements.md#機械検査-1、
  requirements.md#機械検査-6、design.md#要点と畳みの照合、design.md#出所の目印の照合、
  design.md#人が読む文字数の集計
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import checks
import layout_rules
import markdown_scan

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REAL_TABLE = Path(__file__).resolve().parents[3] / "quality-standards" / "base" / "spec-layout.md"

RULES = layout_rules.load_layout_rules(str(REAL_TABLE))


def read(spec, name):
    with open(str(FIXTURES / spec / name), encoding="utf-8") as fp:
        return fp.read()


def inspect(spec, name):
    scan = markdown_scan.scan(read(spec, name))
    found = checks.check_folding(name, scan, RULES)
    found += checks.check_provenance(name, scan, RULES)
    return scan, found


def kinds(violations):
    return sorted(v.kind for v in violations)


class 新形式のお手本(unittest.TestCase):
    """正しく書かれた仕様書が1件も違反にならないことを確かめる。"""

    # 仕様: requirements.md#機械検査-1
    def test_お手本のrequirementsが違反0であること(self):
        _, found = inspect("ok_spec", "requirements.md")
        self.assertEqual(found, [], [str(v) for v in found])

    # 仕様: requirements.md#機械検査-1
    def test_お手本のdesignが違反0であること(self):
        _, found = inspect("ok_spec", "design.md")
        self.assertEqual(found, [], [str(v) for v in found])

    # 仕様: requirements.md#機械検査-1
    def test_お手本のarchitectureが違反0であること(self):
        _, found = inspect("ok_spec", "architecture.md")
        self.assertEqual(found, [], [str(v) for v in found])

    # 仕様: requirements.md#要点と畳み-4、requirements.md#読み手の区分け-3
    def test_図と図の説明が畳みの外にあっても違反にならないこと(self):
        """否定確認: 図の範囲を見える行から除く処理を外すと「要点が長い」で落ちる"""
        _, found = inspect("ok_spec", "requirements.md")
        self.assertNotIn("要点が長い", kinds(found))
        self.assertNotIn("畳みの外に本文", kinds(found))


class 違反の検出(unittest.TestCase):
    """形が崩れている仕様書から、崩れ方の種類ごとに1件ずつ拾えることを確かめる。"""

    def setUp(self):
        _, self.found = inspect("violations_spec", "requirements.md")

    # 仕様: requirements.md#機械検査-2
    def test_仕込んだ違反が種類ごとに1件ずつ出ること(self):
        """否定確認: 見える行の上限を2行から3行に緩めると「要点が長い」が消えて落ちる"""
        self.assertEqual(kinds(self.found), sorted([
            "章の外に本文", "読み手不明", "畳み過ぎ", "畳み忘れ", "要点が長い",
            "畳みの外に本文", "summary直後に空行なし", "出所なし", "出所が重複"]))

    # 仕様: requirements.md#機械検査-2
    def test_違反にファイル名と見出し名が入ること(self):
        畳み忘れ = [v for v in self.found if v.kind == "畳み忘れ"][0]
        self.assertEqual(畳み忘れ.file_name, "requirements.md")
        self.assertEqual(畳み忘れ.heading, "## 依存関係")

    # 仕様: requirements.md#要点と畳み-3
    def test_畳みの単位が見出しごとに分かれること(self):
        要点が長い = [v for v in self.found if v.kind == "要点が長い"][0]
        self.assertEqual(要点が長い.heading, "## 機能要件 / ### 要点が3行ある機能")

    # 仕様: requirements.md#出所の目印-3
    def test_決定事項の表に出所列が無ければ出所なしになること(self):
        _, found = inspect("violations_spec", "design.md")
        self.assertEqual(kinds(found), ["出所なし"])
        self.assertIn("列なし", found[0].note)

    # 仕様: requirements.md#出所の目印-3
    def test_決定事項の出所列の値が別の語なら出所なしになること(self):
        text = read("ok_spec", "design.md").replace("| テスト | 合意 |", "| テスト | 未定 |")
        scan = markdown_scan.scan(text)
        found = checks.check_provenance("design.md", scan, RULES)
        self.assertEqual(kinds(found), ["出所なし"])

    # 仕様: requirements.md#出所の目印-4
    def test_リスク種別の目印の前後どちらに置いても目印として数えること(self):
        base = read("ok_spec", "requirements.md")
        for 要点 in ("見本として置く機能の1行概要。 〔合意〕",):
            for 書き方 in ("見本として置く機能の1行概要。 〔論理〕 〔合意〕",
                         "見本として置く機能の1行概要。 〔合意〕 〔論理〕"):
                scan = markdown_scan.scan(base.replace(要点, 書き方))
                found = checks.check_provenance("requirements.md", scan, RULES)
                self.assertEqual(found, [], 書き方)

    # 仕様: requirements.md#機械検査-3
    def test_廃止見出しと畳みが同居する文書は廃止見出しの違反になること(self):
        _, found = inspect("legacy_mixed_spec", "requirements.md")
        self.assertIn("廃止見出し", kinds(found))


class 人が読む量の集計(unittest.TestCase):
    """承認者が実際に目にする分量だけを数えていることを確かめる。"""

    # 仕様: requirements.md#機械検査-6
    def test_見えている行の文字数だけを合計すること(self):
        """否定確認: 畳みの中を除く条件を外すと合計が増えて落ちる"""
        scan = markdown_scan.scan(read("counting_spec", "requirements.md"))
        self.assertEqual(checks.count_visible_chars("requirements.md", scan, RULES), 32)

    # 仕様: requirements.md#出所の目印-5
    def test_見えている行の目印を種類ごとに数えること(self):
        scan = markdown_scan.scan(read("counting_spec", "requirements.md"))
        self.assertEqual(checks.count_provenance("requirements.md", scan, RULES),
                         {"合意": 1, "提案": 1})

    # 仕様: requirements.md#機械検査-6
    def test_畳みの中を増やしても人が読む文字数が変わらないこと(self):
        text = read("counting_spec", "requirements.md")
        scan = markdown_scan.scan(text)
        before = checks.count_visible_chars("requirements.md", scan, RULES)
        for 追加 in range(1, 6):
            膨らませた = text.replace(
                "- [2] 畳みの中の目印 〔合意〕",
                "- [2] 畳みの中の目印 〔合意〕\n" + "\n".join(
                    "- [%d] 畳みの中で増やした行 〔提案〕" % (2 + n) for n in range(追加)))
            after = markdown_scan.scan(膨らませた)
            self.assertEqual(checks.count_visible_chars("requirements.md", after, RULES),
                             before, "畳みの中に%d行足した" % 追加)

    # 仕様: requirements.md#出所の目印-5
    def test_畳みの中の目印を増やしても目印の行数が変わらないこと(self):
        text = read("counting_spec", "requirements.md")
        before = checks.count_provenance(
            "requirements.md", markdown_scan.scan(text), RULES)
        for 追加 in range(1, 6):
            膨らませた = text.replace(
                "- [2] 畳みの中の目印 〔合意〕",
                "- [2] 畳みの中の目印 〔合意〕\n" + "\n".join(
                    "- [%d] 畳みの中の目印 〔合意〕" % (2 + n) for n in range(追加)))
            self.assertEqual(checks.count_provenance(
                "requirements.md", markdown_scan.scan(膨らませた), RULES), before)


class 折り返した箇条書き(unittest.TestCase):
    """複数行に折り返した箇条書きを、1つの項目として数えることを確かめる。"""

    折り返しあり = """# 見本

ステータス: 実装中 ／ 優先度: 低

## スコープ外

- 長い項目なので途中で改行しており、
  目印は最後の行の末尾に付いている 〔合意〕
- 1行で収まる項目 〔提案〕
"""

    # 仕様: requirements.md#出所の目印-1、-4
    def test_折り返しの最後の行に目印があれば出所ありと数えること(self):
        """否定確認: 折り返し行を前の行にまとめる処理を外すと「出所なし」で落ちる"""
        scan = markdown_scan.scan(self.折り返しあり)
        found = checks.check_provenance("requirements.md", scan, RULES)
        self.assertEqual(found, [], [str(v) for v in found])

    # 仕様: requirements.md#出所の目印-4
    def test_折り返した項目の目印が無ければ違反1件だけになること(self):
        text = self.折り返しあり.replace("目印は最後の行の末尾に付いている 〔合意〕",
                                   "目印を付け忘れている")
        found = checks.check_provenance("requirements.md", markdown_scan.scan(text), RULES)
        self.assertEqual([v.kind for v in found], ["出所なし"])

    # 仕様: requirements.md#出所の目印-5
    def test_折り返した項目を目印の行数として1つだけ数えること(self):
        scan = markdown_scan.scan(self.折り返しあり)
        self.assertEqual(checks.count_provenance("requirements.md", scan, RULES),
                         {"合意": 1, "提案": 1})


class 要点も畳む見出し(unittest.TestCase):
    """図が概要を担う処理フローでは、要点行を畳みの外に残さないことを確かめる。"""

    図だけ = """# 設計

## 概要

設計の概要。 〔提案〕

## 処理フロー

### 図のある処理

```mermaid
flowchart LR
    a --> b
```

図はこの処理の俯瞰。

<details><summary>詳細を開く</summary>

処理の1行概要。

- **手順**: …

</details>

### もう1つの処理

```mermaid
flowchart LR
    c --> d
```

図はこの処理の俯瞰。

<details><summary>詳細を開く</summary>

処理の1行概要。

- **手順**: …

</details>
"""

    # 仕様: requirements.md#要点と畳み-3a
    def test_図と図の説明だけなら違反0であること(self):
        scan = markdown_scan.scan(self.図だけ)
        found = checks.check_folding("design.md", scan, RULES)
        found += checks.check_provenance("design.md", scan, RULES)
        self.assertEqual(found, [], [str(v) for v in found])

    # 仕様: requirements.md#要点と畳み-3a
    def test_要点行が畳みの外に残っていれば違反になること(self):
        """否定確認: 見える行の上限を見え方から決めず常に2行にすると落ちる"""
        text = self.図だけ.replace("### もう1つの処理\n",
                                "### もう1つの処理\n\n処理の1行概要。 〔提案〕\n")
        scan = markdown_scan.scan(text)
        found = checks.check_folding("design.md", scan, RULES)
        self.assertEqual([v.kind for v in found], ["要点が長い"])
        self.assertEqual(found[0].heading, "## 処理フロー / ### もう1つの処理")


class 一部だけ見せて残りを畳む見出し(unittest.TestCase):
    """決定事項のように、主な行だけ見せて残りを畳む見出しが許されることを確かめる。"""

    決定事項 = """# 設計

## 概要

設計の概要。 〔提案〕

## 決定事項

| 論点 | 選んだ案 | 採らなかった案 | 理由 | 影響範囲 | 出所 |
|---|---|---|---|---|---|
| 置き場 | lib 配下 | skills 配下 | 両方から呼べる | lib | 合意 |

<details><summary>詳細を開く</summary>

書式の細かい取り決め。

| 論点 | 選んだ案 | 採らなかった案 | 理由 | 影響範囲 | 出所 |
|---|---|---|---|---|---|
| 目印の文字 | 亀甲括弧 | 絵文字 | 環境で表示が揺れない | 検査 | 提案 |

</details>
"""

    # 仕様: requirements.md#決定事項の表-4
    def test_人が読む見出しでも見え方に畳むとあれば畳めること(self):
        """否定確認: 人の見出しを一律で畳み過ぎにすると落ちる"""
        scan = markdown_scan.scan(self.決定事項)
        found = checks.check_folding("design.md", scan, RULES)
        self.assertEqual(found, [], [str(v) for v in found])

    # 仕様: requirements.md#出所の目印-3
    def test_畳んだ側の表の出所も検査すること(self):
        text = self.決定事項.replace("| 検査 | 提案 |", "| 検査 | 未定 |")
        found = checks.check_provenance("design.md", markdown_scan.scan(text), RULES)
        self.assertEqual([v.kind for v in found], ["出所なし"])

    # 仕様: requirements.md#出所の目印-5
    def test_畳んだ側の表の行は読む量に数えないこと(self):
        """否定確認: 畳みの中の表も数えると提案が1増えて落ちる"""
        scan = markdown_scan.scan(self.決定事項)
        self.assertEqual(checks.count_provenance("design.md", scan, RULES),
                         {"合意": 1, "提案": 0})


class 図が要る見出し(unittest.TestCase):
    """処理フローの各処理に図が置かれていることを確かめる。"""

    図なし = """# 設計

## 概要

設計の概要。 〔提案〕

## 処理フロー

### 図のない処理

<details><summary>詳細を開く</summary>

処理の1行概要。

</details>
"""

    # 仕様: requirements.md#要点と畳み-3a
    def test_処理フローの処理に図が無ければ違反になること(self):
        """否定確認: 図の有無を見ない実装にすると落ちる"""
        found = checks.check_folding("design.md", markdown_scan.scan(self.図なし), RULES)
        self.assertEqual([v.kind for v in found], ["図なし"])
        self.assertEqual(found[0].heading, "## 処理フロー / ### 図のない処理")

    # 仕様: requirements.md#要点と畳み-3a
    def test_図があれば違反にならないこと(self):
        text = self.図なし.replace("### 図のない処理\n",
                                "### 図のある処理\n\n```mermaid\nflowchart LR\n    a --> b\n```\n\n図は流れの俯瞰。\n")
        found = checks.check_folding("design.md", markdown_scan.scan(text), RULES)
        self.assertEqual(found, [], [str(v) for v in found])


class 概要の見出し(unittest.TestCase):
    """「概要」は必須見出しとして置けることを確かめる。"""

    概要あり = """# 見本

## 概要

| 項目 | 内容 |
|---|---|
| ステータス | 実装中 |
| 優先度 | 高 |

## スコープ外

- 対象外のこと 〔合意〕
"""

    # 仕様: requirements.md#見出しの固定セットと読み手-1
    def test_概要があっても廃止見出しにならないこと(self):
        """否定確認: 廃止見出しの一覧に「概要」を戻すと落ちる"""
        scan = markdown_scan.scan(self.概要あり)
        found = checks.check_folding("requirements.md", scan, RULES)
        found += checks.check_provenance("requirements.md", scan, RULES)
        self.assertEqual(found, [], [str(v) for v in found])

    # 仕様: requirements.md#見出しの固定セットと読み手-1
    def test_サマリは廃止見出しのままであること(self):
        text = self.概要あり.replace("## 概要", "## サマリ")
        found = checks.check_folding("requirements.md", markdown_scan.scan(text), RULES)
        self.assertIn("廃止見出し", [v.kind for v in found])


class 章の外の本文(unittest.TestCase):
    """タイトルと最初の見出しの間に、どの章にも属さない本文が無いことを確かめる。"""

    ラベルだけ = """# 見本

ステータス: 実装中 ／ 優先度: 高

## 概要

見本の概要。 〔合意〕

## スコープ外

- 対象外のこと 〔合意〕
"""

    # 仕様: requirements.md#見出しの固定セットと読み手-3
    def test_タイトル直下がラベル行だけなら違反0であること(self):
        scan = markdown_scan.scan(self.ラベルだけ)
        found = checks.check_folding("requirements.md", scan, RULES)
        self.assertEqual(found, [], [str(v) for v in found])

    # 仕様: requirements.md#見出しの固定セットと読み手-3
    def test_章の外に本文があれば違反になること(self):
        """否定確認: 章の外の本文を見ない実装にすると落ちる"""
        text = self.ラベルだけ.replace("## 概要", "どの章にも属さない文。\n\n## 概要")
        found = checks.check_folding("requirements.md", markdown_scan.scan(text), RULES)
        self.assertEqual([v.kind for v in found], ["章の外に本文"])

    # 仕様: requirements.md#機械検査-6
    def test_章の外の本文は読む量に数えないこと(self):
        scan = markdown_scan.scan(self.ラベルだけ)
        self.assertEqual(checks.count_visible_chars("requirements.md", scan, RULES),
                         len("見本の概要。 〔合意〕") + len("- 対象外のこと 〔合意〕"))


class 小見出しで畳む見出し(unittest.TestCase):
    """`###` ごとに畳むと定めた見出しが、`###` を持たないまま通らないことを確かめる。"""

    小見出しなし = """# 見本

ステータス: 実装中 ／ 優先度: 低

## 概要

見本の概要。 〔提案〕

## 機能要件

機能全体の1行概要。 〔提案〕

<details><summary>詳細を開く</summary>

- [1] 機能ごとに分けていない 〔論理〕

</details>
"""

    # 仕様: requirements.md#要点と畳み-3
    def test_小見出しが無ければ違反になること(self):
        """否定確認: `###` の有無を見ない実装にすると、機能要件全体で1行しか
        見えない文書が素通りして落ちる"""
        found = checks.check_folding("requirements.md",
                                     markdown_scan.scan(self.小見出しなし), RULES)
        self.assertEqual([v.kind for v in found], ["小見出しなし"])
        self.assertEqual(found[0].heading, "## 機能要件")

    # 仕様: requirements.md#要点と畳み-3
    def test_小見出しがあれば違反にならないこと(self):
        text = self.小見出しなし.replace(
            "## 機能要件\n\n機能全体の1行概要。 〔提案〕",
            "## 機能要件\n\n### ある機能\n\n機能の1行概要。 〔提案〕")
        found = checks.check_folding("requirements.md", markdown_scan.scan(text), RULES)
        self.assertEqual(found, [], [str(v) for v in found])


class 入れ子のコードフェンス(unittest.TestCase):
    """4連フェンスの中に3連フェンスを書いた書式例で誤判定しないことを確かめる。"""

    入れ子 = """# 設計

## 概要

設計の概要。 〔提案〕

## ログ

書式の例を載せる。 〔提案〕

<details><summary>詳細を開く</summary>

````markdown
## エラーハンドリング

<要点>

```mermaid
flowchart LR
    a --> b
```

<details><summary>詳細を開く</summary>

(本文)

</details>
````

</details>
"""

    # 仕様: requirements.md#機械検査-5
    def test_入れ子のフェンスの中身を実体として扱わないこと(self):
        """否定確認: 閉じフェンスの長さを見ない実装にすると、内側の ``` で
        閉じたことになり偽陽性が出て落ちる"""
        scan = markdown_scan.scan(self.入れ子)
        found = checks.check_folding("design.md", scan, RULES)
        found += checks.check_provenance("design.md", scan, RULES)
        self.assertEqual(found, [], [str(v) for v in found])



class 章の外に置ける行(unittest.TestCase):
    """ラベル1行の例外が requirements.md のタイトル直下だけに効くことを確かめる。"""

    本文 = "## 概要\n\n全体像。 〔提案〕\n"

    def 違反(self, file_name, text):
        return [v.kind for v in checks.check_folding(
            file_name, markdown_scan.scan(text), RULES)]

    # 仕様: requirements.md#見出しの固定セットと読み手-3
    def test_requirements_mdの1行目のラベルは違反にしないこと(self):
        self.assertNotIn(checks.KIND_TEXT_OUTSIDE_SECTION, self.違反(
            "requirements.md",
            "# 題\n\nステータス: 実装中 ／ 優先度: 高\n\n" + self.本文))

    # 仕様: requirements.md#見出しの固定セットと読み手-3
    def test_design_mdのラベル行は章の外に本文にすること(self):
        """否定確認: 例外をファイルで絞らないと、この行が見逃されて落ちる"""
        self.assertIn(checks.KIND_TEXT_OUTSIDE_SECTION, self.違反(
            "design.md", "# 題\n\nステータス: 実装中 ／ 優先度: 高\n\n" + self.本文))

    # 仕様: requirements.md#見出しの固定セットと読み手-3
    def test_ラベル行が2行あれば2行目を違反にすること(self):
        """否定確認: 例外を1行目に絞らないと、2行目が見逃されて落ちる"""
        違反 = self.違反("requirements.md",
                     "# 題\n\nステータス: 実装中 ／ 優先度: 高\n"
                     "ステータス: もう1行\n\n" + self.本文)
        self.assertEqual(違反.count(checks.KIND_TEXT_OUTSIDE_SECTION), 1, 違反)

if __name__ == "__main__":
    unittest.main()
