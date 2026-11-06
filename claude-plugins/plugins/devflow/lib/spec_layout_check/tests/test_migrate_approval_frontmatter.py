"""既存specへ承認フロントマターを付ける移行スクリプトのテスト。

承認の有無を機械で決めてよいのは、実装に入った(=承認を経た)ことがステータス行から
読める spec だけ。それ以外を推測で approved にすると、承認していない仕様が承認済みに
見えてしまうので「要判断」で止まることを確かめる。

仕様: ~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers/
  requirements.md#既存specの扱い-3
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
import migrate_approval_frontmatter as migrate

REQ = "# 見本\n\nステータス: %s ／ 優先度: 中\n\n## 概要\n\n本文。\n"
DESIGN = "# 見本(設計)\n\n## 概要\n\n全体像。\n"
TASKS = "# 見本 タスク\n\n全1件。\n"


def write_spec(spec, label="リリース済み", tasks=True):
    (Path(spec) / "requirements.md").write_text(
        REQ % label if label else "# 見本\n\n## 概要\n\n本文。\n", encoding="utf-8")
    (Path(spec) / "design.md").write_text(DESIGN, encoding="utf-8")
    if tasks:
        (Path(spec) / "tasks.md").write_text(TASKS, encoding="utf-8")


def git(spec, *args, date=None):
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1")
    if date:
        env.update(GIT_AUTHOR_DATE=date + "T12:00:00", GIT_COMMITTER_DATE=date + "T12:00:00")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                   cwd=spec, env=env, check=True, capture_output=True)


def run(*argv):
    out = io.StringIO()
    code = migrate.main(list(argv), stdout=out)
    return code, [line.split("\t") for line in out.getvalue().rstrip("\n").split("\n") if line]


def head(path, lines=5):
    return Path(path).read_text(encoding="utf-8").split("\n")[:lines]


class 試し実行(unittest.TestCase):

    def test_applyを付けなければ書き込まないこと(self):
        with tempfile.TemporaryDirectory() as spec:
            write_spec(spec)
            before = Path(spec, "requirements.md").read_text(encoding="utf-8")
            run("--approved-date", "2026-10-01", spec)
            self.assertEqual(Path(spec, "requirements.md").read_text(encoding="utf-8"), before)


class 承認状態の推定(unittest.TestCase):

    def test_実装中かリリース済みならapprovedと1点0を付けること(self):
        for label in ("実装中", "リリース済み"):
            with tempfile.TemporaryDirectory() as spec:
                write_spec(spec, label)
                code, rows = run("--apply", "--approved-date", "2026-10-01", spec)
                self.assertEqual(code, 0, rows)
                for name in ("requirements.md", "design.md", "tasks.md"):
                    self.assertEqual(
                        head(Path(spec, name)),
                        ["---", "status: approved", "approved_date: 2026-10-01",
                         'version: "1.0"', "---"], name)

    def test_承認日を指定しなければ最後にコミットした日を使うこと(self):
        with tempfile.TemporaryDirectory() as spec:
            write_spec(spec)
            git(spec, "init", "-q")
            git(spec, "add", ".")
            git(spec, "commit", "-q", "-m", "初版", date="2026-09-01")
            Path(spec, "design.md").write_text(DESIGN + "\n追記。\n", encoding="utf-8")
            git(spec, "commit", "-q", "-am", "設計を直す", date="2026-09-15")
            code, rows = run("--apply", spec)
            self.assertEqual(code, 0, rows)
            self.assertIn("approved_date: 2026-09-01", head(Path(spec, "requirements.md")))
            self.assertIn("approved_date: 2026-09-15", head(Path(spec, "design.md")))

    def test_コミット履歴が無く日付も無ければ要判断にして書かないこと(self):
        with tempfile.TemporaryDirectory() as spec:
            write_spec(spec)
            code, rows = run("--apply", spec)
            self.assertEqual(code, 2, rows)
            self.assertEqual({row[2] for row in rows}, {"要判断"})
            self.assertEqual(head(Path(spec, "requirements.md"), 1), ["# 見本"])

    def test_仕様確認中やステータス行が無ければ要判断にして書かないこと(self):
        """否定確認: 推定できないものを draft や approved で埋めると書き込まれて落ちる"""
        for label in ("仕様確認中(未実装)", None):
            with tempfile.TemporaryDirectory() as spec:
                write_spec(spec, label)
                code, rows = run("--apply", "--approved-date", "2026-10-01", spec)
                self.assertEqual(code, 2, (label, rows))
                self.assertEqual({row[2] for row in rows}, {"要判断"})
                self.assertEqual(head(Path(spec, "design.md"), 1), ["# 見本(設計)"])

    def test_引用で書いた旧いステータス行も読むこと(self):
        with tempfile.TemporaryDirectory() as spec:
            write_spec(spec)
            Path(spec, "requirements.md").write_text(
                "# 見本\n\n> ステータス: 実装中\n\n## 概要\n", encoding="utf-8")
            code, _ = run("--apply", "--approved-date", "2026-10-01", spec)
            self.assertEqual(code, 0)
            self.assertIn("status: approved", head(Path(spec, "requirements.md")))

    def test_statusを指定すれば推定せずその値で付けること(self):
        with tempfile.TemporaryDirectory() as spec:
            write_spec(spec, None)
            code, _ = run("--apply", "--status", "draft", spec)
            self.assertEqual(code, 0)
            self.assertEqual(head(Path(spec, "tasks.md"), 4),
                             ["---", "status: draft", 'version: "0.1"', "---"])


class 移行後の検査(unittest.TestCase):

    def test_既にフロントマターのあるファイルには重ねて付けないこと(self):
        with tempfile.TemporaryDirectory() as spec:
            write_spec(spec)
            run("--apply", "--approved-date", "2026-10-01", spec)
            code, rows = run("--apply", "--approved-date", "2026-11-01", spec)
            self.assertEqual(code, 0)
            self.assertEqual({row[2] for row in rows}, {"移行済み"})
            self.assertIn("approved_date: 2026-10-01", head(Path(spec, "requirements.md")))

    def test_移行したspecは検査でフロントマター無しにならないこと(self):
        with tempfile.TemporaryDirectory() as spec:
            write_spec(spec)
            run("--apply", "--approved-date", "2026-10-01", spec)
            out = io.StringIO()
            check_spec_layout.main([spec], stdout=out, stderr=io.StringIO())
        self.assertNotIn("フロントマター無し", out.getvalue())
        self.assertNotIn("フロントマター不正", out.getvalue())
        self.assertNotIn("章の外に本文", out.getvalue())

    def test_不正な引数は1で終わること(self):
        self.assertEqual(run("--status", "in-review", "x")[0], 1)
        self.assertEqual(run("--approved-date", "2026/10/01", "x")[0], 1)


if __name__ == "__main__":
    unittest.main()
