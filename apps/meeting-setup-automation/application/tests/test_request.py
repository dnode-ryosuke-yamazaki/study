"""依頼IDの生成・依頼の組み立てと書き出し・入力値のバリデーション(tasks.md 4・5)のテスト。

依頼ファイルは探索フローが読む「探索の指示」と、Skillだけが読む「絞り込みの条件」
「開催者が指定した項目」を持ち、待ちを打ち切った後の再開でも依頼時の情報が失われない
ことを検証する。受け付け条件を満たさない依頼は書き出さず、満たしていない項目を返す。
"""

import json
import tempfile
import unittest
from datetime import date, time
from pathlib import Path

import config
import request

今日 = date(2026, 9, 9)  # 水曜
参加者 = [
    {"name": "山田 太郎", "email": "taro@example.com"},
    {"name": "鈴木 花子", "email": "hanako@example.com"},
]


def _設定(d=None):
    env = {config.台帳ルート環境変数: d} if d else {}
    return config.load(environ=env)


def _条件(**上書き):
    値 = dict(件名="定例", 参加者=参加者, 所要時間分=60, アジェンダ="- 進捗\n- 課題")
    値.update(上書き)
    return request.依頼条件(**値)


class 依頼IDの生成(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議設定の依頼-5
    def test_依頼IDが年月日と時分秒に乱数4文字を添えた形であること(self):
        from datetime import datetime

        依頼id = request.依頼idを生成(datetime(2026, 9, 9, 10, 15, 0))
        self.assertRegex(依頼id, r"^20260909-101500-[0-9a-z]{4}$")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#非機能要件-1
    def test_同じ時刻に連続して生成しても重ならないこと(self):
        from datetime import datetime

        同時刻 = datetime(2026, 9, 9, 10, 15, 0)
        一覧 = {request.依頼idを生成(同時刻) for _ in range(200)}
        self.assertEqual(len(一覧), 200)


class 依頼の組み立て(unittest.TestCase):

    def setUp(self):
        self.設定 = _設定()

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補探索の既定条件-1、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議設定の依頼-2
    def test_指定のない項目には既定値が使われること(self):
        依頼 = request.組み立て(_条件(), self.設定, 今日, "ID1")
        self.assertEqual(依頼["requestId"], "ID1")
        self.assertEqual(依頼["attempt"], 1)
        self.assertEqual(依頼["search"]["start"], "2026-09-09T00:00:00+09:00")
        self.assertEqual(依頼["search"]["end"], "2026-09-23T23:59:59+09:00")
        self.assertEqual(依頼["search"]["minimumAttendeePercentage"], 100)
        self.assertEqual(依頼["search"]["maxCandidates"], 50)
        self.assertEqual(依頼["filter"]["timeWindowStart"], "09:30")
        self.assertEqual(依頼["filter"]["timeWindowEnd"], "17:30")
        self.assertEqual(依頼["filter"]["weekdays"], [0, 1, 2, 3, 4])
        self.assertTrue(依頼["filter"]["requireAllFree"])
        self.assertEqual(依頼["filter"]["maxResults"], 5)
        self.assertEqual(依頼["specified"], [])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議設定の依頼-2
    def test_指定がある項目はそれを優先し指定した項目の一覧に記録されること(self):
        依頼 = request.組み立て(
            _条件(
                期間開始=date(2026, 9, 10),
                期間終了=date(2026, 9, 12),
                時間帯開始=time(13, 0),
                時間帯終了=time(18, 0),
                候補件数=3,
                対象曜日=(0, 5),
                全員空き=False,
            ),
            self.設定,
            今日,
            "ID1",
        )
        self.assertEqual(依頼["search"]["start"], "2026-09-10T00:00:00+09:00")
        self.assertEqual(依頼["search"]["end"], "2026-09-12T23:59:59+09:00")
        self.assertEqual(依頼["filter"]["timeWindowStart"], "13:00")
        self.assertEqual(依頼["filter"]["timeWindowEnd"], "18:00")
        self.assertEqual(依頼["filter"]["maxResults"], 3)
        self.assertEqual(依頼["filter"]["weekdays"], [0, 5])
        self.assertFalse(依頼["filter"]["requireAllFree"])
        self.assertEqual(
            依頼["specified"], ["period", "timeWindow", "maxResults", "weekdays", "allFree"]
        )

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#依頼ファイルの区分
    def test_既定値と同じ値を明示的に指定した場合も指定として扱われること(self):
        依頼 = request.組み立て(_条件(候補件数=5), self.設定, 今日, "ID1")
        self.assertEqual(依頼["specified"], ["maxResults"])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補探索の既定条件-3
    def test_全員空きを求めない指示では出席可能率の下限も併せて下げること(self):
        依頼 = request.組み立て(_条件(全員空き=False), self.設定, 今日, "ID1")
        self.assertLess(依頼["search"]["minimumAttendeePercentage"], 100)
        self.assertFalse(依頼["filter"]["requireAllFree"])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#台帳ファイルの扱い-5
    def test_依頼にアジェンダの原文と会議の内容が含まれること(self):
        依頼 = request.組み立て(_条件(), self.設定, 今日, "ID1")
        self.assertEqual(依頼["meeting"]["subject"], "定例")
        self.assertEqual(依頼["meeting"]["durationMinutes"], 60)
        self.assertEqual(依頼["meeting"]["agenda"], "- 進捗\n- 課題")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議の作成内容-2
    def test_参加者はGraphが受け取る形の必須出席者として書かれること(self):
        依頼 = request.組み立て(_条件(), self.設定, 今日, "ID1")
        self.assertEqual(
            依頼["meeting"]["attendees"],
            [
                {"emailAddress": {"address": "taro@example.com", "name": "山田 太郎"}, "type": "required"},
                {"emailAddress": {"address": "hanako@example.com", "name": "鈴木 花子"}, "type": "required"},
            ],
        )

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#依頼内容の受け付け条件-6
    def test_アジェンダの指定が無くても依頼を組み立てられること(self):
        依頼 = request.組み立て(_条件(アジェンダ=""), self.設定, 今日, "ID1")
        self.assertEqual(依頼["meeting"]["agenda"], "")


class 依頼の書き出し(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議設定の依頼-5、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#台帳ファイルの扱い-2
    def test_依頼フォルダへ依頼IDと試行番号を含む名前で書き出されること(self):
        with tempfile.TemporaryDirectory() as d:
            設定 = _設定(d)
            依頼 = request.組み立て(_条件(), 設定, 今日, "ID1")
            結果 = request.書き出す(設定, 依頼)
            self.assertTrue(結果.ok)
            path = Path(d, "request", "request-ID1-a1.json")
            self.assertTrue(path.is_file())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["requestId"], "ID1")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#4-依頼idの生成と依頼の書き出しrequestpy
    def test_書き出しに失敗しても例外を投げず失敗した旨を返すこと(self):
        with tempfile.TemporaryDirectory() as d:
            # 依頼フォルダの位置に通常ファイルを置いて、フォルダを作れない状態にする
            Path(d, "request").write_text("x", encoding="utf-8")
            設定 = _設定(d)
            結果 = request.書き出す(設定, request.組み立て(_条件(), 設定, 今日, "ID1"))
        self.assertFalse(結果.ok)
        self.assertIn("書き出せません", 結果.error)


class 入力値のバリデーション(unittest.TestCase):

    def setUp(self):
        self.設定 = _設定()

    def _不備(self, **上書き):
        return request.検証(_条件(**上書き), self.設定, 今日)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#依頼内容の受け付け条件-1
    def test_所要時間が5分未満または時間帯の長さを超える場合は不正になること(self):
        self.assertTrue(any("所要時間" in 項目 for 項目 in self._不備(所要時間分=4)))
        self.assertTrue(any("所要時間" in 項目 for 項目 in self._不備(所要時間分=8 * 60 + 1)))
        self.assertEqual(self._不備(所要時間分=5), [])
        self.assertEqual(self._不備(所要時間分=8 * 60), [])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#依頼内容の受け付け条件-2
    def test_探索期間の開始が終了より後または当日より前の場合は不正になること(self):
        self.assertTrue(
            any("探索期間" in 項目 for 項目 in self._不備(期間開始=date(2026, 9, 12), 期間終了=date(2026, 9, 10)))
        )
        self.assertTrue(any("探索期間" in 項目 for 項目 in self._不備(期間開始=date(2026, 9, 8))))
        self.assertEqual(self._不備(期間開始=今日, 期間終了=今日), [])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#依頼内容の受け付け条件-3
    def test_探索期間の終了日が当日から3週間より先の場合は不正になること(self):
        self.assertTrue(any("3週間" in 項目 for 項目 in self._不備(期間終了=date(2026, 10, 1))))
        self.assertEqual(self._不備(期間終了=date(2026, 9, 30)), [])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#依頼内容の受け付け条件-4
    def test_時間帯の開始が終了以降または差が所要時間未満の場合は不正になること(self):
        self.assertTrue(any("時間帯" in 項目 for 項目 in self._不備(時間帯開始=time(17, 0), 時間帯終了=time(17, 0))))
        self.assertTrue(any("時間帯" in 項目 for 項目 in self._不備(時間帯開始=time(17, 0), 時間帯終了=time(17, 30))))
        self.assertEqual(self._不備(時間帯開始=time(16, 30), 時間帯終了=time(17, 30)), [])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#依頼内容の受け付け条件-5
    def test_候補件数が0以下の場合は不正になること(self):
        self.assertTrue(any("候補件数" in 項目 for 項目 in self._不備(候補件数=0)))
        self.assertEqual(self._不備(候補件数=1), [])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#依頼内容の受け付け条件-8
    def test_参加者の人数では不正としないこと(self):
        多数 = [{"name": f"人{i}", "email": f"p{i}@example.com"} for i in range(200)]
        self.assertEqual(self._不備(参加者=多数), [])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#依頼内容の受け付け条件-6
    def test_アジェンダの指定が無くても不正としないこと(self):
        self.assertEqual(self._不備(アジェンダ=""), [])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#依頼内容の受け付け条件-7
    def test_満たしていない項目が複数あればすべて返ること(self):
        不備 = self._不備(所要時間分=1, 候補件数=0)
        self.assertEqual(len(不備), 2)


if __name__ == "__main__":
    unittest.main()
