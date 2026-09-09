"""作成結果の読み取りと会議オプション画面の直リンクの取り出し(tasks.md 15)のテスト。

作成フローは会議本文をそのまま渡し、直リンクの取り出しはSkillが行う。本文に直リンクが
無い場合は失敗ではなく「取り出せなかった」として扱う(会議自体は作成できている)。
"""

import unittest
from datetime import datetime, timedelta, timezone

import result

JST = timezone(timedelta(hours=9))

直リンク = (
    "https://teams.microsoft.com/meetingOptions/?organizerId=0000-1111&tenantId=2222-3333"
    "&threadId=19_meeting_abc@thread.v2&messageId=0&language=ja-JP"
)


def _作成結果(本文, 失敗="", **上書き):
    内容 = {
        "requestId": "ID1",
        "retry": 0,
        "error": 失敗,
        "event": {
            "id": "AAMkAGI=",
            "subject": "定例",
            "start": {"dateTime": "2026-09-10T10:00:00.0000000", "timeZone": "Tokyo Standard Time"},
            "end": {"dateTime": "2026-09-10T11:00:00.0000000", "timeZone": "Tokyo Standard Time"},
            "attendees": [
                {"emailAddress": {"address": "a@example.com", "name": "A"}, "type": "required"},
                {"emailAddress": {"address": "b@example.com", "name": "B"}, "type": "required"},
            ],
            "onlineMeeting": {"joinUrl": "https://teams.microsoft.com/l/meetup-join/19%3ameeting_abc%40thread.v2/0"},
            "webLink": "https://outlook.office365.com/owa/?itemid=AAMkAGI%3D",
            "body": {"contentType": "html", "content": 本文},
        },
    }
    内容.update(上書き)
    return 内容


class 作成結果の読み取り(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議の作成-3
    def test_会議の識別子と件名と開始終了と出席者と参加URLと会議本文を取り出せること(self):
        r = result.読む(_作成結果(f'<p>アジェンダ</p><a href="{直リンク}">会議のオプション</a>'))
        self.assertFalse(r.失敗)
        self.assertEqual(r.依頼id, "ID1")
        self.assertEqual(r.再試行番号, 0)
        self.assertEqual(r.会議id, "AAMkAGI=")
        self.assertEqual(r.件名, "定例")
        self.assertEqual(r.開始, datetime(2026, 9, 10, 10, 0, tzinfo=JST))
        self.assertEqual(r.終了, datetime(2026, 9, 10, 11, 0, tzinfo=JST))
        self.assertEqual(r.出席者, ["A <a@example.com>", "B <b@example.com>"])
        self.assertTrue(r.参加url.startswith("https://teams.microsoft.com/l/meetup-join/"))
        self.assertIn("アジェンダ", r.会議本文)

    def test_世界標準時で返った開始終了は日本時間に変換されること(self):
        内容 = _作成結果("")
        内容["event"]["start"] = {"dateTime": "2026-09-10T01:00:00.0000000", "timeZone": "UTC"}
        self.assertEqual(result.読む(内容).開始, datetime(2026, 9, 10, 10, 0, tzinfo=JST))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議の作成-5
    def test_失敗理由が入っている作成結果は失敗として返ること(self):
        r = result.読む({"requestId": "ID1", "retry": 1, "error": "ErrorAccessDenied", "event": None})
        self.assertTrue(r.失敗)
        self.assertEqual(r.失敗理由, "ErrorAccessDenied")
        self.assertEqual(r.再試行番号, 1)


class 会議オプション画面の直リンク(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#録画とファシリテーターの設定-2
    def test_会議本文から会議オプション画面のURLを機械的に取り出せること(self):
        本文 = f'<div>...<a href="{直リンク}" target="_blank">会議のオプション</a> | <a href="https://aka.ms/x">法的情報</a></div>'
        self.assertEqual(result.会議オプション直リンク(本文), 直リンク)

    def test_本文でエスケープされたアンパサンドを元に戻して取り出すこと(self):
        本文 = f'<a href="{直リンク.replace("&", "&amp;")}">会議のオプション</a>'
        self.assertEqual(result.会議オプション直リンク(本文), 直リンク)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#15-作成結果の読み取りと直リンクの取り出しresultpy
    def test_URLが複数見つかる場合は最初のものを使うこと(self):
        本文 = f'<a href="{直リンク}">1</a><a href="{直リンク.replace("abc", "def")}">2</a>'
        self.assertEqual(result.会議オプション直リンク(本文), 直リンク)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#録画とファシリテーターの設定-3
    def test_それらしいURLが無い場合は失敗とせず取り出せなかったとしてNoneを返すこと(self):
        self.assertIsNone(result.会議オプション直リンク("<p>本文だけ</p>"))
        self.assertIsNone(result.会議オプション直リンク(""))
        self.assertIsNone(result.会議オプション直リンク(None))


if __name__ == "__main__":
    unittest.main()
