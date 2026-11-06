"""日本時間の現在時刻と、配信日・編の決定。

基準日は「起動時刻が 06:30 より前なら前日、以後なら起動日」。記事公開の配信日は
基準日から遡って最も近い配信曜日(基準日を含む)、月次見直しの配信日は基準日。
曜日の番号は launchd の Weekday と同じ 0=日曜〜6=土曜。
"""

import datetime as dt

try:
    from zoneinfo import ZoneInfo

    JST = ZoneInfo("Asia/Tokyo")
except Exception:  # zoneinfo のデータが読めない環境では固定の +09:00(日本は夏時間が無い)
    JST = dt.timezone(dt.timedelta(hours=9), "JST")

DAY_START = dt.time(6, 30)
LAST_CHANCE = dt.time(18, 30)


def now_jst():
    return dt.datetime.now(JST)


def to_jst(moment):
    return moment.astimezone(JST)


def base_date(now):
    local = to_jst(now)
    if local.time() < DAY_START:
        return local.date() - dt.timedelta(days=1)
    return local.date()


def launchd_weekday(day):
    return (day.weekday() + 1) % 7


def _as_date(value):
    return dt.date.fromisoformat(value) if isinstance(value, str) else value


def edition_for(registration, date):
    editions = registration.get("editionByWeekday")
    if not editions:
        return None
    return editions.get(str(launchd_weekday(_as_date(date))))


def _latest_delivery_on_or_before(registration, day):
    weekdays = registration["weekdays"]
    for back in range(7):
        candidate = day - dt.timedelta(days=back)
        if launchd_weekday(candidate) in weekdays:
            return candidate
    raise ValueError("配信曜日がありません")


def resolve(registration, now):
    """(配信日 YYYY-MM-DD, 編 または None) を返す。"""
    base = base_date(now)
    if registration["kind"] == "review":
        return base.isoformat(), None
    day = _latest_delivery_on_or_before(registration, base)
    return day.isoformat(), edition_for(registration, day)


def previous_delivery_date(registration, date):
    """配信日の1つ前の配信日(登録表の配信曜日で1つ前)。"""
    day = _latest_delivery_on_or_before(registration, _as_date(date) - dt.timedelta(days=1))
    return day.isoformat()


def last_chance_at(date):
    """配信日の 18:30(日本時間)。最後の再実行時刻。"""
    return dt.datetime.combine(_as_date(date), LAST_CHANCE, tzinfo=JST)
