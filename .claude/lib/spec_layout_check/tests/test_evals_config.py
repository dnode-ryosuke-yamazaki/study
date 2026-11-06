"""evals(promptfoo)の設定とテスト方針の構造検証。

evalsは1回あたり数分・数万トークンかかるため、毎回は回せない。新しい書式を
採点する assert が設定から落ちていないことだけは、手元で軽く見張っておく。

仕様: ~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers/
  requirements.md#SKILL.md の骨格-3、design.md#テスト戦略
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVALS = ROOT / ("eval" + "s")


def read(path):
    with open(str(path), encoding="utf-8") as fp:
        return fp.read()


class 要件定義の採点基準(unittest.TestCase):
    """新形式の成果物を採点する assert が入っていることを確かめる。"""

    def setUp(self):
        self.text = read(EVALS / "requirement.promptfooconfig.yaml")

    # 仕様: requirements.md#見出しの固定セットと読み手-1
    def test_骨格の必須5見出しを採点していること(self):
        """否定確認: contains-all から「## スコープ外」を消すと落ちる"""
        for 見出し in ("## ユーザーストーリー", "## ユースケース図", "## 機能要件",
                     "## ビジネスルール", "## スコープ外"):
            self.assertIn("'%s'" % 見出し, self.text)

    # 仕様: requirements.md#見出しの固定セットと読み手-1
    def test_廃止した見出しを不合格にする判定があること(self):
        self.assertIn("not-icontains-any", self.text)
        self.assertIn("廃止した見出し", self.text)

    # 仕様: requirements.md#出所の目印-1
    def test_出所の目印を両方採点していること(self):
        self.assertIn("'〔合意〕'", self.text)
        self.assertIn("'〔提案〕'", self.text)

    # 仕様: requirements.md#分量-1
    def test_数値ルール6件の依頼で分割提案を採点するケースがあること(self):
        self.assertIn("数値ルールが6件ある依頼では、specの分割を提案する", self.text)
        self.assertIn("'分割'", self.text)


class 設計の採点基準(unittest.TestCase):
    """決定事項・畳み・付録分離を採点する assert があることを確かめる。"""

    def setUp(self):
        self.text = read(EVALS / "design.promptfooconfig.yaml")

    # 仕様: requirements.md#決定事項の表-1
    def test_決定事項と出所列と畳みを採点していること(self):
        """否定確認: '| 出所 |' の行を消すと落ちる"""
        for 値 in ("'## 決定事項'", "'| 出所 |'",
                   "'<details><summary>詳細を開く</summary>'"):
            self.assertIn(値, self.text)

    # 仕様: requirements.md#AI専用情報の付録分離-2
    def test_付録の分離を判断つきで採点していること(self):
        """否定確認: 付録の判定を消すと落ちる

        付録に回す書式が無い機能もあるので、appendix.md の存在を無条件には求めない。
        書式があるのに本文に置いていないか、を見る。
        """
        self.assertIn("appendix.md", self.text)
        self.assertIn("無い場合は appendix.md を作っていない", self.text)

    # 仕様: requirements.md#見出しの固定セットと読み手-2
    def test_サマリを不合格にする判定があること(self):
        self.assertIn("value: '## サマリ'", self.text)
        self.assertIn("not-icontains", self.text)



    # 仕様: design.md#テスト戦略、test-policy.md#テスト種別の定義
    def test_採点基準のテスト種別がテスト方針と揃っていること(self):
        """否定確認: 採点基準に「手動」を種別として書き戻すと落ちる

        test-policy.md は「手動確認はテスト種別ではない」と定めている。採点基準が
        古い種別名を要求していると、方針どおりに書いた設計書が落ちる(実際に起きた)。
        """
        self.assertNotIn("単体/結合/E2E/手動", self.text)
        for 種別 in ("単体", "契約", "構造検証", "環境スモーク", "性能"):
            self.assertIn(種別, self.text)

    # 仕様: design.md#テスト戦略
    def test_タスクの件数行の一致を採点していること(self):
        """否定確認: 件数行の判定を消すと落ちる"""
        self.assertIn("件数行", self.text)

    # 仕様: design.md#テスト戦略
    def test_本文だけを出させる指示があること(self):
        """否定確認: この指示を消すと落ちる

        応答の本文の外に書いた補足も判定の対象になるため、本文だけを出させないと
        「本文は正しいのに補足の語で落ちる」「注記で読み替えを求めて済ませる」が起きる。
        """
        # 特別指示と依頼文の両方に置く(片方だけ消えても気づけるように数で見る)
        self.assertEqual(self.text.count("前置き・補足・注記"), 2)
        self.assertIn("本文そのものを直した状態", self.text)

    # 仕様: design.md#tasks.md の書き方
    def test_件数行を最後のタスクの番号から書かせていること(self):
        """否定確認: 「最後のタスクの番号」の規定を消すと落ちる

        「数えて書く」だけの指示では、書き手が総件数を4回続けて間違えた
        (evals の実行で毎回落ちた)。数え上げずに写せる形にする。
        """
        text = read(ROOT / "skills" / "design" / "SKILL.md")
        self.assertIn("最後のタスクの番号がそのまま総件数", text)
        self.assertIn("タスク <最後のタスクの番号>件", text)

class レビューの採点基準(unittest.TestCase):
    """決定事項の網羅漏れと、検査の起動失敗を採点していることを確かめる。"""

    def setUp(self):
        self.text = read(EVALS / "spec-review.promptfooconfig.yaml")
        self.fixture = read(EVALS / "fixtures" / "spec-review" / "design.md")

    # 仕様: requirements.md#決定事項の表-2
    def test_本文の却下が表に無い欠陥をfixtureに仕込んであること(self):
        """否定確認: fixture の決定事項の表にセキュリティの行を足すと、この欠陥が消える"""
        self.assertIn("## 決定事項", self.fixture)
        self.assertIn("採らず", self.fixture)
        表 = self.fixture[self.fixture.index("## 決定事項"):self.fixture.index("## 処理フロー")]
        self.assertNotIn("条件式", 表)

    # 仕様: requirements.md#決定事項の表-2
    def test_表の網羅漏れを検出する条件が採点基準にあること(self):
        self.assertIn("決定事項の表に", self.text)
        self.assertIn("網羅漏れ", self.text)

    # 仕様: requirements.md#機械検査-9
    def test_検査の起動失敗が修正必須として出ることを採点していること(self):
        self.assertIn("'起動失敗'", self.text)
        self.assertIn("'🔴'", self.text)


class テスト方針(unittest.TestCase):
    """テスト戦略表に書ける種別名が定義されていることを確かめる。"""

    # 仕様: design.md#テスト戦略
    def test_手順書の検証の種別名がevalsとして明記されていること(self):
        """否定確認: 種別名の明記を消すと落ちる"""
        text = read(ROOT / "test-policy.md")
        self.assertIn("種別名を `evals` と書く", text)

    # 仕様: design.md#テスト戦略
    def test_書ける種別名の一覧が方針と手順書の両方にあること(self):
        """否定確認: どちらかから一覧を消すと落ちる

        参照先を読ませるだけだと、書き手が「結合」のような一般的な呼び名を
        持ち込む(evals の実行で実際に起きた)。書く場所に名前を並べておく。
        """
        for path in (ROOT / "test-policy.md", ROOT / "skills" / "design" / "SKILL.md"):
            text = read(path)
            self.assertIn("「結合」", text, "%s に使わない呼び名の明示が無い" % path.name)
            for 種別 in ("単体", "性質", "契約", "構造検証", "環境スモーク", "性能"):
                self.assertIn(種別, text, "%s に種別名「%s」が無い" % (path.name, 種別))


if __name__ == "__main__":
    unittest.main()
