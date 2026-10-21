"""Claude に渡す材料の組み立て(design.md「Claude に自動化案と作業の要約を作らせる」1〜4・7)。

材料に入れてよいのは、集計した組・時間・時刻、ウィンドウの題名・Excel のシート名・カーソルのある部品の種類
(中の文字は含まない)、既存の作業の記録、メモ、Skill とアプリの名前と説明だけ(requirements.md「社外へ送るもの」)。
記録の行や既存の作業の記録のほかの項目(bundleId・サイトの名前など)は、ここで項目を選んで入れないことで外す。
除外中の行は、時刻と「除外中」の印だけを入れる。形は appendix.md「Claude に渡す材料の形」。
"""

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from routine_work_finder.report import aggregate

CHAR_LIMIT = 120_000
MAX_CANDIDATES = 15
SKILLS_DIR = Path.home() / ".claude" / "skills"
# このファイルは apps/routine-work-finder/application/routine_work_finder/report/ にある
STUDY_APPS_DIR = Path(__file__).resolve().parents[4]
OVERVIEW_HEADING = "## 概要"


@dataclass
class AutomationMaterials:
    """payload: 標準入力に渡す JSON、candidates: 番号から自動化案の候補、memo_ids: 渡したメモの番号、
    reusable_names: 渡した既存の仕組みの名前"""

    payload: dict
    candidates: dict = field(default_factory=dict)
    memo_ids: set = field(default_factory=set)
    reusable_names: set = field(default_factory=set)


@dataclass
class SummaryMaterials:
    """payload: 標準入力に渡す JSON、items: 番号から上位の組(渡した順)"""

    payload: dict
    items: dict = field(default_factory=dict)


def serialize(payload):
    """標準入力に渡す文字列。字数の上限もこの文字列で数える"""
    return json.dumps(payload, ensure_ascii=False)


def build_automation_materials(week_name, week, memos, records, reusable):
    """自動化案の材料。候補は時間の長い順に最大15件、メモは全件。上限を超えたら候補を時間の短い方から減らす"""
    numbered_memos = _number_memos(memos)
    candidates = {f"c{index}": candidate for index, candidate in enumerate(week.candidates[:MAX_CANDIDATES], 1)}
    entries = [
        {
            "id": candidate_id,
            **_group_fields(candidate.group),
            "sessions": candidate.session_count,
            "totalMinutes": minutes(candidate.seconds),
            "when": candidate.when,
            "overlappingRecords": _overlapping_records(records, candidate.sessions),
        }
        for candidate_id, candidate in candidates.items()
    ]
    payload = {
        "week": week_name,
        "candidates": entries,
        "memos": [{"id": memo_id, "t": memo["time"].isoformat(), "text": memo["text"]} for memo_id, memo in numbered_memos],
        "reusable": [{"name": item["name"], "kind": item["kind"], "description": item["description"]} for item in reusable],
    }
    fit(payload, "candidates")
    kept = {entry["id"] for entry in payload["candidates"]}
    return AutomationMaterials(
        payload=payload,
        candidates={candidate_id: candidate for candidate_id, candidate in candidates.items() if candidate_id in kept},
        memo_ids={memo_id for memo_id, _ in numbered_memos},
        reusable_names={item["name"] for item in reusable},
    )


def build_summary_materials(week_name, week, memos, records):
    """作業の要約の材料。上位10件ごとに組・時間・主な時間帯・前後のアプリ・重なる記録とメモ。
    上限を超えたら項目を時間の短い方から減らす"""
    numbered_memos = _number_memos(memos)
    items = {f"w{index}": group for index, group in enumerate(week.top, 1)}
    positions = {id(line): index for index, (line, _) in enumerate(week.classified)}
    entries = []
    for item_id, group in items.items():
        sessions = group.sessions
        entries.append({
            "id": item_id,
            **_group_fields(group),
            "totalMinutes": minutes(group.seconds),
            "mainTimes": group.main_times,
            "titleKnown": group.title_known,
            "neighborApps": _neighbor_apps(week.classified, positions, group),
            "overlappingRecords": _overlapping_records(records, sessions),
            "memos": [
                {"id": memo_id, "t": memo["time"].isoformat(), "text": memo["text"]}
                for memo_id, memo in numbered_memos if _overlaps(memo["time"], sessions)
            ],
        })
    payload = {"week": week_name, "items": entries}
    fit(payload, "items")
    kept = [entry["id"] for entry in payload["items"]]
    return SummaryMaterials(payload=payload, items={item_id: items[item_id] for item_id in kept})


def collect_reusable(skills_dir=SKILLS_DIR, apps_dir=STUDY_APPS_DIR):
    """使える既存の仕組みの一覧。Skill は SKILL.md の冒頭の名前と説明、アプリは architecture.md の概要の1段落目"""
    found = []
    for path in _sorted_children(skills_dir):
        skill = _skill_entry(path / "SKILL.md")
        if skill is not None:
            found.append(skill)
    for path in _sorted_children(apps_dir):
        description = _overview_paragraph(path / "specs" / "architecture.md")
        if description:
            found.append({"name": path.name, "kind": "app", "description": description})
    return found


def _group_fields(group):
    return {"app": group.app, "title": group.title, "sheet": group.sheet, "focusRole": _focus_role(group.lines)}


def _focus_role(lines):
    """組の中で最も長くカーソルがあった部品の種類。取れなかった組は None"""
    counts = Counter(line["focusRole"] for line in lines if line.get("focusRole"))
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def minutes(seconds):
    return (seconds + 30) // 60


def _number_memos(memos):
    ordered = sorted(memos, key=lambda memo: memo["time"])
    return [(f"m{index}", memo) for index, memo in enumerate(ordered, 1)]


def _overlaps(time, sessions):
    return any(session.start <= time <= session.end for session in sessions)


def _overlapping_records(records, sessions):
    """作業のまとまりの時間帯に重なる既存の作業の記録を、時刻の順に出どころ・時刻・文だけで"""
    overlapping = sorted((record for record in records if _overlaps(record["time"], sessions)), key=lambda record: record["time"])
    return [{"source": record["source"], "t": record["time"].isoformat(), "text": _record_text(record)} for record in overlapping]


def _record_text(record):
    source = record["source"]
    if source == "jira":
        return f"{record['key']} {record['summary']} {record['field']}: {record['from'] or ''} → {record['to'] or ''}"
    if source == "confluence":
        return record["title"]
    if source == "claudeCode":
        return f"{record['repo']}: {record['text']}"
    if source == "minutes":
        return f"{record['title']}: {record['summary']}"
    raise ValueError(f"知らない記録の出どころです: {source}")


def _neighbor_apps(classified, positions, group):
    """作業のまとまりごとの直前と直後に使ったアプリ名(離席の行と同じ組の行は飛ばす)。
    除外中の行は時刻と除外中の印だけにする"""
    key = (group.app, group.title, group.sheet)
    found = []
    for session in group.sessions:
        inside = [positions[id(line)] for line in group.lines if session.start <= line["time"] < session.end]
        for step, begin in ((-1, min(inside) - 1), (1, max(inside) + 1)):
            entry = _nearest_other(classified, begin, step, key)
            if entry is not None and entry not in found:
                found.append(entry)
    return found


def _nearest_other(classified, index, step, key):
    while 0 <= index < len(classified):
        line, category = classified[index]
        index += step
        if category == aggregate.EXCLUDED:
            return {"t": line["time"].isoformat(), "excluded": True}
        if category == aggregate.AWAY or (line.get("app"), line.get("title"), line.get("sheet")) == key:
            continue
        if line.get("app"):
            return line["app"]
    return None


def fit(payload, list_key):
    """材料の字数が上限を超えるあいだ、一覧の最後(時間の最も短いもの)から減らす"""
    while len(serialize(payload)) > CHAR_LIMIT and payload[list_key]:
        payload[list_key].pop()


def _sorted_children(directory):
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.iterdir() if path.is_dir())


def _skill_entry(path):
    """SKILL.md の冒頭(--- で囲んだ部分)の name と description。どちらかが無ければ None"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    if not lines or lines[0].strip() != "---":
        return None
    values = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        name, separator, value = line.partition(":")
        if separator and name.strip() in ("name", "description"):
            values[name.strip()] = _unquote(value.strip())
    if not values.get("name") or not values.get("description"):
        return None
    return {"name": values["name"], "kind": "skill", "description": values["description"]}


def _unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _overview_paragraph(path):
    """「## 概要」の見出しのあとの最初の段落。見出しが無い・読めないときは空"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return ""
    paragraph, inside = [], False
    for line in lines:
        if not inside:
            inside = line.strip() == OVERVIEW_HEADING
            continue
        if line.startswith("#"):
            break
        if line.strip():
            paragraph.append(line.strip())
        elif paragraph:
            break
    return "\n".join(paragraph)
