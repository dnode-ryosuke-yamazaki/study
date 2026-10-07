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
            self.assertIsNone(名簿.organizer_name)
            名簿2 = roster.load(
                _名簿を書く(
                    d,
                    [{"name": "A", "email": "a@example.com"}],
                    organizer={"name": "私", "email": "me@example.com"},
                )
            )
            self.assertEqual(名簿2.organizer_name, "私")


class 名前の解決(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.名簿 = roster.load(
            _名簿を書く(
                self._tmp.name,
                [
                    {"name": "山田 太郎", "email": "taro@example.com"},
                    {"name": "架空 花子", "email": "hanako@example.com"},
                    {"name": "佐藤 次郎", "email": "jiro1@example.com"},
                    {"name": "佐藤 次郎", "email": "jiro2@example.com"},
                ],
            )
        )

    def tearDown(self):
        self._tmp.cleanup()

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議設定の依頼-3
    def test_登録のある名前を1件解決できること(self):
        self.assertEqual(self.名簿.resolve_one("架空 花子"), "hanako@example.com")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-2
    def test_登録がない名前は解決できないものとして返ること(self):
        self.assertIsNone(self.名簿.resolve_one("存在 しない"))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-2
    def test_同じ名前が複数ある場合はどちらかを選ばず解決できないものとして返ること(self):
        self.assertIsNone(self.名簿.resolve_one("佐藤 次郎"))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#会議設定の依頼-4、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-3
    def test_複数の名前をまとめて解決し解決できなかった名前の一覧が返ること(self):
        結果 = self.名簿.resolve(["山田 太郎", "存在 しない", "佐藤 次郎", "架空 花子"])
        self.assertEqual(結果.未解決, ["存在 しない", "佐藤 次郎"])
        self.assertFalse(結果.ok)
        self.assertEqual(
            結果.解決済み,
            [
                {"name": "山田 太郎", "email": "taro@example.com"},
                {"name": "架空 花子", "email": "hanako@example.com"},
            ],
        )

    def test_全員解決できた場合は成功として返ること(self):
        結果 = self.名簿.resolve(["山田 太郎", "架空 花子"])
        self.assertTrue(結果.ok)
        self.assertEqual(結果.未解決, [])

    def test_名前の前後の空白は無視して解決すること(self):
        self.assertEqual(self.名簿.resolve_one("  山田 太郎 "), "taro@example.com")


class 表記のゆれを吸収した照合(unittest.TestCase):
    """数百人規模の名簿では、登録された表記どおりに打ち分けることを利用者に求められない。
    姓名の区切り・敬称・姓だけ/名だけの指定を同じ人物への指定として扱う。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.名簿 = roster.load(
            _名簿を書く(
                self._tmp.name,
                [
                    {"name": "西園寺　彩", "email": "nao@example.com"},  # 区切りは全角スペース
                    {"name": "架空 一郎", "email": "ichiro@example.com"},
                    {"name": "架空 二郎", "email": "jiro@example.com"},
                    {"name": "Dubois, Antoine", "email": "seb@example.com"},
                ],
            )
        )

    def tearDown(self):
        self._tmp.cleanup()

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-4
    def test_姓名の区切りが全角でも半角でも無くても同じ人物として解決すること(self):
        for 打ち方 in ("西園寺　彩", "西園寺 彩", "西園寺彩"):
            with self.subTest(打ち方=打ち方):
                self.assertEqual(self.名簿.resolve_one(打ち方), "nao@example.com")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-4
    def test_敬称さんが付いていても解決すること(self):
        self.assertEqual(self.名簿.resolve_one("西園寺　彩さん"), "nao@example.com")
        self.assertEqual(self.名簿.resolve_one("西園寺さん"), "nao@example.com")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-4
    def test_姓だけの指定でも該当が1人なら解決すること(self):
        self.assertEqual(self.名簿.resolve_one("西園寺"), "nao@example.com")
        self.assertEqual(self.名簿.resolve_one("Dubois"), "seb@example.com")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-4
    def test_名だけの指定でも該当が1人なら解決すること(self):
        self.assertEqual(self.名簿.resolve_one("彩"), "nao@example.com")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-2
    def test_姓だけで複数人が該当する場合は解決しないこと(self):
        self.assertIsNone(self.名簿.resolve_one("架空"))
        self.assertIsNone(self.名簿.resolve_one("架空さん"))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-4
    def test_フルネームで指定すれば同姓でも解決すること(self):
        self.assertEqual(self.名簿.resolve_one("架空 一郎"), "ichiro@example.com")


class 照合を緩めても取り違えないこと(unittest.TestCase):
    """照合を緩めた分、別人が1人に潰れる経路が増えていないことを固定する。"""

    def _名簿(self, members):
        return roster.load(_名簿を書く(self._tmp.name, members))

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-2、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-6
    def test_区切りの無い登録名が同姓の別人を隠して解決されないこと(self):
        名簿 = self._名簿(
            [
                {"name": "架空", "email": "one@example.com"},  # 区切りの無い1語の登録
                {"name": "架空 一郎", "email": "ichiro@example.com"},
            ]
        )
        self.assertIsNone(名簿.resolve_one("架空"))
        self.assertEqual(
            [c["email"] for c in 名簿.候補("架空")], ["one@example.com", "ichiro@example.com"]
        )

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-6
    def test_登録名が敬称で終わる人を登録どおりに指定できること(self):
        名簿 = self._名簿([{"name": "ハッサン", "email": "hassan@example.com"}])
        # 索引側で「さん」を外すと「ハッ」に潰れて登録どおり打っても解決できなくなる
        self.assertEqual(名簿.resolve_one("ハッサン"), "hassan@example.com")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-2、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-6
    def test_敬称で終わる登録名が別人の名と重なる場合は解決せず候補を示すこと(self):
        名簿 = self._名簿(
            [
                {"name": "ハッサン", "email": "hassan@example.com"},
                {"name": "アリ ハッサン", "email": "ali@example.com"},  # 名が「ハッサン」
            ]
        )
        self.assertIsNone(名簿.resolve_one("ハッサン"))
        self.assertEqual(
            [c["email"] for c in 名簿.候補("ハッサン")], ["hassan@example.com", "ali@example.com"]
        )
        self.assertEqual(名簿.resolve_one("アリ"), "ali@example.com")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-4
    def test_姓と名を読点で区切った登録名を空白区切りで打っても解決すること(self):
        名簿 = self._名簿([{"name": "Dubois, Antoine", "email": "antoine@example.com"}])
        for 打ち方 in ("Dubois, Antoine", "Dubois Antoine", "DuboisAntoine", "dubois antoine"):
            with self.subTest(打ち方=打ち方):
                self.assertEqual(名簿.resolve_one(打ち方), "antoine@example.com")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-2
    def test_nameやemailが空白だけの行は名簿エラーになること(self):
        for 行 in ({"name": "  ", "email": "a@example.com"}, {"name": "A", "email": "  "}):
            with self.subTest(行=行):
                with self.assertRaises(roster.名簿エラー) as cm:
                    self._名簿([行])
                self.assertIn("空白だけ", str(cm.exception))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-7
    def test_同じ人を姓だけとフルネームで挙げても出席者は1人になること(self):
        名簿 = self._名簿([{"name": "架空 一郎", "email": "ichiro@example.com"}])
        結果 = 名簿.resolve(["架空", "架空 一郎", "架空さん"])
        self.assertTrue(結果.ok)
        self.assertEqual(結果.解決済み, [{"name": "架空 一郎", "email": "ichiro@example.com"}])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-5
    def test_同じ名前を複数回指定しても聞き返しが重複しないこと(self):
        名簿 = self._名簿(
            [
                {"name": "架空 一郎", "email": "ichiro@example.com"},
                {"name": "架空 二郎", "email": "jiro@example.com"},
            ]
        )
        結果 = 名簿.resolve(["架空", "架空", "居ない人", "居ない人"])
        self.assertEqual(結果.未解決, ["架空", "居ない人"])
        self.assertEqual(len(結果.候補一覧["架空"]), 2)


class 複数該当時の候補の提示(unittest.TestCase):
    """誰を指定し直せばよいか分からないと、利用者が名簿を自分で開いて調べることになる。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.名簿 = roster.load(
            _名簿を書く(
                self._tmp.name,
                [
                    {"name": "架空 一郎", "email": "ichiro@example.com"},
                    {"name": "架空 二郎", "email": "jiro@example.com"},
                    {"name": "西園寺　彩", "email": "nao@example.com"},
                ],
            )
        )

    def tearDown(self):
        self._tmp.cleanup()

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-5
    def test_複数該当の名前について候補のフルネームとメールアドレスが返ること(self):
        候補 = self.名簿.候補(" 架空さん ")
        self.assertEqual(
            候補,
            [
                {"name": "架空 一郎", "email": "ichiro@example.com"},
                {"name": "架空 二郎", "email": "jiro@example.com"},
            ],
        )

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-5
    def test_登録が無い名前の候補は空であること(self):
        self.assertEqual(self.名簿.候補("居ない人"), [])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-5
    def test_一意に解決できる名前の候補は空であること(self):
        self.assertEqual(self.名簿.候補("西園寺"), [])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-5
    def test_解決結果が未解決の名前ごとの候補を持つこと(self):
        結果 = self.名簿.resolve(["西園寺", "架空", "居ない人"])
        self.assertFalse(結果.ok)
        self.assertEqual(結果.未解決, ["架空", "居ない人"])
        self.assertEqual([c["name"] for c in 結果.候補一覧["架空"]], ["架空 一郎", "架空 二郎"])
        self.assertEqual(結果.候補一覧["居ない人"], [])


class ローマ字表記での照合(unittest.TestCase):
    """OutlookやTeamsの表示名はローマ字の「姓, 名」なので、そこから写した名前でも参加者を指定できるようにする。
    名簿の値は架空の人物。打ち方の例はOutlookの実際の表示名の形(「姓, 名」)に合わせている。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.名簿 = roster.load(
            _名簿を書く(
                self._tmp.name,
                [
                    {"name": "架空　雅寛", "email": "kaku@example.com", "romaji": "Masahiro Kaku"},
                    {"name": "仮名 素彦", "email": "kamei@example.com", "romaji": "Motohiko Kamei"},
                    {"name": "見本 花子", "email": "mihon@example.com"},  # ローマ字の項目自体が無い
                    {"name": "試験 次郎", "email": "shiken@example.com", "romaji": ""},
                    {"name": "例示 三郎", "email": "reiji@example.com", "romaji": "   "},
                    {"name": "長名 太郎", "email": "nagana@example.com", "romaji": "Taro Mid Nagana"},
                ],
            )
        )

    def tearDown(self):
        self._tmp.cleanup()

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-8
    def test_ローマ字のフルネームは名姓と姓名のどちらの並びでも解決すること(self):
        """否定確認: ローマ字のフルネームを「名 姓」の並びだけで持たせると落ちる。"""
        for 打ち方 in ("Masahiro Kaku", "Kaku, Masahiro", "Kaku Masahiro", "KakuMasahiro"):
            with self.subTest(打ち方=打ち方):
                self.assertEqual(self.名簿.resolve_one(打ち方), "kaku@example.com")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-8
    def test_大文字小文字と全角英字の違いは同じ名前として扱うこと(self):
        """否定確認: 照合キーで全角英数字を半角に揃えるのをやめると落ちる。"""
        for 打ち方 in ("KAKU, MASAHIRO", "kaku masahiro", "Ｋａｋｕ，　Ｍａｓａｈｉｒｏ"):
            with self.subTest(打ち方=打ち方):
                self.assertEqual(self.名簿.resolve_one(打ち方), "kaku@example.com")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-8
    def test_ローマ字の姓だけ名だけでも該当が1人なら解決すること(self):
        self.assertEqual(self.名簿.resolve_one("Kamei"), "kamei@example.com")
        self.assertEqual(self.名簿.resolve_one("motohiko"), "kamei@example.com")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-8
    def test_ローマ字で解決しても名簿の氏名で返ること(self):
        結果 = self.名簿.resolve(["Kaku, Masahiro"])
        self.assertEqual(結果.解決済み, [{"name": "架空　雅寛", "email": "kaku@example.com"}])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-8
    def test_3語以上のローマ字は先頭を名末尾を姓とし間の語は照合に使わないこと(self):
        for 打ち方 in ("Taro Nagana", "Nagana, Taro", "Nagana"):
            with self.subTest(打ち方=打ち方):
                self.assertEqual(self.名簿.resolve_one(打ち方), "nagana@example.com")
        self.assertIsNone(self.名簿.resolve_one("Mid"))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-8
    def test_ローマ字表記が無い空空白だけの人は氏名だけで照合されること(self):
        self.assertEqual(self.名簿.resolve_one("見本 花子"), "mihon@example.com")
        self.assertEqual(self.名簿.resolve_one("試験"), "shiken@example.com")
        self.assertEqual(self.名簿.resolve_one("例示 三郎"), "reiji@example.com")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-8
    def test_ローマ字が文字列でない行は名簿エラーになること(self):
        with self.assertRaises(roster.名簿エラー) as cm:
            roster.load(_名簿を書く(self._tmp.name, [{"name": "A", "email": "a@example.com", "romaji": 1}]))
        self.assertIn("romaji", str(cm.exception))


class 氏名とローマ字の該当の合算(unittest.TestCase):
    """片方を優先して打ち切ると、別人が候補にも現れないまま1人に確定してしまう。"""

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-6、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-5
    def test_氏名で該当する人とローマ字で該当する別人がいれば解決せず両方を候補に示すこと(self):
        with tempfile.TemporaryDirectory() as d:
            名簿 = roster.load(
                _名簿を書く(
                    d,
                    [
                        {"name": "Smith, John", "email": "john@example.com"},  # 氏名欄が英字の人
                        {"name": "架空 一郎", "email": "ichiro@example.com", "romaji": "Ichiro Smith"},
                    ],
                )
            )
        self.assertIsNone(名簿.resolve_one("Smith"))
        self.assertEqual(
            sorted(c["email"] for c in 名簿.候補("Smith")), ["ichiro@example.com", "john@example.com"]
        )


class 末尾の番号を外した照合(unittest.TestCase):
    """Outlookは同姓同名を区別するために表示名の末尾へ番号を付ける(例: 「Baba, Masahiro 1」の「1」)。
    番号は名簿のローマ字表記に含まれないので外して照合するが、別人を区別する印でもあるため、
    外して解決したことを呼び出し側が分かるようにし、複数人が該当したら番号で絞らずに聞き返す。
    """

    def _名簿(self, members):
        return roster.load(_名簿を書く(self._tmp.name, members))

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-9
    def test_末尾の番号は直前の空白の有無や全角半角を問わず外して照合すること(self):
        名簿 = self._名簿([{"name": "架空 雅寛", "email": "kaku@example.com", "romaji": "Masahiro Kaku"}])
        for 打ち方 in ("Kaku, Masahiro 1", "Kaku, Masahiro1", "Kaku, Masahiro １２", "Kaku 2"):
            with self.subTest(打ち方=打ち方):
                self.assertEqual(名簿.resolve_one(打ち方), "kaku@example.com")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-9
    def test_番号を外して解決した参加者は解決結果でその旨が分かること(self):
        """否定確認: 番号を外した段で解決した人を記録しないようにすると落ちる。"""
        名簿 = self._名簿(
            [
                {"name": "架空 雅寛", "email": "kaku@example.com", "romaji": "Masahiro Kaku"},
                {"name": "仮名 素彦", "email": "kamei@example.com", "romaji": "Motohiko Kamei"},
            ]
        )
        結果 = 名簿.resolve(["Kaku, Masahiro 1", "Kamei, Motohiko"])
        self.assertTrue(結果.ok)
        self.assertEqual(結果.番号を外して解決, {"kaku@example.com"})

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-9、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-6
    def test_番号まで含めて一致する登録があれば番号を外した照合に進まないこと(self):
        """否定確認: 番号を外した照合を最初の段に移すと落ちる。"""
        名簿 = self._名簿(
            [
                {"name": "架空 1号", "email": "one@example.com", "romaji": "Kaku1"},
                {"name": "架空 雅寛", "email": "kaku@example.com", "romaji": "Masahiro Kaku"},
            ]
        )
        結果 = 名簿.resolve(["Kaku1"])
        self.assertEqual(結果.解決済み, [{"name": "架空 1号", "email": "one@example.com"}])
        self.assertEqual(結果.番号を外して解決, set())

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-9、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-5
    def test_番号を外して複数人が該当したら番号で絞らずに候補を示すこと(self):
        """否定確認: 解決できなかった名前の候補を常に空にすると落ちる。"""
        名簿 = self._名簿(
            [
                {"name": "架空 雅寛", "email": "kaku-a@example.com", "romaji": "Masahiro Kaku"},
                {"name": "架空 雅寛", "email": "kaku-b@example.com", "romaji": "Masahiro Kaku"},
            ]
        )
        結果 = 名簿.resolve(["Kaku, Masahiro 1"])
        self.assertFalse(結果.ok)
        self.assertEqual(
            [c["email"] for c in 結果.候補一覧["Kaku, Masahiro 1"]],
            ["kaku-a@example.com", "kaku-b@example.com"],
        )

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-9
    def test_数字だけの名前は照合しないこと(self):
        名簿 = self._名簿([{"name": "架空 雅寛", "email": "kaku@example.com", "romaji": "Masahiro Kaku"}])
        self.assertIsNone(名簿.resolve_one("1"))
        self.assertEqual(名簿.候補("１２"), [])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#参加者の解決-9
    def test_敬称と番号の両方が付いた名前は一方だけしか外さないため解決しないこと(self):
        名簿 = self._名簿([{"name": "架空 雅寛", "email": "kaku@example.com", "romaji": "Masahiro Kaku"}])
        self.assertIsNone(名簿.resolve_one("Kakuさん 1"))
        self.assertIsNone(名簿.resolve_one("Kaku 1さん"))


if __name__ == "__main__":
    unittest.main()
