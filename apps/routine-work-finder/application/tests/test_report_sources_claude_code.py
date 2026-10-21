"""週次レポートが、Claude Code の会話の記録からその週に人が打った依頼文を読む(契約)

作業の要約と自動化案の手がかりにするため、会話の記録から人が打った依頼文だけを選び、冒頭200字・日時・
リポジトリ名を読む。ツールの結果・補助の印・要約・ヘッドレスの会話・作業の終わりの知らせ・ローカルの
コマンドの行は社外へ送る材料に混ぜない。依頼文に貼った認証情報やメールアドレスは伏せ字にしてから使う。
"""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from routine_work_finder.report import sources_claude_code

JST = timezone(timedelta(hours=9))
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "claude_code"
PROJECT = "-Users-example-repo-sample"
SESSION = "11111111-1111-4111-8111-111111111111"
WEEK_START = datetime(2026, 10, 5, 0, 0, tzinfo=JST)
WEEK_END = datetime(2026, 10, 9, 17, 0, tzinfo=JST)
SPEC = "週次の進捗表を更新して、変わったチケットの一覧を作ってください。連絡先は [メール] です。キーは [伏せ字] を使ってください。"


def jst(text):
    return datetime.fromisoformat(text + "+09:00")


def fixture_lines():
    """fixture の会話のファイルの行(上から1番目が [0])"""
    path = FIXTURES / PROJECT / f"{SESSION}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def human_line(content, timestamp="2026-10-06T01:00:00.000Z", **changes):
    """fixture の月曜0時の依頼文(13行目)の形で、本文と日時を差し替えた行"""
    line = fixture_lines()[12]
    line["message"] = {"role": "user", "content": content}
    line["timestamp"] = timestamp
    line.update(changes)
    return line


def without(line, *keys):
    return {key: value for key, value in line.items() if key not in keys}


class ClaudeCodeTestCase(unittest.TestCase):
    def setUp(self):
        base = os.environ.get("TMPDIR") or tempfile.gettempdir()
        self.temporary = tempfile.TemporaryDirectory(dir=base)
        self.folder = Path(self.temporary.name) / "projects"
        self.folder.mkdir()

    def tearDown(self):
        for path in self.folder.rglob("*"):
            path.chmod(0o700)
        self.temporary.cleanup()

    def copy_fixture(self):
        shutil.copytree(FIXTURES / PROJECT, self.folder / PROJECT)

    def write(self, name, lines, project=PROJECT):
        """会話のファイルを1つ作る。lines の要素は辞書(JSON の1行)か文字列(そのまま1行)"""
        path = self.folder / project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        text = "".join((line if isinstance(line, str) else json.dumps(line, ensure_ascii=False)) + "\n" for line in lines)
        path.write_text(text, encoding="utf-8")
        return path

    def read(self, start=WEEK_START, end=WEEK_END):
        return sources_claude_code.read_claude_code(start, end, self.folder)

    def texts(self, result):
        return [request["text"] for request in result.requests]


class ClaudeCodeContractTests(ClaudeCodeTestCase):
    """会話の記録から、その週に人が打った依頼文だけを選ぶ"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3
    def test_人が打った依頼文だけを日時の順にリポジトリ名と日本時間の日時つきで読む(self):
        """ツールの結果・補助の印・要約・ヘッドレス・作業の終わりの知らせ・ローカルのコマンド・添付・題名・
        返答の行と、VS Code の拡張の知らせだけの行は選ばない。画像つきの依頼は文章の要素を改行でつなぐ。
        否定確認: 補助の印の条件を外すと「補助の本文」が入って落ちる。要約の印・ヘッドレスの条件・種類の条件・
        出どころの条件(人の入力だけ)もそれぞれ外すと落ちる"""
        self.copy_fixture()
        result = self.read()
        self.assertEqual(result.failures, [])
        self.assertEqual(result.skipped, {})
        self.assertEqual(
            [(r["source"], r["repo"], r["time"]) for r in result.requests],
            [("claudeCode", "sample", jst("2026-10-05T00:00:00")),
             ("claudeCode", "sample", jst("2026-10-06T10:00:00")),
             ("claudeCode", "sample", jst("2026-10-07T11:30:00")),
             ("claudeCode", "sample", jst("2026-10-07T12:00:00")),
             ("claudeCode", "sample", jst("2026-10-08T11:00:00")),
             ("claudeCode", "sample", jst("2026-10-08T12:00:00"))],
        )
        texts = self.texts(result)
        self.assertEqual(texts[0], "月曜0時の依頼文")
        self.assertTrue(texts[1].startswith(SPEC))
        self.assertEqual(texts[2], "画像を見て直してください。\n2つ目の文です。")
        self.assertEqual(texts[3], "/sample コマンドの引数の本文")
        self.assertEqual(texts[4:], ["開いているファイルの手順を直してください。", "選んだ行を言い換えてください。"])
        self.assertEqual(set(result.requests[0]), {"source", "repo", "text", "time"})

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#社外へ送るもの-1
    def test_依頼文は冒頭200字を取ってからメールアドレスとトークンらしい文字列を伏せる(self):
        """伏せ字で短くなっても取り直さない(200字から メール19字→5字・トークン28字→5字 で163字)。
        否定確認: 伏せ字を外すと落ちる。伏せ字のあとに200字を取ると字数が変わって落ちる"""
        self.copy_fixture()
        text = self.read().requests[1]["text"]
        self.assertTrue(text.startswith(SPEC))
        self.assertNotIn("someone@example.com", text)
        self.assertNotIn("abcd1234EFGH5678ijkl9012MNOP", text)
        self.assertEqual(len(text), 200 - 19 + 5 - 28 + 5)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3
    def test_VS_Codeの拡張が付ける知らせを取り除いて人が打った文だけを依頼文にし知らせだけの行は選ばない(self):
        """開いているファイル・選んだ行の知らせは人が打った文ではなく、ローカルのファイルのパスを含む。
        配列の要素として付く形・文字列の中に入る形のどちらも取り除き、前後の空白と改行を詰める。
        否定確認: 知らせを取り除く処理を外すと知らせの文面とパスが依頼文に入って落ちる。
        取り除いて空になった行を選ぶと空の依頼文が入って落ちる"""
        self.write(f"{SESSION}.jsonl", fixture_lines()[15:18])
        result = self.read()
        self.assertEqual(self.texts(result), ["開いているファイルの手順を直してください。", "選んだ行を言い換えてください。"])
        self.assertEqual(result.skipped, {})
        for text in self.texts(result):
            self.assertNotIn("/Users/example", text)
            self.assertNotIn("ide_", text)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3
    def test_知らせは本文の途中や複数あっても取り除き冒頭200字は取り除いたあとの本文から取る(self):
        """知らせが長いと冒頭200字が知らせで埋まり、人が打った文が1字も残らなくなるのを防ぐ。
        否定確認: 200字を取ってから知らせを取り除くと人が打った文が消えて落ちる。
        最初の知らせだけを取り除くと2つ目の知らせが残って落ちる"""
        notice = ("<ide_opened_file>The user opened the file /Users/example/repo/sample/" + "長い名前" * 60
                  + ".md in the IDE. This may or may not be related to the current task.</ide_opened_file>")
        selection = ("<ide_selection>The user selected the lines 1 to 2 from /Users/example/repo/sample/a.md:\n"
                     "選んだ行\n\nThis may or may not be related to the current task.</ide_selection>")
        self.write(f"{SESSION}.jsonl", [
            human_line([{"type": "text", "text": notice}, {"type": "text", "text": "  前半の文。  "}]),
            human_line(f"後半の前。\n{selection}\n後半の後。\n\n", "2026-10-06T02:00:00.000Z"),
            human_line(f"{notice}{selection}二つの知らせのあと。", "2026-10-06T03:00:00.000Z"),
        ])
        self.assertEqual(self.texts(self.read()), ["前半の文。", "後半の前。\n\n後半の後。", "二つの知らせのあと。"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3
    def test_本文の始まりは知らせを取り除いたあとの本文で見る(self):
        """知らせが先頭に付いていても、スラッシュコマンドの依頼はコマンド名と引数になり、出どころの印が無い
        古い形式のローカルのコマンドの出力は選ばない。
        否定確認: 知らせを取り除く前の本文で始まりを見ると、スラッシュコマンドが本文のまま入り、
        ローカルのコマンドの出力も入って落ちる"""
        notice = {"type": "text", "text": "<ide_opened_file>The user opened the file /Users/example/repo/sample/a.md in the IDE. "
                                          "This may or may not be related to the current task.</ide_opened_file>"}
        slash = "<command-message>sample is running…</command-message>\n<command-name>/sample</command-name>\n<command-args>引数</command-args>"
        self.write(f"{SESSION}.jsonl", [
            human_line([notice, {"type": "text", "text": slash}]),
            without(human_line([notice, {"type": "text", "text": "<local-command-stdout>出力</local-command-stdout>"}],
                               "2026-10-06T02:00:00.000Z"), "origin"),
        ])
        self.assertEqual(self.texts(self.read()), ["/sample 引数"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3
    def test_スラッシュコマンドで打った依頼はコマンド名と引数をつなぎ引数が空ならコマンド名だけにする(self):
        """否定確認: 引数が空のときも空白をつなぐと「/sample 」になって落ちる"""
        slash = fixture_lines()[5]
        empty = json.loads(json.dumps(slash))
        empty["message"]["content"] = "<command-message>sample is running…</command-message>\n<command-name>/sample</command-name>\n<command-args></command-args>"
        empty["timestamp"] = "2026-10-07T04:00:00.000Z"
        self.write(f"{SESSION}.jsonl", [slash, empty])
        self.assertEqual(self.texts(self.read()), ["/sample コマンドの引数の本文", "/sample"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3
    def test_日本時間の月曜0時を含み日曜の最後と金曜17時ちょうどを含まない(self):
        """否定確認: 範囲の終わりを含む比べ方にすると金曜17時ちょうどが入って落ちる"""
        self.write(f"{SESSION}.jsonl", [
            human_line("日曜の最後", "2026-10-04T14:59:59.999Z"),
            human_line("月曜0時", "2026-10-04T15:00:00.000Z"),
            human_line("金曜16時59分", "2026-10-09T07:59:59.999Z"),
            human_line("金曜17時", "2026-10-09T08:00:00.000Z"),
        ])
        result = self.read()
        self.assertEqual(self.texts(result), ["月曜0時", "金曜16時59分"])
        self.assertEqual(result.requests[1]["time"], datetime(2026, 10, 9, 16, 59, 59, 999000, tzinfo=JST))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3
    def test_出どころの印が無い古い形式の行は作業の終わりの知らせとローカルのコマンドの行だけを除く(self):
        """否定確認: 印が無い行の本文の始まりを見ないと4種類の行が入って落ちる。
        印が無い行をすべて除くと普通の依頼文まで消えて落ちる"""
        lines = [without(human_line(content, f"2026-10-06T0{index}:00:00.000Z"), "origin")
                 for index, content in enumerate([
                     "古い形式の依頼文",
                     "<task-notification>\n<result>作業の結果</result>\n</task-notification>",
                     "<local-command-stdout>出力</local-command-stdout>",
                     "<local-command-stderr>エラーの出力</local-command-stderr>",
                     "<command-name>/sample-local</command-name>\n<command-message>sample-local</command-message>\n<command-args></command-args>",
                 ])]
        self.write(f"{SESSION}.jsonl", lines)
        self.assertEqual(self.texts(self.read()), ["古い形式の依頼文"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3
    def test_出どころの印がある行は人の入力の印のものだけを選ぶ(self):
        """否定確認: 印の種類を見ないと作業の終わりの知らせ(本文が普通の文のもの)が入って落ちる"""
        self.write(f"{SESSION}.jsonl", [
            human_line("人の依頼文", origin={"kind": "human"}),
            human_line("知らせの本文", "2026-10-06T02:00:00.000Z", origin={"kind": "task-notification"}),
        ])
        self.assertEqual(self.texts(self.read()), ["人の依頼文"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3
    def test_ツールの結果を持つ行とツールの結果の要素だけの行は選ばない(self):
        """否定確認: ツールの結果の有無を見ないと文字列の本文の行が入って落ちる。
        文章の要素を持たない配列を除かないと空の依頼文が入って落ちる"""
        tool_result = fixture_lines()[2]
        self.write(f"{SESSION}.jsonl", [
            human_line("ツールの結果の本文", toolUseResult={"stdout": "x"}),
            without(tool_result, "toolUseResult") | {"origin": {"kind": "human"}},
            human_line([{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "x"}}],
                       "2026-10-06T03:00:00.000Z"),
        ])
        result = self.read()
        self.assertEqual(result.requests, [])
        self.assertEqual(result.skipped, {})

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3
    def test_サブエージェントの印がある行は選ばない(self):
        """否定確認: サブエージェントの印を見ないと落ちる"""
        self.write(f"{SESSION}.jsonl", [human_line("サブエージェントへの指示文", isSidechain=True)])
        self.assertEqual(self.read().requests, [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3
    def test_サブエージェントの会話のフォルダは読まない(self):
        """否定確認: 会話のフォルダの下を深く探すとサブエージェントの会話が入って落ちる"""
        self.write(f"{SESSION}.jsonl", [human_line("親の依頼文")])
        self.write(f"{SESSION}/subagents/agent-a0000000000000002.jsonl",
                   [human_line("印の無いサブエージェントの行", "2026-10-06T02:00:00.000Z")])
        self.assertEqual(self.texts(self.read()), ["親の依頼文"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3
    def test_更新日時が対象の週の月曜より前の会話のファイルは開かない(self):
        """否定確認: 更新日時を見ないと古いファイルの行が入って落ちる"""
        old = self.write("22222222-2222-4222-8222-222222222222.jsonl", [human_line("古いファイルの依頼文")])
        self.write(f"{SESSION}.jsonl", [human_line("新しいファイルの依頼文", "2026-10-06T02:00:00.000Z")])
        before = (WEEK_START - timedelta(seconds=1)).timestamp()
        os.utime(old, (before, before))
        self.assertEqual(self.texts(self.read()), ["新しいファイルの依頼文"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3
    def test_会話のファイル以外とフォルダの外のファイルは見ない(self):
        self.write(f"{SESSION}.jsonl", [human_line("依頼文")])
        self.write("メモ.txt", ["x"])
        (self.folder / "直下.jsonl").write_text(json.dumps(human_line("直下の行")) + "\n", encoding="utf-8")
        result = self.read()
        self.assertEqual(self.texts(result), ["依頼文"])
        self.assertEqual(result.skipped, {})


class ClaudeCodeFailureTests(ClaudeCodeTestCase):
    """形の違う行や読めないファイルがあっても、残りで作る"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3
    def test_JSONとして読めない行は読み飛ばした数を返して残りの行を読む(self):
        """書き込みの途中で切れた行と、JSON の値が辞書でない行。
        否定確認: 読めない行で例外のまま止めると落ちる"""
        self.write(f"{SESSION}.jsonl", [
            '{"type": "user", "message": {"role": "user", "content": "途中で',
            "[1, 2]",
            human_line("読める依頼文"),
        ])
        result = self.read()
        self.assertEqual(self.texts(result), ["読める依頼文"])
        self.assertEqual(result.skipped, {"badLine": 2})
        self.assertEqual(result.failures, [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3
    def test_本文の中に改行以外の行区切りの文字があっても1行として読む(self):
        """実物の会話のファイルには、本文の中に行区切りの文字(U+2028)がそのまま入った行がある。
        否定確認: 改行以外の行区切りでも行を分けると、その行が読めない行になって落ちる"""
        self.write(f"{SESSION}.jsonl", [human_line("前半 後半")])
        result = self.read()
        self.assertEqual(self.texts(result), ["前半 後半"])
        self.assertEqual(result.skipped, {})

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3
    def test_日時や本文や作業フォルダの形が違う行は読み飛ばした数を返す(self):
        """否定確認: 時差の無い日時を読み飛ばさずに受け入れると落ちる。
        コマンド名の無いスラッシュコマンドの行を本文のまま使うと落ちる"""
        self.write(f"{SESSION}.jsonl", [
            human_line("日時が読めない", "昨日"),
            human_line("時差の無い日時", "2026-10-06T01:00:00.000"),
            without(human_line("日時が無い"), "timestamp"),
            human_line("x") | {"message": "文字列の本文"},
            human_line({"text": "辞書の本文"}),
            without(human_line("作業フォルダが無い"), "cwd"),
            human_line("<command-message>x</command-message>\n<command-args>引数</command-args>"),
            human_line("読める依頼文", "2026-10-06T02:00:00.000Z"),
        ])
        result = self.read()
        self.assertEqual(self.texts(result), ["読める依頼文"])
        self.assertEqual(result.skipped, {"badField": 7})
        self.assertEqual(result.failures, [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3
    def test_1つの会話のファイルが読めなくても残りのファイルで作る(self):
        """否定確認: 1つのファイルの読み取りの失敗で全体を止めると落ちる"""
        self.write(f"{SESSION}.jsonl", [human_line("読める依頼文")])
        broken = self.folder / PROJECT / "33333333-3333-4333-8333-333333333333.jsonl"
        broken.write_bytes(b"\xff\xfe\x80\x81\n")
        locked = self.write("44444444-4444-4444-8444-444444444444.jsonl", [human_line("鍵のかかった依頼文")])
        locked.chmod(0o000)
        result = self.read()
        self.assertEqual(self.texts(result), ["読める依頼文"])
        self.assertEqual(result.skipped, {"unreadable": 2})
        self.assertEqual(result.failures, [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-5
    def test_会話の記録のフォルダが無いときは会話を読めなかった記録として控える(self):
        result = sources_claude_code.read_claude_code(WEEK_START, WEEK_END, self.folder / "無いフォルダ")
        self.assertEqual(result.requests, [])
        self.assertEqual(result.failures, [{"source": "claudeCode", "site": None, "reason": "unreadable"}])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-3、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-5
    def test_会話の記録のフォルダの一覧が取れないときは会話を読めなかった記録として控える(self):
        """否定確認: 一覧の取得の失敗を握りつぶして0件にすると落ちる"""
        self.copy_fixture()
        self.folder.chmod(0o000)
        try:
            result = self.read()
        finally:
            self.folder.chmod(0o700)
        self.assertEqual(result.requests, [])
        self.assertEqual(result.failures, [{"source": "claudeCode", "site": None, "reason": "unreadable"}])


class MaskTests(unittest.TestCase):
    """依頼文に貼った認証情報やメールアドレスを社外へ送らない"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#社外へ送るもの-1
    def test_メールアドレスはトークンより先に伏せる(self):
        """24字以上の英数字の名前のメールアドレスが、名前だけ伏せられてドメインが残らないことを確かめる。
        否定確認: トークンを先に伏せると「[伏せ字]@example.com」になって落ちる"""
        self.assertEqual(sources_claude_code.mask("宛先 abcdefghij1234567890klmn@example.com へ"), "宛先 [メール] へ")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#社外へ送るもの-1
    def test_英字と数字の両方を含む24字以上の続きだけをトークンとして伏せる(self):
        """否定確認: 英字と数字の両方を含む条件を外すと英字だけの長い語が伏せられて落ちる。
        字数の下限を25字にすると24字のトークンが残って落ちる"""
        cases = {
            "a1" * 12: "[伏せ字]",                      # 24字
            "a1" * 11 + "a": "a1" * 11 + "a",           # 23字
            "abcdefghijklmnopqrstuvwxyz": "abcdefghijklmnopqrstuvwxyz",
            "123456789012345678901234": "123456789012345678901234",
            "ab_cd-ef+gh/ij=kl12345678": "[伏せ字]",
            "鍵 sk-ABCDEFGH12345678abcdefgh です": "鍵 [伏せ字] です",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(sources_claude_code.mask(text), expected)


if __name__ == "__main__":
    unittest.main()
