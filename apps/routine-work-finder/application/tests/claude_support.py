"""Claude に渡す材料と応答の検査のテストで使う、記録の行と集計の結果の作り方"""

from datetime import datetime, timedelta

from routine_work_finder.report import aggregate

WEEK_START = datetime.fromisoformat("2026-10-05T00:00:00+09:00")
WEEK_END = datetime.fromisoformat("2026-10-09T17:00:00+09:00")


def jst(text):
    return datetime.fromisoformat(text + "+09:00")


def sample(text, **fields):
    """記録の共通の処理が読んだ形の通常の行(入力の直後・ロックなし・マイクなし・スリープの抑止なし)"""
    line = {"t": text + "+09:00", "kind": "sample", "app": "Code", "bundleId": "com.microsoft.VSCode", "monitor": 1,
            "idleSec": 0.5, "locked": False, "mic": False, "displaySleepPrevented": False, "title": "main.swift"}
    line.update(fields)
    line["time"] = jst(text)
    return line


def untitled(text, app="Microsoft Teams", reason="timeout"):
    """題名が取れなかった行"""
    line = sample(text, app=app, titleUnavailable=True, titleReason=reason)
    del line["title"]
    return line


def excluded(text):
    return {"t": text + "+09:00", "kind": "excluded", "time": jst(text)}


def run(start, count, **fields):
    """start から5秒ごとに count 行の通常の行"""
    first = jst(start)
    return [sample((first + timedelta(seconds=5 * index)).strftime("%Y-%m-%dT%H:%M:%S"), **fields) for index in range(count)]


def week_of(lines):
    """行から1週間分の集計の結果を作る(記録のファイルを通さない)"""
    classified = aggregate.classify(sorted(lines, key=lambda line: line["time"]))
    return aggregate.WeekAggregate(
        totals=aggregate.category_totals(classified),
        groups=aggregate.group_work(classified),
        gaps=[],
        title_unavailable=[],
        skipped=0,
        classified=classified,
    )


def memo(text, body, memo_id="20261006-101530-a1b2"):
    return {"id": memo_id, "t": text + "+09:00", "text": body, "time": jst(text)}


def walk_keys(value, prefix=""):
    """材料の JSON に現れる項目の場所をすべて「親.子」の形で返す(一覧の中は [] で表す)"""
    found = set()
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            found.add(path)
            found |= walk_keys(child, path)
    elif isinstance(value, list):
        for child in value:
            found |= walk_keys(child, prefix + "[]")
    return found
