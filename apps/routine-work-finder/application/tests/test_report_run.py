"""週次レポート係の組み上げ(対象の週の決定・二重作成の防止・ロック・作り直しの依頼の処理)。

金曜17時の定期の起動と、作り直しの依頼のフォルダの変化での起動を、同じ手順で重ならずに処理できることを確かめる。
定期の作成は成功でも失敗でも1週に1回だけ行い、作り直しは作成済みに数えない。
実際の claude -p・OneDrive・Teams・記録のデータフォルダには触れず、一時フォルダと偽物で確かめる。
"""

import io
import json
import logging
import os
import stat
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from routine_work_finder import paths, weeks
from routine_work_finder.report import run_report

HOUR = 3600
MAX_FAKE_CALLS = 30
UTC = timezone.utc


def jst(text):
    return datetime.fromisoformat(text + "+09:00")


def sample_line(moment, title="main.swift", app="Code"):
    return {"t": moment.isoformat(), "kind": "sample", "app": app, "bundleId": "com.example.app", "monitor": 1,
            "idleSec": 0.5, "locked": False, "mic": False, "displaySleepPrevented": False, "title": title}


class FakeHeadless:
    """材料の形で呼び出しの種類を見分け、種類ごとに用意した応答を順に返す。
    用意が無ければ、記録しない候補は候補0件、自動化案と作業の要約は失敗を返す"""

    def __init__(self, **responses):
        self.responses = {name: list(values) for name, values in responses.items()}
        self.calls = []

    def __call__(self, prompt, stdin_text, timeout_seconds):
        payload = json.loads(stdin_text)
        name = "proposals" if "candidates" in payload else "summaries" if "items" in payload else "exclusions"
        self.calls.append((name, payload))
        if len(self.calls) > MAX_FAKE_CALLS:
            # 同じ依頼を繰り返すなどで止まらなくなったときに、テストを止めずに失敗させる
            raise RuntimeError("呼び出しが多すぎます")
        queue = self.responses.get(name)
        if queue:
            value = queue.pop(0)
        elif name == "exclusions" and name not in self.responses:
            value = {"exclusions": []}
        else:
            return SimpleNamespace(success=False, output="", failure_category="タイムアウト")
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(success=True, output=json.dumps(value, ensure_ascii=False), failure_category="")

    def names(self):
        return [name for name, _ in self.calls]

    def weeks(self):
        """呼び出しの週を、続けて同じ週なら1つにまとめて順に"""
        found = []
        for _, payload in self.calls:
            if not found or found[-1] != payload["week"]:
                found.append(payload["week"])
        return found


class ReportRunTestCase(unittest.TestCase):
    now_text = "2026-10-09T17:05:00"

    def setUp(self):
        base = os.environ.get("TMPDIR") or tempfile.gettempdir()
        self.temporary = tempfile.TemporaryDirectory(dir=base)
        folder = Path(self.temporary.name)
        self.paths = paths.DataPaths(folder / "routine-work-finder")
        self.paths.root.mkdir(mode=0o700)
        self.onedrive = folder / "onedrive"
        self.onedrive.mkdir()
        self.clock = jst(self.now_text)
        self.bodies = []
        self.notify_results = []
        self.on_notify = None
        self.alive = set()
        self.headless = FakeHeadless()
        self.sleeps = []
        self.copy = None
        self.atlassian = lambda start, end: SimpleNamespace(jira=[], confluence=[], failures=[])
        self.claude_code = lambda start, end: SimpleNamespace(requests=[], skipped={}, failures=[])
        self.minutes = lambda start, end: SimpleNamespace(minutes=[], skipped={}, failures=[])
        self.logs = []

    def tearDown(self):
        for path in [self.paths.root, *self.paths.root.rglob("*")]:
            if path.exists():
                os.chmod(path, stat.S_IRWXU)
        self.temporary.cleanup()

    # 偽物

    def notifier(self, skill, kind, body):
        self.bodies.append(body)
        if self.on_notify is not None:
            self.on_notify(len(self.bodies), body)
        ok = self.notify_results.pop(0) if self.notify_results else True
        return {"success": ok}

    def deps(self):
        extra = {"copy": self.copy} if self.copy is not None else {}
        return run_report.Deps(
            data_paths=self.paths,
            now=lambda: self.clock,
            read_atlassian=lambda start, end: self.atlassian(start, end),
            read_claude_code=lambda start, end: self.claude_code(start, end),
            read_minutes=lambda start, end: self.minutes(start, end),
            collect_reusable=lambda: [{"name": "jira-progress", "kind": "skill", "description": "JIRA の進捗を集める"}],
            run_headless=self.headless,
            notifier=self.notifier,
            sleep=self.sleeps.append,
            onedrive_dir=self.onedrive,
            pid=4242,
            pid_alive=lambda pid: pid in self.alive,
            **extra,
        )

    def run_report(self):
        with self.assertLogs("routine_work_finder.report", level="INFO") as captured:
            code = run_report.run(self.deps())
        self.logs.extend(captured.output)
        return code

    # 記録・状態・依頼のファイル

    def write_lines(self, start_text, count, title="main.swift", app="Code", step=5):
        self.paths.records.mkdir(exist_ok=True)
        first = jst(start_text)
        by_day = {}
        for index in range(count):
            line = sample_line(first + timedelta(seconds=step * index), title=title, app=app)
            by_day.setdefault(line["t"][:10], []).append(json.dumps(line, ensure_ascii=False) + "\n")
        for day, texts in by_day.items():
            with (self.paths.records / f"{day}.jsonl").open("a", encoding="utf-8") as file:
                file.write("".join(texts))

    def write_week_lines(self, name, count=3, title="main.swift"):
        """その週の月曜10時から少しだけの記録(作業が5時間未満の週になる)"""
        monday = weeks.parse_week_name(name).monday
        self.write_lines((monday + timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%S"), count, title=title)

    def write_enough_week(self, name, title="進捗表.xlsx", app="Microsoft Excel"):
        """月曜と火曜の9時から2時間半ずつ、同じ組の作業(ちょうど5時間で自動化案の候補が1つ)"""
        monday = weeks.parse_week_name(name).monday
        for day in (0, 1):
            start = monday + timedelta(days=day, hours=9)
            self.write_lines(start.strftime("%Y-%m-%dT%H:%M:%S"), 1800, title=title, app=app)

    def write_state(self, weeks_results):
        self.paths.report_state.write_text(json.dumps({"version": 1, "weeks": {
            name: {"result": result, "at": "2026-09-01T17:00:00+09:00", "notified": True}
            for name, result in weeks_results.items()}}), encoding="utf-8")

    def read_state(self):
        if not self.paths.report_state.exists():
            return {}
        return json.loads(self.paths.report_state.read_text(encoding="utf-8"))["weeks"]

    def results(self):
        return {name: entry["result"] for name, entry in self.read_state().items()}

    def write_request(self, file_name, content):
        self.paths.requests.mkdir(exist_ok=True)
        path = self.paths.requests / file_name
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
        return path

    def request(self, week, requested_at="2026-10-09T18:00:00+09:00", file_name=None):
        return self.write_request(file_name or f"20261009-180000-{week[-2:]}00.json",
                                  {"week": week, "requestedAt": requested_at})

    def remaining_requests(self):
        return sorted(path.name for path in self.paths.requests.iterdir()) if self.paths.requests.exists() else []

    def local_html(self, week):
        return (self.paths.reports / f"{week}.html").read_text(encoding="utf-8")

    def write_lock(self, owner=None, age_hours=0, raw=None):
        self.paths.report_lock.mkdir()
        owner_path = self.paths.report_lock / "owner.json"
        if raw is not None:
            owner_path.write_text(raw, encoding="utf-8")
        elif owner is not None:
            owner_path.write_text(json.dumps(owner), encoding="utf-8")
        moment = (self.clock - timedelta(hours=age_hours)).timestamp()
        os.utime(self.paths.report_lock, (moment, moment))


class TargetWeekTests(ReportRunTestCase):
    """定期の作成の対象の週の決め方"""

    now_text = "2026-10-10T09:00:00"

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-2
    def test_金曜17時を2回またいで眠っていたら作っていない2週を古い順に作りどちらも状態に書く(self):
        """否定確認: 対象を直近の週だけにすると W40 が作られずに落ちる"""
        self.write_state({"2026-W39": "generated"})
        self.write_week_lines("2026-W40")
        self.write_week_lines("2026-W41")
        self.run_report()
        self.assertEqual(self.headless.weeks(), ["2026-W40", "2026-W41"])
        self.assertEqual(self.results(), {"2026-W39": "generated", "2026-W40": "insufficient", "2026-W41": "insufficient"})

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-2
    def test_月曜が28日より前の週は記録があっても作らない(self):
        """否定確認: 28日以内かを確かめないと W37 も作られて落ちる"""
        self.write_state({"2026-W30": "generated"})
        for name in ("2026-W37", "2026-W38", "2026-W39", "2026-W40", "2026-W41"):
            self.write_week_lines(name)
        self.run_report()
        self.assertEqual(self.headless.weeks(), ["2026-W38", "2026-W39", "2026-W40", "2026-W41"])
        self.assertNotIn("2026-W37", self.read_state())

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-2
    def test_状態のファイルが空のときは直近に過ぎた金曜17時の週だけを作る(self):
        """否定確認: 空のときに28日分さかのぼると W40 も作られて落ちる"""
        self.write_week_lines("2026-W40")
        self.write_week_lines("2026-W41")
        self.run_report()
        self.assertEqual(self.headless.weeks(), ["2026-W41"])
        self.assertEqual(self.results(), {"2026-W41": "insufficient"})

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-1
    def test_金曜16時59分の起動ではその週を作らず17時の起動で作る(self):
        """否定確認: 金曜17時を待たずに今の週を対象にすると16時59分で W41 が作られて落ちる"""
        self.write_state({"2026-W40": "generated"})
        self.write_week_lines("2026-W41")
        self.clock = jst("2026-10-09T16:59:00")
        self.run_report()
        self.assertEqual(self.headless.calls, [])
        self.clock = jst("2026-10-09T17:00:00")
        self.run_report()
        self.assertEqual(self.headless.weeks(), ["2026-W41"])
        self.assertEqual(self.results()["2026-W41"], "insufficient")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-1
    def test_範囲は月曜0時から金曜17時までで金曜17時より後の記録は入れない(self):
        """否定確認: 範囲の終わりを起動した時刻にすると金曜17時2分の題名が入って落ちる"""
        self.write_state({"2026-W40": "generated"})
        self.write_lines("2026-10-04T23:59:00", 3, title="前の週の日曜.txt")
        self.write_lines("2026-10-05T00:00:00", 3, title="月曜0時.txt")
        self.write_lines("2026-10-09T16:59:50", 2, title="金曜16時59分.txt")
        self.write_lines("2026-10-09T17:02:00", 3, title="金曜17時のあと.txt")
        self.run_report()
        _, payload = self.headless.calls[0]
        self.assertEqual(sorted(window["title"] for window in payload["windows"]), ["月曜0時.txt", "金曜16時59分.txt"])


class OncePerWeekTests(ReportRunTestCase):
    """定期の作成は成功でも失敗でも1週に1回だけ"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-5
    def test_記録が1行も無い週は保存も通知もせず状態に記録なしと書く(self):
        """否定確認: 記録が無い週でもレポートを作ると保存のファイルができて落ちる"""
        self.write_state({"2026-W40": "generated"})
        self.run_report()
        self.assertEqual(self.read_state()["2026-W41"]["result"], "noRecords")
        self.assertIs(self.read_state()["2026-W41"]["notified"], False)
        self.assertEqual((self.bodies, list(self.onedrive.iterdir()), self.headless.calls), ([], [], []))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-4、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-7
    def test_通知が3回とも失敗したら状態に通知できなかったと書き次の起動で送り直さない(self):
        """否定確認: 通知の成否を状態に書かずに常に真にすると落ちる"""
        self.write_state({"2026-W40": "generated"})
        self.write_week_lines("2026-W41")
        self.notify_results = [False, False, False]
        self.run_report()
        self.assertEqual(self.read_state()["2026-W41"], {
            "result": "insufficient", "at": "2026-10-09T17:05:00+09:00", "notified": False})
        self.assertEqual(len(self.bodies), 3)
        self.run_report()
        self.assertEqual(len(self.bodies), 3)
        self.assertEqual(self.headless.weeks(), ["2026-W41"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-7
    def test_Claudeが3回続けて失敗した週は作成の失敗と書かれ次の起動で作り直さない(self):
        """否定確認: 作成の失敗の週を状態に書かないと次の起動で作り直されて落ちる"""
        self.write_state({"2026-W40": "generated"})
        self.write_enough_week("2026-W41")
        self.run_report()
        self.assertEqual(self.results()["2026-W41"], "claudeFailed")
        self.assertEqual(self.headless.names(), ["proposals"] * 3 + ["exclusions"])
        self.run_report()
        self.assertEqual(len(self.headless.calls), 4)
        self.assertEqual(len(self.bodies), 1)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-7
    def test_保存に3回失敗した週は保存の失敗と書かれ次の起動で作り直さない(self):
        """否定確認: 保存の失敗を結果に移さず Claude の結果を書くと落ちる"""
        def failing_copy(source, dest):
            raise OSError(11, "Resource deadlock avoided")
        self.copy = failing_copy
        self.write_state({"2026-W40": "generated"})
        self.write_week_lines("2026-W41")
        self.run_report()
        self.assertEqual(self.read_state()["2026-W41"]["result"], "saveFailed")
        self.assertIs(self.read_state()["2026-W41"]["notified"], True)
        self.assertIn("OneDrive に保存できませんでした", self.bodies[0])
        self.run_report()
        self.assertEqual(len(self.bodies), 1)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-7
    def test_思わぬ例外で止まった週は失敗と書かれ思わぬ失敗の本文で知らせロックを外し次の起動で作り直さない(self):
        """否定確認: 思わぬ例外のときに状態へ失敗を書かないと次の起動で作り直されて落ちる"""
        self.write_state({"2026-W40": "generated"})
        self.write_week_lines("2026-W41")
        self.headless = FakeHeadless(exclusions=[RuntimeError("壊れた")])
        self.assertEqual(self.run_report(), 1)
        self.assertEqual(self.read_state()["2026-W41"]["result"], "failed")
        self.assertEqual(len(self.bodies), 1)
        self.assertIn("2026-W41 の週次レポートの作成に失敗しました", self.bodies[0])
        self.assertIn("「2026-W41 の定型業務レポートを作り直して」", self.bodies[0])
        self.assertFalse(self.paths.report_lock.exists())
        self.assertTrue(any("ERROR" in line and "unexpected" in line for line in self.logs))
        self.headless = FakeHeadless()
        self.run_report()
        self.assertEqual(self.headless.calls, [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-7
    def test_対象の週を決める前に止まったら週の名前のない思わぬ失敗の本文で知らせロックを外す(self):
        """否定確認: 週が決まる前でも週の名前入りの本文を使おうとすると落ちる"""
        with mock.patch.object(run_report.weeks, "latest_closed_week", side_effect=RuntimeError("壊れた")):
            self.assertEqual(self.run_report(), 1)
        self.assertEqual(len(self.bodies), 1)
        self.assertIn("対象の週を決める前に止まりました", self.bodies[0])
        self.assertNotRegex(self.bodies[0], r"\d{4}-W\d{2}")
        self.assertFalse(self.paths.report_lock.exists())
        self.assertEqual(self.read_state(), {})

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-7
    def test_状態のファイルがJSONとして読めないときは退避して空から続け退避の本文で知らせる(self):
        """否定確認: 読めない状態のファイルを退避せずに上書きすると退避先が無くて落ちる"""
        self.paths.report_state.write_text("{壊れた", encoding="utf-8")
        self.write_week_lines("2026-W41")
        self.run_report()
        backup = self.paths.root / "report-state.broken-20261009-170500.json"
        self.assertEqual(backup.read_text(encoding="utf-8"), "{壊れた")
        self.assertEqual(self.results(), {"2026-W41": "insufficient"})
        self.assertIn("状態のファイルが読めなかったため退避して続けました", self.bodies[0])
        self.assertIn(f"退避先: {backup}", self.bodies[0])
        self.assertFalse(any("対象の週を決める前に止まりました" in body for body in self.bodies))
        self.assertEqual(len(self.bodies), 2)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-7
    def test_状態のファイルの形が違うときも退避して空から続ける(self):
        """否定確認: 形を確かめずに読むと退避されずに落ちる"""
        for content in ({"version": 1, "weeks": []}, {"version": 1, "weeks": {"W41": {"result": "generated"}}},
                        {"version": 1, "weeks": {"2026-W40": {"result": "できた"}}}, ["2026-W40"]):
            with self.subTest(content=content):
                for path in self.paths.root.glob("report-state*"):
                    path.unlink()
                self.bodies.clear()
                self.paths.report_state.write_text(json.dumps(content), encoding="utf-8")
                self.run_report()
                self.assertEqual(len(list(self.paths.root.glob("report-state.broken-*.json"))), 1)
                self.assertEqual(self.results(), {"2026-W41": "noRecords"})
                self.assertIn("退避して続けました", self.bodies[0])


class RequestTests(ReportRunTestCase):
    """作り直しの依頼の処理"""

    now_text = "2026-10-10T09:00:00"

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-1、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-5
    def test_依頼の週を作り直して同じ名前で上書きし作り直しは状態に書かずリンク付きで知らせる(self):
        """否定確認: 作り直しの結果を状態に書くと W40 の結果が変わって落ちる"""
        self.write_state({"2026-W40": "claudeFailed", "2026-W41": "generated"})
        (self.onedrive / "2026-W40.html").write_text("前のレポート", encoding="utf-8")
        self.write_week_lines("2026-W40")
        self.request("2026-W40")
        self.run_report()
        self.assertIn("2026-W40", (self.onedrive / "2026-W40.html").read_text(encoding="utf-8"))
        self.assertNotEqual((self.onedrive / "2026-W40.html").read_text(encoding="utf-8"), "前のレポート")
        self.assertEqual(self.read_state()["2026-W40"]["result"], "claudeFailed")
        self.assertEqual(self.read_state()["2026-W40"]["at"], "2026-09-01T17:00:00+09:00")
        self.assertEqual(len(self.bodies), 1)
        self.assertIn("週: 2026-W40", self.bodies[0])
        self.assertRegex(self.bodies[0], r'<a href="https://[^"]*routineWorkFinder%2F2026-W40\.html[^"]*">2026-W40\.html</a>')
        self.assertEqual(self.remaining_requests(), [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-7、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-7
    def test_金曜17時を過ぎて状態に無い週の依頼は定期の作成として1回だけ作り状態に書く(self):
        """否定確認: 依頼を定期の作成に切り替えた週を対象の一覧から除かないと W41 が二度作られて落ちる"""
        self.write_state({"2026-W40": "generated"})
        self.write_week_lines("2026-W41")
        self.request("2026-W41")
        self.run_report()
        self.assertEqual(self.headless.weeks(), ["2026-W41"])
        self.assertEqual(len(self.headless.calls), 1)
        self.assertEqual(self.results()["2026-W41"], "insufficient")
        self.assertEqual(len(self.bodies), 1)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-7、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-1
    def test_状態に無い同じ週の依頼が2件あれば1件目は定期の作成で状態に書き2件目は作り直しで状態に書かない(self):
        """否定確認: 2件目も定期の作成として扱うと状態への書き込みが2回になって落ちる"""
        self.write_state({"2026-W40": "generated"})
        self.write_week_lines("2026-W41")
        self.request("2026-W41", file_name="20261009-180000-0001.json")
        self.request("2026-W41", file_name="20261009-180100-0002.json")
        self.run_report()
        self.assertEqual([payload["week"] for _, payload in self.headless.calls], ["2026-W41", "2026-W41"])
        self.assertEqual(len(self.bodies), 2)
        self.assertEqual(self.results(), {"2026-W40": "generated", "2026-W41": "insufficient"})
        self.assertEqual(sum("state week=2026-W41" in line for line in self.logs), 1)
        self.assertTrue(any("kind=schedule week=2026-W41" in line for line in self.logs))
        self.assertTrue(any("kind=remake week=2026-W41" in line for line in self.logs))
        self.assertEqual(self.remaining_requests(), [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-2
    def test_最後がW36でW38の依頼があればW38を先に作りW37とW39とW40を漏れなく作る(self):
        """否定確認: 対象の一覧を依頼の処理のあとに決めると W37 が落ちて落ちる"""
        self.clock = jst("2026-10-03T10:00:00")
        self.write_state({"2026-W36": "generated"})
        for name in ("2026-W37", "2026-W38", "2026-W39", "2026-W40"):
            self.write_week_lines(name)
        self.request("2026-W38")
        self.run_report()
        self.assertEqual(self.headless.weeks(), ["2026-W38", "2026-W37", "2026-W39", "2026-W40"])
        self.assertEqual(sorted(self.read_state()), ["2026-W36", "2026-W37", "2026-W38", "2026-W39", "2026-W40"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-2
    def test_依頼を処理したら次の依頼へ戻りそのあとで対象の週を作る(self):
        """否定確認: 依頼より先に対象の週を作ると、依頼の W39 が作り直しとしてもう一度作られて落ちる"""
        self.write_state({"2026-W38": "generated"})
        for name in ("2026-W39", "2026-W41"):
            self.write_week_lines(name)
        self.request("2026-W40", file_name="20261009-180000-0001.json")
        self.request("2026-W39", file_name="20261009-180001-0002.json")
        self.run_report()
        self.assertEqual(self.headless.weeks(), ["2026-W39", "2026-W41"])
        self.assertEqual(self.results(), {"2026-W38": "generated", "2026-W39": "insufficient",
                                          "2026-W40": "noRecords", "2026-W41": "insufficient"})
        self.assertIn("2026-W40 は記録が0件のため作り直せませんでした", self.bodies[0])
        self.assertEqual(self.remaining_requests(), [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-2、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-1
    def test_ロックを外す前に残っていた依頼を処理し対象の週の一覧は決め直さない(self):
        """否定確認: ロックを外す前に依頼のフォルダを見直さないと W39 の依頼が残って落ちる。
        見直しで対象の週を決め直すと、17時を過ぎた W41 が作られて落ちる"""
        self.clock = jst("2026-10-09T16:59:00")
        self.write_state({"2026-W39": "generated"})
        for name in ("2026-W39", "2026-W40", "2026-W41"):
            self.write_week_lines(name)

        def arrive(count, body):
            if count == 1:
                self.request("2026-W39")
                self.clock = jst("2026-10-09T17:01:00")
        self.on_notify = arrive
        self.run_report()
        self.assertEqual(self.headless.weeks(), ["2026-W40", "2026-W39"])
        self.assertEqual(sorted(self.read_state()), ["2026-W39", "2026-W40"])
        self.assertEqual(self.remaining_requests(), [])
        self.assertFalse(self.paths.report_lock.exists())

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-1
    def test_処理を終えた依頼ファイルは消え見直しで同じ依頼をもう一度処理しない(self):
        """否定確認: 処理した依頼ファイルを消さないと依頼が残り、見直しでも同じ依頼をもう一度作って落ちる"""
        self.write_state({"2026-W41": "generated"})
        self.write_week_lines("2026-W40")
        self.request("2026-W40")
        self.run_report()
        self.assertEqual(self.headless.weeks(), ["2026-W40"])
        self.assertEqual(len(self.headless.calls), 1)
        self.assertEqual(self.remaining_requests(), [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-1、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-3
    def test_形が読めない依頼ファイルは作らずにログに書いて消す(self):
        """否定確認: 週の名前が ISO 週として存在するかを確かめないと 2026-W60 で作り始めて落ちる"""
        self.write_state({"2026-W41": "generated"})
        self.write_week_lines("2026-W40")
        contents = {
            "a-json.json": "{壊れた",
            "b-noweek.json": {"requestedAt": "2026-10-09T18:00:00+09:00"},
            "c-null.json": {"week": None, "requestedAt": "2026-10-09T18:00:00+09:00"},
            "d-shape.json": {"week": "2026-40", "requestedAt": "2026-10-09T18:00:00+09:00"},
            "e-missing-week.json": {"week": "2026-W60", "requestedAt": "2026-10-09T18:00:00+09:00"},
            "f-no-requested.json": {"week": "2026-W40"},
            "g-bad-requested.json": {"week": "2026-W40", "requestedAt": "きのう"},
            "h-list.json": ["2026-W40"],
        }
        for name, content in contents.items():
            self.write_request(name, content)
        self.run_report()
        self.assertEqual(self.headless.calls, [])
        self.assertEqual(self.bodies, [])
        self.assertEqual(self.remaining_requests(), [])
        for name in contents:
            self.assertTrue(any("WARN" in line and "request invalid" in line and name in line for line in self.logs), name)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-1
    def test_処理中に思わぬ例外で止まった依頼ファイルは消し週の名前入りの失敗を知らせロックを外す(self):
        """否定確認: 思わぬ例外のときに依頼ファイルを消さないと残って落ちる"""
        self.write_state({"2026-W40": "generated", "2026-W41": "generated"})
        self.write_week_lines("2026-W40")
        self.request("2026-W40")
        self.headless = FakeHeadless(exclusions=[RuntimeError("壊れた")])
        self.assertEqual(self.run_report(), 1)
        self.assertEqual(self.remaining_requests(), [])
        self.assertEqual(len(self.bodies), 1)
        self.assertIn("2026-W40 の週次レポートの作成に失敗しました", self.bodies[0])
        self.assertEqual(self.results(), {"2026-W40": "generated", "2026-W41": "generated"})
        self.assertFalse(self.paths.report_lock.exists())

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-6
    def test_受け付けたあとで範囲の記録が0行なら作らず記録が0件の本文だけで知らせる(self):
        """否定確認: 作り直しで記録が0行のときに知らせないと落ちる"""
        self.write_state({"2026-W40": "generated", "2026-W41": "generated"})
        self.request("2026-W40")
        self.run_report()
        self.assertEqual(self.bodies, ["【定型業務の週次レポート】<br>2026-W40 は記録が0件のため作り直せませんでした"])
        self.assertEqual(list(self.onedrive.iterdir()), [])
        self.assertEqual(self.results(), {"2026-W40": "generated", "2026-W41": "generated"})

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-6、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-5
    def test_定期の作成に切り替えた依頼で記録が0行なら記録なしと書いたうえで記録が0件の本文で知らせる(self):
        """否定確認: 定期の作成に切り替えた経路で知らせないと落ちる"""
        self.write_state({"2026-W40": "generated"})
        self.request("2026-W41")
        self.run_report()
        self.assertEqual(self.read_state()["2026-W41"]["result"], "noRecords")
        self.assertIs(self.read_state()["2026-W41"]["notified"], True)
        self.assertEqual(self.bodies, ["【定型業務の週次レポート】<br>2026-W41 は記録が0件のため作り直せませんでした"])


class CurrentWeekRemakeTests(ReportRunTestCase):
    """金曜17時より前の今の週の作り直し"""

    now_text = "2026-10-07T12:00:00"

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-4
    def test_今週の途中の作り直しは頼んだ時点までで途中までの記録になり状態に書かれず金曜17時に定期の作成が行われる(self):
        """否定確認: 範囲の終わりを処理を始めた時刻にすると頼んだあとの題名が入って落ちる"""
        self.write_state({"2026-W40": "generated"})
        self.write_lines("2026-10-05T09:00:00", 3, title="朝の作業.txt")
        self.write_lines("2026-10-07T11:00:00", 3, title="頼んだあとの作業.txt")
        self.request("2026-W41", requested_at="2026-10-07T10:00:00+09:00")
        self.run_report()
        _, payload = self.headless.calls[0]
        self.assertEqual([window["title"] for window in payload["windows"]], ["朝の作業.txt"])
        self.assertIn("〜10月7日(水) 10:00(途中までの記録)", self.local_html("2026-W41"))
        self.assertNotIn("2026-W41", self.read_state())
        self.clock = jst("2026-10-09T17:00:00")
        self.run_report()
        self.assertEqual(self.results()["2026-W41"], "insufficient")
        self.assertNotIn("途中までの記録", self.local_html("2026-W41"))
        self.assertEqual(self.headless.weeks(), ["2026-W41"])
        self.assertEqual(len(self.headless.calls), 2)


class LockTests(ReportRunTestCase):
    """ロック(同時に動かない仕組み)"""

    now_text = "2026-10-10T09:00:00"

    def setUp(self):
        super().setUp()
        self.write_state({"2026-W40": "generated"})
        self.write_week_lines("2026-W41")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-1
    def test_ほかの起動がロックを持っていれば何もせず終わる(self):
        """否定確認: ロックが取れなくても続けると W41 が作られて落ちる"""
        self.alive.add(777)
        self.write_lock({"pid": 777, "at": "2026-10-10T08:30:00+09:00"})
        self.request("2026-W40")
        self.run_report()
        self.assertEqual((self.headless.calls, self.bodies), ([], []))
        self.assertTrue(self.paths.report_lock.exists())
        self.assertEqual(self.remaining_requests(), ["20261009-180000-4000.json"])
        self.assertTrue(any("skip reason=locked" in line for line in self.logs))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-1
    def test_2時間より古いロックでもpidが動いていれば捨てない(self):
        """否定確認: pid を確かめずに古さだけで捨てると W41 が作られて落ちる"""
        self.alive.add(777)
        self.write_lock({"pid": 777, "at": "2026-10-10T06:59:00+09:00"}, age_hours=3)
        self.run_report()
        self.assertEqual(self.headless.calls, [])
        self.assertTrue(self.paths.report_lock.exists())

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-1
    def test_2時間より古くpidが動いていないロックは捨てて取り直す(self):
        """否定確認: 動いていない pid のロックを捨てないと W41 が作られずに落ちる"""
        self.write_lock({"pid": 777, "at": "2026-10-10T06:59:00+09:00"})
        self.run_report()
        self.assertEqual(self.headless.weeks(), ["2026-W41"])
        self.assertFalse(self.paths.report_lock.exists())

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-1
    def test_2時間以内のロックはpidが動いていなくても捨てない(self):
        """否定確認: 古さを確かめずに pid だけで捨てると W41 が作られて落ちる"""
        self.write_lock({"pid": 777, "at": "2026-10-10T07:00:00+09:00"})
        self.run_report()
        self.assertEqual(self.headless.calls, [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-1
    def test_持ち主のファイルが無いか読めないロックはフォルダの更新日時が2時間より古ければ捨て新しければ捨てない(self):
        """否定確認: 持ち主のファイルが無いロックを常に捨てると新しいロックで落ちる"""
        for raw, age, expected in ((None, 3, True), (None, 1, False), ("{壊れた", 3, True), ("{壊れた", 1, False),
                                   ('{"pid": "777", "at": "きのう"}', 1, False)):
            with self.subTest(raw=raw, age=age):
                for path in self.paths.root.glob("report-state.json"):
                    path.unlink()
                self.write_state({"2026-W40": "generated"})
                if self.paths.report_lock.exists():
                    for child in self.paths.report_lock.iterdir():
                        child.unlink()
                    self.paths.report_lock.rmdir()
                self.headless = FakeHeadless()
                self.write_lock(raw=raw, age_hours=age)
                self.run_report()
                self.assertEqual(bool(self.headless.calls), expected)
                self.assertEqual(self.paths.report_lock.exists(), not expected)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-1
    def test_依頼を1件処理するたびにロックの持ち主の日時を書き直す(self):
        """否定確認: 持ち主の日時を取ったときのままにすると2件目の通知のときの日時が違って落ちる"""
        self.write_state({"2026-W40": "generated", "2026-W41": "generated"})
        self.write_week_lines("2026-W40")
        self.request("2026-W40", file_name="20261009-180000-0001.json")
        self.request("2026-W41", file_name="20261009-180001-0002.json")
        seen = []

        def arrive(count, body):
            owner = json.loads((self.paths.report_lock / "owner.json").read_text(encoding="utf-8"))
            seen.append(owner)
            self.clock += timedelta(minutes=30)
        self.on_notify = arrive
        self.run_report()
        self.assertEqual(seen, [{"pid": 4242, "at": "2026-10-10T09:00:00+09:00"},
                                {"pid": 4242, "at": "2026-10-10T09:30:00+09:00"}])


class ConfigTests(ReportRunTestCase):
    """操作の記録の設定ファイルが無い・読めないときもレポートを作り続ける"""

    def setUp(self):
        super().setUp()
        self.write_state({"2026-W40": "generated"})
        self.write_week_lines("2026-W41")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-8
    def test_設定ファイルが無いときは異常を出さず記録しないアプリとことばの初期値を出し終わりの予定を出さない(self):
        """否定確認: 設定ファイルが無いのを読めないと同じに扱うと「設定ファイルが読めない」が出て落ちる"""
        self.run_report()
        html_text = self.local_html("2026-W41")
        self.assertIn("パスワード・キーチェーンアクセス・システム設定", html_text)
        self.assertNotIn("設定ファイルが読めない", html_text)
        self.assertNotIn("に終わります", html_text)
        self.assertEqual(self.results()["2026-W41"], "insufficient")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-8
    def test_設定ファイルが読めないときは読めないと出し一覧と終わりの予定を出さずにレポートを作る(self):
        """否定確認: 読めない設定ファイルで止まるとレポートが作られずに落ちる"""
        self.paths.config.write_text("{壊れた", encoding="utf-8")
        self.run_report()
        html_text = self.local_html("2026-W41")
        self.assertIn("設定ファイルが読めない", html_text)
        self.assertNotIn("パスワード・キーチェーンアクセス", html_text)
        self.assertNotIn("に終わります", html_text)
        self.assertEqual(self.headless.names(), ["exclusions"])
        self.assertEqual(self.results()["2026-W41"], "insufficient")


class SourceAndExclusionFlowTests(ReportRunTestCase):
    """既存の作業の記録の取り込みと、記録しない候補の呼び出しの流れ"""

    def setUp(self):
        super().setUp()
        self.write_state({"2026-W40": "generated"})

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-5
    def test_一部の記録が読めなくても残りの記録で作り読めなかった記録の名前が記録の状態に出る(self):
        """否定確認: 読み込みの思わぬ例外を囲まないとレポートが止まって落ちる"""
        self.write_enough_week("2026-W41")
        moment = jst("2026-10-05T09:30:00")
        self.atlassian = lambda start, end: SimpleNamespace(
            jira=[{"source": "jira", "site": "a.atlassian.net", "key": "SAG-1", "summary": "進捗", "field": "status",
                   "from": "未着手", "to": "進行中", "time": moment}],
            confluence=[], failures=[{"source": "confluence", "site": "a.atlassian.net", "reason": "auth"}])

        def broken(start, end):
            raise RuntimeError("壊れた")
        self.claude_code = broken
        self.minutes = lambda start, end: SimpleNamespace(
            minutes=[{"source": "minutes", "title": "定例", "summary": "進捗の確認", "time": moment}], skipped={}, failures=[])
        self.run_report()
        _, payload = self.headless.calls[0]
        self.assertEqual([record["source"] for record in payload["candidates"][0]["overlappingRecords"]], ["jira", "minutes"])
        html_text = self.local_html("2026-W41")
        self.assertIn("Confluence(a.atlassian.net): 認証に失敗したため", html_text)
        self.assertIn("Claude Code の会話: 読めなかったため", html_text)
        self.assertTrue(any("WARN" in line and "source=claudeCode" in line for line in self.logs))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-5
    def test_検索で断られたサイトはステータスを打ち切られたサイトは一部のみと分けてログに書く(self):
        """否定確認: ステータスを書かないと原因を切り分けられず落ちる"""
        self.write_enough_week("2026-W41")
        self.atlassian = lambda start, end: SimpleNamespace(
            jira=[], confluence=[],
            failures=[{"source": "jira", "site": "a.atlassian.net", "reason": "request", "status": 400},
                      {"source": "confluence", "site": "a.atlassian.net", "reason": "truncated"}])
        self.run_report()
        self.assertTrue(any("WARN" in line and "source=jira site=a.atlassian.net failed reason=request status=400" in line
                            for line in self.logs))
        self.assertTrue(any("WARN" in line and "source=confluence site=a.atlassian.net partial reason=truncated" in line
                            for line in self.logs))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#記録しない候補の提案-7
    def test_作業が5時間未満の週も記録しない候補だけは呼び結果は記録が足りない週のまま(self):
        """否定確認: 記録が足りない週で記録しない候補を飛ばすと落ちる"""
        self.write_week_lines("2026-W41")
        self.run_report()
        self.assertEqual(self.headless.names(), ["exclusions"])
        self.assertEqual(self.results()["2026-W41"], "insufficient")
        self.assertIn("自動化案: 記録が5時間未満のため作っていません", self.bodies[0])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#記録しない候補の提案-6
    def test_自動化案が3回続けて失敗しても記録しない候補を呼び候補がレポートに出る(self):
        """否定確認: 自動化案の失敗のときに記録しない候補を渡さないと候補の欄が空になって落ちる"""
        self.write_enough_week("2026-W41")
        self.headless = FakeHeadless(exclusions=[{"exclusions": [
            {"kind": "社外秘の固有名", "target": "word", "value": "進捗表", "example": "進捗表.xlsx", "reason": "案件名"}]}])
        self.run_report()
        self.assertEqual(self.headless.names(), ["proposals"] * 3 + ["exclusions"])
        self.assertEqual(self.results()["2026-W41"], "claudeFailed")
        self.assertIn('id="ex-1"', self.local_html("2026-W41"))
        self.assertNotIn("進捗表", self.bodies[0])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#記録しない候補の提案-6
    def test_記録しない候補が3回続けて失敗しても週の結果と自動化案は変わらず候補の欄だけが作れなかったになる(self):
        """否定確認: 候補が作れなかったときに空の一覧を渡すと「候補はありません」が出て落ちる"""
        self.write_enough_week("2026-W41")
        proposal = {"title": "進捗表への転記", "candidateIds": ["c1"], "memoIds": [], "effect": "大", "seen": "毎朝",
                    "idea": "JQLで取る", "reuse": ["jira-progress"]}
        summary = {"id": "w1", "summary": "進捗表を更新していた。", "estimated": False, "examples": []}
        self.headless = FakeHeadless(proposals=[{"proposals": [proposal]}], summaries=[{"items": [summary]}],
                                     exclusions=["x", "y", "z"])
        self.run_report()
        self.assertEqual(self.results()["2026-W41"], "generated")
        html_text = self.local_html("2026-W41")
        self.assertIn("記録しない候補を作れませんでした", html_text)
        self.assertNotIn("今週は記録しない候補はありません", html_text)
        self.assertIn("自動化案: 1件", self.bodies[0])


class LoggingTests(unittest.TestCase):
    """ログは1行1件で、日本時間の日時・レベル(INFO / WARN / ERROR)・英語の短い文"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知
    def test_ログの行は日本時間の日時とWARNの表記で書かれる(self):
        """否定確認: レベルの名前をそのまま出すと WARNING になって落ちる。実行環境の時刻帯で日時を書くと +00:00 になって落ちる"""
        saved = os.environ.get("TZ")
        os.environ["TZ"] = "UTC"
        time.tzset()
        stream = io.StringIO()
        logger = logging.getLogger("routine_work_finder.report")
        handler = run_report.configure_logging(stream)
        try:
            logger.warning("source=%s failed reason=%s", "confluence", "auth")
            logger.info("done seconds=%d", 3)
        finally:
            logger.removeHandler(handler)
            if saved is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = saved
            time.tzset()
        lines = stream.getvalue().splitlines()
        self.assertRegex(lines[0], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00 WARN source=confluence failed reason=auth$")
        self.assertRegex(lines[1], r"^\S+\+09:00 INFO done seconds=3$")


class EntryTests(unittest.TestCase):
    """launchd からの起動"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-3
    def test_起動時に同期フォルダの実体化を許可してから組み上げた手順を動かす(self):
        """否定確認: 実体化の許可を呼ばないと落ちる"""
        order = []
        with mock.patch.object(run_report.onedrive_write, "allow_dataless_materialization",
                               side_effect=lambda: order.append("allow")), \
                mock.patch.object(run_report, "run", side_effect=lambda deps: order.append("run") or 0), \
                mock.patch.object(run_report.paths, "data_paths", return_value=paths.DataPaths("/nonexistent")), \
                mock.patch.object(run_report, "configure_logging", return_value=logging.NullHandler()):
            self.assertEqual(run_report.main(), 0)
        self.assertEqual(order, ["allow", "run"])


if __name__ == "__main__":
    unittest.main()
