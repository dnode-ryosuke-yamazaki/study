"""操作スクリプトの記録しないアプリ・ことばの追加・削除・一覧と、週次レポートの依頼文からのまとめての追加。

自由に書かれた文(ことば・アプリ名・依頼文)は入力ファイルで受け、シェルのコマンド文字列に入れない。
入力ファイルは読み終えたら消すが、データフォルダに書けないときは残して手元のターミナルで使えるようにする。
"""

import os
import shutil
import stat
import unittest
from pathlib import Path

from tests.control_support import ControlTestCase

REQUEST_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "exclusion_request.txt"
PHRASE = "/routine-work-finder 記録しないものに次を足してください。"


class ExcludeAppTests(ControlTestCase):
    """記録しないアプリを足す・外す"""

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-5
    def test_入力ファイルのアプリを足し_入力ファイルを消す(self):
        """否定確認: 読み終えた入力ファイルを消さないと落ちる"""
        path = self.write_input("app.json", {"name": "1Password", "bundleId": "com.1password.1password"})
        result = self.run_control("exclude-app", "add", "--input-file", str(path))
        self.assertTrue(result["ok"], result)
        self.assertIn({"name": "1Password", "bundleId": "com.1password.1password"}, self.read_config()["excludedApps"])
        self.assertFalse(path.exists())

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-5
    def test_アプリを外す_一覧に無ければ断る(self):
        self.write_config()
        path = self.write_input("app.json", {"name": "システム設定"})
        self.assertTrue(self.run_control("exclude-app", "remove", "--input-file", str(path))["ok"])
        self.assertNotIn("システム設定", [app["name"] for app in self.read_config()["excludedApps"]])
        path = self.write_input("app.json", {"name": "無いアプリ"})
        result = self.run_control("exclude-app", "remove", "--input-file", str(path))
        self.assertEqual(result["error"], "notFound")
        self.assertEqual([app["name"] for app in result["data"]["excludedApps"]], ["パスワード", "キーチェーンアクセス"])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-5
    def test_すでにあるアプリは足さずにすでにあると返す(self):
        """否定確認: すでにあるアプリを二重に足すと落ちる"""
        self.write_config()
        before = self.read_config()["excludedApps"]
        path = self.write_input("app.json", {"name": "システム設定", "bundleId": None})
        result = self.run_control("exclude-app", "add", "--input-file", str(path))
        self.assertTrue(result["ok"], result)
        self.assertIn("すでに", result["message"])
        self.assertEqual(self.read_config()["excludedApps"], before)
        self.assertEqual(result["data"]["excludedApps"], before)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-5
    def test_設定ファイルが壊れているときは除外の追加を断る(self):
        """否定確認: 壊れた設定を初期値で上書きして足すと落ちる"""
        self.root.mkdir(parents=True)
        self.paths.config.write_text("{broken", encoding="utf-8")
        path = self.write_input("app.json", {"name": "1Password", "bundleId": None})
        self.assertEqual(self.run_control("exclude-app", "add", "--input-file", str(path))["error"], "configUnreadable")
        self.assertEqual(self.paths.config.read_text(encoding="utf-8"), "{broken")

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-5
    def test_入力ファイルが無い_形が違うときは断る(self):
        for name, content in [("missing.json", None), ("broken.json", "{x"), ("shape.json", {"word": "x"}), ("empty.json", {"name": " "})]:
            with self.subTest(name=name):
                path = self.input_dir / name if content is None else self.write_input(name, content)
                result = self.run_control("exclude-app", "add", "--input-file", str(path))
                self.assertEqual(result["error"], "badInputFile" if name != "empty.json" else "emptyWord")


class ExcludeWordTests(ControlTestCase):
    """記録しないことばを足す・外す"""

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-5
    def test_ことばの前後の空白を除いて足し_空なら断る(self):
        """否定確認: 前後の空白を除かずに足すと落ちる"""
        path = self.write_input("word.json", {"word": "  給与 "})
        self.assertTrue(self.run_control("exclude-word", "add", "--input-file", str(path))["ok"])
        self.assertEqual(self.read_config()["excludedTitleWords"], ["給与"])
        path = self.write_input("word.json", {"word": "   "})
        self.assertEqual(self.run_control("exclude-word", "add", "--input-file", str(path))["error"], "emptyWord")

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-5
    def test_ことばを外す(self):
        self.write_config(excludedTitleWords=["給与", "人事"])
        path = self.write_input("word.json", {"word": "給与"})
        self.assertTrue(self.run_control("exclude-word", "remove", "--input-file", str(path))["ok"])
        self.assertEqual(self.read_config()["excludedTitleWords"], ["人事"])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-5
    def test_一覧に無いことばは外さずに断り_今の一覧を返す(self):
        """否定確認: 一致しないのに一覧を書き換える・一覧を返さないと落ちる"""
        self.write_config(excludedTitleWords=["人事"])
        path = self.write_input("word.json", {"word": "給与"})
        result = self.run_control("exclude-word", "remove", "--input-file", str(path))
        self.assertEqual(result["error"], "notFound")
        self.assertEqual(result["data"]["excludedTitleWords"], ["人事"])
        self.assertEqual(self.read_config()["excludedTitleWords"], ["人事"])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-5
    def test_すでにあることばは足さずにすでにあると返す(self):
        """否定確認: すでにあることばを二重に足すと落ちる"""
        self.write_config(excludedTitleWords=["給与"])
        path = self.write_input("word.json", {"word": "給与"})
        result = self.run_control("exclude-word", "add", "--input-file", str(path))
        self.assertTrue(result["ok"], result)
        self.assertIn("すでに", result["message"])
        self.assertEqual(self.read_config()["excludedTitleWords"], ["給与"])
        self.assertEqual(result["data"]["excludedTitleWords"], ["給与"])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-5
    def test_データフォルダに書けないときは入力ファイルを残し_その絶対パスを返す(self):
        """否定確認: 書けるかを確かめる前に入力ファイルを読んで消すと落ちる"""
        path = self.write_input("word.json", {"word": "給与"})
        self.make_unwritable()
        result = self.run_control("exclude-word", "add", "--input-file", str(path))
        self.assertEqual(result["error"], "dataFolderUnwritable")
        self.assertEqual(result["inputFile"], str(path.resolve()))
        self.assertTrue(path.exists())

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-5
    def test_ログには件数だけを書き_ことばは書かない(self):
        """否定確認: ログにことばを書くと落ちる"""
        path = self.write_input("word.json", {"word": "給与"})
        self.run_control("exclude-word", "add", "--input-file", str(path))
        log = self.paths.control_log.read_text(encoding="utf-8")
        self.assertNotIn("給与", log)
        self.assertIn("exclude-word add count=1", log)


class ExcludeListTests(ControlTestCase):
    """記録しないアプリ・ことばの一覧"""

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-6
    def test_今の一覧を返す(self):
        self.write_config(excludedTitleWords=["給与"])
        data = self.run_control("exclude-list")["data"]
        self.assertEqual(data["excludedTitleWords"], ["給与"])
        self.assertEqual(len(data["excludedApps"]), 3)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-6
    def test_設定ファイルが無いときは初期値を返し_ファイルを作らない(self):
        """否定確認: 一覧のために設定ファイルを作ると落ちる"""
        data = self.run_control("exclude-list")["data"]
        self.assertEqual(len(data["excludedApps"]), 3)
        self.assertFalse(self.paths.config.exists())


class ExcludeAddRequestTests(ControlTestCase):
    """週次レポートの記録しない候補からコピーした依頼文で、まとめて足す"""

    def request(self, text):
        return self.write_input("request.txt", text)

    def add(self, request_path, bundle_ids_path=None):
        argv = ["exclude-add", "--request-file", str(request_path)]
        if bundle_ids_path:
            argv += ["--bundle-ids-file", str(bundle_ids_path)]
        return self.run_control(*argv)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-7
    def test_週次レポートと共有するfixtureの依頼文をそのまま読み_ことば1件とアプリ1件を足す(self):
        """否定確認: 「ことば: 」の行を読み分けないと落ちる"""
        request = self.input_dir / "request.txt"
        shutil.copy(REQUEST_FIXTURE, request)
        result = self.add(request)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["data"]["added"], {"words": ["給与明細"], "apps": ["家計簿"]})
        self.assertIn({"name": "家計簿", "bundleId": None}, self.read_config()["excludedApps"])
        self.assertEqual(result["data"]["excludedTitleWords"], ["給与明細"])
        self.assertFalse(request.exists())

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-7
    def test_1行目が決まり文句でなければ何も足さずに断る(self):
        """否定確認: 1行目を確かめないと落ちる"""
        self.write_config()
        before = self.paths.config.read_text(encoding="utf-8")
        result = self.add(self.request("記録しないものを足して\nことば: 給与明細\n"))
        self.assertEqual(result["error"], "badRequest")
        self.assertEqual(self.paths.config.read_text(encoding="utf-8"), before)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-7
    def test_形の違う行は除いて返し_空の行は読み飛ばす(self):
        result = self.add(self.request(f"{PHRASE}\nことば: 給与明細\n\nサイト: 給与システム\nことば:   \n"))
        self.assertEqual(result["data"]["added"]["words"], ["給与明細"])
        self.assertEqual(result["data"]["skippedLines"], ["サイト: 給与システム", "ことば:"])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-7
    def test_すでにあるものは足さずにすでにあると返す(self):
        """否定確認: すでにあるものを二重に足すと落ちる"""
        self.write_config(excludedTitleWords=["給与明細"])
        result = self.add(self.request(f"{PHRASE}\nことば: 給与明細\nアプリ: パスワード\n"))
        self.assertEqual(result["data"]["added"], {"words": [], "apps": []})
        self.assertEqual(result["data"]["alreadyExists"], {"words": ["給与明細"], "apps": ["パスワード"]})
        self.assertEqual(self.read_config()["excludedTitleWords"], ["給与明細"])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-7
    def test_設定ファイルが読めないときは何も足さずに断る(self):
        self.root.mkdir(parents=True)
        self.paths.config.write_text("{broken", encoding="utf-8")
        self.assertEqual(self.add(self.request(f"{PHRASE}\nことば: 給与明細\n"))["error"], "configUnreadable")
        self.assertEqual(self.paths.config.read_text(encoding="utf-8"), "{broken")

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-7
    def test_ことば2件と重なりをまとめて1回の書き換えで足す(self):
        """否定確認: 同じ依頼文の中の重なりをまとめないと落ちる"""
        result = self.add(self.request(f"{PHRASE}\nことば: 給与明細\nことば: 人事評価\nことば: 給与明細\n"))
        self.assertEqual(result["data"]["added"]["words"], ["給与明細", "人事評価"])
        self.assertEqual(self.read_config()["excludedTitleWords"], ["給与明細", "人事評価"])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-7
    def test_有効な行が1つも無いときは設定ファイルを書き換えず_空の追加で返す(self):
        """否定確認: 有効な行が無くても設定ファイルを作り直すと落ちる"""
        result = self.add(self.request(f"{PHRASE}\nサイト: 給与システム\n"))
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["added"], {"words": [], "apps": []})
        self.assertFalse(self.paths.config.exists())

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-7
    def test_バンドルIDは依頼文にある新しいアプリにだけ付け_それ以外は無視する(self):
        """否定確認: 依頼文に無いアプリまで足すと落ちる"""
        bundle_ids = self.write_input("ids.json", {"家計簿": "com.example.kakeibo", "無関係": "com.example.other",
                                                   "パスワード": "com.example.fake"})
        result = self.add(self.request(f"{PHRASE}\nアプリ: 家計簿\nアプリ: パスワード\n"), bundle_ids)
        apps = self.read_config()["excludedApps"]
        self.assertIn({"name": "家計簿", "bundleId": "com.example.kakeibo"}, apps)
        self.assertNotIn("無関係", [app["name"] for app in apps])
        self.assertIn({"name": "パスワード", "bundleId": "com.apple.Passwords"}, apps)
        self.assertFalse(bundle_ids.exists())
        self.assertTrue(result["ok"])

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-7
    def test_書けないときは依頼文とバンドルIDの2つの入力ファイルを残しパスを返す(self):
        request = self.request(f"{PHRASE}\nアプリ: 家計簿\n")
        bundle_ids = self.write_input("ids.json", {"家計簿": "com.example.kakeibo"})
        self.make_unwritable()
        result = self.add(request, bundle_ids)
        self.assertEqual(result["error"], "dataFolderUnwritable")
        self.assertEqual((result["inputFile"], result["bundleIdsFile"]), (str(request.resolve()), str(bundle_ids.resolve())))
        self.assertTrue(request.exists() and bundle_ids.exists())

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-7
    def test_依頼文のファイルが無い_読めないときは断る(self):
        self.assertEqual(self.add(self.input_dir / "missing.txt")["error"], "badInputFile")
        unreadable = self.request(f"{PHRASE}\nことば: x\n")
        os.chmod(unreadable, 0)
        try:
            self.assertEqual(self.add(unreadable)["error"], "badInputFile")
        finally:
            os.chmod(unreadable, stat.S_IRUSR | stat.S_IWUSR)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-7
    def test_ログには件数だけを書く(self):
        self.add(self.request(f"{PHRASE}\nことば: 給与明細\nアプリ: 家計簿\nサイト: x\n"))
        log = self.paths.control_log.read_text(encoding="utf-8")
        self.assertIn("exclude added words=1 apps=1 alreadyExists=0 skipped=1", log)
        self.assertNotIn("給与明細", log)


if __name__ == "__main__":
    unittest.main()
