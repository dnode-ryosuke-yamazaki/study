import datetime as dt
import os
import sys
import types
import unittest

from tests.runner.handoff_support import FAILURE_KEYS, JST, FakeJudge, attempt, put_state, read_state
from tests.runner.support import DAILY, TempDirTestCase, publish_entry, review_entry

from digest_runner import handoff, state

NOW = dt.datetime(2026, 11, 8, 6, 30, 1, tzinfo=JST)


class HandoffTestCase(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.data_dir = self.path("digest", "research-digest")
        self.summary = os.path.join(self.data_dir, "runner-publish.log")
        self.runs = os.path.join(self.data_dir, "runs", "publish")

    def ctx(self, manual=False, app="research-digest", kind="publish"):
        return {"app": app, "kind": kind, "manual": manual, "summary_path": self.summary}

    def summary_lines(self):
        if not os.path.exists(self.summary):
            return []
        with open(self.summary, encoding="utf-8") as f:
            return f.read().splitlines()


class 失敗通知への引き渡しと結果の記録(HandoffTestCase):
    """通知するかどうかの判定は失敗通知に委ね、実行係は決まった12項目を渡して返った結果を実行状態に残す。
    通知できなかったときも実行係は落ちず、要約ログに失敗の印を残して次の起動で渡し直せるようにする。"""

    def exhausted_state(self, **over):
        data = state.empty("research-digest", "publish", "2026-11-07", None, 4)
        for no in range(1, 5):
            state.add_attempt(data, attempt(no, log=f"/d/logs/publish/2026-11-07-{no}.log"))
        state.set_status(data, "failed", "exhausted")
        data.update(over)
        return data

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#失敗の引き渡し-1
    def test_失敗確定のとき12項目がそろって確定の理由とともに渡る(self):
        data = self.exhausted_state()
        failure = handoff.build(self.ctx(), data, "temporary_failure", "exhausted",
                                dt.datetime(2026, 11, 7, 18, 41, 11, tzinfo=JST), "/d/logs/publish/2026-11-07-4.log")
        self.assertEqual(set(failure), FAILURE_KEYS)
        self.assertEqual(failure, {
            "app": "research-digest", "kind": "publish", "date": "2026-11-07", "edition": None,
            "attempt": 4, "maxAttempts": 4, "manual": False, "failureKind": "temporary_failure",
            "finalReason": "exhausted", "failedAt": "2026-11-07T18:41:11+09:00", "alreadyNotified": False,
            "logPath": "/d/logs/publish/2026-11-07-4.log",
        })

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#失敗の引き渡し-1、apps/digest-platform/specs/batch-runner/requirements.md#再実行-4
    def test_手動実行の失敗は手動の印と確定の理由手動実行で渡り定時の回数だけを数える(self):
        data = state.empty("research-digest", "publish", "2026-11-07", None, 4)
        state.add_attempt(data, attempt(1))
        state.add_attempt(data, attempt(manual=True))
        failure = handoff.build(self.ctx(manual=True), data, "temporary_failure", "manual", "2026-11-07T14:33:40+09:00", "/m.log")
        self.assertEqual((failure["manual"], failure["finalReason"], failure["attempt"]), (True, "manual", 1))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#失敗の引き渡し-1、apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-8
    def test_成功した回の警告は種類をつないで渡り通知済みかは警告用の印から来る(self):
        """否定確認: 通知済みかを常に失敗用の印から取ると落ちる"""
        data = self.exhausted_state(status="succeeded", notified=True, warningNotified=False)
        failure = handoff.build(self.ctx(), data, ["broadcast_failed", "other"], "warning", "2026-11-07T06:40:00+09:00", "/1.log")
        self.assertEqual(failure["failureKind"], "broadcast_failed+other")
        self.assertEqual(failure["finalReason"], "warning")
        self.assertIs(failure["alreadyNotified"], False)
        result = handoff.notify(FakeJudge(), failure)
        handoff.record(data, result, failure, warning=True, summary_path=self.summary)
        self.assertIs(data["warningNotified"], True)
        self.assertEqual(data["warningNotifyReason"], "notified")
        self.assertIsNone(data["notifyReason"])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#失敗の引き渡し-2
    def test_通知したかと理由が実行状態に書かれる(self):
        data = self.exhausted_state()
        failure = handoff.build(self.ctx(), data, "temporary_failure", "exhausted", NOW, "/4.log")
        judge = FakeJudge({"notified": True, "reason": "notified"})
        result = handoff.notify(judge, failure)
        self.assertEqual(result, {"notified": True, "reason": "notified"})
        self.assertEqual(judge.calls, [failure])
        handoff.record(data, result, failure, summary_path=self.summary)
        self.assertEqual((data["notified"], data["notifyReason"], data["lastHandoff"]), (True, "notified", None))
        self.assertEqual(self.summary_lines(), [])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#失敗の引き渡し-2
    def test_判定関数が例外で落ちても実行係は落ちず通知の失敗として残す(self):
        """否定確認: 例外の受け止めを外すと落ちる"""
        data = self.exhausted_state()
        failure = handoff.build(self.ctx(), data, "temporary_failure", "exhausted", NOW, "/4.log")
        result = handoff.notify(FakeJudge(RuntimeError("boom")), failure)
        self.assertEqual((result["notified"], result["reason"]), (False, "notify_error"))
        handoff.record(data, result, failure, summary_path=self.summary)
        self.assertEqual((data["notified"], data["notifyReason"]), (False, "notify_error"))
        self.assertEqual(data["lastHandoff"], failure)
        [line] = self.summary_lines()
        self.assertIn(" WARNING 失敗通知の失敗: ", line)
        self.assertIn("RuntimeError: boom", line)
        self.assertTrue(line.endswith(" RUN-FAILED"))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#失敗の引き渡し-2
    def test_投稿用ファイルの書き出しに失敗したら要約ログに失敗の印付きの警告を書く(self):
        """否定確認: 書き出し失敗の理由を WARNING の対象から外すと落ちる"""
        data = self.exhausted_state()
        failure = handoff.build(self.ctx(), data, "temporary_failure", "exhausted", NOW, "/4.log")
        result = handoff.notify(FakeJudge({"notified": False, "reason": "write_failed"}), failure)
        handoff.record(data, result, failure, summary_path=self.summary)
        self.assertEqual((data["notified"], data["notifyReason"]), (False, "write_failed"))
        self.assertEqual(data["lastHandoff"], failure)
        [line] = self.summary_lines()
        self.assertIn(" WARNING 失敗通知の書き出し失敗: ", line)
        self.assertTrue(line.endswith(" RUN-FAILED"))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#失敗の引き渡し-2
    def test_一度通知済みになった印は後の通知の見送りで偽に戻らない(self):
        """否定確認: 印を返った値で上書きすると落ちる"""
        data = self.exhausted_state(notified=True)
        failure = handoff.build(self.ctx(), data, "temporary_failure", "exhausted", NOW, "/4.log")
        self.assertIs(failure["alreadyNotified"], True)
        handoff.record(data, {"notified": False, "reason": "already_notified"}, failure, summary_path=self.summary)
        self.assertEqual((data["notified"], data["notifyReason"]), (True, "already_notified"))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#失敗の引き渡し-1
    def test_判定関数のモジュールは環境変数で差し替えられ既定は失敗通知のモジュールになる(self):
        """否定確認: 環境変数を読まずに既定のモジュール名を使うと落ちる"""
        received = []
        fake = types.ModuleType("fake_failure_notification_for_test")
        fake.judge_and_notify = lambda failure: received.append(failure) or {"notified": True, "reason": "notified"}
        sys.modules[fake.__name__] = fake
        self.addCleanup(sys.modules.pop, fake.__name__, None)
        judge = handoff.resolve_judge_fn({"DIGEST_HANDOFF_MODULE": fake.__name__})
        self.assertEqual(handoff.notify(judge, {"app": "x"}), {"notified": True, "reason": "notified"})
        self.assertEqual(received, [{"app": "x"}])
        self.assertEqual(handoff.module_name({}), "failure_notification")
        missing = handoff.resolve_judge_fn({"DIGEST_HANDOFF_MODULE": "no_such_module_for_digest_test"})
        self.assertEqual(handoff.notify(missing, {"app": "x"})["reason"], "notify_error")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#失敗の引き渡し-2
    def test_判定関数が契約と違う形を返したら通知の失敗として扱う(self):
        result = handoff.notify(FakeJudge({"ok": True}), {"app": "x"})
        self.assertEqual((result["notified"], result["reason"]), (False, "notify_error"))


class 前日以前に締まらなかった記録の締め(HandoffTestCase):
    """スリープやロック中で定時の回が足りず、再実行待ちや手動の失敗だけのまま残った記録を、
    その記録が今回の配信日でなくなった後の最初の起動で失敗確定にし、通知に回す。"""

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-8
    def test_前日の再実行待ちの記録が失敗確定になり前日以前の締めとして通知に渡る(self):
        """否定確認: 再実行待ちを締める対象から外すと落ちる"""
        path = put_state(self.data_dir, "2026-11-06", "retry_pending", [
            attempt(1, ended="2026-11-06T06:41:00+09:00", log="/d/1.log"),
            attempt(2, result="timeout", ended="2026-11-06T11:30:00+09:00", log="/d/2.log"),
        ])
        judge = FakeJudge()
        touched = handoff.expire_stale(self.runs, "2026-11-08", "2026-11-08", judge, self.ctx(), now=NOW)
        self.assertEqual(touched, [path])
        data = read_state(path)
        self.assertEqual((data["status"], data["finalReason"], len(data["attempts"])), ("failed", "expired", 2))
        self.assertEqual((data["notified"], data["notifyReason"]), (True, "notified"))
        [failure] = judge.calls
        self.assertEqual(set(failure), FAILURE_KEYS)
        self.assertEqual((failure["finalReason"], failure["failureKind"], failure["attempt"]), ("expired", "timeout", 2))
        self.assertEqual((failure["failedAt"], failure["logPath"], failure["manual"]), ("2026-11-06T11:30:00+09:00", "/d/2.log", False))
        [line] = self.summary_lines()
        self.assertIn("INFO 実行終了: result=expired date=2026-11-06 edition=- attempt=2 status=failed RUN-FAILED log=/d/2.log", line)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-8
    def test_手動の失敗だけが積まれた未着手の記録も締めて定時の回数0で渡る(self):
        """否定確認: 未着手を締める対象から外すと落ちる"""
        path = put_state(self.data_dir, "2026-11-06", "pending",
                         [attempt(manual=True, result="permanent_failure", ended="2026-11-06T20:00:00+09:00", log="/d/m.log")])
        judge = FakeJudge()
        handoff.expire_stale(self.runs, "2026-11-08", "2026-11-08", judge, self.ctx(manual=True), now=NOW)
        self.assertEqual(read_state(path)["status"], "failed")
        [failure] = judge.calls
        self.assertEqual((failure["attempt"], failure["failureKind"], failure["manual"]), (0, "permanent_failure", True))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-8
    def test_今回の配信日の記録と基準日以後の記録と確定済みの記録は締めない(self):
        """否定確認: 今回の配信日の除外を外すと落ちる"""
        current = put_state(self.data_dir, "2026-11-01", "retry_pending", [attempt(1)])
        today = put_state(self.data_dir, "2026-11-08", "retry_pending", [attempt(1)])
        done = put_state(self.data_dir, "2026-11-02", "succeeded", [attempt(1, result="succeeded")])
        judge = FakeJudge()
        touched = handoff.expire_stale(self.runs, "2026-11-08", "2026-11-01", judge, self.ctx(), now=NOW)
        self.assertEqual((touched, judge.calls), ([], []))
        self.assertEqual(read_state(current)["status"], "retry_pending")
        self.assertEqual(read_state(today)["status"], "retry_pending")
        self.assertEqual(read_state(done)["status"], "succeeded")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-8、apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-3
    def test_走査中に読めない記録があれば飛ばして警告を1行書き残りを締める(self):
        """否定確認: 壊れた記録の受け止めを外すと落ちる"""
        os.makedirs(self.runs)
        with open(os.path.join(self.runs, "2026-11-05.json"), "w") as f:
            f.write("{")
        path = put_state(self.data_dir, "2026-11-06", "retry_pending", [attempt(1)])
        judge = FakeJudge()
        touched = handoff.expire_stale(self.runs, "2026-11-08", "2026-11-08", judge, self.ctx(), now=NOW)
        self.assertEqual(touched, [path])
        self.assertTrue(os.path.exists(os.path.join(self.runs, "2026-11-05.json")))
        lines = self.summary_lines()
        warnings = [l for l in lines if " WARNING " in l]
        self.assertEqual(len(warnings), 1)
        self.assertIn("2026-11-05.json", warnings[0])
        self.assertNotIn("RUN-FAILED", warnings[0])


class 記録の無い直前の配信日の締め(HandoffTestCase):
    """電源断で一度も試行が無かった回は記録が無く、前日以前の締めにも日次ヘルスチェックにも乗らない。
    次の起動で直前の配信日に記録が無ければ「記録なし」の失敗確定を作って通知に回す。"""

    def registration(self, weekdays=(6,), kind="publish", editions=None):
        if kind == "review":
            reg = review_entry("research-digest", 1)
        else:
            reg = publish_entry("research-digest", list(weekdays), edition_by_weekday=editions)
        reg.update(app="research-digest", kind=kind)
        return reg

    def ever_started(self):
        from digest_runner import summary_log
        summary_log.started(self.summary, dict(app="research-digest", kind="publish", date="2026-10-24", edition=None, attempt=1))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-9
    def test_直前の配信日に記録が無ければ記録なしの失敗確定ができて通知に渡り失敗の印が付く(self):
        """否定確認: 記録の有無の確かめを外すと「記録があれば作らない」側が、失敗の印を外すとこちらが落ちる"""
        self.ever_started()
        judge = FakeJudge()
        reg = self.registration(DAILY)
        now = dt.datetime(2026, 11, 7, 6, 30, 1, tzinfo=JST)
        touched = handoff.expire_missing(self.runs, reg, "2026-11-07", now, judge, self.ctx())
        path = os.path.join(self.runs, "2026-11-06.json")
        self.assertEqual(touched, [path])
        data = read_state(path)
        self.assertEqual((data["status"], data["finalReason"], data["attempts"]), ("failed", "missed", []))
        self.assertEqual((data["maxAttempts"], data["notified"]), (4, True))
        [failure] = judge.calls
        self.assertEqual(set(failure), FAILURE_KEYS)
        self.assertEqual(
            (failure["date"], failure["attempt"], failure["failureKind"], failure["finalReason"], failure["failedAt"], failure["logPath"], failure["alreadyNotified"]),
            ("2026-11-06", 0, "temporary_failure", "missed", "2026-11-07T06:30:01+09:00", self.summary, False),
        )
        last = self.summary_lines()[-1]
        self.assertIn("INFO 実行終了: result=missed date=2026-11-06 edition=- attempt=0 status=failed RUN-FAILED", last)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-9
    def test_直前の配信日に記録があれば作らない(self):
        self.ever_started()
        put_state(self.data_dir, "2026-11-06", "succeeded", [attempt(1, result="succeeded")])
        judge = FakeJudge()
        touched = handoff.expire_missing(self.runs, self.registration(DAILY), "2026-11-07", NOW, judge, self.ctx())
        self.assertEqual((touched, judge.calls), ([], []))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-9
    def test_週1回のアプリは7日前の配信日と編を見る(self):
        self.ever_started()
        judge = FakeJudge()
        reg = self.registration([6], editions={"6": "sci"})
        handoff.expire_missing(self.runs, reg, "2026-11-07", NOW, judge, self.ctx())
        [failure] = judge.calls
        self.assertEqual((failure["date"], failure["edition"]), ("2026-10-31", "sci"))
        self.assertTrue(os.path.exists(os.path.join(self.runs, "2026-10-31-sci.json")))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-9
    def test_一度もバッチを起動していない間は作らない(self):
        """否定確認: 実行開始の有無の確かめを外すと落ちる"""
        judge = FakeJudge()
        touched = handoff.expire_missing(self.runs, self.registration(DAILY), "2026-11-07", NOW, judge, self.ctx())
        self.assertEqual((touched, judge.calls), ([], []))
        self.assertFalse(os.path.exists(self.runs))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-9
    def test_アプリを有効にした直後の2回目の起動では有効にする前の配信日を締めず通知しない(self):
        """有効にした日(2026-11-07)の本番で「実行開始」が書かれたあと、同じ日の再実行が来ても、
        有効にする前の配信日(2026-11-06)は記録が無いのが当然なので「記録なし」にしない。
        否定確認: 最初の「実行開始」の配信日との比較を外す(実行開始があれば締める)と落ちる"""
        from digest_runner import summary_log
        summary_log.started(self.summary, dict(app="research-digest", kind="publish", date="2026-11-07", edition=None, attempt=1))
        put_state(self.data_dir, "2026-11-07", "pending", [attempt(1, result="temporary_failure")])
        judge = FakeJudge()
        retry = dt.datetime(2026, 11, 7, 10, 30, tzinfo=JST)
        touched = handoff.expire_missing(self.runs, self.registration(DAILY), "2026-11-07", retry, judge, self.ctx())
        self.assertEqual((touched, judge.calls), ([], []))
        self.assertFalse(os.path.exists(os.path.join(self.runs, "2026-11-06.json")))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-9
    def test_最初の実行開始の配信日と同じ日が直前の配信日なら締める(self):
        """有効にした日に起動したが記録が残らなかった回(当日の起動は実行開始のみ書かれ、記録が無い)は締めの対象。
        否定確認: 比較を「以前なら締めない」(<=)に変えると落ちる"""
        from digest_runner import summary_log
        summary_log.started(self.summary, dict(app="research-digest", kind="publish", date="2026-11-07", edition=None, attempt=1))
        judge = FakeJudge()
        now = dt.datetime(2026, 11, 8, 6, 30, 1, tzinfo=JST)
        touched = handoff.expire_missing(self.runs, self.registration(DAILY), "2026-11-08", now, judge, self.ctx())
        self.assertEqual(touched, [os.path.join(self.runs, "2026-11-07.json")])
        self.assertEqual([f["finalReason"] for f in judge.calls], ["missed"])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-9
    def test_月次見直しでは作らない(self):
        """否定確認: 系統の確かめを外すと落ちる"""
        self.ever_started()
        judge = FakeJudge()
        touched = handoff.expire_missing(self.runs, self.registration(kind="review"), "2026-11-07", NOW, judge, self.ctx(kind="review"))
        self.assertEqual((touched, judge.calls), ([], []))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-9
    def test_直前の配信日の1830をまだ過ぎていなければ作らない(self):
        """否定確認: 18:30 との比較を外すと落ちる"""
        self.ever_started()
        judge = FakeJudge()
        early = dt.datetime(2026, 11, 6, 18, 29, tzinfo=JST)
        touched = handoff.expire_missing(self.runs, self.registration(DAILY), "2026-11-07", early, judge, self.ctx())
        self.assertEqual((touched, judge.calls), ([], []))


class 通知できなかった記録の渡し直し(HandoffTestCase):
    """週1回のアプリと月次見直しは日次ヘルスチェックが失敗の印を読まないため、
    通知し損ねた失敗と警告は実行係が次の起動で、残しておいた12項目のまま渡し直す。"""

    def left_over(self, date, failed_at, notified=False, status="failed", warning=False, **extra):
        failure = {
            "app": "research-digest", "kind": "publish", "date": date, "edition": None, "attempt": 4,
            "maxAttempts": 4, "manual": False, "failureKind": "broadcast_failed" if warning else "temporary_failure",
            "finalReason": "warning" if warning else "exhausted", "failedAt": failed_at,
            "alreadyNotified": False, "logPath": f"/d/logs/publish/{date}-4.log",
        }
        if warning:
            return put_state(self.data_dir, date, status, [attempt(1, result="succeeded", warnings=["broadcast_failed"])],
                             warningNotified=notified, lastWarningHandoff=failure, warningNotifyReason="write_failed", **extra), failure
        extra.setdefault("finalReason", "exhausted" if status == "failed" else None)
        return put_state(self.data_dir, date, status, [attempt(n) for n in range(1, 5)],
                         notified=notified, lastHandoff=failure, notifyReason="write_failed", **extra), failure

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#失敗の引き渡し-3
    def test_書き出しに失敗した記録は次の起動で残した項目のまま渡し直され通知済みになる(self):
        """否定確認: 残した12項目を使わず組み立て直すと落ちる"""
        path = put_state(self.data_dir, "2026-11-06", "retry_pending", [attempt(1, ended="2026-11-06T06:41:00+09:00")])
        first = FakeJudge({"notified": False, "reason": "write_failed"})
        touched = handoff.expire_stale(self.runs, "2026-11-07", "2026-11-07", first, self.ctx(), now=NOW)
        left = read_state(path)["lastHandoff"]
        self.assertEqual(left, first.calls[0])
        self.assertEqual(handoff.renotify(self.runs, "2026-11-07", NOW, FakeJudge(), self.ctx(), exclude=touched), [])
        second = FakeJudge()
        renotified = handoff.renotify(self.runs, "2026-11-08", NOW, second, self.ctx(manual=True))
        self.assertEqual(renotified, [path])
        self.assertEqual(second.calls, [left])
        data = read_state(path)
        self.assertEqual((data["notified"], data["notifyReason"], data["lastHandoff"]), (True, "notified", None))
        last = self.summary_lines()[-1]
        self.assertIn("INFO 実行終了: result=renotified date=2026-11-06", last)
        self.assertNotIn("RUN-FAILED", last)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#失敗の引き渡し-3
    def test_渡し直しも失敗したら残したまま失敗の印付きの警告を書く(self):
        path, failure = self.left_over("2026-11-06", "2026-11-06T18:41:00+09:00")
        handoff.renotify(self.runs, "2026-11-08", NOW, FakeJudge(RuntimeError("down")), self.ctx())
        data = read_state(path)
        self.assertEqual((data["notified"], data["notifyReason"], data["lastHandoff"]), (False, "notify_error", failure))
        lines = self.summary_lines()
        self.assertTrue(any(" WARNING 失敗通知の失敗: " in l and l.endswith("RUN-FAILED") for l in lines))
        self.assertNotIn("RUN-FAILED", [l for l in lines if "result=renotified" in l][0])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#失敗の引き渡し-3
    def test_警告の通知し損ねも警告用の印と残した項目で渡し直される(self):
        """否定確認: 警告側の渡し直しを消すと落ちる"""
        path, failure = self.left_over("2026-11-06", "2026-11-06T06:40:00+09:00", status="succeeded", warning=True)
        judge = FakeJudge()
        self.assertEqual(handoff.renotify(self.runs, "2026-11-08", NOW, judge, self.ctx()), [path])
        self.assertEqual(judge.calls, [failure])
        data = read_state(path)
        self.assertEqual((data["warningNotified"], data["warningNotifyReason"], data["lastWarningHandoff"]), (True, "notified", None))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#失敗の引き渡し-3
    def test_通知済みと残した項目の無い記録と36日前と同じ起動で渡したばかりの記録は渡さない(self):
        """否定確認: 35日の期限・通知済みの確かめ・同じ起動の除外のどれを外しても落ちる"""
        done, _ = self.left_over("2026-11-05", "2026-11-05T18:41:00+09:00", notified=True)
        put_state(self.data_dir, "2026-11-04", "failed", [attempt(1)], finalReason="exhausted")
        old, _ = self.left_over("2026-10-02", (NOW - dt.timedelta(days=36)).isoformat(timespec="seconds"))
        fresh, _ = self.left_over("2026-11-06", "2026-11-06T18:41:00+09:00")
        edge, _ = self.left_over("2026-10-03", (NOW - dt.timedelta(days=35)).isoformat(timespec="seconds"))
        today, _ = self.left_over("2026-11-08", "2026-11-08T06:20:00+09:00")
        judge = FakeJudge()
        got = handoff.renotify(self.runs, "2026-11-08", NOW, judge, self.ctx(), exclude=[fresh])
        self.assertEqual(got, [edge])
        self.assertEqual([c["date"] for c in judge.calls], ["2026-10-03"])
        self.assertIsNotNone(read_state(old)["lastHandoff"])
        self.assertIsNotNone(read_state(fresh)["lastHandoff"])
        self.assertIsNotNone(read_state(today)["lastHandoff"])
        self.assertTrue(read_state(done)["notified"])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#失敗の引き渡し-3
    def test_成功で終わった日に残った手動の失敗は渡さず残した項目を消す(self):
        """否定確認: 成功の日の片付けを消すと落ちる"""
        path, _ = self.left_over("2026-11-06", "2026-11-06T09:00:00+09:00", status="succeeded")
        judge = FakeJudge()
        self.assertEqual(handoff.renotify(self.runs, "2026-11-08", NOW, judge, self.ctx()), [])
        self.assertEqual(judge.calls, [])
        self.assertIsNone(read_state(path)["lastHandoff"])


if __name__ == "__main__":
    unittest.main()
