import os
import unittest

from tests.runner import LAUNCHD_DIR


class 実行係の土台(unittest.TestCase):
    """実行係は Python 標準ライブラリだけで動き、運営者個人の ~/.claude/lib に依存しない。
    study リポジトリのアプリが個人の部品に依存すると、他の環境で動かなくなるため。"""

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#概要
    def test_実行係のパッケージを読み込める(self):
        import digest_runner  # noqa: F401

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#概要
    def test_実行係のどのファイルも個人の共有ライブラリを参照しない(self):
        """否定確認: launchd/ の下のファイルに `.claude/lib` を書いた行を足すと落ちる"""
        scanned = 0
        offenders = []
        for root, _dirs, files in os.walk(LAUNCHD_DIR):
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(root, name)
                scanned += 1
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                if ".claude/lib" in text or "claude_lib" in text:
                    offenders.append(path)
        self.assertGreaterEqual(scanned, 1, "検査対象のファイルが1つも無い")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
