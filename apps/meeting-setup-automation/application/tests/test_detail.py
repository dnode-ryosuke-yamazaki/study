"""予定詳細の依頼と件名の取り出し(tasks.md 10)のテスト。

代替案1の枠に仮の予定を持つ参加者について、重ねてよいかの判断材料として予定の件名を示す。
予定詳細は世界標準時で届くため日本時間に変換してから枠と突き合わせる。共有されていない
カレンダー・繰り返し予定・非公開の予定は件名を示さず、その旨だけを返す。
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import candidates
import config
import detail

JST = timezone(timedelta(hours=9))


def _枠(開始, 分=60, 試行=1):
    return candidates.枠(開始=開始, 終了=開始 + timedelta(minutes=分), 出席者空き=[], 開催者空き="free", 試行番号=試行)


def _utc(jst: datetime) -> str:
    return jst.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000")


def _予定(開始jst, 分=60, 件名="顧客MTG", showAs="tentative", sensitivity="normal", **追加):
    項目 = {
        "subject": 件名,
        "showAs": showAs,
        "sensitivity": sensitivity,
        "start": {"dateTime": _utc(開始jst), "timeZone": "UTC"},
        "end": {"dateTime": _utc(開始jst + timedelta(minutes=分)), "timeZone": "UTC"},
    }
    項目.update(追加)
    return 項目


class 予定詳細の依頼(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#予定詳細の依頼ファイルの区分
    def test_対象の参加者と代替案1の枠すべてを含む範囲で依頼を組み立てること(self):
        枠一覧 = [_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST)), _枠(datetime(2026, 9, 12, 15, 0, tzinfo=JST))]
        依頼 = detail.依頼を組み立てる("ID1", 枠一覧, ["b@example.com", "c@example.com"])
        self.assertEqual(依頼["requestId"], "ID1")
        self.assertEqual(依頼["attendees"], ["b@example.com", "c@example.com"])
        self.assertEqual(依頼["start"], "2026-09-10T10:00:00+09:00")
        self.assertEqual(依頼["end"], "2026-09-12T16:00:00+09:00")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#10-予定詳細の依頼と件名の取り出しdetailpy
    def test_予定詳細の依頼フォルダへdetail_request_依頼IDの名前で書き出せること(self):
        with tempfile.TemporaryDirectory() as d:
            設定 = config.load(environ={config.台帳ルート環境変数: d})
            依頼 = detail.依頼を組み立てる("ID1", [_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST))], ["b@example.com"])
            結果 = detail.書き出す(設定, 依頼)
            self.assertTrue(結果.ok)
            path = Path(d, "detailRequest", "detail-request-ID1.json")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["requestId"], "ID1")

    def test_書き出しに失敗しても例外を投げず失敗した旨を返すこと(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "detailRequest").write_text("x", encoding="utf-8")
            設定 = config.load(environ={config.台帳ルート環境変数: d})
            結果 = detail.書き出す(設定, detail.依頼を組み立てる("ID1", [_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST))], ["b@example.com"]))
        self.assertFalse(結果.ok)


class 件名の取り出し(unittest.TestCase):

    def setUp(self):
        self.枠 = _枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST))  # 10:00-11:00

    def _読み(self, 参加者一覧, 失敗=""):
        return detail.読む({"requestId": "ID1", "error": 失敗, "attendees": 参加者一覧})

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-2
    def test_枠と時間が重なる仮の予定の件名を参加者ごとに返すこと(self):
        読み = self._読み(
            [
                {
                    "address": "b@example.com",
                    "calendarFound": True,
                    "events": [
                        _予定(datetime(2026, 9, 10, 10, 30, tzinfo=JST), 件名="顧客MTG"),
                        _予定(datetime(2026, 9, 10, 14, 0, tzinfo=JST), 件名="重ならない予定"),
                        _予定(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 件名="確定済み", showAs="busy"),
                    ],
                }
            ]
        )
        一覧 = detail.枠に重なる仮の予定(読み, self.枠, ["b@example.com"])
        self.assertEqual(len(一覧), 1)
        self.assertEqual(一覧[0].アドレス, "b@example.com")
        self.assertEqual(一覧[0].件名一覧, ["顧客MTG"])
        self.assertFalse(一覧[0].取得できない)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#10-予定詳細の依頼と件名の取り出しdetailpy
    def test_世界標準時で届いた予定を日本時間に変換してから突き合わせること(self):
        # 日本時間10:30の予定は世界標準時では01:30。変換せずに比較すると枠(10:00-11:00)と重ならない
        読み = self._読み(
            [{"address": "b@example.com", "calendarFound": True, "events": [_予定(datetime(2026, 9, 10, 10, 30, tzinfo=JST))]}]
        )
        self.assertEqual(detail.枠に重なる仮の予定(読み, self.枠, ["b@example.com"])[0].件名一覧, ["顧客MTG"])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-3
    def test_カレンダーが見つからなかった参加者は件名を取得できないものとして返すこと(self):
        読み = self._読み([{"address": "c@example.com", "calendarFound": False, "events": []}])
        一覧 = detail.枠に重なる仮の予定(読み, self.枠, ["c@example.com"])
        self.assertTrue(一覧[0].取得できない)
        self.assertIn("共有", 一覧[0].理由)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-3
    def test_予定詳細に現れない参加者も件名を取得できないものとして返すこと(self):
        読み = self._読み([])
        一覧 = detail.枠に重なる仮の予定(読み, self.枠, ["d@example.com"])
        self.assertEqual(一覧[0].アドレス, "d@example.com")
        self.assertTrue(一覧[0].取得できない)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-2
    def test_件名が空で返った参加者は件名を取得できないものとして返すこと(self):
        読み = self._読み(
            [{"address": "b@example.com", "calendarFound": True, "events": [_予定(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 件名="")]}]
        )
        self.assertTrue(detail.枠に重なる仮の予定(読み, self.枠, ["b@example.com"])[0].取得できない)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-3
    def test_繰り返し予定は件名の取得対象にしないこと(self):
        読み = self._読み(
            [
                {
                    "address": "b@example.com",
                    "calendarFound": True,
                    "events": [_予定(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 件名="毎週の定例", isRecurring=True)],
                }
            ]
        )
        一覧 = detail.枠に重なる仮の予定(読み, self.枠, ["b@example.com"])
        self.assertEqual(一覧[0].件名一覧, [])
        self.assertTrue(一覧[0].取得できない)
        self.assertIn("繰り返し", 一覧[0].理由)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#ログ
    def test_件名を取得できた人数は画面に件名を示せる参加者だけを数えること(self):
        読み = self._読み(
            [
                {
                    "address": "b@example.com",
                    "calendarFound": True,
                    "events": [_予定(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 件名="顧客MTG")],
                },
                {  # 非公開なので件名は示せない
                    "address": "c@example.com",
                    "calendarFound": True,
                    "events": [_予定(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 件名="秘密", sensitivity="private")],
                },
                {  # 繰り返しなので件名は示せない
                    "address": "d@example.com",
                    "calendarFound": True,
                    "events": [_予定(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 件名="毎週の定例", isRecurring=True)],
                },
                {  # カレンダーが共有されていない
                    "address": "e@example.com",
                    "calendarFound": False,
                    "events": [],
                },
            ]
        )
        self.assertEqual(detail.件名を取得できた人数(読み), 1)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-2
    def test_非公開の予定は件名を返さず非公開であることだけを返すこと(self):
        読み = self._読み(
            [
                {
                    "address": "b@example.com",
                    "calendarFound": True,
                    "events": [_予定(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 件名="秘密の件名", sensitivity="private")],
                }
            ]
        )
        一覧 = detail.枠に重なる仮の予定(読み, self.枠, ["b@example.com"])
        self.assertTrue(一覧[0].非公開)
        self.assertEqual(一覧[0].件名一覧, [])
        self.assertNotIn("秘密の件名", repr(一覧[0]))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#10-予定詳細の依頼と件名の取り出しdetailpy
    def test_失敗理由が入っている予定詳細は失敗として返り件名なしで示せること(self):
        読み = self._読み([], 失敗="Calendar API failed")
        self.assertTrue(読み.失敗)
        一覧 = detail.枠に重なる仮の予定(読み, self.枠, ["b@example.com"])
        self.assertTrue(一覧[0].取得できない)

    def test_予定詳細が無い場合も件名なしで示せること(self):
        一覧 = detail.枠に重なる仮の予定(None, self.枠, ["b@example.com"])
        self.assertEqual(len(一覧), 1)
        self.assertTrue(一覧[0].取得できない)


class 予定詳細ファイルの削除(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#セキュリティ
    def test_選択結果を書き出した時点で予定詳細ファイルを削除できること(self):
        with tempfile.TemporaryDirectory() as d:
            設定 = config.load(environ={config.台帳ルート環境変数: d})
            path = Path(d, "detail", "detail-ID1.json")
            path.parent.mkdir(parents=True)
            path.write_text("{}", encoding="utf-8")
            self.assertTrue(detail.削除(設定, "ID1"))
            self.assertFalse(path.exists())
            self.assertFalse(detail.削除(設定, "ID1"))  # 無ければFalse(例外にしない)


if __name__ == "__main__":
    unittest.main()
