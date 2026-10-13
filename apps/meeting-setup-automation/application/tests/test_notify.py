"""通知文の組み立てと通知フォルダへの書き出し(tasks.md 16)のテスト。

Teams通知は通知フォルダへのファイル書き出しで行い、HTTPで直接投稿する経路は持たない
(組織のDLPポリシーでブロックされる)。通知の書き出しが失敗しても例外にせず、チャットへの
表示で処理を続けられるようにする。
"""

import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
import notify
import result

JST = timezone(timedelta(hours=9))


class 選択画面の通知文(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-5
    def test_件名と候補件数と選択画面のURLと開けない場合の再読込の案内が含まれること(self):
        文 = notify.選択画面の通知文("定例", 3, "https://example/viewer?id=x", None)
        self.assertIn("定例", 文)
        self.assertIn("3件", 文)
        self.assertIn("https://example/viewer?id=x", 文)
        self.assertIn("再読込", 文)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#通知-3
    def test_URLが組み立てられない場合は選択画面のファイルパスを載せること(self):
        文 = notify.選択画面の通知文("定例", 3, None, "/ledger/html/select-ID1.html")
        self.assertIn("select-ID1.html", 文)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-9
    def test_開催者の予定のみ重なる枠の件数と枠ごとの行が含まれ0件なら見出しも行も含めないこと(self):
        """否定確認: 件数が0でも見出しを出すように変えると、後半の assertNotIn で落ちる。"""
        枠 = notify.開催者の枠の要約(件数=2, 行一覧=[
            "・09/11(金) 16:00〜17:00 — 社内レビュー 16:00〜16:30(仮)、非公開の予定 16:30〜17:00(予約済み)",
            "・09/12(土) 10:00〜11:00 — 開催者の予定を取得できませんでした(待ち上限(5分)を超えました)",
        ])
        文 = notify.選択画面の通知文("定例", 3, "https://example/v", None, 開催者の枠=枠)
        self.assertIn("開催者の予定のみ重なる枠: 2件(自分の予定を調整すれば開けられる枠)", 文)
        self.assertIn("・09/11(金) 16:00〜17:00 — 社内レビュー 16:00〜16:30(仮)、非公開の予定 16:30〜17:00(予約済み)", 文)
        self.assertIn("開催者の予定を取得できませんでした(待ち上限(5分)を超えました)", 文)
        self.assertLess(文.index("候補: 3件"), 文.index("開催者の予定のみ重なる枠"))
        self.assertLess(文.index("開催者の予定のみ重なる枠"), 文.index("選択画面:"))
        無し = notify.選択画面の通知文("定例", 3, "https://example/v", None, 開催者の枠=None)
        self.assertNotIn("開催者の予定のみ重なる枠", 無し)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-8
    def test_代替案を提示する通知文にも同じ見出しと行が含まれ両方0件のときは選択画面のURLと相談の文面の両方が含まれること(self):
        枠 = notify.開催者の枠の要約(件数=1, 行一覧=["・09/11(金) 16:00〜17:00 — 社内レビュー 16:00〜17:00(仮)"])
        代替 = notify.代替案の要約(代替案1件数=1, 代替案1の仮の予定=[], 代替案2件数=1, 代替案2の条件="c2", 代替案2が得られなかった理由="", 打ち切りの可能性=False)
        文 = notify.選択画面の通知文("定例", 2, "https://example/v", None, 代替, 開催者の枠=枠)
        self.assertIn("代替案1", 文)
        self.assertIn("開催者の予定のみ重なる枠: 1件", 文)
        両方0件 = notify.代替案の要約(代替案1件数=0, 代替案1の仮の予定=[], 代替案2件数=0, 代替案2の条件="c2", 代替案2が得られなかった理由="", 打ち切りの可能性=False)
        相談 = ["候補が見つかりませんでした。試した条件:", "- 既定の条件: c0", "参加者・期間・所要時間のどれを緩めるかを決めて、`submit` で依頼し直してください。"]
        文2 = notify.選択画面の通知文("定例", 0, "https://example/v", None, 両方0件, 開催者の枠=枠, 相談=相談)
        self.assertIn("https://example/v", 文2)
        self.assertIn("参加者・期間・所要時間のどれを緩めるか", 文2)
        self.assertIn("開催者の予定のみ重なる枠: 1件", 文2)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#セキュリティ
    def test_通知文に予定の本文や出席者や場所に当たる内容が含まれないこと(self):
        """行は organizer_events が件名・時刻・種別だけから組み立てるので、本文などは渡りようがないことを確かめる。"""
        import organizer_events
        from tests.test_organizer_events import _予定, _予定ファイル, _枠 as _開催者枠
        枠 = _開催者枠(datetime(2026, 9, 11, 16, 0, tzinfo=JST))
        読み = organizer_events.読む(_予定ファイル([
            _予定("社内レビュー", datetime(2026, 9, 11, 7, 0, tzinfo=timezone.utc), body={"content": "本文は秘密"},
                attendees=[{"emailAddress": {"address": "x@example.com"}}], location={"displayName": "第3会議室"}),
        ]), "20260909-101500-ab3f")
        行 = organizer_events.通知の行(枠, organizer_events.枠の表示行(枠, 読み.予定一覧))
        文 = notify.選択画面の通知文("定例", 0, "https://example/v", None, 開催者の枠=notify.開催者の枠の要約(件数=1, 行一覧=[行]))
        self.assertIn("社内レビュー", 文)
        for 出してはいけない in ("本文は秘密", "x@example.com", "第3会議室"):
            self.assertNotIn(出してはいけない, 文)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-8、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-2
    def test_代替案の提示では既定で0件だったことと各代替案の件数と仮の予定と広げた条件が含まれること(self):
        代替 = notify.代替案の要約(
            代替案1件数=2,
            代替案1の仮の予定=["候補1 2026-09-10 10:00〜11:00: 山田 太郎: 顧客MTG", "候補2 2026-09-11 14:00〜15:00: 鈴木 花子: (非公開の予定)"],
            代替案2件数=1,
            代替案2の条件="期間 2026-09-09〜2026-09-30、時間帯 09:30〜18:30",
            代替案2が得られなかった理由="",
            打ち切りの可能性=False,
        )
        文 = notify.選択画面の通知文("定例", 3, "https://example/v", None, 代替)
        self.assertIn("既定の条件では候補が0件", 文)
        self.assertIn("代替案1", 文)
        self.assertIn("2件", 文)
        self.assertIn("山田 太郎: 顧客MTG", 文)
        self.assertIn("(非公開の予定)", 文)
        self.assertIn("代替案2", 文)
        self.assertIn("2026-09-30", 文)
        self.assertIn("18:30", 文)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち合わせ-5
    def test_代替案2が得られなかった場合はその理由が含まれ代替案2を作らなかった場合はその旨が含まれること(self):
        代替 = notify.代替案の要約(代替案1件数=1, 代替案1の仮の予定=[], 代替案2件数=None,
                             代替案2の条件="", 代替案2が得られなかった理由="待ち上限(300秒)を超えて打ち切りました", 打ち切りの可能性=False)
        文 = notify.選択画面の通知文("定例", 1, "https://example/v", None, 代替)
        self.assertIn("打ち切り", 文)
        代替2 = notify.代替案の要約(代替案1件数=1, 代替案1の仮の予定=[], 代替案2件数=None,
                              代替案2の条件="", 代替案2が得られなかった理由="", 打ち切りの可能性=False,
                              広げなかった項目=["期間", "時間帯"])
        文2 = notify.選択画面の通知文("定例", 1, "https://example/v", None, 代替2)
        self.assertIn("代替案2は作りませんでした", 文2)
        self.assertIn("期間", 文2)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-7
    def test_応答が件数で打ち切られている可能性を伝えられること(self):
        代替 = notify.代替案の要約(代替案1件数=0, 代替案1の仮の予定=[], 代替案2件数=1, 代替案2の条件="c",
                             代替案2が得られなかった理由="", 打ち切りの可能性=True)
        文 = notify.選択画面の通知文("定例", 1, "https://example/v", None, 代替)
        self.assertIn("件数で打ち切られている可能性", 文)


class 完了の通知文(unittest.TestCase):

    def setUp(self):
        self.結果 = result.作成結果(
            依頼id="ID1", 再試行番号=0, 失敗理由="", 会議id="AAMk", 件名="定例",
            開始=datetime(2026, 9, 10, 10, 0, tzinfo=JST), 終了=datetime(2026, 9, 10, 11, 0, tzinfo=JST),
            出席者=["A <a@example.com>", "B <b@example.com>"],
            参加url="https://teams.microsoft.com/l/meetup-join/x", 会議本文="", 開くリンク="https://outlook.office365.com/owa/?itemid=x",
        )

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#完了の通知-1、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#完了の通知-2
    def test_会議の日時と出席者と参加URLと直リンクと手動有効化の注意書きが含まれること(self):
        文 = notify.完了の通知文(self.結果, "https://teams.microsoft.com/meetingOptions/?x=1")
        self.assertIn("2026-09-10", 文)
        self.assertIn("10:00", 文)
        self.assertIn("11:00", 文)
        self.assertIn("A <a@example.com>", 文)
        self.assertIn("https://teams.microsoft.com/l/meetup-join/x", 文)
        self.assertIn("https://teams.microsoft.com/meetingOptions/?x=1", 文)
        self.assertIn("録画", 文)
        self.assertIn("ファシリテーター", 文)
        self.assertIn("手動", 文)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#録画とファシリテーターの設定-3
    def test_直リンクが取り出せなかった場合はその旨とTeamsのカレンダーから会議オプションを開く手順が含まれること(self):
        文 = notify.完了の通知文(self.結果, None)
        self.assertIn("取り出せ", 文)
        self.assertIn("カレンダー", 文)
        self.assertIn("会議のオプション", 文)
        self.assertNotIn("失敗", 文)


class 通知フォルダへの書き出し(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#通知-1、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#台帳ファイルの扱い-4
    def test_通知フォルダへmeeting_書き出し時刻の一意な名前で書き出し台帳フォルダとは別であること(self):
        with tempfile.TemporaryDirectory() as d:
            設定 = config.load(environ={config.台帳ルート環境変数: f"{d}/ledger", config.通知フォルダ環境変数: f"{d}/notice"})
            今 = datetime(2026, 9, 9, 10, 15, 0, tzinfo=JST)
            r1 = notify.書き出す(設定, "本文1", 今=今)
            r2 = notify.書き出す(設定, "本文2", 今=今)
            self.assertTrue(r1.ok and r2.ok)
            self.assertNotEqual(r1.path, r2.path)
            for p in (r1.path, r2.path):
                self.assertRegex(Path(p).name, r"^meeting-20260909-101500(-\d+)?\.txt$")
                self.assertEqual(Path(p).parent, Path(d, "notice"))
            self.assertFalse(Path(d, "ledger").exists())

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#通知-3
    def test_書き出しに失敗しても例外を投げず失敗した旨を返すこと(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "notice").write_text("x", encoding="utf-8")
            設定 = config.load(environ={config.通知フォルダ環境変数: f"{d}/notice"})
            r = notify.書き出す(設定, "本文")
        self.assertFalse(r.ok)
        self.assertIn("通知", r.error)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#通知-2
    def test_HTTPで直接投稿する経路を持たないこと(self):
        原文 = Path(notify.__file__).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"urllib\.request|http\.client|import requests|webhook", 原文, re.IGNORECASE))


class 通知本文のHTML化(unittest.TestCase):
    """通知フローがTeamsへ渡す本文はHTML断片として描画される。改行をそのまま書くと1行に
    潰れ、URLはクリックできず、山括弧を含む値はタグとみなされて消える。書き出しの直前に
    HTMLへ組み替え、チャットに出す文はプレーンのまま保つ。
    """

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#通知-1
    def test_改行がbrになりURLがリンクになること(self):
        html = notify.html断片にする("【会議候補が出そろいました】\n選択画面: https://example.com/v?id=1&x=2")
        self.assertIn("【会議候補が出そろいました】<br>選択画面: ", html)
        self.assertIn('<a href="https://example.com/v?id=1&amp;x=2">https://example.com/v?id=1&amp;x=2</a>', html)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#通知-1
    def test_山括弧を含む値がタグとして解釈されずそのまま読めること(self):
        html = notify.html断片にする("件名: 定例 <確認>\n出席者: 山田 太郎 <taro@example.com>")
        self.assertIn("定例 &lt;確認&gt;", html)
        self.assertIn("山田 太郎 &lt;taro@example.com&gt;", html)
        self.assertNotIn("<確認>", html)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-8
    def test_仮の予定の字下げが潰れないこと(self):
        html = notify.html断片にする("- 代替案1(仮の予定を含める): 2件\n    候補1: 山田 太郎: 顧客MTG")
        self.assertIn("&nbsp;&nbsp;&nbsp;&nbsp;候補1: 山田 太郎: 顧客MTG", html)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#通知-1
    def test_文の途中に現れたURLが後ろの日本語や句点を巻き込まないこと(self):
        html = notify.html断片にする("理由: https://example.com/run/123。次を確認してください")
        self.assertIn('<a href="https://example.com/run/123">https://example.com/run/123</a>', html)
        self.assertIn("</a>。次を確認してください", html)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#通知-3
    def test_チャットに出す通知文はプレーンなまま組み立てられること(self):
        文 = notify.選択画面の通知文("定例 <確認>", 1, "https://example.com/v", None)
        self.assertIn("定例 <確認>", 文)
        self.assertNotIn("<br>", 文)
        self.assertNotIn("<a href", 文)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#通知-1
    def test_書き出すファイルの中身がHTML断片になっていること(self):
        with tempfile.TemporaryDirectory() as d:
            設定 = config.load(environ={config.通知フォルダ環境変数: f"{d}/notice"})
            r = notify.書き出す(設定, "件名: 定例 <確認>\n選択画面: https://example.com/v")
            self.assertTrue(r.ok)
            中身 = Path(r.path).read_text(encoding="utf-8")
        self.assertIn("定例 &lt;確認&gt;<br>", 中身)
        self.assertIn('<a href="https://example.com/v">', 中身)
        self.assertNotIn("\n", 中身)


if __name__ == "__main__":
    unittest.main()
