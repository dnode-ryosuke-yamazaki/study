"""仕様書Markdownの走査。

判定に要る位置(見出し・どの章にも属さない行・読み手宣言・畳みの範囲・図の範囲・行末の目印・
決定事項の表)を行番号つきで取り出す。ここでは違反かどうかを決めず、字句として
「どこに何があるか」だけを返す。

仕様: ~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers/
  design.md#見出しの抽出と読み手の判定、design.md#出所の目印の照合
"""

import re

SUMMARY_OPEN = "<details><summary>詳細を開く</summary>"
DETAILS_CLOSE = "</details>"
DECLARATION = re.compile(r"^>\s*読み手:\s*(\S+)\s*$")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})\s*(\S*)")
TRAILING_MARK = re.compile(r"〔([^〔〕]+)〕\s*$")
# /autopilot が推測で決めた箇所に付ける `【推測】` は行末を占めるが出所の目印ではない。
# 読み飛ばさないと、目印を付けた行が「出所なし」になってしまう
TRAILING_NOTE = re.compile(r"【[^【】]+】\s*$")
SOURCE_MARKS = ("合意", "提案")
# タイトル直下に置くステータス・優先度のラベル行。章の外に許す唯一の行で、
# 許すのは requirements.md の1行目だけ(判定は checks.check_folding)。
# 引用(`>`)にはしない規定なので、引用で書かれたものはこれに一致せず違反になる
STATUS_LINE = re.compile(r"^ステータス:")


class Heading:
    """1つの見出しと、その本文の範囲(行番号は1始まり、body_end は含む)。"""

    def __init__(self, level, text, line):
        self.level = level
        self.text = text
        self.line = line
        self.body_start = line + 1
        self.body_end = line
        self.declaration = None
        self.declaration_line = None
        self.parent = None

    @property
    def path(self):
        """出力に載せる見出し名(`###` は親の `##` を前に付ける)。"""
        if self.parent is None:
            return "## " + self.text
        return "## %s / ### %s" % (self.parent.text, self.text)

    def __repr__(self):
        return "Heading(%d, %s, L%d)" % (self.level, self.text, self.line)


class Range:
    """開始行と終了行(どちらも含む)。"""

    def __init__(self, start, end, blank_after_summary=None):
        self.start = start
        self.end = end
        self.blank_after_summary = blank_after_summary

    def contains(self, line_no):
        return self.start <= line_no <= self.end

    def __repr__(self):
        return "Range(%d, %d)" % (self.start, self.end)


class Table:
    """Markdownの表1つ。"""

    def __init__(self, header_line, header, rows):
        self.header_line = header_line
        self.header = header
        self.rows = rows

    def column(self, name):
        """列名を指定して (行番号, 値) の一覧を返す。列が無ければ空。"""
        if name not in self.header:
            return []
        index = self.header.index(name)
        found = []
        for line_no, cells in self.rows:
            found.append((line_no, cells[index] if index < len(cells) else ""))
        return found


class ScanResult:
    def __init__(self, lines):
        self.lines = lines
        self.headings = []
        self.outside_section_lines = []
        self.detail_ranges = []
        self.mermaid_ranges = []
        self.code_ranges = []

    def line_text(self, line_no):
        if 1 <= line_no <= len(self.lines):
            return self.lines[line_no - 1]
        return ""

    def body_lines(self, heading):
        return [self.line_text(n) for n in range(heading.body_start, heading.body_end + 1)]

    def in_details(self, line_no):
        return any(r.contains(line_no) for r in self.detail_ranges)

    def in_mermaid(self, line_no):
        return any(r.contains(line_no) for r in self.mermaid_ranges)

    def in_code(self, line_no):
        return any(r.contains(line_no) for r in self.code_ranges)

    def figure_caption_lines(self):
        """図の直後の説明1行(空行を1つ挟む場合を含む)の行番号。"""
        captions = set()
        for figure in self.mermaid_ranges:
            line_no = figure.end + 1
            while line_no <= len(self.lines) and not self.line_text(line_no).strip():
                line_no += 1
            if line_no <= len(self.lines) and self.line_text(line_no).strip():
                captions.add(line_no)
        return captions

    def find_table(self, heading_text):
        """見出しの本文にある最初の表。無ければ None。"""
        for heading in self.headings:
            if heading.text != heading_text:
                continue
            return self._table_in(heading.body_start, heading.body_end)
        return None

    def tables_in(self, start, end):
        """その範囲にある表をすべて返す(畳みの中のものを含む)。"""
        found = []
        line_no = start
        while line_no <= end:
            if self.line_text(line_no).strip().startswith("|"):
                table = self._table_in(line_no, end)
                if table is None:
                    break
                found.append(table)
                line_no = (table.rows[-1][0] if table.rows else table.header_line) + 1
                continue
            line_no += 1
        return found

    def _table_in(self, start, end):
        header = None
        header_line = None
        rows = []
        for line_no in range(start, end + 1):
            line = self.line_text(line_no)
            if not line.strip().startswith("|"):
                if header is not None:
                    break
                continue
            cells = split_row(line)
            if header is None:
                header, header_line = cells, line_no
                continue
            if is_separator_row(cells):
                continue
            rows.append((line_no, cells))
        if header is None:
            return None
        return Table(header_line, header, rows)


def split_row(line):
    cells = line.strip().split("|")
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return [cell.strip() for cell in cells]


def is_separator_row(cells):
    return bool(cells) and all(set(cell) <= set("-: ") and "-" in cell for cell in cells)


def trailing_marks(line):
    """行末から連続する `〔…〕` のトークンを、文中の出現順で返す。

    間に挟まる `【…】`(/autopilot の `【推測】` など)は読み飛ばす。
    """
    rest = line.rstrip()
    marks = []
    while True:
        note = TRAILING_NOTE.search(rest)
        if note:
            rest = rest[:note.start()].rstrip()
            continue
        found = TRAILING_MARK.search(rest)
        if not found:
            break
        marks.append(found.group(1))
        rest = rest[:found.start()].rstrip()
    marks.reverse()
    return marks


def source_marks(line):
    """行末のトークンのうち出所の目印(合意 / 提案)だけを返す。"""
    return [mark for mark in trailing_marks(line) if mark in SOURCE_MARKS]


def scan(text):
    """Markdown全文を走査して ScanResult を返す。"""
    lines = text.split("\n")
    result = ScanResult(lines)

    _collect_code_ranges(result)
    _collect_detail_ranges(result)
    _collect_headings(result)
    _collect_outside_section_lines(result)
    return result


def _collect_code_ranges(result):
    fence_char = None
    fence_len = 0
    start = None
    info = ""
    for index, line in enumerate(result.lines, start=1):
        found = FENCE.match(line)
        if not found:
            continue
        if fence_char is None:
            fence_char = found.group(1)[0]
            fence_len = len(found.group(1))
            start = index
            info = found.group(2)
            continue
        # 閉じるのは、開きと同じ文字で開き以上の長さのフェンスだけ。
        # 4連の中に書いた ``` の例で閉じてしまうと、以降の本文を実体として読む
        if found.group(1)[0] != fence_char or len(found.group(1)) < fence_len \
                or found.group(2):
            continue
        block = Range(start, index)
        result.code_ranges.append(block)
        if info.lower() == "mermaid":
            result.mermaid_ranges.append(block)
        fence_char = None
        fence_len = 0
        start = None
        info = ""


def _collect_detail_ranges(result):
    start = None
    for index, line in enumerate(result.lines, start=1):
        if result.in_code(index):
            continue
        stripped = line.strip()
        if start is None and stripped.startswith(SUMMARY_OPEN):
            start = index
            continue
        if start is not None and stripped == DETAILS_CLOSE:
            blank = not result.line_text(start + 1).strip()
            result.detail_ranges.append(Range(start, index, blank_after_summary=blank))
            start = None
    if start is not None:
        blank = not result.line_text(start + 1).strip()
        result.detail_ranges.append(
            Range(start, len(result.lines), blank_after_summary=blank))


def _collect_headings(result):
    parent = None
    for index, line in enumerate(result.lines, start=1):
        if result.in_code(index) or result.in_details(index):
            continue
        if not line.startswith("##"):
            continue
        level = len(line) - len(line.lstrip("#"))
        if level not in (2, 3):
            continue
        heading = Heading(level, line.lstrip("#").strip(), index)
        if level == 3:
            heading.parent = parent
        else:
            parent = heading
        # 見出しの直後に空行を1つ置く書き方が普通なので、最初の中身のある行を見る
        probe = index + 1
        while probe <= len(result.lines) and not result.line_text(probe).strip():
            probe += 1
        declaration = DECLARATION.match(result.line_text(probe).strip())
        if declaration:
            heading.declaration = declaration.group(1)
            heading.declaration_line = probe
        result.headings.append(heading)

    total = len(result.lines)
    for position, heading in enumerate(result.headings):
        end = total
        for later in result.headings[position + 1:]:
            if later.level <= heading.level:
                end = later.line - 1
                break
        heading.body_end = max(end, heading.body_start - 1)


def _collect_outside_section_lines(result):
    first = result.headings[0].line if result.headings else len(result.lines) + 1
    for line_no in range(1, first):
        line = result.line_text(line_no)
        if not line.strip():
            continue
        if line.startswith("# "):
            continue
        result.outside_section_lines.append((line_no, line.strip()))
