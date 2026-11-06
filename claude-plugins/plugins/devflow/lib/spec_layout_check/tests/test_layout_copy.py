"""区分け表の写し検査。

仕様書(requirements.md)に載っている読み手の区分け表と、機械が読む正である
quality-standards/base/spec-layout.md の表が食い違うと、人が読む仕様と検査の
判定がずれる。2つを1文字も違わない写しとして保つ。
"""

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
SPEC_LAYOUT = os.path.join(REPO_ROOT, "quality-standards", "base", "spec-layout.md")
REQUIREMENTS = os.path.expanduser(
    "~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/"
    "spec-reading-layers/requirements.md")

TABLE_HEADING = "読み手の区分け"


def read_lines(path):
    with open(path, encoding="utf-8") as fp:
        return fp.read().split("\n")


def extract_table(lines, heading_text):
    """見出し `heading_text` より後に最初に現れる表の行だけを返す。"""
    started = False
    table = []
    for line in lines:
        if not started:
            if line.lstrip("#").strip() == heading_text and line.startswith("#"):
                started = True
            continue
        if line.startswith("|"):
            table.append(line.rstrip())
        elif table:
            break
    return table


class 区分け表の写し検査(unittest.TestCase):
    """仕様書の区分け表と機械が読む区分け表が同じ内容であることを確かめる。"""

    # 仕様: requirements.md#見出しの固定セットと読み手-4
    def test_仕様書の表と検査が読む表が行単位で一致すること(self):
        """否定確認: spec-layout.md の表から1行消すと落ちる"""
        self.assertTrue(os.path.exists(SPEC_LAYOUT),
                        "spec-layout.md が見つからない: %s" % SPEC_LAYOUT)
        self.assertTrue(os.path.exists(REQUIREMENTS),
                        "requirements.md が見つからない: %s" % REQUIREMENTS)
        expected = extract_table(read_lines(REQUIREMENTS), TABLE_HEADING)
        actual = extract_table(read_lines(SPEC_LAYOUT), TABLE_HEADING)
        self.assertTrue(expected, "requirements.md から区分け表を取り出せない")
        self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
