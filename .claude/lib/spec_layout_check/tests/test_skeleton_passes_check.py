"""手順書の骨格どおりに書いた文書が、検査スクリプトを通ることの検査。

手順書(SKILL.md)の骨格と検査スクリプトは別々に育つため、片方だけ直すと
「手順書どおりに書いたのに検査で落ちる」状態になる。見出し名の一致だけでは
この食い違いを拾えないので、骨格を実際のMarkdownとして組み立てて検査に通す。

仕様: ~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers/
  requirements.md#SKILL.md の骨格-1、requirements.md#機械検査-1
"""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_spec_layout.py"
LAYOUT = ROOT / "quality-standards" / "base" / "spec-layout.md"

SKELETON_FENCE = re.compile(r"^````+markdown\s*$")

# 骨格に残る差し込み口。検査は字句だけを見るので、中身は何でもよいが
# 「<...>」のままだとHTMLタグに見える行が出るため、無難な文字に置き換える
PLACEHOLDER = re.compile(r"<[^<>\n]{1,60}>")
# `<details>` などのHTMLタグは差し込み口ではないので置き換えない
HTML_TAG = re.compile(r"^</?(details|summary|br|code|pre|p|ul|ol|li|table|tr|td|th"
                      r"|strong|em|a|div|span|img)\b", re.I)


def skeleton_of(skill):
    """SKILL.md の文書骨格(````markdown のブロック)を1つ返す。"""
    text = (ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    lines, block, current = text.split("\n"), None, None
    for line in lines:
        if current is None:
            if SKELETON_FENCE.match(line):
                current = []
            continue
        if line.startswith("````") and not line.strip("`"):
            block = "\n".join(current)
            break
        current.append(line)
    return block


def fill(skeleton):
    """差し込み口を埋めて、そのまま検査に通せるMarkdownにする。"""
    def 置換(match):
        return match.group(0) if HTML_TAG.match(match.group(0)) else "ここに書く"

    return PLACEHOLDER.sub(置換, skeleton)


def run_check(spec_dir):
    done = subprocess.run(
        [sys.executable, str(SCRIPT), str(spec_dir)],
        capture_output=True, text=True)
    違反 = [line for line in done.stdout.rstrip("\n").split("\n")
           if line and line.split("\t")[2] not in
           ("人が読む文字数", "合意の行数", "提案の行数")]
    return done.returncode, 違反, done.stderr


class 骨格どおりに書いた文書(unittest.TestCase):
    """書き手が手順書を写したとおりに書けば、検査に通ることを確かめる。"""

    # 仕様: requirements.md#SKILL.md の骨格-1、requirements.md#機械検査-1
    def test_3つの手順書の骨格を写した文書が違反0で通ること(self):
        """否定確認: 骨格の最初の `##` より前に本文を1行戻すと「章の外に本文」で落ちる"""
        骨格 = {"requirements.md": skeleton_of("requirement"),
              "design.md": skeleton_of("design"),
              "architecture.md": skeleton_of("architecture-workflow")}
        for name, block in 骨格.items():
            self.assertIsNotNone(block, "%s の骨格が見つからない" % name)

        with tempfile.TemporaryDirectory() as spec:
            for name, block in 骨格.items():
                (Path(spec) / name).write_text(fill(block) + "\n", encoding="utf-8")
            code, 違反, err = run_check(spec)
        self.assertEqual(違反, [], "\n".join(違反))
        self.assertEqual(code, 0, err)

    # 仕様: requirements.md#見出しの固定セットと読み手-4
    def test_骨格が読み手の区分け表に載っている見出しだけを使うこと(self):
        """区分け表に無い見出しを骨格が使うと、検査は「読み手不明」で落ちる。"""
        表 = LAYOUT.read_text(encoding="utf-8")
        for skill, name in (("requirement", "requirements.md"),
                            ("design", "design.md")):
            for line in skeleton_of(skill).split("\n"):
                if not line.startswith("## "):
                    continue
                見出し = line[3:].strip()
                self.assertIn(見出し, 表, "%s の「%s」が区分け表に無い" % (name, 見出し))


if __name__ == "__main__":
    unittest.main()
