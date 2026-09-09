"""貼られた選択結果の読み取り・突き合わせ・書き出しとアジェンダの整形(tasks.md 13・14)のテスト。

開催者がチャットに貼った1行を候補ファイルと突き合わせてから選択結果を書き出す。候補ファイルの
枠は世界標準時、貼られた時刻は日本時間なので時点として比較する。同じ依頼IDの選択結果は
1つの再試行番号につき1回しか書き出さず、作成に成功した依頼には書き出さない。
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
import ledger
import selection
from tests.test_candidates import _候補ファイル, _枠

JST = timezone(timedelta(hours=9))
行 = "MEETING-SELECT 20260909-101500-ab3f a1 #2 2026-09-10T10:00:00+09:00 2026-09-10T11:00:00+09:00"


class 貼られた行の読み取り(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の選択-3
    def test_目印の語と依頼IDと試行番号と候補番号と開始終了を読み取れること(self):
        結果 = selection.読み取る(行)
        self.assertEqual(結果.依頼id, "20260909-101500-ab3f")
        self.assertEqual(結果.試行番号, 1)
        self.assertEqual(結果.候補番号, 2)
        self.assertEqual(結果.開始, datetime(2026, 9, 10, 10, 0, tzinfo=JST))
        self.assertEqual(結果.終了, datetime(2026, 9, 10, 11, 0, tzinfo=JST))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#13-貼られた選択結果の読み取りと書き出しselectionpy
    def test_前後に余分な文字があっても目印の語を起点に読み取れること(self):
        結果 = selection.読み取る(f"これでお願いします。\n{行}\nよろしく")
        self.assertEqual(結果.候補番号, 2)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の選択-4
    def test_目印の語がない場合や項目が欠けている場合は読み取れなかったことを返すこと(self):
        self.assertIsNone(selection.読み取る("20260909-101500-ab3f a1 #2 2026-09-10T10:00:00+09:00"))
        self.assertIsNone(selection.読み取る("MEETING-SELECT 20260909-101500-ab3f a1 #2"))
        self.assertIsNone(selection.読み取る(""))


class 候補ファイルとの突き合わせ(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.設定 = config.load(environ={config.台帳ルート環境変数: self._tmp.name})
        self.id = "20260909-101500-ab3f"
        ledger.write_json(
            ledger.候補ファイル(self.設定, self.id, 1),
            _候補ファイル([_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST)), _枠(datetime(2026, 9, 11, 14, 0, tzinfo=JST))]),
        )

    def tearDown(self):
        self._tmp.cleanup()

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#13-貼られた選択結果の読み取りと書き出しselectionpy
    def test_候補ファイルの枠は世界標準時で貼られた時刻は日本時間なので時点として比較して一致すること(self):
        結果 = selection.突き合わせる(self.設定, selection.読み取る(行))
        self.assertTrue(結果.ok)
        self.assertEqual(結果.枠.開始, datetime(2026, 9, 10, 10, 0, tzinfo=JST))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の選択-4
    def test_一致する枠が無い場合は書き出さずに理由を返すこと(self):
        別の枠 = 行.replace("2026-09-10T10:00:00+09:00", "2026-09-10T09:00:00+09:00").replace("2026-09-10T11:00:00+09:00", "2026-09-10T10:00:00+09:00")
        結果 = selection.突き合わせる(self.設定, selection.読み取る(別の枠))
        self.assertFalse(結果.ok)
        self.assertIn("一致", 結果.error)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#13-貼られた選択結果の読み取りと書き出しselectionpy
    def test_突き合わせに候補番号を使わないこと(self):
        番号違い = 行.replace("#2", "#9")
        self.assertTrue(selection.突き合わせる(self.設定, selection.読み取る(番号違い)).ok)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#13-貼られた選択結果の読み取りと書き出しselectionpy
    def test_貼られた試行番号の候補ファイルを見ること(self):
        ledger.write_json(
            ledger.候補ファイル(self.設定, self.id, 2),
            _候補ファイル([_枠(datetime(2026, 9, 25, 18, 0, tzinfo=JST))], 試行=2),
        )
        代替2の行 = "MEETING-SELECT 20260909-101500-ab3f a2 #3 2026-09-25T18:00:00+09:00 2026-09-25T19:00:00+09:00"
        self.assertTrue(selection.突き合わせる(self.設定, selection.読み取る(代替2の行)).ok)
        # 試行番号1のファイルにはこの枠は無い
        self.assertFalse(selection.突き合わせる(self.設定, selection.読み取る(代替2の行.replace(" a2 ", " a1 "))).ok)

    def test_候補ファイルが無い場合は一致しないものとして返すこと(self):
        結果 = selection.突き合わせる(self.設定, selection.読み取る(行.replace("ab3f", "zzzz")))
        self.assertFalse(結果.ok)


class 選択結果の書き出し(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.設定 = config.load(environ={config.台帳ルート環境変数: self._tmp.name})
        self.id = "ID1"
        self.依頼 = {
            "requestId": self.id, "attempt": 1,
            "meeting": {
                "subject": "定例", "durationMinutes": 60,
                "attendees": [{"emailAddress": {"address": "a@example.com", "name": "A"}, "type": "required"}],
                "agenda": "- 進捗\n- 課題",
            },
        }
        ledger.write_json(ledger.依頼ファイル(self.設定, self.id, 1), self.依頼)
        self.枠 = _枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST))
        import candidates
        self.読み枠 = candidates.読む(_候補ファイル([self.枠])).枠一覧[0]

    def tearDown(self):
        self._tmp.cleanup()

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議の作成-1、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議の作成内容-2、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議の作成内容-3
    def test_選択結果は単体で会議を作れる内容でTeams会議として作る指定を含み会議室を含まないこと(self):
        内容 = selection.選択結果を組み立てる(self.依頼, self.読み枠)
        ev = 内容["meeting"]
        self.assertEqual(内容["requestId"], "ID1")
        self.assertEqual(内容["retry"], 0)
        self.assertEqual(ev["subject"], "定例")
        # 台帳の日時はオフセット付き。フロー側で末尾を落として timeZone と組み合わせる
        self.assertEqual(ev["start"], "2026-09-10T10:00:00+09:00")
        self.assertEqual(ev["end"], "2026-09-10T11:00:00+09:00")
        self.assertEqual(ev["timeZone"], "Tokyo Standard Time")
        self.assertEqual(ev["attendees"], self.依頼["meeting"]["attendees"])
        self.assertTrue(all(a["type"] == "required" for a in ev["attendees"]))
        self.assertTrue(ev["isOnlineMeeting"])
        self.assertEqual(ev["onlineMeetingProvider"], "teamsForBusiness")
        self.assertIn("進捗", ev["bodyHtml"])
        self.assertNotIn("location", ev)
        self.assertNotIn("locations", ev)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の選択-3
    def test_選択結果フォルダへselection_依頼IDの名前で書き出されること(self):
        判定 = selection.書き出せるか(self.設定, self.id)
        self.assertEqual(判定.種別, selection.書き出せる)
        結果 = selection.書き出す(self.設定, selection.選択結果を組み立てる(self.依頼, self.読み枠))
        self.assertTrue(結果.ok)
        path = Path(self._tmp.name, "selection", "selection-ID1.json")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["requestId"], "ID1")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の選択-5
    def test_その依頼IDの選択結果が既にある場合は書き出さないこと(self):
        ledger.write_json(ledger.選択結果ファイル(self.設定, self.id, 0), {"requestId": self.id})
        判定 = selection.書き出せるか(self.設定, self.id)
        self.assertEqual(判定.種別, selection.選択結果あり)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議の作成-4
    def test_作成に成功した作成結果がある依頼IDでは書き出さず作成済みとして返すこと(self):
        ledger.write_json(ledger.選択結果ファイル(self.設定, self.id, 0), {"requestId": self.id})
        ledger.write_json(ledger.作成結果ファイル(self.設定, self.id, 0), {"requestId": self.id, "error": "", "event": {}})
        判定 = selection.書き出せるか(self.設定, self.id)
        self.assertEqual(判定.種別, selection.作成済み)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議の作成-5
    def test_失敗した作成結果がある依頼IDは再試行として書き出せる状態を返し自動では書き出さないこと(self):
        ledger.write_json(ledger.選択結果ファイル(self.設定, self.id, 0), {"requestId": self.id, "retry": 0, "meeting": {"subject": "定例"}})
        ledger.write_json(ledger.作成結果ファイル(self.設定, self.id, 0), {"requestId": self.id, "error": "Forbidden"})
        判定 = selection.書き出せるか(self.設定, self.id)
        self.assertEqual(判定.種別, selection.作成失敗)
        self.assertEqual(判定.再試行番号, 0)
        self.assertEqual(判定.失敗理由, "Forbidden")
        self.assertFalse(ledger.選択結果ファイル(self.設定, self.id, 1).exists())

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の選択-5、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議の作成-5
    def test_再試行として書き出す場合は再試行番号を1つ増やした名前に前回と同じ内容を書くこと(self):
        前回 = {"requestId": self.id, "retry": 0, "meeting": {"subject": "定例"}}
        ledger.write_json(ledger.選択結果ファイル(self.設定, self.id, 0), 前回)
        ledger.write_json(ledger.作成結果ファイル(self.設定, self.id, 0), {"requestId": self.id, "error": "Forbidden"})
        結果 = selection.再試行を書き出す(self.設定, self.id)
        self.assertTrue(結果.ok)
        書いた = json.loads(Path(self._tmp.name, "selection", "selection-ID1-r1.json").read_text(encoding="utf-8"))
        self.assertEqual(書いた["retry"], 1)
        self.assertEqual(書いた["meeting"], 前回["meeting"])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議の作成-5
    def test_失敗した作成結果が無い依頼IDには再試行を書き出さないこと(self):
        ledger.write_json(ledger.選択結果ファイル(self.設定, self.id, 0), {"requestId": self.id})
        結果 = selection.再試行を書き出す(self.設定, self.id)
        self.assertFalse(結果.ok)
        self.assertFalse(ledger.選択結果ファイル(self.設定, self.id, 1).exists())


class アジェンダの整形(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議の作成-2
    def test_箇条書きの記号を項目として扱い見出しと箇条書きのHTMLにすること(self):
        html = selection.アジェンダを整形("今回の議題\n- 進捗確認\n・ 課題の共有\n1. 次回日程")
        self.assertIn("<h3>アジェンダ</h3>", html)
        self.assertIn("<p>今回の議題</p>", html)
        self.assertIn("<li>進捗確認</li>", html)
        self.assertIn("<li>課題の共有</li>", html)
        self.assertIn("<li>次回日程</li>", html)
        self.assertEqual(html.count("<ul>"), 1)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#依頼内容の受け付け条件-6
    def test_アジェンダが空の場合は本文を空にせずアジェンダが無いことが分かる本文にすること(self):
        html = selection.アジェンダを整形("")
        self.assertTrue(html.strip())
        self.assertIn("アジェンダ", html)
        self.assertIn("未", html)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#14-アジェンダの整形selectionpy
    def test_HTMLとして解釈されうる文字をエスケープすること(self):
        html = selection.アジェンダを整形("- <b>太字</b> & co")
        self.assertNotIn("<b>", html)
        self.assertIn("&lt;b&gt;", html)
        self.assertIn("&amp;", html)


if __name__ == "__main__":
    unittest.main()
