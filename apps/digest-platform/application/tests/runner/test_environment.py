import os
import unittest

from tests.runner.support import TempDirTestCase

from digest_runner import environment


class バッチを起動する環境の組み立て(TempDirTestCase):
    """launchd は PATH や環境変数を引き継がないため、実行係が node・claude の場所と
    社内プロキシ用の CAバンドルを自分で決めてバッチに渡す。APIキーなど認証に見える値は渡さない。"""

    def exe(self, rel):
        p = self.write_text(rel, "#!/bin/sh\n")
        os.chmod(p, 0o755)
        return p

    def context(self, **over):
        ctx = dict(
            app="research-digest", kind="publish", date="2026-11-07", edition=None, attempt="1", manual=False,
            claude_io_dir="/d/claude-io/publish/2026-11-07", data_dir="/d",
            binaries={"node": "/opt/n/bin/node", "claude": "/opt/c/bin/claude", "python": "/usr/bin/python3"},
            ca_bundle="/h/Library/Application Support/ca-bundle/ca-bundle.pem",
        )
        ctx.update(over)
        return ctx

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-5
    def test_PATHの上から実行ファイルが見つかれば絶対パスで返る(self):
        node = self.exe("bin/node")
        claude = self.exe("bin/claude")
        python = self.exe("bin/python3")
        got = environment.find_binaries({"PATH": self.path("bin")}, candidates={})
        self.assertEqual(got, {"node": node, "claude": claude, "python": python})

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-5
    def test_環境変数で指定された実行ファイルがPATHより優先される(self):
        """否定確認: 環境変数を見る段を消すと落ちる"""
        self.exe("bin/node"); self.exe("bin/claude"); self.exe("bin/python3")
        pinned = self.exe("pinned/node")
        env = {"PATH": self.path("bin"), "DIGEST_NODE_BIN": pinned}
        self.assertEqual(environment.find_binaries(env, candidates={})["node"], pinned)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-5
    def test_どこにも見つからなければ見つからない失敗になる(self):
        self.exe("bin/node"); self.exe("bin/python3")
        with self.assertRaises(environment.BinaryNotFound) as cm:
            environment.find_binaries({"PATH": self.path("bin")}, candidates={})
        self.assertIn("claude", str(cm.exception))

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-5
    def test_PATHに無くても既知の候補の場所にあれば見つかる(self):
        self.exe("bin/node"); self.exe("bin/python3")
        claude = self.exe("home/.local/bin/claude")
        got = environment.find_binaries(
            {"PATH": self.path("bin")}, candidates={"claude": [self.path("nowhere/claude"), claude]})
        self.assertEqual(got["claude"], claude)
        self.assertIn(os.path.join(self.tmp, "home", ".local", "bin", "claude"),
                      environment.default_candidates(self.path("home"))["claude"])

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#Claude の呼び出し規約-1
    def test_認証に見える環境変数はバッチに渡さない(self):
        """否定確認: 名前で落とす処理を消すと落ちる"""
        parent = {
            "PATH": "/usr/bin:/bin", "HOME": "/h", "LANG": "ja_JP.UTF-8",
            "ANTHROPIC_API_KEY": "sk-ant-xxx", "GITHUB_TOKEN": "ghp_xxx", "MY_SECRET": "s",
            "AWS_ACCESS_KEY_ID": "a", "api_key": "k", "DIGEST_HANDOFF_MODULE": "fake_mod",
        }
        built = environment.build(parent, self.context())
        for name in ("ANTHROPIC_API_KEY", "GITHUB_TOKEN", "MY_SECRET", "AWS_ACCESS_KEY_ID", "api_key", "DIGEST_HANDOFF_MODULE"):
            self.assertNotIn(name, built)
        self.assertNotIn("sk-ant-xxx", "\n".join(built.values()))
        self.assertEqual(built["HOME"], "/h")
        self.assertEqual(built["LANG"], "ja_JP.UTF-8")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-5
    def test_バッチへ識別子とパスとCAバンドルを渡しnodeとclaudeの場所をPATHの前に足す(self):
        built = environment.build({"PATH": "/usr/bin:/bin"}, self.context(edition="sci", attempt="manual-142510", manual=True))
        self.assertEqual(built["DIGEST_APP"], "research-digest")
        self.assertEqual(built["DIGEST_KIND"], "publish")
        self.assertEqual(built["DIGEST_DATE"], "2026-11-07")
        self.assertEqual(built["DIGEST_EDITION"], "sci")
        self.assertEqual(built["DIGEST_ATTEMPT"], "manual-142510")
        self.assertEqual(built["DIGEST_MANUAL"], "1")
        self.assertEqual(built["DIGEST_CLAUDE_IO_DIR"], "/d/claude-io/publish/2026-11-07")
        self.assertEqual(built["DIGEST_CLAUDE_BIN"], "/opt/c/bin/claude")
        self.assertEqual(built["DIGEST_DATA_DIR"], "/d")
        self.assertEqual(built["NODE_EXTRA_CA_CERTS"], "/h/Library/Application Support/ca-bundle/ca-bundle.pem")
        self.assertEqual(built["SSL_CERT_FILE"], built["NODE_EXTRA_CA_CERTS"])
        self.assertEqual(built["PATH"].split(":"), ["/opt/n/bin", "/opt/c/bin", "/usr/bin", "/bin"])
        self.assertEqual(environment.build({}, self.context())["DIGEST_EDITION"], "")
        self.assertEqual(environment.build({}, self.context())["DIGEST_MANUAL"], "0")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#実行時刻-5
    def test_バッチには日本時間の時間帯を渡す(self):
        built = environment.build({"TZ": "UTC"}, self.context())
        self.assertEqual(built["TZ"], "Asia/Tokyo")

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-5
    def test_CAバンドルは社内用の束があればそれを使い無ければ標準の束を使う(self):
        """否定確認: 社内用の束の有無の分岐を消すと落ちる"""
        home = self.path("home")
        self.assertEqual(environment.ca_bundle(home), "/etc/ssl/cert.pem")
        bundle = self.write_text("home/Library/Application Support/ca-bundle/ca-bundle.pem", "x")
        self.assertEqual(environment.ca_bundle(home), bundle)

    # 仕様: apps/digest-platform/specs/batch-runner/requirements.md#定時起動-5
    def test_tsxはアプリの土台のnode_modulesから探し無ければ見つからない失敗になる(self):
        with self.assertRaises(environment.BinaryNotFound):
            environment.find_tsx(self.tmp)
        tsx = self.exe("node_modules/.bin/tsx")
        self.assertEqual(environment.find_tsx(self.tmp), tsx)


if __name__ == "__main__":
    unittest.main()
