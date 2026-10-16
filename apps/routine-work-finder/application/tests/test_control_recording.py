"""操作スクリプトの記録の開始・停止・状態の確認。

チャットから終わりの日時を決めて始め、止め、状態を確かめられるようにする。
終わりの日時を決めない記録は始めず、壊れた設定ファイルは初期値で上書きしない。
"""

import json
import os
import stat
import unittest

from tests.control_support import ControlTestCase, jst, marker, sample


class StartTests(ControlTestCase):
    """記録を始める"""

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-1
    def test_終わりの日時を設定ファイルに書き_止めた日時を戻す(self):
        """否定確認: stoppedAt を null に戻さないと落ちる"""
        self.write_config(stoppedAt="2026-10-06T18:00:00+09:00")
        result = self.run_control("start", "--until", "2026-10-31T18:00:00+09:00")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["message"], "10月31日 18:00 まで記録します")
        config = self.read_config()
        self.assertEqual(config["endsAt"], "2026-10-31T18:00:00+09:00")
        self.assertIsNone(config["stoppedAt"])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-1
    def test_設定ファイルが無いときは初期値で作ってから終わりの日時を書く(self):
        result = self.run_control("start", "--until", "2026-10-31T18:00:00+09:00")
        self.assertTrue(result["ok"], result)
        config = self.read_config()
        self.assertEqual(len(config["excludedApps"]), 3)
        self.assertEqual(config["endsAt"], "2026-10-31T18:00:00+09:00")

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-1
    def test_設定ファイルが壊れているときは上書きせずに断る(self):
        """否定確認: 壊れた設定を初期値で上書きすると落ちる"""
        self.root.mkdir(parents=True)
        self.paths.config.write_text("{broken", encoding="utf-8")
        result = self.run_control("start", "--until", "2026-10-31T18:00:00+09:00")
        self.assertEqual((result["ok"], result["error"]), (False, "configUnreadable"))
        self.assertEqual(self.paths.config.read_text(encoding="utf-8"), "{broken")

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-1
    def test_止めた日時の項目が欠けた設定ファイルでも始められる(self):
        self.root.mkdir(parents=True)
        self.paths.config.write_text('{"version":1,"endsAt":null,"excludedApps":[],"excludedTitleWords":[]}', encoding="utf-8")
        result = self.run_control("start", "--until", "2026-10-31T18:00:00+09:00")
        self.assertTrue(result["ok"], result)
        self.assertIsNone(self.read_config()["stoppedAt"])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-1
    def test_データフォルダに書けないときは何も書かずに返す(self):
        """否定確認: 書けるかを確かめずに書き始めると落ちる(例外で止まる)"""
        self.make_unwritable()
        result = self.run_control("start", "--until", "2026-10-31T18:00:00+09:00")
        self.assertEqual((result["ok"], result["error"]), (False, "dataFolderUnwritable"))
        os.chmod(self.root, stat.S_IRWXU)
        self.assertEqual(list(self.root.iterdir()), [])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-1
    def test_操作スクリプトのログに書けないときも何も書かずに返す(self):
        self.write_config()
        self.paths.control_log.write_text("", encoding="utf-8")
        os.chmod(self.paths.control_log, stat.S_IRUSR)
        before = self.paths.config.read_text(encoding="utf-8")
        result = self.run_control("start", "--until", "2026-10-31T18:00:00+09:00")
        self.assertEqual(result["error"], "dataFolderUnwritable")
        self.assertEqual(self.paths.config.read_text(encoding="utf-8"), before)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-2、apps/routine-work-finder/specs/activity-recording/requirements.md#使ってよい期間-1
    def test_終わりの日時が無い_読めないときは始めない(self):
        """否定確認: 終わりの日時なしで始めると落ちる"""
        for argv in [("start",), ("start", "--until", "10月31日")]:
            with self.subTest(argv=argv):
                result = self.run_control(*argv)
                self.assertEqual((result["ok"], result["error"]), (False, "missingEndsAt"))
        self.assertFalse(self.paths.config.exists())

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-2
    def test_今と同じか前の日時では始めない(self):
        """否定確認: 今との比較を `<` にすると落ちる(今と同じ日時で始めてしまう)"""
        self.write_config()
        before = self.paths.config.read_text(encoding="utf-8")
        for until in ["2026-10-07T10:00:00+09:00", "2026-10-07T09:59:59+09:00"]:
            with self.subTest(until=until):
                result = self.run_control("start", "--until", until)
                self.assertEqual((result["ok"], result["error"]), (False, "pastEndsAt"))
        self.assertEqual(self.paths.config.read_text(encoding="utf-8"), before)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-3
    def test_記録中に別の終わりの日時を伝えると置き換える(self):
        self.write_config(endsAt="2026-10-31T18:00:00+09:00")
        result = self.run_control("start", "--until", "2026-11-15T12:00:00+09:00")
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.read_config()["endsAt"], "2026-11-15T12:00:00+09:00")

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-8
    def test_アクセシビリティの許可が無いときはオンにする案内を返す(self):
        """否定確認: 許可の有無を見ずに案内を返す(または返さない)と落ちる"""
        self.write_status(self.now, accessibility=False)
        notices = self.run_control("start", "--until", "2026-10-31T18:00:00+09:00")["notices"]
        self.assertTrue(any("アクセシビリティ" in notice for notice in notices), notices)

        self.write_status(self.now, accessibility=True)
        notices = self.run_control("start", "--until", "2026-10-31T18:00:00+09:00")["notices"]
        self.assertFalse(any("アクセシビリティ" in notice for notice in notices), notices)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-6
    def test_記録係が動いていないときはセットアップの案内を返す(self):
        notices = self.run_control("start", "--until", "2026-10-31T18:00:00+09:00")["notices"]
        self.assertTrue(any("記録係が動いていません" in notice for notice in notices), notices)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-1
    def test_ログには操作と終わりの日時だけを書く(self):
        self.run_control("start", "--until", "2026-10-31T18:00:00+09:00")
        log = self.paths.control_log.read_text(encoding="utf-8")
        self.assertEqual(log, "2026-10-07T10:00:00+09:00 INFO start endsAt=2026-10-31T18:00:00+09:00\n")


class StopTests(ControlTestCase):
    """記録を止める"""

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-5
    def test_止めると終わりの日時が消え_止めた日時が入る(self):
        """否定確認: 止めた日時を書かないと落ちる(記録係が停止の理由を止める依頼と見分けられない)"""
        self.write_config(endsAt="2026-10-31T18:00:00+09:00")
        result = self.run_control("stop")
        self.assertTrue(result["ok"], result)
        config = self.read_config()
        self.assertIsNone(config["endsAt"])
        self.assertEqual(config["stoppedAt"], "2026-10-07T10:00:00+09:00")

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-1
    def test_設定ファイルが壊れているときは止める操作も断る(self):
        self.root.mkdir(parents=True)
        self.paths.config.write_text("{broken", encoding="utf-8")
        self.assertEqual(self.run_control("stop")["error"], "configUnreadable")
        self.assertEqual(self.paths.config.read_text(encoding="utf-8"), "{broken")


class StatusTests(ControlTestCase):
    """記録の状態を確かめる"""

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-6
    def test_設定ファイルが無いときは停止中_終わりの日時なしを返し_読めないとは返さない(self):
        """否定確認: 設定ファイルが無いときに読めないと返すと落ちる"""
        data = self.run_control("status")["data"]
        self.assertEqual((data["recording"], data["endsAt"], data["configError"]), (False, None, None))
        self.assertFalse(self.paths.config.exists())

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-6
    def test_終わりの日時が今より後なら記録中_そうでなければ停止中(self):
        self.write_config(endsAt="2026-10-31T18:00:00+09:00")
        self.assertTrue(self.run_control("status")["data"]["recording"])
        self.write_config(endsAt="2026-10-07T10:00:00+09:00")
        self.assertFalse(self.run_control("status")["data"]["recording"])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-6
    def test_状態のファイルがまだ無いときは記録係が動いていないと返す(self):
        self.write_config(endsAt="2026-10-31T18:00:00+09:00")
        data = self.run_control("status")["data"]
        self.assertFalse(data["recorderRunning"])
        self.assertIsNone(data["accessibilityGranted"])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-6
    def test_記録係の最後の更新が29秒前なら動いている_30秒前なら止まっている(self):
        """否定確認: 30秒との比較を `>` にすると落ちる"""
        self.write_status(jst("2026-10-07T09:59:31"))
        self.assertTrue(self.run_control("status")["data"]["recorderRunning"])
        self.write_status(jst("2026-10-07T09:59:30"))
        self.assertFalse(self.run_control("status")["data"]["recorderRunning"])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-6
    def test_記録係が設定ファイルを読めなかった理由を返す(self):
        self.write_config(endsAt="2026-10-31T18:00:00+09:00")
        self.write_status(self.now, config_error="missingField:endsAt")
        self.assertEqual(self.run_control("status")["data"]["configError"], "missingField:endsAt")

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-6
    def test_操作スクリプトが設定ファイルを読めないときも読めないと返す(self):
        self.root.mkdir(parents=True)
        self.paths.config.write_text("{broken", encoding="utf-8")
        result = self.run_control("status")
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["configError"], "invalidJson")
        self.assertIn("設定ファイルが読めません", result["message"])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-6
    def test_今日の記録時間は開始と停止の行を数えず_行数に5秒を掛ける(self):
        """否定確認: 開始・停止の行も数えると落ちる"""
        self.write_config(endsAt="2026-10-31T18:00:00+09:00")
        self.write_records(marker("2026-10-06T23:59:55", "start"), sample("2026-10-06T23:59:55"),
                           marker("2026-10-07T09:00:00", "start"), sample("2026-10-07T09:00:00"), sample("2026-10-07T09:00:05"),
                           marker("2026-10-07T09:00:10", "excluded"), marker("2026-10-07T09:00:12", "stop", reason="stopRequested"))
        self.assertEqual(self.run_control("status")["data"]["todayRecordedSeconds"], 15)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-6
    def test_記録中で最後の行が数秒前なら取れなかった時間帯を返さない(self):
        self.write_config(endsAt="2026-10-31T18:00:00+09:00")
        self.write_records(marker("2026-10-07T09:59:50", "start"), sample("2026-10-07T09:59:50"), sample("2026-10-07T09:59:55"))
        self.assertEqual(self.run_control("status")["data"]["gaps"], [])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-6
    def test_記録係が止まって最後の行から30秒以上空いていればその時間帯を返す(self):
        """否定確認: 前日0時から今までの範囲で求めず、今日の0時からにすると落ちる(前日の空きが消える)"""
        self.write_config(endsAt="2026-10-31T18:00:00+09:00")
        self.write_records(marker("2026-10-06T17:00:00", "start"), sample("2026-10-06T17:00:00"), sample("2026-10-06T17:10:00"),
                           sample("2026-10-07T09:40:00"))
        gaps = self.run_control("status")["data"]["gaps"]
        self.assertEqual(gaps, [
            {"start": "2026-10-07T09:40:00+09:00", "end": "2026-10-07T10:00:00+09:00"},
            {"start": "2026-10-06T17:10:00+09:00", "end": "2026-10-07T09:40:00+09:00"},
            {"start": "2026-10-06T17:00:00+09:00", "end": "2026-10-06T17:10:00+09:00"},
        ])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-6
    def test_状態の確認は何も書かない(self):
        self.write_config(endsAt="2026-10-31T18:00:00+09:00")
        before = sorted(p.name for p in self.root.iterdir())
        self.run_control("status")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), before)


class MainTests(ControlTestCase):
    """コマンドとして呼んだときの結果の返し方"""

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-6
    def test_結果は標準出力に1つのJSONで返す(self):
        import io
        from contextlib import redirect_stdout
        from routine_work_finder import control
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = control.main(["status"], now=self.now, environ={"RWF_DATA_DIR": str(self.root)})
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(buffer.getvalue())["ok"])


if __name__ == "__main__":
    unittest.main()
