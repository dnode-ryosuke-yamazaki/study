"""launchdのplist定義がPythonの更新で止まらない書き方になっていることのテスト。"""

import plistlib
import re
import unittest
from pathlib import Path

_plistのパス = (
    Path(__file__).resolve().parent.parent
    / "launchd"
    / "com.example.teams-transcript-fetcher.plist"
)

#: 登録時にそのまま使えるPythonの絶対パス。`Versions/Current` は python.org 版の
#: インストーラが最新版へ張り替えるsymlinkなので、Pythonを上げても指し先が残る。
_想定するPython = "/Library/Frameworks/Python.framework/Versions/Current/bin/python3"


class Pythonの指定がバージョンに依存しないこと(unittest.TestCase):
    """plistに書いたPythonのパスが特定のバージョンを指していると、Pythonを上げた
    時点でlaunchdがプロセスを起動できなくなる。

    このときバッチ自身のログにも `StandardErrorPath` のログにも1行も残らず、外から
    は「静かに止まっている」ようにしか見えない。気づく手段が乏しい壊れ方なので、
    テンプレートの側で起こらないようにする。
    """

    def setUp(self):
        self.本文 = _plistのパス.read_text(encoding="utf-8")
        self.定義 = plistlib.loads(_plistのパス.read_bytes())

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#トランスクリプトの取得と保存 [5]
    def test_pythonがバージョン非依存の絶対パスで指定されていること(self):
        self.assertEqual(self.定義["ProgramArguments"][0], _想定するPython)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#トランスクリプトの取得と保存 [5]
    def test_バージョン番号を含むpythonのパスが混入していないこと(self):
        """コメントや他のキーに紛れて `Versions/3.13` のような指定が残らないようにする。"""
        self.assertEqual(re.findall(r"Python\.framework/Versions/\d", self.本文), [])

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#トランスクリプトの取得と保存 [5]
    def test_pythonのパスが登録時の置換を要さないこと(self):
        """置換を要する形にしておくと、登録する人の環境の `which python3` 次第で
        バージョン番号込みのパスが焼き込まれる。置換の対象はホームディレクトリだけにする。
        """
        self.assertNotIn("__PYTHON__", self.本文)


class 起動に必要な定義が揃っていること(unittest.TestCase):
    """Pythonのパスを差し替えたときに、他の定義を巻き込んで壊していないことを確認する。"""

    def setUp(self):
        self.定義 = plistlib.loads(_plistのパス.read_bytes())

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#実行環境 [7]
    def test_5分間隔の定期起動が取りこぼし回収用に残っていること(self):
        """即時起動だけに寄せると、スリープ中に届いたファイルやイベントの
        取りこぼしが回収されない。
        """
        self.assertEqual(self.定義["StartInterval"], 300)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#実行環境 [7]
    def test_台帳とurlの到着で即時起動する定義になっていること(self):
        監視先 = self.定義["WatchPaths"]
        self.assertEqual(len(監視先), 2)
        self.assertTrue(any(p.endswith("/transcript/ledger") for p in 監視先), 監視先)
        self.assertTrue(any(p.endswith("/transcript/url") for p in 監視先), 監視先)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#バッチの起動launchd
    def test_バッチ自身が書くフォルダを監視していないこと(self):
        """`request/`・`invalid/`・`vtt/` はバッチ自身の書き込みで起動が増えるだけで、
        取得を進める契機にならない。
        """
        監視先 = self.定義["WatchPaths"]
        for 除外 in ("/request", "/invalid", "/vtt"):
            self.assertFalse(any(p.endswith(除外) for p in 監視先), 監視先)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#バッチの起動launchd
    def test_監視先のパスが登録時のホームディレクトリ置換を通ること(self):
        """置換前のテンプレートに実パスを焼き込むと、他の環境で存在しない
        フォルダを監視してイベントが飛ばなくなる。
        """
        for パス in self.定義["WatchPaths"]:
            self.assertTrue(パス.startswith("__ホームディレクトリ__/"), パス)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#関連するファイル抜粋
    def test_バッチ本体のスクリプトを起動する定義になっていること(self):
        self.assertTrue(self.定義["ProgramArguments"][1].endswith("fetch_transcripts.py"))
