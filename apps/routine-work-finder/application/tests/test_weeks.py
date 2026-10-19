"""週の決め方(日本時間の ISO 週・金曜17時・週の名前の読み方・記録が残っている28日)。

週次レポート係が定期の作成の対象の週を決めるときと、操作スクリプトが作り直しの週を決めるときに、
同じ決め方で同じ週になることを確かめる。実行環境の時刻帯が UTC でも、時刻帯のデータが読めなくても、
日本時間で週を決める。
"""

import os
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from routine_work_finder import weeks

UTC = timezone.utc


def jst(text):
    return datetime.fromisoformat(text + "+09:00")


class FridayCloseTests(unittest.TestCase):
    """金曜17時(日本時間)を過ぎた週がレポートの対象になる"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-1
    def test_金曜16時59分は前の週が最新で17時ちょうどからその週が最新になり翌月曜もその週のまま(self):
        """否定確認: 金曜17時との比べ方を「より後」にすると17時ちょうどで落ちる"""
        self.assertEqual(weeks.latest_closed_week(jst("2026-10-09T16:59:59")).name, "2026-W40")
        self.assertEqual(weeks.latest_closed_week(jst("2026-10-09T17:00:00")).name, "2026-W41")
        self.assertEqual(weeks.latest_closed_week(jst("2026-10-12T09:00:00")).name, "2026-W41")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-1
    def test_対象の範囲は日本時間の月曜0時から金曜17時まで(self):
        """否定確認: 金曜の終わりを16時にすると落ちる"""
        week = weeks.parse_week_name("2026-W41")
        self.assertEqual(week.monday, jst("2026-10-05T00:00:00"))
        self.assertEqual(week.closing, jst("2026-10-09T17:00:00"))
        self.assertEqual(week.monday.utcoffset(), timedelta(hours=9))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-1
    def test_実行環境の時刻帯がUTCでも日本時間で同じ週になる(self):
        """否定確認: 日本時間に直さずに日付を取ると、UTC の金曜8時(日本時間17時)が前の週になって落ちる"""
        saved = os.environ.get("TZ")
        os.environ["TZ"] = "UTC"
        time.tzset()
        try:
            moment = datetime(2026, 10, 9, 8, 0, tzinfo=UTC)
            self.assertEqual(weeks.latest_closed_week(moment).name, "2026-W41")
            self.assertEqual(weeks.week_containing(datetime(2026, 10, 4, 15, 0, tzinfo=UTC)).name, "2026-W41")
            self.assertEqual(weeks.now().utcoffset(), timedelta(hours=9))
        finally:
            if saved is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = saved
            time.tzset()

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-1
    def test_時刻帯のデータが読めないときも固定の9時間の時差で同じ週になる(self):
        """否定確認: 時刻帯のデータが読めないときに UTC に倒すと落ちる"""
        with mock.patch.object(weeks, "ZoneInfo", side_effect=weeks.ZoneInfoNotFoundError("Asia/Tokyo")):
            zone = weeks.tokyo()
            self.assertEqual(zone.utcoffset(None), timedelta(hours=9))
            self.assertEqual(weeks.latest_closed_week(datetime(2026, 10, 9, 8, 0, tzinfo=UTC)).name, "2026-W41")
            self.assertEqual(weeks.parse_week_name("2026-W41").monday, jst("2026-10-05T00:00:00"))


class WeekNameTests(unittest.TestCase):
    """週の名前は ISO の週番号。存在しない週は受け付けない"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-3
    def test_ISO週として存在しない週や形の違う値は読めないとする(self):
        """否定確認: 週の番号の範囲を確かめないと W00・W60 で落ちる。53週目の有無を見ないと 2025-W53 で落ちる"""
        for text in ("2026-W00", "2026-W60", "2025-W53", "今週", "2026-41", "", None, "2026-W1", " 2026-W41"):
            with self.subTest(text=text):
                self.assertIsNone(weeks.parse_week_name(text))
        self.assertEqual(weeks.parse_week_name("2026-W52").name, "2026-W52")
        self.assertEqual(weeks.parse_week_name("2020-W53").monday, jst("2020-12-28T00:00:00"))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-3
    def test_年をまたぐ週は月曜の属するISOの年で名前が付き前後の週へ進める(self):
        """否定確認: 暦の年で名前を付けると 2027-01-01 が 2027-W53 になって落ちる"""
        week = weeks.week_containing(jst("2027-01-01T12:00:00"))
        self.assertEqual(week.name, "2026-W53")
        self.assertEqual(week.next().name, "2027-W01")
        self.assertEqual(weeks.parse_week_name("2027-W01").previous().name, "2026-W53")


class RemakeWordTests(unittest.TestCase):
    """作り直しの週の指定(current・previous・last・週の名前・指定なし)の決め方"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-8、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-2
    def test_今週は今の週で先週は1つ前の週で最新の週と指定なしは金曜17時を過ぎた最新の週(self):
        """否定確認: previous を金曜17時を過ぎた最新の週にすると金曜17時と土曜で落ちる"""
        cases = {
            "2026-10-07T10:00:00": ("2026-W41", "2026-W40", "2026-W40"),
            "2026-10-09T16:59:00": ("2026-W41", "2026-W40", "2026-W40"),
            "2026-10-09T17:00:00": ("2026-W41", "2026-W40", "2026-W41"),
            "2026-10-10T09:00:00": ("2026-W41", "2026-W40", "2026-W41"),
        }
        for text, (current, previous, last) in cases.items():
            with self.subTest(now=text):
                now = jst(text)
                self.assertEqual(weeks.resolve("current", now).name, current)
                self.assertEqual(weeks.resolve("previous", now).name, previous)
                self.assertEqual(weeks.resolve("last", now).name, last)
                self.assertEqual(weeks.resolve(None, now).name, last)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-8、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-9
    def test_週の名前はそのまま受け決まった語でも週の名前でもない値は受けない(self):
        """否定確認: 決まった語の大文字小文字を区別しないと Current で落ちる"""
        now = jst("2026-10-07T10:00:00")
        self.assertEqual(weeks.resolve("2026-W38", now).name, "2026-W38")
        for text in ("今週", "Current", "next", "2026-W60", ""):
            with self.subTest(text=text):
                self.assertIsNone(weeks.resolve(text, now))


class RetentionTests(unittest.TestCase):
    """記録が残っているのは月曜が今日から28日以内の週"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-2、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-3
    def test_月曜が27日前と28日前の週は残っていて29日前の週は残っていない(self):
        """否定確認: 28日との比べ方を「未満」にすると28日前で落ちる"""
        week = weeks.parse_week_name("2026-W41")
        for now, expected in (("2026-11-01T23:59:00", True), ("2026-11-02T00:00:00", True),
                              ("2026-11-02T23:59:00", True), ("2026-11-03T00:00:00", False)):
            with self.subTest(now=now):
                self.assertEqual(weeks.within_retention(week, jst(now)), expected)
        self.assertTrue(weeks.within_retention(week, datetime(2026, 11, 2, 14, 59, tzinfo=UTC)))
        self.assertFalse(weeks.within_retention(week, datetime(2026, 11, 2, 15, 0, tzinfo=UTC)))
