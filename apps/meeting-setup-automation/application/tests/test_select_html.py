"""候補選択画面の生成とビューア形式URLの組み立て(tasks.md 11・12)のテスト。

選択画面は静的HTML1枚。候補ごとのカードとラジオボタン、選んだ候補の1行を組み立てて
コピーする3段構えのスクリプトを持つ。試行番号はカードごとに埋め込む(代替案1の枠は1、
代替案2の枠は2)。件名・参加者名は開催者の入力値なのでエスケープして埋め込む。
"""

import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

import candidates
import config
import select_html

JST = timezone(timedelta(hours=9))


def _枠(開始, 分=60, 試行=1, 出席者=("free", "free"), 開催者="free"):
    return candidates.枠(
        開始=開始, 終了=開始 + timedelta(minutes=分),
        出席者空き=[(f"p{i}@example.com", s) for i, s in enumerate(出席者)],
        開催者空き=開催者, 試行番号=試行,
    )


class _ラジオ収集(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ラジオ = []
        self.スクリプト = []
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "input" and a.get("type") == "radio":
            self.ラジオ.append(a)
        if tag == "script":
            self._in_script = True

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script = False

    def handle_data(self, data):
        if self._in_script:
            self.スクリプト.append(data)


def _解析(html):
    p = _ラジオ収集()
    p.feed(html)
    return p


def _既定の画面(**上書き):
    引数 = dict(
        依頼id="ID1", 件名="定例 <会議>", 所要時間分=60, 参加者数=3,
        セクション一覧=[
            select_html.セクション(
                見出し="候補", 条件="期間 2026-09-09〜2026-09-23、時間帯 09:30〜17:30",
                カード一覧=[
                    select_html.カード(枠=_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST))),
                    select_html.カード(枠=_枠(datetime(2026, 9, 11, 14, 0, tzinfo=JST))),
                ],
            )
        ],
        緩めた=False,
    )
    引数.update(上書き)
    return select_html.組み立てる(**引数)


class 選択画面の内容(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-3
    def test_ヘッダーに件名と所要時間と参加者数と条件の要約が含まれること(self):
        html = _既定の画面()
        self.assertIn("定例 &lt;会議&gt;", html)
        self.assertIn("60分", html)
        self.assertIn("3人", html)
        self.assertIn("期間 2026-09-09〜2026-09-23、時間帯 09:30〜17:30", html)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-3、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-4
    def test_候補1件につきカード1枚で候補番号と日付と曜日と時刻と空き状況が含まれること(self):
        html = _既定の画面()
        self.assertEqual(html.count('class="card"'), 2)
        self.assertIn("2026-09-10", html)
        self.assertIn("(木)", html)
        self.assertIn("10:00", html)
        self.assertIn("11:00", html)
        self.assertIn("全員空き", html)
        self.assertRegex(html, r"候補\s*1")
        self.assertRegex(html, r"候補\s*2")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-4
    def test_同じ名前のラジオボタン群で1つだけ選べること(self):
        p = _解析(_既定の画面())
        self.assertEqual(len(p.ラジオ), 2)
        self.assertEqual({r["name"] for r in p.ラジオ}, {"candidate"})

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#画面設計
    def test_ラジオボタンに依頼IDと試行番号と候補番号と日本時間のオフセット付き時刻が埋め込まれていること(self):
        p = _解析(_既定の画面())
        r = p.ラジオ[1]
        self.assertEqual(r["data-request"], "ID1")
        self.assertEqual(r["data-attempt"], "1")
        self.assertEqual(r["data-number"], "2")
        self.assertEqual(r["data-start"], "2026-09-11T14:00:00+09:00")
        self.assertEqual(r["data-end"], "2026-09-11T15:00:00+09:00")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#11-候補選択画面の生成select_htmlpy
    def test_試行番号はカードごとにその枠の候補ファイルの試行番号を埋め込むこと(self):
        html = _既定の画面(
            セクション一覧=[
                select_html.セクション(見出し="代替案1: 仮の予定を含める", 条件="c1",
                                  カード一覧=[select_html.カード(枠=_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 試行=1))]),
                select_html.セクション(見出し="代替案2: 期間と時間帯を広げる", 条件="c2",
                                  カード一覧=[select_html.カード(枠=_枠(datetime(2026, 9, 25, 18, 0, tzinfo=JST), 試行=2))]),
            ],
            緩めた=True,
        )
        p = _解析(html)
        self.assertEqual([r["data-attempt"] for r in p.ラジオ], ["1", "2"])
        self.assertEqual([r["data-number"] for r in p.ラジオ], ["1", "2"])  # 候補番号は画面全体の連番

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-8、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-5
    def test_代替案は見出しで分けて並べ緩めたことと広げた後の条件が分かること(self):
        html = _既定の画面(
            セクション一覧=[
                select_html.セクション(見出し="代替案1: 仮の予定を含める", 条件="期間・時間帯は既定のまま。仮の予定を空きとみなす",
                                  カード一覧=[select_html.カード(枠=_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST)),
                                                            仮の予定=["山田 太郎: 顧客MTG", "鈴木 花子: (非公開の予定)"])]),
                select_html.セクション(見出し="代替案2: 期間と時間帯を広げる", 条件="期間 2026-09-09〜2026-09-30、時間帯 09:30〜18:30",
                                  カード一覧=[select_html.カード(枠=_枠(datetime(2026, 9, 25, 18, 0, tzinfo=JST), 試行=2))]),
            ],
            緩めた=True,
        )
        self.assertIn("代替案1: 仮の予定を含める", html)
        self.assertIn("代替案2: 期間と時間帯を広げる", html)
        self.assertIn("2026-09-30", html)
        self.assertIn("18:30", html)
        self.assertIn("既定の条件では候補が0件", html)
        self.assertIn("山田 太郎: 顧客MTG", html)
        self.assertIn("(非公開の予定)", html)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#画面設計
    def test_空き状況は全員空きまたは空いていない人数だけを表示すること(self):
        html = _既定の画面(
            セクション一覧=[select_html.セクション(見出し="候補", 条件="c",
                                            カード一覧=[select_html.カード(枠=_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 出席者=("free", "busy")))])],
        )
        self.assertIn("1人が空いていません", html)
        self.assertNotIn("p1@example.com", html)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#セキュリティ
    def test_件名と参加者名をHTMLとして解釈されない形で埋め込むこと(self):
        html = _既定の画面(
            件名='<script>alert(1)</script>',
            セクション一覧=[select_html.セクション(見出し="候補", 条件="c",
                                            カード一覧=[select_html.カード(枠=_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST)),
                                                                      仮の予定=['<img src=x onerror=alert(1)>: 件名'])])],
        )
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", html)


class コピーの仕組み(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の選択-1、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の選択-2
    def test_コピーの3段構えがすべて含まれること(self):
        js = "".join(_解析(_既定の画面()).スクリプト)
        self.assertIn('execCommand("copy")', js)
        self.assertIn("navigator.clipboard", js)
        self.assertIn("writeText", js)
        self.assertIn(".select()", js)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#画面設計
    def test_選んだ候補の1行が目印の語から始まり依頼IDと試行番号と候補番号と時刻を並べること(self):
        js = "".join(_解析(_既定の画面()).スクリプト)
        self.assertIn(select_html.目印の語, js)
        for 項目 in ("request", "attempt", "number", "start", "end"):
            self.assertIn(f"dataset.{項目}", js)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#11-候補選択画面の生成select_htmlpy
    @unittest.skipUnless(shutil.which("node"), "nodeが無い環境では構文検査を省く")
    def test_生成物に含まれるJavaScriptが構文として成立していること(self):
        js = "\n".join(_解析(_既定の画面(件名='改行\nを含む "件名"')).スクリプト)
        with tempfile.TemporaryDirectory() as d:
            置き場 = Path(d, "select.js")
            置き場.write_text(js, encoding="utf-8")
            結果 = subprocess.run(["node", "--check", str(置き場)], capture_output=True, text=True)
        self.assertEqual(結果.returncode, 0, 結果.stderr)


class 選択画面の書き出し(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-2
    def test_HTMLフォルダへselect_依頼IDの名前で書き出し同じ名前があれば上書きすること(self):
        with tempfile.TemporaryDirectory() as d:
            設定 = config.load(environ={config.台帳ルート環境変数: d})
            path = Path(d, "html", "select-ID1.html")
            path.parent.mkdir()
            path.write_text("old", encoding="utf-8")
            結果 = select_html.書き出して確認(設定, "ID1", "<p>new</p>")
            self.assertTrue(結果.ok)
            self.assertTrue(結果.確認済み)
            self.assertEqual(path.read_text(encoding="utf-8"), "<p>new</p>")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#候補の絞り込みと選択画面の用意
    def test_書き出した後に読み戻して内容とサイズを確認すること(self):
        with tempfile.TemporaryDirectory() as d:
            設定 = config.load(environ={config.台帳ルート環境変数: d})
            読み = []

            def 読む(p):
                読み.append(p)
                return Path(p).read_text(encoding="utf-8")

            結果 = select_html.書き出して確認(設定, "ID1", "<p>x</p>", 読む=読む)
            self.assertTrue(結果.確認済み)
            self.assertGreaterEqual(len(読み), 2)

    def test_書き出しに失敗しても例外を投げず失敗した旨を返すこと(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "html").write_text("x", encoding="utf-8")
            設定 = config.load(environ={config.台帳ルート環境変数: d})
            結果 = select_html.書き出して確認(設定, "ID1", "<p>x</p>")
        self.assertFalse(結果.ok)


class ビューア形式URLの組み立て(unittest.TestCase):

    ビューア = "https://example-my.sharepoint.com/personal/u_example_com/_layouts/15/onedrive.aspx?view=0"
    相対パス = "/personal/u_example_com/Documents/00_root/auto/meetingSetting/html"

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-6
    def test_ファイルビューアで開く形式のURLになりビューアのクエリは落とすこと(self):
        url = select_html.ビューアurlを組み立てる(self.ビューア, self.相対パス, "select-ID1.html")
        self.assertTrue(url.startswith("https://example-my.sharepoint.com/personal/u_example_com/_layouts/15/onedrive.aspx?id="))
        self.assertNotIn("view=0", url)
        self.assertIn("&parent=%2Fpersonal%2Fu_example_com%2FDocuments%2F00_root%2Fauto%2FmeetingSetting%2Fhtml", url)
        self.assertIn("%2Fselect-ID1.html", url)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#12-ビューア形式urlの組み立てselect_htmlpy
    def test_エンコード済みのサーバー相対パスを二重にエンコードしないこと(self):
        url = select_html.ビューアurlを組み立てる(self.ビューア, "/personal/u/Documents/00_root/auto/meeting%20Setting/html", "s.html")
        self.assertIn("meeting%20Setting", url)
        self.assertNotIn("%2520", url)

    def test_パスの前後のスラッシュの有無を吸収すること(self):
        a = select_html.ビューアurlを組み立てる(self.ビューア, self.相対パス, "s.html")
        b = select_html.ビューアurlを組み立てる(self.ビューア + "/", self.相対パス.strip("/") + "/", "s.html")
        self.assertEqual(a, b)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-5
    def test_設定が欠けている場合はURLを組み立てずNoneを返すこと(self):
        self.assertIsNone(select_html.ビューアurlを組み立てる(None, self.相対パス, "s.html"))
        self.assertIsNone(select_html.ビューアurlを組み立てる(self.ビューア, "", "s.html"))


if __name__ == "__main__":
    unittest.main()
