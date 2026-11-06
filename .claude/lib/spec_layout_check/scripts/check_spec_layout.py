#!/usr/bin/env python3
"""仕様書の層分け検査の入口。

specフォルダを受け取り、requirements.md / design.md / architecture.md の畳み・要点・
出所の目印と、requirements.md / design.md / tasks.md の承認フロントマターを照合して、
1違反1行のタブ区切りと終了コードで返す。/spec-review が
spec-reviewer を起動する前に実行し、出力をそのまま起動指示に添える。

起動: python3 .claude/lib/spec_layout_check/scripts/check_spec_layout.py <specフォルダ>
      (.claude は study のリポジトリルートからの相対パス。各 SKILL.md ではこの表記で書く)

仕様: ~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers/
  design.md#結果の出力、appendix.md#検査結果の出力書式
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import checks
import layout_rules
import markdown_scan

LAYOUT_RELATIVE_PATH = os.path.join("quality-standards", "base", "spec-layout.md")


def default_layout_path():
    """区分け表の場所。自分のファイル位置から study の `.claude` を求める。

    worktree・ローカルクローンで動かしても、その配置の区分け表を読む。本番配置では
    `<study>/.claude/quality-standards/base/spec-layout.md` になる。見つからない
    場合だけ旧配置の `~/.claude` を直接見る。
    """
    # scripts → spec_layout_check → lib → .claude
    root = os.path.abspath(__file__)
    for _ in range(4):
        root = os.path.dirname(root)
    near = os.path.join(root, LAYOUT_RELATIVE_PATH)
    if os.path.exists(near):
        return near
    return os.path.expanduser(os.path.join("~/.claude", LAYOUT_RELATIVE_PATH))


TARGET_FILES = ("requirements.md", "design.md", "architecture.md")
# 層分けは検査せず、承認フロントマターだけを見るファイル
FRONTMATTER_ONLY_FILES = tuple(f for f in checks.APPROVAL_FILES if f not in TARGET_FILES)
CHAR_COUNT_FILES = ("requirements.md", "design.md")
COMBINED_LABEL = "+".join(CHAR_COUNT_FILES)

KIND_VISIBLE_CHARS = "人が読む文字数"
KIND_AGREED_LINES = "合意の行数"
KIND_PROPOSED_LINES = "提案の行数"

EXIT_CLEAN = 0
EXIT_VIOLATION = 1
EXIT_LEGACY = 2
EXIT_TABLE_UNREADABLE = 3

NO_TARGET_NOTE = "specフォルダに対象ファイルが無い"


class FileResult:
    """1ファイルぶんの検査結果。"""

    def __init__(self, file_name):
        self.file_name = file_name
        self.violations = []
        self.legacy = False
        self.no_frontmatter = False
        self.layout_checked = file_name in TARGET_FILES
        self.visible_chars = 0
        self.provenance = {"合意": 0, "提案": 0}
        self.visible = []


def _is_legacy(scan, rules, file_name):
    """旧形式(この仕様より前の書き方)かどうか。

    次の3つがそろったファイルを旧形式とみなす。

    1. 折りたたみが1つも無い
    2. 折りたたむべきAI見出しが1つ以上ある
    3. 出所の目印が1つも無い

    見出し名では判定しない: 新形式は「概要」を必須にしたので「概要」があることは
    旧形式の証拠にならず、旧形式の design.md には「サマリ」も「概要」も無いものが
    ある。一方で条件1だけでは、AI見出しを持たない architecture.md や書きかけの
    文書まで検査対象外にしてしまうため、条件2・3で絞る。
    """
    if scan.detail_ranges:
        return False
    # `###` ごとに畳む見出しは `###` が無くても「畳むべき見出し」に数える
    # (旧形式の requirements.md は機能要件を `###` 無しで書いていることがある)
    畳むべき見出し = [unit for _h, unit in checks.iter_units(file_name, scan, rules)
                if unit is not None and getattr(unit, "reader", None) == "AI"
                and unit.rule.folded]
    if not 畳むべき見出し:
        return False
    return not any(markdown_scan.source_marks(line) for line in scan.lines)


def inspect_file(path, file_name, rules):
    """1ファイルを検査する。読めなければ違反1件だけを持つ結果を返す。"""
    result = FileResult(file_name)
    try:
        with open(path, encoding="utf-8") as fp:
            text = fp.read()
    except (OSError, UnicodeDecodeError) as exc:
        result.violations.append(checks.Violation(
            file_name, checks.FILE_WIDE, checks.KIND_UNREADABLE, str(exc)))
        return result

    scan = markdown_scan.scan(text)
    if file_name in checks.APPROVAL_FILES:
        violations, result.no_frontmatter = checks.check_frontmatter(file_name, scan)
        result.violations.extend(violations)
    if not result.layout_checked:
        return result
    if _is_legacy(scan, rules, file_name):
        result.legacy = True
        return result

    result.violations.extend(checks.check_folding(file_name, scan, rules))
    result.violations.extend(checks.check_provenance(file_name, scan, rules))
    result.visible_chars = checks.count_visible_chars(file_name, scan, rules)
    result.provenance = checks.count_provenance(file_name, scan, rules)
    result.visible = checks.visible_report(file_name, scan, rules)
    return result


def inspect_spec(spec_dir, rules):
    """specフォルダにある対象ファイルを順に検査する。"""
    results = []
    for file_name in TARGET_FILES + FRONTMATTER_ONLY_FILES:
        path = os.path.join(spec_dir, file_name)
        if not os.path.exists(path):
            continue
        results.append(inspect_file(path, file_name, rules))
    return results


def build_rows(results):
    """出力する行(4列のタプル)を組み立てる。"""
    rows = []
    for result in results:
        if result.no_frontmatter:
            rows.append((result.file_name, checks.FILE_WIDE, checks.KIND_NO_FRONTMATTER,
                         "承認状態のフロントマター(status / version)が無い"))
        if result.legacy:
            rows.append((result.file_name, checks.FILE_WIDE, checks.KIND_LEGACY,
                         "畳むべき見出しが畳まれておらず目印も無い"))
        for violation in result.violations:
            rows.append(violation.as_row())

    total_chars = 0
    total_marks = {"合意": 0, "提案": 0}
    counted_any = False
    for result in results:
        if result.legacy or not result.layout_checked:
            continue
        rows.extend(_count_rows(result.file_name, result.visible_chars,
                                result.provenance))
        if result.file_name in CHAR_COUNT_FILES:
            counted_any = True
            total_chars += result.visible_chars
            for mark in total_marks:
                total_marks[mark] += result.provenance.get(mark, 0)
    if counted_any:
        rows.extend(_count_rows(COMBINED_LABEL, total_chars, total_marks))
    return rows


def _count_rows(label, chars, marks):
    """文字数・目印別行数の補足3行(違反ではない)。"""
    return [
        (label, checks.FILE_WIDE, KIND_VISIBLE_CHARS, str(chars)),
        (label, checks.FILE_WIDE, KIND_AGREED_LINES, str(marks.get("合意", 0))),
        (label, checks.FILE_WIDE, KIND_PROPOSED_LINES, str(marks.get("提案", 0))),
    ]


def decide_exit_code(results):
    """違反あり(1) > 違反は無く旧形式かフロントマター無しのファイルがある(2) > 違反なし(0)
    の順に決める。

    2は「旧形式のファイルだけ」ではない。違反0の新形式ファイルと混ざっていても、
    旧形式かフロントマター無しのファイルが1つでもあれば2を返す。
    """
    if any(result.violations for result in results):
        return EXIT_VIOLATION
    if any(result.legacy or result.no_frontmatter for result in results):
        return EXIT_LEGACY
    return EXIT_CLEAN


def _write(stream, rows):
    for row in rows:
        stream.write("\t".join(row) + "\n")


def _write_visible(stream, results):
    """承認者が見る行だけを、ファイルごとに順に書く。"""
    for result in results:
        if result.legacy or not result.visible:
            continue
        stream.write("=== %s ===\n" % result.file_name)
        for 種別, 本文 in result.visible:
            stream.write("%s\n" % 本文)  # 見出しは "## 名前" の形で入っている
        stream.write("\n")


def main(argv, layout_path=None, stdout=None, stderr=None):
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    visible_only = "--visible" in argv
    argv = [a for a in argv if a != "--visible"]
    if len(argv) != 1:
        stderr.write("使い方: check_spec_layout.py [--visible] <specフォルダの絶対パス>\n")
        return EXIT_VIOLATION
    spec_dir = argv[0]

    try:
        rules = layout_rules.load_layout_rules(layout_path or default_layout_path())
    except layout_rules.LayoutTableError as exc:
        _write(stdout, [(checks.FILE_WIDE, checks.FILE_WIDE,
                         checks.KIND_UNREADABLE, "区分け表を読めない: %s" % exc)])
        return EXIT_TABLE_UNREADABLE

    try:
        results = inspect_spec(spec_dir, rules)
        if not any(result.layout_checked for result in results):
            _write(stdout, [(checks.FILE_WIDE, checks.FILE_WIDE,
                             checks.KIND_UNREADABLE, NO_TARGET_NOTE)])
            return EXIT_VIOLATION
        rows = build_rows(results)
        code = decide_exit_code(results)
    except Exception:
        # 例外を握りつぶして「違反なし」で終えると、検査が動かなかったことに
        # 誰も気づけない。トレースを標準エラーへ出して「違反あり」で終える。
        traceback.print_exc(file=stderr)
        return EXIT_VIOLATION

    if visible_only:
        _write_visible(stdout, results)
    _write(stdout, rows)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
