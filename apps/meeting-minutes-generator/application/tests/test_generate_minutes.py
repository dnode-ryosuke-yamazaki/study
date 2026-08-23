"""未処理VTTの検知(タスク3)とバッチ本体の結合(タスク7)のテスト。"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import claude_runner
import config
import generate_minutes
import state

整った議事録 = "\n".join(
    f"## {見出し}\n\n- なし\n" for 見出し in claude_runner.必須見出し
)


class バッチのテスト基盤(unittest.TestCase):
    """一時フォルダを作業フォルダ・状態フォルダに差し替える共通のsetUp。

    実物のOneDrive同期フォルダに触れるとPower Automateフローが検知して
    誤投稿につながるため、テストは必ず差し替えて動かす。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.addCleanup(self.一時ディレクトリ.cleanup)
        ルート = Path(self.一時ディレクトリ.name)
        self.設定 = config.load(
            作業フォルダ=ルート / "auto", 状態フォルダ=ルート / "app-support"
        )
        self.設定.入力フォルダ.mkdir(parents=True)

    def vttを置く(self, 名前: str, 中身: str = "WEBVTT\n<v 山田>おはようございます") -> Path:
        パス = self.設定.入力フォルダ / 名前
        パス.write_text(中身, encoding="utf-8")
        return パス

    def 空の状態を保存する(self) -> None:
        state.保存する(state.状態(), self.設定.状態ファイル)


class 未処理VTTの検知(バッチのテスト基盤):
    """入力フォルダと状態の突き合わせで、処理すべきVTTだけが選ばれることを検証する。"""

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#新規トランスクリプトの検知-1
    def test_状態に記録のないVTTが未処理として選ばれること(self):
        self.vttを置く("会議A.vtt")
        一覧 = generate_minutes.未処理のvtt一覧(self.設定.入力フォルダ, state.状態())
        self.assertEqual([p.name for p in 一覧], ["会議A.vtt"])

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#新規トランスクリプトの検知-2
    def test_処理済みと対象外のVTTが選ばれないこと(self):
        self.vttを置く("処理済み.vtt")
        self.vttを置く("対象外.vtt")
        self.vttを置く("未処理.vtt")
        状態 = state.状態()
        状態.処理済みにする("処理済み.vtt", datetime.now(timezone.utc))
        状態.対象外にする("対象外.vtt", datetime.now(timezone.utc))
        一覧 = generate_minutes.未処理のvtt一覧(self.設定.入力フォルダ, 状態)
        self.assertEqual([p.name for p in 一覧], ["未処理.vtt"])

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#定期実行と未処理vttの検知
    def test_vtt以外の拡張子のファイルが対象にならないこと(self):
        (self.設定.入力フォルダ / "メモ.txt").write_text("対象外", encoding="utf-8")
        一覧 = generate_minutes.未処理のvtt一覧(self.設定.入力フォルダ, state.状態())
        self.assertEqual(一覧, [])


class 初回実行(バッチのテスト基盤):
    """導入時に溜まっている過去分VTTを議事録化しない(遡及処理はスコープ外)ことを
    検証する。初回に全件生成すると過去会議の議事録が一斉にTeamsへ投稿されてしまう。
    """

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#新規トランスクリプトの検知-3
    def test_状態ファイルが無い初回は既存VTTを処理済み登録だけして生成しないこと(self):
        self.vttを置く("過去の会議.vtt")
        with mock.patch("generate_minutes.claude_runner.生成する") as 生成モック:
            with self.assertLogs(level="INFO"):
                結果 = generate_minutes.実行する(self.設定)
        生成モック.assert_not_called()
        self.assertTrue(結果.初回初期化した)
        読んだ状態 = state.読み込む(self.設定.状態ファイル)
        self.assertTrue(読んだ状態.処理済みか("過去の会議.vtt"))


class 生成から投稿までの通し(バッチのテスト基盤):
    """成功パスで、議事録の保存 → 処理済み記録 → 投稿用ファイルの書き出しが
    この順で揃うことを検証する。
    """

    def setUp(self):
        super().setUp()
        self.空の状態を保存する()

    def _成功する生成(self):
        return mock.patch(
            "generate_minutes.claude_runner.生成する",
            return_value=claude_runner.生成の結果(成功=True, 本文=整った議事録),
        )

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#議事録の保存
    def test_成功すると議事録が保存され処理済みになり投稿用ファイルが書き出されること(self):
        self.vttを置く("会議A.vtt")
        with self._成功する生成(), self.assertLogs(level="INFO"):
            結果 = generate_minutes.実行する(self.設定)
        self.assertEqual(結果.成功件数, 1)
        self.assertTrue((self.設定.議事録フォルダ / "会議A.md").exists())
        読んだ状態 = state.読み込む(self.設定.状態ファイル)
        self.assertTrue(読んだ状態.処理済みか("会議A.vtt"))
        投稿ファイル = list(self.設定.投稿フォルダ.glob("minutes-*.txt"))
        self.assertEqual(len(投稿ファイル), 1)
        self.assertIn("全文", 投稿ファイル[0].read_text(encoding="utf-8"))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#生成手段claude--pの制約への対処-2
    def test_ログにトランスクリプトと議事録の本文が出ないこと(self):
        self.vttを置く("会議A.vtt", 中身="WEBVTT\n<v 山田>ひみつの発言です")
        with self._成功する生成(), self.assertLogs(level="INFO") as ログ:
            generate_minutes.実行する(self.設定)
        全ログ = "\n".join(ログ.output)
        self.assertNotIn("ひみつの発言です", 全ログ)
        self.assertNotIn("なし", 全ログ)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#投稿用ファイルの書き出し
    def test_投稿用ファイルの書き出しに失敗しても処理済みのままになること(self):
        """議事録の二重生成(と再投稿)の防止を投稿の確実さより優先する。"""
        self.vttを置く("会議A.vtt")
        with self._成功する生成(), mock.patch(
            "generate_minutes.writer.投稿用に書き出す", side_effect=OSError("書けない")
        ), self.assertLogs(level="WARNING"):
            結果 = generate_minutes.実行する(self.設定)
        self.assertEqual(結果.投稿失敗件数, 1)
        読んだ状態 = state.読み込む(self.設定.状態ファイル)
        self.assertTrue(読んだ状態.処理済みか("会議A.vtt"))


class 失敗時の挙動(バッチのテスト基盤):
    """生成失敗・読み取り失敗・状態破損のそれぞれで、仕様どおりの側に倒れることを
    検証する。
    """

    def setUp(self):
        super().setUp()
        self.空の状態を保存する()

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の生成-4
    def test_生成に失敗すると再試行回数が増え処理済みにならないこと(self):
        self.vttを置く("会議A.vtt")
        失敗 = claude_runner.生成の結果(成功=False, 失敗の分類="検証NG")
        with mock.patch(
            "generate_minutes.claude_runner.生成する", return_value=失敗
        ), self.assertLogs(level="WARNING"):
            結果 = generate_minutes.実行する(self.設定)
        self.assertEqual(結果.生成失敗件数, 1)
        読んだ状態 = state.読み込む(self.設定.状態ファイル)
        self.assertFalse(読んだ状態.処理済みか("会議A.vtt"))
        self.assertEqual(読んだ状態.再試行回数("会議A.vtt"), 1)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録の生成-5
    def test_再試行が上限に達すると対象外になること(self):
        self.vttを置く("会議A.vtt")
        状態 = state.状態()
        状態.生成失敗を記録する("会議A.vtt")
        状態.生成失敗を記録する("会議A.vtt")
        state.保存する(状態, self.設定.状態ファイル)
        失敗 = claude_runner.生成の結果(成功=False, 失敗の分類="タイムアウト")
        with mock.patch(
            "generate_minutes.claude_runner.生成する", return_value=失敗
        ), self.assertLogs(level="WARNING"):
            結果 = generate_minutes.実行する(self.設定)
        self.assertEqual(結果.対象外化件数, 1)
        読んだ状態 = state.読み込む(self.設定.状態ファイル)
        self.assertTrue(読んだ状態.対象外か("会議A.vtt"))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#新規トランスクリプトの検知-4
    def test_読み取り失敗は状態を変えず次回に持ち越されること(self):
        """OneDrive同期の実体化待ちは一時的なもの。生成失敗と区別し、
        再試行回数を消費しない。
        """
        self.vttを置く("会議A.vtt")
        with mock.patch(
            "generate_minutes.vttを読む", side_effect=OSError("実体化待ち")
        ), self.assertLogs(level="INFO"):
            結果 = generate_minutes.実行する(self.設定)
        self.assertEqual(結果.読めなかった件数, 1)
        読んだ状態 = state.読み込む(self.設定.状態ファイル)
        self.assertFalse(読んだ状態.処理済みか("会議A.vtt"))
        self.assertEqual(読んだ状態.再試行回数("会議A.vtt"), 0)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#エラーハンドリング
    def test_1件の失敗が他のVTTの処理に影響しないこと(self):
        self.vttを置く("失敗する.vtt")
        self.vttを置く("成功する.vtt")

        def 生成(トランスクリプト, vtt名, *, タイムアウト秒):
            if vtt名 == "失敗する.vtt":
                return claude_runner.生成の結果(成功=False, 失敗の分類="検証NG")
            return claude_runner.生成の結果(成功=True, 本文=整った議事録)

        with mock.patch(
            "generate_minutes.claude_runner.生成する", side_effect=生成
        ), self.assertLogs(level="INFO"):
            結果 = generate_minutes.実行する(self.設定)
        self.assertEqual(結果.成功件数, 1)
        self.assertEqual(結果.生成失敗件数, 1)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#エラーハンドリング
    def test_状態ファイルが壊れている場合は初期化せず中断すること(self):
        self.設定.状態ファイル.parent.mkdir(parents=True, exist_ok=True)
        self.設定.状態ファイル.write_text("{壊れている", encoding="utf-8")
        self.vttを置く("会議A.vtt")
        with mock.patch("generate_minutes.claude_runner.生成する") as 生成モック:
            with self.assertLogs(level="ERROR"):
                結果 = generate_minutes.実行する(self.設定)
        self.assertTrue(結果.中断した)
        生成モック.assert_not_called()
        # 壊れた状態ファイルが上書き・初期化されていないこと
        self.assertEqual(
            self.設定.状態ファイル.read_text(encoding="utf-8"), "{壊れている"
        )


if __name__ == "__main__":
    unittest.main()
