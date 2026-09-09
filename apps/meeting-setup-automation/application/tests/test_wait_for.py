"""台帳ファイルの到着待ち(tasks.md 7)のテスト。

フローが書き出すファイルは依頼IDから名前が決まるため、フォルダの一覧は取らずその名前の
ファイルの有無だけを一定間隔で確かめる。途中まで書かれたファイルは書き込み中とみなして待ち、
上限を超えたら打ち切る。時間は差し替え可能な時計と待ち関数で進める(テストで実時間を使わない)。
"""

import json
import tempfile
import unittest
from pathlib import Path

import wait_for


class 偽の時計:
    def __init__(self):
        self.今 = 0.0
        self.待った秒 = []

    def time(self):
        return self.今

    def sleep(self, 秒):
        self.待った秒.append(秒)
        self.今 += 秒


class 到着待ち(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name, "candidates-X-a1.json")
        self.時計 = 偽の時計()
        self.進捗 = []

    def tearDown(self):
        self._tmp.cleanup()

    def _待つ(self, 上限秒=30, 間隔秒=5, 現れる回=None, 内容=None):
        回数 = {"n": 0}

        def 確認前():
            回数["n"] += 1
            if 現れる回 is not None and 回数["n"] == 現れる回:
                self.path.write_text(json.dumps(内容 if 内容 is not None else {"ok": True}), encoding="utf-8")

        return wait_for.wait_for_json(
            self.path,
            上限秒=上限秒,
            間隔秒=間隔秒,
            対象名="候補",
            進捗=self.進捗.append,
            時計=self.時計.time,
            待つ=self.時計.sleep,
            確認前=確認前,
        )

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち合わせ-1
    def test_ファイルが現れるまで一定間隔で確認し現れたら内容を返すこと(self):
        結果 = self._待つ(現れる回=3, 内容={"requestId": "X"})
        self.assertTrue(結果.到着)
        self.assertEqual(結果.内容, {"requestId": "X"})
        self.assertEqual(self.時計.待った秒, [5, 5])

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#往復の待ち合わせと打ち切り
    def test_途中まで書かれたファイルは書き込み中とみなして待ち続けること(self):
        回数 = {"n": 0}

        def 確認前():
            回数["n"] += 1
            if 回数["n"] == 1:
                self.path.write_text('{"requestId": ', encoding="utf-8")
            elif 回数["n"] == 2:
                self.path.write_text('{"requestId": "X"}', encoding="utf-8")

        結果 = wait_for.wait_for_json(
            self.path, 上限秒=30, 間隔秒=5, 対象名="候補", 進捗=self.進捗.append,
            時計=self.時計.time, 待つ=self.時計.sleep, 確認前=確認前,
        )
        self.assertTrue(結果.到着)
        self.assertEqual(結果.内容, {"requestId": "X"})

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち合わせ-2、apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち時間の上限-1
    def test_待ち上限を超えたら打ち切りとして返すこと(self):
        結果 = self._待つ(上限秒=12, 間隔秒=5)
        self.assertFalse(結果.到着)
        self.assertTrue(結果.打ち切り)
        self.assertIsNone(結果.内容)
        self.assertGreaterEqual(結果.経過秒, 12)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち合わせ-4
    def test_確認のたびに待っている対象と経過時間が進捗として出ること(self):
        self._待つ(上限秒=12, 間隔秒=5)
        self.assertTrue(self.進捗)
        self.assertTrue(all("候補" in 行 for 行 in self.進捗))
        self.assertTrue(any("秒" in 行 for 行 in self.進捗))

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち時間の上限-2
    def test_上限と間隔を引数で受け取れること(self):
        結果 = self._待つ(上限秒=3, 間隔秒=1)
        self.assertTrue(結果.打ち切り)
        self.assertEqual(self.時計.待った秒, [1, 1, 1])


class 複数の到着待ち(unittest.TestCase):
    """代替案の予定詳細と代替案2の候補のように、2つの待ちを同時に行い、それぞれに上限を適用する。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.a = Path(self._tmp.name, "detail-X.json")
        self.b = Path(self._tmp.name, "candidates-X-a2.json")
        self.時計 = 偽の時計()

    def tearDown(self):
        self._tmp.cleanup()

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち合わせ-5
    def test_片方だけが上限内に届いた場合は届いた側を到着届かなかった側を打ち切りとして返すこと(self):
        回数 = {"n": 0}

        def 確認前():
            回数["n"] += 1
            if 回数["n"] == 2:
                self.a.write_text('{"requestId": "X"}', encoding="utf-8")

        結果 = wait_for.wait_for_all(
            {"予定詳細": (self.a, 10), "代替案2の候補": (self.b, 10)},
            間隔秒=5, 進捗=lambda s: None, 時計=self.時計.time, 待つ=self.時計.sleep, 確認前=確認前,
        )
        self.assertTrue(結果["予定詳細"].到着)
        self.assertTrue(結果["代替案2の候補"].打ち切り)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#往復の待ち時間の上限-2
    def test_待ちごとに別々の上限が適用されること(self):
        結果 = wait_for.wait_for_all(
            {"予定詳細": (self.a, 5), "代替案2の候補": (self.b, 15)},
            間隔秒=5, 進捗=lambda s: None, 時計=self.時計.time, 待つ=self.時計.sleep,
        )
        self.assertTrue(結果["予定詳細"].打ち切り)
        self.assertTrue(結果["代替案2の候補"].打ち切り)
        self.assertLess(結果["予定詳細"].経過秒, 結果["代替案2の候補"].経過秒)

    def test_両方が届けば両方の内容が返ること(self):
        self.a.write_text('{"a": 1}', encoding="utf-8")
        self.b.write_text('{"b": 2}', encoding="utf-8")
        結果 = wait_for.wait_for_all(
            {"予定詳細": (self.a, 5), "代替案2の候補": (self.b, 5)},
            間隔秒=5, 進捗=lambda s: None, 時計=self.時計.time, 待つ=self.時計.sleep,
        )
        self.assertEqual(結果["予定詳細"].内容, {"a": 1})
        self.assertEqual(結果["代替案2の候補"].内容, {"b": 2})
        self.assertEqual(self.時計.待った秒, [])


if __name__ == "__main__":
    unittest.main()
