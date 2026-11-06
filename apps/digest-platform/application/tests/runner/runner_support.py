"""runner.py の入口を、一時フォルダのアプリの土台・偽のバッチ・偽の判定関数で動かす小道具。

偽のバッチは /bin/sh のスクリプトで、一時フォルダの mode ファイルの値で終わり方を変える:
ok(生成物を書いて成功マーカー)・warn(警告の行のあと成功)・fail1(exit 1)・fail2(exit 2)・nomarker(生成物は書くがマーカー無し)。
呼ばれるたびに calls ファイルへ1行足す。偽の判定関数は契約どおり12項目を受け取って記録する。
"""

import datetime as dt
import json
import os
import sys
import types

from tests.runner.support import TempDirTestCase, publish_entry, review_entry

import runner  # launchd/runner.py

JST = dt.timezone(dt.timedelta(hours=9))
FAKE_MODULE = "fake_failure_notification_for_runner_test"

BATCH = """#!/bin/sh
echo "$DIGEST_ATTEMPT" >> '{root}/calls'
mode=$(cat '{root}/mode')
mkdir -p out
case "$mode" in
  ok) echo working; : > "out/$DIGEST_DATE$EDITION_SUFFIX.txt"; echo DIGEST-BATCH-OK; exit 0 ;;
  warn) : > "out/$DIGEST_DATE$EDITION_SUFFIX.txt"; echo "DIGEST-BATCH-WARN broadcast_failed"; echo DIGEST-BATCH-OK; exit 0 ;;
  nomarker) : > "out/$DIGEST_DATE$EDITION_SUFFIX.txt"; echo done; exit 0 ;;
  fail2) echo "quota exhausted"; exit 2 ;;
  *) echo "temporary"; exit 1 ;;
esac
"""


def at(y, m, d, hh, mm):
    return dt.datetime(y, m, d, hh, mm, tzinfo=JST)


class RunnerTestCase(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.root = self.path("app-root")
        self.data_dir = self.path("data", "research-digest")
        os.makedirs(os.path.join(self.root, "node_modules", ".bin"))
        tsx = os.path.join(self.root, "node_modules", ".bin", "tsx")
        open(tsx, "w").close()
        os.chmod(tsx, 0o755)
        batch = os.path.join(self.root, "batch.sh")
        with open(batch, "w") as f:
            f.write(BATCH.replace("{root}", self.root).replace("$EDITION_SUFFIX", '${DIGEST_EDITION:+-$DIGEST_EDITION}'))
        os.chmod(batch, 0o755)
        self.batch = batch
        self.set_mode("ok")
        self.registry = {"apps": {}}
        self.add_app("research-digest", [6])
        self.add_app("ai-dev-digest", [0, 1, 2, 3, 4, 5, 6])
        self.received = []
        fake = types.ModuleType(FAKE_MODULE)
        fake.judge_and_notify = self._judge
        self.judge_result = {"notified": True, "reason": "notified"}
        sys.modules[FAKE_MODULE] = fake
        self.addCleanup(sys.modules.pop, FAKE_MODULE, None)

    def _judge(self, failure):
        self.received.append(dict(failure))
        return dict(self.judge_result)

    def add_app(self, app, weekdays, editions=None, enabled=True):
        pub = publish_entry(app, weekdays, enabled=enabled, edition_by_weekday=editions)
        pub["command"] = ["/bin/sh", self.batch]
        pub["artifacts"] = ["out/{date}{edition}.txt"]
        rev = review_entry(app, 1)
        rev["command"] = ["/bin/sh", self.batch]
        rev["artifacts"] = ["out/{date}{edition}.txt"]
        self.registry["apps"][app] = {"publish": pub, "review": rev}

    def set_mode(self, mode):
        with open(os.path.join(self.root, "mode"), "w") as f:
            f.write(mode)

    def calls(self):
        try:
            with open(os.path.join(self.root, "calls")) as f:
                return f.read().splitlines()
        except FileNotFoundError:
            return []

    def env(self, app="research-digest"):
        return {
            "PATH": "/usr/bin:/bin",
            "HOME": self.path("home"),
            "DIGEST_DATA_DIR": self.path("data", app),
            "DIGEST_NODE_BIN": "/bin/sh",
            "DIGEST_CLAUDE_BIN": "/bin/sh",
            "DIGEST_PYTHON_BIN": sys.executable,
            "DIGEST_HANDOFF_MODULE": FAKE_MODULE,
        }

    def registry_path(self):
        p = os.path.join(self.root, "launchd", "apps.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            json.dump(self.registry, f)
        return p

    def run_at(self, when, app="research-digest", kind="publish", manual=False, mode=None):
        if mode:
            self.set_mode(mode)
        argv = [app, kind] + (["--manual"] if manual else [])
        return runner.main(argv, env=self.env(app), clock=lambda: when, app_root=self.root,
                           registry_path=self.registry_path(), home=self.path("home"))

    def seed_succeeded(self, date, app="research-digest", kind="publish", edition=None):
        """直前の配信日を成功済みにしておく(記録の無い回の締めを、その締めを見ないテストで起こさないため)。"""
        from digest_runner import state
        data = state.empty(app, kind, date, edition, 4)
        data["status"] = "succeeded"
        state.save(state.path_for(self.path("data", app), kind, date, edition), data)

    def state_of(self, date, app="research-digest", kind="publish", edition=None):
        from digest_runner import state
        return state.read(state.path_for(self.path("data", app), kind, date, edition))

    def summary(self, app="research-digest", kind="publish"):
        p = os.path.join(self.path("data", app), f"runner-{kind}.log")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return f.read().splitlines()

    def finished_lines(self, app="research-digest", kind="publish"):
        return [l for l in self.summary(app, kind) if " INFO 実行終了: " in l]
