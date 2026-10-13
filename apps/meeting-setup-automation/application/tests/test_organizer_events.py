"""開催者の予定の依頼・読み取り・枠との突き合わせ(tasks.md 30)のテスト。

参加者全員が空きで開催者だけが空き以外の枠について、開催者自身の予定を専用フロー(開催者予定フロー)に
頼んで受け取り、どの予定がどの枠に重なるかを判断材料として整える。件名は開催者本人の情報だが、
非公開に設定した予定は伏せ、本文・出席者・場所は読まない。取得できなくても枠の提示は止めない。
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import candidates
import config
import ledger
import organizer_events

JST = timezone(timedelta(hours=9))
ID = "20260909-101500-ab3f"


def _枠(開始jst, 分=60, 開催者="busy"):
    return candidates.枠(
        開始=開始jst, 終了=開始jst + timedelta(minutes=分),
        出席者空き=[("a@example.com", "free"), ("b@example.com", "free")],
        開催者空き=開催者, 試行番号=1,
    )


def _予定(件名, 開始utc, 分=60, showAs="busy", sensitivity="normal", **余分):
    """開催者予定フローが書く形(dateTime は7桁小数・timeZone は UTC)。"""
    終了 = 開始utc + timedelta(minutes=分)
    項目 = {
        "subject": 件名, "showAs": showAs, "sensitivity": sensitivity,
        "start": {"dateTime": 開始utc.strftime("%Y-%m-%dT%H:%M:%S.0000000"), "timeZone": "UTC"},
        "end": {"dateTime": 終了.strftime("%Y-%m-%dT%H:%M:%S.0000000"), "timeZone": "UTC"},
    }
    項目.update(余分)
    return 項目


def _予定ファイル(予定一覧, 失敗="", 依頼id=ID):
    return {"requestId": 依頼id, "error": 失敗, "events": 予定一覧}


class 開催者の予定の依頼(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.設定 = config.load(environ={config.台帳ルート環境変数: self._tmp.name})

    def tearDown(self):
        self._tmp.cleanup()

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#開催者の予定の依頼ファイルの区分
    def test_枠の最小の開始から最大の終了までを世界標準時の範囲として依頼を組み立てること(self):
        依頼 = organizer_events.依頼を組み立てる(ID, [
            _枠(datetime(2026, 9, 12, 15, 0, tzinfo=JST)),
            _枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST)),
        ])
        self.assertEqual(依頼, {"requestId": ID, "rangeStart": "2026-09-10T01:00:00Z", "rangeEnd": "2026-09-12T07:00:00Z"})

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-6
    def test_枠が0件なら依頼を組み立てず書き出しもしないこと(self):
        self.assertIsNone(organizer_events.依頼を組み立てる(ID, []))
        結果 = organizer_events.依頼を書き出す(self.設定, ID, [])
        self.assertFalse(結果.ok)
        self.assertFalse(ledger.開催者の予定の依頼ファイル(self.設定, ID).exists())

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#台帳ファイルの扱い-1、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-6
    def test_依頼フォルダへ依頼IDの名前で書き出し同じ依頼IDの依頼が既にあれば書き直さないこと(self):
        枠 = [_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST))]
        結果 = organizer_events.依頼を書き出す(self.設定, ID, 枠)
        path = ledger.開催者の予定の依頼ファイル(self.設定, ID)
        self.assertTrue(結果.ok)
        self.assertFalse(結果.既にあった)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["rangeStart"], "2026-09-10T01:00:00Z")
        更新前 = path.stat().st_mtime_ns
        path.write_text(path.read_text(encoding="utf-8").replace("01:00:00Z", "00:00:00Z"), encoding="utf-8")
        結果2 = organizer_events.依頼を書き出す(self.設定, ID, [_枠(datetime(2026, 9, 11, 10, 0, tzinfo=JST))])
        self.assertTrue(結果2.ok)
        self.assertTrue(結果2.既にあった)
        self.assertIn("00:00:00Z", path.read_text(encoding="utf-8"))  # 2回目は書き直していない
        self.assertGreaterEqual(path.stat().st_mtime_ns, 更新前)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-6
    def test_書き出しに失敗しても例外を投げず失敗した旨を返すこと(self):
        設定 = config.load(environ={config.台帳ルート環境変数: str(Path(self._tmp.name, "file"))})
        Path(self._tmp.name, "file").write_text("x", encoding="utf-8")  # 台帳ルートの位置にファイルがある → 作れない
        結果 = organizer_events.依頼を書き出す(設定, ID, [_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST))])
        self.assertFalse(結果.ok)
        self.assertIn("開催者の予定の依頼を書き出せません", 結果.error)


class 開催者の予定ファイルの読み取り(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#開催者の予定ファイルの区分
    def test_予定ごとの件名と種別と非公開かどうかと開始終了を取り出し本文や出席者や場所は読まないこと(self):
        読み = organizer_events.読む(_予定ファイル([
            _予定("社内レビュー", datetime(2026, 9, 11, 5, 0, tzinfo=timezone.utc), showAs="tentative",
                body={"content": "秘密"}, attendees=[{"emailAddress": {"address": "x@example.com"}}], location={"displayName": "会議室"}),
        ]), ID)
        self.assertEqual(読み.失敗理由, "")
        self.assertEqual(len(読み.予定一覧), 1)
        予定 = 読み.予定一覧[0]
        self.assertEqual(予定.件名, "社内レビュー")
        self.assertEqual(予定.種別, "tentative")
        self.assertFalse(予定.非公開)
        self.assertEqual(予定.開始, datetime(2026, 9, 11, 5, 0, tzinfo=timezone.utc))
        self.assertEqual(予定.終了, datetime(2026, 9, 11, 6, 0, tzinfo=timezone.utc))
        for 読まない項目 in ("本文", "出席者", "場所", "body", "attendees", "location"):
            self.assertFalse(hasattr(予定, 読まない項目))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#開催者の予定ファイルの区分
    def test_失敗理由が入っていれば失敗として返し予定は空であること(self):
        読み = organizer_events.読む(_予定ファイル([_予定("x", datetime(2026, 9, 11, 5, 0, tzinfo=timezone.utc))], 失敗="Connector failed"), ID)
        self.assertEqual(読み.失敗理由, "Connector failed")
        self.assertEqual(読み.予定一覧, [])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#バリデーション
    def test_依頼IDが一致しないファイルは受け付けず理由を返すこと(self):
        読み = organizer_events.読む(_予定ファイル([], 依頼id="other"), ID)
        self.assertNotEqual(読み.失敗理由, "")
        self.assertIn("依頼ID", 読み.失敗理由)
        self.assertEqual(読み.予定一覧, [])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#バリデーション
    def test_知らない種別と非公開の値は不明と件名そのままとして読むこと(self):
        読み = organizer_events.読む(_予定ファイル([
            _予定("謎", datetime(2026, 9, 11, 5, 0, tzinfo=timezone.utc), showAs="weird", sensitivity="odd"),
            {"subject": "欠け", "start": {"dateTime": "2026-09-11T05:00:00Z"}, "end": {"dateTime": "2026-09-11T06:00:00Z"}},
        ]), ID)
        self.assertEqual(organizer_events.種別の表示語(読み.予定一覧[0].種別), "不明")
        self.assertFalse(読み.予定一覧[0].非公開)
        self.assertEqual(読み.予定一覧[1].件名, "欠け")
        self.assertEqual(organizer_events.種別の表示語(読み.予定一覧[1].種別), "不明")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#開催者の予定ファイルの区分
    def test_開始か終了が読めない予定は飛ばして残りを読むこと(self):
        読み = organizer_events.読む(_予定ファイル([
            {"subject": "壊れ", "showAs": "busy", "start": {"dateTime": ""}, "end": {}},
            _予定("正常", datetime(2026, 9, 11, 5, 0, tzinfo=timezone.utc)),
        ]), ID)
        self.assertEqual([p.件名 for p in 読み.予定一覧], ["正常"])


class 開催者の予定ファイルの受け付け(unittest.TestCase):
    """待つ側は、依頼IDが一致して `events` が配列として読める(または失敗理由が入っている)ファイルだけを
    「届いた」とみなし、それ以外は途中まで書かれているのと同じく「まだ来ていない」として待ち続ける
    (design.md#バリデーション)。
    """

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#バリデーション
    def test_依頼IDが一致しeventsが配列のファイルと失敗理由入りのファイルだけを受け付けること(self):
        """否定確認: `events` の配列判定を外すと、`events` が文字列のファイルを受け付けて落ちる。"""
        self.assertTrue(organizer_events.受け付けられる(_予定ファイル([]), ID))
        self.assertTrue(organizer_events.受け付けられる(_予定ファイル([], 失敗="Connector failed"), ID))
        self.assertTrue(organizer_events.受け付けられる({"requestId": ID, "error": "x"}, ID))  # 失敗時は events が無くてもよい
        self.assertFalse(organizer_events.受け付けられる(_予定ファイル([], 依頼id="other"), ID))
        self.assertFalse(organizer_events.受け付けられる({"requestId": ID, "error": "", "events": "まだ"}, ID))
        self.assertFalse(organizer_events.受け付けられる({"requestId": ID, "error": ""}, ID))
        self.assertFalse(organizer_events.受け付けられる(["not", "a", "dict"], ID))
        self.assertFalse(organizer_events.受け付けられる(None, ID))


class 枠と予定の突き合わせ(unittest.TestCase):

    def setUp(self):
        self.枠 = _枠(datetime(2026, 9, 11, 14, 0, tzinfo=JST), 開催者="tentative")  # 05:00〜06:00 UTC
        self.予定一覧 = organizer_events.読む(_予定ファイル([
            _予定("前にある", datetime(2026, 9, 11, 3, 0, tzinfo=timezone.utc), 分=120),           # 03:00〜05:00 接するだけ
            _予定("部分的に重なる", datetime(2026, 9, 11, 5, 30, tzinfo=timezone.utc), 分=60),      # 05:30〜06:30
            _予定("空きの予定", datetime(2026, 9, 11, 5, 0, tzinfo=timezone.utc), showAs="free"),  # 重なるが free
            _予定("定例(第1回)", datetime(2026, 9, 11, 5, 0, tzinfo=timezone.utc), 分=30, showAs="tentative"),
            _予定("定例(第2回)", datetime(2026, 9, 18, 5, 0, tzinfo=timezone.utc), 分=30, showAs="tentative"),
            _予定("後にある", datetime(2026, 9, 11, 6, 0, tzinfo=timezone.utc)),                  # 06:00〜 接するだけ
        ]), ID).予定一覧

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#決定事項、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-9
    def test_世界標準時で開始が枠の終了より前かつ終了が枠の開始より後の予定だけが重なりfreeは除き回ごとに個別に突き合わせること(self):
        """否定確認: 比較の不等号を `<=` にすると「前にある」「後にある」が重なりに入って落ちる。"""
        重なり = organizer_events.重なる予定(self.枠, self.予定一覧)
        self.assertEqual([p.件名 for p in 重なり], ["定例(第1回)", "部分的に重なる"])  # 開始時刻順

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-10
    def test_表示の行は件名と日本時間の開始終了と種別の表示語を並べること(self):
        行 = organizer_events.枠の表示行(self.枠, self.予定一覧)
        self.assertEqual(行, ["定例(第1回) 14:00〜14:30(仮)", "部分的に重なる 14:30〜15:30(予約済み)"])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-5
    def test_非公開の予定は件名の代わりに非公開の予定と示すこと(self):
        予定一覧 = organizer_events.読む(_予定ファイル([
            _予定("病院", datetime(2026, 9, 11, 5, 0, tzinfo=timezone.utc), sensitivity="private"),
            _予定("人事面談", datetime(2026, 9, 11, 5, 0, tzinfo=timezone.utc), sensitivity="confidential"),
            _予定("個人的", datetime(2026, 9, 11, 5, 0, tzinfo=timezone.utc), sensitivity="personal"),
        ]), ID).予定一覧
        行 = organizer_events.枠の表示行(self.枠, 予定一覧)
        self.assertEqual(行, ["非公開の予定 14:00〜15:00(予約済み)", "非公開の予定 14:00〜15:00(予約済み)", "個人的 14:00〜15:00(予約済み)"])
        self.assertNotIn("病院", "".join(行))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#決定事項
    def test_種別の表示語はOutlookの表示と同じ語でそれ以外は不明であること(self):
        self.assertEqual(
            [organizer_events.種別の表示語(v) for v in ("tentative", "busy", "oof", "workingElsewhere", "unknown", "", "free")],
            ["仮", "予約済み", "外出中", "他の場所で作業中", "不明", "不明", "空き"],
        )

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#開催者の予定のみ重なる枠の提示
    def test_枠の日と異なる日付にかかる予定は日付も添えること(self):
        予定一覧 = organizer_events.読む(_予定ファイル([
            _予定("終日の出張", datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc), 分=24 * 60, showAs="oof"),  # 9/11 0:00〜9/12 0:00 JST
        ]), ID).予定一覧
        行 = organizer_events.枠の表示行(self.枠, 予定一覧)
        self.assertEqual(行, ["終日の出張 09/11 00:00〜09/12 00:00(外出中)"])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#開催者の予定のみ重なる枠の提示
    def test_重なる予定が1件も無い枠は見つからなかったことと開催者の空き状況を示し提示は止めないこと(self):
        枠 = _枠(datetime(2026, 9, 30, 14, 0, tzinfo=JST), 開催者="unknown")
        self.assertEqual(organizer_events.枠の表示行(枠, self.予定一覧), ["重なる予定は見つかりませんでした(空き状況: 不明)"])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-12、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-6
    def test_取得できなかったときは件名の代わりに取得できなかったことと理由の行になること(self):
        理由 = organizer_events.理由_待ち上限(300)
        self.assertEqual(理由, "待ち上限(5分)を超えました")
        self.assertEqual(organizer_events.枠の表示行(self.枠, None, 理由), ["開催者の予定を取得できませんでした(待ち上限(5分)を超えました)"])
        self.assertEqual(organizer_events.理由_フロー失敗("Connector failed"), "開催者予定フローが失敗を返しました: Connector failed")
        self.assertEqual(organizer_events.理由_書き出し失敗("disk full"), "開催者の予定の依頼を書き出せませんでした: disk full")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-9
    def test_通知とチャット用の1行は日付と曜日と枠の時刻のあとに予定の行を読点でつなぐこと(self):
        行 = organizer_events.通知の行(self.枠, organizer_events.枠の表示行(self.枠, self.予定一覧))
        self.assertEqual(行, "・09/11(金) 14:00〜15:00 — 定例(第1回) 14:00〜14:30(仮)、部分的に重なる 14:30〜15:30(予約済み)")


if __name__ == "__main__":
    unittest.main()
