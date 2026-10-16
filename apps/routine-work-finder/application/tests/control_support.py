"""操作スクリプトのテストの共通部品"""

import json
import os
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from routine_work_finder import config_store, control, paths

JST = timezone(timedelta(hours=9))


def jst(text):
    return datetime.fromisoformat(text + "+09:00")


class ControlTestCase(unittest.TestCase):
    now = jst("2026-10-07T10:00:00")

    def setUp(self):
        base = os.environ.get("TMPDIR") or tempfile.gettempdir()
        self.temporary = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.temporary.name) / "routine-work-finder"
        self.paths = paths.DataPaths(self.root)
        self.input_dir = Path(self.temporary.name) / "input"
        self.input_dir.mkdir()

    def tearDown(self):
        for path in [self.root, *(self.root.rglob("*") if self.root.exists() else [])]:
            if path.exists():
                os.chmod(path, stat.S_IRWXU)
        self.temporary.cleanup()

    def run_control(self, *argv, now=None):
        return control.run(list(argv), now=now or self.now, environ={"RWF_DATA_DIR": str(self.root)})

    def write_config(self, **changes):
        config = config_store.default_config()
        config.update(changes)
        config_store.write_config(self.paths, config)
        return config

    def read_config(self):
        return json.loads(self.paths.config.read_text(encoding="utf-8"))

    def write_status(self, updated_at, accessibility=True, config_error=None, recording=True):
        self.root.mkdir(parents=True, exist_ok=True)
        status = {"version": 1, "updatedAt": updated_at.isoformat(), "recording": recording, "tickMillis": 3,
                  "configError": config_error, "lastWriteError": None, "accessibilityGranted": accessibility,
                  "lastPurgeDate": "2026-10-07"}
        self.paths.status.write_text(json.dumps(status), encoding="utf-8")

    def write_records(self, *lines):
        self.paths.records.mkdir(parents=True, exist_ok=True)
        for line in lines:
            with (self.paths.records / f"{line['t'][:10]}.jsonl").open("a", encoding="utf-8") as file:
                file.write(json.dumps(line, ensure_ascii=False) + "\n")

    def write_input(self, name, content):
        path = self.input_dir / name
        path.write_text(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False), encoding="utf-8")
        return path

    def make_unwritable(self):
        """データフォルダを読み取り専用にする(Bash からの書き込みが拒否されるセッションの代わり)"""
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, stat.S_IRUSR | stat.S_IXUSR)


def sample(text):
    return {"t": text + "+09:00", "kind": "sample", "app": "Code", "bundleId": "com.microsoft.VSCode", "monitor": 1,
            "idleSec": 0.5, "locked": False, "mic": False, "displaySleepPrevented": False, "title": "main.swift"}


def marker(text, kind, **extra):
    return {"t": text + "+09:00", "kind": kind, **extra}
