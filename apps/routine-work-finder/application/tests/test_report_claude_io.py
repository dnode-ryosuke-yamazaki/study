"""Claude とのやり取りの控え(送った指示文と材料・受け取った応答・成否をデータフォルダに残し、28日で消す)。

自動化案が0件になった週や応答が検査を通らなかった週に、Claude が何を見て何を返したかを人が読めるようにする。
控えは調査用で、書けない・消せないときもレポートの作成は止めない。
実際の claude -p・OneDrive・Teams・記録のデータフォルダには触れず、一時フォルダと偽物で確かめる。
"""

import json
import logging
import os
import shutil
import stat
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from routine_work_finder import paths
from routine_work_finder.report import claude_calls, claude_io, materials
from tests.test_report_run import ReportRunTestCase, jst

SPEC = "apps/routine-work-finder/specs/weekly-automation-report/requirements.md"
EXCHANGE_FILES = ("build.json", "proposals.prompt.md", "proposals-1.materials.json", "proposals-1.response.txt",
                  "proposals-1.result.json", "summaries.prompt.md", "summaries-1.materials.json",
                  "summaries-1.response.txt", "summaries-1.result.json", "exclusions.prompt.md",
                  "exclusions-1.materials.json", "exclusions-1.response.txt", "exclusions-1.result.json")


def proposal_response():
    return {"proposals": [{"title": "進捗表への転記", "candidateIds": ["c1"], "memoIds": [], "effect": "大",
                           "seen": "月曜と火曜の朝", "idea": "JQLで取って貼る", "reuse": ["jira-progress"]}]}


def summary_response():
    return {"items": [{"id": "w1", "summary": "進捗表を更新していた。", "estimated": False,
                       "examples": [{"t": "2026-10-05T09:10:00+09:00", "text": "月曜の朝に進捗表を開いていた"}]}]}


class RecordingHeadless:
    """偽物の呼び出しを包み、標準入力の文字列と返した本文をそのまま控える。呼び出しの前後に差し込める"""

    def __init__(self, inner):
        self.inner = inner
        self.stdin_texts = []
        self.outputs = []
        self.before_call = None

    def __call__(self, prompt, stdin_text, timeout_seconds):
        if self.before_call is not None:
            self.before_call(len(self.stdin_texts) + 1)
        result = self.inner(prompt, stdin_text, timeout_seconds)
        self.stdin_texts.append(stdin_text)
        self.outputs.append(result.output)
        return result


def quiet_logger():
    logger = logging.getLogger("test.claude_io")
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class ExchangeRunTests(ReportRunTestCase):
    """週次レポート係が1週分を作るとき、呼び出しごとの控えが作成回のフォルダに残る"""

    now_text = "2026-10-09T17:05:00"

    def setUp(self):
        super().setUp()
        self.headless.responses = {"proposals": [proposal_response()], "summaries": [summary_response()],
                                   "exclusions": [{"exclusions": []}]}
        self.recorder = RecordingHeadless(self.headless)

    def deps(self):
        built = super().deps()
        built.run_headless = self.recorder
        return built

    def exchange_dirs(self):
        root = self.paths.claude_io
        return sorted(path.name for path in root.iterdir()) if root.exists() else []

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#Claudeとのやり取りの控え-1
    def test_定期の作成で3種類の指示文と呼び出しごとの材料と応答と成否が作成回のフォルダに揃う(self):
        """否定確認: 応答を検査後の値で書くと一字一句一致せず落ちる。控えの文字列を加工すると落ちる"""
        self.write_enough_week("2026-W41")
        self.run_report()
        self.assertEqual(self.exchange_dirs(), ["20261009-170500-2026-W41"])
        folder = self.paths.claude_io / "20261009-170500-2026-W41"
        self.assertEqual(sorted(path.name for path in folder.iterdir()), sorted(EXCHANGE_FILES))
        build = read_json(folder / "build.json")
        self.assertEqual(build, {"week": "2026-W41", "kind": "schedule", "partial": False,
                                 "startedAt": "2026-10-09T17:05:00+09:00", "periodEnd": "2026-10-09T17:00:00+09:00"})
        self.assertEqual((folder / "proposals.prompt.md").read_text(encoding="utf-8"), claude_calls.build_prompt("proposals"))
        for index, name in enumerate(("proposals", "summaries", "exclusions")):
            self.assertEqual((folder / f"{name}-1.materials.json").read_text(encoding="utf-8"), self.recorder.stdin_texts[index])
            self.assertEqual((folder / f"{name}-1.response.txt").read_text(encoding="utf-8"), self.recorder.outputs[index])
            result = read_json(folder / f"{name}-1.result.json")
            self.assertEqual(result["ok"], True)
            self.assertIsNone(result["reason"])
            self.assertIsNone(result["detail"])
            self.assertEqual(result["chars"], len(self.recorder.stdin_texts[index]))
            self.assertEqual(result["finishedAt"], "2026-10-09T17:05:00+09:00")
        self.assertIn("claude-io dir=" + str(folder), "\n".join(self.logs))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#Claudeとのやり取りの控え-1
    def test_作り直しは種類が作り直しになり同じ秒に同じ週の作成回が2つ始まると2つ目に連番が付く(self):
        """否定確認: 同じ名前のフォルダをそのまま使うと1つ目の控えが上書きされ、フォルダが1つしか無くて落ちる"""
        self.write_enough_week("2026-W41")
        self.write_state({"2026-W41": "generated"})
        self.headless.responses["proposals"].append(proposal_response())
        self.headless.responses["summaries"].append(summary_response())
        self.headless.responses["exclusions"].append({"exclusions": []})
        self.request("2026-W41", file_name="20261009-180000-0001.json")
        self.request("2026-W41", file_name="20261009-180000-0002.json")
        self.run_report()
        self.assertEqual(self.exchange_dirs(), ["20261009-170500-2026-W41", "20261009-170500-2026-W41-2"])
        for name in self.exchange_dirs():
            build = read_json(self.paths.claude_io / name / "build.json")
            self.assertEqual((build["kind"], build["partial"]), ("remake", False))
            self.assertTrue((self.paths.claude_io / name / "proposals-1.response.txt").exists())

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#Claudeとのやり取りの控え-3、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#社外へ送るもの-4
    def test_控えはデータフォルダの下に700と600で置かれ材料の項目は増えずレポートと通知とログに中身が入らない(self):
        """否定確認: フォルダの mkdir の mode とファイルの opener の mode を外すと umask 022 で 755・644 になり落ちる。ログに材料の文字列を書くと落ちる"""
        self.write_enough_week("2026-W41")
        memo_text = "目印のメモ 月末の請求書を手で移している"
        self.paths.memos.mkdir(exist_ok=True)
        (self.paths.memos / "2026-10-05.jsonl").write_text(
            json.dumps({"id": "20261005-100000-ab12", "t": "2026-10-05T10:00:00+09:00", "text": memo_text}, ensure_ascii=False) + "\n", encoding="utf-8")
        old_umask = os.umask(0o022)
        try:
            self.run_report()
        finally:
            os.umask(old_umask)
        folder = self.paths.claude_io / "20261009-170500-2026-W41"
        self.assertEqual(folder.parent.parent, self.paths.root)
        self.assertEqual(stat.S_IMODE(self.paths.claude_io.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
        for path in folder.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path.name)
        automation = read_json(folder / "proposals-1.materials.json")
        self.assertEqual(sorted(automation), ["candidates", "memos", "reusable", "week"])
        self.assertIn(memo_text, (folder / "proposals-1.materials.json").read_text(encoding="utf-8"))
        joined_logs = "\n".join(self.logs)
        self.assertNotIn(memo_text, joined_logs)
        self.assertNotIn('"candidates"', joined_logs)
        self.assertNotIn(memo_text, "\n".join(self.bodies))
        self.assertNotIn('"overlappingRecords"', self.local_html("2026-W41"))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#Claudeとのやり取りの控え-5
    def test_控えのフォルダを作れなくても呼び出しは行われレポートは作られログに警告だけが出る(self):
        """否定確認: 書けないときの例外を握りつぶさないと作成が止まり result=generated にならず落ちる"""
        self.write_enough_week("2026-W41")
        self.paths.claude_io.write_text("これはフォルダではない", encoding="utf-8")
        self.run_report()
        self.assertEqual(self.results(), {"2026-W41": "generated"})
        self.assertEqual(self.recorder.inner.names(), ["proposals", "summaries", "exclusions"])
        joined_logs = "\n".join(self.logs)
        self.assertIn("WARNING:routine_work_finder.report:claude-io", joined_logs)
        self.assertNotIn("ERROR", joined_logs)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#Claudeとのやり取りの控え-5
    def test_ファイルを書けなくても呼び出しは行われレポートは作られる(self):
        """否定確認: 書き込みの OSError を拾わないと落ちる"""
        self.write_enough_week("2026-W41")
        with mock.patch.object(claude_io, "_write_file", side_effect=OSError(13, "Permission denied")):
            self.run_report()
        self.assertEqual(self.results(), {"2026-W41": "generated"})
        self.assertEqual(self.recorder.inner.names(), ["proposals", "summaries", "exclusions"])
        self.assertIn("WARNING:routine_work_finder.report:claude-io write failed file=build.json errno=13", self.logs)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#Claudeとのやり取りの控え-6
    def test_控えのフォルダが無くても作られ作成の途中で消されると残りは警告になり次の作成回で作り直す(self):
        """否定確認: 消されたあとの書き込みで例外を出すと2回目の作成が始まらず落ちる"""
        self.write_enough_week("2026-W41")
        self.assertFalse(self.paths.claude_io.exists())

        def remove_after_first_call(call_number):
            if call_number == 2:
                shutil.rmtree(self.paths.claude_io)

        self.recorder.before_call = remove_after_first_call
        self.run_report()
        self.assertEqual(self.results(), {"2026-W41": "generated"})
        self.assertFalse((self.paths.claude_io / "20261009-170500-2026-W41" / "summaries-1.response.txt").exists())
        self.assertTrue(any("claude-io write failed" in line for line in self.logs))
        self.recorder.before_call = None
        self.headless.responses = {"proposals": [proposal_response()], "summaries": [summary_response()],
                                   "exclusions": [{"exclusions": []}]}
        self.clock = jst("2026-10-09T17:06:00")
        self.request("2026-W41")
        self.run_report()
        self.assertTrue((self.paths.claude_io / "20261009-170600-2026-W41" / "summaries-1.response.txt").exists())

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#Claudeとのやり取りの控え-4
    def test_起動のたびに28日を過ぎた作成回を消して数をログに書く(self):
        """否定確認: 起動時の削除の呼び出しを外すと古い作成回が残って落ちる"""
        self.paths.claude_io.mkdir(mode=0o700)
        (self.paths.claude_io / "20260910-170000-2026-W37").mkdir()
        (self.paths.claude_io / "20260911-170000-2026-W37").mkdir()
        self.write_state({"2026-W41": "generated"})
        self.run_report()
        self.assertEqual(self.exchange_dirs(), ["20260911-170000-2026-W37"])
        self.assertIn("INFO:routine_work_finder.report:claude-io purged=1 failed=0", self.logs)


class ExchangeWriteTests(unittest.TestCase):
    """呼び出しの成否ごとに、材料・応答・結果のどれが残るか"""

    def setUp(self):
        base = os.environ.get("TMPDIR") or tempfile.gettempdir()
        self.temporary = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.temporary.name) / "claude-io"
        self.clock = jst("2026-10-09T17:05:00")
        self.store = claude_io.ExchangeStore.open(self.root, "2026-W41", "schedule", False, jst("2026-10-09T17:00:00"),
                                                  lambda: self.clock, quiet_logger())
        self.folder = self.root / "20261009-170500-2026-W41"

    def tearDown(self):
        self.temporary.cleanup()

    def call(self, headless, name="proposals"):
        payload = {"week": "2026-W41", "candidates": [], "memos": [], "reusable": []}
        return claude_calls.call_with_retries(name, "指示文", payload, lambda parsed: parsed, headless, quiet_logger(),
                                              store=self.store)

    def names(self):
        return sorted(path.name for path in self.folder.iterdir())

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#Claudeとのやり取りの控え-2
    def test_時間切れと起動の失敗と終了コード非0の呼び出しは材料と結果だけが残り結果に分類と詳細が入る(self):
        """否定確認: 失敗の呼び出しで response.txt を空で書くと落ちる。detail を書かないと落ちる"""
        failures = [SimpleNamespace(success=False, output="", failure_category="タイムアウト", detail="600秒"),
                    SimpleNamespace(success=False, output="", failure_category="起動失敗", detail="claude が無い"),
                    SimpleNamespace(success=False, output="", failure_category="終了コード非0", detail="exit=1")]
        value = self.call(lambda prompt, stdin_text, timeout: failures.pop(0))
        self.assertIsNone(value)
        self.assertEqual(self.names(), ["build.json", "proposals-1.materials.json", "proposals-1.result.json",
                                        "proposals-2.materials.json", "proposals-2.result.json",
                                        "proposals-3.materials.json", "proposals-3.result.json", "proposals.prompt.md"])
        results = [read_json(self.folder / f"proposals-{attempt}.result.json") for attempt in (1, 2, 3)]
        self.assertEqual([(r["ok"], r["reason"], r["detail"]) for r in results],
                         [(False, "timeout", "600秒"), (False, "launch", "claude が無い"), (False, "exitCode", "exit=1")])
        self.assertEqual((self.folder / "proposals-2.materials.json").read_text(encoding="utf-8"),
                         materials.serialize({"week": "2026-W41", "candidates": [], "memos": [], "reusable": []}))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#Claudeとのやり取りの控え-2
    def test_検査で落ちた呼び出しは検査前の本文が残り理由が形の違いになり呼び直しは2番で残る(self):
        """否定確認: 検査で落ちたときに response.txt を消すと落ちる。呼び直しを同じ番号で上書きすると落ちる"""
        outputs = ['前置き {"proposals": "形が違う"} 後置き', '{"proposals": []}']

        def headless(prompt, stdin_text, timeout):
            return SimpleNamespace(success=True, output=outputs.pop(0), failure_category="", detail="")

        def validate(parsed):
            if not isinstance(parsed["proposals"], list):
                raise claude_calls.ResponseError("invalidShape", "proposals が一覧ではない")
            return parsed

        payload = {"week": "2026-W41", "candidates": [], "memos": [], "reusable": []}
        value = claude_calls.call_with_retries("proposals", "指示文", payload, validate, headless, quiet_logger(),
                                               store=self.store)
        self.assertEqual(value, {"proposals": []})
        self.assertEqual((self.folder / "proposals-1.response.txt").read_text(encoding="utf-8"),
                         '前置き {"proposals": "形が違う"} 後置き')
        first = read_json(self.folder / "proposals-1.result.json")
        self.assertEqual((first["ok"], first["reason"], first["detail"]), (False, "invalidShape", "proposals が一覧ではない"))
        self.assertEqual((self.folder / "proposals-2.response.txt").read_text(encoding="utf-8"), '{"proposals": []}')
        self.assertEqual(read_json(self.folder / "proposals-2.result.json")["ok"], True)
        self.assertEqual((self.folder / "proposals.prompt.md").read_text(encoding="utf-8"), "指示文")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#Claudeとのやり取りの控え-2
    def test_呼び出しの途中で止まっても材料は残っている(self):
        """否定確認: 材料を呼び出しのあとに書くと、止まった呼び出しの材料が無くて落ちる"""

        def crash(prompt, stdin_text, timeout):
            raise RuntimeError("呼び出しの途中で止まった")

        with self.assertRaises(RuntimeError):
            self.call(crash)
        self.assertEqual(self.names(), ["build.json", "proposals-1.materials.json", "proposals.prompt.md"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#Claudeとのやり取りの控え-1
    def test_控えを渡さない呼び出しは何も書かずに動く(self):
        """否定確認: 控えが無いときに書こうとすると AttributeError で落ちる"""
        value = claude_calls.call_with_retries(
            "proposals", "指示文", {"week": "2026-W41"}, lambda parsed: parsed,
            lambda prompt, stdin_text, timeout: SimpleNamespace(success=True, output="{}", failure_category="", detail=""),
            quiet_logger())
        self.assertEqual(value, {})
        self.assertEqual(self.names(), ["build.json"])


class PurgeTests(unittest.TestCase):
    """28日を過ぎた作成回の削除"""

    def setUp(self):
        base = os.environ.get("TMPDIR") or tempfile.gettempdir()
        self.temporary = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.temporary.name) / "claude-io"
        self.root.mkdir(mode=0o700)
        self.now = jst("2026-10-09T17:05:00")
        self.logger = logging.getLogger("test.claude_io.purge")

    def tearDown(self):
        for path in [self.root, *self.root.rglob("*")]:
            if path.exists():
                os.chmod(path, stat.S_IRWXU)
        self.temporary.cleanup()

    def folder(self, days_ago, suffix=""):
        day = (self.now - timedelta(days=days_ago)).strftime("%Y%m%d")
        path = self.root / f"{day}-170000-2026-W37{suffix}"
        path.mkdir()
        (path / "build.json").write_text("{}", encoding="utf-8")
        return path

    def remaining(self):
        return sorted(path.name for path in self.root.iterdir())

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#Claudeとのやり取りの控え-4
    def test_28日前の作成回は残り29日前は連番付きも消え形に合わない名前とファイルとリンクは消さない(self):
        """否定確認: 不等号を >= にすると28日前が消えて落ちる。連番を形に含めないと -2 が残って落ちる"""
        keep = self.folder(28)
        self.folder(29)
        self.folder(29, "-2")
        odd = self.root / "memo-20260801"
        odd.mkdir()
        (self.root / "20260801-170000-2026-W31.txt").write_text("file", encoding="utf-8")
        target = self.root / "target"
        target.mkdir()
        (self.root / "20260801-170000-2026-W31").symlink_to(target, target_is_directory=True)
        with self.assertLogs("test.claude_io.purge", level="INFO") as captured:
            purged, failed = claude_io.purge_old(self.root, self.now, self.logger)
        self.assertEqual((purged, failed), (2, 0))
        self.assertEqual(self.remaining(), ["20260801-170000-2026-W31", "20260801-170000-2026-W31.txt",
                                            keep.name, "memo-20260801", "target"])
        self.assertTrue(target.exists())
        self.assertIn("INFO:test.claude_io.purge:claude-io purged=2 failed=0", captured.output)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#Claudeとのやり取りの控え-4
    def test_消せない作成回は警告を書いて数え次の起動で消える(self):
        """否定確認: 削除の例外を拾わないと起動が止まって落ちる"""
        stuck = self.folder(40)
        os.chmod(stuck, 0o500)
        with self.assertLogs("test.claude_io.purge", level="INFO") as captured:
            self.assertEqual(claude_io.purge_old(self.root, self.now, self.logger), (0, 1))
        self.assertTrue(any("WARNING:test.claude_io.purge:claude-io purge failed dir=" + stuck.name in line
                            for line in captured.output))
        self.assertIn("INFO:test.claude_io.purge:claude-io purged=0 failed=1", captured.output)
        os.chmod(stuck, 0o700)
        self.assertEqual(claude_io.purge_old(self.root, self.now, self.logger), (1, 0))
        self.assertEqual(self.remaining(), [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#Claudeとのやり取りの控え-6
    def test_控えのフォルダが無いときは何も消さずに数だけ書く(self):
        """否定確認: フォルダが無いときに iterdir すると落ちる"""
        shutil.rmtree(self.root)
        self.assertEqual(claude_io.purge_old(self.root, self.now, self.logger), (0, 0))
        self.assertFalse(self.root.exists())


if __name__ == "__main__":
    unittest.main()
