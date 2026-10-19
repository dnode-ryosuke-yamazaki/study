"""操作スクリプトの週次レポートの作り直しの依頼。

チャットで「定型業務レポートを作り直して」と頼むと、記録の操作Skillが週の指定を決まった語か週の番号にして
操作スクリプトに渡す。操作スクリプトは日本時間で週を決め、記録が残っているかを確かめてから依頼ファイルを置く。
週次レポート係がその依頼ファイルを拾って作り直す。チャットのサンドボックスでは日付が UTC になるため、
週を決めるのは操作スクリプトだけにする。
"""

import json
import os
import stat
import time
import unittest
from datetime import datetime, timezone
from unittest import mock

from routine_work_finder import control, weeks
from routine_work_finder.report import run_report
from tests.control_support import ControlTestCase, jst, sample

UTC = timezone.utc
REQUEST_NAME = r"^\d{8}-\d{6}-[0-9a-f]{4}\.json$"


class RemakeTestCase(ControlTestCase):
    def remake(self, *week, now=None):
        argv = ["remake", "--week", *week] if week else ["remake"]
        return self.run_control(*argv, now=now)

    def request_files(self):
        if not self.paths.requests.exists():
            return []
        return sorted(self.paths.requests.iterdir())

    def requests(self):
        return [json.loads(path.read_text(encoding="utf-8")) for path in self.request_files()]

    def record_days(self, *days):
        self.write_records(*(sample(day + "T10:00:00") for day in days))


class RemakeWeekWordsTests(RemakeTestCase):
    """チャットの「今週」「先週」「最新の週」と指定なしを、操作スクリプトが日本時間で週に決める"""

    def setUp(self):
        super().setUp()
        # W40(9/28〜)と W41(10/5〜)に記録がある
        self.record_days("2026-09-28", "2026-10-05")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-2、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-8
    def test_週の指定が無いときと最新の週は金曜17時を過ぎた最新の週になる(self):
        """否定確認: 指定なしを last と同じに扱わないと落ちる"""
        for argv in ((), ("last",)):
            with self.subTest(argv=argv):
                result = self.remake(*argv)
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["data"]["week"], "2026-W40")
        self.assertEqual([request["week"] for request in self.requests()], ["2026-W40", "2026-W40"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-2、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-8
    def test_今週は今の週_先週は今の週の1つ前の週になる(self):
        """否定確認: current と previous を取り違えると落ちる"""
        self.assertEqual(self.remake("current")["data"]["week"], "2026-W41")
        self.assertEqual(self.remake("previous")["data"]["week"], "2026-W40")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-2、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-8
    def test_金曜16時59分は最新の週も先週も前の週で_17時ちょうどと土曜は最新の週だけがその週になる(self):
        """「先週」を last に当てると金曜の夕方以降に今週と取り違えるため、previous は金曜17時の前後で変わらない。
        否定確認: previous を金曜17時を過ぎた最新の週の1つ前にすると、17時ちょうどで W40 にならず落ちる"""
        cases = [("2026-10-09T16:59:00", "2026-W40", "2026-W40"),
                 ("2026-10-09T17:00:00", "2026-W41", "2026-W40"),
                 ("2026-10-10T09:00:00", "2026-W41", "2026-W40")]
        for moment, latest, previous in cases:
            with self.subTest(moment=moment):
                self.assertEqual(self.remake("last", now=jst(moment))["data"]["week"], latest)
                self.assertEqual(self.remake(now=jst(moment))["data"]["week"], latest)
                self.assertEqual(self.remake("previous", now=jst(moment))["data"]["week"], previous)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-2
    def test_実行環境の時刻帯がUTCでも日本時間で同じ週になる(self):
        """否定確認: 依頼ファイルの名前と受け付けた日時を日本時間に直さずに付けると落ちる"""
        saved = os.environ.get("TZ")
        os.environ["TZ"] = "UTC"
        time.tzset()
        try:
            result = self.remake(now=datetime(2026, 10, 9, 8, 0, tzinfo=UTC))
        finally:
            if saved is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = saved
            time.tzset()
        self.assertEqual(result["data"]["week"], "2026-W41")
        self.assertEqual(self.requests()[0]["requestedAt"], "2026-10-09T17:00:00+09:00")
        self.assertRegex(self.request_files()[0].name, r"^20261009-170000-[0-9a-f]{4}\.json$")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-2
    def test_時刻帯のデータが読めないときも固定の9時間の時差で同じ週になる(self):
        """否定確認: 時刻帯のデータが読めないときの倒し先を UTC にすると落ちる"""
        with mock.patch.object(weeks, "ZoneInfo", side_effect=weeks.ZoneInfoNotFoundError("Asia/Tokyo")):
            result = self.remake(now=datetime(2026, 10, 9, 8, 0, tzinfo=UTC))
        self.assertEqual(result["data"]["week"], "2026-W41")
        self.assertEqual(self.requests()[0]["requestedAt"], "2026-10-09T17:00:00+09:00")


class RemakeRequestFileTests(RemakeTestCase):
    """受け付けた依頼は、週次レポート係が読める形の依頼ファイルとして依頼のフォルダに置く"""

    def setUp(self):
        super().setUp()
        self.record_days("2026-09-28", "2026-10-05")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-1
    def test_決めた週と受け付けた日時だけを書いた依頼ファイルを置き_受け付けたと返す(self):
        """否定確認: 週の指定(last)を週の名前に決めずにそのまま書くと落ちる"""
        result = self.remake("last")
        self.assertEqual(result, {"ok": True, "message": "2026-W40 の作り直しを受け付けました。できたら Teams に届きます",
                                  "notices": [], "data": {"week": "2026-W40"}})
        files = self.request_files()
        self.assertEqual(len(files), 1)
        self.assertRegex(files[0].name, r"^20261007-100000-[0-9a-f]{4}\.json$")
        self.assertEqual(self.requests(), [{"week": "2026-W40", "requestedAt": "2026-10-07T10:00:00+09:00"}])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-1
    def test_置いた依頼ファイルを週次レポート係がそのまま読める(self):
        """否定確認: 依頼ファイルの名前を .json 以外で終えると、週次レポート係が拾わずに落ちる"""
        self.remake("2026-W41")
        found = run_report._request_files(self.paths.requests)
        self.assertEqual(len(found), 1)
        week, requested_at = run_report.read_request(found[0])
        self.assertEqual(week.name, "2026-W41")
        self.assertEqual(requested_at, jst("2026-10-07T10:00:00"))
        self.assertEqual([path.name for path in self.request_files()], [found[0].name])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-1
    def test_依頼のフォルダとファイルは本人だけが読み書きできる(self):
        """否定確認: フォルダを既定の権限で作ると落ちる"""
        self.remake("2026-W41")
        self.assertEqual(stat.S_IMODE(self.paths.requests.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.request_files()[0].stat().st_mode), 0o600)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-1
    def test_同じ秒に2回頼んでも依頼ファイルが上書きされない(self):
        """否定確認: 同じ名前があっても付け直さないと、2件目が1件目を上書きして落ちる"""
        with mock.patch.object(control.secrets, "token_hex", side_effect=["a1b2", "a1b2", "c3d4"]):
            self.remake("2026-W40")
            self.remake("2026-W41")
        self.assertEqual(sorted(request["week"] for request in self.requests()), ["2026-W40", "2026-W41"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-1
    def test_操作スクリプトのログには操作と週だけを書く(self):
        """否定確認: 利用者の週の指定もログに書くと落ちる"""
        self.remake("2026-W41")
        self.assertEqual(self.paths.control_log.read_text(encoding="utf-8"),
                         "2026-10-07T10:00:00+09:00 INFO remake week=2026-W41\n")


class RemakeCurrentWeekTests(RemakeTestCase):
    """金曜17時より前の今の週も、その時点までの記録で作り直しを頼める"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-4
    def test_金曜17時より前の今の週を頼むと_今の時点までの記録で作り直すことと定期のレポートも届くことを返す(self):
        """否定確認: 今の週を断る(金曜17時を過ぎた週だけを受け付ける)と落ちる"""
        self.record_days("2026-10-05")
        result = self.remake("current")
        self.assertEqual(result, {"ok": True, "message": "2026-W41 は今週のため、今の時点までの記録で作り直します。"
                                                         "金曜17時の定期のレポートも届きます",
                                  "notices": [], "data": {"week": "2026-W41"}})
        self.assertEqual(self.requests(), [{"week": "2026-W41", "requestedAt": "2026-10-07T10:00:00+09:00"}])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-4
    def test_金曜17時を過ぎた今の週は_途中までの記録ではないため通常の受け付けの文を返す(self):
        """否定確認: 今の週かどうかだけで文を分けると、金曜17時ちょうどに途中までの記録と返して落ちる"""
        self.record_days("2026-10-05")
        result = self.remake("current", now=jst("2026-10-09T17:00:00"))
        self.assertEqual(result["message"], "2026-W41 の作り直しを受け付けました。できたら Teams に届きます")


class RemakeRefusalTests(RemakeTestCase):
    """記録が無い・消えた週と、形の違う指定は、依頼を置かずにチャットで断る"""

    def assert_nothing_written(self):
        self.assertEqual(self.request_files(), [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-3
    def test_月曜が27日前と28日前の週は受け付け_29日前の週は記録がもう消えていると断る(self):
        """否定確認: 記録が消えたかを確かめないと、29日前の週を受け付けて落ちる"""
        self.record_days("2026-10-05")
        for moment in ("2026-11-01T10:00:00", "2026-11-02T23:59:00"):
            with self.subTest(moment=moment):
                self.assertTrue(self.remake("2026-W41", now=jst(moment))["ok"])
        for path in self.request_files():
            path.unlink()
        result = self.remake("2026-W41", now=jst("2026-11-03T00:00:00"))
        self.assertEqual(result, {"ok": False, "error": "recordsPurged",
                                  "message": "2026-W41 の記録はもう消えているため作り直せません"})
        self.assert_nothing_written()

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-3
    def test_28日以内で記録のファイルが1つも無い週は_その週の記録が無いと断る(self):
        """前後の週(日曜・翌月曜)の記録のファイルは、その週の記録に数えない。
        否定確認: 週の終わりを翌月曜まで含めると、W41 に翌月曜(10/12)の記録があると数えて落ちる"""
        self.record_days("2026-10-04", "2026-10-12")
        result = self.remake("2026-W41", now=jst("2026-10-14T10:00:00"))
        self.assertEqual(result, {"ok": False, "error": "noRecordsForWeek",
                                  "message": "2026-W41 の記録がないため作り直せません"})
        self.assert_nothing_written()

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-3
    def test_まだ記録が無い今の週と_まだ来ていない週も_その週の記録が無いと断る(self):
        """否定確認: 記録のファイルの有無を見ずに28日以内かだけで受け付けると落ちる"""
        self.record_days("2026-09-28")
        for week in ("current", "2026-W43"):
            with self.subTest(week=week):
                result = self.remake(week)
                self.assertEqual(result["error"], "noRecordsForWeek")
        self.assert_nothing_written()

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-3
    def test_記録のファイルの名前の形でないファイルは記録に数えない(self):
        """否定確認: 名前の先頭の日付だけを見ると、書きかけの一時ファイルを数えて落ちる"""
        self.paths.records.mkdir(parents=True)
        (self.paths.records / "2026-10-06.jsonl.tmp").write_text("", encoding="utf-8")
        self.assertEqual(self.remake("2026-W41")["error"], "noRecordsForWeek")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-3、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-9
    def test_形の違う指定は週の番号か決まった言い方で指定するよう断る(self):
        """否定確認: 空の値を指定なし(最新の週)として扱うと落ちる"""
        self.record_days("2026-09-28", "2026-10-05")
        for value in ("今週", "2026-41", "", "next", "2026-w41", "2026-W41 "):
            with self.subTest(value=value):
                result = self.remake(value)
                self.assertEqual(result, {"ok": False, "error": "invalidWeek",
                                          "message": "「今週」「先週」「最新の週」か、2026-W41 のような週の番号で指定してください"})
        self.assert_nothing_written()

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-3
    def test_存在しない週は_その週が無いと断る(self):
        """2026年は53週目があり、2025年は無い。
        否定確認: 形だけを確かめて ISO 週として存在するかを見ないと、2026-W60 を受け付けようとして落ちる"""
        self.record_days("2026-09-28", "2026-10-05")
        for value in ("2026-W00", "2026-W60", "2025-W53"):
            with self.subTest(value=value):
                result = self.remake(value)
                self.assertEqual(result, {"ok": False, "error": "invalidWeek",
                                          "message": f"{value} という週はありません。2026-W41 のように指定してください"})
        self.assert_nothing_written()
        self.assertEqual(weeks.parse_week_name("2026-W53").name, "2026-W53")


class RemakeUnwritableTests(RemakeTestCase):
    """チャットのサンドボックスで依頼のフォルダに書けないときは、何も書かずに決めた週を返す。
    Skill はその週を引数にした手元のターミナル向けのコマンドを渡す(自分で週を計算しない)"""

    def setUp(self):
        super().setUp()
        self.record_days("2026-09-28", "2026-10-05")

    def assert_unwritable(self, result, week):
        self.assertEqual(result, {"ok": False, "error": "dataFolderUnwritable",
                                  "message": "依頼のフォルダに書けなかったため、何も書いていません",
                                  "data": {"week": week}})

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-3
    def test_データフォルダに書けないときは何も書かずに_週の指定が無くても決めた週を返す(self):
        """否定確認: 決めた週を結果に入れないと落ちる"""
        self.make_unwritable()
        for argv in ((), ("current",), ("previous",), ("2026-W41",)):
            with self.subTest(argv=argv):
                expected = "2026-W41" if argv in (("current",), ("2026-W41",)) else "2026-W40"
                self.assert_unwritable(self.remake(*argv), expected)
        self.assertFalse(self.paths.requests.exists())
        self.assertFalse(self.paths.control_log.exists())

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-3
    def test_依頼のフォルダへの書き込みを拒否されたときも何も書かずに決めた週を返す(self):
        """データフォルダと control.log には書けても、依頼のフォルダが拒否される場合。
        否定確認: データフォルダと control.log だけを確かめて依頼のフォルダを確かめないと落ちる"""
        real_open = os.open

        def refuse_requests(path, *args, **kwargs):
            if str(self.paths.requests) in str(path):
                raise PermissionError(1, "Operation not permitted", str(path))
            return real_open(path, *args, **kwargs)

        with mock.patch.object(control.os, "open", side_effect=refuse_requests):
            result = self.remake()
        self.assert_unwritable(result, "2026-W40")
        self.assertEqual(self.request_files(), [])
        self.assertFalse(self.paths.control_log.exists() and self.paths.control_log.read_text(encoding="utf-8"))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-3
    def test_依頼のフォルダが読み取り専用のときも何も書かずに決めた週を返す(self):
        """否定確認: 依頼のフォルダの一時ファイルを試さずに書きにいくと、例外で止まって落ちる"""
        self.paths.requests.mkdir(parents=True)
        os.chmod(self.paths.requests, stat.S_IRUSR | stat.S_IXUSR)
        self.assert_unwritable(self.remake("previous"), "2026-W40")
        os.chmod(self.paths.requests, stat.S_IRWXU)
        self.assertEqual(self.request_files(), [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-3
    def test_形の違う指定は書けるかより先に断る(self):
        """形の違う指定はターミナルで実行し直しても通らないため、週の決まらない dataFolderUnwritable にはしない。
        否定確認: 週を決める前に書けるかを確かめると落ちる"""
        self.make_unwritable()
        self.assertEqual(self.remake("今週")["error"], "invalidWeek")


if __name__ == "__main__":
    unittest.main()
