"""週次レポートが、議事録の控えからその週の会議の題名と要点を読む(契約)

その週の会議の要点を作業の要約の材料にするため、ファイル名の日時で週を絞り、「要約」の見出しの
本文の先頭500字を読む。読めない控えがあっても残りで作り、控えのフォルダが読めないときは理由を控える。
"""

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from routine_work_finder.report import sources_minutes

JST = timezone(timedelta(hours=9))
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "minutes"
REGULAR = "[定例] チーム定例MTG-20261006_013000UTC-Meeting Recording__20261006T0130__01.md"
DAILY = "[日次] デイリーMTG-20261007_000012UTC-Meeting Recording__20261007T0000__01-2.md"
WEEK_START = datetime(2026, 10, 5, 0, 0, tzinfo=JST)
WEEK_END = datetime(2026, 10, 9, 17, 0, tzinfo=JST)


def jst(text):
    return datetime.fromisoformat(text + "+09:00")


class MinutesTestCase(unittest.TestCase):
    def setUp(self):
        base = os.environ.get("TMPDIR") or tempfile.gettempdir()
        self.temporary = tempfile.TemporaryDirectory(dir=base)
        self.folder = Path(self.temporary.name) / "minutes"
        self.folder.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def copy(self, fixture_name, as_name=None):
        shutil.copy(FIXTURES / fixture_name, self.folder / (as_name or fixture_name))

    def read(self, start=WEEK_START, end=WEEK_END):
        return sources_minutes.read_minutes(start, end, self.folder)


class MinutesContractTests(MinutesTestCase):
    """控えの Markdown から題名と要点を読む"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-4
    def test_ファイル名の会議名を題名にし要約の見出しの本文を要点として日時の順に読む(self):
        self.copy(DAILY)
        self.copy(REGULAR)
        result = self.read()
        self.assertEqual(result.failures, [])
        self.assertEqual(
            [(m["title"], m["time"]) for m in result.minutes],
            [("[定例] チーム定例MTG-20261006_013000UTC-Meeting Recording", jst("2026-10-06T10:30:00")),
             ("[日次] デイリーMTG-20261007_000012UTC-Meeting Recording", jst("2026-10-07T09:00:00"))],
        )
        self.assertEqual(
            result.minutes[0]["summary"],
            "- 週次の進め方を確認した。\n- 次のリリースの日程を決めた。\n- 手順書の更新は来週に回した。",
        )
        self.assertTrue(all(m["source"] == "minutes" for m in result.minutes))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-4
    def test_要点は要約の見出しの本文の先頭500字までで次の見出しの中身を含まない(self):
        """否定確認: 500字で切らないと落ちる"""
        self.copy(DAILY)
        [minutes] = self.read().minutes
        self.assertEqual(len(minutes["summary"]), 500)
        self.assertTrue(minutes["summary"].startswith("- 担当者ごとの進捗の要点その1を確認した。"))
        self.assertNotIn("進捗\n", minutes["summary"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-4
    def test_要約が短いときは次の見出しの手前で止める(self):
        """否定確認: 次の見出しで止めないと決定事項まで入って落ちる"""
        self.copy(REGULAR)
        [minutes] = self.read().minutes
        self.assertNotIn("決定事項", minutes["summary"])
        self.assertNotIn("リリースは10月20日", minutes["summary"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-4
    def test_ファイル名の日時をUTCとして日本時間の月曜0時を含み金曜17時ちょうどを含まない範囲で絞る(self):
        """否定確認: ファイル名の日時を日本時間として読むと境界の控えの出入りが変わって落ちる"""
        names = {
            "会議-20261004_145900UTC-Meeting Recording__20261004T1459__01.md": False,  # 日曜 23:59
            "会議-20261004_150000UTC-Meeting Recording__20261004T1500__01.md": True,   # 月曜 0:00
            "会議-20261009_075900UTC-Meeting Recording__20261009T0759__01.md": True,   # 金曜 16:59
            "会議-20261009_080000UTC-Meeting Recording__20261009T0800__01.md": False,  # 金曜 17:00
        }
        for name in names:
            self.copy(REGULAR, name)
        result = self.read()
        self.assertEqual(
            [m["time"] for m in result.minutes],
            [jst("2026-10-05T00:00:00"), jst("2026-10-09T16:59:00")],
        )

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-4
    def test_要約の見出しが無い控えは使わずに読み飛ばした数を返す(self):
        """否定確認: 要約の見出しが無い控えを空の要点で使うと落ちる"""
        self.copy(REGULAR)
        text = (FIXTURES / REGULAR).read_text(encoding="utf-8").replace("## 要約", "## まとめ")
        (self.folder / "要約なし-20261007_010000UTC-Meeting Recording__20261007T0100__01.md").write_text(text, encoding="utf-8")
        result = self.read()
        self.assertEqual([m["title"] for m in result.minutes], ["[定例] チーム定例MTG-20261006_013000UTC-Meeting Recording"])
        self.assertEqual(result.skipped, {"noSummary": 1})
        self.assertEqual(result.failures, [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-4
    def test_ファイル名の日時が読めない控えは使わずに読み飛ばした数を返す(self):
        """否定確認: 日時が読めない控えを除かずに例外で止めると落ちる"""
        self.copy(REGULAR)
        for name in ("日時なし-Meeting Recording__01.md", "日付が無い-Meeting Recording__20261399T9999__01.md"):
            self.copy(REGULAR, name)
        result = self.read()
        self.assertEqual(len(result.minutes), 1)
        self.assertEqual(result.skipped, {"badName": 2})
        self.assertEqual(result.failures, [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-4
    def test_Markdownでないファイルとフォルダは見ない(self):
        self.copy(REGULAR)
        (self.folder / "メモ.txt").write_text("x", encoding="utf-8")
        (self.folder / "古い控え__20261006T0130__01").mkdir()
        result = self.read()
        self.assertEqual(len(result.minutes), 1)
        self.assertEqual(result.skipped, {})


class MinutesFailureTests(MinutesTestCase):
    """控えが読めなくても、ほかの控えと記録でレポートを作る"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-5
    def test_1つの控えが読めなくても残りの控えで作る(self):
        """否定確認: 1つの控えの読み取りの失敗で全体を止めると落ちる"""
        self.copy(REGULAR)
        (self.folder / "壊れた控え-20261007_010000UTC-Meeting Recording__20261007T0100__01.md").write_bytes(b"\xff\xfe## \x80\x81")
        result = self.read()
        self.assertEqual(len(result.minutes), 1)
        self.assertEqual(result.skipped, {"unreadable": 1})
        self.assertEqual(result.failures, [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-5
    def test_控えのフォルダが無いときは議事録を読めなかった記録として控える(self):
        result = sources_minutes.read_minutes(WEEK_START, WEEK_END, self.folder / "無いフォルダ")
        self.assertEqual(result.minutes, [])
        self.assertEqual(result.failures, [{"source": "minutes", "site": None, "reason": "missing"}])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-5
    def test_控えのフォルダの一覧が取れないときは議事録を読めなかった記録として控える(self):
        """否定確認: 一覧の取得の失敗を握りつぶして0件にすると落ちる"""
        self.copy(REGULAR)
        self.folder.chmod(0o000)
        try:
            result = self.read()
        finally:
            self.folder.chmod(0o700)
        self.assertEqual(result.minutes, [])
        self.assertEqual(result.failures, [{"source": "minutes", "site": None, "reason": "unreadable"}])


if __name__ == "__main__":
    unittest.main()
