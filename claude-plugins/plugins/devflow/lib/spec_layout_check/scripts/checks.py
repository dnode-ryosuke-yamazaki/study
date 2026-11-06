"""要点・畳み・出所の目印の照合と、人が読む量の集計。

判定はすべて字句だけで行い、要点の中身が妥当かどうかや、目印が本当に会話で決めた
ことを指しているかには踏み込まない。人が目で見つけにくい「畳み忘れ」「目印の付け
忘れ」だけを機械の担当にする。

仕様: ~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers/
  design.md#要点と畳みの照合、design.md#出所の目印の照合、design.md#人が読む文字数の集計、
  design.md#承認フロントマターの照合
"""

import datetime
import re

import markdown_scan
from layout_rules import HeadingRule

KIND_UNKNOWN_READER = "読み手不明"
KIND_OVER_FOLDED = "畳み過ぎ"
KIND_MISSING_FOLD = "畳み忘れ"
KIND_LONG_SUMMARY = "要点が長い"
KIND_BODY_OUTSIDE = "畳みの外に本文"
KIND_ABOLISHED_HEADING = "廃止見出し"
KIND_NO_BLANK_AFTER_SUMMARY = "summary直後に空行なし"
KIND_NO_SOURCE = "出所なし"
KIND_DUPLICATE_SOURCE = "出所が重複"
KIND_TEXT_OUTSIDE_SECTION = "章の外に本文"
KIND_UNREADABLE = "読めない"
KIND_NO_FIGURE = "図なし"
KIND_NO_SUBSECTION = "小見出しなし"
KIND_LEGACY = "旧形式"
KIND_BAD_FRONTMATTER = "フロントマター不正"
# 違反ではなく状態(旧形式と同じ扱い)。フロントマターを持つ前に書かれた既存specを
# 一括で違反にしないため、終了コード2で「移行が要る」ことだけを伝える
KIND_NO_FRONTMATTER = "フロントマター無し"

# 承認状態のフロントマターを持つファイルと、その値
APPROVAL_FILES = ("requirements.md", "design.md", "tasks.md")
APPROVAL_STATUSES = ("draft", "in-review", "approved")
APPROVED = "approved"
VERSION = re.compile(r"^\d+\.\d+$")

# ステータス・優先度のラベル行を置けるファイル(他のファイルは章の外に本文になる)
STATUS_LABEL_FILE = "requirements.md"

# 違反として扱う廃止見出し。「概要」は必須見出しとして残すので含めない
ABOLISHED_HEADINGS = ("サマリ",)
DECISION_HEADING = "決定事項"
# 「出所」列で目印を持つ表の見出し。行は箇条書きではないので列の値で照合する
SOURCE_TABLE_HEADINGS = (DECISION_HEADING, "品質統制の適用")
SOURCE_COLUMN = "出所"
SOURCE_VALUES = ("合意", "提案")

BULLET = re.compile(r"^\s*([-*+]|\d+\.)\s")
FILE_WIDE = "-"

_UNKNOWN_RULE = HeadingRule("", "", "AI", "要点が見える・本文は畳む", "")


class Violation:
    """違反1件。出力の1行にそのまま対応する。"""

    def __init__(self, file_name, heading, kind, note=FILE_WIDE):
        self.file_name = file_name
        self.heading = heading
        self.kind = kind
        self.note = note

    def as_row(self):
        return (self.file_name, self.heading, self.kind, self.note)

    def __eq__(self, other):
        return isinstance(other, Violation) and self.as_row() == other.as_row()

    def __repr__(self):
        return "Violation(%s)" % "\t".join(self.as_row())

    __str__ = __repr__


class Unit:
    """畳みの単位1つ(`##` 見出し、または `###` 見出し)。"""

    def __init__(self, heading, rule, reader):
        self.heading = heading
        self.rule = rule
        self.reader = reader


def rule_and_reader(file_name, heading, rules):
    """見出しの規定と読み手を決める。決まらなければ (None, None)。"""
    rule = rules.rule_for(file_name, heading.text)
    if heading.declaration in ("人", "AI"):
        return rule or _UNKNOWN_RULE, heading.declaration
    if rule is None:
        return None, None
    return rule, rule.reader


def iter_units(file_name, scan, rules):
    """畳みの単位を順に返す。読み手が決まらない `##` は (heading, None) を返す。"""
    for heading in scan.headings:
        if heading.level != 2:
            continue
        if heading.text in ABOLISHED_HEADINGS:
            continue
        rule, reader = rule_and_reader(file_name, heading, rules)
        if rule is None:
            yield heading, None
            rule, reader = _UNKNOWN_RULE, _UNKNOWN_RULE.reader
        if not rule.checked:
            continue
        children = [h for h in scan.headings
                    if h.level == 3 and h.parent is heading]
        if rule.fold_unit == "###":
            # `###` ごとに畳むと定めた見出しは、`###` が無いと機能全体で1行しか
            # 見えない形になる。単位が作れないので、その旨を違反として返す
            yield heading, _Parent(heading, rule, reader, children)
            for child in children:
                yield child, Unit(child, rule, reader)
        else:
            yield heading, Unit(heading, rule, reader)


class _Parent:
    """`###` ごとに畳む `##` 見出し。直下に本文を置いていないかだけを見る。"""

    def __init__(self, heading, rule, reader, children):
        self.heading = heading
        self.rule = rule
        self.reader = reader
        self.children = children


def visible_lines(scan, heading, body_end=None):
    """畳みの外に見えている行(行番号, 本文)。空行・図・図の説明・宣言行は除く。"""
    end = heading.body_end if body_end is None else body_end
    captions = scan.figure_caption_lines()
    found = []
    for line_no in range(heading.body_start, end + 1):
        text = scan.line_text(line_no)
        if not text.strip():
            continue
        if scan.in_details(line_no) or scan.in_mermaid(line_no):
            continue
        if line_no in captions:
            continue
        if line_no == heading.declaration_line:
            continue
        found.append((line_no, text))
    return found


def _figures_in(scan, heading, body_end=None):
    """その見出しの本文にあるMermaid図(畳みの外のもの)。"""
    end = heading.body_end if body_end is None else body_end
    return [r for r in scan.mermaid_ranges
            if heading.body_start <= r.start <= end and not scan.in_details(r.start)]


def _details_in(scan, heading, body_end=None):
    end = heading.body_end if body_end is None else body_end
    return [r for r in scan.detail_ranges
            if heading.body_start <= r.start <= end]


def _is_body_line(text):
    """要点ではなく本文とみなす行(箇条書き・表・コードブロック)。"""
    stripped = text.strip()
    return bool(BULLET.match(text)) or stripped.startswith("|") or \
        stripped.startswith("```") or stripped.startswith("~~~")


def check_folding(file_name, scan, rules):
    """章の外の本文・廃止見出し・畳み・要点の形を照合する。"""
    found = []

    # タイトルと最初の `##` の間に本文を置かない。どの章にも属さない文は、
    # 見出しから探せず、読み手にとって位置づけの分からない記載になる。
    # 例外は requirements.md のタイトル直下に置くラベル1行だけで、
    # 引用(`>`)で書いたもの・2行目以降・他のファイルのものは違反にする
    for index, (line_no, text) in enumerate(scan.outside_section_lines):
        if (index == 0 and file_name == STATUS_LABEL_FILE
                and markdown_scan.STATUS_LINE.match(text)):
            continue
        found.append(Violation(file_name, FILE_WIDE, KIND_TEXT_OUTSIDE_SECTION,
                               "L%d" % line_no))

    for heading in scan.headings:
        if heading.level == 2 and heading.text in ABOLISHED_HEADINGS:
            found.append(Violation(file_name, heading.path, KIND_ABOLISHED_HEADING,
                                   "L%d" % heading.line))

    for detail in scan.detail_ranges:
        if not detail.blank_after_summary:
            found.append(Violation(file_name, _heading_path_at(scan, detail.start),
                                   KIND_NO_BLANK_AFTER_SUMMARY, "L%d" % detail.start))

    for heading, unit in iter_units(file_name, scan, rules):
        if unit is None:
            found.append(Violation(file_name, heading.path, KIND_UNKNOWN_READER,
                                   "L%d" % heading.line))
            continue
        if isinstance(unit, _Parent):
            if not unit.children:
                found.append(Violation(file_name, heading.path, KIND_NO_SUBSECTION,
                                       "L%d" % heading.line))
                continue
            body_end = unit.children[0].line - 1
            for line_no, text in visible_lines(scan, heading, body_end):
                found.append(Violation(file_name, heading.path, KIND_BODY_OUTSIDE,
                                       "L%d" % line_no))
            continue
        found.extend(_check_unit(file_name, scan, unit))
    return found


def _check_unit(file_name, scan, unit):
    found = []
    heading = unit.heading
    details = _details_in(scan, heading)
    if unit.reader == "人":
        # 決定事項のように「主な行が見える・残りは畳む」と定めた見出しは畳んでよい
        if not unit.rule.folded:
            for detail in details:
                found.append(Violation(file_name, heading.path, KIND_OVER_FOLDED,
                                       "L%d" % detail.start))
        return found

    if unit.rule.figure_required and not _figures_in(scan, heading):
        found.append(Violation(file_name, heading.path, KIND_NO_FIGURE,
                               "L%d" % heading.line))

    if unit.rule.folded and not details:
        found.append(Violation(file_name, heading.path, KIND_MISSING_FOLD,
                               "L%d" % heading.line))
    visible = visible_lines(scan, heading)
    限度 = unit.rule.visible_summary_lines
    if len(visible) > 限度:
        found.append(Violation(file_name, heading.path, KIND_LONG_SUMMARY,
                               "%d行(上限%d行)" % (len(visible), 限度)))
    for line_no, text in visible:
        if _is_body_line(text):
            found.append(Violation(file_name, heading.path, KIND_BODY_OUTSIDE,
                                   "L%d" % line_no))
    return found


def _heading_path_at(scan, line_no):
    """その行が属する見出しの名前。見出しの前なら `-`。"""
    current = FILE_WIDE
    for heading in scan.headings:
        if heading.line > line_no:
            break
        current = heading.path
    return current


def _join_wrapped(lines):
    """折り返した箇条書きを1項目にまとめる。

    `- ` で始まる行に続く字下げされた行は、その項目の続き。目印は項目の末尾
    (最後の行の行末)に付くため、続きの行を独立した行として数えない。
    返すのは (項目の先頭行の行番号, 目印を探す最後の行の本文)。
    """
    items = []
    for line_no, text in lines:
        続き = items and text.startswith((" ", "\t")) and not BULLET.match(text)
        if 続き:
            items[-1] = (items[-1][0], text)
            continue
        items.append((line_no, text))
    return items


def provenance_lines(file_name, scan, rules):
    """出所の目印を付けるべき行(行番号, 目印を探す本文)。"""
    found = []
    for heading, unit in iter_units(file_name, scan, rules):
        if unit is None or isinstance(unit, _Parent):
            continue
        for line_no, text in _join_wrapped(visible_lines(scan, unit.heading)):
            if unit.reader == "人" and not BULLET.match(scan.line_text(line_no)):
                continue
            found.append((line_no, text))
    return found


def check_provenance(file_name, scan, rules):
    """目印を付けるべき行に目印がちょうど1つあるかを照合する。"""
    found = []
    for line_no, text in provenance_lines(file_name, scan, rules):
        marks = markdown_scan.source_marks(text)
        if not marks:
            found.append(Violation(file_name, _heading_path_at(scan, line_no),
                                   KIND_NO_SOURCE, "L%d" % line_no))
        elif len(marks) > 1:
            found.append(Violation(file_name, _heading_path_at(scan, line_no),
                                   KIND_DUPLICATE_SOURCE, "L%d" % line_no))
    found.extend(_check_source_tables(file_name, scan))
    return found


def _source_tables(scan):
    """「出所」列を持つべき表すべて(見出し名, 表)。畳みの中のものを含む。"""
    found = []
    for name in SOURCE_TABLE_HEADINGS:
        for heading in scan.headings:
            if heading.text != name:
                continue
            found.extend((name, table) for table in
                         scan.tables_in(heading.body_start, heading.body_end))
            break
    return found


def _check_source_tables(file_name, scan):
    found = []
    for name, table in _source_tables(scan):
        heading = "## " + name
        if SOURCE_COLUMN not in table.header:
            found.append(Violation(file_name, heading, KIND_NO_SOURCE,
                                   "列なし(L%d)" % table.header_line))
            continue
        for line_no, value in table.column(SOURCE_COLUMN):
            if value not in SOURCE_VALUES:
                found.append(Violation(file_name, heading, KIND_NO_SOURCE,
                                       "L%d" % line_no))
    return found


def check_frontmatter(file_name, scan):
    """承認状態のフロントマターを照合する。(違反の一覧, フロントマターが無いか) を返す。

    status は draft / in-review / approved のどれか、version は「数字.数字」。
    approved_date は approved のときだけ置き、YYYY-MM-DD の日付にする。承認済みは
    1.0 以上(初回の承認で 1.0 にする)。他のキーは読み飛ばす(標準の type・title 等)。
    """
    entries = scan.frontmatter
    if entries is None:
        return [], True

    notes = []
    status = entries.get("status")
    if status is None:
        notes.append("status が無い")
    elif status not in APPROVAL_STATUSES:
        notes.append("status が draft / in-review / approved のどれでもない: %s" % status)

    version = entries.get("version")
    if version is None:
        notes.append("version が無い")
    elif not VERSION.match(version):
        notes.append("version が「数字.数字」でない: %s" % version)
    elif status == APPROVED and version.startswith("0."):
        notes.append("approved なのに version が 1.0 未満: %s" % version)

    approved_date = entries.get("approved_date")
    if status == APPROVED:
        if not approved_date:
            notes.append("approved なのに approved_date が無い")
        elif not _is_date(approved_date):
            notes.append("approved_date が YYYY-MM-DD の日付でない: %s" % approved_date)
    elif "approved_date" in entries:
        notes.append("approved でないのに approved_date がある")

    return [Violation(file_name, FILE_WIDE, KIND_BAD_FRONTMATTER, note)
            for note in notes], False


def _is_date(value):
    try:
        datetime.datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _visible_text_lines(file_name, scan, rules):
    """人が実際に目にする行(人見出しの本文・要点行・図の説明1行)。"""
    seen = {}
    captions = scan.figure_caption_lines()
    for heading, unit in iter_units(file_name, scan, rules):
        if unit is None or isinstance(unit, _Parent):
            continue
        for line_no, text in visible_lines(scan, unit.heading):
            seen[line_no] = text.strip()
    for line_no in captions:
        if not scan.in_details(line_no):
            seen[line_no] = scan.line_text(line_no).strip()
    return [seen[line_no] for line_no in sorted(seen)]


def visible_report(file_name, scan, rules):
    """承認者が実際に目にする行を、見出しつきで出現順に返す。

    書き手が「出す前に承認者と同じものを読み返す」ために使う。畳みの中は含めない。
    """
    行 = {}
    for heading, unit in iter_units(file_name, scan, rules):
        if unit is None or isinstance(unit, _Parent):
            continue
        行.setdefault(unit.heading.line, ("見出し", unit.heading.path))
        for line_no, text in visible_lines(scan, unit.heading):
            行[line_no] = ("本文", text.strip())
    for line_no in scan.figure_caption_lines():
        if not scan.in_details(line_no):
            行.setdefault(line_no, ("図の説明", scan.line_text(line_no).strip()))
    for figure in scan.mermaid_ranges:
        if not scan.in_details(figure.start):
            行.setdefault(figure.start, ("図", "(Mermaidの図)"))
    return [行[line_no] for line_no in sorted(行)]


def count_visible_chars(file_name, scan, rules):
    """人が読む部分の文字数の合計。"""
    return sum(len(text) for text in _visible_text_lines(file_name, scan, rules))


def count_provenance(file_name, scan, rules):
    """見えている行に付いた目印を種類ごとに数える(決定事項の表の行を含む)。"""
    counted = {"合意": 0, "提案": 0}
    for line_no, text in provenance_lines(file_name, scan, rules):
        for mark in markdown_scan.source_marks(text):
            counted[mark] += 1
    # 畳みの中の表は承認者が開かないと見えないので、読む量には数えない
    for _name, table in _source_tables(scan):
        if SOURCE_COLUMN not in table.header:
            continue
        for line_no, value in table.column(SOURCE_COLUMN):
            if value in counted and not scan.in_details(line_no):
                counted[value] += 1
    return counted
