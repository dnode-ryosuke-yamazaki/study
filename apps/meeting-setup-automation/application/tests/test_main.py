"""コマンドの入口と台帳フォルダの取り扱いの通し確認(tasks.md 18・19)のテスト。

一時ディレクトリを台帳のルートに差し替え、`main.py` のサブコマンド経由で依頼の書き出しから
完了の通知までを通す。フローが書くファイル(候補・作成結果)はテストが待ちの途中で
置く。時計は偽物で、待ち関数が呼ばれるたびに進める(実時間を使わない)。
"""

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

import config
import ledger
import main
import progress
from tests.test_candidates import _候補ファイル, _枠
from tests.test_organizer_events import _予定, _予定ファイル
from tests.test_result import _作成結果, 直リンク

JST = timezone(timedelta(hours=9))
今日 = "2026-09-09"
A, B, ME = "a@example.com", "b@example.com", "me@example.com"
E = "e@example.com"


class _ラジオ収集(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ラジオ = []
        self.見出し = []
        self._h2 = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "input" and a.get("type") == "radio":
            self.ラジオ.append(a)
        if tag == "h2":
            self._h2 = True

    def handle_endtag(self, tag):
        if tag == "h2":
            self._h2 = False

    def handle_data(self, data):
        if self._h2:
            self.見出し.append(data.strip())


def _選択行(r):
    return f"MEETING-SELECT {r['data-request']} a{r['data-attempt']} #{r['data-number']} {r['data-start']} {r['data-end']}"


class 通し環境:
    """偽の時計・差し替えた台帳フォルダ・出力の記録。待ち関数が呼ばれた回数で「ファイルの到着」を演出する。"""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.設定 = config.load(
            environ={
                config.台帳ルート環境変数: str(root / "ledger"),
                config.通知フォルダ環境変数: str(root / "notice"),
                config.作業フォルダ環境変数: str(root / "work"),
                config.同期猶予環境変数: "0",
                config.確認間隔環境変数: "5",
                config.候補待ち上限環境変数: "30",
                config.作成結果待ち上限環境変数: "30",
            }
        )
        (root / "work").mkdir()
        (root / "work" / "roster.json").write_text(
            json.dumps(
                {
                    "organizer": {"name": "私", "email": ME},
                    "members": [{"name": "A さん", "email": A}, {"name": "B さん", "email": B}, {"name": "重複", "email": "x1@example.com"}, {"name": "重複", "email": "x2@example.com"}, {"name": "E さん", "email": E, "romaji": "Taro Ei"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.今 = 0.0
        self.tick = 0
        self.予約 = {}
        self.出力 = []

    def close(self):
        self.tmp.cleanup()

    def 時計(self):
        return self.今

    def 待つ(self, 秒):
        self.今 += 秒
        self.tick += 1
        for f in self.予約.pop(self.tick, []):
            f()

    def 到着させる(self, tick, path, 内容):
        self.予約.setdefault(tick, []).append(lambda: ledger.write_json(path, 内容))

    def run(self, *argv):
        self.出力.clear()
        self.tick = 0
        env = main.実行環境(設定=self.設定, 今日=datetime.fromisoformat(今日).date(), 出力=self.出力.append, 時計=self.時計, 待つ=self.待つ)
        code = main.main(["--today", 今日, *argv], env=env)
        return code, "\n".join(self.出力)

    # --- 台帳の道具 ---
    def 依頼(self, id, 試行=1):
        return ledger.依頼ファイル(self.設定, id, 試行)

    def 候補(self, id, 試行=1):
        return ledger.候補ファイル(self.設定, id, 試行)

    def 作成結果(self, id, 再試行=0):
        return ledger.作成結果ファイル(self.設定, id, 再試行)

    def 選択結果(self, id, 再試行=0):
        return ledger.選択結果ファイル(self.設定, id, 再試行)

    def 画面(self, id):
        html = ledger.選択画面ファイル(self.設定, id).read_text(encoding="utf-8")
        p = _ラジオ収集()
        p.feed(html)
        return html, p

    def 開催者の依頼(self, id):
        return ledger.開催者の予定の依頼ファイル(self.設定, id)

    def 開催者の予定(self, id):
        return ledger.開催者の予定ファイル(self.設定, id)

    def 通知一覧(self):
        d = self.設定.通知フォルダ
        return sorted(d.iterdir()) if d.exists() else []

    def submit(self, id="ID1", **追加):
        argv = ["submit", "--subject", "定例", "--attendee", "A さん", "--attendee", "B さん", "--duration", "60", "--agenda", "- 進捗\n- 課題", "--request-id", id]
        for k, v in 追加.items():
            argv += [f"--{k.replace('_', '-')}"] + ([] if v is True else [str(v)])
        return self.run(*argv)


def _空き枠(日時, 出席者=("free", "free"), 開催者="free"):
    return _枠(日時, 出席者=出席者, 開催者=開催者, アドレス=[A, B])


class 依頼の書き出し(unittest.TestCase):

    def setUp(self):
        self.e = 通し環境()

    def tearDown(self):
        self.e.close()

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#18-コマンドの入口mainpy
    def test_dry_runは依頼を書き出さず依頼の内容だけを返すこと(self):
        code, out = self.e.submit(dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("依頼内容の確認", out)
        self.assertIn("A さん, B さん", out)
        self.assertIn("60分", out)
        self.assertFalse(self.e.依頼("ID1").exists())

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議設定の依頼-5
    def test_submitが依頼フォルダへ依頼を書き出すこと(self):
        code, out = self.e.submit()
        self.assertEqual(code, 0)
        self.assertTrue(self.e.依頼("ID1").is_file())
        self.assertIn("resume ID1", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議設定の依頼-4
    def test_名簿で解決できない名前があれば依頼を書き出さず聞き返すこと(self):
        code, out = self.e.run("submit", "--subject", "x", "--attendee", "A さん", "--attendee", "居ない人", "--attendee", "重複", "--duration", "30", "--request-id", "ID1")
        self.assertEqual(code, 2)
        self.assertIn("居ない人", out)
        self.assertIn("重複", out)
        self.assertFalse(self.e.依頼("ID1").exists())

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-5
    def test_複数人が該当する名前は候補のフルネームとメールアドレスを挙げて聞き返すこと(self):
        code, out = self.e.run("submit", "--subject", "x", "--attendee", "重複", "--duration", "30", "--request-id", "ID1")
        self.assertEqual(code, 2)
        self.assertIn("「重複」は2人が該当します", out)
        self.assertIn("重複 <x1@example.com>", out)
        self.assertIn("重複 <x2@example.com>", out)
        self.assertFalse(self.e.依頼("ID1").exists())
        # 候補の氏名・メールアドレスはログファイルに残さない(design.md#セキュリティ)
        ログ = self.e.設定.ログファイル.read_text(encoding="utf-8")
        self.assertNotIn("x1@example.com", ログ)
        self.assertNotIn("重複", ログ)
        self.assertIn("複数該当=1件", ログ)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-5
    def test_名簿に登録が無い名前はその旨を伝えること(self):
        code, out = self.e.run("submit", "--subject", "x", "--attendee", "居ない人", "--duration", "30", "--request-id", "ID1")
        self.assertEqual(code, 2)
        self.assertIn("「居ない人」は名簿に登録がありません", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-4
    def test_姓だけの指定でも該当が1人なら名簿のフルネームで依頼を書き出すこと(self):
        code, out = self.e.run("submit", "--subject", "x", "--attendee", "A", "--attendee", "Bさん", "--duration", "30", "--request-id", "ID1")
        self.assertEqual(code, 0)
        依頼 = json.loads(self.e.依頼("ID1").read_text(encoding="utf-8"))
        出席者 = [(a["emailAddress"]["name"], a["emailAddress"]["address"]) for a in 依頼["meeting"]["attendees"]]
        # 打った文字列(A / Bさん)ではなく、名簿の登録名で招待する
        self.assertEqual(sorted(出席者), [("A さん", A), ("B さん", B)])
        # 送信前の確認提示にも名簿の登録名が出る(誤解決に気づけるようにするため)
        self.assertIn("A さん, B さん", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-9
    def test_末尾の番号を外して解決した参加者だけ確認の提示にメールアドレスを添えること(self):
        """否定確認: 全員にメールアドレスを添えるようにすると落ちる。"""
        # Outlookの表示名の形(「姓, 名 1」)をそのまま貼った場合を想定する。名簿の値は架空
        code, out = self.e.run("submit", "--subject", "x", "--attendee", "Ei, Taro 1", "--attendee", "A", "--duration", "30", "--request-id", "ID1", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn(f"E さん <{E}>", out)
        # 番号を外さずに解決した参加者にはメールアドレスを添えない(提示を名簿の氏名のまま保つ)
        self.assertIn("A さん", out)
        self.assertNotIn(f"<{A}>", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-9
    def test_末尾の番号を外して解決した参加者のメールアドレスはログに残さないこと(self):
        """否定確認: 依頼を書き出したときのログに確認の提示と同じ参加者の表記を出すようにすると落ちる。

        --dry-run ではログを1行も書かないので、書き出しまで進めてログが書かれたことを確かめたうえで見る。
        """
        code, out = self.e.run("submit", "--subject", "x", "--attendee", "Ei, Taro 1", "--duration", "30", "--request-id", "ID1")
        self.assertEqual(code, 0)
        self.assertIn(f"E さん <{E}>", out)
        ログ = self.e.設定.ログファイル.read_text(encoding="utf-8")
        self.assertIn("ID1", ログ)
        self.assertNotIn(E, ログ)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#依頼内容の受け付け条件-7
    def test_受け付け条件を満たさない依頼は書き出さず項目を示すこと(self):
        code, out = self.e.submit(duration=3)
        self.assertEqual(code, 2)
        self.assertIn("所要時間", out)
        self.assertFalse(self.e.依頼("ID1").exists())


class 候補提示から会議作成までの通し(unittest.TestCase):

    def setUp(self):
        self.e = 通し環境()
        self.e.submit()
        self.枠一覧 = [
            _空き枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST)),
            _空き枠(datetime(2026, 9, 10, 8, 0, tzinfo=JST)),  # 時間帯外
            _空き枠(datetime(2026, 9, 11, 14, 0, tzinfo=JST)),
        ]

    def tearDown(self):
        self.e.close()

    def _候補を提示させる(self):
        self.e.到着させる(2, self.e.候補("ID1"), _候補ファイル(self.枠一覧))
        return self.e.run("resume", "ID1")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち合わせ-1、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-5
    def test_候補の到着を待って絞り込み選択画面と通知を書き出しURLをチャットにも出すこと(self):
        code, out = self._候補を提示させる()
        self.assertEqual(code, 0)
        self.assertIn("候補(試行1)の到着を待っています", out)
        html, p = self.e.画面("ID1")
        self.assertEqual(len(p.ラジオ), 2)  # 時間帯外の枠は除かれる
        self.assertEqual(len(self.e.通知一覧()), 1)
        self.assertIn("候補: 2件", out)
        self.assertIn("select-ID1.html", out)
        self.assertIn("select-ID1.html", self.e.通知一覧()[0].read_text(encoding="utf-8"))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#ログ
    def test_待ちの開始と進捗が依頼IDと対象と経過時間つきでログにも残ること(self):
        self.e.到着させる(2, self.e.候補("ID1"), _候補ファイル(self.枠一覧))
        with self.assertLogs(main.logger, level="INFO") as 記録:
            self.e.run("resume", "ID1")
        開始 = [r for r in 記録.output if "待ちの開始" in r]
        進捗 = [r for r in 記録.output if "待ちの進捗" in r]
        self.assertTrue(開始)
        self.assertTrue(進捗)
        self.assertIn("依頼ID=ID1", 進捗[0])
        self.assertIn("候補(試行1)", 進捗[0])
        self.assertRegex(進捗[0], r"\d+秒経過")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-5
    def test_通知ファイルの中身がHTML断片で選択画面のURLがリンクになっていること(self):
        self.e.設定 = replace(
            self.e.設定,
            ビューアurl="https://example-my.sharepoint.com/personal/u/_layouts/15/onedrive.aspx",
            サーバー相対パス="/personal/u/Documents/00_root/auto/meetingSetting/html",
        )
        _, out = self._候補を提示させる()
        中身 = self.e.通知一覧()[0].read_text(encoding="utf-8")
        self.assertIn("<br>", 中身)
        self.assertNotIn("\n", 中身)
        self.assertIn('<a href="https://example-my.sharepoint.com', 中身)
        # チャットへ出す文は同じ内容をプレーンテキストのまま出す
        self.assertNotIn("<br>", out)
        self.assertNotIn("<a href", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の選択-3、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#完了の通知-1
    def test_貼られた選択結果から選択結果を書き出し作成結果を待って完了を通知すること(self):
        self._候補を提示させる()
        _, p = self.e.画面("ID1")
        行 = _選択行(p.ラジオ[1])
        self.e.到着させる(1, self.e.作成結果("ID1"), _作成結果(f'<a href="{直リンク}">会議のオプション</a>'))
        code, out = self.e.run("select", 行)
        self.assertEqual(code, 0)
        選択 = json.loads(self.e.選択結果("ID1").read_text(encoding="utf-8"))
        self.assertEqual(選択["meeting"]["start"], "2026-09-11T14:00:00+09:00")
        self.assertIn("進捗", 選択["meeting"]["bodyHtml"])
        self.assertIn("Teams会議を作成しました", out)
        self.assertIn("meetup-join", out)
        self.assertIn(直リンク, out)
        self.assertIn("手動", out)
        self.assertEqual(len(self.e.通知一覧()), 2)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#台帳ファイルの扱い-3、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#台帳ファイルの扱い-1
    def test_到達した依頼の台帳ファイルが1つも削除されずSkillとフローの書くパスが重ならないこと(self):
        self._候補を提示させる()
        _, p = self.e.画面("ID1")
        self.e.到着させる(1, self.e.作成結果("ID1"), _作成結果(""))
        self.e.run("select", _選択行(p.ラジオ[0]))
        全部 = sorted(str(x.relative_to(self.e.設定.台帳ルート)) for x in self.e.設定.台帳ルート.rglob("*") if x.is_file())
        self.assertEqual(
            全部,
            ["candidates/candidates-ID1-a1.json", "html/select-ID1.html", "request/request-ID1-a1.json", "result/result-ID1.json", "selection/selection-ID1.json"],
        )

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議の作成-4
    def test_同じ選択結果を2回貼っても選択結果を2つ書き出さず作成済みを伝えること(self):
        self._候補を提示させる()
        _, p = self.e.画面("ID1")
        行 = _選択行(p.ラジオ[0])
        self.e.到着させる(1, self.e.作成結果("ID1"), _作成結果(""))
        self.e.run("select", 行)
        code, out = self.e.run("select", 行)
        self.assertEqual(code, 0)
        self.assertIn("作成済み", out)
        選択一覧 = list(self.e.設定.選択結果フォルダ.iterdir())
        self.assertEqual(len(選択一覧), 1)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の選択-4
    def test_古い画面や別の依頼の内容を貼った場合は書き出さず聞き返すこと(self):
        self._候補を提示させる()
        code, out = self.e.run("select", "MEETING-SELECT ID1 a1 #1 2026-09-10T09:00:00+09:00 2026-09-10T10:00:00+09:00")
        self.assertEqual(code, 2)
        self.assertIn("一致する候補", out)
        self.assertFalse(self.e.選択結果("ID1").exists())
        code, out = self.e.run("select", "これを選びます")
        self.assertEqual(code, 2)
        self.assertFalse(self.e.選択結果("ID1").exists())

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議の作成-5、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議の作成-6
    def test_失敗した作成結果は完了として報告せず指示を受けてから再試行番号付きで書き出し完了まで進むこと(self):
        self._候補を提示させる()
        _, p = self.e.画面("ID1")
        self.e.到着させる(1, self.e.作成結果("ID1"), {"requestId": "ID1", "retry": 0, "error": "ErrorAccessDenied", "event": None})
        code, out = self.e.run("select", _選択行(p.ラジオ[0]))
        self.assertEqual(code, 0)
        self.assertIn("作成に失敗", out)
        self.assertIn("ErrorAccessDenied", out)
        self.assertIn("カレンダー", out)
        self.assertIn("retry-create ID1", out)
        self.assertNotIn("Teams会議を作成しました", out)
        self.assertFalse(self.e.選択結果("ID1", 1).exists())
        # resume しても完了とは言わず再試行の案内に留まる
        code, out = self.e.run("resume", "ID1")
        self.assertIn("作成失敗", out)
        self.assertNotIn("Teams会議を作成しました", out)
        # 指示を受けて再試行
        self.e.到着させる(1, self.e.作成結果("ID1", 1), _作成結果(f'<a href="{直リンク}">x</a>', retry=1))
        code, out = self.e.run("retry-create", "ID1")
        self.assertEqual(code, 0)
        self.assertIn("会議が既に作られていないか", out)
        self.assertTrue(self.e.選択結果("ID1", 1).is_file())
        self.assertEqual(json.loads(self.e.選択結果("ID1", 1).read_text(encoding="utf-8"))["retry"], 1)
        self.assertIn("Teams会議を作成しました", out)
        # 失敗した作成結果が無い依頼には何もしない
        code, out = self.e.run("retry-create", "ID1")
        self.assertIn("再試行は行いません", out)
        self.assertFalse(self.e.選択結果("ID1", 2).exists())

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#録画とファシリテーターの設定-3
    def test_会議本文に直リンクが無い場合はカレンダーから会議オプションを開く手順を通知に含めること(self):
        self._候補を提示させる()
        _, p = self.e.画面("ID1")
        self.e.到着させる(1, self.e.作成結果("ID1"), _作成結果("<p>本文だけ</p>"))
        code, out = self.e.run("select", _選択行(p.ラジオ[0]))
        self.assertIn("Teams会議を作成しました", out)
        self.assertIn("取り出せませんでした", out)
        self.assertIn("会議のオプション", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち合わせ-2、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち合わせ-3
    def test_途中で打ち切っても台帳が残り依頼IDを渡した再開でその続きから進むこと(self):
        code, out = self.e.run("resume", "ID1")  # 候補は来ない
        self.assertEqual(code, 0)
        self.assertIn("打ち切りました", out)
        self.assertIn("resume ID1", out)
        self.assertTrue(self.e.依頼("ID1").is_file())
        ledger.write_json(self.e.候補("ID1"), _候補ファイル(self.枠一覧))
        code, out = self.e.run("resume", "ID1")
        self.assertEqual(code, 0)
        self.assertIn("候補到着", out)
        self.assertTrue(ledger.選択画面ファイル(self.e.設定, "ID1").is_file())
        # 選択後に作成結果を待って打ち切っても、再開で作成結果の待ちから続く
        _, p = self.e.画面("ID1")
        code, out = self.e.run("select", _選択行(p.ラジオ[0]))
        self.assertIn("打ち切りました", out)
        self.e.到着させる(1, self.e.作成結果("ID1"), _作成結果(""))
        code, out = self.e.run("resume", "ID1")
        self.assertIn("選択済み", out)
        self.assertIn("Teams会議を作成しました", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#非機能要件-1
    def test_依頼IDが異なる2件を並べても互いのファイルを取り違えないこと(self):
        self.e.submit(id="ID2")
        ledger.write_json(self.e.候補("ID2"), _候補ファイル(self.枠一覧))
        code, out = self.e.run("resume", "ID1")
        self.assertIn("打ち切りました", out)  # ID2の候補でID1が進まない
        code, out = self.e.run("resume", "ID2")
        self.assertTrue(ledger.選択画面ファイル(self.e.設定, "ID2").is_file())
        self.assertFalse(ledger.選択画面ファイル(self.e.設定, "ID1").exists())

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#エラーハンドリング
    def test_候補ファイルに失敗理由が入っていればその時点で理由を伝えて終了すること(self):
        self.e.到着させる(1, self.e.候補("ID1"), _候補ファイル([], 失敗="Connector timeout"))
        code, out = self.e.run("resume", "ID1")
        self.assertEqual(code, 1)
        self.assertIn("Connector timeout", out)
        self.assertFalse(ledger.選択画面ファイル(self.e.設定, "ID1").exists())

    def test_存在しない依頼IDを再開すると依頼が無いことを伝えること(self):
        code, out = self.e.run("resume", "NOPE")
        self.assertEqual(code, 2)
        self.assertIn("見つかりません", out)


class 候補が0件のときの代替案の通し(unittest.TestCase):

    def setUp(self):
        self.e = 通し環境()
        self.e.submit()
        # 既定の条件では全員空きの枠が無い: Bが仮(10:00)・Bと開催者が仮(11:00)・開催者だけが仮(13:00)・Aが予約済み(15:00)
        # 代替案1は10:00と11:00、開催者の予定のみ重なる枠は13:00、代替案2は広げた期間にだけある枠
        self.枠一覧 = [
            _空き枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 出席者=("free", "tentative")),
            _空き枠(datetime(2026, 9, 10, 11, 0, tzinfo=JST), 出席者=("free", "tentative"), 開催者="tentative"),
            _空き枠(datetime(2026, 9, 10, 13, 0, tzinfo=JST), 開催者="tentative"),
            _空き枠(datetime(2026, 9, 10, 15, 0, tzinfo=JST), 出席者=("busy", "free")),
        ]
        self.代替2枠 = [_空き枠(datetime(2026, 9, 25, 17, 30, tzinfo=JST))]  # 広げた時間帯・期間にだけある枠
        # 開催者予定フローが返す予定: 13:00の枠に重なる仮の予定(04:00 UTC = 13:00 JST)
        self.予定一覧 = [_予定("社内レビュー", datetime(2026, 9, 10, 4, 0, tzinfo=timezone.utc), showAs="tentative")]

    def tearDown(self):
        self.e.close()

    def _代替案を提示させる(self, 代替2到着=True, 代替2内容=None, 予定到着=True):
        self.e.到着させる(1, self.e.候補("ID1"), _候補ファイル(self.枠一覧))
        if 代替2到着:
            self.e.到着させる(2, self.e.候補("ID1", 2), 代替2内容 if 代替2内容 is not None else _候補ファイル(self.代替2枠, 試行=2))
        if 予定到着:
            self.e.到着させる(2, self.e.開催者の予定("ID1"), _予定ファイル(self.予定一覧, 依頼id="ID1"))
        return self.e.run("resume", "ID1")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-7、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-1、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-2、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-5
    def test_既定で0件なら確認を挟まず2つの代替案を作り1枚の選択画面に2つの見出しで並べること(self):
        code, out = self._代替案を提示させる()
        self.assertEqual(code, 0)
        self.assertIn("確認を挟まず", out)
        # 代替案1は依頼を出し直さず、代替案2(試行2)の依頼だけが書かれる
        代替2依頼 = json.loads(self.e.依頼("ID1", 2).read_text(encoding="utf-8"))
        self.assertEqual(代替2依頼["filter"]["timeWindowEnd"], "18:30")
        self.assertEqual(代替2依頼["search"]["end"][:10], "2026-09-30")
        self.assertEqual(len(list(self.e.設定.依頼フォルダ.iterdir())), 2)
        html, p = self.e.画面("ID1")
        self.assertEqual(p.見出し, [main.見出し_代替案1, main.見出し_代替案2, main.見出し_開催者])
        self.assertEqual([r["data-attempt"] for r in p.ラジオ], ["1", "1", "2", "1"])
        self.assertIn("B さん", html)
        self.assertIn("私(開催者)", html)
        self.assertNotIn("顧客MTG", html)  # 参加者の予定の件名は扱わない
        self.assertIn("既定の条件では候補が0件", out)
        self.assertIn("仮の予定あり", out)
        self.assertIn("18:30", out)
        self.assertIn("開催者の予定のみ重なる枠: 1件", out)
        self.assertIn("社内レビュー 13:00〜14:00(仮)", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-2
    def test_代替案1の枠を貼った選択結果が突き合わせを通ること(self):
        self._代替案を提示させる()
        _, p = self.e.画面("ID1")
        self.e.到着させる(1, self.e.作成結果("ID1"), _作成結果(""))
        code, out = self.e.run("select", _選択行(p.ラジオ[0]))  # 代替案1(試行1)の枠
        self.assertEqual(code, 0)
        self.assertIn("Teams会議を作成しました", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#依頼ファイルの区分
    def test_候補ファイルに試行番号が書かれていなくても読んだファイルの試行番号で扱うこと(self):
        内容 = _候補ファイル(self.代替2枠, 試行=2)
        del 内容["attempt"]
        self._代替案を提示させる(代替2内容=内容)
        _, p = self.e.画面("ID1")
        self.assertEqual([r["data-attempt"] for r in p.ラジオ], ["1", "1", "2", "1"])
        self.e.到着させる(1, self.e.作成結果("ID1"), _作成結果(""))
        code, out = self.e.run("select", _選択行(p.ラジオ[2]))
        self.assertEqual(code, 0)
        self.assertIn("Teams会議を作成しました", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#19-台帳フォルダの取り扱いの通し確認結合テスト
    def test_代替案2の枠を貼った場合も突き合わせが通ること(self):
        self._代替案を提示させる()
        _, p = self.e.画面("ID1")
        self.e.到着させる(1, self.e.作成結果("ID1"), _作成結果(""))
        code, out = self.e.run("select", _選択行(p.ラジオ[2]))  # 代替案2(試行2)の枠
        self.assertEqual(code, 0)
        self.assertIn("Teams会議を作成しました", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-8
    def test_代替案の台帳がある依頼を再開すると両方を絞り直して同じ画面にまとめ直すこと(self):
        self._代替案を提示させる()
        html1, _ = self.e.画面("ID1")
        code, out = self.e.run("resume", "ID1")
        self.assertIn("代替案の提示済み", out)
        html2, p = self.e.画面("ID1")
        self.assertEqual(p.見出し, [main.見出し_代替案1, main.見出し_代替案2, main.見出し_開催者])
        self.assertEqual(len(p.ラジオ), 4)
        self.assertNotIn("開催者の予定の到着を待っています", out)  # 取得済みの予定を使い、取り直さない

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#19-台帳フォルダの取り扱いの通し確認結合テスト
    def test_代替案2の依頼を書いた直後の再開は依頼済みではなく代替案の提示中として扱われること(self):
        code, out = self._代替案を提示させる(代替2到着=False)
        self.assertIn("打ち切り", out)
        self.assertEqual(progress.判定(self.e.設定, "ID1").状態, progress.代替案の提示中)
        code, out = self.e.run("resume", "ID1")
        self.assertIn("代替案の提示中", out)
        self.assertNotIn("状態: 依頼済み", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-3、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-3
    def test_出席者に仮があり開催者も仮の枠は代替案1に開催者込みで示され開催者だけが仮の枠は開催者の予定のみ重なる枠の区画に出ること(self):
        code, out = self._代替案を提示させる()
        self.assertEqual(code, 0)
        html, p = self.e.画面("ID1")
        self.assertEqual(len(p.ラジオ), 4)
        self.assertEqual(html.count("仮の予定あり"), 2)  # 代替案1の2枠(10:00・11:00)だけ
        self.assertIn("B さん", html)          # 出席者の仮の予定
        self.assertIn("私(開催者)", html)     # 11:00の枠: 開催者自身の仮の予定も添える
        self.assertEqual([r["data-start"][11:16] for r in p.ラジオ], ["10:00", "11:00", "17:30", "13:00"])
        self.assertIn("⚠ 開催者の予定あり", html)
        self.assertIn("社内レビュー 13:00〜14:00(仮)", html)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち合わせ-5、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち時間の上限-3
    def test_代替案2の候補が届かなくても代替案1の枠を提示し台帳が残って再開で続けられること(self):
        code, out = self._代替案を提示させる(代替2到着=False)
        self.assertEqual(code, 0)
        html, p = self.e.画面("ID1")
        self.assertEqual([r["data-attempt"] for r in p.ラジオ], ["1", "1", "1"])
        self.assertIn("打ち切りました", out)
        self.assertTrue(self.e.依頼("ID1", 2).is_file())
        # 再開すると代替案2の候補の到着から続く
        self.e.到着させる(1, self.e.候補("ID1", 2), _候補ファイル(self.代替2枠, 試行=2))
        code, out = self.e.run("resume", "ID1")
        _, p = self.e.画面("ID1")
        self.assertEqual([r["data-attempt"] for r in p.ラジオ], ["1", "1", "2", "1"])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#19-台帳フォルダの取り扱いの通し確認結合テスト
    def test_代替案2の候補が届かないまま代替案1の枠を選んだ依頼を再開しても来ない候補を待たないこと(self):
        self._代替案を提示させる(代替2到着=False)
        _, p = self.e.画面("ID1")
        code, out = self.e.run("select", _選択行(p.ラジオ[0]))  # 作成結果は来ない → 打ち切り
        self.assertIn("打ち切りました", out)
        code, out = self.e.run("resume", "ID1")
        self.assertIn("選択済み", out)
        self.assertNotIn("代替案2の候補の到着を待っています", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち合わせ-5
    def test_代替案2の候補ファイルに失敗理由が入っていても代替案1の枠を並べて理由を伝え全体を終了しないこと(self):
        code, out = self._代替案を提示させる(代替2内容=_候補ファイル([], 失敗="Connector failed", 試行=2))
        self.assertEqual(code, 0)
        _, p = self.e.画面("ID1")
        self.assertEqual(len(p.ラジオ), 3)
        self.assertIn("Connector failed", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち時間の上限-2
    def test_代替案2の候補の待ちに候補の待ち上限が適用されること(self):
        self.e.到着させる(1, self.e.候補("ID1"), _候補ファイル(self.枠一覧))
        code, out = self.e.run("resume", "ID1")  # 代替案2の候補は来ない → 上限で打ち切り
        self.assertEqual(code, 0)
        # 上限30秒・間隔5秒なので、経過が30秒に達した時点で打ち切られる
        進捗 = [行 for 行 in out.splitlines() if "代替案2の候補の到着を待っています" in 行]
        self.assertTrue(進捗)
        self.assertIn("上限30秒", 進捗[0])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-8
    def test_代替案2を作らない依頼を再開しても同じ選択画面に至ること(self):
        self.e.close()
        self.e = 通し環境()
        self.e.submit(start_date="2026-09-09", end_date="2026-09-12", time_start="09:30", time_end="17:30")
        self.e.到着させる(1, self.e.候補("ID1"), _候補ファイル(self.枠一覧))
        code, _初回 = self.e.run("resume", "ID1")
        self.assertEqual(code, 0)
        _, p1 = self.e.画面("ID1")
        code, 再開出力 = self.e.run("resume", "ID1")  # 代替案の台帳が増えないので既定の絞り込みからやり直す
        self.assertEqual(code, 0)
        _, p2 = self.e.画面("ID1")
        self.assertEqual([r["data-start"] for r in p1.ラジオ], [r["data-start"] for r in p2.ラジオ])
        self.assertEqual(p1.見出し, p2.見出し)
        self.assertIn("代替案2は作りませんでした", 再開出力)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-4
    def test_期間と時間帯の両方を指定した依頼では代替案2が作られないこと(self):
        self.e.close()
        self.e = 通し環境()
        self.e.submit(start_date="2026-09-09", end_date="2026-09-12", time_start="09:30", time_end="17:30")
        self.e.到着させる(1, self.e.候補("ID1"), _候補ファイル(self.枠一覧))
        code, out = self.e.run("resume", "ID1")
        self.assertEqual(code, 0)
        self.assertFalse(self.e.依頼("ID1", 2).exists())
        _, p = self.e.画面("ID1")
        self.assertEqual(p.見出し, [main.見出し_代替案1, main.見出し_開催者])
        self.assertIn("代替案2は作りませんでした", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-6
    def test_どちらの代替案も0件なら試した条件を報告して相談に切り替え次の依頼を作らないこと(self):
        全員予約済み = [_空き枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 出席者=("busy", "busy"))]
        self.e.到着させる(1, self.e.候補("ID1"), _候補ファイル(全員予約済み))
        self.e.到着させる(2, self.e.候補("ID1", 2), _候補ファイル([], 理由="OrganizerUnavailable", 試行=2))
        code, out = self.e.run("resume", "ID1")
        self.assertEqual(code, 0)
        self.assertIn("候補が見つかりませんでした", out)
        self.assertIn("代替案2:", out)
        self.assertIn("submit", out)
        self.assertFalse(ledger.選択画面ファイル(self.e.設定, "ID1").exists())
        self.assertEqual(len(list(self.e.設定.依頼フォルダ.iterdir())), 2)  # 試行3以降は作らない
        # 再開しても同じ結論に至る
        code, out = self.e.run("resume", "ID1")
        self.assertIn("候補が見つかりませんでした", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-7
    def test_代替案1が0件で受け取った枠が要求件数と同数なら打ち切りの可能性を伝えること(self):
        self.e.close()
        self.e = 通し環境()
        self.e.submit(start_date="2026-09-09", end_date="2026-09-12", time_start="09:30", time_end="17:30")
        依頼 = json.loads(self.e.依頼("ID1").read_text(encoding="utf-8"))
        n = 依頼["search"]["maxCandidates"]
        全員予約済み = [_空き枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST) + timedelta(hours=i % 5, days=i // 5), 出席者=("busy", "busy")) for i in range(n)]
        self.e.到着させる(1, self.e.候補("ID1"), _候補ファイル(全員予約済み))
        code, out = self.e.run("resume", "ID1")
        self.assertIn("件数で打ち切られている可能性", out)


class 開催者の予定のみ重なる枠の通し(unittest.TestCase):
    """参加者全員は空いていて開催者の予定だけが重なる枠について、開催者の予定の依頼を書き出し、
    予定の到着を待って突き合わせ、候補とは別の区画で選択画面・通知・チャットに示すまでを通す。
    取得できなくても枠の提示は止めない。
    """

    def setUp(self):
        self.e = 通し環境()
        self.e.submit()
        self.枠一覧 = [
            _空き枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST)),                       # 候補
            _空き枠(datetime(2026, 9, 11, 16, 0, tzinfo=JST), 開催者="busy"),         # 開催者だけが予約済み
        ]
        # 16:00〜17:00 JST = 07:00〜08:00 UTC に重なる開催者の予定(2件目は非公開)
        self.予定一覧 = [
            _予定("社内レビュー", datetime(2026, 9, 11, 7, 0, tzinfo=timezone.utc), 分=30),
            _予定("病院", datetime(2026, 9, 11, 7, 30, tzinfo=timezone.utc), 分=30, sensitivity="private"),
        ]

    def tearDown(self):
        self.e.close()

    def _提示させる(self, 予定内容=None, 予定到着=True, 枠一覧=None):
        self.e.到着させる(1, self.e.候補("ID1"), _候補ファイル(枠一覧 if 枠一覧 is not None else self.枠一覧))
        if 予定到着:
            self.e.到着させる(3, self.e.開催者の予定("ID1"), 予定内容 if 予定内容 is not None else _予定ファイル(self.予定一覧, 依頼id="ID1"))
        return self.e.run("resume", "ID1")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-9、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-10、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち合わせ-1
    def test_候補と開催者のみ不在の枠があれば開催者の予定の依頼を書き出し予定の到着を待ってから別区画付きの選択画面と通知を用意すること(self):
        code, out = self._提示させる()
        self.assertEqual(code, 0)
        self.assertIn("開催者の予定の到着を待っています", out)
        依頼 = json.loads(self.e.開催者の依頼("ID1").read_text(encoding="utf-8"))
        self.assertEqual(依頼, {"requestId": "ID1", "rangeStart": "2026-09-11T07:00:00Z", "rangeEnd": "2026-09-11T08:00:00Z"})
        html, p = self.e.画面("ID1")
        self.assertEqual(p.見出し, [main.見出し_既定, main.見出し_開催者])
        self.assertEqual([r["data-attempt"] for r in p.ラジオ], ["1", "1"])
        self.assertIn("⚠ 開催者の予定あり", html)
        self.assertIn("社内レビュー 16:00〜16:30(予約済み)", html)
        self.assertIn("非公開の予定 16:30〜17:00(予約済み)", html)
        self.assertNotIn("病院", html)
        self.assertIn("候補: 1件", out)
        self.assertIn("開催者の予定のみ重なる枠: 1件(自分の予定を調整すれば開けられる枠)", out)
        self.assertIn("・09/11(金) 16:00〜17:00 — 社内レビュー 16:00〜16:30(予約済み)、非公開の予定 16:30〜17:00(予約済み)", out)
        通知 = self.e.通知一覧()[0].read_text(encoding="utf-8")
        self.assertIn("開催者の予定のみ重なる枠: 1件", 通知)
        self.assertNotIn("病院", 通知)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-6
    def test_開催者のみ不在の枠が無ければ依頼を書かず待たないこと(self):
        code, out = self._提示させる(枠一覧=[_空き枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST))], 予定到着=False)
        self.assertEqual(code, 0)
        self.assertFalse(self.e.開催者の依頼("ID1").exists())
        self.assertNotIn("開催者の予定", out)
        _, p = self.e.画面("ID1")
        self.assertEqual(p.見出し, [main.見出し_既定])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-1
    def test_一部不在の枠も含める依頼では開催者のみ不在の切り出しも依頼も待ちもしないこと(self):
        self.e.close()
        self.e = 通し環境()
        self.e.submit(allow_partial=True)
        code, out = self._提示させる(予定到着=False)
        self.assertEqual(code, 0)
        self.assertFalse(self.e.開催者の依頼("ID1").exists())
        self.assertNotIn("開催者の予定", out)
        _, p = self.e.画面("ID1")
        self.assertEqual(p.見出し, [main.見出し_既定])
        self.assertEqual(len(p.ラジオ), 2)  # 開催者が予約済みの枠も候補として採用される

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-12、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち時間の上限-3
    def test_予定が待ち上限内に届かなくても件名なしで枠を提示し台帳を残して依頼を終了させないこと(self):
        code, out = self._提示させる(予定到着=False)
        self.assertEqual(code, 0)
        html, p = self.e.画面("ID1")
        self.assertEqual(p.見出し, [main.見出し_既定, main.見出し_開催者])
        self.assertIn("開催者の予定を取得できませんでした(待ち上限(30秒)を超えました)", html)
        self.assertIn("開催者の予定を取得できませんでした(待ち上限(30秒)を超えました)", out)
        self.assertIn("select-ID1.html", out)
        self.assertTrue(self.e.開催者の依頼("ID1").is_file())
        self.assertNotIn("resume ID1", out.split("選択画面")[0])  # 依頼全体の打ち切りとしては扱わない

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-6
    def test_予定ファイルに失敗理由が入っていれば件名なしで枠を提示し理由を添えること(self):
        code, out = self._提示させる(予定内容=_予定ファイル([], 失敗="Connector failed", 依頼id="ID1"))
        self.assertEqual(code, 0)
        html, _ = self.e.画面("ID1")
        self.assertIn("開催者予定フローが失敗を返しました: Connector failed", html)
        self.assertIn("開催者予定フローが失敗を返しました: Connector failed", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-6
    def test_依頼を書き出せなくても件名なしで枠を提示し理由を添えること(self):
        self.e.設定.開催者の予定の依頼フォルダ.parent.mkdir(parents=True, exist_ok=True)
        self.e.設定.開催者の予定の依頼フォルダ.write_text("x", encoding="utf-8")  # フォルダの位置にファイルがある → 書けない
        code, out = self._提示させる(予定到着=False)
        self.assertEqual(code, 0)
        html, _ = self.e.画面("ID1")
        self.assertIn("開催者の予定の依頼を書き出せませんでした", html)
        self.assertNotIn("開催者の予定の到着を待っています", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-7
    def test_再開時は依頼だけがあれば待ちから続き予定があれば取り直さず選択済み以降は待たないこと(self):
        self._提示させる(予定到着=False)  # 依頼は書かれ、予定は来ないまま件名なしで提示
        更新前 = self.e.開催者の依頼("ID1").stat().st_mtime_ns
        self.e.到着させる(1, self.e.開催者の予定("ID1"), _予定ファイル(self.予定一覧, 依頼id="ID1"))
        code, out = self.e.run("resume", "ID1")
        self.assertEqual(code, 0)
        self.assertIn("開催者の予定の到着を待っています", out)
        self.assertEqual(self.e.開催者の依頼("ID1").stat().st_mtime_ns, 更新前)  # 依頼は書き直さない
        html, p = self.e.画面("ID1")
        self.assertIn("社内レビュー 16:00〜16:30(予約済み)", html)
        code, out = self.e.run("resume", "ID1")  # 予定ファイルがある → 待たずに使う
        self.assertNotIn("開催者の予定の到着を待っています", out)
        self.assertIn("社内レビュー 16:00〜16:30(予約済み)", out)
        self.e.run("select", _選択行(p.ラジオ[0]))  # 作成結果は来ない → 打ち切り
        code, out = self.e.run("resume", "ID1")
        self.assertIn("選択済み", out)
        self.assertNotIn("開催者の予定", out)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-11
    def test_開催者の予定のみ重なる枠を選んでコピーした1行が突き合わせを通り候補と同じ流れで会議が作られること(self):
        self._提示させる()
        _, p = self.e.画面("ID1")
        行 = _選択行(p.ラジオ[1])  # 開催者の予定のみ重なる枠(試行番号1)
        self.assertIn(" a1 ", 行)
        self.e.到着させる(1, self.e.作成結果("ID1"), _作成結果(""))
        code, out = self.e.run("select", 行)
        self.assertEqual(code, 0)
        self.assertIn("Teams会議を作成しました", out)
        選択 = json.loads(self.e.選択結果("ID1").read_text(encoding="utf-8"))
        self.assertEqual(選択["meeting"]["start"], "2026-09-11T16:00:00+09:00")
        self.assertNotIn("organizer", json.dumps(選択))  # 開催者の予定に関する項目を選択結果に持たない

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-8
    def test_両方の代替案とも0件で開催者のみ不在の枠だけがあるときはその区画だけの選択画面を通知し相談も併せて伝えること(self):
        枠一覧 = [
            _空き枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 出席者=("busy", "busy")),
            _空き枠(datetime(2026, 9, 11, 16, 0, tzinfo=JST), 開催者="busy"),
        ]
        self.e.到着させる(1, self.e.候補("ID1"), _候補ファイル(枠一覧))
        self.e.到着させる(2, self.e.候補("ID1", 2), _候補ファイル([], 理由="OrganizerUnavailable", 試行=2))
        self.e.到着させる(2, self.e.開催者の予定("ID1"), _予定ファイル(self.予定一覧, 依頼id="ID1"))
        code, out = self.e.run("resume", "ID1")
        self.assertEqual(code, 0)
        html, p = self.e.画面("ID1")
        self.assertEqual(p.見出し, [main.見出し_開催者])
        self.assertEqual(len(p.ラジオ), 1)
        self.assertIn("既定の条件では候補が0件", html)
        self.assertIn("select-ID1.html", out)
        self.assertIn("候補が見つかりませんでした", out)
        self.assertIn("参加者・期間・所要時間のどれを緩めるか", out)
        self.assertEqual(len(list(self.e.設定.依頼フォルダ.iterdir())), 2)  # 試行3以降は作らない
        通知 = self.e.通知一覧()[0].read_text(encoding="utf-8")
        self.assertIn("select-ID1.html", 通知)
        self.assertIn("緩めるか", 通知)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#非機能要件-1
    def test_依頼IDが異なる2件で開催者の予定ファイルを取り違えないこと(self):
        self.e.submit(id="ID2")
        別の予定 = [_予定("別件", datetime(2026, 9, 11, 7, 0, tzinfo=timezone.utc))]
        ledger.write_json(self.e.候補("ID2"), _候補ファイル(self.枠一覧))
        ledger.write_json(self.e.開催者の予定("ID2"), _予定ファイル(別の予定, 依頼id="ID2"))
        code, out = self._提示させる()
        html1, _ = self.e.画面("ID1")
        self.assertIn("社内レビュー", html1)
        self.assertNotIn("別件", html1)
        # ID2の予定ファイルに ID1 の requestId が入っていても、ID2 の依頼には使わない
        ledger.write_json(self.e.開催者の予定("ID2"), _予定ファイル(別の予定, 依頼id="ID1"))
        code, out = self.e.run("resume", "ID2")
        html2, _ = self.e.画面("ID2")
        self.assertIn("依頼IDが一致しません", html2)
        self.assertNotIn("別件", html2)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち合わせ-4、apps/meeting-setup-automation/specs/meeting-scheduling/design.md#ログ
    def test_待ちの進捗に開催者の予定が対象として出てログに件名を残さないこと(self):
        self.e.到着させる(1, self.e.候補("ID1"), _候補ファイル(self.枠一覧))
        self.e.到着させる(3, self.e.開催者の予定("ID1"), _予定ファイル(self.予定一覧, 依頼id="ID1"))
        with self.assertLogs(main.logger, level="INFO") as 記録:
            code, out = self.e.run("resume", "ID1")
        進捗 = [行 for 行 in out.splitlines() if "開催者の予定の到着を待っています" in 行]
        self.assertTrue(進捗)
        self.assertIn("上限30秒", 進捗[0])
        全ログ = "\n".join(記録.output)
        self.assertIn("開催者の予定の依頼を書き出しました", 全ログ)
        self.assertIn("開催者の予定の突き合わせ", 全ログ)
        self.assertNotIn("社内レビュー", 全ログ)
        self.assertNotIn("病院", 全ログ)


if __name__ == "__main__":
    unittest.main()
