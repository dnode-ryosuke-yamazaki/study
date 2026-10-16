"""記録係を常駐させる launchd の設定ファイルと、署名して配置するスクリプトの構造検証。

ログインしたら起動し、落ちたら起動し直すことで、Mac の再起動・ログアウトのあとも終わりの日時までは記録を再開する。
"""

import plistlib
import re
import unittest
from pathlib import Path

APPLICATION_DIR = Path(__file__).resolve().parent.parent
PLIST_PATH = APPLICATION_DIR / "launchd" / "com.example.routine-work-finder-recorder.plist"
INSTALL_SCRIPT = APPLICATION_DIR / "scripts" / "install_recorder.sh"
RECORDER_PATH = "__HOME__/Library/Application Support/routine-work-finder/bin/rwf-recorder"


class LaunchdPlistTests(unittest.TestCase):
    """記録係の launchd の設定ファイル"""

    def load(self):
        with PLIST_PATH.open("rb") as file:
            return plistlib.load(file)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-7
    def test_ログイン時に起動し落ちたら起動し直す指定がある(self):
        """否定確認: KeepAlive を外すと落ちる"""
        plist = self.load()
        self.assertEqual(plist["Label"], "com.example.routine-work-finder-recorder")
        self.assertIs(plist["RunAtLoad"], True)
        self.assertIs(plist["KeepAlive"], True)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-7
    def test_実行ファイルは署名して置いた決まった場所を指す(self):
        """否定確認: 実行ファイルの場所を .build の下に変えると落ちる"""
        self.assertEqual(self.load()["ProgramArguments"], [RECORDER_PATH])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-7
    def test_ログはホームのログのフォルダに書く(self):
        plist = self.load()
        log = "__HOME__/Library/Logs/routine-work-finder-recorder.log"
        self.assertEqual(plist["StandardOutPath"], log)
        self.assertEqual(plist["StandardErrorPath"], log)


class InstallScriptTests(unittest.TestCase):
    """記録係をビルドして署名し、決まった場所に置くスクリプト"""

    def script(self):
        return INSTALL_SCRIPT.read_text(encoding="utf-8")

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-7
    def test_変数名はASCIIだけ(self):
        """否定確認: 日本語の変数名を1つ足すと落ちる(launchd から動く /bin/bash 3.2 が読めない)"""
        names = re.findall(r"^\s*(?:local\s+)?([^\s=#()]+)=", self.script(), flags=re.MULTILINE)
        self.assertTrue(names)
        self.assertEqual([name for name in names if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)], [])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-7
    def test_決まった証明書と識別子で署名して検証する(self):
        """否定確認: 署名の識別子を変えると落ちる(作り直しでアクセシビリティの許可が外れる)"""
        script = self.script()
        self.assertIn('--sign "routine-work-finder code signing"', script)
        self.assertIn("--identifier com.example.routine-work-finder.recorder", script)
        self.assertIn("codesign --verify", script)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-7
    def test_launchdの設定ファイルのホームを置き換えてから置く(self):
        script = self.script()
        self.assertIn("__HOME__", script)
        self.assertIn("Library/LaunchAgents/com.example.routine-work-finder-recorder.plist", script)


if __name__ == "__main__":
    unittest.main()
