"""日時の解釈と日本時間への変換(design.md 候補の絞り込み 手順3)のテスト。

候補の時刻は世界標準時で届き、台帳の日時は日本時間のオフセット付きで書く。
変換を忘れると9時間ずれた枠を採用するため、届く形のばらつきを吸収して日本時間に
揃えられることを検証する。
"""

import unittest
from datetime import datetime, timedelta, timezone

import timeutil

JST = timezone(timedelta(hours=9))


class 世界標準時で届く日時の解釈(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#候補ファイルの区分
    def test_オフセットの無い日時は世界標準時として解釈し日本時間に変換できること(self):
        dt = timeutil.parse_datetime("2026-09-10T01:00:00.0000000")
        self.assertEqual(dt.utcoffset(), timedelta(0))
        self.assertEqual(timeutil.to_jst(dt), datetime(2026, 9, 10, 10, 0, tzinfo=JST))

    def test_末尾Zの日時とオフセット付きの日時をどちらも解釈できること(self):
        self.assertEqual(
            timeutil.to_jst(timeutil.parse_datetime("2026-09-10T01:00:00Z")),
            datetime(2026, 9, 10, 10, 0, tzinfo=JST),
        )
        self.assertEqual(
            timeutil.parse_datetime("2026-09-10T10:00:00+09:00"),
            datetime(2026, 9, 10, 10, 0, tzinfo=JST),
        )

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#データ設計台帳ファイル
    def test_台帳に書く日時は日本時間のオフセット付きISO8601であること(self):
        dt = datetime(2026, 9, 10, 1, 0, tzinfo=timezone.utc)
        self.assertEqual(timeutil.format_jst(dt), "2026-09-10T10:00:00+09:00")

    def test_解釈できない文字列は例外になること(self):
        with self.assertRaises(ValueError):
            timeutil.parse_datetime("not a date")


if __name__ == "__main__":
    unittest.main()
