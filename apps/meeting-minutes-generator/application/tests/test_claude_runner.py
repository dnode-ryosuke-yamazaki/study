"""claude -p の起動と生成結果の検証(タスク4)のテスト。"""

import subprocess
import unittest
from unittest import mock

import claude_runner


def _整った議事録(除く: str = "") -> str:
    """必須見出しをすべて含む議事録の例。`除く`に指定した見出しだけ落とす。"""
    見出し一覧 = [h for h in claude_runner.必須見出し if h != 除く]
    return "\n".join(f"## {h}\n\n- なし\n" for h in 見出し一覧)


class プロンプトの組み立て(unittest.TestCase):
    """構成指示に、承認済みのビジネスルールが漏れなく入ることを検証する。

    claude -p には対話での軌道修正が効かないため、指示から漏れたルールは
    成果物に反映されない。
    """

    def setUp(self):
        self.指示 = claude_runner.構成指示を組み立てる("2026-08-24 定例会議.vtt")

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の記載内容-1
    def test_日本語で書く指示が含まれること(self):
        self.assertIn("日本語", self.指示)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の生成-2
    def test_必須見出し6つがすべて指示に含まれること(self):
        for 見出し in claude_runner.必須見出し:
            self.assertIn(見出し, self.指示)

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


class 生成結果の検証(unittest.TestCase):
    """claude -p は exit 0 でも失敗していることがあるため、生成物が議事録として
    成立しているか(必須見出しの存在)をバッチ側で検証することを確認する。
    """

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#生成手段claude--pの制約への対処-1
    def test_必須見出しがすべて揃っていれば欠けなしと判定されること(self):
        self.assertEqual(claude_runner.欠けている見出し(_整った議事録()), [])

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#生成手段claude--pの制約への対処-1
    def test_見出しが1つでも欠けていれば欠けとして報告されること(self):
        欠け = claude_runner.欠けている見出し(_整った議事録(除く="決定事項"))
        self.assertEqual(欠け, ["決定事項"])

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#生成手段claude--pの制約への対処-1
    def test_見出し行でない本文中の語は見出しと数えないこと(self):
        """「決定事項は特にない」のような本文の語で検証をすり抜けさせない。"""
        本文 = _整った議事録(除く="決定事項") + "\n決定事項は特にない\n"
        self.assertEqual(claude_runner.欠けている見出し(本文), ["決定事項"])


class 生成の実行(unittest.TestCase):
    """claude -p の起動と、3分類(タイムアウト・exit非0・検証NG)の失敗判定を検証する。"""

    def _実行(self, **mockの設定):
        with mock.patch("claude_runner.subprocess.run", **mockの設定) as 実行モック:
            結果 = claude_runner.生成する(
                "WEBVTT\n00:00 --> 00:01\n<v 山田>おはようございます",
                "会議A.vtt",
                タイムアウト秒=900,
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

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#議事録の生成
    def test_claudeコマンドが見つからない場合も失敗として分類されること(self):
        結果, _ = self._実行(side_effect=FileNotFoundError("claude"))
        self.assertFalse(結果.成功)
        self.assertEqual(結果.失敗の分類, "起動失敗")


if __name__ == "__main__":
    unittest.main()
