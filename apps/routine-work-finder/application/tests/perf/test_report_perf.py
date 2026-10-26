"""週次レポート係の性能テスト。1週間分の最大の規模(記録6万行)で、作成の所要時間と Claude の呼び出し回数を確かめる。

毎回の TDD サイクルでは回さない(tests/perf/ に __init__.py を置かず、`discover -s tests` の対象から外す)。
実行: cd apps/routine-work-finder/application && python3 -m unittest discover -s tests/perf

Claude(claude -p)・Teams・OneDrive・既存の作業の記録(JIRA・Confluence・会話の記録・議事録)は偽物か一時フォルダに差し替え、
記録の行はテストの中で決まった乱数の種から作る(実データには触れない)。Claude の待ち時間は含まないため、
Claude を含む全体の時間は出荷後にログの全体の所要秒数(done seconds=)で見る。
"""

import json
import logging
import os
import random
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from routine_work_finder import paths, weeks
from routine_work_finder.report import run_report

LINES_PER_WEEK = 60_000
LINES_PER_DAY = LINES_PER_WEEK // 5
SECONDS_PER_LINE = 5
BLOCK_LINES = 120                     # 10分ごとに使うアプリと題名を選び直す
LIMIT_SECONDS = 15 * 60               # 要件(30分)の1/2
CALLS_PER_WEEK = ("proposals", "summaries", "exclusions")
SEED = 20261009

APPS = (
    ("Code", "com.microsoft.VSCode", "AXTextArea", None),
    ("Microsoft Excel", "com.microsoft.Excel", "AXTable", ("集計", "明細", "グラフ", "入力")),
    ("Google Chrome", "com.google.Chrome", "AXWebArea", None),
    ("Microsoft Teams", "com.microsoft.teams2", "AXTextArea", None),
    ("Microsoft Outlook", "com.microsoft.Outlook", "AXTextArea", None),
    ("Microsoft Word", "com.microsoft.Word", "AXTextArea", None),
    ("Microsoft PowerPoint", "com.microsoft.Powerpoint", "AXGroup", None),
    ("Terminal", "com.apple.Terminal", "AXTextArea", None),
    ("Finder", "com.apple.finder", "AXOutline", None),
    ("Slack", "com.tinyspeck.slackmacgap", "AXTextArea", None),
    ("Notion", "notion.id", "AXWebArea", None),
    ("プレビュー", "com.apple.Preview", "AXGroup", None),
)
TITLES_PER_APP = 25


def jst(text):
    return datetime.fromisoformat(text + "+09:00")


class FakeHeadless:
    """材料の形で呼び出しの種類を見分け、検査を通る応答を材料から作って返す。呼び出しを週ごとに数える"""

    def __init__(self):
        self.calls = []

    def __call__(self, prompt, stdin_text, timeout_seconds):
        payload = json.loads(stdin_text)
        if "candidates" in payload:
            name = "proposals"
            ids = [entry["id"] for entry in payload["candidates"][:2]]
            value = {"proposals": [{"title": "定型の転記", "candidateIds": ids, "memoIds": [], "effect": "大", "importance": "大",
                                    "importanceReason": "毎朝続く", "seen": "毎朝同じ表を更新している",
                                    "idea": "表の更新を自動で行う", "reuse": ["jira-progress"]}]}
        elif "items" in payload:
            name = "summaries"
            value = {"items": [{"id": entry["id"], "summary": "表を更新していた。", "estimated": False, "examples": []}
                               for entry in payload["items"]]}
        else:
            name = "exclusions"
            value = {"exclusions": []}
        self.calls.append((name, payload["week"]))
        return SimpleNamespace(success=True, output=json.dumps(value, ensure_ascii=False), failure_category="")

    def names_by_week(self):
        found = {}
        for name, week in self.calls:
            found.setdefault(week, []).append(name)
        return found


def _titles():
    """アプリごとの題名。よく使う題名ほど選ばれやすい(上位の組に時間が偏る実データに合わせる)"""
    choices, weights = [], []
    for app, bundle, role, sheets in APPS:
        for number in range(TITLES_PER_APP):
            title = f"{app} の資料 {number:02d} - 案件{number % 7}"
            sheet = sheets[number % len(sheets)] if sheets else None
            choices.append((app, bundle, role, title, sheet))
            weights.append(1 / (number + 1))
    return choices, weights


def write_week(data_paths, name, rng):
    """その週の月曜〜金曜に1日12,000行(5秒ごと)、合計6万行の記録を書く。
    作業(題名あり・題名なし)・会議(マイク使用中)・離席・画面ロック・除外中の行を混ぜる"""
    data_paths.records.mkdir(mode=0o700, exist_ok=True)
    titles, weights = _titles()
    monday = weeks.parse_week_name(name).monday
    written = 0
    for day in range(5):
        first = monday + timedelta(days=day)
        lines = [json.dumps({"t": first.isoformat(), "kind": "start", "reason": "login"})]
        for block in range(LINES_PER_DAY // BLOCK_LINES):
            kind = rng.choices(("work", "untitled", "meeting", "away", "locked", "excluded"),
                               weights=(70, 5, 10, 8, 4, 3))[0]
            app, bundle, role, title, sheet = rng.choices(titles, weights=weights)[0]
            for step in range(BLOCK_LINES):
                moment = first + timedelta(seconds=SECONDS_PER_LINE * (block * BLOCK_LINES + step))
                lines.append(json.dumps(_line(kind, moment, step, app, bundle, role, title, sheet), ensure_ascii=False))
                written += 1
        (data_paths.records / f"{first:%Y-%m-%d}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return written


def _line(kind, moment, step, app, bundle, role, title, sheet):
    if kind == "excluded":
        return {"t": moment.isoformat(), "kind": "excluded"}
    line = {"t": moment.isoformat(), "kind": "sample", "app": app, "bundleId": bundle, "monitor": 1,
            "idleSec": 0.5, "locked": False, "mic": False, "displaySleepPrevented": False, "focusRole": role}
    if kind == "untitled":
        line.update(titleUnavailable=True, titleReason="timeout")
    else:
        line["title"] = title
        if sheet is not None:
            line["sheet"] = sheet
    if kind == "meeting":
        line.update(app="Microsoft Teams", bundleId="com.microsoft.teams2", mic=True, idleSec=float(step * 5))
    elif kind == "away":
        line["idleSec"] = float(step * 5)
    elif kind == "locked":
        line.update(locked=True, idleSec=None)
    return line


def source_records(start, rng):
    """既存の作業の記録(JIRA 40件・Confluence 20件・会話の記録の依頼文 60件・議事録 10件)を週の中に散らす"""
    def when():
        return start + timedelta(days=rng.randrange(5), seconds=rng.randrange(16 * 3600))
    jira = [{"source": "jira", "site": "example.atlassian.net", "key": f"SAG-{number}", "summary": f"チケット {number}",
             "field": "status", "from": "進行中", "to": "完了", "time": when()} for number in range(40)]
    confluence = [{"source": "confluence", "site": "example.atlassian.net", "title": f"作業ページ {number}", "time": when()}
                  for number in range(20)]
    claude_code = [{"source": "claudeCode", "repo": "study", "text": f"依頼文 {number}", "time": when()} for number in range(60)]
    minutes = [{"source": "minutes", "title": f"定例 {number}", "summary": "進捗を確認した。", "time": when()}
               for number in range(10)]
    return jira, confluence, claude_code, minutes


class ReportPerfTestCase(unittest.TestCase):
    """一時フォルダのデータフォルダと偽物の外部で週次レポート係を1回起動する"""

    def setUp(self):
        base = os.environ.get("TMPDIR") or tempfile.gettempdir()
        self.temporary = tempfile.TemporaryDirectory(dir=base)
        folder = Path(self.temporary.name)
        self.paths = paths.DataPaths(folder / "routine-work-finder")
        self.paths.root.mkdir(mode=0o700)
        self.onedrive = folder / "onedrive"
        self.onedrive.mkdir()
        self.headless = FakeHeadless()
        self.bodies = []
        self.rng = random.Random(SEED)

    def tearDown(self):
        self.temporary.cleanup()

    def write_state(self, done_week):
        self.paths.report_state.write_text(json.dumps({"version": 1, "weeks": {
            done_week: {"result": "generated", "at": "2026-09-01T17:00:00+09:00", "notified": True}}}), encoding="utf-8")

    def run_report(self, now):
        def found(start):
            return source_records(start, random.Random(SEED + start.toordinal()))

        def read_atlassian(start, end):
            jira, confluence, _, _ = found(start)
            return SimpleNamespace(jira=jira, confluence=confluence, failures=[])

        deps = run_report.Deps(
            data_paths=self.paths,
            now=lambda: now,
            read_atlassian=read_atlassian,
            read_claude_code=lambda start, end: SimpleNamespace(requests=found(start)[2], skipped={}, failures=[]),
            read_minutes=lambda start, end: SimpleNamespace(minutes=found(start)[3], skipped={}, failures=[]),
            collect_reusable=lambda: [{"name": "jira-progress", "kind": "skill", "description": "JIRA の進捗を集める"}],
            run_headless=self.headless,
            notifier=lambda skill, kind, body: self.bodies.append(body) or {"success": True},
            sleep=lambda seconds: None,
            onedrive_dir=self.onedrive,
            pid=4242,
            pid_alive=lambda pid: False,
        )
        logger = logging.getLogger("routine_work_finder.report")
        with self.assertLogs(logger, level="INFO") as captured:
            started = time.perf_counter()
            code = run_report.run(deps)
            elapsed = time.perf_counter() - started
        self.assertEqual(code, 0)
        return elapsed, captured.output

    def results(self):
        state = json.loads(self.paths.report_state.read_text(encoding="utf-8"))["weeks"]
        return {name: entry["result"] for name, entry in state.items()}


class 一週間分の最大の規模でレポートを作るとき(ReportPerfTestCase):
    """記録6万行の週でも、集計・材料の組み立て・HTMLの作成が要件の30分を大きく下回り、Claude の呼び出しが決まった回数に収まる"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#非機能要件-1
    def test_記録6万行の1週分の集計と材料の組み立てとHTMLの作成が15分以内に終わる(self):
        """否定確認: 閾値を0.001秒に下げると落ちる(所要時間を実際に比べている)"""
        self.write_state("2026-W40")
        self.assertEqual(write_week(self.paths, "2026-W41", self.rng), LINES_PER_WEEK)
        elapsed, logs = self.run_report(jst("2026-10-09T17:05:00"))
        print(f"\n  非機能要件-1: 6万行の1週分の作成 {elapsed:.2f}秒(上限 {LIMIT_SECONDS}秒)")
        self.assertEqual(self.results()["2026-W41"], "generated")
        self.assertTrue((self.onedrive / "2026-W41.html").exists())
        self.assertTrue(any(f"rows read={LINES_PER_WEEK} skipped=0 " in line for line in logs), "6万行をすべて集計していない")
        self.assertLessEqual(elapsed, LIMIT_SECONDS)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#非機能要件-2
    def test_成功したときの1週分の作成でClaudeを呼ぶのは自動化案と作業の要約と記録しない候補の3回(self):
        """否定確認: 1週分の作成で Claude の呼び出しをもう1組行うようにすると落ちる"""
        self.write_state("2026-W40")
        write_week(self.paths, "2026-W41", self.rng)
        self.run_report(jst("2026-10-09T17:05:00"))
        print(f"\n  非機能要件-2: 1週分の呼び出し {len(self.headless.calls)}回")
        self.assertEqual(self.results()["2026-W41"], "generated")
        self.assertEqual(self.headless.names_by_week(), {"2026-W41": list(CALLS_PER_WEEK)})
        self.assertLessEqual(len(self.headless.calls), 10)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#非機能要件-2
    def test_2週分を作る起動では1週あたり3回の計6回を呼ぶ(self):
        """否定確認: 定期の作成の対象を直近の週だけにすると3回になって落ちる"""
        self.write_state("2026-W39")
        write_week(self.paths, "2026-W40", self.rng)
        write_week(self.paths, "2026-W41", self.rng)
        elapsed, _ = self.run_report(jst("2026-10-10T09:00:00"))
        print(f"\n  非機能要件-2: 2週分の呼び出し {len(self.headless.calls)}回({elapsed:.2f}秒)")
        self.assertEqual(self.results(), {"2026-W39": "generated", "2026-W40": "generated", "2026-W41": "generated"})
        self.assertEqual(self.headless.names_by_week(),
                         {"2026-W40": list(CALLS_PER_WEEK), "2026-W41": list(CALLS_PER_WEEK)})
        self.assertEqual(len(self.headless.calls), 6)


if __name__ == "__main__":
    unittest.main()
