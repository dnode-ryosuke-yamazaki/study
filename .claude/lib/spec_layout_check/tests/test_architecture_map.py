"""~/.claude 側 architecture.md の機能一覧表の構造検証。

機能一覧表は複数のセッションが同時に触る唯一の表で、進捗の見え方がここに集まる。
状態が本文の文章に紛れていると、状態別に数えることも並べ替えることもできないため、
列として持っていることを見張る。

このテストは worktree の外にある実ファイル(`~/.claude/local-specs/.../architecture.md`)を
読む。他セッションもこの表を編集するため、他セッションが規約を破ればここが落ちる。
それは検知したい事象そのものなので、fixture の写しには置き換えない。

仕様: ~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers/
  requirements.md#architecture.md の機能一覧表-1、-2、-3、design.md#architecture.md の状態列
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

SPECS_ROOT = Path(os.path.expanduser(
    "~/.claude/local-specs/Users/ryosyamazaki/.claude/specs"))
ARCHITECTURE = SPECS_ROOT / "architecture.md"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_spec_layout.py"

HEADING = "## 機能一覧表(機能マップ)"
STATUS_VALUES = ("仕様のみ(未実装)", "実装中", "リリース済み")
STATUS_WORDS = ("実装済み", "実装中", "リリース済み", "仕様のみ")


def feature_table():
    """機能一覧表のヘッダーとデータ行を返す。"""
    with open(str(ARCHITECTURE), encoding="utf-8") as fp:
        text = fp.read()
    body = text[text.index(HEADING) + len(HEADING):]
    header, rows = None, []
    for line in body.split("\n"):
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if header is None:
            header = cells
        elif set("".join(cells)) <= set("-: "):
            continue
        else:
            rows.append(cells)
    return header, rows


class 機能一覧表(unittest.TestCase):
    """全体の進捗を状態列だけで追えることを確かめる。"""

    def setUp(self):
        self.assertTrue(ARCHITECTURE.exists(), "architecture.md が見つからない")
        self.header, self.rows = feature_table()

    # 仕様: requirements.md#architecture.md の機能一覧表-1
    def test_見出し名と状態列があること(self):
        self.assertIn("状態", self.header)
        self.assertTrue(self.rows)

    # 仕様: requirements.md#architecture.md の機能一覧表-1
    def test_状態列の値が3段階のいずれかであること(self):
        """否定確認: どれか1行の状態を「実装済み」に変えると落ちる"""
        index = self.header.index("状態")
        for row in self.rows:
            self.assertIn(row[index], STATUS_VALUES, row[0])

    # 仕様: requirements.md#architecture.md の機能一覧表-2
    def test_何をするか列に状態の文言が残っていないこと(self):
        """否定確認: どれか1行の説明に「実装済み」を書き足すと落ちる"""
        index = self.header.index("何をするか")
        for row in self.rows:
            for 文言 in STATUS_WORDS:
                self.assertNotIn(文言, row[index], "%s に %s が残っている" % (row[0], 文言))


class 検査スクリプトを通した結果(unittest.TestCase):
    """機能一覧表を含む architecture.md 全体が新形式で書けていることを確かめる。"""

    # 仕様: requirements.md#機械検査-1、完了時の確認
    def test_architectureが違反0で通ること(self):
        done = subprocess.run([sys.executable, str(SCRIPT), str(SPECS_ROOT)],
                              capture_output=True, text=True)
        違反 = [line for line in done.stdout.rstrip("\n").split("\n")
               if line and line.split("\t")[2] not in
               ("人が読む文字数", "合意の行数", "提案の行数")]
        self.assertEqual(違反, [], done.stdout)
        self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":
    unittest.main()
