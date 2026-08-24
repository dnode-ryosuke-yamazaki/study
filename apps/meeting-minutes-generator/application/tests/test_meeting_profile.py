"""会議の性質の判定(タスク9)のテスト。

会議種別ごとに議事録の見出し構成が変わるため、判定を1箇所に集めたこのモジュールが
「指示する見出し」「検証する見出し」「投稿する見出し」の唯一の情報源になる。
ここがずれると、生成した議事録が毎回検証NGになり再試行上限で対象外化する。
"""

import unittest

import meeting_profile

判定語 = ("デイリー", "daily", "朝会")


def _vtt(*, 分: int, 秒: int = 0) -> str:
    """指定した実尺のトランスクリプトを作る(終了時刻だけが判定に効く)。"""
    return (
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:02.000\n<v 山田>おはようございます\n\n"
        f"00:00:03.000 --> {分 // 60:02d}:{分 % 60:02d}:{秒:02d}.500\n<v 佐藤>よろしく\n"
    )


class デイリー系会議の判定(unittest.TestCase):
    """定期進捗確認の会議を、上流が付けるVTTファイル名から見分けられることを検証する。"""

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#会議種別による構成の切り替え-1
    def test_判定語を含むファイル名がデイリー系になること(self):
        性質 = meeting_profile.見極める(
            "[AI FaaS] デイリーMTG（縮小体制）-20260727_020021UTC-Meeting Recording1.vtt",
            _vtt(分=28),
            判定語,
        )
        self.assertTrue(性質.デイリー系)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#会議種別による構成の切り替え-1
    def test_大文字小文字を区別せずに判定されること(self):
        """実例に「共通インフラDaily」があるため、英字の大小で取りこぼさない。"""
        性質 = meeting_profile.見極める(
            "[AI FaaS] 共通インフラDaily-20260722_052929UTC-Meeting Recording1.vtt",
            _vtt(分=28),
            判定語,
        )
        self.assertTrue(性質.デイリー系)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#会議種別による構成の切り替え-4
    def test_判定語を含まないファイル名は通常の会議になること(self):
        性質 = meeting_profile.見極める("AIニュースレター確認-20260819.vtt", _vtt(分=28), 判定語)
        self.assertFalse(性質.デイリー系)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#会議種別による構成の切り替え-1
    def test_判定語が空なら通常の会議として扱われること(self):
        性質 = meeting_profile.見極める("デイリーMTG.vtt", _vtt(分=28), ())
        self.assertFalse(性質.デイリー系)


class 会議の実尺(unittest.TestCase):
    """要約の分量上限を決めるための実尺を、トランスクリプトから求められることを検証する。"""

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の記載内容-7
    def test_タイムスタンプの終了時刻の最大値から実尺が求まること(self):
        self.assertEqual(meeting_profile.会議の実尺分(_vtt(分=28, 秒=13)), 28)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の記載内容-7
    def test_時間の桁がないタイムスタンプも読めること(self):
        """WEBVTTは `mm:ss.mmm` 形式も許すため、短い会議で桁が落ちても読めること。"""
        本文 = "WEBVTT\n\n00:01.000 --> 12:34.500\n<v 山田>はい\n"
        self.assertEqual(meeting_profile.会議の実尺分(本文), 12)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の記載内容-7
    def test_タイムスタンプが1つも無ければ不明になること(self):
        self.assertIsNone(meeting_profile.会議の実尺分("WEBVTT\n\n<v 山田>はい\n"))


class 要約の上限(unittest.TestCase):
    """実尺に応じて要約の分量上限が3段階で変わることを検証する。

    上限が厳しすぎると長い会議の要点が落ち、緩すぎるとTeams投稿が読めなくなる。
    """

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の記載内容-6
    def test_30分以下は3から5点で300字以内になること(self):
        上限 = meeting_profile.要約の上限を決める(28)
        self.assertEqual(上限.字数, 300)
        self.assertIn("3", 上限.点数)
        self.assertIn("5", 上限.点数)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の記載内容-6
    def test_30分ちょうどは厳しい側の段が使われること(self):
        self.assertEqual(meeting_profile.要約の上限を決める(30).字数, 300)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の記載内容-6
    def test_30分超60分以下は最大7点で500字以内になること(self):
        上限 = meeting_profile.要約の上限を決める(45)
        self.assertEqual(上限.字数, 500)
        self.assertIn("7", 上限.点数)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の記載内容-6
    def test_60分超は最大10点で800字以内になること(self):
        上限 = meeting_profile.要約の上限を決める(90)
        self.assertEqual(上限.字数, 800)
        self.assertIn("10", 上限.点数)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の記載内容-7
    def test_実尺が不明なら最も厳しい段が使われること(self):
        self.assertEqual(meeting_profile.要約の上限を決める(None).字数, 300)


class 見出し構成の導出(unittest.TestCase):
    """会議種別から必須見出しと投稿する見出しが導かれることを検証する。

    投稿する見出しを必須見出しから導くことで、見出し構成を変えたときに
    投稿側の追随漏れが起きないようにしている。
    """

    def setUp(self):
        self.デイリー = meeting_profile.見極める("デイリーMTG.vtt", _vtt(分=28), 判定語)
        self.通常 = meeting_profile.見極める("定例会議.vtt", _vtt(分=28), 判定語)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の生成-2
    def test_通常の会議は進捗を含まない6見出しになること(self):
        self.assertEqual(
            self.通常.必須見出し,
            ("会議メタ情報", "要約", "決定事項", "TODO", "議論の経緯", "未決事項・次回議題"),
        )

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#会議種別による構成の切り替え-2
    def test_デイリー系は要約と決定事項の間に進捗が入る7見出しになること(self):
        self.assertEqual(
            self.デイリー.必須見出し,
            (
                "会議メタ情報",
                "要約",
                "進捗",
                "決定事項",
                "TODO",
                "議論の経緯",
                "未決事項・次回議題",
            ),
        )

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#teamsへの共有-1
    def test_投稿する見出しは議論の経緯と未決事項を除いたものになること(self):
        self.assertEqual(self.通常.投稿する見出し, ("会議メタ情報", "要約", "決定事項", "TODO"))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#teamsへの共有-1
    def test_デイリー系では進捗が投稿する見出しに含まれること(self):
        self.assertEqual(
            self.デイリー.投稿する見出し,
            ("会議メタ情報", "要約", "進捗", "決定事項", "TODO"),
        )

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#ログ
    def test_ログ用に会議種別の名前が取れること(self):
        self.assertEqual(self.デイリー.種別の名前, "デイリー系")
        self.assertEqual(self.通常.種別の名前, "通常")


if __name__ == "__main__":
    unittest.main()
