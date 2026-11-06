import datetime as dt
import unittest

from tests.runner.support import DAILY, publish_entry, review_entry

from digest_runner import calendar as cal

JST = dt.timezone(dt.timedelta(hours=9))
UTC = dt.timezone.utc


def weekly(editions=None):
    reg = publish_entry("research-digest", [6], edition_by_weekday=editions)
    reg.update(app="research-digest", kind="publish")
    return reg


def daily(editions=None):
    reg = publish_entry("ai-dev-digest", DAILY, edition_by_weekday=editions)
    reg.update(app="ai-dev-digest", kind="publish")
    return reg


def at(y, m, d, hh, mm, tz=JST):
    return dt.datetime(y, m, d, hh, mm, tzinfo=tz)


class 配信日と編の決定(unittest.TestCase):
    """実行係はバッチを起動する前に、どの配信日・編の実行状態を見るかを自分で決める。
    深夜や何日か後にずれた追い実行を、元の配信日の回として数えるため(2026-11-07 は土曜)。"""

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-5
    def test_配信曜日の0630以後に起動するとその日が配信日になり曜日の編が付く(self):
        self.assertEqual(cal.resolve(weekly({"6": "sci"}), at(2026, 11, 7, 6, 30)), ("2026-11-07", "sci"))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-5
    def test_同じ日の0629の起動は前日の回になる(self):
        """否定確認: 06:30 との比較を <= に変えると 06:30 ちょうどの側が、比較を消すとこちらが落ちる"""
        self.assertEqual(cal.resolve(daily(), at(2026, 11, 7, 6, 29)), ("2026-11-06", None))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-5
    def test_週1回のアプリを翌日の日中に起動すると前の配信曜日の配信日と編になる(self):
        """否定確認: 配信曜日まで遡る処理を消すと落ちる"""
        self.assertEqual(cal.resolve(weekly({"6": "sci"}), at(2026, 11, 8, 12, 0)), ("2026-11-07", "sci"))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-5
    def test_週1回のアプリを3日後に起動しても同じ配信日になる(self):
        self.assertEqual(cal.resolve(weekly(), at(2026, 11, 10, 12, 0)), ("2026-11-07", None))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-5
    def test_毎日のアプリを翌日の0030に起動すると前日の回になる(self):
        self.assertEqual(cal.resolve(daily(), at(2026, 11, 8, 0, 30)), ("2026-11-07", None))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-5
    def test_協定世界時では前日の深夜でも日本時間の朝なら日本時間の日付で決まる(self):
        """否定確認: 日本時間への変換を外すと落ちる"""
        self.assertEqual(cal.resolve(daily(), at(2026, 11, 6, 21, 40, UTC)), ("2026-11-07", None))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-5
    def test_編を持たないアプリは配信日だけで決まる(self):
        self.assertEqual(cal.resolve(daily(None), at(2026, 11, 7, 10, 30)), ("2026-11-07", None))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-5
    def test_曜日と編の対応に配信日の曜日が無ければ編なしになる(self):
        self.assertEqual(cal.resolve(daily({"1": "mon"}), at(2026, 11, 7, 10, 30)), ("2026-11-07", None))
        self.assertEqual(cal.resolve(daily({"1": "mon"}), at(2026, 11, 9, 10, 30)), ("2026-11-09", "mon"))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-5
    def test_月次見直しの配信日は基準日で編を持たない(self):
        reg = review_entry("research-digest", 1)
        reg.update(app="research-digest", kind="review")
        self.assertEqual(cal.resolve(reg, at(2026, 11, 8, 7, 30)), ("2026-11-08", None))
        self.assertEqual(cal.resolve(reg, at(2026, 11, 8, 6, 0)), ("2026-11-07", None))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-5
    def test_一週間のどの時刻に起動しても配信日は基準日以前の直近の配信曜日になる(self):
        """性質テストの代わりに、1週間を30分刻みで列挙して確かめる"""
        for weekdays in ([6], [0], DAILY, [1, 4]):
            reg = publish_entry("x", weekdays)
            reg.update(app="x", kind="publish")
            start = at(2026, 11, 2, 0, 0)
            for step in range(7 * 48):
                now = start + dt.timedelta(minutes=30 * step)
                date, _ = cal.resolve(reg, now)
                d = dt.date.fromisoformat(date)
                base = now.date() if now.time() >= dt.time(6, 30) else now.date() - dt.timedelta(days=1)
                self.assertIn((d.weekday() + 1) % 7, weekdays, (weekdays, now))
                self.assertLessEqual(d, base)
                self.assertGreater(d, base - dt.timedelta(days=7))
                for gap in range(1, (base - d).days + 1):
                    between = d + dt.timedelta(days=gap)
                    self.assertNotIn((between.weekday() + 1) % 7, weekdays, (weekdays, now))


class 最後の機会の時刻と直前の配信日(unittest.TestCase):
    """再実行の判定は配信日の 18:30 と起動時刻を比べる。記録の無い回の締めは直前の配信日を見る。"""

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-7
    def test_配信日の1830が日本時間で返る(self):
        got = cal.last_chance_at("2026-11-07")
        self.assertEqual(got, at(2026, 11, 7, 18, 30))
        self.assertEqual(got.utcoffset(), dt.timedelta(hours=9))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-9
    def test_直前の配信日は毎日のアプリなら前日で週1回のアプリなら7日前になる(self):
        self.assertEqual(cal.previous_delivery_date(daily(), "2026-11-07"), "2026-11-06")
        self.assertEqual(cal.previous_delivery_date(weekly(), "2026-11-07"), "2026-10-31")
        self.assertEqual(cal.edition_for(weekly({"6": "sci"}), "2026-10-31"), "sci")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-5
    def test_現在時刻は実行環境の時間帯によらず日本時間で返る(self):
        now = cal.now_jst()
        self.assertEqual(now.utcoffset(), dt.timedelta(hours=9))
        self.assertLess(abs((now - dt.datetime.now(UTC)).total_seconds()), 5)


if __name__ == "__main__":
    unittest.main()
