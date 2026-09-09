"""日本の祝日の判定(tasks.md 2)のテスト。

候補から祝日と土日を除くための判定。祝日は固定テーブルで持つため、テーブルの範囲外の年を
黙って平日扱いしないことも検証する(範囲外に気づかず祝日の枠を候補に出す事故を防ぐ)。
"""

import unittest
from datetime import date

import holidays_jp


class 祝日と土日の判定(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補探索の既定条件-2
    def test_国民の祝日が祝日と判定されること(self):
        self.assertTrue(holidays_jp.is_holiday(date(2026, 1, 1)))
        self.assertTrue(holidays_jp.is_holiday(date(2026, 11, 23)))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補探索の既定条件-2
    def test_振替休日と国民の休日も祝日と判定されること(self):
        # 2023年は元日が日曜のため1/2が振替休日
        self.assertTrue(holidays_jp.is_holiday(date(2023, 1, 2)))
        # 2026年は敬老の日(9/21)と秋分の日(9/23)に挟まれた9/22が国民の休日
        self.assertTrue(holidays_jp.is_holiday(date(2026, 9, 22)))

    def test_祝日でない平日は祝日と判定されないこと(self):
        self.assertFalse(holidays_jp.is_holiday(date(2026, 9, 9)))  # 水曜

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補探索の既定条件-2
    def test_土曜と日曜は祝日ではないが休業日と判定されること(self):
        土曜 = date(2026, 9, 12)
        日曜 = date(2026, 9, 13)
        self.assertFalse(holidays_jp.is_holiday(土曜))
        self.assertFalse(holidays_jp.is_holiday(日曜))
        self.assertTrue(holidays_jp.is_weekend(土曜))
        self.assertTrue(holidays_jp.is_weekend(日曜))
        self.assertTrue(holidays_jp.is_non_working_day(土曜))
        self.assertTrue(holidays_jp.is_non_working_day(日曜))

    def test_祝日の平日は休業日と判定されること(self):
        self.assertTrue(holidays_jp.is_non_working_day(date(2026, 9, 21)))
        self.assertFalse(holidays_jp.is_non_working_day(date(2026, 9, 9)))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#2-日本の祝日の判定holidays_jppy
    def test_テーブルの範囲外の年は黙って平日にせず範囲外として例外になること(self):
        with self.assertRaises(holidays_jp.祝日テーブル範囲外):
            holidays_jp.is_holiday(date(2099, 1, 1))
        with self.assertRaises(holidays_jp.祝日テーブル範囲外):
            holidays_jp.is_non_working_day(date(2010, 5, 3))

    def test_テーブルが今年と来年を含んでいること(self):
        self.assertTrue(holidays_jp.covers(date(2026, 1, 1)))
        self.assertTrue(holidays_jp.covers(date(2027, 12, 31)))
        self.assertFalse(holidays_jp.covers(date(2099, 1, 1)))


if __name__ == "__main__":
    unittest.main()
