"""Claude に渡す材料の組み立て。

自動化案と作業の要約を Claude に作らせるために、送ってよいもの(集計した組・時間・時刻・題名・シート名・
カーソルのある部品の種類・既存の作業の記録・メモ・Skill とアプリの名前と説明)だけで材料を組み立て、
1回の呼び出しに収まる字数に絞る。社外へ出るものを絞るための決まりなので、項目の種類を突き合わせて確かめる。
"""

import os
import tempfile
import unittest
from pathlib import Path

from routine_work_finder.report import materials
from tests.claude_support import excluded, jst, memo, run, untitled, walk_keys, week_of

AUTOMATION_KEYS = {
    "week", "candidates", "candidates[].id", "candidates[].app", "candidates[].title", "candidates[].sheet",
    "candidates[].focusRole", "candidates[].sessions", "candidates[].totalMinutes", "candidates[].when",
    "candidates[].overlappingRecords", "candidates[].overlappingRecords[].source",
    "candidates[].overlappingRecords[].t", "candidates[].overlappingRecords[].text",
    "memos", "memos[].id", "memos[].t", "memos[].text",
    "reusable", "reusable[].name", "reusable[].kind", "reusable[].description",
}
SUMMARY_KEYS = {
    "week", "items", "items[].id", "items[].app", "items[].title", "items[].sheet", "items[].focusRole",
    "items[].totalMinutes", "items[].mainTimes", "items[].titleKnown", "items[].neighborApps",
    "items[].neighborApps[].t", "items[].neighborApps[].excluded",
    "items[].overlappingRecords", "items[].overlappingRecords[].source", "items[].overlappingRecords[].t",
    "items[].overlappingRecords[].text", "items[].memos", "items[].memos[].id", "items[].memos[].t",
    "items[].memos[].text",
}


def two_session_lines(title, count=12, **fields):
    """月曜と火曜の9時に count 行ずつ現れる組(30分以上あけて2回なので自動化案の候補になる)"""
    return run("2026-10-05T09:00:00", count, title=title, **fields) + run("2026-10-06T09:00:00", count, title=title, **fields)


def jira_record(text_time, host="example.atlassian.net"):
    return {"source": "jira", "site": host, "key": "SAG-123", "summary": "進捗表を直す", "field": "status",
            "from": "対応中", "to": "レビュー中", "time": jst(text_time)}


class SendableItemsTests(unittest.TestCase):
    """社外へ送ってよい種類の項目だけが材料に入る"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#社外へ送るもの-1、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#作業の要約-6
    def test_自動化案と作業の要約の材料に入る項目は送ってよい種類だけで記録の行の他の項目やサイトの名前は入らない(self):
        """否定確認: 候補に記録の行の bundleId を足すと落ちる。JIRA の記録の文にサイトの名前を入れると落ちる"""
        lines = two_session_lines("進捗表.xlsx", app="Microsoft Excel", sheet="集計", focusRole="AXTable",
                                  focusSubrole="AXSortButton", bundleId="com.microsoft.Excel", monitor=2)
        lines += run("2026-10-05T09:10:00", 2, app="Google Chrome", title="受信トレイ")
        lines.append(excluded("2026-10-05T09:01:00"))
        week = week_of(lines)
        memos = [memo("2026-10-05T09:00:30", "毎朝の転記が面倒")]
        records = [jira_record("2026-10-05T09:00:20")]
        reusable = [{"name": "jira-progress", "kind": "skill", "description": "JIRA の進捗を集める"}]

        automation = materials.build_automation_materials("2026-W41", week, memos, records, reusable)
        summary = materials.build_summary_materials("2026-W41", week, memos, records)

        self.assertEqual(walk_keys(automation.payload), AUTOMATION_KEYS)
        self.assertEqual(walk_keys(summary.payload), SUMMARY_KEYS)
        for payload in (automation.payload, summary.payload):
            text = materials.serialize(payload)
            for secret in ("example.atlassian.net", "com.microsoft.Excel", "AXSortButton"):
                self.assertNotIn(secret, text)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#作業の要約-6、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#社外へ送るもの-2
    def test_前後に記録しなかった時間があるときは時刻と除外中の印だけが入る(self):
        """否定確認: 除外中の行を飛ばして次のアプリを前後のアプリにすると落ちる"""
        lines = run("2026-10-05T09:00:00", 10, title="main.swift")
        lines.append(excluded("2026-10-05T09:00:50"))
        lines += run("2026-10-05T09:00:55", 3, app="Google Chrome", title="受信トレイ")
        summary = materials.build_summary_materials("2026-W41", week_of(lines), [], [])
        code = summary.payload["items"][0]
        self.assertEqual(code["title"], "main.swift")
        self.assertEqual(code["neighborApps"], [{"t": "2026-10-05T09:00:50+09:00", "excluded": True}])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#作業の要約-6
    def test_前後に使ったアプリは作業のまとまりの直前と直後のアプリ名で離席の行は飛ばす(self):
        """否定確認: 離席の行を飛ばさないと落ちる(離席の行のアプリ名が入る)"""
        lines = run("2026-10-05T08:59:50", 2, app="Microsoft Teams", title="会議の予定")
        lines += run("2026-10-05T09:00:00", 10, title="main.swift")
        lines += run("2026-10-05T09:00:50", 1, app="Finder", title="ダウンロード", locked=True)
        lines += run("2026-10-05T09:00:55", 3, app="Google Chrome", title="受信トレイ")
        summary = materials.build_summary_materials("2026-W41", week_of(lines), [], [])
        code = next(item for item in summary.payload["items"] if item["title"] == "main.swift")
        self.assertEqual(code["neighborApps"], ["Microsoft Teams", "Google Chrome"])


class AutomationMaterialsTests(unittest.TestCase):
    """自動化案の材料: 候補を時間の長い順に最大15件、メモは全件"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-4
    def test_メモは繰り返しの候補が無い週でも全件が番号付きで時刻の順に入る(self):
        """否定確認: 候補に重なるメモだけを入れると落ちる"""
        week = week_of(run("2026-10-05T09:00:00", 10))
        memos = [memo("2026-10-05T10:00:00", "勤怠のメールを毎回手で移す", "20261005-100000-aaaa"),
                 memo("2026-10-07T15:00:00", "CSVの列を並べ替える", "20261007-150000-bbbb")]
        payload = materials.build_automation_materials("2026-W41", week, memos, [], []).payload
        self.assertEqual(payload["candidates"], [])
        self.assertEqual(payload["memos"], [
            {"id": "m1", "t": "2026-10-05T10:00:00+09:00", "text": "勤怠のメールを毎回手で移す"},
            {"id": "m2", "t": "2026-10-07T15:00:00+09:00", "text": "CSVの列を並べ替える"},
        ])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-3
    def test_候補には組と回数と時間と曜日の時刻と最も長くカーソルがあった部品の種類と重なる記録が入る(self):
        """否定確認: 部品の種類を最初の行のものにすると落ちる。重なる記録をまとまりの外まで広げると落ちる"""
        lines = run("2026-10-05T09:00:00", 4, app="Microsoft Excel", title="進捗表.xlsx", sheet="集計", focusRole="AXTextArea")
        lines += run("2026-10-05T09:00:20", 8, app="Microsoft Excel", title="進捗表.xlsx", sheet="集計", focusRole="AXTable")
        lines += run("2026-10-06T09:00:00", 12, app="Microsoft Excel", title="進捗表.xlsx", sheet="集計")
        records = [
            jira_record("2026-10-05T09:00:30"),
            {"source": "confluence", "site": "example.atlassian.net", "title": "週報", "time": jst("2026-10-05T12:00:00")},
            {"source": "claudeCode", "repo": "study", "text": "進捗表の転記を手伝って", "time": jst("2026-10-06T09:00:10")},
            {"source": "minutes", "title": "定例", "summary": "進捗の確認", "time": jst("2026-10-06T09:00:55")},
        ]
        payload = materials.build_automation_materials("2026-W41", week_of(lines), [], records, []).payload
        self.assertEqual(payload["week"], "2026-W41")
        self.assertEqual(payload["candidates"], [{
            "id": "c1", "app": "Microsoft Excel", "title": "進捗表.xlsx", "sheet": "集計", "focusRole": "AXTable",
            "sessions": 2, "totalMinutes": 2, "when": ["月 09:00-09:01", "火 09:00-09:01"],
            "overlappingRecords": [
                {"source": "jira", "t": "2026-10-05T09:00:30+09:00", "text": "SAG-123 進捗表を直す status: 対応中 → レビュー中"},
                {"source": "claudeCode", "t": "2026-10-06T09:00:10+09:00", "text": "study: 進捗表の転記を手伝って"},
                {"source": "minutes", "t": "2026-10-06T09:00:55+09:00", "text": "定例: 進捗の確認"},
            ],
        }])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-3
    def test_部品の種類が取れなかった行は数えず1行も取れなかった組は空になる(self):
        """否定確認: 取れなかった行も数えて空の種類を選ぶと落ちる"""
        lines = two_session_lines("a.txt")
        lines += run("2026-10-07T09:00:00", 3, title="a.txt", focusRole="AXTextArea")
        lines += two_session_lines("b.txt", count=2)
        payload = materials.build_automation_materials("2026-W41", week_of(lines), [], [], []).payload
        self.assertEqual([candidate["focusRole"] for candidate in payload["candidates"]], ["AXTextArea", None])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-2
    def test_候補は時間の長い順に15件までで16件目は入らない(self):
        """否定確認: 件数の上限を外すと落ちる"""
        lines = []
        for index in range(16):
            lines += two_session_lines(f"作業{index:02d}.txt", count=40 - index)
        payload = materials.build_automation_materials("2026-W41", week_of(lines), [], [], []).payload
        self.assertEqual([candidate["title"] for candidate in payload["candidates"]],
                         [f"作業{index:02d}.txt" for index in range(15)])
        self.assertEqual(payload["candidates"][-1]["id"], "c15")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#社外へ送るもの-1
    def test_材料が120000字を超えると候補を時間の短い方から減らして収める(self):
        """否定確認: 長い方から減らすと落ちる。減らさないと字数の確認で落ちる"""
        lines = []
        for index in range(15):
            lines += two_session_lines(f"{index:02d}" + "表" * 3000, count=40 - index)
        memos = [memo("2026-10-05T10:00:00", "メ" * 100000)]
        built = materials.build_automation_materials("2026-W41", week_of(lines), memos, [], [])
        kept = [candidate["id"] for candidate in built.payload["candidates"]]
        self.assertLessEqual(len(materials.serialize(built.payload)), materials.CHAR_LIMIT)
        self.assertTrue(0 < len(kept) < 15)
        self.assertEqual(kept, [f"c{index}" for index in range(1, len(kept) + 1)])
        self.assertEqual(sorted(built.candidates), sorted(kept))
        self.assertEqual(len(built.payload["memos"]), 1)


class SummaryMaterialsTests(unittest.TestCase):
    """作業の要約の材料: 上位10件ごとの組・時間・主な時間帯と、前後のアプリ・重なる記録とメモ"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#作業の要約-2、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#作業の要約-5
    def test_上位の項目には主な時間帯と題名が取れたかと時間帯に重なるメモが入る(self):
        """否定確認: まとまりの外のメモも入れると落ちる"""
        lines = two_session_lines("main.swift")
        lines += [untitled(f"2026-10-07T09:00:{second:02d}", app="Code") for second in (0, 5, 10, 15)]
        memos = [memo("2026-10-05T09:00:30", "ビルドが遅い"), memo("2026-10-05T11:00:00", "関係ないメモ")]
        payload = materials.build_summary_materials("2026-W41", week_of(lines), memos, []).payload
        first, second = payload["items"]
        self.assertEqual((first["id"], first["title"], first["titleKnown"], first["totalMinutes"]), ("w1", "main.swift", True, 2))
        self.assertEqual(first["mainTimes"], ["月 09:00-09:01", "火 09:00-09:01"])
        self.assertEqual(first["memos"], [{"id": "m1", "t": "2026-10-05T09:00:30+09:00", "text": "ビルドが遅い"}])
        self.assertEqual((second["id"], second["title"], second["titleKnown"]), ("w2", None, False))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#社外へ送るもの-1
    def test_材料が120000字を超えると上位の項目を時間の短い方から減らして収める(self):
        """否定確認: 減らす向きを逆にすると落ちる"""
        lines = []
        for index in range(10):
            lines += run(f"2026-10-05T{9 + index:02d}:00:00", 30 - index, title=f"{index}" + "題" * 12500)
        built = materials.build_summary_materials("2026-W41", week_of(lines), [], [])
        self.assertLessEqual(len(materials.serialize(built.payload)), materials.CHAR_LIMIT)
        self.assertEqual([item["id"] for item in built.payload["items"]], [f"w{index}" for index in range(1, 10)])
        self.assertEqual(list(built.items), [f"w{index}" for index in range(1, 10)])


class ReusableListTests(unittest.TestCase):
    """使える既存の仕組みの一覧: Claude Code Skill の名前と説明と、study のアプリの概要"""

    def setUp(self):
        base = os.environ.get("TMPDIR") or tempfile.gettempdir()
        self.temporary = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-5
    def test_Skillは冒頭の名前と説明をアプリは概要の1段落目を集め説明の無いものは入れない(self):
        """否定確認: 概要の2段落目まで入れると落ちる。冒頭の区切りの無い SKILL.md も入れると落ちる"""
        self.write("skills/jira-progress/SKILL.md",
                   "---\nname: jira-progress\ndescription: JIRA の進捗を集める\n---\n\n# 本文\n")
        self.write("skills/no-front/SKILL.md", "# 冒頭の区切りが無い\nname: no-front\ndescription: 区切りの外\n")
        self.write("skills/empty/README.md", "SKILL.md が無い\n")
        self.write("apps/notes-api/specs/architecture.md",
                   "# notes-api の全体像\n\n## 概要\n\nノートを保存するAPI。\n\n2段落目。\n\n## 構成\n\n本文\n")
        self.write("apps/no-spec/README.md", "仕様が無い\n")
        reusable = materials.collect_reusable(self.root / "skills", self.root / "apps")
        self.assertEqual(reusable, [
            {"name": "jira-progress", "kind": "skill", "description": "JIRA の進捗を集める"},
            {"name": "notes-api", "kind": "app", "description": "ノートを保存するAPI。"},
        ])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-5
    def test_一覧のフォルダが無くても空の一覧で続ける(self):
        """否定確認: フォルダの有無を確かめずに読むと落ちる"""
        self.assertEqual(materials.collect_reusable(self.root / "none", self.root / "none2"), [])


if __name__ == "__main__":
    unittest.main()
