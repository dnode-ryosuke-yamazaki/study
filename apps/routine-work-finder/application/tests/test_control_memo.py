"""操作スクリプトの面倒だった作業のメモの追加・一覧・削除。

面倒だと思ったときにチャットで書き残し、週次レポートの材料にする。記録を止めている間も書ける。
"""

import json
import os
import stat
import unittest

from tests.control_support import ControlTestCase, jst


class MemoTests(ControlTestCase):
    """面倒だった作業のメモ"""

    def add(self, text, now=None):
        path = self.write_input("memo.json", {"text": text})
        return self.run_control("memo", "add", "--input-file", str(path), now=now), path

    def memo_lines(self, date):
        path = self.paths.memos / f"{date}.jsonl"
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        return [json.loads(line) for line in text.split("\n") if line]

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#面倒だった作業のメモ-1
    def test_入力ファイルの文と日時を残し_入力ファイルを消す(self):
        """否定確認: 日時を残さないと落ちる"""
        result, path = self.add("勤怠の通知メールを毎回手でフォルダに移している")
        self.assertTrue(result["ok"], result)
        lines = self.memo_lines("2026-10-07")
        self.assertEqual(lines[0]["text"], "勤怠の通知メールを毎回手でフォルダに移している")
        self.assertEqual(lines[0]["t"], "2026-10-07T10:00:00+09:00")
        self.assertRegex(lines[0]["id"], r"^20261007-100000-[0-9a-f]{4}$")
        self.assertEqual(result["data"]["id"], lines[0]["id"])
        self.assertFalse(path.exists())

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#面倒だった作業のメモ-1
    def test_空の文は断る(self):
        result, _ = self.add("  \n ")
        self.assertEqual(result["error"], "emptyText")

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#面倒だった作業のメモ-1、apps/routine-work-finder/specs/activity-recording/requirements.md#面倒だった作業のメモ-5
    def test_断ったときはメモのフォルダもファイルも作らない(self):
        """否定確認: 書けるかを確かめるために作ったフォルダ・ファイルを残すと落ちる"""
        for text in ("  ", "あ" * 2001):
            with self.subTest(length=len(text)):
                result, _ = self.add(text)
                self.assertFalse(result["ok"])
                self.assertFalse(self.paths.memos.exists())

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#面倒だった作業のメモ-1
    def test_入力ファイルが無い_形が違うときは断る(self):
        self.assertEqual(self.run_control("memo", "add", "--input-file", str(self.input_dir / "x.json"))["error"], "badInputFile")
        path = self.write_input("memo.json", {"note": "x"})
        self.assertEqual(self.run_control("memo", "add", "--input-file", str(path))["error"], "badInputFile")

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#面倒だった作業のメモ-1
    def test_書けないときは入力ファイルを残しその絶対パスを返す(self):
        path = self.write_input("memo.json", {"text": "メモ"})
        self.make_unwritable()
        result = self.run_control("memo", "add", "--input-file", str(path))
        self.assertEqual(result["error"], "dataFolderUnwritable")
        self.assertEqual(result["inputFile"], str(path.resolve()))
        self.assertTrue(path.exists())

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#面倒だった作業のメモ-1
    def test_メモのフォルダ_その日のメモのファイルに書けないときも入力ファイルを残しその絶対パスを返す(self):
        """否定確認: データフォルダと control.log だけを確かめてメモのファイルに書きにいくと落ちる"""
        self.add("先に残したメモ")
        memo_file = self.paths.memos / "2026-10-07.jsonl"
        # その日のファイルがあるときはファイルに、まだ無い日(翌日)はフォルダに書けないと書き足せない
        cases = [(memo_file, stat.S_IRUSR, stat.S_IRUSR | stat.S_IWUSR, self.now),
                 (self.paths.memos, stat.S_IRUSR | stat.S_IXUSR, stat.S_IRWXU, jst("2026-10-08T10:00:00"))]
        for target, locked, unlocked, now in cases:
            with self.subTest(target=target.name):
                path = self.write_input("memo.json", {"text": "メモ"})
                os.chmod(target, locked)
                try:
                    result = self.run_control("memo", "add", "--input-file", str(path), now=now)
                finally:
                    os.chmod(target, unlocked)
                self.assertEqual(result["error"], "dataFolderUnwritable")
                self.assertEqual(result["inputFile"], str(path.resolve()))
                self.assertTrue(path.exists())
                self.assertEqual([line["text"] for line in self.memo_lines("2026-10-07")], ["先に残したメモ"])
                self.assertEqual(self.memo_lines("2026-10-08"), [])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#面倒だった作業のメモ-4
    def test_メモのフォルダに書けないときは消さずに断る(self):
        """否定確認: メモのフォルダに書けるかを確かめずに書き直しにいくと落ちる"""
        result, _ = self.add("残る")
        os.chmod(self.paths.memos, stat.S_IRUSR | stat.S_IXUSR)
        try:
            deleted = self.run_control("memo", "delete", "--id", result["data"]["id"])
        finally:
            os.chmod(self.paths.memos, stat.S_IRWXU)
        self.assertEqual(deleted["error"], "dataFolderUnwritable")
        self.assertEqual([line["text"] for line in self.memo_lines("2026-10-07")], ["残る"])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#面倒だった作業のメモ-2
    def test_記録を止めていても_設定ファイルが壊れていてもメモは書ける(self):
        """否定確認: メモでも設定ファイルを読んで断ると落ちる"""
        self.root.mkdir(parents=True)
        self.paths.config.write_text("{broken", encoding="utf-8")
        result, _ = self.add("メモ")
        self.assertTrue(result["ok"], result)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#面倒だった作業のメモ-3、apps/routine-work-finder/specs/activity-recording/requirements.md#日付と週の基準-2
    def test_その週のメモの一覧は月曜0時から_日曜23時59分のメモは前の週に入る(self):
        """否定確認: 週の始まりを日曜にすると落ちる"""
        self.add("前の週", now=jst("2026-10-11T23:59:00"))
        self.add("今週", now=jst("2026-10-12T00:00:00"))
        result = self.run_control("memo", "list", now=jst("2026-10-13T10:00:00"))
        self.assertEqual([memo["text"] for memo in result["data"]["memos"]], ["今週"])
        self.assertEqual(set(result["data"]["memos"][0]), {"id", "t", "text"})

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#面倒だった作業のメモ-4
    def test_指定したメモを消し_ほかのメモは残す(self):
        """否定確認: 番号を見ずにファイルごと消すと落ちる"""
        self.add("残す", now=jst("2026-10-07T09:00:00"))
        second, _ = self.add("消す", now=jst("2026-10-07T09:30:00"))
        result = self.run_control("memo", "delete", "--id", second["data"]["id"])
        self.assertTrue(result["ok"], result)
        self.assertEqual([line["text"] for line in self.memo_lines("2026-10-07")], ["残す"])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#面倒だった作業のメモ-4
    def test_文に行区切りの文字U2028があるメモも消せ_ほかのメモはそのまま残る(self):
        """否定確認: splitlines で行を分けると、メモが割れて番号が見つからず落ちる"""
        self.add("残す メモ", now=jst("2026-10-07T09:00:00"))
        second, _ = self.add("消す メモ", now=jst("2026-10-07T09:30:00"))
        result = self.run_control("memo", "delete", "--id", second["data"]["id"])
        self.assertTrue(result["ok"], result)
        self.assertEqual([line["text"] for line in self.memo_lines("2026-10-07")], ["残す メモ"])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#面倒だった作業のメモ-4
    def test_無い番号_形の違う番号は断る(self):
        self.add("メモ")
        self.assertEqual(self.run_control("memo", "delete", "--id", "20261007-100000-ffff")["error"], "notFound")
        self.assertEqual(self.run_control("memo", "delete", "--id", "abc")["error"], "badRequest")

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#面倒だった作業のメモ-5
    def test_2000字までは残し_2001字は残さずに短くするよう返す(self):
        """否定確認: 2,000字との比較を `>=` にすると落ちる"""
        for length in (1999, 2000):
            with self.subTest(length=length):
                result, _ = self.add("あ" * length)
                self.assertTrue(result["ok"], result)
        result, _ = self.add("あ" * 2001)
        self.assertEqual(result["error"], "tooLong")
        self.assertEqual(len(self.memo_lines("2026-10-07")), 2)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#面倒だった作業のメモ-1
    def test_メモのファイルは600で_ログに文は書かない(self):
        self.add("給与の振込を確かめる")
        path = self.paths.memos / "2026-10-07.jsonl"
        self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")
        self.assertEqual(oct(self.paths.memos.stat().st_mode & 0o777), "0o700")
        self.assertNotIn("給与", self.paths.control_log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
