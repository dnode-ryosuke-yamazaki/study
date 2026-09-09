"""候補が0件のときの代替案の組み立て(tasks.md 9)のテスト。

既定の条件で0件のとき、条件を段階的に緩めるのではなく2つの代替案を並べて開催者に選ばせる。
代替案1は同じ候補ファイルを仮の予定を空きとみなして絞り直すだけで依頼を出し直さない。
代替案2は期間と時間帯を広げた試行番号2の依頼を作るが、開催者が明示的に指定した項目は広げない。
"""

import unittest
from datetime import date, datetime, time, timedelta, timezone

import candidates
import config
import request
from tests.test_candidates import _候補ファイル, _枠

JST = timezone(timedelta(hours=9))
今日 = date(2026, 9, 9)
参加者 = [{"name": "A", "email": "a@example.com"}, {"name": "B", "email": "b@example.com"}]


def _依頼(**上書き):
    設定 = config.load(environ={})
    条件 = request.依頼条件(件名="定例", 参加者=参加者, 所要時間分=60, **上書き)
    return request.組み立て(条件, 設定, 今日, "ID1")


class 代替案2の依頼(unittest.TestCase):

    def setUp(self):
        self.設定 = config.load(environ={})

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-1
    def test_期間を当日から3週間に時間帯を9時30分から18時30分に広げた試行番号2の依頼を作ること(self):
        代替 = request.代替案2の依頼を組み立てる(_依頼(), self.設定, 今日)
        self.assertEqual(代替["requestId"], "ID1")
        self.assertEqual(代替["attempt"], 2)
        self.assertEqual(代替["search"]["start"], "2026-09-09T00:00:00+09:00")
        self.assertEqual(代替["search"]["end"], "2026-09-30T23:59:59+09:00")
        self.assertEqual(代替["filter"]["timeWindowStart"], "09:30")
        self.assertEqual(代替["filter"]["timeWindowEnd"], "18:30")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#9-候補が0件のときの代替案の組み立てrequestpy
    def test_対象曜日と全員空きと候補件数とアジェンダは元の依頼のまま引き継ぐこと(self):
        元 = _依頼(対象曜日=(0, 5), 候補件数=3, アジェンダ="- 議題")
        代替 = request.代替案2の依頼を組み立てる(元, self.設定, 今日)
        self.assertEqual(代替["filter"]["weekdays"], [0, 5])
        self.assertEqual(代替["filter"]["maxResults"], 3)
        self.assertEqual(代替["meeting"], 元["meeting"])
        self.assertEqual(代替["specified"], 元["specified"])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-4
    def test_探索期間が指定されていれば期間は広げず時間帯だけを広げること(self):
        元 = _依頼(期間開始=date(2026, 9, 10), 期間終了=date(2026, 9, 12))
        代替 = request.代替案2の依頼を組み立てる(元, self.設定, 今日)
        self.assertEqual(代替["search"], 元["search"])
        self.assertEqual(代替["filter"]["timeWindowEnd"], "18:30")
        self.assertEqual(request.広げなかった項目(元), ["期間"])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-4
    def test_時間帯が指定されていれば時間帯は広げず期間だけを広げること(self):
        元 = _依頼(時間帯開始=time(13, 0), 時間帯終了=time(15, 0))
        代替 = request.代替案2の依頼を組み立てる(元, self.設定, 今日)
        self.assertEqual(代替["filter"]["timeWindowStart"], "13:00")
        self.assertEqual(代替["filter"]["timeWindowEnd"], "15:00")
        self.assertEqual(代替["search"]["end"], "2026-09-30T23:59:59+09:00")
        self.assertEqual(request.広げなかった項目(元), ["時間帯"])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-4
    def test_期間と時間帯の両方が指定されていれば代替案2を作らないこと(self):
        元 = _依頼(期間終了=date(2026, 9, 12), 時間帯終了=time(15, 0))
        self.assertFalse(request.代替案2を作れるか(元))
        self.assertIsNone(request.代替案2の依頼を組み立てる(元, self.設定, 今日))
        self.assertEqual(request.広げなかった項目(元), ["期間", "時間帯"])

    def test_指定が無ければ代替案2を作れること(self):
        self.assertTrue(request.代替案2を作れるか(_依頼()))
        self.assertEqual(request.広げなかった項目(_依頼()), [])


class 代替案1の絞り直し(unittest.TestCase):

    def _読み(self, 枠一覧):
        return candidates.読む(_候補ファイル(枠一覧))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-1
    def test_同じ候補ファイルを仮の予定を空きとみなして絞り直し依頼を作らないこと(self):
        読み = self._読み([_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 出席者=("free", "tentative"))])
        結果 = request.代替案1を組み立てる(読み, candidates.絞り込み条件.依頼から(_依頼()), 要求件数=50)
        self.assertEqual(len(結果.採用), 1)
        self.assertEqual(結果.件名を取りに行く対象, ["p1@example.com"])
        self.assertFalse(結果.打ち切りの可能性)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-7
    def test_代替案1が0件で受け取った枠が要求件数と同数なら打ち切りの可能性を含めること(self):
        枠一覧 = [_枠(datetime(2026, 9, 10, 10 + i, 0, tzinfo=JST), 出席者=("busy", "free")) for i in range(3)]
        結果 = request.代替案1を組み立てる(self._読み(枠一覧), candidates.絞り込み条件.依頼から(_依頼()), 要求件数=3)
        self.assertEqual(結果.採用, [])
        self.assertTrue(結果.打ち切りの可能性)
        結果2 = request.代替案1を組み立てる(self._読み(枠一覧), candidates.絞り込み条件.依頼から(_依頼()), 要求件数=50)
        self.assertFalse(結果2.打ち切りの可能性)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-2
    def test_開催者が仮の枠では開催者のメールアドレスが分かる場合だけ件名を取りに行く対象に含めること(self):
        読み = self._読み([_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 開催者="tentative")])
        条件 = candidates.絞り込み条件.依頼から(_依頼())
        self.assertEqual(request.代替案1を組み立てる(読み, 条件, 要求件数=50).件名を取りに行く対象, [])
        結果 = request.代替案1を組み立てる(読み, 条件, 要求件数=50, 開催者メール="me@example.com")
        self.assertEqual(結果.件名を取りに行く対象, ["me@example.com"])


class 試した条件の報告(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-6
    def test_代替案2を作らなかった場合は既定と代替案1の2通りを返すこと(self):
        元 = _依頼(期間終了=date(2026, 9, 12), 時間帯終了=time(15, 0))
        一覧 = request.試した条件(元, None)
        self.assertEqual(len(一覧), 2)
        self.assertIn("09:30", 一覧[0])
        self.assertIn("仮の予定", 一覧[1])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-6
    def test_代替案2を作った場合は3通りを返し広げた後の条件が含まれること(self):
        元 = _依頼()
        代替 = request.代替案2の依頼を組み立てる(元, config.load(environ={}), 今日)
        一覧 = request.試した条件(元, 代替)
        self.assertEqual(len(一覧), 3)
        self.assertIn("18:30", 一覧[2])
        self.assertIn("2026-09-30", 一覧[2])


if __name__ == "__main__":
    unittest.main()
