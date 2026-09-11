"""進行状態の判定(tasks.md 6)のテスト。

依頼の進行状態は専用の状態ファイルではなく、その依頼IDを含む台帳ファイルの有無と中身から導く。
design.mdの状態管理の表を上から順に当てはめ、最初に一致した行を状態にする。順序を守らないと
代替案2の依頼を書いた直後に「依頼済み」へ
戻るといった取り違えが起きるため、その順序を検証する。
"""

import tempfile
import unittest

import config
import ledger
import progress


class 進行状態の判定(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.設定 = config.load(environ={config.台帳ルート環境変数: self._tmp.name})
        self.id = "20260909-101500-ab3f"

    def tearDown(self):
        self._tmp.cleanup()

    def _置く(self, path, 内容=None):
        ledger.write_json(path, 内容 if 内容 is not None else {"requestId": self.id})

    def _判定(self):
        return progress.判定(self.設定, self.id)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#6-進行状態の判定progresspy
    def test_依頼ファイルが1つも無い依頼IDは存在しない依頼として返ること(self):
        状態 = self._判定()
        self.assertEqual(状態.状態, progress.存在しない)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#状態管理
    def test_試行番号1の依頼だけがあれば依頼済みであること(self):
        self._置く(ledger.依頼ファイル(self.設定, self.id, 1))
        状態 = self._判定()
        self.assertEqual(状態.状態, progress.依頼済み)
        self.assertEqual(状態.試行番号, 1)
        self.assertEqual(状態.再試行番号, 0)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#状態管理
    def test_試行番号1の候補があれば候補到着であること(self):
        self._置く(ledger.依頼ファイル(self.設定, self.id, 1))
        self._置く(ledger.候補ファイル(self.設定, self.id, 1))
        self.assertEqual(self._判定().状態, progress.候補到着)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/requirements.md#候補が0件のときの代替案の提示-8
    def test_代替案2の依頼があり候補が届いていなければ代替案の提示中であること(self):
        self._置く(ledger.依頼ファイル(self.設定, self.id, 1))
        self._置く(ledger.候補ファイル(self.設定, self.id, 1))
        self._置く(ledger.依頼ファイル(self.設定, self.id, 2))
        状態 = self._判定()
        self.assertEqual(状態.状態, progress.代替案の提示中)
        self.assertTrue(状態.代替案2の候補を待つ)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#状態管理
    def test_代替案2の候補が届けば代替案の提示済みであること(self):
        self._置く(ledger.依頼ファイル(self.設定, self.id, 1))
        self._置く(ledger.候補ファイル(self.設定, self.id, 1))
        self._置く(ledger.依頼ファイル(self.設定, self.id, 2))
        self._置く(ledger.候補ファイル(self.設定, self.id, 2))
        状態 = self._判定()
        self.assertEqual(状態.状態, progress.代替案の提示済み)
        self.assertTrue(状態.代替案2の依頼あり)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#6-進行状態の判定progresspy
    def test_代替案2の依頼を書いた直後でも依頼済みへ戻らないこと(self):
        self._置く(ledger.依頼ファイル(self.設定, self.id, 1))
        self._置く(ledger.候補ファイル(self.設定, self.id, 1))
        self._置く(ledger.依頼ファイル(self.設定, self.id, 2))
        状態 = self._判定()
        self.assertEqual(状態.状態, progress.代替案の提示中)
        self.assertEqual(状態.試行番号, 2)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#状態管理
    def test_選択結果があれば代替案の台帳が揃っていなくても選択済みであること(self):
        self._置く(ledger.依頼ファイル(self.設定, self.id, 1))
        self._置く(ledger.候補ファイル(self.設定, self.id, 1))
        self._置く(ledger.依頼ファイル(self.設定, self.id, 2))  # 代替案2の候補は届いていない
        self._置く(ledger.選択結果ファイル(self.設定, self.id, 0))
        状態 = self._判定()
        self.assertEqual(状態.状態, progress.選択済み)
        self.assertEqual(状態.再試行番号, 0)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/tasks.md#6-進行状態の判定progresspy
    def test_作成結果に失敗理由が入っていれば作成失敗であり作成済みと取り違えないこと(self):
        self._置く(ledger.依頼ファイル(self.設定, self.id, 1))
        self._置く(ledger.候補ファイル(self.設定, self.id, 1))
        self._置く(ledger.選択結果ファイル(self.設定, self.id, 0))
        self._置く(ledger.作成結果ファイル(self.設定, self.id, 0), {"requestId": self.id, "error": "Forbidden"})
        状態 = self._判定()
        self.assertEqual(状態.状態, progress.作成失敗)
        self.assertEqual(状態.失敗理由, "Forbidden")

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#状態管理
    def test_失敗理由の無い作成結果があれば作成済みであること(self):
        self._置く(ledger.依頼ファイル(self.設定, self.id, 1))
        self._置く(ledger.候補ファイル(self.設定, self.id, 1))
        self._置く(ledger.選択結果ファイル(self.設定, self.id, 0))
        self._置く(ledger.作成結果ファイル(self.設定, self.id, 0), {"requestId": self.id, "error": "", "event": {}})
        self.assertEqual(self._判定().状態, progress.作成済み)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#状態管理
    def test_最後の再試行番号の選択結果と作成結果で判定すること(self):
        self._置く(ledger.依頼ファイル(self.設定, self.id, 1))
        self._置く(ledger.候補ファイル(self.設定, self.id, 1))
        self._置く(ledger.選択結果ファイル(self.設定, self.id, 0))
        self._置く(ledger.作成結果ファイル(self.設定, self.id, 0), {"requestId": self.id, "error": "失敗"})
        self._置く(ledger.選択結果ファイル(self.設定, self.id, 1))
        状態 = self._判定()
        self.assertEqual(状態.状態, progress.選択済み)  # 再試行1の作成結果はまだ無い
        self.assertEqual(状態.再試行番号, 1)
        self._置く(ledger.作成結果ファイル(self.設定, self.id, 1), {"requestId": self.id, "error": ""})
        self.assertEqual(self._判定().状態, progress.作成済み)

    # 仕様: apps/meeting-setup-automation/specs/meeting-scheduling/design.md#エラーハンドリング
    def test_途中まで書かれた作成結果はまだ来ていないものとして選択済みのままであること(self):
        self._置く(ledger.依頼ファイル(self.設定, self.id, 1))
        self._置く(ledger.候補ファイル(self.設定, self.id, 1))
        self._置く(ledger.選択結果ファイル(self.設定, self.id, 0))
        ledger.作成結果ファイル(self.設定, self.id, 0).parent.mkdir(parents=True, exist_ok=True)
        ledger.作成結果ファイル(self.設定, self.id, 0).write_text('{"requestId": ', encoding="utf-8")
        self.assertEqual(self._判定().状態, progress.選択済み)


if __name__ == "__main__":
    unittest.main()
