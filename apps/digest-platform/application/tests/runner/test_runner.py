import ast
import os
import unittest
from unittest import mock

from tests.runner import LAUNCHD_DIR
from tests.runner.runner_support import RunnerTestCase, at

import runner
from digest_runner import state

SAT = (2026, 11, 7)


class 定時と手動の起動と成否の記録(RunnerTestCase):
    """launchd と手元ターミナルのどちらから起動しても、同じ判定と記録で1回の実行が完結する。"""

    def setUp(self):
        super().setUp()
        self.seed_succeeded("2026-10-31")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-1、apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-6
    def test_本番の起動が成功すると成功が記録され実行終了の行に成功の印が付く(self):
        code = self.run_at(at(*SAT, 6, 30))
        self.assertEqual(code, 0)
        self.assertEqual(self.calls(), ["1"])
        data = self.state_of("2026-11-07")
        self.assertEqual((data["status"], data["attempts"][0]["no"], data["attempts"][0]["result"]), ("succeeded", 1, "succeeded"))
        lines = self.summary()
        self.assertIn("INFO 実行開始: app=research-digest kind=publish date=2026-11-07 edition=- attempt=1", lines[0])
        self.assertIn("result=succeeded date=2026-11-07 edition=- attempt=1 status=succeeded RUN-SUCCEEDED log=", lines[-1])
        log = data["attempts"][0]["logPath"]
        self.assertEqual(log, os.path.join(self.data_dir, "logs", "publish", "2026-11-07-1.log"))
        with open(log, encoding="utf-8") as f:
            self.assertIn("result=succeeded", f.read().splitlines()[-1])
        self.assertFalse(os.path.exists(os.path.join(self.data_dir, "lock", "publish")))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-2
    def test_成功済みの配信日に再び起動されるとバッチを起動せず既に成功済みで終わる(self):
        """否定確認: 成功済みの分岐を消すと落ちる"""
        self.run_at(at(*SAT, 6, 30))
        self.assertEqual(self.run_at(at(*SAT, 10, 30)), 0)
        self.assertEqual(self.calls(), ["1"])
        last = self.finished_lines()[-1]
        self.assertIn("result=already_succeeded date=2026-11-07 edition=- attempt=- status=succeeded log=-", last)
        self.assertNotIn("RUN-SUCCEEDED", last)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-1、apps/digest-platform/specs/batch-runner/requirements.md#再実行-2
    def test_記事公開は一時的な失敗が続いても4回目まで起動され上限で失敗確定になる(self):
        for hh in (6, 10, 14):
            self.assertEqual(self.run_at(at(*SAT, hh, 30), mode="fail1"), 1)
            self.assertEqual(self.state_of("2026-11-07")["status"], "retry_pending")
        self.assertEqual(self.run_at(at(*SAT, 18, 0)), 1)
        self.assertEqual(self.calls(), ["1", "2", "3", "4"])
        data = self.state_of("2026-11-07")
        self.assertEqual((data["status"], data["finalReason"]), ("failed", "exhausted"))
        lines = self.finished_lines()
        self.assertEqual([("RUN-FAILED" in l) for l in lines], [False, False, False, True])
        [failure] = self.received
        self.assertEqual((failure["finalReason"], failure["attempt"], failure["maxAttempts"]), ("exhausted", 4, 4))
        self.assertTrue(data["notified"])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-1、apps/digest-platform/specs/batch-runner/requirements.md#再実行-2
    def test_上限に達して失敗確定の日の定時の5回目は起動せず失敗の印も付けない(self):
        for hh, mm in ((6, 30), (10, 30), (14, 30), (18, 0)):
            self.run_at(at(*SAT, hh, mm), mode="fail1")
        self.assertEqual(self.run_at(at(*SAT, 18, 30)), 0)
        self.assertEqual(len(self.calls()), 4)
        last = self.finished_lines()[-1]
        self.assertIn("result=failed_final date=2026-11-07", last)
        self.assertNotIn("RUN-FAILED", last)
        self.assertEqual(len(self.received), 1)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-5
    def test_月次見直しは1回目の失敗で失敗確定になり2回目は起動しない(self):
        self.assertEqual(self.run_at(at(2026, 11, 1, 7, 30), kind="review", mode="fail1"), 1)
        data = self.state_of("2026-11-01", kind="review")
        self.assertEqual((data["status"], data["finalReason"]), ("failed", "exhausted"))
        self.assertEqual(self.run_at(at(2026, 11, 1, 9, 0), kind="review"), 0)
        self.assertEqual(len(self.calls()), 1)
        self.assertIn("RUN-FAILED", self.finished_lines(kind="review")[0])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-3、apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-4
    def test_再試行しても直らない失敗は上限未満でも失敗確定になり終了コード2で終わる(self):
        """否定確認: 再試行しても直らない失敗の分岐を消すと落ちる"""
        self.assertEqual(self.run_at(at(*SAT, 6, 30), mode="fail2"), 2)
        data = self.state_of("2026-11-07")
        self.assertEqual((data["status"], data["finalReason"]), ("failed", "permanent"))
        self.assertEqual(self.received[0]["failureKind"], "permanent_failure")
        self.assertIn("RUN-FAILED", self.finished_lines()[-1])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-2、apps/digest-platform/specs/batch-runner/requirements.md#再実行-3
    def test_上限未満のまま失敗確定になった日は以降の定時の回を起動しない(self):
        """否定確認: 当日の状態が失敗確定なら起動しない分岐を消すと落ちる"""
        self.run_at(at(*SAT, 6, 30), mode="fail2")
        self.assertEqual(self.run_at(at(*SAT, 10, 30), mode="ok"), 0)
        self.assertEqual(self.calls(), ["1"])
        last = self.finished_lines()[-1]
        self.assertIn("result=failed_final date=2026-11-07 edition=- attempt=- status=failed log=-", last)
        self.assertNotIn("RUN-FAILED", last)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-7
    def test_配信日の1830以後の定時の失敗は2回目でも最後の機会として失敗確定になる(self):
        """否定確認: 最後の機会の比較を消すと落ちる"""
        self.run_at(at(*SAT, 6, 30), mode="fail1")
        self.run_at(at(*SAT, 18, 30))
        data = self.state_of("2026-11-07")
        self.assertEqual((data["status"], data["finalReason"], len(data["attempts"])), ("failed", "last_chance", 2))
        self.assertEqual(self.received[0]["finalReason"], "last_chance")
        self.assertIn("RUN-FAILED", self.finished_lines()[-1])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-7、apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-5
    def test_翌日0030の追い実行の失敗は前日の記録に積まれ最後の機会で失敗確定になる(self):
        self.seed_succeeded("2026-11-06", app="ai-dev-digest")
        self.run_at(at(*SAT, 6, 30), app="ai-dev-digest", mode="fail1")
        self.run_at(at(2026, 11, 8, 0, 30), app="ai-dev-digest")
        self.assertEqual([f["finalReason"] for f in self.received], ["last_chance"])
        data = self.state_of("2026-11-07", app="ai-dev-digest")
        self.assertEqual((data["status"], data["finalReason"], len(data["attempts"])), ("failed", "last_chance", 2))
        self.assertFalse(os.path.exists(state.path_for(self.path("data", "ai-dev-digest"), "publish", "2026-11-08", None)))


class 手動実行(RunnerTestCase):
    """運営者は手元のターミナルから同じバッチを動かせる。手動の失敗は定時の回数と状態を変えず、
    失敗が確定した日も手動ならやり直せる。成功済みの日は手動でも起動しない。"""

    def setUp(self):
        super().setUp()
        self.seed_succeeded("2026-10-31")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-4、apps/digest-platform/specs/batch-runner/requirements.md#定時起動-7
    def test_手動の失敗は試行回数と当日の状態を変えず手動実行の失敗として通知に渡る(self):
        """否定確認: 手動の失敗でも定時と同じく状態を更新するようにすると落ちる"""
        self.assertEqual(self.run_at(at(*SAT, 9, 0), manual=True, mode="fail1"), 1)
        data = self.state_of("2026-11-07")
        self.assertEqual((data["status"], state.scheduled_attempts(data), len(data["attempts"])), ("pending", 0, 1))
        self.assertEqual(self.calls(), ["manual-090000"])
        [failure] = self.received
        self.assertEqual((failure["manual"], failure["finalReason"], failure["attempt"]), (True, "manual", 0))
        self.assertTrue(data["attempts"][0]["logPath"].endswith("2026-11-07-manual-090000.log"))
        last = self.finished_lines()[-1]
        self.assertIn("attempt=manual status=pending log=", last)
        self.assertNotIn("RUN-FAILED", last)
        self.run_at(at(*SAT, 10, 30))
        self.assertEqual(self.calls()[-1], "1")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-4
    def test_手動の成功でその日は成功になり以降の定時は起動しない(self):
        self.run_at(at(*SAT, 6, 30), mode="fail1")
        self.assertEqual(self.run_at(at(*SAT, 9, 0), manual=True, mode="ok"), 0)
        self.assertEqual(self.state_of("2026-11-07")["status"], "succeeded")
        self.run_at(at(*SAT, 10, 30))
        self.assertEqual(len(self.calls()), 2)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-6
    def test_失敗確定の日も手動なら起動し成功すれば成功に変わる(self):
        """否定確認: 失敗確定の日を手動でも起動しないようにすると落ちる"""
        self.run_at(at(*SAT, 6, 30), mode="fail2")
        self.assertEqual(self.run_at(at(*SAT, 12, 0), manual=True, mode="ok"), 0)
        data = self.state_of("2026-11-07")
        self.assertEqual((data["status"], data["finalReason"]), ("succeeded", None))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-6
    def test_手動でも成功済みの日は起動しない(self):
        self.run_at(at(*SAT, 6, 30))
        self.assertEqual(self.run_at(at(*SAT, 12, 0), manual=True), 0)
        self.assertEqual(self.calls(), ["1"])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-6、apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-6
    def test_手動の失敗は再実行待ちの日も失敗確定の日も失敗の印を付けない(self):
        self.run_at(at(*SAT, 6, 30), mode="fail1")
        self.run_at(at(*SAT, 9, 0), manual=True)
        self.run_at(at(*SAT, 10, 30), mode="fail2")
        self.run_at(at(*SAT, 12, 0), manual=True, mode="fail1")
        lines = self.finished_lines()
        self.assertEqual([("RUN-FAILED" in l) for l in lines], [False, False, True, False])
        self.assertEqual(self.state_of("2026-11-07")["status"], "failed")
        self.assertEqual([f["finalReason"] for f in self.received], ["manual", "permanent", "manual"])


class 前日以前の締めと記録の無い回と週1回のアプリ(RunnerTestCase):
    """同じ日に締まらなかった記録と、電源断で一度も試行が無かった回を、次の起動で通知に回す。"""

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-8、apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-5
    def test_週1回のアプリを3日後に起動すると直前の配信曜日の記録で動きそれより前の週の再実行待ちだけを締める(self):
        self.run_at(at(2026, 10, 31, 6, 30), mode="fail1")
        self.run_at(at(*SAT, 6, 30), mode="fail1")
        self.assertEqual(self.run_at(at(2026, 11, 10, 12, 0)), 1)
        self.assertEqual(self.calls(), ["1", "1", "2"])
        older = self.state_of("2026-10-31")
        self.assertEqual((older["status"], older["finalReason"]), ("failed", "expired"))
        current = self.state_of("2026-11-07")
        self.assertEqual((current["status"], current["finalReason"]), ("failed", "last_chance"))
        reasons = [f["finalReason"] for f in self.received]
        self.assertEqual(reasons, ["expired", "last_chance"])
        expired_line = [l for l in self.finished_lines() if "result=expired" in l][0]
        self.assertIn("date=2026-10-31", expired_line)
        self.assertIn("RUN-FAILED", expired_line)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#再実行-9
    def test_電源断で直前の配信日の記録が無いまま起動すると記録なしで通知に渡ってから当日の本番が動く(self):
        self.run_at(at(2026, 11, 5, 6, 30), app="ai-dev-digest")
        self.assertEqual(self.run_at(at(*SAT, 6, 30), app="ai-dev-digest"), 0)
        missed = self.state_of("2026-11-06", app="ai-dev-digest")
        self.assertEqual((missed["status"], missed["finalReason"]), ("failed", "missed"))
        [failure] = self.received
        self.assertEqual((failure["date"], failure["finalReason"], failure["attempt"]), ("2026-11-06", "missed", 0))
        lines = self.summary(app="ai-dev-digest")
        missed_at = next(i for i, l in enumerate(lines) if "result=missed" in l)
        started_at = max(i for i, l in enumerate(lines) if "実行開始" in l)
        self.assertLess(missed_at, started_at)
        self.assertIn("RUN-FAILED", lines[missed_at])
        self.assertEqual(self.state_of("2026-11-07", app="ai-dev-digest")["status"], "succeeded")


class 成功した回の警告と壊れた記録(RunnerTestCase):
    """新着の送り出し失敗は成功のまま警告として通知に回し、壊れた実行状態は退避して失敗確定で書き直す。"""

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-8
    def test_警告付きで成功したバッチは成功のまま警告として通知に渡る(self):
        """否定確認: 警告の引き渡しを消すと落ちる"""
        self.assertEqual(self.run_at(at(*SAT, 6, 30), mode="warn"), 0)
        data = self.state_of("2026-11-07")
        self.assertEqual((data["status"], data["attempts"][0]["warnings"]), ("succeeded", ["broadcast_failed"]))
        [failure] = self.received
        self.assertEqual((failure["finalReason"], failure["failureKind"]), ("warning", "broadcast_failed"))
        self.assertEqual((data["warningNotified"], data["notified"]), (True, False))
        self.assertIn("RUN-SUCCEEDED", self.finished_lines()[-1])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行状態の記録-3
    def test_壊れた実行状態は退避して失敗確定で書き直し壊れた記録として通知に渡る(self):
        path = state.path_for(self.data_dir, "publish", "2026-11-07", None)
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as f:
            f.write("{broken")
        self.assertEqual(self.run_at(at(*SAT, 6, 30, )), 2)
        self.assertEqual(self.calls(), [])
        moved = [n for n in os.listdir(os.path.dirname(path)) if ".corrupt-" in n]
        self.assertEqual(moved, ["2026-11-07.json.corrupt-20261107-063000"])
        data = self.state_of("2026-11-07")
        self.assertEqual((data["status"], data["finalReason"], data["attempts"]), ("failed", "corrupt", []))
        [failure] = self.received
        self.assertEqual((failure["finalReason"], failure["failureKind"], failure["attempt"]), ("corrupt", "permanent_failure", 0))
        last = self.finished_lines()[-1]
        self.assertIn("result=corrupt_state", last)
        self.assertIn("RUN-FAILED", last)


class 実行係自身が動けなかったとき(RunnerTestCase):
    """未登録・登録表の壊れ・想定外の例外は試行に数えず実行状態も変えず、要約ログに失敗の印を残す。"""

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-3、apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-7
    def test_未登録のアプリと系統と有効でないアプリは起動せず失敗の印を付けて終了コード2で終わる(self):
        self.add_app("news-digest", [0, 1, 2, 3, 4, 5, 6], enabled=False)
        self.assertEqual(self.run_at(at(*SAT, 6, 30), app="no-such-digest"), 2)
        self.assertEqual(self.run_at(at(*SAT, 6, 30), kind="weekly"), 2)
        self.assertEqual(self.run_at(at(*SAT, 6, 30), app="news-digest"), 2)
        self.assertEqual(self.calls(), [])
        for app, kind in (("no-such-digest", "publish"), ("research-digest", "weekly"), ("news-digest", "publish")):
            [line] = self.finished_lines(app=app, kind=kind)
            self.assertIn("result=unregistered date=- edition=- attempt=- status=- RUN-FAILED log=-", line)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-7
    def test_登録表が壊れていたら失敗の印を付けて終了コード2で終わる(self):
        path = self.registry_path()
        with open(path, "w") as f:
            f.write("{")
        code = runner.main(["research-digest", "publish"], env=self.env(), clock=lambda: at(*SAT, 6, 30),
                           app_root=self.root, registry_path=path, home=self.path("home"))
        self.assertEqual(code, 2)
        self.assertIn("RUN-FAILED", self.finished_lines()[-1])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-7
    def test_想定外の例外は失敗の印と終了コード2で終わり実行状態を変えずロックを外す(self):
        """否定確認: 想定外の例外の受け止めを外すと落ちる"""
        self.run_at(at(*SAT, 6, 30), mode="fail1")
        path = state.path_for(self.data_dir, "publish", "2026-11-07", None)
        with open(path, "rb") as f:
            before = f.read()
        with mock.patch("digest_runner.judge.evaluate", side_effect=RuntimeError("judge exploded")):
            self.assertEqual(self.run_at(at(*SAT, 10, 30)), 2)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), before)
        last = self.finished_lines()[-1]
        self.assertIn("result=runner_error", last)
        self.assertIn("RUN-FAILED", last)
        self.assertTrue(any("RuntimeError: judge exploded" in l for l in self.summary()))
        self.assertFalse(os.path.exists(os.path.join(self.data_dir, "lock", "publish")))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-4
    def test_同じアプリと系統が動いている間に起動されると何もせず終わる(self):
        from digest_runner import lock
        self.assertTrue(lock.acquire(os.path.join(self.data_dir, "lock", "publish")))
        self.assertEqual(self.run_at(at(*SAT, 6, 30)), 0)
        self.assertEqual(self.calls(), [])
        self.assertIn("result=locked date=- edition=- attempt=- status=- log=-", self.finished_lines()[-1])
        self.assertTrue(os.path.exists(os.path.join(self.data_dir, "lock", "publish")), "他人のロックを外さない")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-5、apps/digest-platform/specs/batch-runner/requirements.md#再実行-3
    def test_実行ファイルが見つからなければバッチを起動せず再試行しても直らない失敗になる(self):
        os.unlink(os.path.join(self.root, "node_modules", ".bin", "tsx"))
        self.assertEqual(self.run_at(at(*SAT, 6, 30)), 2)
        self.assertEqual(self.calls(), [])
        data = self.state_of("2026-11-07")
        self.assertEqual((data["status"], data["finalReason"], data["attempts"][0]["result"]), ("failed", "permanent", "permanent_failure"))


def _subprocess_calls_mentioning_claude(source):
    """subprocess・os の起動系の呼び出しのうち、引数に claude を含む文字列や DIGEST_CLAUDE_BIN を使うものを返す。"""
    tree = ast.parse(source)
    launchers = {"run", "Popen", "call", "check_call", "check_output", "system", "popen", "execv", "execvp",
                 "execve", "execl", "execlp", "spawnv", "spawnvp", "posix_spawn", "posix_spawnp"}
    found, total = [], 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
        base = func.value.id if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else None
        if name not in launchers or base not in ("subprocess", "os"):
            continue
        total += 1
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and "claude" in sub.value.lower():
                found.append(node.lineno)
    return found, total


class 実行係はClaudeを呼ばない(unittest.TestCase):
    """実行係自身の処理(起動・成否の判定・記録・失敗の引き渡し)では Claude を呼ばない(呼び出し回数0回)。
    Claude を起動するのはバッチ側の共通部品だけ。"""

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#非機能要件-2
    def test_入口と実行係のパッケージのどのファイルにもClaudeを起動する記述が無い(self):
        """否定確認: 実行係のどこかに subprocess.run(["claude", "-p"]) を1行入れると落ちる"""
        files = [os.path.join(LAUNCHD_DIR, "runner.py")]
        package = os.path.join(LAUNCHD_DIR, "digest_runner")
        files += [os.path.join(package, n) for n in sorted(os.listdir(package)) if n.endswith(".py")]
        self.assertGreaterEqual(len(files), 12)
        offenders, launches = [], 0
        for path in files:
            with open(path, encoding="utf-8") as f:
                source = f.read()
            found, total = _subprocess_calls_mentioning_claude(source)
            launches += total
            offenders += [f"{path}:{line}" for line in found]
        self.assertGreaterEqual(launches, 1, "バッチを起動する呼び出しが1つも見つからない(検査が働いていない)")
        self.assertEqual(offenders, [])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#非機能要件-2
    def test_検査はClaudeを起動する呼び出しを見つけられる(self):
        found, total = _subprocess_calls_mentioning_claude('import subprocess\nsubprocess.run(["claude", "-p", "x"])\n')
        self.assertEqual((found, total), ([2], 1))
        found, _ = _subprocess_calls_mentioning_claude('import os, subprocess\nsubprocess.Popen([os.environ["DIGEST_CLAUDE_BIN"]])\n')
        self.assertEqual(found, [2])


if __name__ == "__main__":
    unittest.main()
