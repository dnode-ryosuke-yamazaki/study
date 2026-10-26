"""操作スクリプトのデータフォルダと設定ファイルの読み書き。

Skill が書いた設定を、記録係が書きかけを読まずに次の回から使えるよう、一時ファイルに書いてから名前を付け替える。
生の記録を同期フォルダへ上げないよう、データフォルダが同期フォルダの下を指していたら断る。
"""

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from routine_work_finder import config_store, paths

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "recorder" / "Tests" / "RecorderCoreTests" / "Fixtures" / "config.json"


def fixture_config():
    """記録係の契約テストが読む設定ファイルの中身(初期値に終わりの日時とマイクの扱いを足したもの)"""
    config = config_store.default_config()
    config["endsAt"] = "2026-10-31T18:00:00+09:00"
    config["micAsMeeting"] = True
    return config


class TemporaryDataFolder(unittest.TestCase):
    def setUp(self):
        base = os.environ.get("TMPDIR") or tempfile.gettempdir()
        self.temporary = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.temporary.name) / "routine-work-finder"
        self.paths = paths.DataPaths(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def mode(self, path):
        return stat.S_IMODE(path.stat().st_mode)


class DataFolderTests(unittest.TestCase):
    """データフォルダの場所"""

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録を残す場所と期間-1
    def test_既定のデータフォルダはローカルのApplication_Supportの下(self):
        found = paths.data_paths(environ={}, home=Path("/Users/someone"))
        self.assertEqual(found.root, Path("/Users/someone/Library/Application Support/routine-work-finder"))

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録を残す場所と期間-1
    def test_データフォルダが同期フォルダの下を指していたら断る(self):
        """否定確認: 同期フォルダの判定を外すと落ちる"""
        for root in [
            "/Users/someone/Library/CloudStorage/OneDrive-Example/rwf",
            "/Users/someone/Library/Mobile Documents/com~apple~CloudDocs/rwf",
            "/Users/someone/Dropbox/rwf",
        ]:
            with self.subTest(root=root), self.assertRaises(paths.SyncFolderError):
                paths.data_paths(environ={"RWF_DATA_DIR": root}, home=Path("/Users/someone"))


class DefaultConfigTests(unittest.TestCase):
    """設定ファイルの初期値"""

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-1
    def test_記録しないアプリの初期値はパスワード_キーチェーンアクセス_システム設定の3つ(self):
        """否定確認: 初期値に 1Password を足すと落ちる"""
        self.assertEqual(
            config_store.default_config()["excludedApps"],
            [
                {"name": "パスワード", "bundleId": "com.apple.Passwords"},
                {"name": "キーチェーンアクセス", "bundleId": "com.apple.keychainaccess"},
                {"name": "システム設定", "bundleId": "com.apple.systempreferences"},
            ],
        )

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-2
    def test_記録しないことばの初期値は空_終わりの日時も無い(self):
        config = config_store.default_config()
        self.assertEqual(config["excludedTitleWords"], [])
        self.assertIsNone(config["endsAt"])
        self.assertIsNone(config["stoppedAt"])
        self.assertEqual(config["version"], 1)


class WriteConfigTests(TemporaryDataFolder):
    """設定ファイルを書く"""

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録を残す場所と期間-1
    def test_データフォルダは700_設定ファイルは600で置く(self):
        """否定確認: 権限を指定せずに作ると落ちる"""
        config_store.write_config(self.paths, config_store.default_config())
        self.assertEqual(self.mode(self.root), 0o700)
        self.assertEqual(self.mode(self.paths.config), 0o600)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-5
    def test_一時ファイルに書いてから名前を付け替え_一時ファイルを残さない(self):
        """否定確認: config.json に直接書くと落ちる(config.json.tmp からの付け替えが起きない)"""
        config_store.write_config(self.paths, config_store.default_config())
        with mock.patch.object(config_store.os, "replace", wraps=os.replace) as replace:
            config_store.write_config(self.paths, fixture_config())
        replace.assert_called_once_with(self.root / "config.json.tmp", self.paths.config)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["config.json"])
        self.assertEqual(json.loads(self.paths.config.read_text(encoding="utf-8"))["endsAt"], "2026-10-31T18:00:00+09:00")


class ReadConfigTests(TemporaryDataFolder):
    """設定ファイルを読む(記録係と同じ基準で読めない形を見分ける)"""

    def write_raw(self, text):
        self.root.mkdir(parents=True)
        self.paths.config.write_text(text, encoding="utf-8")

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-1
    def test_設定ファイルが無いときは無いと返す(self):
        """否定確認: 無いときに読めないと返すと落ちる"""
        self.assertEqual(config_store.read_config(self.paths), config_store.ConfigRead("missing", None, None))

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-1
    def test_書いた設定を読み戻せる(self):
        config_store.write_config(self.paths, fixture_config())
        result = config_store.read_config(self.paths)
        self.assertEqual(result.state, "ok")
        self.assertEqual(result.config, fixture_config())

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-1
    def test_止めた日時の項目が欠けていても読め_無いとみなす(self):
        self.write_raw('{"version":1,"endsAt":null,"excludedApps":[],"excludedTitleWords":[]}')
        result = config_store.read_config(self.paths)
        self.assertEqual(result.state, "ok")
        self.assertIsNone(result.config["stoppedAt"])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-1
    def test_壊れた設定は理由を付けて読めないと返す(self):
        """否定確認: 型の確かめを外す、または日時の時差の確かめを外すと落ちる"""
        cases = {
            '{"version":1,"endsAt":': "invalidJson",
            "[]": "invalidJson",
            '{"version":1,"excludedApps":[],"excludedTitleWords":[]}': "missingField:endsAt",
            '{"version":1,"endsAt":20261031,"excludedApps":[],"excludedTitleWords":[]}': "invalidType:endsAt",
            '{"version":1,"endsAt":"10月31日","excludedApps":[],"excludedTitleWords":[]}': "invalidType:endsAt",
            '{"version":1,"endsAt":"2026-10-31T18:00:00","excludedApps":[],"excludedTitleWords":[]}': "invalidType:endsAt",
            '{"version":1,"endsAt":null,"excludedApps":["x"],"excludedTitleWords":[]}': "invalidType:excludedApps",
            '{"version":true,"endsAt":null,"excludedApps":[],"excludedTitleWords":[]}': "invalidType:version",
        }
        for text, reason in cases.items():
            with self.subTest(text=text):
                if self.paths.config.exists():
                    self.paths.config.unlink()
                if not self.root.exists():
                    self.root.mkdir(parents=True)
                self.paths.config.write_text(text, encoding="utf-8")
                self.assertEqual(config_store.read_config(self.paths), config_store.ConfigRead("unreadable", None, reason))

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-1
    def test_UTF8として読めない設定は壊れた設定として返す(self):
        """否定確認: 文字に直せない例外を拾わずに投げると落ちる(記録係と同じく invalidJson にする)"""
        self.root.mkdir(parents=True)
        self.paths.config.write_bytes(b'{"version":1,"endsAt":null,"excludedApps":[],"excludedTitleWords":["\xe7\xb5"]}')
        self.assertEqual(config_store.read_config(self.paths), config_store.ConfigRead("unreadable", None, "invalidJson"))


class MicAsMeetingConfigTests(TemporaryDataFolder):
    """週次レポートがマイクを会議とみなすかの項目 micAsMeeting と、付録に無い項目を残す読み書き"""

    BASE = '"version":1,"endsAt":null,"excludedApps":[],"excludedTitleWords":[]'

    def write_raw(self, text):
        self.root.mkdir(parents=True)
        self.paths.config.write_text(text, encoding="utf-8")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-1
    def test_micAsMeetingの真偽値を読んで書き戻せる(self):
        """否定確認: 読み込みで micAsMeeting を捨てると落ちる"""
        for value in (True, False):
            with self.subTest(value=value):
                config_store.write_config(self.paths, {**config_store.default_config(), "micAsMeeting": value})
                result = config_store.read_config(self.paths)
                self.assertEqual(result.state, "ok")
                self.assertIs(result.config["micAsMeeting"], value)
                self.assertIs(config_store.mic_as_meeting(result.config), value)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-5
    def test_項目が無い設定はみなす扱いで読め_項目を足さずに残す(self):
        """否定確認: 欠けているときに false とみなす・読んだ結果へ勝手に項目を足すと落ちる"""
        self.write_raw("{" + self.BASE + "}")
        result = config_store.read_config(self.paths)
        self.assertEqual(result.state, "ok")
        self.assertNotIn("micAsMeeting", result.config)
        self.assertIs(config_store.mic_as_meeting(result.config), True)
        self.assertIs(config_store.mic_as_meeting(None), True)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-5
    def test_micAsMeetingが真偽値でない設定は形が違うとみなす(self):
        """否定確認: 真偽値の確かめを外す(0・文字列・null を通す)と落ちる"""
        for text in ('0', '1', '"false"', 'null', '[]'):
            with self.subTest(value=text):
                self.write_raw('{' + self.BASE + ',"micAsMeeting":' + text + '}')
                self.assertEqual(config_store.read_config(self.paths),
                                 config_store.ConfigRead("unreadable", None, "invalidType:micAsMeeting"))
                self.paths.config.unlink()
                self.root.rmdir()

    # 仕様: apps/routine-work-finder/specs/activity-recording/appendix.md#設定ファイルの形
    def test_付録に無い項目も読み込みの結果に持ち_書き戻しても落とさない(self):
        """否定確認: 既知の項目だけを書き戻すと落ちる"""
        self.write_raw('{' + self.BASE + ',"futureField":{"a":[1,2]},"note":"x"}')
        result = config_store.read_config(self.paths)
        self.assertEqual(result.config["futureField"], {"a": [1, 2]})
        config_store.write_config(self.paths, result.config)
        written = json.loads(self.paths.config.read_text(encoding="utf-8"))
        self.assertEqual(written["futureField"], {"a": [1, 2]})
        self.assertEqual(written["note"], "x")


class RecorderConfigFixtureTests(TemporaryDataFolder):
    """記録係(Swift)の契約テストが読む設定ファイルの fixture を、操作スクリプトが書く形と同じに保つ。
    書き換えるときは RWF_FIXTURE_OUT にフォルダを指定してこのテストを回し、出てきた config.json で置き換える"""

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-1
    def test_操作スクリプトが書く設定ファイルと記録係のfixtureが一致している(self):
        config_store.write_config(self.paths, fixture_config())
        written = self.paths.config.read_text(encoding="utf-8")
        out_dir = os.environ.get("RWF_FIXTURE_OUT")
        if out_dir:
            Path(out_dir, "config.json").write_text(written, encoding="utf-8")
        self.assertEqual(FIXTURE_PATH.read_text(encoding="utf-8"), written)


if __name__ == "__main__":
    unittest.main()
