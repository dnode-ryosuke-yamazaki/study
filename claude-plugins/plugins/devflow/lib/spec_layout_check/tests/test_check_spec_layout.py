"""検査スクリプトの入口(引数・出力・終了コード)のテスト。

検査が動かなかったことを「違反なし」と取り違えると、レビューは検査した気になった
まま素通りする。読めないファイル・予期しない例外・区分け表の破損のいずれでも、
黙って0で終わらないことを確かめる。

仕様: ~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers/
  requirements.md#機械検査-2、-3、-7、-8、design.md#結果の出力
"""
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_spec_layout

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_spec_layout.py"
REAL_TABLE = Path(__file__).resolve().parents[3] / "quality-standards" / "base" / "spec-layout.md"


def run(spec, layout=None):
    out, err = io.StringIO(), io.StringIO()
    code = check_spec_layout.main(
        [str(spec)], layout_path=str(layout or REAL_TABLE), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def rows(output):
    return [line.split("\t") for line in output.rstrip("\n").split("\n") if line]


def kinds(output):
    return [row[2] for row in rows(output)]


class 検査の終了コード(unittest.TestCase):
    """検査の結果が呼び出し側に4つの状態として伝わることを確かめる。"""

    # 仕様: requirements.md#機械検査-1
    def test_新形式で違反が無ければ違反なしで終わること(self):
        code, out, err = run(FIXTURES / "ok_spec")
        self.assertEqual(code, 0, out)
        self.assertEqual(err, "")

    # 仕様: requirements.md#機械検査-2
    def test_違反があれば違反ありで終わること(self):
        code, out, _ = run(FIXTURES / "violations_spec")
        self.assertEqual(code, 1)
        self.assertIn("畳み忘れ", kinds(out))

    # 仕様: requirements.md#機械検査-3
    def test_旧形式のファイルだけなら旧形式で終わり違反を出さないこと(self):
        """否定確認: 旧形式の判定を外すと既存specが違反の山になって落ちる"""
        code, out, _ = run(FIXTURES / "legacy_spec")
        self.assertEqual(code, 2, out)
        self.assertIn("旧形式", kinds(out))
        self.assertNotIn("廃止見出し", kinds(out))

    # 仕様: requirements.md#機械検査-7
    def test_designが無いspecでも残りのファイルを検査して終わること(self):
        code, out, _ = run(FIXTURES / "no_design_spec")
        self.assertEqual(code, 0, out)
        self.assertNotIn("design.md", [row[0] for row in rows(out)])

    # 仕様: requirements.md#機械検査-7
    def test_対象ファイルが1つも無ければ違反ありで終わること(self):
        with tempfile.TemporaryDirectory() as empty:
            code, out, _ = run(empty)
        self.assertEqual(code, 1)
        self.assertIn("読めない", kinds(out))

    # 仕様: requirements.md#機械検査-7
    def test_存在しないパスでも違反ありで終わること(self):
        code, out, _ = run(FIXTURES / "存在しないspec")
        self.assertEqual(code, 1)

    # 仕様: requirements.md#機械検査-7
    def test_文字コードが不正なファイルは違反1件として記録し他を検査し続けること(self):
        with tempfile.TemporaryDirectory() as spec:
            with open(os.path.join(spec, "requirements.md"), "wb") as fp:
                fp.write(b"# \xff\xfe\xff\n")
            broken = Path(spec) / "architecture.md"
            broken.write_text(
                (FIXTURES / "ok_spec" / "architecture.md").read_text(encoding="utf-8"),
                encoding="utf-8")
            code, out, _ = run(spec)
        self.assertEqual(code, 1)
        読めない = [row for row in rows(out) if row[2] == "読めない"]
        self.assertEqual([row[0] for row in 読めない], ["requirements.md"])
        self.assertIn("人が読む文字数", kinds(out))

    # 仕様: design.md#エラーハンドリング
    def test_区分け表が読めなければ検査を中断して専用のコードで終わること(self):
        with tempfile.TemporaryDirectory() as bad:
            layout = Path(bad) / "spec-layout.md"
            layout.write_text("# 表がありません\n", encoding="utf-8")
            code, out, err = run(FIXTURES / "ok_spec", layout=layout)
        self.assertEqual(code, 3)
        self.assertIn("区分け表", out + err)


class 検査結果の出力(unittest.TestCase):
    """結果がそのままレビューの起動指示に貼れる形であることを確かめる。"""

    # 仕様: requirements.md#機械検査-2
    def test_出力の各行がタブ区切りの4列であること(self):
        """否定確認: どれか1行の列を3列に減らすと落ちる"""
        _, out, _ = run(FIXTURES / "violations_spec")
        for row in rows(out):
            self.assertEqual(len(row), 4, row)

    # 仕様: requirements.md#機械検査-6、requirements.md#出所の目印-5
    def test_末尾に人が読む文字数と目印別の行数が出ること(self):
        _, out, _ = run(FIXTURES / "ok_spec")
        末尾 = kinds(out)[-6:]
        self.assertEqual(末尾, ["人が読む文字数", "合意の行数", "提案の行数",
                               "人が読む文字数", "合意の行数", "提案の行数"])
        合計 = rows(out)[-3:]
        self.assertTrue(all(row[0] == "requirements.md+design.md" for row in 合計), 合計)

    # 仕様: requirements.md#機械検査-6
    def test_人が読む文字数が数値で出ること(self):
        _, out, _ = run(FIXTURES / "counting_spec")
        文字数 = [row for row in rows(out) if row[2] == "人が読む文字数"][0]
        self.assertEqual(文字数[3], "32")


class 予期しない例外(unittest.TestCase):
    """検査そのものが壊れたときに「違反なし」で終わらないことを確かめる。"""

    # 仕様: requirements.md#機械検査-8
    def test_走査で例外が起きたら標準エラーにトレースを出して違反ありで終わること(self):
        """否定確認: 例外を握りつぶして0で返す実装にすると落ちる"""
        original = check_spec_layout.checks.check_folding

        def 爆発する(*args, **kwargs):
            raise RuntimeError("注入した例外")

        check_spec_layout.checks.check_folding = 爆発する
        try:
            code, out, err = run(FIXTURES / "ok_spec")
        finally:
            check_spec_layout.checks.check_folding = original
        self.assertEqual(code, 1)
        self.assertIn("Traceback", err)
        self.assertIn("注入した例外", err)


class コマンドとしての起動(unittest.TestCase):
    """付録に書いた起動コマンドの形でそのまま動くことを確かめる。"""

    # 仕様: appendix.md#起動コマンド
    def test_python3から直接起動できること(self):
        done = subprocess.run(
            [sys.executable, str(SCRIPT), str(FIXTURES / "ok_spec")],
            capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("人が読む文字数", done.stdout)


class 承認者が見る行だけを出す(unittest.TestCase):
    """書き手が出す前に、承認者と同じものを読み返せることを確かめる。"""

    # 仕様: requirements.md#機械検査-10
    def test_visibleを付けると見えている行だけが順に出ること(self):
        """否定確認: 畳みの中の行を出す実装にすると落ちる"""
        out, err = io.StringIO(), io.StringIO()
        code = check_spec_layout.main(
            ["--visible", str(FIXTURES / "ok_spec")],
            layout_path=str(REAL_TABLE), stdout=out, stderr=err)
        self.assertEqual(code, 0, out.getvalue())
        text = out.getvalue()
        self.assertIn("見本として置く機能の1行概要。 〔合意〕", text)
        self.assertNotIn("見本であること", text)  # 畳みの中の行
        self.assertIn("requirements.md", text)

    # 仕様: requirements.md#機械検査-10
    def test_visibleでも違反があれば違反ありで終わること(self):
        out, err = io.StringIO(), io.StringIO()
        code = check_spec_layout.main(
            ["--visible", str(FIXTURES / "violations_spec")],
            layout_path=str(REAL_TABLE), stdout=out, stderr=err)
        self.assertEqual(code, 1)


class 既存specを壊さない旧形式の判定(unittest.TestCase):
    """新形式が「概要」を持つようになっても、既存specを違反の山にしないことを確かめる。"""

    # 仕様: requirements.md#機械検査-3
    def test_折りたたみも目印も無い既存specが旧形式と判定されること(self):
        """否定確認: 見出し名で旧形式を判定すると、違反の山になって落ちる"""
        with tempfile.TemporaryDirectory() as spec:
            (Path(spec) / "requirements.md").write_text(
                "# 既存のspec\n\n## 概要\n\n昔の書き方で書かれた仕様。\n\n"
                "## 機能要件\n\n- [1] 何かをすること\n", encoding="utf-8")
            code, out, _ = run(spec)
        self.assertEqual(code, 2, out)
        self.assertIn("旧形式", kinds(out))
        self.assertNotIn("章の外に本文", kinds(out))

    # 仕様: requirements.md#機械検査-3
    def test_人が読む見出しだけの文書を旧形式と判定しないこと(self):
        """否定確認: 「折りたたみも目印も無い」だけで判定すると、AI見出しを持たない
        正しい architecture.md まで検査対象外になって落ちる"""
        with tempfile.TemporaryDirectory() as spec:
            (Path(spec) / "architecture.md").write_text(
                "# 見本アプリの全体像\n\n## 概要\n\n人が読む見出しだけで足りるアプリ。\n\n"
                "## サマリ\n\n廃止した見出しなので違反になるはず。\n\n"
                "## 機能一覧表(機能マップ)\n\n| spec | 状態 |\n|---|---|\n| a | 実装中 |\n",
                encoding="utf-8")
            code, out, _ = run(spec)
        self.assertNotIn("旧形式", kinds(out))
        self.assertIn("廃止見出し", kinds(out))
        self.assertEqual(code, 1, out)

    # 仕様: requirements.md#機械検査-3
    def test_人の見出しだけの書きかけを旧形式と判定しないこと(self):
        """概要とユーザーストーリーまで書いた途中の文書は、検査して直させる。

        畳むべきAIの見出しがまだ無いので、条件②を満たさず旧形式にならない。
        """
        with tempfile.TemporaryDirectory() as spec:
            (Path(spec) / "requirements.md").write_text(
                "# 書きかけ\n\n## 概要\n\nこれから書く。\n\n"
                "## ユーザーストーリー\n\n- まだ目印を付けていない\n", encoding="utf-8")
            code, out, _ = run(spec)
        self.assertNotIn("旧形式", kinds(out))
        self.assertIn("出所なし", kinds(out))

    # 仕様: requirements.md#機械検査-3
    def test_AIの見出しまで書いた書きかけは旧形式と同じ判定になること(self):
        """畳みも目印もまだ入れていない書きかけは、旧形式と文字面が同じで見分けられない。

        機械では区別できないので、/spec-review が終了コード2を🔴として書き手に
        戻すことで埋める(skills/spec-review/SKILL.md の終了コードの表)。
        この挙動が変わったら手順書側も同時に直すため、現状をテストで固定する。
        """
        with tempfile.TemporaryDirectory() as spec:
            (Path(spec) / "requirements.md").write_text(
                "# 書きかけ\n\n## 概要\n\nこれから書く。\n\n"
                "## 機能要件\n\n### ある機能\n\nまだ畳んでいない。\n", encoding="utf-8")
            code, out, _ = run(spec)
        self.assertIn("旧形式", kinds(out))
        self.assertEqual(code, 2, out)

    # 仕様: requirements.md#機械検査-3
    def test_旧形式と違反が混ざっても他のファイルの違反で終わること(self):
        """旧形式のファイルの分は違反に数えず、他のファイルの違反だけで終了コードを決める。

        否定確認: 旧形式のファイルの違反を捨てずに数えると、件数が合わずに落ちる。
        """
        with tempfile.TemporaryDirectory() as spec:
            (Path(spec) / "requirements.md").write_text(
                "# 旧形式\n\n## サマリ\n\nまとめ。\n\n"
                "## 機能要件\n\n### ある機能\n\n畳んでいない本文。\n", encoding="utf-8")
            (Path(spec) / "design.md").write_text(
                "# 設計\n\n## 概要\n\n全体像。 〔提案〕\n\n"
                "## セキュリティ\n\n畳み忘れの本文。 〔提案〕\n", encoding="utf-8")
            code, out, _ = run(spec)
        行 = [line.split("\t") for line in out.strip().split("\n") if line]
        旧形式の行 = [r for r in 行 if r[0] == "requirements.md" and r[2] == "旧形式"]
        self.assertEqual(len(旧形式の行), 1, out)
        self.assertNotIn("廃止見出し", kinds(out))          # 旧形式のファイルの違反は捨てる
        self.assertIn("畳み忘れ", kinds(out))                # 他のファイルの違反は残る
        self.assertEqual(code, 1, out)

    # 仕様: requirements.md#機械検査-3
    def test_旧形式と違反0の新形式が混ざっても旧形式の終了コードになること(self):
        """終了コード2は「旧形式のファイルだけ」ではない。

        違反0の新形式ファイルと混ざっていても、旧形式のファイルが1つでもあれば2。
        否定確認: 判定順を入れ替えて違反なし(0)を先に返すと落ちる。
        """
        with tempfile.TemporaryDirectory() as spec:
            (Path(spec) / "requirements.md").write_text(
                "# 旧形式\n\n## サマリ\n\nまとめ。\n\n"
                "## 機能要件\n\n### ある機能\n\n畳んでいない本文。\n", encoding="utf-8")
            (Path(spec) / "design.md").write_text(
                "# 設計\n\n## 概要\n\n全体像。 〔提案〕\n\n"
                "## セキュリティ\n\n要点。 〔提案〕\n\n"
                "<details><summary>詳細を開く</summary>\n\n- 対象: …\n\n</details>\n",
                encoding="utf-8")
            code, out, _ = run(spec)
        self.assertIn("旧形式", kinds(out))
        self.assertEqual(code, 2, out)

    # 仕様: requirements.md#機械検査-3
    def test_目印があれば旧形式と判定しないこと(self):
        """折りたたみか出所の目印があれば新形式。見出し名では判定しない。"""
        with tempfile.TemporaryDirectory() as spec:
            (Path(spec) / "architecture.md").write_text(
                "# 新しいspec\n\n## 概要\n\n新しい書き方の全体像。 〔提案〕\n\n"
                "## 機能一覧表(機能マップ)\n\n| spec | 状態 |\n|---|---|\n| a | 実装中 |\n",
                encoding="utf-8")
            code, out, _ = run(spec)
        self.assertNotIn("旧形式", kinds(out))
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
