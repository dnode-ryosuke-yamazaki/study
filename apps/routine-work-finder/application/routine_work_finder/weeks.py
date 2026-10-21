"""週の決め方。週次レポート係(report/run_report.py)と操作スクリプトの作り直し(control.py の remake)が同じ決め方を使う。

- 週は ISO の週(月曜始まり)で、名前は `YYYY-Www`(例: 2026-W41)。週の境界(月曜0時)と金曜17時は日本時間で求める
- 時刻帯は Asia/Tokyo を明示し、時刻帯のデータが読めないときは固定の+09:00 で求める(日本は夏時間が無い)。
  実行環境の時刻帯(UTC のサンドボックスなど)には左右されない
- 「金曜17時を過ぎた」は金曜17時ちょうどを含む
- 記録が残っている週は、月曜が今日(日本時間)から28日以内の週
- 作り直しの週の指定は決まった語 current(今の週)・previous(今の週の1つ前の週)・last(金曜17時を過ぎた最新の週)
  か週の名前。指定なしは last と同じ
"""

import re
from datetime import date, datetime, timedelta, timezone
from typing import NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ZONE_NAME = "Asia/Tokyo"
FIXED_JST = timezone(timedelta(hours=9))
WEEK_NAME_PATTERN = re.compile(r"^(\d{4})-W(\d{2})$")
CLOSING_OFFSET = timedelta(days=4, hours=17)
RETENTION_DAYS = 28
CURRENT = "current"
PREVIOUS = "previous"
LAST = "last"


def tokyo():
    """日本時間の時刻帯。時刻帯のデータが読めなければ固定の+09:00"""
    try:
        return ZoneInfo(ZONE_NAME)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return FIXED_JST


def now():
    """今の日時(日本時間)"""
    return datetime.now(tokyo())


def to_tokyo(moment):
    """日本時間に直す。時差の無い日時は日本時間とみなす(実行環境の時刻帯では読まない)"""
    zone = tokyo()
    if moment.tzinfo is None:
        return moment.replace(tzinfo=zone)
    return moment.astimezone(zone)


class Week(NamedTuple):
    """ISO の週。並べると古い順になる"""

    year: int
    number: int

    @property
    def name(self):
        return f"{self.year}-W{self.number:02d}"

    @property
    def monday(self):
        """月曜0時(日本時間)"""
        return datetime.fromisocalendar(self.year, self.number, 1).replace(tzinfo=tokyo())

    @property
    def closing(self):
        """金曜17時(日本時間)"""
        return self.monday + CLOSING_OFFSET

    def next(self):
        return week_of_date(self.monday.date() + timedelta(days=7))

    def previous(self):
        return week_of_date(self.monday.date() - timedelta(days=7))

    def __str__(self):
        return self.name


def week_of_date(day: date):
    year, number, _ = day.isocalendar()
    return Week(year, number)


def week_containing(moment):
    """その日時(日本時間で見る)が属する週"""
    return week_of_date(to_tokyo(moment).date())


def parse_week_name(text) -> Week | None:
    """`YYYY-Www` の形で、ISO 週として存在する週(W01〜その年の最終週)だけを読む。読めなければ None"""
    if not isinstance(text, str):
        return None
    matched = WEEK_NAME_PATTERN.match(text)
    if not matched:
        return None
    year, number = int(matched.group(1)), int(matched.group(2))
    try:
        datetime.fromisocalendar(year, number, 1)
    except ValueError:
        return None
    return Week(year, number)


def is_closed(week, moment):
    """その週の金曜17時を過ぎているか(17時ちょうどを含む)"""
    return week.closing <= to_tokyo(moment)


def current_week(moment):
    return week_containing(moment)


def previous_week(moment):
    """今の週の1つ前の週(金曜17時の前後で変わらない)"""
    return current_week(moment).previous()


def latest_closed_week(moment):
    """金曜17時を過ぎた最新の週"""
    week = current_week(moment)
    return week if is_closed(week, moment) else week.previous()


def resolve(spec, moment) -> Week | None:
    """作り直しの週の指定を週に決める。指定なし(None)は last と同じ。決まった語でも存在する週の名前でもなければ None"""
    if spec is None or spec == LAST:
        return latest_closed_week(moment)
    if spec == CURRENT:
        return current_week(moment)
    if spec == PREVIOUS:
        return previous_week(moment)
    return parse_week_name(spec)


def within_retention(week, moment):
    """月曜が今日(日本時間)から28日以内か"""
    today = to_tokyo(moment).date()
    return (today - week.monday.date()).days <= RETENTION_DAYS


def weeks_between(after, until):
    """after より後で until まで(until を含む)の週を古い順に"""
    found = []
    week = after.next()
    while week <= until:
        found.append(week)
        week = week.next()
    return found
