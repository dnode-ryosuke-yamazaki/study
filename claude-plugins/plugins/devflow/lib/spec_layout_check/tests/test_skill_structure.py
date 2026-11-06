"""開発フローSkillの手順書(SKILL.md)とレビュー基準の構造検証。

書き手も承認者も、手順書に書いてあるとおりに文書を作り読む。手順書から規定が
落ちると、検査スクリプトだけが新しい形を求めて書き手は古い形で書き続けるという
食い違いが起きるため、規定の文言が残っていることを字句で見張る。

仕様: ~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers/
  requirements.md#SKILL.md の骨格、requirements.md#出所の目印の運用、
  requirements.md#既存specの扱い、requirements.md#分量、requirements.md#appendix.md、
  requirements.md#決定事項の表の運用
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC_LAYOUT = ROOT / "quality-standards" / "base" / "spec-layout.md"

REQUIRED_HEADINGS = ("概要", "ユーザーストーリー", "ユースケース図", "機能要件",
                     "ビジネスルール・制約", "スコープ外")
OPTIONAL_HEADINGS = ("非機能要件", "依存関係", "UI/UX要件")
# 「概要」はステータス・優先度を置く必須見出しとして残す。廃止したのは「サマリ」だけ
ABOLISHED_HEADINGS = ("サマリ",)

SKELETON_FENCE = re.compile(r"^````+markdown\s*$")


def read(*parts):
    with open(str(ROOT.joinpath(*parts)), encoding="utf-8") as fp:
        return fp.read()


HOME_CLAUDE = Path("~/.claude").expanduser()


def read_home(*parts):
    """プラグインに移さずホーム(~/.claude)に残した全PJ共通文書を読む。"""
    with open(str(HOME_CLAUDE.joinpath(*parts)), encoding="utf-8") as fp:
        return fp.read()


def skeleton_blocks(text):
    """````markdown で囲んだ文書骨格のブロック本文を返す。"""
    blocks = []
    current = None
    for line in text.split("\n"):
        if current is None:
            if SKELETON_FENCE.match(line):
                current = []
            continue
        if line.startswith("````") and not line.strip("`"):
            blocks.append("\n".join(current))
            current = None
            continue
        current.append(line)
    return blocks


def skeleton_headings(text, level="## "):
    found = []
    for block in skeleton_blocks(text):
        for line in block.split("\n"):
            if line.startswith(level) and not line.startswith(level + "#"):
                found.append(line[len(level):].strip())
    return found


def layout_headings(file_name):
    """区分け表に載っている、そのファイルの見出し名。"""
    found = []
    started = False
    for line in read("quality-standards", "base", "spec-layout.md").split("\n"):
        if not started:
            if line.startswith("#") and line.lstrip("#").strip() == "読み手の区分け":
                started = True
            continue
        if not line.startswith("|"):
            if found:
                break
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 3 or cells[0] != file_name:
            continue
        for heading in cells[1].split(" / "):
            heading = heading.strip()
            if heading.startswith("(") or heading == "上記以外":
                continue
            found.append(heading)
    return found


class 要件定義の手順書(unittest.TestCase):
    """書き手が写す骨格と、目印・分量・既存specの扱いの規定があることを確かめる。"""

    def setUp(self):
        self.text = read("skills", "requirement", "SKILL.md")
        self.skeleton = "\n".join(skeleton_blocks(self.text))

    # 仕様: requirements.md#見出しの固定セットと読み手-1
    def test_骨格に必須5と任意3の見出しが揃っていること(self):
        """否定確認: 骨格から「スコープ外」を消すと落ちる"""
        headings = skeleton_headings(self.text)
        for heading in REQUIRED_HEADINGS + OPTIONAL_HEADINGS:
            self.assertIn(heading, headings)

    # 仕様: requirements.md#見出しの固定セットと読み手-1
    def test_骨格に廃止した見出しが残っていないこと(self):
        headings = skeleton_headings(self.text)
        for heading in ABOLISHED_HEADINGS:
            self.assertNotIn(heading, headings)

    # 仕様: requirements.md#見出しの固定セットと読み手-1
    def test_必須と任意の区別が本文に書かれていること(self):
        self.assertIn("必須6", self.text)
        self.assertIn("任意3", self.text)

    # 仕様: requirements.md#見出しの固定セットと読み手-4、SKILL.md の骨格-1
    def test_骨格の見出しが区分け表と一致すること(self):
        """否定確認: 骨格に区分け表に無い見出しを足すと落ちる"""
        self.assertEqual(sorted(set(skeleton_headings(self.text))),
                         sorted(set(layout_headings("requirements.md"))))

    # 仕様: requirements.md#見出しの固定セットと読み手-3
    def test_章の外に本文を置かない規定があること(self):
        """否定確認: 「タイトルと最初の`##`の間に本文を置かない」を消すと落ちる"""
        self.assertIn("タイトルと最初の`##`の間に本文を置かない", self.text)
        self.assertIn("ステータスと優先度のラベル1行", self.text)
        self.assertIn("ステータス: 仕様確認中(未実装) ／ 優先度:", self.skeleton)

    # 仕様: requirements.md#読み手に伝わる書き方-1
    def test_概要に作るものと何のために要るかを書く規定があること(self):
        self.assertIn("この仕様で作るものと、それが何のために要るか", self.text)
        self.assertIn("作るものを名前だけ並べない", self.text)

    # 仕様: requirements.md#要点と畳み-1、-5
    def test_骨格に要点と畳みのタグが埋まっていること(self):
        block = "\n".join(skeleton_blocks(self.text))
        self.assertIn("<details><summary>詳細を開く</summary>", block)
        self.assertIn("</details>", block)

    # 仕様: requirements.md#出所の目印-1、出所の目印の運用-1
    def test_骨格に出所の目印の置き場があること(self):
        block = "\n".join(skeleton_blocks(self.text))
        self.assertIn("〔合意〕", block)
        self.assertIn("〔提案〕", block)

    # 仕様: requirements.md#出所の目印の運用-1
    def test_迷ったら提案にする規定があること(self):
        """否定確認: 「迷ったら`〔提案〕`」の1行を消すと落ちる"""
        self.assertIn("迷ったら`〔提案〕`", self.text)

    # 仕様: requirements.md#出所の目印の運用-4
    def test_骨格の目印は例だと書いてあること(self):
        """否定確認: この規定を消すと落ちる

        骨格をそのまま写すと全行が `〔合意〕` になり、承認者が読むべき行を
        読み飛ばす(evals の初回実行で実際に起きた)。
        """
        self.assertIn("骨格に書いてある目印は置き場所の例", self.text)
        self.assertIn("全部`〔合意〕`になったら", self.text)

    # 仕様: requirements.md#見出しの固定セットと読み手-5
    def test_読み手宣言の書き方があること(self):
        self.assertIn("> 読み手: AI", self.text)

    # 仕様: requirements.md#既存specの扱い-1、-2
    def test_既存specを一括で書き換えない規定があること(self):
        self.assertIn("一括で新形式に書き換えない", self.text)
        self.assertIn("部分適用の状態", self.text)

    # 仕様: requirements.md#分量-1
    def test_数値ルールが5件を超えたら分割を提案する規定があること(self):
        self.assertIn("5件を超えたら", self.text)
        self.assertIn("分割", self.text)

    # 仕様: requirements.md#読み手に伝わる書き方-1、-2
    def test_中間成果物の目的と中身を初出で書く規定があること(self):
        """否定確認: 「誰が何のために使うか」の1文を消すと落ちる"""
        self.assertIn("読み手に伝わる書き方", self.text)
        self.assertIn("誰が何のために使うか", self.text)
        self.assertIn("何が入っているか", self.text)
        self.assertIn("名前を出すだけでは", self.text)

    # 仕様: requirements.md#読み手に伝わる書き方-2
    def test_目的をどの行に書くかが決まっていること(self):
        self.assertIn("それを使う機能要件の要点行", self.text)
        self.assertIn("その成果物を定義しているビジネスルールの要点行", self.text)

    # 仕様: requirements.md#読み手に伝わる書き方-6
    def test_主語と対象を省かない規定があること(self):
        """否定確認: 「主語と対象を省かない」の節を消すと落ちる"""
        self.assertIn("主語と対象を省かない", self.text)
        self.assertIn("何が(誰が)・何に対して", self.text)
        self.assertIn("どのファイルか", self.text)

    # 仕様: requirements.md#読み手に伝わる書き方-3
    def test_用語集を前段に置かない規定があること(self):
        self.assertIn("用語の説明を前段に並べない", self.text)

    # 仕様: requirements.md#読み手に伝わる書き方-5
    def test_長い説明を図に置き換えてよい規定があること(self):
        self.assertIn("図を1枚置いて説明を短くしてよい", self.text)


class 出す前の読み返し(unittest.TestCase):
    """書いた本人が、承認者と同じ行を読み返してから出す規定があることを確かめる。"""

    # 仕様: requirements.md#機械検査-10
    def test_要件定義と設計の完了前に読み返す規定があること(self):
        """否定確認: 「出す前に、承認者と同じものを読み返す」の節を消すと落ちる"""
        for skill in ("requirement", "design"):
            text = read("skills", skill, "SKILL.md")
            self.assertIn("出す前に、承認者と同じものを読み返す", text, skill)
            self.assertIn("--visible", text, skill)
            self.assertIn("完了報告にそのまま貼る", text, skill)

    # 仕様: requirements.md#機械検査-10
    def test_レビューにも同じ行を渡す規定があること(self):
        text = read("skills", "spec-review", "SKILL.md")
        self.assertIn("--visible", text)
        self.assertIn("文脈を持たない読み手として読ませる", text)


class 実装の手順書(unittest.TestCase):
    """自分のspecが決めた完了条件を、実測で確かめてから終わる規定があることを確かめる。"""

    def setUp(self):
        self.text = read("skills", "implementation", "SKILL.md")

    # 仕様: requirements.md#非機能要件-1、tasks.md#完了時の確認
    def test_完了時の確認を実測値で埋める規定があること(self):
        """否定確認: 「実測値を添えて埋める」の1文を消すと落ちる"""
        self.assertIn("tasks.mdの「完了時の確認」に書いた項目は、実測値を添えて埋める",
                      self.text)
        self.assertIn("満たしていない場合は満たすまで直してから完了とする", self.text)


class 修正の手順書(unittest.TestCase):
    """旧形式のspecに触るときに新形式へ直す手順があることを確かめる。"""

    def setUp(self):
        self.text = read("skills", "fix", "SKILL.md")

    # 仕様: requirements.md#SKILL.md の骨格-4、既存specの扱い-2
    def test_旧形式を新形式へ直す手順があること(self):
        """否定確認: 「新形式化」の節を消すと落ちる"""
        self.assertIn("旧形式", self.text)
        self.assertIn("新形式", self.text)
        self.assertIn("check_spec_layout.py", self.text)

    # 仕様: requirements.md#出所の目印の運用-3
    def test_承認済みは合意で改修分は提案にする規定があること(self):
        self.assertIn("承認済みだった内容の行は`〔合意〕`", self.text)
        self.assertIn("この改修で追加・変更した行は`〔提案〕`", self.text)

    # 仕様: requirements.md#既存specの扱い-2
    def test_片方だけ直さない規定があること(self):
        self.assertIn("片方だけにしない", self.text)


class 設計の手順書(unittest.TestCase):
    """決定事項の表・付録分離・件数行の規定があることを確かめる。"""

    def setUp(self):
        self.text = read("skills", "design", "SKILL.md")
        self.skeleton = "\n".join(skeleton_blocks(self.text))

    # 仕様: requirements.md#見出しの固定セットと読み手-2
    def test_骨格が概要で始まり決定事項が続くこと(self):
        """否定確認: 骨格で決定事項を処理フローの後ろに移すと落ちる"""
        self.assertEqual(skeleton_headings(self.text)[:2], ["概要", "決定事項"])

    # 仕様: requirements.md#見出しの固定セットと読み手-7
    def test_決定事項の直後に品質統制の適用の6行があること(self):
        """否定確認: 骨格から IMC-03 の行を消すと落ちる"""
        self.assertEqual(skeleton_headings(self.text)[:3],
                         ["概要", "決定事項", "品質統制の適用"])
        self.assertIn("| 統制 | 判定 | 理由 | 反映先 | 出所 |", self.skeleton)
        for 番号 in range(1, 7):
            self.assertIn("| IMC-%02d " % 番号, self.skeleton)

    # 仕様: requirements.md#見出しの固定セットと読み手-7
    def test_統制の定義は標準側が正と書いてあること(self):
        """観点を書き直しただけで、CSVを複製していないことを示す文言を見張る"""
        self.assertIn("implementation-control-catalog.csv", self.text)
        self.assertIn("ここには判定に要る観点だけを書き直している", self.text)

    # 仕様: requirements.md#見出しの固定セットと読み手-2
    def test_サマリを必須とする規定が残っていないこと(self):
        self.assertNotIn("サマリ(必須)", self.text)
        self.assertNotIn("サマリ", skeleton_headings(self.text))

    # 仕様: requirements.md#SKILL.md の骨格-1
    def test_骨格の見出しが区分け表と一致すること(self):
        self.assertEqual(sorted(set(skeleton_headings(self.text))),
                         sorted(set(layout_headings("design.md"))))

    # 仕様: requirements.md#決定事項の表-1、出所の目印-3
    def test_骨格の決定事項が出所列を含む6列であること(self):
        """否定確認: 骨格の表から出所列を落とすと落ちる"""
        self.assertIn("| 論点 | 選んだ案 | 採らなかった案 | 理由 | 影響範囲 | 出所 |",
                      self.skeleton)

    # 仕様: requirements.md#決定事項の表-3
    def test_分かれ道が無いときの書き方があること(self):
        self.assertIn("決定事項なし", self.text)

    # 仕様: requirements.md#決定事項の表の運用-1
    def test_理由列の長さとADR分離の規定があること(self):
        self.assertIn("「理由」列は**1〜2行**に収める", self.text)
        self.assertIn("ADRに分離", self.text)

    # 仕様: requirements.md#決定事項の表の運用-2
    def test_採らなかった案が無いときはなしと書く規定があること(self):
        self.assertIn("「なし」と書く", self.text)

    # 仕様: requirements.md#要点と畳み-1、-3
    def test_処理フローの骨格が図を畳みより先に出すこと(self):
        処理フロー = self.skeleton[self.skeleton.index("## 処理フロー"):]
        処理フロー = 処理フロー[:処理フロー.index("\n## ", 3)]
        self.assertIn("<details><summary>詳細を開く</summary>", 処理フロー)
        self.assertLess(処理フロー.index("```mermaid"),
                        処理フロー.index("<details><summary>詳細を開く</summary>"))

    # 仕様: requirements.md#出所の目印-1
    def test_骨格に出所の目印の置き場があること(self):
        self.assertIn("〔合意〕", self.skeleton)
        self.assertIn("〔提案〕", self.skeleton)

    # 仕様: requirements.md#AI専用情報の付録分離-1、-2、appendix.md-2
    def test_付録分離の規定があること(self):
        """否定確認: appendix.md の節を消すと落ちる"""
        self.assertIn("appendix.md", self.text)
        self.assertIn("リンクを1行残す", self.text)
        self.assertIn("手順・分岐・方針は置かない", self.text)

    # 仕様: requirements.md#要点と畳み-7
    def test_tasksの冒頭に件数行を置く雛形があること(self):
        self.assertIn("タスク <最後のタスクの番号>件(claude <件数> / copilot <件数>)", self.text)

    # 仕様: requirements.md#要点と畳み-7、読み手に伝わる書き方-6
    def test_tasksのタスク名と目的の規定があること(self):
        """否定確認: タスク名と目的の箇条書きを消すと落ちる"""
        self.assertIn("開かなくても何をするかが分かる言い方", self.text)
        self.assertIn("そのタスクが要る理由を書く", self.text)
        self.assertIn("タスク名でも主語と対象を省かない", self.text)

    # 仕様: requirements.md#要点と畳み-7
    def test_tasksがタスク名と担当マークだけを見せる雛形であること(self):
        """否定確認: tasks.md の雛形から `<details>` を外すと落ちる"""
        雛形 = self.text[self.text.index("タスク <最後のタスクの番号>件"):]
        雛形 = 雛形[:雛形.index("````")] if "````" in 雛形 else 雛形[:600]
        self.assertIn("【担当: claude】", 雛形)
        self.assertIn("<何のための作業か1行>", 雛形)
        self.assertIn("<details><summary>詳細を開く</summary>", 雛形)

    # 仕様: requirements.md#要点と畳み-3a
    def test_処理フローの骨格が図だけを畳みの外に出すこと(self):
        """否定確認: 骨格の処理フローに要点行を戻すと落ちる"""
        見出しの次 = self.skeleton.split("### <処理の呼び名>", 1)[1].lstrip("\n")
        self.assertTrue(見出しの次.startswith("```mermaid"), 見出しの次[:40])

    # 仕様: requirements.md#要点と畳み-3a
    def test_処理フローの各見出しに図を置く規定があること(self):
        """否定確認: 「各`###`には図を1枚置く」の1文を消すと落ちる"""
        self.assertIn("各`###`には図を1枚置く", self.text)
        self.assertIn("図を描くほどの流れが無い処理は`###`を立てず", self.text)

    # 仕様: requirements.md#決定事項の表-4
    def test_決定事項は見せる範囲を絞り残りは畳んで残す規定があること(self):
        """否定確認: 「捨てず、…2つ目の表として残す」を消すと落ちる"""
        self.assertIn("畳みの外に見せるのは承認者の判断に効く分かれ道だけ", self.text)
        self.assertIn("2つ目の表として残す", self.text)
        self.assertIn("残りの決定は折りたたみの中", self.skeleton)


class 全体像の手順書(unittest.TestCase):
    """architecture.md の骨格と機能一覧表の規定があることを確かめる。"""

    def setUp(self):
        self.text = read("skills", "architecture-workflow", "SKILL.md")
        self.skeleton = "\n".join(skeleton_blocks(self.text))

    # 仕様: requirements.md#SKILL.md の骨格-1
    def test_骨格の見出しが区分け表と食い違わないこと(self):
        """区分け表の architecture.md は「上記以外」の行を持つため、人が読むと
        定めた見出しの側だけを突き合わせる。骨格に人見出しを勝手に増やさない。

        否定確認: 骨格に区分け表に無い人見出しを足すと落ちる
        """
        人の見出し = set(layout_headings("architecture.md"))
        骨格 = set(skeleton_headings(self.text))
        self.assertTrue(骨格 & 人の見出し, 骨格)
        for 必須 in ("コンテキスト図", "システム構成図", "機能一覧表(機能マップ)"):
            self.assertIn(必須, 骨格)

    # 仕様: requirements.md#architecture.md の機能一覧表-1
    def test_機能一覧表の見出し名と状態列の規定があること(self):
        self.assertIn("機能一覧表(機能マップ)", self.text)
        self.assertIn("仕様のみ(未実装)", self.text)
        self.assertIn("リリース済み", self.text)

    # 仕様: requirements.md#見出しの固定セットと読み手-2
    def test_サマリを必須とする規定が残っていないこと(self):
        self.assertNotIn("サマリ(必須)", self.text)
        self.assertNotIn("サマリ", skeleton_headings(self.text))

    # 仕様: requirements.md#要点と畳み-1、出所の目印-1
    def test_骨格に畳みと目印の置き場があること(self):
        self.assertIn("<details><summary>詳細を開く</summary>", self.skeleton)
        self.assertIn("〔提案〕", self.skeleton)


class レビューの手順書と基準(unittest.TestCase):
    """検査スクリプトの実行と、指摘の扱いが決まっていることを確かめる。"""

    def setUp(self):
        self.skill = read("skills", "spec-review", "SKILL.md")
        self.base = read("quality-standards", "base", "spec-review.md")
        self.pr = read("skills", "pr", "SKILL.md")

    # 仕様: requirements.md#機械検査-4
    def test_レビュー前に検査スクリプトを実行する規定があること(self):
        """否定確認: 起動コマンドの行を消すと落ちる"""
        self.assertIn("check_spec_layout.py", self.skill)

    # 仕様: requirements.md#機械検査-2、-3
    def test_終了コードごとの扱いが書かれていること(self):
        for 文言 in ("違反あり", "旧形式", "区分け表が読めない", "違反なし"):
            self.assertIn(文言, self.skill)

    # 仕様: requirements.md#機械検査-9
    def test_検査を起動できない場合の扱いがあること(self):
        self.assertIn("起動失敗", self.skill)

    # 仕様: requirements.md#出所の目印の運用-2
    def test_合意した覚えのない合意の扱いが手順書と基準の両方にあること(self):
        self.assertIn("合意した覚えのない〔合意〕", self.skill)
        self.assertIn("合意した覚えのない〔合意〕", self.base)

    # 仕様: requirements.md#SKILL.md の骨格-2
    def test_レビュー基準に決定事項の網羅確認と機械検査の項目があること(self):
        """否定確認: 基準から決定事項の網羅確認の行を消すと落ちる"""
        self.assertIn("本文で選択・却下を述べている箇所が、決定事項の表に1行ずつ載っているか",
                      self.base)
        self.assertIn("機械検査の違反は1件を🔴(修正必須)の指摘1件として扱う", self.base)
        self.assertIn("合意した覚えのない〔合意〕", self.base)

    # 仕様: requirements.md#SKILL.md の骨格-2
    def test_レビュー基準にサマリ章を求める項目が残っていないこと(self):
        """削除の対象は requirements.md・design.md・architecture.md の各節。
        本specのスコープ外である system-test.md の節はそのまま残す。

        否定確認: 削除した3項目のどれかを戻すと落ちる
        """
        for 項目 in ("先頭に**サマリ**章があり、この章だけで概略",
                    "先頭に**サマリ**章があり、処理の全体像",
                    "必須4つ(サマリ・"):
            self.assertNotIn(項目, self.base)

    # 仕様: requirements.md#architecture.md の機能一覧表-1
    def test_レビュー基準の見出し名が機能一覧表に揃っていること(self):
        self.assertIn("機能一覧表(機能マップ)", self.base)

    # 仕様: requirements.md#読み手に伝わる書き方-1、-3、-4
    def test_レビュー基準に読み手に伝わる書き方の項目があること(self):
        """否定確認: 追加した項目のどれかを消すと落ちる"""
        self.assertIn("名前の初出で「誰が何のために使うか」", self.base)
        self.assertIn("その行だけを読んで意味が取れるか", self.base)
        self.assertIn("主語(何が・誰が)と対象(何を・どのファイルを)が省かれていないか",
                      self.base)
        self.assertIn("用語の説明だけを並べた節", self.base)
        self.assertIn("開かなくても何をするか分かる言い方", self.base)

    # 仕様: requirements.md#appendix.md-1
    def test_仕様承認PRの対象にappendixが含まれること(self):
        """否定確認: PR本文テンプレートから appendix.md を消すと落ちる"""
        self.assertIn("appendix.md を含めてPRを出し", self.pr)
        self.assertIn("requirements.md / design.md / tasks.md / appendix.md", self.pr)

    # 仕様: skills/requirement/SKILL.md#画面モックの作り方(置き場所と正本)
    def test_仕様承認PRの対象に画面モックが含まれること(self):
        """否定確認: PR本文テンプレートから mock.html を消すと落ちる"""
        self.assertIn("mock.html・appendix.md を含めてPRを出し", self.pr)
        self.assertIn("appendix.md / mock.html", self.pr)



class プレビューでの目印の見せ方(unittest.TestCase):
    """承認者が読むHTMLで、提案の行が見分けられる規定が残っていることを確かめる。"""

    # 仕様: requirements.md#出所の目印の運用-5
    def test_提案の行に下地を敷く規定があること(self):
        """否定確認: この規定を消すと落ちる

        目印が本文と同じ見え方だと、承認者が読むべき行を目で探すことになる。
        specごとに見た目が変わるのも手がかりにならないので、1か所で決める。
        """
        text = read_home("deliverable-preview.md")
        self.assertIn("目立たせるのは提案側", text)
        self.assertIn(".row-proposed", text)
        # 目印は行の下地とは別に、それ自体で読めるバッジにする。
        # 薄い素の文字にすると、行がほとんど〔提案〕のspecでラベルが埋もれる
        self.assertIn(".mark.agreed", text)
        self.assertIn(".mark.proposed", text)
        self.assertIn("ラベルだけで見分けられる", text)
        self.assertNotIn("opacity: .65", text)
        # 見せ方の正がどこかは区分け表のファイルからも辿れるようにする
        self.assertIn("deliverable-preview.md", read("quality-standards", "base", "spec-layout.md"))

if __name__ == "__main__":
    unittest.main()
