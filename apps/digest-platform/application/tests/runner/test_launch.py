import inspect
import os
import signal
import stat
import sys
import threading
import time
import unittest

from tests.runner.support import TempDirTestCase

from digest_runner import launch, lock


def header_info(**over):
    info = dict(
        app="research-digest", kind="publish", date="2026-11-07", edition=None, attempt="1", manual=False,
        claudeIoDir="/d/claude-io/publish/2026-11-07", caBundle="/h/ca-bundle.pem",
    )
    info.update(over)
    return info


class バッチの起動と出力の記録と打ち切り(TempDirTestCase):
    """バッチの標準出力・標準エラーを実行ごとの詳細ログに残して後から読めるようにし、
    終わらないバッチは60分で子プロセスごと止めて次の再実行の時刻と重ならないようにする。"""

    def script(self, body):
        p = self.write_text("batch.sh", "#!/bin/sh\n" + body)
        os.chmod(p, 0o755)
        return p

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-5
    def test_バッチが終わると終了コードと標準出力の最終行が返り出力が詳細ログに残る(self):
        batch = self.script("echo first\necho oops >&2\necho DIGEST-BATCH-OK\nexit 0\n")
        log = self.path("logs", "publish", "2026-11-07-1.log")
        got = launch.run(["/bin/sh", batch], self.tmp, {"PATH": "/usr/bin:/bin"}, log, header=header_info())
        self.assertEqual(got["exit_code"], 0)
        self.assertFalse(got["timed_out"])
        self.assertEqual(got["last_line"], "DIGEST-BATCH-OK")
        self.assertEqual(got["output_lines"], ["first", "DIGEST-BATCH-OK"])
        self.assertLessEqual(got["started_at"], got["ended_at"])
        with open(log, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("first\n", text)
        self.assertIn("oops\n", text)
        self.assertEqual(stat.S_IMODE(os.stat(log).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(log)).st_mode), 0o700)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-3、apps/digest-platform/specs/batch-runner/requirements.md#時間の上限-1
    def test_上限を過ぎても終わらないバッチは子プロセスごと止めて打ち切りになる(self):
        """否定確認: プロセスグループへの KILL を消すと TERM を無視する子プロセスが残って落ちる"""
        child_pid_file = self.path("child.pid")
        batch = self.script(
            f"(trap '' TERM; exec sleep 60) &\necho $! > '{child_pid_file}'\necho started\nsleep 60\n")
        log = self.path("logs", "publish", "2026-11-07-1.log")
        began = time.monotonic()
        got = launch.run(["/bin/sh", batch], self.tmp, {"PATH": "/usr/bin:/bin"}, log, timeout_seconds=2)
        self.assertTrue(got["timed_out"])
        self.assertLess(time.monotonic() - began, 20)
        with open(child_pid_file) as f:
            child = int(f.read().strip())
        deadline = time.monotonic() + 3
        while lock.pid_alive(child) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(lock.pid_alive(child), "子プロセスが残っている")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-3
    def test_グループの外へ抜けた子孫が結果を返した後に書いた出力は詳細ログにだけ入り別のファイルに混ざらない(self):
        """否定確認: 読み取り側に詳細ログの複製を渡さず閉じた番号に書かせると、番号を使い回した別のファイルに混ざって落ちる"""
        late_pid_file = self.path("late.pid")
        late = (f"import os, time; os.setsid(); open({late_pid_file!r}, 'w').write(str(os.getpid())); "
                "time.sleep(8); print('late-output', flush=True)")
        batch = self.script(
            f"'{sys.executable}' -c \"{late}\" &\n"
            f"while [ ! -s '{late_pid_file}' ]; do sleep 0.1; done\necho DIGEST-BATCH-OK\nexit 0\n")
        log = self.path("logs", "publish", "2026-11-07-1.log")
        got = launch.run(["/bin/sh", batch], self.tmp, {"PATH": "/usr/bin:/bin"}, log, timeout_seconds=60)
        self.assertEqual(got["last_line"], "DIGEST-BATCH-OK")
        other_path = self.path("other.json")
        other = os.open(other_path, os.O_WRONLY | os.O_CREAT, 0o600)
        try:
            with open(late_pid_file) as f:
                late_pid = int(f.read().strip())
            deadline = time.monotonic() + 15
            while lock.pid_alive(late_pid) and time.monotonic() < deadline:
                time.sleep(0.1)
            time.sleep(0.5)
        finally:
            os.close(other)
        with open(other_path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "")
        with open(log, encoding="utf-8") as f:
            self.assertIn("late-output", f.read())

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-3
    def test_バッチが終わった後も出力をつかんだ子孫が残っていれば止めてすぐ返る(self):
        """否定確認: 終了後のグループの停止を消すと子孫の sleep が終わるまで待って落ちる"""
        child_pid_file = self.path("child.pid")
        batch = self.script(f"sleep 30 &\necho $! > '{child_pid_file}'\necho DIGEST-BATCH-OK\nexit 0\n")
        log = self.path("logs", "publish", "2026-11-07-1.log")
        began = time.monotonic()
        got = launch.run(["/bin/sh", batch], self.tmp, {"PATH": "/usr/bin:/bin"}, log, timeout_seconds=60)
        self.assertLess(time.monotonic() - began, 15)
        self.assertEqual((got["exit_code"], got["timed_out"], got["last_line"]), (0, False, "DIGEST-BATCH-OK"))
        with open(child_pid_file) as f:
            child = int(f.read().strip())
        deadline = time.monotonic() + 3
        while lock.pid_alive(child) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(lock.pid_alive(child), "子孫のプロセスが残っている")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-4
    def test_待っている間に中断されたらバッチのグループを止めてから中断を伝える(self):
        """否定確認: 中断時のグループの停止を消すとバッチが残り、ロックを外した後に二重に動きうるので落ちる"""
        pid_file = self.path("batch.pid")
        batch = self.script(f"echo $$ > '{pid_file}'\nsleep 60\n")
        log = self.path("logs", "publish", "2026-11-07-1.log")
        timer = threading.Timer(1.0, os.kill, (os.getpid(), signal.SIGINT))
        timer.start()
        self.addCleanup(timer.cancel)
        with self.assertRaises(KeyboardInterrupt):
            launch.run(["/bin/sh", batch], self.tmp, {"PATH": "/usr/bin:/bin"}, log, timeout_seconds=60)
        with open(pid_file) as f:
            batch_pid = int(f.read().strip())
        deadline = time.monotonic() + 3
        while lock.pid_alive(batch_pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(lock.pid_alive(batch_pid), "バッチが残っている")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#時間の上限-1
    def test_打ち切りの上限は登録表ではなく実行係の定数の60分である(self):
        self.assertEqual(launch.BATCH_TIMEOUT_SECONDS, 3600)
        self.assertEqual(inspect.signature(launch.run).parameters["timeout_seconds"].default, 3600)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-5
    def test_詳細ログの先頭にはパスと識別子だけを書き環境変数の値を書かない(self):
        """否定確認: 先頭に環境変数の一覧を書く処理を入れると落ちる"""
        batch = self.script("echo DIGEST-BATCH-OK\n")
        log = self.path("logs", "publish", "2026-11-07-1.log")
        env = {"PATH": "/usr/bin:/bin", "LEAKY_VALUE": "do-not-log-me", "ANTHROPIC_API_KEY": "sk-ant-zzz"}
        launch.run(["/bin/sh", batch], self.tmp, env, log, header=header_info())
        launch.write_result(log, {"ended_at": launch.now(), "exit_code": 0}, marker=True, artifacts_ok=True,
                            result="succeeded", missing=[])
        with open(log, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[0], "=== digest runner ===")
        end = lines.index("=== batch output ===")
        head = lines[1:end]
        keys = [line.split("=", 1)[0] for line in head]
        self.assertEqual(keys, ["startedAt", "app", "command", "cwd", "claudeIoDir", "caBundle"])
        self.assertEqual(head[1], "app=research-digest kind=publish date=2026-11-07 edition=- attempt=1 manual=false")
        joined = "\n".join(head)
        self.assertNotIn("do-not-log-me", joined)
        self.assertNotIn("sk-ant-zzz", joined)
        self.assertNotIn("PATH", joined)
        self.assertEqual(lines[-2], "=== result ===")
        self.assertRegex(lines[-1], r"^endedAt=\S+ exitCode=0 marker=ok artifacts=ok result=succeeded$")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-1
    def test_起動できないコマンドは起動の失敗として返り詳細ログに理由が残る(self):
        log = self.path("logs", "publish", "2026-11-07-1.log")
        got = launch.run([self.path("no-such-node"), "x.ts"], self.tmp, {}, log, header=header_info())
        self.assertTrue(got["start_failed"])
        self.assertIsNone(got["exit_code"])
        with open(log, encoding="utf-8") as f:
            self.assertIn("起動に失敗", f.read())


if __name__ == "__main__":
    unittest.main()
