"""claude -p の起動と生成結果の検証(タスク4・タスク11)のテスト。"""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import claude_runner
import meeting_profile

判定語 = ("デイリー",)

通常の性質 = meeting_profile.見極める("定例会議.vtt", "WEBVTT", 判定語)
デイリーの性質 = meeting_profile.見極める("デイリーMTG.vtt", "WEBVTT", 判定語)


def _整った議事録(除く: str = "", 性質: meeting_profile.会議の性質 = 通常の性質) -> str:
    """必須見出しをすべて含む議事録の例。`除く`に指定した見出しだけ落とす。"""
    見出し一覧 = [h for h in 性質.必須見出し if h != 除く]
    return "\n".join(f"## {h}\n\n- なし\n" for h in 見出し一覧)


class プロンプトの組み立て(unittest.TestCase):
    """構成指示に、承認済みのビジネスルールが漏れなく入ることを検証する。

    claude -p には対話での軌道修正が効かないため、指示から漏れたルールは
    成果物に反映されない。
    """

    def setUp(self):
        self.指示 = claude_runner.構成指示を組み立てる("2026-08-24 定例会議.vtt", 通常の性質)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の記載内容-1
    def test_日本語で書く指示が含まれること(self):
        self.assertIn("日本語", self.指示)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の生成-2
    def test_必須見出し6つがすべて指示に含まれること(self):
        for 見出し in 通常の性質.必須見出し:
            self.assertIn(見出し, self.指示)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#会議種別による構成の切り替え-4
    def test_通常の会議では進捗の見出しを指示しないこと(self):
        self.assertNotIn("進捗", self.指示)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の記載内容-5
    def test_0件でも見出しを省略せず_なし_と書く指示が含まれること(self):
        self.assertIn("なし", self.指示)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の記載内容-3
    def test_会議名と日時のヒントとしてVTTファイル名が含まれること(self):
        self.assertIn("2026-08-24 定例会議.vtt", self.指示)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の記載内容-3
    def test_判別できない項目を不明と書く指示が含まれること(self):
        self.assertIn("不明", self.指示)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の記載内容-2
    def test_担当者を推定できない場合の担当者未定の指示が含まれること(self):
        self.assertIn("担当者未定", self.指示)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の記載内容-4
    def test_参加者一覧を発言者名から書き出す指示が含まれること(self):
        self.assertIn("参加者一覧", self.指示)
        self.assertIn("発言者名", self.指示)


class 要約の分量の指示(unittest.TestCase):
    """要約が長すぎるとTeams投稿で要点が掴めないため、会議の実尺に応じた上限を
    指示に含めることを検証する。上限はバッチでは検証せず、指示だけで守らせる。
    """

    def _指示(self, トランスクリプト: str) -> str:
        性質 = meeting_profile.見極める("定例会議.vtt", トランスクリプト, 判定語)
        return claude_runner.構成指示を組み立てる("定例会議.vtt", 性質)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の記載内容-6
    def test_短い会議では厳しい上限が指示されること(self):
        指示 = self._指示("WEBVTT\n\n00:00:00.000 --> 00:28:13.000\n<v 山田>はい\n")
        self.assertIn("300字", 指示)
        self.assertIn("箇条書き", 指示)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の記載内容-6
    def test_長い会議では緩い上限が指示されること(self):
        指示 = self._指示("WEBVTT\n\n00:00:00.000 --> 01:30:00.000\n<v 山田>はい\n")
        self.assertIn("800字", 指示)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の記載内容-7
    def test_タイムスタンプが無い場合も最も厳しい上限が指示されること(self):
        self.assertIn("300字", self._指示("WEBVTT\n\n<v 山田>はい\n"))


class デイリー系会議の構成指示(unittest.TestCase):
    """定期進捗確認の会議では、進捗を独立した見出しにまとめる指示が入ることを検証する。"""

    def setUp(self):
        self.指示 = claude_runner.構成指示を組み立てる("デイリーMTG.vtt", デイリーの性質)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#会議種別による構成の切り替え-2
    def test_進捗の見出しが指示に含まれること(self):
        self.assertIn("進捗", self.指示)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#会議種別による構成の切り替え-2
    def test_担当者ごとに作業実績と作業予定と課題を書く指示が含まれること(self):
        for 項目 in ("作業実績", "作業予定", "課題"):
            self.assertIn(項目, self.指示)
        self.assertIn("###", self.指示)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#会議種別による構成の切り替え-3
    def test_進捗報告を決定事項とTODOに混ぜない指示が含まれること(self):
        self.assertIn("進捗報告", self.指示)


class 生成結果の検証(unittest.TestCase):
    """claude -p は exit 0 でも失敗していることがあるため、生成物が議事録として
    成立しているか(必須見出しの存在)をバッチ側で検証することを確認する。
    """

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#生成手段claude--pの制約への対処-1
    def test_必須見出しがすべて揃っていれば欠けなしと判定されること(self):
        self.assertEqual(
            claude_runner.欠けている見出し(_整った議事録(), 通常の性質.必須見出し), []
        )

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#生成手段claude--pの制約への対処-1
    def test_見出しが1つでも欠けていれば欠けとして報告されること(self):
        欠け = claude_runner.欠けている見出し(
            _整った議事録(除く="決定事項"), 通常の性質.必須見出し
        )
        self.assertEqual(欠け, ["決定事項"])

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#生成手段claude--pの制約への対処-1
    def test_見出し行でない本文中の語は見出しと数えないこと(self):
        """「決定事項は特にない」のような本文の語で検証をすり抜けさせない。"""
        本文 = _整った議事録(除く="決定事項") + "\n決定事項は特にない\n"
        self.assertEqual(
            claude_runner.欠けている見出し(本文, 通常の性質.必須見出し), ["決定事項"]
        )

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#会議種別による構成の切り替え-5
    def test_通常の会議では進捗が無くても検証に通ること(self):
        """会議種別ごとに検証する見出しを分けないと、全件が検証NGで対象外化する。"""
        self.assertEqual(
            claude_runner.欠けている見出し(_整った議事録(), 通常の性質.必須見出し), []
        )

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#会議種別による構成の切り替え-5
    def test_デイリー系で進捗が欠けていれば検証NGになること(self):
        欠け = claude_runner.欠けている見出し(
            _整った議事録(除く="進捗", 性質=デイリーの性質), デイリーの性質.必須見出し
        )
        self.assertEqual(欠け, ["進捗"])

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#会議種別による構成の切り替え-2
    def test_デイリー系で進捗があれば検証に通ること(self):
        本文 = _整った議事録(性質=デイリーの性質)
        self.assertEqual(claude_runner.欠けている見出し(本文, デイリーの性質.必須見出し), [])


class 生成の実行(unittest.TestCase):
    """claude -p の起動と、3分類(タイムアウト・exit非0・検証NG)の失敗判定を検証する。"""

    def _実行(self, *, 性質=通常の性質, **mockの設定):
        """コマンドの探索結果を固定して実行する。

        探索を固定するのは、テストを動かす環境にclaudeが入っているかどうかで
        結果が変わらないようにするため。
        """
        with mock.patch(
            "claude_runner.claudeコマンドを探す", return_value="/usr/local/bin/claude"
        ), mock.patch("claude_runner.subprocess.run", **mockの設定) as 実行モック:
            結果 = claude_runner.生成する(
                "WEBVTT\n00:00 --> 00:01\n<v 山田>おはようございます",
                "会議A.vtt",
                タイムアウト秒=900,
                性質=性質,
            )
        return 結果, 実行モック

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#議事録の生成
    def test_正常な出力が返れば成功として本文が得られること(self):
        完了 = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=_整った議事録(), stderr=""
        )
        結果, 実行モック = self._実行(return_value=完了)
        self.assertTrue(結果.成功)
        self.assertEqual(結果.本文, _整った議事録().strip())
        # トランスクリプトは引数ではなく標準入力で渡す(引数長の上限を避けるため)
        self.assertIn("山田", 実行モック.call_args.kwargs["input"])
        # 探索で決めた絶対パスで起動する(launchdはPATHを継承しないため)
        self.assertEqual(実行モック.call_args.args[0][0], "/usr/local/bin/claude")

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#議事録の生成
    def test_タイムアウト超過が失敗として分類されること(self):
        結果, _ = self._実行(
            side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=900)
        )
        self.assertFalse(結果.成功)
        self.assertEqual(結果.失敗の分類, "タイムアウト")

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#議事録の生成
    def test_終了コード非0が失敗として分類されること(self):
        完了 = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="err")
        結果, _ = self._実行(return_value=完了)
        self.assertFalse(結果.成功)
        self.assertEqual(結果.失敗の分類, "終了コード非0")

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#生成手段claude--pの制約への対処-1
    def test_exit0でも必須見出しが欠けていれば検証NGとして失敗になること(self):
        完了 = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=_整った議事録(除く="要約"), stderr=""
        )
        結果, _ = self._実行(return_value=完了)
        self.assertFalse(結果.成功)
        self.assertEqual(結果.失敗の分類, "検証NG")

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#会議種別による構成の切り替え-5
    def test_デイリー系では進捗を含む議事録が成功と判定されること(self):
        本文 = _整った議事録(性質=デイリーの性質)
        完了 = subprocess.CompletedProcess(args=[], returncode=0, stdout=本文, stderr="")
        結果, _ = self._実行(return_value=完了, 性質=デイリーの性質)
        self.assertTrue(結果.成功)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#議事録の生成
    def test_claudeコマンドが見つからない場合も失敗として分類されること(self):
        結果, _ = self._実行(side_effect=FileNotFoundError("claude"))
        self.assertFalse(結果.成功)
        self.assertEqual(結果.失敗の分類, "起動失敗")


class claudeコマンドの探索(unittest.TestCase):
    """launchd経由の実行ではログインシェルのPATHを継承しないため、バッチが自分で
    claudeの場所を探せることを検証する。

    ここが効かないと、手元のターミナルでは動くのに定期実行だけが
    「起動失敗」で全件失敗し続ける(実機で発生した)。
    """

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#議事録の生成
    def test_環境変数で指定したコマンドが最優先で使われること(self):
        with mock.patch.dict(
            "os.environ", {claude_runner.コマンド環境変数: "/opt/custom/claude"}
        ):
            self.assertEqual(claude_runner.claudeコマンドを探す(), "/opt/custom/claude")

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#議事録の生成
    def test_PATHにあればその場所が使われること(self):
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch(
            "claude_runner.shutil.which", return_value="/usr/local/bin/claude"
        ):
            self.assertEqual(claude_runner.claudeコマンドを探す(), "/usr/local/bin/claude")

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#議事録の生成
    def test_PATHに無くても既知の場所にあれば見つかること(self):
        """launchdのPATHは最小限のため、実際にはこの経路で見つかる。"""
        with tempfile.TemporaryDirectory() as 一時ディレクトリ:
            偽のコマンド = Path(一時ディレクトリ) / "claude"
            偽のコマンド.write_text("", encoding="utf-8")
            with mock.patch.dict("os.environ", {}, clear=True), mock.patch(
                "claude_runner.shutil.which", return_value=None
            ), mock.patch(
                "claude_runner.既知の候補", return_value=(偽のコマンド,)
            ):
                self.assertEqual(claude_runner.claudeコマンドを探す(), str(偽のコマンド))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#議事録の生成
    def test_どこにも無ければ見つからないと分かること(self):
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch(
            "claude_runner.shutil.which", return_value=None
        ), mock.patch("claude_runner.既知の候補", return_value=()):
            self.assertIsNone(claude_runner.claudeコマンドを探す())

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#生成手段claude--pの制約への対処-1
    def test_コマンドが見つからない場合は起動失敗として分類されること(self):
        with mock.patch("claude_runner.claudeコマンドを探す", return_value=None):
            結果 = claude_runner.生成する(
                "WEBVTT", "会議A.vtt", タイムアウト秒=900, 性質=通常の性質
            )
        self.assertFalse(結果.成功)
        self.assertEqual(結果.失敗の分類, "起動失敗")
        self.assertIn("claude", 結果.詳細)


if __name__ == "__main__":
    unittest.main()
