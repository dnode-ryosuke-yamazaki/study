"""操作スクリプトのマイクの数え方の切り替え(mic-meeting on|off|show)。

週次レポートでマイクが使用中の時間を会議として数えるかを、操作の記録の設定ファイルの micAsMeeting に書く。
設定ファイルは記録の始め方や記録しないものの追加でも書き換わるため、どの経路でも micAsMeeting が残ることを確かめる。
"""

import json
import unittest

from tests.control_support import ControlTestCase


class MicMeetingWriteTests(ControlTestCase):
    """off・on で micAsMeeting を書く"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-1
    def test_offでfalse_onでtrueを書きほかの項目は変えない(self):
        """否定確認: 書くときにほかの項目を初期値で作り直すと落ちる"""
        before = self.write_config(endsAt="2026-10-31T18:00:00+09:00", excludedTitleWords=["給与"])
        off = self.run_control("mic-meeting", "off")
        self.assertTrue(off["ok"], off)
        self.assertEqual(off["data"], {"micAsMeeting": False, "changed": True})
        self.assertEqual(self.read_config(), {**before, "micAsMeeting": False})
        on = self.run_control("mic-meeting", "on")
        self.assertEqual(on["data"], {"micAsMeeting": True, "changed": True})
        self.assertEqual(self.read_config(), {**before, "micAsMeeting": True})

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-1
    def test_結果の文に次のレポートから効き作り直せば過去の週にも効くと入る(self):
        """否定確認: 効く範囲の説明を結果から外すと落ちる"""
        self.write_config()
        for command, head in (("off", "マイクを会議とみなさない設定にしました"), ("on", "マイクを会議とみなす設定にしました")):
            message = self.run_control("mic-meeting", command)["message"]
            self.assertIn(head, message)
            self.assertIn("次に作る週次レポートから効き", message)
            self.assertIn("作り直せば記録が残っている過去の週にも効きます", message)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-1
    def test_すでに同じ値なら書き換えずchangedをfalseで返す(self):
        """否定確認: 同じ値でも書き換える(config.json の更新が起きる)と落ちる"""
        self.write_config(micAsMeeting=False)
        stamp = self.paths.config.stat().st_mtime_ns
        result = self.run_control("mic-meeting", "off")
        self.assertEqual(result["data"], {"micAsMeeting": False, "changed": False})
        self.assertEqual(result["message"], "すでにマイクを会議とみなさない設定です")
        self.assertEqual(self.paths.config.stat().st_mtime_ns, stamp)
        self.write_config(micAsMeeting=True)
        self.assertEqual(self.run_control("mic-meeting", "on")["message"], "すでにマイクを会議とみなす設定です")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-1
    def test_項目が無い設定ファイルでonを頼むと値を書きchangedはtrue(self):
        """否定確認: 項目が無いのを「すでにみなす設定」とみなして書かないと落ちる"""
        self.write_config()
        self.assertNotIn("micAsMeeting", self.read_config())
        result = self.run_control("mic-meeting", "on")
        self.assertEqual(result["data"], {"micAsMeeting": True, "changed": True})
        self.assertIs(self.read_config()["micAsMeeting"], True)


class MicMeetingShowTests(ControlTestCase):
    """show は今の設定を返すだけで書かない"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-2
    def test_今の値を返し設定ファイルは書き換えない(self):
        """否定確認: show で設定ファイルを書き換えると落ちる"""
        self.write_config(micAsMeeting=False)
        before = self.paths.config.stat()
        result = self.run_control("mic-meeting", "show")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["data"], {"micAsMeeting": False})
        after = self.paths.config.stat()
        # 同じ中身で書き戻されても気づけるよう、更新日時と inode も見る。control.log も作らない
        self.assertEqual((after.st_mtime_ns, after.st_ino), (before.st_mtime_ns, before.st_ino))
        self.assertFalse(self.paths.control_log.exists())

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-2
    def test_設定ファイルが無い・項目が無いときはtrueを返しファイルを作らない(self):
        """否定確認: 設定ファイルが無いときに作る・書けるかを確かめてデータフォルダや control.log を作ると落ちる"""
        result = self.run_control("mic-meeting", "show")
        self.assertEqual(result["data"], {"micAsMeeting": True})
        self.assertEqual(result["message"], "マイクを会議とみなす設定です(既定)")
        self.assertFalse(self.root.exists())
        self.write_config()
        self.assertEqual(self.run_control("mic-meeting", "show")["data"], {"micAsMeeting": True})
        self.assertNotIn("micAsMeeting", self.read_config())

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-2
    def test_設定ファイルが読めないときはconfigUnreadableで返す(self):
        """否定確認: 読めない設定を既定の値として返すと落ちる"""
        self.root.mkdir(parents=True)
        self.paths.config.write_text("{broken", encoding="utf-8")
        result = self.run_control("mic-meeting", "show")
        self.assertEqual((result["ok"], result["error"]), (False, "configUnreadable"))


class MicMeetingPreconditionTests(ControlTestCase):
    """設定ファイルを書き換える操作と同じ前提を確かめる"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-3
    def test_設定ファイルが無ければ初期値で作ってから書く_onでも値を書く(self):
        """否定確認: 設定ファイルが無いときに断ると落ちる"""
        result = self.run_control("mic-meeting", "on")
        self.assertEqual(result["data"], {"micAsMeeting": True, "changed": True})
        config = self.read_config()
        self.assertEqual([app["name"] for app in config["excludedApps"]], ["パスワード", "キーチェーンアクセス", "システム設定"])
        self.assertIs(config["micAsMeeting"], True)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-3
    def test_読めない・形が違う設定ファイルは書き換えずに断る(self):
        """否定確認: 壊れた設定を初期値で上書きすると落ちる"""
        self.root.mkdir(parents=True)
        for text in ("{broken", json.dumps({"version": 1, "endsAt": None, "excludedApps": [], "excludedTitleWords": [],
                                            "micAsMeeting": "no"})):
            with self.subTest(text=text):
                self.paths.config.write_text(text, encoding="utf-8")
                result = self.run_control("mic-meeting", "off")
                self.assertEqual(result["error"], "configUnreadable")
                self.assertEqual(self.paths.config.read_text(encoding="utf-8"), text)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-3
    def test_書けないときは何も書かずdataFolderUnwritableで返す(self):
        """否定確認: 書けるかを確かめずに書きに行くと例外で落ちる"""
        self.write_config()
        text = self.paths.config.read_text(encoding="utf-8")
        self.make_unwritable()
        result = self.run_control("mic-meeting", "off")
        self.assertEqual(result["error"], "dataFolderUnwritable")
        self.assertEqual(self.paths.config.read_text(encoding="utf-8"), text)


class MicMeetingKeptByOtherWritesTests(ControlTestCase):
    """micAsMeeting を false にしたあと、設定ファイルを書き換えるどの経路でも消えない(元の項目をすべて残す)"""

    def setUp(self):
        super().setUp()
        self.write_config(micAsMeeting=False)

    def assert_kept(self, result):
        self.assertTrue(result["ok"], result)
        config = self.read_config()
        self.assertIs(config["micAsMeeting"], False)
        return config

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-3
    def test_記録を始めても残る(self):
        """否定確認: 始めるときに設定を初期値から作り直すと落ちる"""
        self.assert_kept(self.run_control("start", "--until", "2026-10-31T18:00:00+09:00"))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-3
    def test_記録を止めても残る(self):
        """否定確認: 止めるときに設定を初期値から作り直すと落ちる"""
        self.assert_kept(self.run_control("stop"))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-3
    def test_記録しないアプリの追加と削除でも残る(self):
        """否定確認: アプリの一覧だけを書き戻す実装にすると落ちる"""
        add = self.write_input("a.json", {"name": "1Password", "bundleId": None})
        self.assert_kept(self.run_control("exclude-app", "add", "--input-file", str(add)))
        remove = self.write_input("r.json", {"name": "1Password"})
        self.assert_kept(self.run_control("exclude-app", "remove", "--input-file", str(remove)))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-3
    def test_記録しないことばの追加と削除でも残る(self):
        """否定確認: ことばの一覧だけを書き戻す実装にすると落ちる"""
        add = self.write_input("a.json", {"word": "給与"})
        self.assert_kept(self.run_control("exclude-word", "add", "--input-file", str(add)))
        remove = self.write_input("r.json", {"word": "給与"})
        self.assert_kept(self.run_control("exclude-word", "remove", "--input-file", str(remove)))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#マイクの数え方の切り替え-3
    def test_依頼文からのまとめての追加でも残る(self):
        """否定確認: まとめての追加で設定を作り直すと落ちる"""
        request = self.write_input("req.txt", "/routine-work-finder 記録しないものに次を足してください。\nことば: 給与\n")
        self.assert_kept(self.run_control("exclude-add", "--request-file", str(request)))

    # 仕様: apps/routine-work-finder/specs/activity-recording/appendix.md#設定ファイルの形
    def test_付録に無い項目も書き換えのあとに残る(self):
        """否定確認: 既知の項目だけを書き戻すと落ちる"""
        raw = self.read_config()
        raw["futureField"] = {"a": 1}
        self.paths.config.write_text(json.dumps(raw), encoding="utf-8")
        self.run_control("stop")
        self.assertEqual(self.read_config()["futureField"], {"a": 1})


if __name__ == "__main__":
    unittest.main()
