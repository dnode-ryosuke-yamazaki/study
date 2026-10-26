"""週次レポートの時間の集計。

1週間分の操作の記録を、作業・会議・離席・記録しなかった時間の4つに分けて数え、
作業をアプリと題名の組にまとめて上位10件・主な時間帯・自動化案の候補・取れなかった時間を出す。
時間の使い方と自動化案のもとになるため、離席の判定と繰り返しの数え方をここで確かめる。
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from routine_work_finder import paths
from routine_work_finder.report import aggregate


def jst(text):
    return datetime.fromisoformat(text + "+09:00")


def sample(text, **fields):
    """記録の共通の処理が読んだ形の通常の行(入力の直後・ロックなし・マイクなし・スリープの抑止なし)"""
    line = {"t": text + "+09:00", "kind": "sample", "app": "Code", "bundleId": "com.microsoft.VSCode", "monitor": 1,
            "idleSec": 0.5, "locked": False, "mic": False, "displaySleepPrevented": False, "title": "main.swift"}
    line.update(fields)
    line["time"] = jst(text)
    return line


def kind(text, name, **extra):
    return {"t": text + "+09:00", "kind": name, **extra, "time": jst(text)}


def run(start, count, **fields):
    """start から5秒ごとに count 行の通常の行"""
    first = jst(start)
    return [sample((first + timedelta(seconds=5 * index)).strftime("%Y-%m-%dT%H:%M:%S"), **fields) for index in range(count)]


def categories(lines):
    return [category for _, category in aggregate.classify(lines)]


class FourCategoryTests(unittest.TestCase):
    """記録の行を作業・会議・離席・記録しなかった時間の4つに分けて数える"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-1
    def test_4つの区分ごとに1行5秒で合計し開始と停止の行は数えない(self):
        """否定確認: 開始・停止の行も5秒として数えると落ちる"""
        lines = [
            kind("2026-10-06T09:00:00", "start"),
            sample("2026-10-06T09:00:00"),
            sample("2026-10-06T09:00:05"),
            kind("2026-10-06T09:00:10", "excluded"),
            sample("2026-10-06T09:00:15", mic=True),
            sample("2026-10-06T09:00:20", locked=True, idleSec=1.0),
            kind("2026-10-06T09:00:25", "stop", reason="stopRequested"),
        ]
        self.assertEqual(aggregate.category_totals(aggregate.classify(lines)),
                         {aggregate.WORK: 10, aggregate.MEETING: 5, aggregate.AWAY: 5, aggregate.EXCLUDED: 5})

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-1
    def test_除外中の行は記録しなかった時間になる(self):
        """否定確認: 除外中の行を作業に数えると落ちる"""
        self.assertEqual(categories([kind("2026-10-06T09:00:00", "excluded")]), [aggregate.EXCLUDED])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-1、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#離席の判定-2
    def test_画面ロック中はマイクが使用中でも離席になる(self):
        """否定確認: マイクの判定をロックより先にすると落ちる"""
        self.assertEqual(categories([sample("2026-10-06T09:00:00", locked=True, mic=True)]), [aggregate.AWAY])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-1、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-3
    def test_マイクが使用中なら入力が10分無くても会議になる(self):
        """否定確認: 入力からの時間の判定をマイクより先にすると落ちる"""
        self.assertEqual(categories([sample("2026-10-06T09:10:00", mic=True, idleSec=600.0)]), [aggregate.MEETING])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-3
    def test_マイクが使用中なら入力があっても会議になる(self):
        """否定確認: マイクの判定を消すと落ちる"""
        self.assertEqual(categories([sample("2026-10-06T09:00:00", mic=True, idleSec=0.2)]), [aggregate.MEETING])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-1、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#離席の判定-3
    def test_入力が5分以上無くても画面のスリープを止めているアプリがあれば作業になる(self):
        """否定確認: スリープの抑止を見ずに入力からの時間だけで離席にすると落ちる"""
        self.assertEqual(categories([sample("2026-10-06T09:10:00", idleSec=400.0, displaySleepPrevented=True)]),
                         [aggregate.WORK])


class UnavailableSurroundingsTests(unittest.TestCase):
    """周りの状態の項目が取れなかった(null の)行の区分。1つ取れなかっただけで作業の時間を消さない"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-1
    def test_ロック中かが取れない行はロックしていないとして次の判定へ進む(self):
        """否定確認: ロック中かが取れない行を離席にすると落ちる"""
        self.assertEqual(categories([sample("2026-10-06T09:00:00", locked=None),
                                     sample("2026-10-06T09:00:05", locked=None, mic=True)]),
                         [aggregate.WORK, aggregate.MEETING])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-1
    def test_マイクの状態が取れない行はマイクを使っていないとして次の判定へ進む(self):
        """否定確認: マイクの状態が取れない行を会議にすると落ちる"""
        self.assertEqual(categories([sample("2026-10-06T09:00:00", mic=None),
                                     sample("2026-10-06T09:10:00", mic=None, idleSec=400.0)]),
                         [aggregate.WORK, aggregate.AWAY])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-1
    def test_スリープの抑止が取れない行は抑止していないとして入力からの時間で離席を判定する(self):
        """否定確認: スリープの抑止が取れない行を抑止中として扱うと落ちる"""
        self.assertEqual(categories([sample("2026-10-06T09:10:00", displaySleepPrevented=None, idleSec=400.0)]),
                         [aggregate.AWAY])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-1
    def test_入力からの時間が取れない行は入力からの時間で離席にせず作業になる(self):
        """否定確認: 入力からの時間が取れない行を離席にすると落ちる"""
        self.assertEqual(categories([sample("2026-10-06T09:00:00", idleSec=None)]), [aggregate.WORK])


class TotalsPropertyTests(unittest.TestCase):
    """4つの区分の合計の和が、開始・停止を除いた行数×5秒と必ず等しい(数え漏れ・二重の数えが無い)"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-1
    def test_境界の値を組み合わせたどの記録でも合計の和が行数かける5秒になる(self):
        """否定確認: 遡りで離席に直した行を作業からも引かずに数えると落ちる"""
        variants = [
            {"locked": locked, "mic": mic, "displaySleepPrevented": prevented, "idleSec": idle}
            for locked in (True, False, None)
            for mic in (True, False, None)
            for prevented in (True, False, None)
            for idle in (None, 0.0, 299.0, 300.0, 301.0, 3600.0)
        ]
        start = jst("2026-10-06T09:00:00")
        lines = [kind("2026-10-06T09:00:00", "start")]
        for index, variant in enumerate(variants):
            time = start + timedelta(seconds=5 * index)
            lines.append(sample(time.strftime("%Y-%m-%dT%H:%M:%S"), **variant))
            if index % 7 == 0:
                lines.append(kind(time.strftime("%Y-%m-%dT%H:%M:%S"), "excluded"))
        lines.append(kind("2026-10-06T23:00:00", "stop", reason="stopRequested"))
        counted = [line for line in lines if line["kind"] not in ("start", "stop")]
        totals = aggregate.category_totals(aggregate.classify(lines))
        self.assertEqual(set(totals), {aggregate.WORK, aggregate.MEETING, aggregate.AWAY, aggregate.EXCLUDED})
        self.assertEqual(sum(totals.values()), len(counted) * 5)


class AwayTests(unittest.TestCase):
    """離席の判定。最後の入力から5分以上たったら離席とし、最後に入力した時点まで遡る"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-2、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#離席の判定-1
    def test_入力から299秒は作業で300秒と301秒は離席になる(self):
        """否定確認: 300秒との比較を > にすると落ちる"""
        self.assertEqual(categories([sample("2026-10-06T09:00:00", idleSec=299.0),
                                     sample("2026-10-06T10:00:00", idleSec=300.0),
                                     sample("2026-10-06T11:00:00", idleSec=301.0)]),
                         [aggregate.WORK, aggregate.AWAY, aggregate.AWAY])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-2、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#離席の判定-1
    def test_離席になった行から最後に入力した時刻まで作業の行を離席に直す(self):
        """否定確認: 遡りをしないと落ちる。最後に入力した時刻ちょうどの行を含めないと落ちる"""
        lines = [
            sample("2026-10-06T09:59:55", idleSec=0.0),
            sample("2026-10-06T10:00:00", idleSec=0.0),
            sample("2026-10-06T10:02:00", idleSec=120.0),
            kind("2026-10-06T10:03:00", "excluded"),
            sample("2026-10-06T10:05:00", idleSec=300.0),
            sample("2026-10-06T10:05:05", idleSec=0.1),
        ]
        self.assertEqual(categories(lines), [aggregate.WORK, aggregate.AWAY, aggregate.AWAY, aggregate.EXCLUDED,
                                             aggregate.AWAY, aggregate.WORK])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#離席の判定-1、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#離席の判定-2
    def test_入力からの時間が取れない画面ロック中の行は遡らずその行だけを離席にする(self):
        """否定確認: 入力からの時間が取れない離席の行から5分遡ると落ちる"""
        lines = [
            sample("2026-10-06T10:00:00", idleSec=0.0),
            sample("2026-10-06T10:01:00", idleSec=60.0),
            sample("2026-10-06T10:02:00", idleSec=None, locked=True),
        ]
        self.assertEqual(categories(lines), [aggregate.WORK, aggregate.WORK, aggregate.AWAY])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#離席の判定-2
    def test_記録が取れなかった空きは4つの区分のどれにも入らない(self):
        """否定確認: 1行5秒でなく次の行までの時間を数えると落ちる"""
        lines = [sample("2026-10-06T09:00:00"), sample("2026-10-06T13:00:00")]
        self.assertEqual(sum(aggregate.category_totals(aggregate.classify(lines)).values()), 10)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#離席の判定-3
    def test_マイクが使用中の行と画面のスリープを止めていた行は遡りでも離席に直さない(self):
        """否定確認: 遡りでスリープの抑止中の作業の行も離席に直すと落ちる"""
        lines = [
            sample("2026-10-06T10:00:00", idleSec=0.0, mic=True),
            sample("2026-10-06T10:01:00", idleSec=60.0, displaySleepPrevented=True),
            sample("2026-10-06T10:02:00", idleSec=120.0),
            sample("2026-10-06T10:05:00", idleSec=300.0),
        ]
        self.assertEqual(categories(lines), [aggregate.MEETING, aggregate.WORK, aggregate.AWAY, aggregate.AWAY])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#離席の判定-3
    def test_マイクが使用中なら入力が5分以上無くても離席にしない(self):
        """否定確認: マイクより先に入力からの時間で離席にすると落ちる"""
        self.assertEqual(categories([sample("2026-10-06T10:00:00", idleSec=900.0, mic=True)]), [aggregate.MEETING])



def group_keys(groups):
    return [(group.app, group.title, group.sheet, group.seconds) for group in groups]


class WorkGroupTests(unittest.TestCase):
    """作業の時間をアプリ名とウィンドウの題名の組にまとめ、長い順に上位10件を出す"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-4
    def test_作業の行だけをアプリと題名とExcelのシート名の組にまとめて長い順に並べる(self):
        """否定確認: シート名を組に入れないと落ちる。作業以外の行も組に数えると落ちる"""
        lines = (run("2026-10-06T09:00:00", 2, app="Microsoft Excel", title="見積.xlsx", sheet="明細")
                 + run("2026-10-06T09:01:00", 3, app="Microsoft Excel", title="見積.xlsx", sheet="集計")
                 + run("2026-10-06T09:02:00", 1)
                 + run("2026-10-06T09:03:00", 4, app="Microsoft Excel", title="見積.xlsx", sheet="集計", mic=True))
        groups = aggregate.group_work(aggregate.classify(lines))
        self.assertEqual(group_keys(groups), [("Microsoft Excel", "見積.xlsx", "集計", 15),
                                              ("Microsoft Excel", "見積.xlsx", "明細", 10),
                                              ("Code", "main.swift", None, 5)])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-4
    def test_題名が1文字違えば別の組にする(self):
        """否定確認: 題名の数字を除いてまとめると落ちる"""
        lines = run("2026-10-06T09:00:00", 2, title="週報_1.docx") + run("2026-10-06T09:01:00", 1, title="週報_2.docx")
        groups = aggregate.group_work(aggregate.classify(lines))
        self.assertEqual([group.title for group in groups], ["週報_1.docx", "週報_2.docx"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-4
    def test_組がちょうど10件なら上位10件にすべて出る(self):
        """否定確認: 上位を9件で切ると落ちる"""
        lines = []
        for index in range(10):
            lines += run(f"2026-10-06T{9 + index:02d}:00:00", index + 1, title=f"資料{index}")
        top = aggregate.top_groups(aggregate.group_work(aggregate.classify(lines)))
        self.assertEqual(len(top), 10)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-4
    def test_組が11件あれば最も短い11件目を落とす(self):
        """否定確認: 上位を11件で切ると落ちる"""
        lines = []
        for index in range(11):
            lines += run(f"2026-10-06T{9 + index:02d}:00:00", index + 1, title=f"資料{index}")
        top = aggregate.top_groups(aggregate.group_work(aggregate.classify(lines)))
        self.assertEqual([group.title for group in top], [f"資料{index}" for index in range(10, 0, -1)])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-5
    def test_題名が取れなかった行は理由にかかわらずアプリ名だけの組にする(self):
        """否定確認: 題名が取れなかった行を理由ごとに別の組にすると落ちる"""
        lines = (run("2026-10-06T09:00:00", 2, app="Microsoft Teams", title=None, titleUnavailable=True, titleReason="timeout")
                 + run("2026-10-06T09:01:00", 1, app="Microsoft Teams", title=None, titleUnavailable=True, titleReason="denied")
                 + run("2026-10-06T09:02:00", 1, app="Microsoft Teams", title="チャット"))
        for line in lines[:3]:
            del line["title"]
        groups = aggregate.group_work(aggregate.classify(lines))
        self.assertEqual([(group.app, group.title, group.title_known, group.seconds) for group in groups],
                         [("Microsoft Teams", None, False, 15), ("Microsoft Teams", "チャット", True, 5)])


class MainTimesTests(unittest.TestCase):
    """時間の使い方の各項目の主な時間帯。その組の作業のまとまりのうち長い2つを「曜日 開始-終了」で出す"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#作業の要約-2
    def test_まとまりが3つある組は長い2つを長い順に出す(self):
        """否定確認: 長さでなく時刻の早い順に2つ選ぶと落ちる"""
        lines = (run("2026-10-05T09:00:00", 12) + run("2026-10-06T10:00:00", 36) + run("2026-10-07T11:00:00", 24))
        group, = aggregate.group_work(aggregate.classify(lines))
        self.assertEqual(group.main_times, ["火 10:00-10:03", "水 11:00-11:02"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#作業の要約-2
    def test_まとまりが1つの組はその1つだけを出す(self):
        """否定確認: 主な時間帯を必ず2つ出そうとして空の時間帯を足すと落ちる"""
        group, = aggregate.group_work(aggregate.classify(run("2026-10-09T16:59:00", 12)))
        self.assertEqual(group.main_times, ["金 16:59-17:00"])


class WeekAggregateTestCase(unittest.TestCase):
    """記録のファイルから1週間分を集計するテストの土台"""

    def setUp(self):
        base = os.environ.get("TMPDIR") or tempfile.gettempdir()
        self.temporary = tempfile.TemporaryDirectory(dir=base)
        self.paths = paths.DataPaths(Path(self.temporary.name) / "routine-work-finder")
        self.paths.records.mkdir(parents=True)

    def tearDown(self):
        self.temporary.cleanup()

    def write_lines(self, *lines):
        for line in lines:
            raw = {key: value for key, value in line.items() if key != "time"}
            with (self.paths.records / f"{raw['t'][:10]}.jsonl").open("a", encoding="utf-8") as file:
                file.write(json.dumps(raw, ensure_ascii=False) + "\n")

    def aggregate_week(self):
        return aggregate.aggregate_week(self.paths, jst("2026-10-05T00:00:00"), jst("2026-10-09T17:00:00"))


class MicNotMeetingTests(WeekAggregateTestCase):
    """マイクを会議とみなさない設定。ミュートのまま開いた会議の画面などでマイクが使われたままでも、会議を0にして作業と離席だけで数える"""

    def classified(self, lines):
        return [category for _, category in aggregate.classify(lines, mic_as_meeting=False)]

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-3
    def test_マイクが使用中でも入力があれば作業になり会議の合計は0になる(self):
        """否定確認: みなさない設定でもマイクの判定を飛ばさないと落ちる"""
        lines = run("2026-10-06T09:00:00", 6, mic=True, idleSec=0.2)
        self.assertEqual(self.classified(lines), [aggregate.WORK] * 6)
        totals = aggregate.category_totals(aggregate.classify(lines, mic_as_meeting=False))
        self.assertEqual(totals[aggregate.MEETING], 0)
        self.assertEqual(totals[aggregate.WORK], 30)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#離席の判定-3
    def test_マイクが使用中でも入力が5分以上無く画面のスリープを止めるアプリが無ければ離席になる(self):
        """否定確認: マイクを飛ばす判定の位置を離席の判定より後ろにすると落ちる"""
        self.assertEqual(self.classified([sample("2026-10-06T10:00:00", idleSec=900.0, mic=True)]), [aggregate.AWAY])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#離席の判定-3
    def test_マイクが使用中でも画面のスリープを止めていれば離席にならない(self):
        """否定確認: 離席の判定のスリープの抑止の条件を外すと落ちる"""
        self.assertEqual(self.classified([sample("2026-10-06T10:00:00", idleSec=900.0, mic=True,
                                                 displaySleepPrevented=True)]), [aggregate.WORK])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-1
    def test_画面ロック中と除外中は設定にかかわらずマイクより先に決まる(self):
        """否定確認: マイクを会議とみなさない設定でロックの判定が飛ぶと落ちる"""
        lines = [sample("2026-10-06T09:00:00", locked=True, mic=True, idleSec=1.0), kind("2026-10-06T09:00:05", "excluded")]
        self.assertEqual(self.classified(lines), [aggregate.AWAY, aggregate.EXCLUDED])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#離席の判定-3
    def test_離席のあと最後に入力した時刻まで遡るとき_マイクが使用中だった作業の行も離席に直す(self):
        """否定確認: みなさない設定でも遡りでマイクの行を直さないと落ちる"""
        lines = [
            sample("2026-10-06T10:00:00", idleSec=0.0, mic=True),
            sample("2026-10-06T10:01:00", idleSec=60.0, mic=True),
            sample("2026-10-06T10:02:00", idleSec=120.0, mic=True, displaySleepPrevented=True),
            sample("2026-10-06T10:05:00", idleSec=300.0, mic=True),
        ]
        self.assertEqual(self.classified(lines), [aggregate.AWAY, aggregate.AWAY, aggregate.WORK, aggregate.AWAY])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-3
    def test_既定はマイクを会議とみなす(self):
        """否定確認: 既定の引数を false にすると落ちる"""
        self.assertEqual(categories([sample("2026-10-06T09:00:00", mic=True)]), [aggregate.MEETING])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-4
    def test_同じ週を設定を変えて数えると会議と作業の合計がそれぞれの設定どおりに変わる(self):
        """否定確認: 設定を記録のファイルや前の集計に残して引き継ぐと落ちる"""
        self.write_lines(*run("2026-10-06T09:00:00", 12, mic=True, idleSec=0.2))
        start, end = jst("2026-10-05T00:00:00"), jst("2026-10-09T17:00:00")
        counted = aggregate.aggregate_week(self.paths, start, end, mic_as_meeting=True)
        not_counted = aggregate.aggregate_week(self.paths, start, end, mic_as_meeting=False)
        self.assertEqual((counted.totals[aggregate.MEETING], counted.totals[aggregate.WORK]), (60, 0))
        self.assertEqual((not_counted.totals[aggregate.MEETING], not_counted.totals[aggregate.WORK]), (0, 60))
        self.assertEqual(aggregate.aggregate_week(self.paths, start, end).totals, counted.totals)
        self.assertEqual([group.seconds for group in not_counted.groups], [60])


class UnavailableTimeTests(WeekAggregateTestCase):
    """記録が取れなかった時間帯と題名が取れなかった時間の一覧。4つの区分には数えず別に合計を出す"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-6
    def test_空きが29秒なら一覧に出さず30秒なら一覧と合計に出す(self):
        """否定確認: 記録の共通の処理を通さず5秒を超える空きをすべて数えると落ちる"""
        self.write_lines(kind("2026-10-06T09:00:00", "start"), sample("2026-10-06T09:00:00"), sample("2026-10-06T09:00:29"),
                         sample("2026-10-06T09:00:59"), kind("2026-10-06T09:01:00", "stop", reason="stopRequested"))
        result = self.aggregate_week()
        self.assertEqual(result.gaps, [(jst("2026-10-06T09:00:29"), jst("2026-10-06T09:00:59"))])
        self.assertEqual(result.gap_seconds, 30)
        self.assertEqual(sum(result.totals.values()), 15)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-6
    def test_止めていた期間は記録が取れなかった時間に数えない(self):
        """否定確認: 停止の行のあとの空きも数えると落ちる"""
        self.write_lines(kind("2026-10-06T09:00:00", "start"), sample("2026-10-06T09:00:00"),
                         kind("2026-10-06T09:00:05", "stop", reason="stopRequested"),
                         kind("2026-10-06T13:00:00", "start"), sample("2026-10-06T13:00:00"),
                         kind("2026-10-06T13:00:05", "stop", reason="stopRequested"))
        result = self.aggregate_week()
        self.assertEqual((result.gaps, result.gap_seconds), ([], 0))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-6
    def test_記録係が起動し直したときの開始の行の前の空きは数える(self):
        """否定確認: 開始の行の前の空きを数えないと落ちる"""
        self.write_lines(kind("2026-10-06T09:00:00", "start"), sample("2026-10-06T09:00:00"),
                         kind("2026-10-06T09:10:00", "start"), sample("2026-10-06T09:10:00"),
                         kind("2026-10-06T09:10:05", "stop", reason="stopRequested"))
        result = self.aggregate_week()
        self.assertEqual(result.gaps, [(jst("2026-10-06T09:00:00"), jst("2026-10-06T09:10:00"))])
        self.assertEqual(result.gap_seconds, 600)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-6
    def test_題名が取れなかった時間をアプリと理由ごとにまとめて長い順に出す(self):
        """否定確認: 理由を見ずにアプリだけでまとめると落ちる"""
        unavailable = {"title": None, "titleUnavailable": True}
        lines = (run("2026-10-06T09:00:00", 1, app="Finder", titleReason="noWindow", **unavailable)
                 + run("2026-10-06T09:00:05", 2, app="Microsoft Teams", titleReason="timeout", **unavailable)
                 + run("2026-10-06T09:00:15", 1, app="Microsoft Teams", titleReason="denied", **unavailable)
                 + run("2026-10-06T09:00:20", 1))
        for line in lines[:4]:
            del line["title"]
        self.write_lines(kind("2026-10-06T09:00:00", "start"), *lines,
                         kind("2026-10-06T09:00:25", "stop", reason="stopRequested"))
        result = self.aggregate_week()
        self.assertEqual(result.title_unavailable, [{"app": "Microsoft Teams", "reason": "timeout", "seconds": 10},
                                                    {"app": "Finder", "reason": "noWindow", "seconds": 5},
                                                    {"app": "Microsoft Teams", "reason": "denied", "seconds": 5}])
        self.assertEqual([(group.app, group.seconds) for group in result.top],
                         [("Microsoft Teams", 15), ("Finder", 5), ("Code", 5)])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-6
    def test_題名が取れなかった時間の一覧は会議と離席の行も含めアプリ名だけの組は作業の行だけにする(self):
        """否定確認: 一覧を作業の行に絞ると会議と離席の分が消えて落ちる"""
        unavailable = {"title": None, "titleUnavailable": True, "titleReason": "timeout"}
        lines = (run("2026-10-06T09:00:00", 1, app="Microsoft Teams", **unavailable)
                 + run("2026-10-06T09:00:05", 2, app="Microsoft Teams", mic=True, **unavailable)
                 + run("2026-10-06T09:00:15", 1, app="Microsoft Teams", locked=True, **unavailable))
        for line in lines:
            del line["title"]
        self.write_lines(kind("2026-10-06T09:00:00", "start"), *lines,
                         kind("2026-10-06T09:00:20", "stop", reason="stopRequested"))
        result = self.aggregate_week()
        self.assertEqual(result.title_unavailable, [{"app": "Microsoft Teams", "reason": "timeout", "seconds": 20}])
        self.assertEqual([(group.app, group.seconds) for group in result.top], [("Microsoft Teams", 5)])


class AutomationCandidateTests(unittest.TestCase):
    """同じアプリと題名の組の作業が30分以上あけて週2回以上現れたものを自動化案の候補にする(キー操作の中身は見ない)"""

    def candidates(self, lines):
        return aggregate.automation_candidates(aggregate.group_work(aggregate.classify(lines)))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-1、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案を作る条件-2
    def test_まとまりが1つだけの組は候補にしない(self):
        """否定確認: まとまりが1つ以上の組を候補にすると落ちる"""
        self.assertEqual(self.candidates(run("2026-10-05T09:00:00", 120)), [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-1、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案を作る条件-2
    def test_まとまりが2つある組を候補にしまとまりの数と合計の時間と曜日と時刻を付ける(self):
        """否定確認: まとまりが3つ以上の組だけを候補にすると落ちる"""
        lines = (run("2026-10-05T09:00:00", 12, app="Microsoft Excel", title="進捗表.xlsx", sheet="集計")
                 + run("2026-10-06T09:10:00", 24, app="Microsoft Excel", title="進捗表.xlsx", sheet="集計"))
        candidate, = self.candidates(lines)
        self.assertEqual((candidate.group.app, candidate.group.title, candidate.group.sheet),
                         ("Microsoft Excel", "進捗表.xlsx", "集計"))
        self.assertEqual((candidate.session_count, candidate.seconds), (2, 180))
        self.assertEqual(candidate.when, ["月 09:00-09:01", "火 09:10-09:12"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-1、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案を作る条件-2
    def test_29分あけて現れた2回は1つのまとまりとして候補にしない(self):
        """否定確認: 30分との比較を29分にすると落ちる"""
        lines = run("2026-10-05T09:00:00", 12) + run("2026-10-05T09:30:00", 12)
        self.assertEqual(self.candidates(lines), [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-1、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案を作る条件-2
    def test_30分あけて現れた2回は2つのまとまりとして候補にする(self):
        """否定確認: 30分との比較を <= にすると落ちる"""
        lines = run("2026-10-05T09:00:00", 12) + run("2026-10-05T09:31:00", 12)
        candidate, = self.candidates(lines)
        self.assertEqual(candidate.when, ["月 09:00-09:01", "月 09:31-09:32"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-1
    def test_候補は合計の時間の長い順に並べる(self):
        """否定確認: 先に現れた順に並べると落ちる"""
        lines = (run("2026-10-05T09:00:00", 2, title="短い.txt") + run("2026-10-05T09:01:00", 3, title="長い.txt")
                 + run("2026-10-06T09:00:00", 2, title="短い.txt") + run("2026-10-06T09:01:00", 3, title="長い.txt"))
        self.assertEqual([candidate.group.title for candidate in self.candidates(lines)], ["長い.txt", "短い.txt"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-1
    def test_1週間分の集計の結果に自動化案の候補が入る(self):
        """否定確認: 集計の結果に候補を渡さないと落ちる"""
        result = aggregate.WeekAggregate(totals={}, groups=aggregate.group_work(aggregate.classify(
            run("2026-10-05T09:00:00", 1) + run("2026-10-06T09:00:00", 1))), gaps=[], title_unavailable=[], skipped=0)
        self.assertEqual([candidate.session_count for candidate in result.candidates], [2])

if __name__ == "__main__":
    unittest.main()
