"""候補の絞り込み(tasks.md 8)のテスト。

探索フローが返す枠は世界標準時で、時間帯・曜日・祝日の絞り込みは効いていない。
日本時間に変換してから、時間帯・祝日・曜日・全員空き・重複の順に絞り、上限件数まで採用する。
全員空きの判定は出席可能率ではなく、出席者ごとの空き状況と開催者の空き状況の両方で行う
(下限100%でも仮の予定を含む枠が返るため)。
"""

import unittest
from datetime import date, datetime, time, timedelta, timezone

import candidates

JST = timezone(timedelta(hours=9))


def _枠(開始jst: datetime, 分=60, 出席者=("free", "free"), 開催者="free", アドレス=None):
    """日本時間で指定した枠を、フローが返す形(世界標準時・オフセット無し・7桁小数)にする。"""
    開始utc = 開始jst.astimezone(timezone.utc)
    終了utc = 開始utc + timedelta(minutes=分)
    アドレス = アドレス or [f"p{i}@example.com" for i in range(len(出席者))]
    return {
        "confidence": 100.0,
        "organizerAvailability": 開催者,
        "meetingTimeSlot": {
            "start": {"dateTime": 開始utc.strftime("%Y-%m-%dT%H:%M:%S.0000000"), "timeZone": "UTC"},
            "end": {"dateTime": 終了utc.strftime("%Y-%m-%dT%H:%M:%S.0000000"), "timeZone": "UTC"},
        },
        "attendeeAvailability": [
            {"attendee": {"emailAddress": {"address": a}}, "availability": s}
            for a, s in zip(アドレス, 出席者)
        ],
    }


def _候補ファイル(枠一覧, 理由="", 失敗="", 試行=1):
    return {
        "requestId": "X",
        "attempt": 試行,
        "meetingTimeSuggestions": 枠一覧,
        "emptySuggestionsReason": 理由,
        "error": 失敗,
    }


既定条件 = candidates.絞り込み条件(
    時間帯開始=time(9, 30), 時間帯終了=time(17, 30), 対象曜日=(0, 1, 2, 3, 4), 全員空き=True, 上限件数=5
)


class 候補ファイルの読み取り(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#候補ファイルの区分
    def test_枠の一覧と枠が無かった理由と失敗理由を取り出せること(self):
        読み = candidates.読む(_候補ファイル([_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST))], 理由="", 失敗=""))
        self.assertEqual(len(読み.枠一覧), 1)
        self.assertEqual(読み.枠が無かった理由, "")
        self.assertEqual(読み.失敗理由, "")
        self.assertFalse(読み.失敗)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#エラーハンドリング
    def test_失敗理由が入っている候補ファイルは絞り込みへ進まない結果として返ること(self):
        読み = candidates.読む(_候補ファイル([], 失敗="Connector failed"))
        self.assertTrue(読み.失敗)
        self.assertEqual(読み.失敗理由, "Connector failed")

    def test_枠が0件のときは理由を取り出せること(self):
        読み = candidates.読む(_候補ファイル([], 理由="OrganizerUnavailable"))
        self.assertEqual(読み.枠一覧, [])
        self.assertEqual(読み.枠が無かった理由, "OrganizerUnavailable")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補の提示-1
    def test_世界標準時で届いた枠の開始と終了が日本時間に変換されていること(self):
        読み = candidates.読む(_候補ファイル([_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST))]))
        枠 = 読み.枠一覧[0]
        self.assertEqual(枠.開始, datetime(2026, 9, 10, 10, 0, tzinfo=JST))
        self.assertEqual(枠.終了, datetime(2026, 9, 10, 11, 0, tzinfo=JST))
        self.assertEqual(枠.試行番号, 1)


class 時間帯と曜日と祝日の絞り込み(unittest.TestCase):

    def _絞る(self, 枠一覧, 条件=既定条件, 仮を空きとみなす=False):
        return candidates.絞り込む(candidates.読む(_候補ファイル(枠一覧)), 条件, 仮を空きとみなす=仮を空きとみなす)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#8-候補の絞り込みcandidatespy
    def test_日本時間に変換してから時間帯を判定し変換前の時刻で判定しないこと(self):
        # 日本時間10:00の枠は世界標準時では01:00。変換せずに判定すると時間帯外として弾かれる
        結果 = self._絞る([_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST))])
        self.assertEqual(len(結果.採用), 1)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補探索の既定条件-1
    def test_開始から終了までが時間帯に収まらない枠を除くこと(self):
        結果 = self._絞る(
            [
                _枠(datetime(2026, 9, 10, 9, 0, tzinfo=JST)),   # 9:00-10:00 開始が時間帯より前
                _枠(datetime(2026, 9, 10, 17, 0, tzinfo=JST)),  # 17:00-18:00 終了が時間帯より後
                _枠(datetime(2026, 9, 10, 16, 30, tzinfo=JST)),  # 16:30-17:30 ちょうど収まる
                _枠(datetime(2026, 9, 10, 9, 30, tzinfo=JST)),  # 9:30-10:30 ちょうど収まる
            ]
        )
        self.assertEqual([枠.開始.hour for 枠 in 結果.採用], [9, 16])
        self.assertEqual(結果.除外内訳["時間帯外"], 2)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補探索の既定条件-2
    def test_祝日にかかる枠を除くこと(self):
        結果 = self._絞る(
            [
                _枠(datetime(2026, 9, 21, 10, 0, tzinfo=JST)),  # 敬老の日(月)
                _枠(datetime(2026, 9, 22, 10, 0, tzinfo=JST)),  # 国民の休日(火)
                _枠(datetime(2026, 9, 24, 10, 0, tzinfo=JST)),  # 木曜・平日
            ]
        )
        self.assertEqual([枠.開始.date() for 枠 in 結果.採用], [date(2026, 9, 24)])
        self.assertEqual(結果.除外内訳["祝日"], 2)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補探索の既定条件-2
    def test_曜日の指定がない場合は土曜と日曜の枠を除くこと(self):
        結果 = self._絞る(
            [
                _枠(datetime(2026, 9, 11, 10, 0, tzinfo=JST)),  # 金
                _枠(datetime(2026, 9, 12, 10, 0, tzinfo=JST)),  # 土
                _枠(datetime(2026, 9, 13, 10, 0, tzinfo=JST)),  # 日
            ]
        )
        self.assertEqual([枠.開始.weekday() for 枠 in 結果.採用], [4])
        self.assertEqual(結果.除外内訳["曜日外"], 2)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補探索の既定条件-2
    def test_曜日を指定された場合はその指定に従い土曜や日曜も候補になりうること(self):
        条件 = candidates.絞り込み条件(
            時間帯開始=time(9, 30), 時間帯終了=time(17, 30), 対象曜日=(5, 6), 全員空き=True, 上限件数=5
        )
        結果 = self._絞る(
            [
                _枠(datetime(2026, 9, 11, 10, 0, tzinfo=JST)),  # 金
                _枠(datetime(2026, 9, 12, 10, 0, tzinfo=JST)),  # 土
                _枠(datetime(2026, 9, 13, 10, 0, tzinfo=JST)),  # 日
            ],
            条件,
        )
        self.assertEqual([枠.開始.weekday() for 枠 in 結果.採用], [5, 6])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補探索の既定条件-2
    def test_曜日を指定しても祝日は常に除くこと(self):
        条件 = candidates.絞り込み条件(
            時間帯開始=time(9, 30), 時間帯終了=time(17, 30), 対象曜日=(0,), 全員空き=True, 上限件数=5
        )
        結果 = self._絞る([_枠(datetime(2026, 9, 21, 10, 0, tzinfo=JST))], 条件)  # 敬老の日(月)
        self.assertEqual(結果.採用, [])


class 全員空きの判定(unittest.TestCase):

    def _絞る(self, 枠一覧, 条件=既定条件, 仮を空きとみなす=False):
        return candidates.絞り込む(candidates.読む(_候補ファイル(枠一覧)), 条件, 仮を空きとみなす=仮を空きとみなす)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補探索の既定条件-3、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-1
    def test_出席者の空き状況がすべて空きで開催者も空きの枠だけを採用し開催者だけが仮の枠は開催者のみ不在に分けること(self):
        """否定確認: 開催者のみ不在の判定を外すと、15:00の枠が「全員空きでない」に数えられて落ちる。"""
        結果 = self._絞る(
            [
                _枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 出席者=("free", "free"), 開催者="free"),
                _枠(datetime(2026, 9, 10, 13, 0, tzinfo=JST), 出席者=("free", "busy"), 開催者="free"),
                _枠(datetime(2026, 9, 10, 15, 0, tzinfo=JST), 出席者=("free", "free"), 開催者="tentative"),
            ]
        )
        self.assertEqual([枠.開始.hour for 枠 in 結果.採用], [10])
        self.assertEqual(結果.除外内訳["全員空きでない"], 1)
        self.assertEqual([枠.開始.hour for 枠 in 結果.開催者のみ不在], [15])
        self.assertEqual(結果.除外内訳["開催者のみ不在"], 1)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補探索の既定条件-5
    def test_仮の予定が入っている出席者を含む枠は出席可能率が100でも採用しないこと(self):
        結果 = self._絞る([_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 出席者=("free", "tentative"))])
        self.assertEqual(結果.採用, [])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補探索の既定条件-3
    def test_全員空きを求めない指示がある場合は空き状況で除外しないこと(self):
        条件 = candidates.絞り込み条件(
            時間帯開始=time(9, 30), 時間帯終了=time(17, 30), 対象曜日=(0, 1, 2, 3, 4), 全員空き=False, 上限件数=5
        )
        結果 = self._絞る([_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 出席者=("free", "busy"))], 条件)
        self.assertEqual(len(結果.採用), 1)
        self.assertEqual(結果.採用[0].空いていない人数, 1)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-1
    def test_仮の予定を空きとみなす条件では開催者以外に仮の予定がある枠だけを採用し予約済みと開催者だけが仮の枠は除くこと(self):
        """否定確認: 代替案1の対象の判定から「開催者以外に仮がいる」の条件を外すと13:00の枠が採用されて落ちる。"""
        結果 = self._絞る(
            [
                _枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 出席者=("free", "tentative")),
                _枠(datetime(2026, 9, 10, 13, 0, tzinfo=JST), 出席者=("free", "free"), 開催者="tentative"),
                _枠(datetime(2026, 9, 10, 14, 0, tzinfo=JST), 出席者=("tentative", "free"), 開催者="tentative"),
                _枠(datetime(2026, 9, 10, 15, 0, tzinfo=JST), 出席者=("busy", "free")),
                _枠(datetime(2026, 9, 10, 16, 0, tzinfo=JST), 出席者=("tentative", "busy")),
            ],
            仮を空きとみなす=True,
        )
        self.assertEqual([枠.開始.hour for 枠 in 結果.採用], [10, 14])
        self.assertEqual(結果.開催者のみ不在, [])  # 代替案1の絞り直しでは切り出さない

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-2、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-3
    def test_絞り直した枠ごとに仮の予定を持つ参加者の一覧が返り開催者自身の仮も分かること(self):
        結果 = self._絞る(
            [
                _枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 出席者=("free", "tentative"),
                   アドレス=["a@example.com", "b@example.com"]),
                _枠(datetime(2026, 9, 10, 13, 0, tzinfo=JST), 出席者=("free", "tentative"), 開催者="tentative",
                   アドレス=["a@example.com", "b@example.com"]),
            ],
            仮を空きとみなす=True,
        )
        self.assertEqual(結果.採用[0].仮の参加者, ["b@example.com"])
        self.assertEqual(結果.採用[0].開催者が仮, False)
        self.assertEqual(結果.採用[1].仮の参加者, ["b@example.com"])
        self.assertEqual(結果.採用[1].開催者が仮, True)


class 開催者のみ不在の枠の切り出し(unittest.TestCase):
    """参加者全員は空いていて開催者だけが空き以外の枠を、候補には数えずに別の一覧として持つ。
    開催者が自分の予定を動かせば開けられる枠なので、候補と取り違えずに判断材料として示す。
    """

    def _絞る(self, 枠一覧, 条件=既定条件, 仮を空きとみなす=False):
        return candidates.絞り込む(candidates.読む(_候補ファイル(枠一覧)), 条件, 仮を空きとみなす=仮を空きとみなす)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-1
    def test_出席者全員が空きで開催者だけが空き以外の枠が採用とは別の一覧に分かれ出席者に空き以外がいる枠は分かれないこと(self):
        """否定確認: 開催者の空き状況の比較を `== 空き` に反転すると、空きの枠まで分けられて落ちる。"""
        開催者の値 = ["tentative", "busy", "oof", "workingElsewhere", "unknown", " Busy "]
        枠一覧 = [_枠(datetime(2026, 9, 10, 10 + i, 0, tzinfo=JST), 開催者=v) for i, v in enumerate(開催者の値)]
        枠一覧.append(_枠(datetime(2026, 9, 11, 10, 0, tzinfo=JST), 出席者=("tentative", "free"), 開催者="busy"))
        枠一覧.append(_枠(datetime(2026, 9, 11, 11, 0, tzinfo=JST), 出席者=("free", "free"), 開催者="free"))
        条件 = candidates.絞り込み条件(
            時間帯開始=time(9, 30), 時間帯終了=time(17, 30), 対象曜日=(0, 1, 2, 3, 4), 全員空き=True, 上限件数=10
        )
        結果 = self._絞る(枠一覧, 条件)
        self.assertEqual([w.開始.hour for w in 結果.採用], [11])
        self.assertEqual(len(結果.開催者のみ不在), len(開催者の値))
        self.assertEqual({w.開催者空き for w in 結果.開催者のみ不在}, {"tentative", "busy", "oof", "workingelsewhere", "unknown"})
        self.assertEqual(結果.除外内訳["全員空きでない"], 1)  # 出席者に仮がいる枠は開催者のみ不在に入らない

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-1、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-4
    def test_開催者のみ不在の枠にも曜日と時間帯と祝日の条件が効き開始時刻順で上限件数までに収まること(self):
        枠一覧 = [
            _枠(datetime(2026, 9, 12, 10, 0, tzinfo=JST), 開催者="busy"),  # 土曜
            _枠(datetime(2026, 9, 10, 8, 0, tzinfo=JST), 開催者="busy"),  # 時間帯外
            _枠(datetime(2026, 9, 21, 10, 0, tzinfo=JST), 開催者="busy"),  # 敬老の日
        ] + [_枠(datetime(2026, 9, 10, 16 - i, 0, tzinfo=JST), 開催者="tentative") for i in range(7)]  # 10:00〜16:00を逆順で
        結果 = self._絞る(枠一覧)
        self.assertEqual(結果.採用, [])
        self.assertEqual([w.開始.hour for w in 結果.開催者のみ不在], [10, 11, 12, 13, 14])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-4
    def test_開催者のみ不在の枠どうしは時間の重なる枠の先のものだけが残り採用した候補と重なっても除かれないこと(self):
        """否定確認: 候補の重複除外を開催者のみ不在の枠にまたいで適用すると、10:00の枠が消えて落ちる。"""
        結果 = self._絞る(
            [
                _枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST)),  # 採用される候補 10:00-11:00
                _枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 開催者="busy"),  # 候補と同じ時間の開催者のみ不在
                _枠(datetime(2026, 9, 10, 10, 30, tzinfo=JST), 開催者="busy"),  # 上の枠と重なる → 除く
                _枠(datetime(2026, 9, 10, 11, 0, tzinfo=JST), 開催者="busy"),  # 接するだけ → 残る
            ]
        )
        self.assertEqual([w.開始.hour for w in 結果.採用], [10])
        self.assertEqual([(w.開始.hour, w.開始.minute) for w in 結果.開催者のみ不在], [(10, 0), (11, 0)])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-1
    def test_全員空きを求めない依頼では開催者のみ不在の一覧が空になること(self):
        条件 = candidates.絞り込み条件(
            時間帯開始=time(9, 30), 時間帯終了=time(17, 30), 対象曜日=(0, 1, 2, 3, 4), 全員空き=False, 上限件数=5
        )
        結果 = self._絞る([_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 開催者="busy")], 条件)
        self.assertEqual(len(結果.採用), 1)
        self.assertEqual(結果.開催者のみ不在, [])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#開催者の予定のみ重なる枠の提示-2
    def test_開催者のみ不在の枠は採用件数に数えず受け取った件数には含まれること(self):
        結果 = self._絞る([_枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 開催者="busy")])
        self.assertEqual(結果.採用, [])
        self.assertEqual(結果.受け取った件数, 1)
        self.assertEqual(len(結果.開催者のみ不在), 1)


class 並び順と重複と上限(unittest.TestCase):

    def _絞る(self, 枠一覧, 条件=既定条件):
        return candidates.絞り込む(candidates.読む(_候補ファイル(枠一覧)), 条件)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補探索の既定条件-4
    def test_開始の早い順に並べ既に採用した枠と時間が重なる枠を除くこと(self):
        結果 = self._絞る(
            [
                _枠(datetime(2026, 9, 10, 11, 0, tzinfo=JST)),  # 11:00-12:00
                _枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST)),  # 10:00-11:00
                _枠(datetime(2026, 9, 10, 10, 30, tzinfo=JST)),  # 10:30-11:30 10:00の枠と重なる
            ]
        )
        self.assertEqual([枠.開始.hour for 枠 in 結果.採用], [10, 11])  # 11:00は10:00-11:00と接するだけで重ならない
        self.assertEqual(結果.除外内訳["重複"], 1)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補探索の既定条件-4
    def test_上限件数まで採用し同じ日に複数の枠が残ってもそのまま採用すること(self):
        枠一覧 = [_枠(datetime(2026, 9, 10, 10 + i, 0, tzinfo=JST)) for i in range(7)]  # 10:00〜16:00 の7枠
        結果 = self._絞る(枠一覧)
        self.assertEqual(len(結果.採用), 5)
        self.assertEqual(len({枠.開始.date() for 枠 in 結果.採用}), 1)
        self.assertEqual(結果.受け取った件数, 7)

    def test_除外の内訳が理由ごとの件数で返ること(self):
        結果 = self._絞る(
            [
                _枠(datetime(2026, 9, 12, 10, 0, tzinfo=JST)),  # 土
                _枠(datetime(2026, 9, 10, 8, 0, tzinfo=JST)),  # 時間帯外
                _枠(datetime(2026, 9, 10, 10, 0, tzinfo=JST), 出席者=("busy", "free")),
            ]
        )
        self.assertEqual(結果.採用, [])
        self.assertEqual(結果.除外内訳["曜日外"], 1)
        self.assertEqual(結果.除外内訳["時間帯外"], 1)
        self.assertEqual(結果.除外内訳["全員空きでない"], 1)


class 依頼ファイルからの条件の復元(unittest.TestCase):

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#台帳ファイルの扱い-5
    def test_依頼ファイルの絞り込みの条件から同じ条件を復元できること(self):
        依頼 = {
            "filter": {
                "timeWindowStart": "09:30", "timeWindowEnd": "18:30",
                "weekdays": [0, 2], "requireAllFree": False, "maxResults": 3,
            }
        }
        条件 = candidates.絞り込み条件.依頼から(依頼)
        self.assertEqual(条件.時間帯開始, time(9, 30))
        self.assertEqual(条件.時間帯終了, time(18, 30))
        self.assertEqual(条件.対象曜日, (0, 2))
        self.assertFalse(条件.全員空き)
        self.assertEqual(条件.上限件数, 3)


if __name__ == "__main__":
    unittest.main()
