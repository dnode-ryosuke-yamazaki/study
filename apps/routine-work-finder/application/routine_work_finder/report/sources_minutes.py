"""議事録の控えから、その週の会議の題名と要点を読む。

議事録の自動生成(meeting-minutes-generator)が同期フォルダの外に置く控えを読む(launchd から同期フォルダを
読むと失敗する例があるため)。ファイル名の日時で週を絞り、ファイル名の会議名を題名、「要約」の見出しの
本文の先頭500字を要点として持つ(design.md「既存の作業の記録を読み込む」6・7)。

控えのファイル名は `<会議名>__<YYYYmmddTHHMM>__<2桁の連番>.md`(同じ名前があれば末尾に `-2` などが付く)。
日時は UTC で書かれている(teams-transcript-fetcher の naming.py が UTC の日時を書く)。
読めない控えは1件ずつ読み飛ばして数え、控えのフォルダそのものが読めないときだけ記録の失敗として控える。
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
MINUTES_FOLDER = Path.home() / "Library" / "Application Support" / "meeting-minutes-generator" / "minutes"
SUMMARY_LIMIT = 500
SUMMARY_HEADING = "要約"
FILE_NAME = re.compile(r"^(?P<title>.+)__(?P<time>\d{8}T\d{4})__\d{2}(?:-\d+)?\.md$")
HEADING = re.compile(r"^(#{1,6})\s*(.+?)\s*$")


@dataclass
class MinutesResult:
    """minutes: その週の議事録(時刻の順)、skipped: 読み飛ばした控えの数(理由ごと)、failures: 読めなかった記録"""

    minutes: list = field(default_factory=list)
    skipped: dict = field(default_factory=dict)
    failures: list = field(default_factory=list)


def read_minutes(start, end, folder=MINUTES_FOLDER):
    """ファイル名の日時が start 以上 end 未満(日本時間)の控えを読む"""
    result = MinutesResult()
    folder = Path(folder)
    if not folder.is_dir():
        result.failures.append(_failure("missing"))
        return result
    try:
        paths = sorted(path for path in folder.iterdir() if path.suffix == ".md" and path.is_file())
    except OSError:
        result.failures.append(_failure("unreadable"))
        return result

    skipped = Counter()
    for path in paths:
        parsed = _parse_name(path.name)
        if parsed is None:
            skipped["badName"] += 1
            continue
        title, when = parsed
        if not start <= when < end:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            skipped["unreadable"] += 1
            continue
        summary = summary_section(text)
        if summary is None:
            skipped["noSummary"] += 1
            continue
        result.minutes.append({"source": "minutes", "title": title, "summary": summary[:SUMMARY_LIMIT], "time": when})
    result.minutes.sort(key=lambda minutes: minutes["time"])
    result.skipped = dict(skipped)
    return result


def _failure(reason):
    return {"source": "minutes", "site": None, "reason": reason}


def _parse_name(name):
    """ファイル名から会議名と日時(UTC を日本時間に直したもの)を取る。読めなければ None"""
    matched = FILE_NAME.match(name)
    if not matched:
        return None
    try:
        when = datetime.strptime(matched.group("time"), "%Y%m%dT%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return matched.group("title"), when.astimezone(JST)


def summary_section(text):
    """「## 要約」の見出しから、次の同じ深さ以上の見出しの手前までの本文。見出しが無ければ None"""
    lines = text.splitlines()
    begin = None
    for index, line in enumerate(lines):
        heading = HEADING.match(line)
        if not heading:
            continue
        level = len(heading.group(1))
        if begin is None:
            if level == 2 and heading.group(2) == SUMMARY_HEADING:
                begin = index + 1
        elif level <= 2:
            return "\n".join(lines[begin:index]).strip()
    if begin is None:
        return None
    return "\n".join(lines[begin:]).strip()
