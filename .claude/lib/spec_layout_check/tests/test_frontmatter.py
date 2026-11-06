"""承認状態のフロントマター(status / approved_date / version)の検査。

承認の有無を会話とPRだけで持つと、仕様書を開いた人には承認済みかどうかが読めず、
承認後に黙って書き換わっても気づけない。フロントマターの形を字句で照合し、
持たない既存specは違反の山にせず「移行が要る」状態(終了コード2)として返す。

仕様: ~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers/
  requirements.md#機械検査-11、-12、appendix.md#承認フロントマターの書式
"""
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_spec_layout
import checks
import markdown_scan

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REAL_TABLE = Path(__file__).resolve().parents[3] / "quality-standards" / "base" / "spec-layout.md"

APPROVED = '---\nstatus: approved\napproved_date: 2026-10-01\nversion: "1.0"\n---\n\n'
DRAFT = '---\nstatus: draft\nversion: "0.1"\n---\n\n'
TASKS = "# 見本 タスク\n\n全1件。\n"


def run(spec):
    out, err = io.StringIO(), io.StringIO()
    code = check_spec_layout.main(
        [str(spec)], layout_path=str(REAL_TABLE), stdout=out, stderr=err)
    return code, out.getvalue()


def rows(output):
    return [line.split("\t") for line in output.rstrip("\n").split("\n") if line]


def notes_of(text, name="requirements.md"):
    violations, missing = checks.check_frontmatter(name, markdown_scan.scan(text))
    return [v.note for v in violations], missing


class OkSpec:
    """ok_spec を一時フォルダへ写し、フロントマターだけを差し替えられるようにする。"""

    def __enter__(self):
        self.dir = tempfile.mkdtemp()
        for name in ("requirements.md", "design.md"):
            shutil.copy(FIXTURES / "ok_spec" / name, Path(self.dir) / name)
        return Path(self.dir)

    def __exit__(self, *exc):
        shutil.rmtree(self.dir)


def replace_head(path, head):
    """先頭のフロントマターを head に置き換える(head が空なら外す)。"""
    text = path.read_text(encoding="utf-8")
    body = text.split("---\n", 2)[2].lstrip("\n")
    path.write_text(head + body, encoding="utf-8")


class フロントマターの走査(unittest.TestCase):

    def test_先頭のフロントマターをキーと値に分け引用符を外すこと(self):
        scan = markdown_scan.scan(APPROVED + "# 題\n\n## 概要\n\n本文。\n")
        self.assertEqual(scan.frontmatter, {
            "status": "approved", "approved_date": "2026-10-01", "version": "1.0"})
        self.assertEqual(scan.frontmatter_end, 5)

    def test_フロントマターの行を章の外に本文として拾わないこと(self):
        """否定確認: 走査の開始行をフロントマターの後ろにしないと5行拾って落ちる"""
        scan = markdown_scan.scan(DRAFT + "# 題\n\n## 概要\n\n本文。\n")
        self.assertEqual(scan.outside_section_lines, [])

    def test_閉じの無い区切り線はフロントマターにしないこと(self):
        scan = markdown_scan.scan("---\nstatus: draft\n\n# 題\n\n## 概要\n")
        self.assertIsNone(scan.frontmatter)
        self.assertIn((1, "---"), scan.outside_section_lines)

    def test_1行目以外の区切り線はフロントマターにしないこと(self):
        scan = markdown_scan.scan("# 題\n\n---\nstatus: draft\n---\n\n## 概要\n")
        self.assertIsNone(scan.frontmatter)


class フロントマターの値の照合(unittest.TestCase):
    """値が規則に合わないものを「フロントマター不正」として1件ずつ返す。"""

    def test_規則どおりの値なら違反にしないこと(self):
        for head in (APPROVED, DRAFT,
                     '---\nstatus: in-review\nversion: "1.1"\n---\n',
                     '---\ntype: requirements\nstatus: draft\nversion: 0.2\n---\n'):
            self.assertEqual(notes_of(head + "# 題\n"), ([], False), head)

    def test_フロントマターが無ければ違反ではなく無しと返すこと(self):
        self.assertEqual(notes_of("# 題\n\n## 概要\n"), ([], True))

    def test_statusの値が3つのどれでもなければ違反になること(self):
        notes, _ = notes_of('---\nstatus: done\nversion: "1.0"\n---\n')
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("status", notes[0])

    def test_statusかversionが無ければ違反になること(self):
        notes, _ = notes_of('---\napproved_date: 2026-10-01\n---\n')
        self.assertTrue(any("status が無い" in n for n in notes), notes)
        self.assertTrue(any("version が無い" in n for n in notes), notes)

    def test_versionが数字ドット数字でなければ違反になること(self):
        for version in ("1", "v1.0", "1.0.0", "一.〇"):
            notes, _ = notes_of('---\nstatus: draft\nversion: "%s"\n---\n' % version)
            self.assertEqual(len(notes), 1, (version, notes))

    def test_approvedなのにapproved_dateが無いか日付でなければ違反になること(self):
        """否定確認: approved の日付の照合を外すと2件とも通って落ちる"""
        for head in ('---\nstatus: approved\nversion: "1.0"\n---\n',
                     '---\nstatus: approved\napproved_date: 2026-13-01\nversion: "1.0"\n---\n'):
            notes, _ = notes_of(head)
            self.assertEqual(len(notes), 1, (head, notes))
            self.assertIn("approved_date", notes[0])

    def test_approvedでないのにapproved_dateがあれば違反になること(self):
        """承認後に draft へ戻すときは approved_date を消す。残すと承認済みと読み違える"""
        notes, _ = notes_of(
            '---\nstatus: draft\napproved_date: 2026-10-01\nversion: "1.1"\n---\n')
        self.assertEqual(len(notes), 1, notes)

    def test_approvedなのにversionが1未満なら違反になること(self):
        notes, _ = notes_of(
            '---\nstatus: approved\napproved_date: 2026-10-01\nversion: "0.1"\n---\n')
        self.assertEqual(len(notes), 1, notes)


class フロントマターの終了コード(unittest.TestCase):
    """フロントマター無しは状態(2)、不正は違反(1)として呼び出し側に伝わる。"""

    # 仕様: requirements.md#機械検査-11
    def test_フロントマターが無いファイルがあれば違反にせず2で終わること(self):
        """否定確認: 無しを違反に数えると既存specが全部1になって落ちる"""
        with OkSpec() as spec:
            replace_head(spec / "design.md", "")
            code, out = run(spec)
        self.assertEqual(code, 2, out)
        無し = [r for r in rows(out) if r[2] == "フロントマター無し"]
        self.assertEqual([r[0] for r in 無し], ["design.md"])

    # 仕様: requirements.md#機械検査-11
    def test_フロントマター不正は違反として1で終わること(self):
        with OkSpec() as spec:
            replace_head(spec / "requirements.md", '---\nstatus: approved\nversion: "1.0"\n---\n\n')
            code, out = run(spec)
        self.assertEqual(code, 1, out)
        self.assertIn("フロントマター不正", [r[2] for r in rows(out)])

    # 仕様: requirements.md#機械検査-11
    def test_tasksmdはフロントマターだけを検査すること(self):
        """tasks.md は層分けの対象外。件数行だけの本文でも、文字数の補足行を出さない"""
        with OkSpec() as spec:
            (spec / "tasks.md").write_text(TASKS, encoding="utf-8")
            code, out = run(spec)
            self.assertEqual(code, 2, out)
            self.assertEqual([r[0] for r in rows(out) if r[2] == "フロントマター無し"],
                             ["tasks.md"])
            self.assertNotIn("tasks.md", [r[0] for r in rows(out)
                                          if r[2] == "人が読む文字数"])

            (spec / "tasks.md").write_text(DRAFT + TASKS, encoding="utf-8")
            code, out = run(spec)
        self.assertEqual(code, 0, out)

    # 仕様: requirements.md#機械検査-7
    def test_tasksmdだけのフォルダは対象ファイルが無いとして1で終わること(self):
        with tempfile.TemporaryDirectory() as spec:
            (Path(spec) / "tasks.md").write_text(DRAFT + TASKS, encoding="utf-8")
            code, out = run(spec)
        self.assertEqual(code, 1, out)
        self.assertIn("読めない", [r[2] for r in rows(out)])

    # 仕様: requirements.md#機械検査-3、-11
    def test_旧形式のファイルにはフロントマター無しと旧形式の両方を出すこと(self):
        code, out = run(FIXTURES / "legacy_spec")
        self.assertEqual(code, 2, out)
        種別 = [r[2] for r in rows(out) if r[0] == "requirements.md"]
        self.assertIn("旧形式", 種別)
        self.assertIn("フロントマター無し", 種別)

    # 仕様: requirements.md#機械検査-11
    def test_architecturemdにはフロントマターを求めないこと(self):
        code, out = run(FIXTURES / "ok_spec")
        self.assertEqual(code, 0, out)
        self.assertNotIn("フロントマター無し", [r[2] for r in rows(out)])


if __name__ == "__main__":
    unittest.main()
