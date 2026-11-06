import io
import os
import plistlib
import unittest
from contextlib import redirect_stderr, redirect_stdout

from tests.runner import LAUNCHD_DIR
from tests.runner.support import TempDirTestCase, all_enabled_registry

import make_plists

PUBLISH_TIMES = [(6, 30), (10, 30), (14, 30), (18, 30)]


class アプリ登録表からのlaunchdジョブの生成(TempDirTestCase):
    """運営者が手元で1コマンド実行するだけで、登録表で有効にしたアプリ×系統の plist が登録できる形で揃う。
    登録した直後に記事公開が走って通知が出ないよう、即実行(RunAtLoad)は付けない。"""

    def setUp(self):
        super().setUp()
        self.home = self.path("home")
        self.node = self.exe("bin/node")
        self.claude = self.exe("home/.local/bin/claude")
        self.python = self.exe("Library/Frameworks/Python.framework/Versions/Current/bin/python3")
        self.registry = self.write_json("apps.json", all_enabled_registry())

    def exe(self, rel):
        p = self.write_text(rel, "#!/bin/sh\n")
        os.chmod(p, 0o755)
        return p

    def generate(self, registry_path=None, out_name="LaunchAgents"):
        out = self.path(out_name)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = make_plists.main(["--node", self.node, "--claude", self.claude, "--python", self.python, "--out", out],
                                    registry_path=registry_path or self.registry, home=self.home)
        self.assertEqual(code, 0)
        plists = {}
        for name in sorted(os.listdir(out)):
            if not name.endswith(".plist"):
                continue
            with open(os.path.join(out, name), "rb") as f:
                plists[name] = plistlib.load(f)
        return plists

    def times(self, plist):
        return [(e["Hour"], e["Minute"]) for e in plist["StartCalendarInterval"]]

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-1
    def test_生成した全てのplistが標準の読み取りで読めアプリと系統ごとに1つずつある(self):
        plists = self.generate()
        apps = ["ai-dev-digest", "future-digest", "news-digest", "research-digest", "trend-digest"]
        self.assertEqual(sorted(plists), sorted(f"com.example.digest-{a}-{k}.plist" for a in apps for k in ("publish", "review")))
        p = plists["com.example.digest-research-digest-publish.plist"]
        self.assertEqual(p["Label"], "com.example.digest-research-digest-publish")
        self.assertEqual(p["ProgramArguments"], [self.python, os.path.join(LAUNCHD_DIR, "runner.py"), "research-digest", "publish"])
        self.assertEqual(p["ProcessType"], "Background")
        log = os.path.join(self.home, "Library", "Logs", "digest-research-digest-publish.log")
        self.assertEqual((p["StandardOutPath"], p["StandardErrorPath"]), (log, log))
        env = p["EnvironmentVariables"]
        self.assertEqual(env["HOME"], self.home)
        self.assertEqual(env["TZ"], "Asia/Tokyo")
        self.assertEqual(env["PATH"], "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin")
        self.assertEqual((env["DIGEST_NODE_BIN"], env["DIGEST_CLAUDE_BIN"], env["DIGEST_PYTHON_BIN"]), (self.node, self.claude, self.python))
        self.assertEqual(env["NODE_EXTRA_CA_CERTS"], env["SSL_CERT_FILE"])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-6
    def test_どのplistにも登録時の即実行の指定が無い(self):
        """否定確認: plist に RunAtLoad を足すと落ちる"""
        plists = self.generate()
        self.assertGreater(len(plists), 0)
        for name, p in plists.items():
            self.assertNotIn("RunAtLoad", p, name)
        with open(os.path.join(self.path("LaunchAgents"), "com.example.digest-news-digest-publish.plist"), "rb") as f:
            self.assertNotIn(b"RunAtLoad", f.read())

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行時刻-3
    def test_週1回のアプリは配信曜日だけを持ち毎日のアプリは曜日を持たない4件になる(self):
        """否定確認: 7曜日すべてのときに曜日を省く分岐を消すと落ちる"""
        plists = self.generate()
        weekdays = lambda app: sorted({e.get("Weekday") for e in plists[f"com.example.digest-{app}-publish.plist"]["StartCalendarInterval"]}, key=str)
        self.assertEqual(weekdays("research-digest"), [6])
        self.assertEqual(weekdays("future-digest"), [0])
        for app in ("ai-dev-digest", "news-digest", "trend-digest"):
            entries = plists[f"com.example.digest-{app}-publish.plist"]["StartCalendarInterval"]
            self.assertEqual(len(entries), 4, app)
            self.assertTrue(all("Weekday" not in e for e in entries), app)
        self.assertEqual(len(plists["com.example.digest-research-digest-publish.plist"]["StartCalendarInterval"]), 4)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行時刻-1
    def test_全ての記事公開の起動時刻に朝0630がある(self):
        plists = self.generate()
        publish = [p for n, p in plists.items() if n.endswith("-publish.plist")]
        self.assertEqual(len(publish), 5)
        for p in publish:
            self.assertEqual(self.times(p)[0], (6, 30))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行時刻-2
    def test_記事公開には再実行の3つの時刻があり月次見直しには無い(self):
        """否定確認: 月次見直しにも再実行の時刻を並べると落ちる"""
        plists = self.generate()
        for name, p in plists.items():
            times = self.times(p)
            if name.endswith("-publish.plist"):
                self.assertEqual(times, PUBLISH_TIMES, name)
            else:
                for t in PUBLISH_TIMES[1:]:
                    self.assertNotIn(t, times, name)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行時刻-4
    def test_月次見直しは登録表の日の朝0730の1つだけ(self):
        plists = self.generate()
        review = [p for n, p in plists.items() if n.endswith("-review.plist")]
        self.assertEqual(len(review), 5)
        for p in review:
            self.assertEqual(p["StartCalendarInterval"], [{"Day": 1, "Hour": 7, "Minute": 30}])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-1
    def test_記事公開が有効でないアプリと月次見直しの日が未定のアプリはその系統のplistを作らない(self):
        """否定確認: 有効の印の条件を外すと落ちる"""
        data = all_enabled_registry()
        data["apps"]["news-digest"]["publish"]["enabled"] = False
        data["apps"]["news-digest"]["review"]["dayOfMonth"] = None
        plists = self.generate(self.write_json("partial.json", data))
        self.assertNotIn("com.example.digest-news-digest-publish.plist", plists)
        self.assertNotIn("com.example.digest-news-digest-review.plist", plists)
        self.assertIn("com.example.digest-trend-digest-publish.plist", plists)
        self.assertEqual(self.generate(os.path.join(LAUNCHD_DIR, "apps.json"), out_name="real"), {}, "本番の登録表は実装直後は全アプリ無効")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-5
    def test_バージョン番号を含むパスと存在しないパスは拒否して何も書かない(self):
        """否定確認: バージョン番号の検査を消すと落ちる"""
        versioned = self.exe("Library/Frameworks/Python.framework/Versions/3.12/bin/python3")
        out = self.path("LaunchAgents")
        for python in (versioned, self.path("nowhere/python3")):
            with redirect_stderr(io.StringIO()) as err:
                code = make_plists.main(["--node", self.node, "--claude", self.claude, "--python", python, "--out", out],
                                        registry_path=self.registry, home=self.home)
            self.assertEqual(code, 2)
            self.assertIn(python, err.getvalue())
        self.assertFalse(os.path.exists(out))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-6
    def test_生成前の検査は読み直せない形のplistを拒否する(self):
        with self.assertRaises(make_plists.InvalidPlist):
            make_plists.checked_bytes({"Label": "x", "Bad": None})
        with self.assertRaises(make_plists.InvalidPlist):
            make_plists.checked_bytes({"Label": "x", "RunAtLoad": False})


if __name__ == "__main__":
    unittest.main()
