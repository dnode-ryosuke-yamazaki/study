import os
import unittest

from tests.runner import LAUNCHD_DIR
from tests.runner.support import TempDirTestCase, all_enabled_registry, clone

from digest_runner import registry


class アプリ登録表からの起動対象の引き当て(TempDirTestCase):
    """実行係は起動すべきアプリと判定条件(配信曜日・上限・生成物・起動コマンド)を
    git 管理の1ファイルから引く。登録が無い・まだ有効でないアプリは起動せず失敗にする。"""

    def load(self, data):
        return registry.load(self.write_json("apps.json", data))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-3
    def test_有効なアプリの記事公開を引くと配信曜日と上限と起動コマンドが返る(self):
        reg = self.load(all_enabled_registry())
        got = reg.get("research-digest", "publish")
        self.assertEqual(got["app"], "research-digest")
        self.assertEqual(got["kind"], "publish")
        self.assertEqual(got["weekdays"], [6])
        self.assertEqual(got["maxAttempts"], 4)
        self.assertEqual(got["command"][0], "{node}")
        self.assertEqual(len(got["artifacts"]), 2)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-3
    def test_登録表に無いアプリ名は未登録になる(self):
        """否定確認: アプリ名の有無を確かめる分岐を消すと KeyError になり落ちる"""
        reg = self.load(all_enabled_registry())
        with self.assertRaises(registry.Unregistered):
            reg.get("no-such-digest", "publish")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-3
    def test_記事公開と月次見直し以外の系統は未登録になる(self):
        """否定確認: 系統の登録が無いときの分岐を消すと落ちる"""
        reg = self.load(all_enabled_registry())
        with self.assertRaises(registry.Unregistered):
            reg.get("research-digest", "weekly")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-3
    def test_記事公開が有効になっていないアプリは未登録になる(self):
        """否定確認: enabled を見る条件を外すと落ちる"""
        data = all_enabled_registry()
        data["apps"]["research-digest"]["publish"]["enabled"] = False
        reg = self.load(data)
        with self.assertRaises(registry.Unregistered):
            reg.get("research-digest", "publish")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-3
    def test_月次見直しの日が未定のアプリの月次見直しは未登録になる(self):
        """否定確認: dayOfMonth の null を見る条件を外すと落ちる"""
        data = all_enabled_registry()
        data["apps"]["news-digest"]["review"]["dayOfMonth"] = None
        reg = self.load(data)
        with self.assertRaises(registry.Unregistered):
            reg.get("news-digest", "review")
        self.assertEqual(reg.get("ai-dev-digest", "review")["dayOfMonth"], 1)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-3
    def test_壊れた登録表と必須項目の欠けた登録表は壊れた登録表として扱う(self):
        """否定確認: 必須項目の検査を消すと欠けの側が落ちる"""
        with self.assertRaises(registry.RegistryBroken):
            registry.load(self.write_text("broken.json", "{ not json"))
        with self.assertRaises(registry.RegistryBroken):
            registry.load(self.path("missing.json"))
        data = all_enabled_registry()
        del data["apps"]["trend-digest"]["publish"]["command"]
        with self.assertRaises(registry.RegistryBroken):
            self.load(data)
        data = clone(all_enabled_registry())
        data["apps"]["trend-digest"]["publish"]["weekdays"] = [7]
        with self.assertRaises(registry.RegistryBroken):
            self.load(data)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-1、apps/digest-platform/specs/batch-runner/requirements.md#再実行-1
    def test_本番の登録表は5アプリとも上限4回で記事公開がまだ有効でない(self):
        reg = registry.load(os.path.join(LAUNCHD_DIR, "apps.json"))
        self.assertEqual(
            sorted(reg.apps()),
            ["ai-dev-digest", "future-digest", "news-digest", "research-digest", "trend-digest"],
        )
        raw = reg.raw()["apps"]
        self.assertEqual(raw["research-digest"]["publish"]["weekdays"], [6])
        self.assertEqual(raw["future-digest"]["publish"]["weekdays"], [0])
        for app in ("ai-dev-digest", "news-digest", "trend-digest"):
            self.assertEqual(raw[app]["publish"]["weekdays"], [0, 1, 2, 3, 4, 5, 6])
        for app, entry in raw.items():
            self.assertEqual(entry["publish"]["maxAttempts"], 4, app)
            self.assertIs(entry["publish"]["enabled"], False, app)
            self.assertIsNone(entry["publish"]["editionByWeekday"], app)
            self.assertIsNone(entry["review"]["dayOfMonth"], app)
            self.assertEqual(entry["review"]["maxAttempts"], 1, app)
            with self.assertRaises(registry.Unregistered):
                reg.get(app, "publish")


if __name__ == "__main__":
    unittest.main()
