"""記録・メモのファイルを期間で読む共通の処理。

状態の確認と週次レポートが同じ読み方で記録を扱えるよう、行・メモの読み取りと、
記録している期間の中の30秒以上の空き(スリープ中など記録が取れなかった時間)の求め方をここ1か所に置く。
"""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from routine_work_finder import paths, records

JST = timezone(timedelta(hours=9))
RECORDER_LINES_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "recorder_lines" / "records.jsonl"


def jst(text):
    return datetime.fromisoformat(text + "+09:00")


def sample(text):
    return {"t": text + "+09:00", "kind": "sample", "app": "Code", "bundleId": "com.microsoft.VSCode", "monitor": 1,
            "idleSec": 0.5, "locked": False, "mic": False, "displaySleepPrevented": False, "title": "main.swift"}


def kind(text, name, **extra):
    return {"t": text + "+09:00", "kind": name, **extra}


class RecordsTestCase(unittest.TestCase):
    def setUp(self):
        base = os.environ.get("TMPDIR") or tempfile.gettempdir()
        self.temporary = tempfile.TemporaryDirectory(dir=base)
        self.paths = paths.DataPaths(Path(self.temporary.name) / "routine-work-finder")
        self.paths.records.mkdir(parents=True)
        self.paths.memos.mkdir(parents=True)

    def tearDown(self):
        self.temporary.cleanup()

    def write_lines(self, *lines, raw_tail=""):
        """行を日本時間の日付ごとのファイルに書き足す"""
        for line in lines:
            date = line["t"][:10]
            with (self.paths.records / f"{date}.jsonl").open("a", encoding="utf-8") as file:
                file.write(json.dumps(line, ensure_ascii=False) + "\n")
        if raw_tail:
            date = lines[-1]["t"][:10]
            with (self.paths.records / f"{date}.jsonl").open("a", encoding="utf-8") as file:
                file.write(raw_tail)

    def gaps(self, start, end):
        return records.find_gaps(self.paths, jst(start), jst(end))


class ReadRecordsContractTests(RecordsTestCase):
    """記録係が書いた行を読む(契約)"""

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-1
    def test_記録係が書いた行を時刻順に読む(self):
        shutil.copy(RECORDER_LINES_FIXTURE, self.paths.records / "2026-10-06.jsonl")
        result = records.read_records(self.paths, jst("2026-10-06T00:00:00"), jst("2026-10-07T00:00:00"))
        self.assertEqual([line["kind"] for line in result.lines], ["start", "sample", "sample", "sample", "excluded", "stop"])
        self.assertEqual(result.lines[1]["title"], "見積_2026.xlsx")
        self.assertEqual(result.lines[1]["time"], jst("2026-10-06T09:00:00"))
        self.assertEqual(result.lines[3]["titleReason"], "timeout")
        self.assertEqual(result.skipped, 0)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-1
    def test_書きかけの最終行と知らない種類の行は読み飛ばして数を返す(self):
        """否定確認: 読めない行で止まる(例外を投げる)と落ちる"""
        self.write_lines(sample("2026-10-06T09:00:00"), kind("2026-10-06T09:00:05", "pause"),
                         raw_tail='{"t":"2026-10-06T09:00:10+09:00","ki')
        result = records.read_records(self.paths, jst("2026-10-06T00:00:00"), jst("2026-10-07T00:00:00"))
        self.assertEqual(len(result.lines), 1)
        self.assertEqual(result.skipped, 2)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-1
    def test_日本語の途中で途切れた最終行があっても前の行は読む(self):
        """否定確認: ファイル全体を UTF-8 として読むと、文字に直せない例外で前の行まで読めずに落ちる"""
        self.write_lines(sample("2026-10-06T09:00:00"))
        with (self.paths.records / "2026-10-06.jsonl").open("ab") as file:
            file.write('{"t":"2026-10-06T09:00:05+09:00","kind":"sample","title":"給'.encode("utf-8")[:-1])
        result = records.read_records(self.paths, jst("2026-10-06T00:00:00"), jst("2026-10-07T00:00:00"))
        self.assertEqual(len(result.lines), 1)
        self.assertEqual(result.skipped, 1)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-1
    def test_題名に行区切りの文字U2028があっても1行として読む(self):
        """否定確認: splitlines で行を分けると、U+2028 で行が割れて読み飛ばされ落ちる"""
        line = sample("2026-10-06T09:00:00")
        line["title"] = "見積 2026"
        self.write_lines(line)
        result = records.read_records(self.paths, jst("2026-10-06T00:00:00"), jst("2026-10-07T00:00:00"))
        self.assertEqual([item["title"] for item in result.lines], ["見積 2026"])
        self.assertEqual(result.skipped, 0)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-1
    def test_知らない項目は無視して行を読む(self):
        """否定確認: 知らない項目のある行を読み飛ばすと落ちる"""
        line = sample("2026-10-06T09:00:00")
        line["futureField"] = 1
        self.write_lines(line)
        result = records.read_records(self.paths, jst("2026-10-06T00:00:00"), jst("2026-10-07T00:00:00"))
        self.assertEqual(len(result.lines), 1)
        self.assertNotIn("futureField", result.lines[0])
        self.assertEqual(result.skipped, 0)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#日付と週の基準-1
    def test_範囲の始まりは含み終わりは含まない(self):
        self.write_lines(sample("2026-10-05T23:59:59"), sample("2026-10-06T00:00:00"), sample("2026-10-07T00:00:00"))
        result = records.read_records(self.paths, jst("2026-10-06T00:00:00"), jst("2026-10-07T00:00:00"))
        self.assertEqual([line["time"] for line in result.lines], [jst("2026-10-06T00:00:00")])


class GapTests(RecordsTestCase):
    """記録している期間の中の、記録が取れなかった時間帯"""

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-3
    def test_空きが29秒なら数えず30秒なら数える(self):
        """否定確認: 30秒との比較を `>` にすると落ちる"""
        self.write_lines(kind("2026-10-06T09:00:00", "start"), sample("2026-10-06T09:00:00"), sample("2026-10-06T09:00:29"),
                         sample("2026-10-06T09:00:59"), kind("2026-10-06T09:01:00", "stop", reason="stopRequested"))
        self.assertEqual(self.gaps("2026-10-06T00:00:00", "2026-10-07T00:00:00"),
                         [(jst("2026-10-06T09:00:29"), jst("2026-10-06T09:00:59"))])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-3
    def test_止めていた間の空きは数えない(self):
        """否定確認: 停止の行のあとの空きも数えると落ちる"""
        self.write_lines(kind("2026-10-06T09:00:00", "start"), sample("2026-10-06T09:00:00"),
                         kind("2026-10-06T09:00:05", "stop", reason="stopRequested"),
                         kind("2026-10-06T13:00:00", "start"), sample("2026-10-06T13:00:00"),
                         kind("2026-10-06T13:00:05", "stop", reason="stopRequested"))
        self.assertEqual(self.gaps("2026-10-06T00:00:00", "2026-10-07T00:00:00"), [])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-3
    def test_起動し直したときの開始の行の前の空きは数える(self):
        self.write_lines(kind("2026-10-06T09:00:00", "start"), sample("2026-10-06T09:00:00"),
                         kind("2026-10-06T09:10:00", "start"), sample("2026-10-06T09:10:00"),
                         kind("2026-10-06T09:10:05", "stop", reason="stopRequested"))
        self.assertEqual(self.gaps("2026-10-06T00:00:00", "2026-10-07T00:00:00"),
                         [(jst("2026-10-06T09:00:00"), jst("2026-10-06T09:10:00"))])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-3
    def test_範囲内に開始の行が無い週で直前が通常の行なら月曜0時から最初の行までを数える(self):
        """否定確認: 範囲の直前の行を見ないと落ちる"""
        self.write_lines(sample("2026-10-02T18:00:00"), sample("2026-10-05T09:00:00"),
                         kind("2026-10-05T09:00:05", "stop", reason="endsAtPassed"))
        self.assertEqual(self.gaps("2026-10-05T00:00:00", "2026-10-10T00:00:00"),
                         [(jst("2026-10-05T00:00:00"), jst("2026-10-05T09:00:00"))])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-3
    def test_直前の行が停止の行なら範囲の始まりからは数えない(self):
        self.write_lines(kind("2026-10-02T18:00:00", "stop", reason="endsAtPassed"),
                         kind("2026-10-05T09:00:00", "start"), sample("2026-10-05T09:00:00"),
                         kind("2026-10-05T09:00:05", "stop", reason="endsAtPassed"))
        self.assertEqual(self.gaps("2026-10-05T00:00:00", "2026-10-10T00:00:00"), [])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-3
    def test_直前の行が無い_28日の保持で消えた_なら範囲の始まりからは数えない(self):
        self.write_lines(sample("2026-10-05T09:00:00"), kind("2026-10-05T09:00:05", "stop", reason="endsAtPassed"))
        self.assertEqual(self.gaps("2026-10-05T00:00:00", "2026-10-10T00:00:00"), [])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-3
    def test_範囲をまたぐ5秒の空きは数えない(self):
        """否定確認: 範囲をまたぐ空きで30秒の判定を外す(直前が通常の行なら必ず数える)と落ちる"""
        self.write_lines(sample("2026-10-04T23:59:58"), sample("2026-10-05T00:00:03"),
                         kind("2026-10-05T00:00:05", "stop", reason="stopRequested"))
        self.assertEqual(self.gaps("2026-10-05T00:00:00", "2026-10-10T00:00:00"), [])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-3
    def test_範囲をまたぐ40秒の空きは月曜0時から数える(self):
        """否定確認: 空きの始まりを直前の行の時刻にすると落ちる"""
        self.write_lines(sample("2026-10-04T23:59:50"), sample("2026-10-05T00:00:30"),
                         kind("2026-10-05T00:00:35", "stop", reason="stopRequested"))
        self.assertEqual(self.gaps("2026-10-05T00:00:00", "2026-10-10T00:00:00"),
                         [(jst("2026-10-05T00:00:00"), jst("2026-10-05T00:00:30"))])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-3
    def test_範囲をまたぐ空きの長さは範囲の始まりからでなく直前の行から測る(self):
        """否定確認: 範囲の始まりから最初の行までの長さで判定すると落ちる(この例では20秒になり数えなくなる)"""
        self.write_lines(sample("2026-10-04T23:59:40"), sample("2026-10-05T00:00:20"),
                         kind("2026-10-05T00:00:25", "stop", reason="stopRequested"))
        self.assertEqual(self.gaps("2026-10-05T00:00:00", "2026-10-10T00:00:00"),
                         [(jst("2026-10-05T00:00:00"), jst("2026-10-05T00:00:20"))])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-3
    def test_範囲の終わりが金曜17時で最後の行が金曜15時なら15時から17時を数える(self):
        """否定確認: 範囲の終わりの空きを見ないと落ちる"""
        self.write_lines(kind("2026-10-09T09:00:00", "start"), sample("2026-10-09T09:00:00"), sample("2026-10-09T15:00:00"))
        self.assertEqual(self.gaps("2026-10-09T00:00:00", "2026-10-09T17:00:00"),
                         [(jst("2026-10-09T09:00:00"), jst("2026-10-09T15:00:00")),
                          (jst("2026-10-09T15:00:00"), jst("2026-10-09T17:00:00"))])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-3
    def test_最後の行が停止の行なら範囲の終わりまでは数えない(self):
        self.write_lines(kind("2026-10-09T14:59:55", "start"), sample("2026-10-09T14:59:55"),
                         kind("2026-10-09T15:00:00", "stop", reason="stopRequested"))
        self.assertEqual(self.gaps("2026-10-09T14:59:55", "2026-10-09T17:00:00"), [])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-3
    def test_最後の行から範囲の終わりまで29秒は数えず30秒は数える(self):
        """否定確認: 範囲の終わりの判定で30秒との比較を `>` にすると落ちる"""
        self.write_lines(kind("2026-10-09T16:59:31", "start"), sample("2026-10-09T16:59:31"))
        self.assertEqual(self.gaps("2026-10-09T16:59:31", "2026-10-09T17:00:00"), [])
        self.assertEqual(self.gaps("2026-10-09T16:59:31", "2026-10-09T17:00:01"),
                         [(jst("2026-10-09T16:59:31"), jst("2026-10-09T17:00:01"))])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-3
    def test_範囲内に行が無く直前が通常の行なら範囲全体を数える(self):
        self.write_lines(sample("2026-10-04T18:00:00"))
        self.assertEqual(self.gaps("2026-10-05T00:00:00", "2026-10-06T00:00:00"),
                         [(jst("2026-10-05T00:00:00"), jst("2026-10-06T00:00:00"))])


class ReadMemosTests(RecordsTestCase):
    """面倒だった作業のメモを期間で読む"""

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#面倒だった作業のメモ-3
    def test_期間のメモを時刻順に返し_形の違う行は読み飛ばす(self):
        lines = [
            {"id": "20261006-101530-a1b2", "t": "2026-10-06T10:15:30+09:00", "text": "勤怠の通知メールを移している"},
            {"id": "bad", "t": "2026-10-06T11:00:00+09:00", "text": "番号の形が違う"},
            {"id": "20261005-090000-ffff", "t": "2026-10-05T09:00:00+09:00", "text": "範囲の前"},
        ]
        with (self.paths.memos / "2026-10-06.jsonl").open("w", encoding="utf-8") as file:
            for line in lines[:2]:
                file.write(json.dumps(line, ensure_ascii=False) + "\n")
        with (self.paths.memos / "2026-10-05.jsonl").open("w", encoding="utf-8") as file:
            file.write(json.dumps(lines[2], ensure_ascii=False) + "\n")
        memos = records.read_memos(self.paths, jst("2026-10-06T00:00:00"), jst("2026-10-07T00:00:00"))
        self.assertEqual([memo["id"] for memo in memos], ["20261006-101530-a1b2"])
        self.assertEqual(memos[0]["time"], jst("2026-10-06T10:15:30"))

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#面倒だった作業のメモ-3
    def test_メモの文に行区切りの文字U2028があってもそのまま返す(self):
        """否定確認: splitlines で行を分けると、メモが割れて読み飛ばされ落ちる"""
        memo = {"id": "20261006-101530-a1b2", "t": "2026-10-06T10:15:30+09:00", "text": "1行目 2行目"}
        with (self.paths.memos / "2026-10-06.jsonl").open("w", encoding="utf-8") as file:
            file.write(json.dumps(memo, ensure_ascii=False) + "\n")
        memos = records.read_memos(self.paths, jst("2026-10-06T00:00:00"), jst("2026-10-07T00:00:00"))
        self.assertEqual([item["text"] for item in memos], ["1行目 2行目"])


if __name__ == "__main__":
    unittest.main()
