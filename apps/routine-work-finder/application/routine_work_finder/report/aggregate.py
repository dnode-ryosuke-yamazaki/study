"""週次レポートの時間の集計(design.md「時間を集計する」)。

記録の行を作業・会議・離席・記録しなかった時間に分けて数え、離席を最後の入力まで遡る。
作業はアプリ名と題名(Excel はシート名も)の組にまとめ、上位10件・作業のまとまり・主な時間帯を出す。
記録が取れなかった時間帯は記録の共通の処理(records.py)の求め方をそのまま使う。
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import NamedTuple, Optional

from routine_work_finder import records

WORK = "work"
MEETING = "meeting"
AWAY = "away"
EXCLUDED = "excluded"
CATEGORIES = (WORK, MEETING, AWAY, EXCLUDED)

SECONDS_PER_LINE = 5
AWAY_IDLE_SECONDS = 300
NOT_COUNTED_KINDS = {"start", "stop"}
TOP_COUNT = 10
MAIN_TIMES_COUNT = 2
SESSION_BREAK = timedelta(minutes=30)
CANDIDATE_MIN_SESSIONS = 2
WEEKDAYS = "月火水木金土日"


class Session(NamedTuple):
    """作業のまとまり。同じ組が30分以上現れなかった所で区切る。終わりは最後の行の5秒後"""

    start: datetime
    end: datetime
    seconds: int

    def label(self):
        return f"{WEEKDAYS[self.start.weekday()]} {self.start:%H:%M}-{self.end:%H:%M}"


@dataclass
class WorkGroup:
    """アプリ名と題名(Excel はシート名も)の組。題名が取れなかった行はアプリ名だけの組(title が None)"""

    app: Optional[str]
    title: Optional[str]
    sheet: Optional[str]
    title_known: bool
    lines: list = field(default_factory=list)

    @property
    def seconds(self):
        return len(self.lines) * SECONDS_PER_LINE

    @property
    def sessions(self):
        return split_sessions([line["time"] for line in self.lines])

    @property
    def main_times(self):
        """長いまとまり2つを長い順に「曜日 開始-終了」で"""
        longest = sorted(self.sessions, key=lambda session: (-session.seconds, session.start))[:MAIN_TIMES_COUNT]
        return [session.label() for session in longest]


class Candidate(NamedTuple):
    """自動化案の候補。まとまりが2つ以上ある組"""

    group: WorkGroup
    sessions: list

    @property
    def session_count(self):
        return len(self.sessions)

    @property
    def seconds(self):
        return self.group.seconds

    @property
    def when(self):
        """まとまりごとの「曜日 開始-終了」を時刻の順に"""
        return [session.label() for session in self.sessions]


@dataclass
class WeekAggregate:
    """1週間分の集計の結果"""

    totals: dict
    groups: list
    gaps: list
    title_unavailable: list
    skipped: int
    # 開始・停止を除いた行と区分の組(時刻順)。Claude に渡す材料が前後のアプリと題名の組を集めるのに使う
    classified: list = field(default_factory=list)

    @property
    def top(self):
        return top_groups(self.groups)

    @property
    def candidates(self):
        return automation_candidates(self.groups)

    @property
    def gap_seconds(self):
        return int(sum((end - start).total_seconds() for start, end in self.gaps))


def aggregate_week(data_paths, start, end):
    """start 以上 end 未満の記録を集計する"""
    record_range = records.read_records(data_paths, start, end)
    classified = classify(record_range.lines)
    return WeekAggregate(
        totals=category_totals(classified),
        groups=group_work(classified),
        gaps=records.find_gaps(data_paths, start, end),
        title_unavailable=title_unavailable_times(record_range.lines),
        skipped=record_range.skipped,
        classified=classified,
    )


def classify(lines):
    """開始・停止を除いた行を時刻順に (行, 区分) の一覧で返す。離席は最後に入力した時刻まで遡って直してある"""
    counted = [line for line in lines if line["kind"] not in NOT_COUNTED_KINDS]
    found = [_first_category(line) for line in counted]
    result = list(found)
    for index, line in enumerate(counted):
        if found[index] == AWAY and line.get("idleSec") is not None:
            _back_fill_away(counted, result, index, line["time"] - timedelta(seconds=line["idleSec"]))
    return list(zip(counted, result))


def _back_fill_away(counted, result, index, last_input):
    """離席の行の前の、最後に入力した時刻以降の作業の行を離席に直す。画面のスリープを止めていた行は直さない"""
    for earlier in range(index - 1, -1, -1):
        if counted[earlier]["time"] < last_input:
            break
        if result[earlier] == WORK and counted[earlier].get("displaySleepPrevented") is not True:
            result[earlier] = AWAY


def category_totals(classified):
    """4つの区分ごとの合計の秒数(1行5秒)"""
    totals = dict.fromkeys(CATEGORIES, 0)
    for _, category in classified:
        totals[category] += SECONDS_PER_LINE
    return totals


def _first_category(line):
    """1行だけを見た区分。周りの状態が取れなかった(null の)項目は「そうでない」として次の判定へ進む"""
    if line["kind"] == "excluded":
        return EXCLUDED
    if line.get("locked") is True:
        return AWAY
    if line.get("mic") is True:
        return MEETING
    idle = line.get("idleSec")
    if idle is not None and idle >= AWAY_IDLE_SECONDS and line.get("displaySleepPrevented") is not True:
        return AWAY
    return WORK


def group_work(classified):
    """作業の行を組にまとめ、合計の時間の長い順(同じなら先に現れた順)に返す"""
    groups = {}
    for line, category in classified:
        if category != WORK:
            continue
        title = line.get("title")
        key = (line.get("app"), title, line.get("sheet"))
        if key not in groups:
            groups[key] = WorkGroup(*key, title_known=title is not None)
        groups[key].lines.append(line)
    return sorted(groups.values(), key=lambda group: -group.seconds)


def top_groups(groups):
    return groups[:TOP_COUNT]


def automation_candidates(groups):
    """まとまりが2つ以上ある組を、合計の時間の長い順に自動化案の候補にする"""
    candidates = [Candidate(group, group.sessions) for group in groups]
    candidates = [candidate for candidate in candidates if candidate.session_count >= CANDIDATE_MIN_SESSIONS]
    return sorted(candidates, key=lambda candidate: -candidate.seconds)


def split_sessions(times):
    """時刻の一覧を、同じ組が30分以上現れなかった所で区切って作業のまとまりにする"""
    sessions = []
    for time in sorted(times):
        if sessions and time - sessions[-1].end < SESSION_BREAK:
            last = sessions[-1]
            sessions[-1] = Session(last.start, time + timedelta(seconds=SECONDS_PER_LINE), last.seconds + SECONDS_PER_LINE)
        else:
            sessions.append(Session(time, time + timedelta(seconds=SECONDS_PER_LINE), SECONDS_PER_LINE))
    return sessions


def title_unavailable_times(lines):
    """題名が取れなかった行を、アプリと理由ごとの合計の秒数にまとめて長い順(同じなら先に現れた順)に返す"""
    totals = {}
    for line in lines:
        if line["kind"] == "sample" and line.get("titleUnavailable") is True:
            key = (line.get("app"), line.get("titleReason"))
            totals[key] = totals.get(key, 0) + SECONDS_PER_LINE
    ordered = sorted(totals.items(), key=lambda item: -item[1])
    return [{"app": app, "reason": reason, "seconds": seconds} for (app, reason), seconds in ordered]
