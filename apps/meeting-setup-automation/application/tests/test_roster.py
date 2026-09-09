"""メンバー名簿の読み込みと名前の解決(tasks.md 3)のテスト。

参加者は名前で指定され、Git管理外の名簿でメールアドレスに解決する。登録がない名前や
同じ名前が複数ある名前を黙って解決すると、誤字や同姓の別人を会議に招待する事故になるため、
解決できない名前があれば全体を失敗として返すことを検証する。
"""

import json
import tempfile
import unittest
from pathlib import Path

import roster


def _名簿を書く(d, members, organizer=None):
    内容 = {"members": members}
    if organizer is not None:
        内容["organizer"] = organizer
    path = Path(d, "roster.json")
    path.write_text(json.dumps(内容, ensure_ascii=False), encoding="utf-8")
    return path


class 名簿の読み込み(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-1
    def test_作業フォルダのrosterjsonから名前とメールアドレスの対応表を読めること(self):
        with tempfile.TemporaryDirectory() as d:
            path = _名簿を書く(d, [{"name": "山田 太郎", "email": "taro@example.com"}])
            名簿 = roster.load(path)
        self.assertEqual(名簿.resolve_one("山田 太郎"), "taro@example.com")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#3-メンバー名簿の読み込みと名前の解決rosterpy
    def test_名簿が無い場合は解決を試みずその旨の例外になること(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(roster.名簿エラー) as cm:
                roster.load(Path(d, "roster.json"))
        self.assertIn("見つかりません", str(cm.exception))

    def test_名簿がJSONとして読めない場合もその旨の例外になること(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "roster.json")
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(roster.名簿エラー):
                roster.load(path)

    def test_開催者の記載は任意で無くても読めること(self):
        with tempfile.TemporaryDirectory() as d:
            名簿 = roster.load(_名簿を書く(d, [{"name": "A", "email": "a@example.com"}]))
            self.assertIsNone(名簿.organizer_email)
            名簿2 = roster.load(
                _名簿を書く(
                    d,
                    [{"name": "A", "email": "a@example.com"}],
                    organizer={"name": "私", "email": "me@example.com"},
                )
            )
            self.assertEqual(名簿2.organizer_email, "me@example.com")


class 名前の解決(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.名簿 = roster.load(
            _名簿を書く(
                self._tmp.name,
                [
                    {"name": "山田 太郎", "email": "taro@example.com"},
                    {"name": "鈴木 花子", "email": "hanako@example.com"},
                    {"name": "佐藤 次郎", "email": "jiro1@example.com"},
                    {"name": "佐藤 次郎", "email": "jiro2@example.com"},
                ],
            )
        )

    def tearDown(self):
        self._tmp.cleanup()

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議設定の依頼-3
    def test_登録のある名前を1件解決できること(self):
        self.assertEqual(self.名簿.resolve_one("鈴木 花子"), "hanako@example.com")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-2
    def test_登録がない名前は解決できないものとして返ること(self):
        self.assertIsNone(self.名簿.resolve_one("存在 しない"))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-2
    def test_同じ名前が複数ある場合はどちらかを選ばず解決できないものとして返ること(self):
        self.assertIsNone(self.名簿.resolve_one("佐藤 次郎"))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議設定の依頼-4、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-3
    def test_複数の名前をまとめて解決し解決できなかった名前の一覧が返ること(self):
        結果 = self.名簿.resolve(["山田 太郎", "存在 しない", "佐藤 次郎", "鈴木 花子"])
        self.assertEqual(結果.未解決, ["存在 しない", "佐藤 次郎"])
        self.assertFalse(結果.ok)
        self.assertEqual(
            結果.解決済み,
            [
                {"name": "山田 太郎", "email": "taro@example.com"},
                {"name": "鈴木 花子", "email": "hanako@example.com"},
            ],
        )

    def test_全員解決できた場合は成功として返ること(self):
        結果 = self.名簿.resolve(["山田 太郎", "鈴木 花子"])
        self.assertTrue(結果.ok)
        self.assertEqual(結果.未解決, [])

    def test_名前の前後の空白は無視して解決すること(self):
        self.assertEqual(self.名簿.resolve_one("  山田 太郎 "), "taro@example.com")


if __name__ == "__main__":
    unittest.main()
