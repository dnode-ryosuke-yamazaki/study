"""読み手の区分け表(`quality-standards/base/spec-layout.md`)の読み込み。

表の「本文の見え方」列は人が読む日本語のままにしてあり、そこから機械が使う3つの
判定材料(畳みの単位・本文を畳むか・図が見えてよいか)を導く。表を機械向けのJSONに
写すと二重管理になるため、人が読む表を1つだけ置いてここで解釈する。

仕様: ~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers/
  design.md#区分け表の読み込み
"""


TABLE_HEADING = "読み手の区分け"
REQUIRED_COLUMNS = ("ファイル", "見出し", "読み手", "本文の見え方")
VALID_READERS = ("人", "AI")

MAX_SUMMARY_LINES = 2

DEFAULT_KEY = "上記以外"
WHOLE_FILE_KEY = "(全体)"
HEADING_SEPARATOR = " / "


class LayoutTableError(Exception):
    """区分け表が読めない(表が無い・列が欠ける・読み手の値が不正)。"""


class HeadingRule:
    """1見出しぶんの規定。"""

    def __init__(self, file_name, heading, reader, visibility, summary_hint):
        self.file_name = file_name
        self.heading = heading
        self.reader = reader
        self.visibility = visibility
        self.summary_hint = summary_hint

    @property
    def fold_unit(self):
        """畳みの単位。`###` ごとに要点を置く見出しだけ `###`。"""
        return "###" if self.visibility.startswith("`###`") or \
            self.visibility.startswith("###") else "##"

    @property
    def folded(self):
        """本文を `<details>` で畳むべき見出しか。"""
        return "畳む" in self.visibility

    @property
    def checked(self):
        """畳み・要点の検査対象にする見出しか(appendix.md・tasks.md は対象外)。"""
        return "畳まない" not in self.visibility

    @property
    def figure_visible(self):
        """畳みの外に図が出ることを前提にした見出しか。"""
        return "図" in self.visibility

    @property
    def figure_required(self):
        """畳みの単位ごとに図を置くことを求める見出しか。"""
        return "図が要る" in self.visibility

    @property
    def visible_summary_lines(self):
        """畳みの外に置いてよい要点の行数。

        処理フローのように図が概要を担う見出しは、見え方に「要点が見える」と
        書かれていない。その場合は要点も畳むので0行になる。
        """
        見える要点 = any(語 in self.visibility
                    for 語 in ("要点が見え", "1行要点", "1行概要"))
        return MAX_SUMMARY_LINES if 見える要点 else 0

    def __repr__(self):
        return "HeadingRule(%s, %s, %s)" % (self.file_name, self.heading, self.reader)


class LayoutRules:
    """ファイル名→見出し→規定の辞書。"""

    def __init__(self):
        self._by_file = {}
        self._defaults = {}

    def add(self, rule):
        if rule.heading == DEFAULT_KEY:
            self._defaults[rule.file_name] = rule
        else:
            self._by_file.setdefault(rule.file_name, {})[rule.heading] = rule

    def rule_for(self, file_name, heading):
        """見出しの規定。表に無ければファイル既定(`上記以外`)、それも無ければ None。"""
        found = self._by_file.get(file_name, {}).get(heading)
        if found is not None:
            return found
        return self._defaults.get(file_name)

    def whole_file_rule(self, file_name):
        """ファイル全体を1つの規定で扱うファイル(appendix.md)。"""
        return self._by_file.get(file_name, {}).get(WHOLE_FILE_KEY)

    def files(self):
        names = set(self._by_file) | set(self._defaults)
        return sorted(names)


def _split_row(line):
    """表の1行をセルに割る(前後の `|` は落とす)。"""
    cells = line.strip().split("|")
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return [cell.strip() for cell in cells]


def _is_separator_row(cells):
    return bool(cells) and all(set(cell) <= set("-: ") and "-" in cell for cell in cells)


def parse_layout_table(text):
    """区分け表のMarkdownから LayoutRules を組み立てる。"""
    lines = text.split("\n")
    start = None
    for index, line in enumerate(lines):
        if line.startswith("#") and line.lstrip("#").strip() == TABLE_HEADING:
            start = index + 1
            break
    if start is None:
        raise LayoutTableError("区分け表の見出し「%s」が見つからない" % TABLE_HEADING)

    header = None
    rules = LayoutRules()
    rows = 0
    for line in lines[start:]:
        if not line.startswith("|"):
            if header is not None and rows:
                break
            continue
        cells = _split_row(line)
        if header is None:
            header = cells
            missing = [name for name in REQUIRED_COLUMNS if name not in header]
            if missing:
                raise LayoutTableError("区分け表の列が欠けている: %s" % "、".join(missing))
            continue
        if _is_separator_row(cells):
            continue
        if len(cells) < len(header):
            raise LayoutTableError("区分け表の行の列数が足りない: %s" % line.strip())
        row = dict(zip(header, cells))
        reader = row["読み手"]
        if reader not in VALID_READERS:
            raise LayoutTableError(
                "区分け表の読み手が「人」「AI」以外: %s(%s)" % (reader, row["見出し"]))
        for heading in row["見出し"].split(HEADING_SEPARATOR):
            heading = heading.strip()
            if not heading:
                continue
            rules.add(HeadingRule(row["ファイル"], heading, reader,
                                  row["本文の見え方"], row.get("要点に書くもの", "")))
        rows += 1
    if not rows:
        raise LayoutTableError("区分け表にデータ行が無い")
    return rules


def load_layout_rules(path):
    """区分け表のファイルを読んで LayoutRules を返す。"""
    try:
        with open(path, encoding="utf-8") as fp:
            text = fp.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise LayoutTableError("区分け表を読めない: %s(%s)" % (path, exc))
    return parse_layout_table(text)
