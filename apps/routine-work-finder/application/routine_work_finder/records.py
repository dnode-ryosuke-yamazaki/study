"""記録・メモのファイルを期間で読む共通の処理。

状態の確認(control.py)と週次レポート(report/aggregate.py)が同じ読み方で記録を扱うため、
行・メモの読み取りと、記録が取れなかった時間帯の求め方をここに置く(appendix.md「操作の記録の行の形」)。
"""

import json
import re
from datetime import datetime, timedelta, timezone
from typing import NamedTuple, Optional

JST = timezone(timedelta(hours=9))
GAP_THRESHOLD = timedelta(seconds=30)
FILE_NAME_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl$")
MEMO_ID_PATTERN = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")
KNOWN_KINDS = {"start", "stop", "sample", "excluded"}
KNOWN_FIELDS = {
    "t", "kind", "reason", "app", "bundleId", "monitor", "idleSec", "locked", "mic", "displaySleepPrevented",
    "title", "titleTruncated", "sheet", "focusRole", "focusSubrole", "titleUnavailable", "titleReason",
}


class RecordRange(NamedTuple):
    """期間の行(時刻順)と、読み飛ばした行の数(書きかけ・知らない種類)"""

    lines: list
    skipped: int


def read_records(data_paths, start, end):
    """start 以上 end 未満の行を時刻順に返す。各行は知っている項目と、時刻を読んだ "time"(日本時間)を持つ"""
    lines, skipped = [], 0
    for path in _dated_files(data_paths.records, start, end):
        file_lines, file_skipped = _read_record_file(path)
        skipped += file_skipped
        lines.extend(line for line in file_lines if start <= line["time"] < end)
    lines.sort(key=lambda line: line["time"])
    return RecordRange(lines, skipped)


def find_gaps(data_paths, start, end):
    """記録している期間の中で、前後の行が30秒以上空いた時間帯を (始まり, 終わり) の一覧で返す。
    範囲の始まりが期間の内かは範囲の直前の行で決め、範囲の後の行は見ない"""
    previous = _line_before(data_paths, start)
    in_range = read_records(data_paths, start, end).lines
    gaps = []
    if previous is not None and previous["kind"] != "stop":
        first_time = in_range[0]["time"] if in_range else end
        if first_time - previous["time"] >= GAP_THRESHOLD:
            gaps.append((start, first_time))
    for before, after in zip(in_range, in_range[1:]):
        if before["kind"] != "stop" and after["time"] - before["time"] >= GAP_THRESHOLD:
            gaps.append((before["time"], after["time"]))
    if in_range and in_range[-1]["kind"] != "stop" and end - in_range[-1]["time"] >= GAP_THRESHOLD:
        gaps.append((in_range[-1]["time"], end))
    return gaps


def read_memos(data_paths, start, end):
    """start 以上 end 未満のメモを時刻順に返す。番号・時刻・文の形が違う行は読み飛ばす"""
    memos = []
    for path in _dated_files(data_paths.memos, start, end):
        for raw in _read_json_lines(path):
            memo = _parse_memo(raw)
            if memo is not None and start <= memo["time"] < end:
                memos.append(memo)
    memos.sort(key=lambda memo: memo["time"])
    return memos


def _line_before(data_paths, start):
    """範囲より前の、いちばん新しい読める行。28日の保持で消えていれば None"""
    start_date = start.astimezone(JST).date().isoformat()
    candidates = sorted(
        (match.group(1), path)
        for path in _list(data_paths.records)
        if (match := FILE_NAME_PATTERN.match(path.name)) and match.group(1) <= start_date
    )
    for _, path in reversed(candidates):
        earlier = [line for line in _read_record_file(path)[0] if line["time"] < start]
        if earlier:
            return max(earlier, key=lambda line: line["time"])
    return None


def _dated_files(directory, start, end):
    first = start.astimezone(JST).date().isoformat()
    last = (end - timedelta(microseconds=1)).astimezone(JST).date().isoformat()
    return sorted(
        path for path in _list(directory)
        if (match := FILE_NAME_PATTERN.match(path.name)) and first <= match.group(1) <= last
    )


def _list(directory):
    return list(directory.iterdir()) if directory.exists() else []


def _read_json_lines(path):
    """JSON として読める行だけを返す(書きかけの最終行などは飛ばす)。読めなかった数も返したいときは _read_record_file を使う"""
    return [raw for raw, ok in _parse_lines(path) if ok]


def _parse_lines(path):
    results = []
    for text in path.read_text(encoding="utf-8").splitlines():
        if not text.strip():
            continue
        try:
            results.append((json.loads(text), True))
        except ValueError:
            results.append((None, False))
    return results


def _read_record_file(path):
    lines, skipped = [], 0
    for raw, ok in _parse_lines(path):
        line = _parse_record(raw) if ok else None
        if line is None:
            skipped += 1
        else:
            lines.append(line)
    return lines, skipped


def _parse_record(raw) -> Optional[dict]:
    if not isinstance(raw, dict) or raw.get("kind") not in KNOWN_KINDS:
        return None
    time = _parse_time(raw.get("t"))
    if time is None:
        return None
    line = {key: value for key, value in raw.items() if key in KNOWN_FIELDS}
    line["time"] = time
    return line


def _parse_memo(raw) -> Optional[dict]:
    if not isinstance(raw, dict) or not MEMO_ID_PATTERN.match(str(raw.get("id", ""))) or not isinstance(raw.get("text"), str):
        return None
    time = _parse_time(raw.get("t"))
    if time is None:
        return None
    return {"id": raw["id"], "t": raw["t"], "text": raw["text"], "time": time}


def _parse_time(text):
    if not isinstance(text, str):
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(JST)
