"""取得済み記録の読み書き(T8)と二重起動の防止(T9)のテスト。"""

import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import state


class 空の状態(unittest.TestCase):
    """記録がまだ無い状態から始められることを検証する。

    初回実行や、記録を消して作り直した直後にここで例外を投げると、
    バッチが一度も動けなくなる。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.状態ファイル = Path(self.一時ディレクトリ.name) / "state.json"
        self.addCleanup(self.一時ディレクトリ.cleanup)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#状態管理
    def test_ファイルが無い場合に空の記録が返ること(self):
        読んだ状態 = state.読み込む(self.状態ファイル)
        self.assertEqual(読んだ状態.取得済み, {})
        self.assertEqual(読んだ状態.録画, {})

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#状態管理
    def test_記録ファイルが壊れていても処理を中断せず空として扱われること(self):
        """記録は「速さとエラー回数の保持」のためのもので、唯一の真実の源ではない。
        壊れていても出力先の同名チェックが二重取得を防ぐため、止まる必要がない。
        """
        self.状態ファイル.write_text("{壊れている", encoding="utf-8")
        with self.assertLogs(level="WARNING"):
            読んだ状態 = state.読み込む(self.状態ファイル)
        self.assertEqual(読んだ状態.取得済み, {})


class 取得済みトランスクリプトの記録(unittest.TestCase):
    """どのトランスクリプトを保存し終えたかを記録し、読み直せることを検証する。

    識別はトランスクリプト単位で行う(1つの録画に複数存在しうるため)。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.状態ファイル = Path(self.一時ディレクトリ.name) / "state.json"
        self.addCleanup(self.一時ディレクトリ.cleanup)
        self.日時 = datetime(2026, 8, 19, 10, 35, tzinfo=timezone.utc)

    def 保存して読み直す(self, 対象: state.状態) -> state.状態:
        state.保存する(対象, self.状態ファイル)
        return state.読み込む(self.状態ファイル)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#状態管理-3
    def test_トランスクリプトの識別子が録画の識別子と並び順から組み立てられること(self):
        self.assertNotEqual(
            state.トランスクリプトの識別子("01ABCDEF", 0),
            state.トランスクリプトの識別子("01ABCDEF", 1),
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#状態管理-2
    def test_取得済みの識別子と取得日時を保存して読み直せること(self):
        対象 = state.状態()
        識別子 = state.トランスクリプトの識別子("01ABCDEF", 0)
        対象.取得済みにする(識別子, self.日時)
        読み直した = self.保存して読み直す(対象)
        self.assertTrue(読み直した.取得済みか(識別子))
        self.assertEqual(読み直した.取得済み[識別子], self.日時)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#状態管理-2
    def test_記録していない識別子は取得済みでないこと(self):
        self.assertFalse(state.状態().取得済みか("01ABCDEF#0"))


class 録画ごとに持つ状態(unittest.TestCase):
    """打ち切り判定に使うカウンタや履歴が、録画ごとに保存・復元できることを検証する。

    どれもサイクルを越えて持たないと打ち切りが機能しない(毎回0に戻ると
    永久に上限へ達しない)。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.状態ファイル = Path(self.一時ディレクトリ.name) / "state.json"
        self.addCleanup(self.一時ディレクトリ.cleanup)

    def 保存して読み直す(self, 対象: state.状態) -> state.状態:
        state.保存する(対象, self.状態ファイル)
        return state.読み込む(self.状態ファイル)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-5
    def test_恒久的失敗の累積回数を加算して読み直せること(self):
        対象 = state.状態()
        対象.録画の状態("01ABCDEF").恒久的失敗の回数 += 1
        対象.録画の状態("01ABCDEF").恒久的失敗の回数 += 1
        self.assertEqual(self.保存して読み直す(対象).録画の状態("01ABCDEF").恒久的失敗の回数, 2)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-7
    def test_進捗のない発行要求の連続回数を加算して読み直せること(self):
        """器と読み書きはフェーズ1で用意する。加算と上限判定の発火はフェーズ2。"""
        対象 = state.状態()
        対象.録画の状態("01ABCDEF").進捗なし発行要求の回数 += 1
        self.assertEqual(
            self.保存して読み直す(対象).録画の状態("01ABCDEF").進捗なし発行要求の回数, 1
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-7
    def test_進捗のない発行要求の連続回数を0に戻して読み直せること(self):
        対象 = state.状態()
        対象.録画の状態("01ABCDEF").進捗なし発行要求の回数 = 5
        対象 = self.保存して読み直す(対象)
        対象.録画の状態("01ABCDEF").進捗なし発行要求の回数 = 0
        self.assertEqual(
            self.保存して読み直す(対象).録画の状態("01ABCDEF").進捗なし発行要求の回数, 0
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-11
    def test_台帳の読み取り失敗の連続回数を加算して読み直せること(self):
        対象 = state.状態()
        対象.録画の状態("01ABCDEF").読み取り失敗の回数 += 1
        対象.録画の状態("01ABCDEF").読み取り失敗の回数 += 1
        self.assertEqual(
            self.保存して読み直す(対象).録画の状態("01ABCDEF").読み取り失敗の回数, 2
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-11
    def test_台帳の読み取り失敗の連続回数を0に戻して読み直せること(self):
        """一度読めれば連続は途切れる。ここが戻らないと実体化待ちの累積で記録が出る。"""
        対象 = state.状態()
        対象.録画の状態("01ABCDEF").読み取り失敗の回数 = 3
        対象 = self.保存して読み直す(対象)
        対象.録画の状態("01ABCDEF").読み取り失敗の回数 = 0
        self.assertEqual(
            self.保存して読み直す(対象).録画の状態("01ABCDEF").読み取り失敗の回数, 0
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-13
    def test_urlファイルの読み取り失敗の連続回数を加算して読み直せること(self):
        対象 = state.状態()
        対象.録画の状態("01ABCDEF").url読み取り失敗の回数 += 1
        対象.録画の状態("01ABCDEF").url読み取り失敗の回数 += 1
        self.assertEqual(
            self.保存して読み直す(対象).録画の状態("01ABCDEF").url読み取り失敗の回数, 2
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#エラー時の挙動-13
    def test_urlファイルの読み取り失敗の連続回数を0に戻して読み直せること(self):
        """一度読めれば連続は途切れる。ここが戻らないと実体化待ちの累積で記録が出る。"""
        対象 = state.状態()
        対象.録画の状態("01ABCDEF").url読み取り失敗の回数 = 3
        対象 = self.保存して読み直す(対象)
        対象.録画の状態("01ABCDEF").url読み取り失敗の回数 = 0
        self.assertEqual(
            self.保存して読み直す(対象).録画の状態("01ABCDEF").url読み取り失敗の回数, 0
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#エラーハンドリング
    def test_恒久的失敗と判定した発行時刻を追加して読み直せること(self):
        対象 = state.状態()
        時刻 = datetime(2026, 8, 19, 10, 31, 12, 345000, tzinfo=timezone.utc)
        対象.録画の状態("01ABCDEF").死んだ発行時刻に加える(時刻)
        self.assertTrue(
            self.保存して読み直す(対象).録画の状態("01ABCDEF").発行時刻は死んでいるか(時刻)
        )

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#エラーハンドリング
    def test_発行時刻を2つ以上追加しても既存の値が保持されること(self):
        """単一値だと、台帳のURLと再発行されたURLの両方が死んだときに
        前者が上書きで失われ、同じ死んだURLへアクセスし続けてしまう。
        """
        対象 = state.状態()
        一つ目 = datetime(2026, 8, 19, 10, 31, tzinfo=timezone.utc)
        二つ目 = datetime(2026, 8, 19, 10, 41, tzinfo=timezone.utc)
        対象.録画の状態("01ABCDEF").死んだ発行時刻に加える(一つ目)
        対象.録画の状態("01ABCDEF").死んだ発行時刻に加える(二つ目)
        読み直した = self.保存して読み直す(対象).録画の状態("01ABCDEF")
        self.assertTrue(読み直した.発行時刻は死んでいるか(一つ目))
        self.assertTrue(読み直した.発行時刻は死んでいるか(二つ目))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#エラーハンドリング
    def test_記録していない発行時刻は死んでいないと判定されること(self):
        時刻 = datetime(2026, 8, 19, 10, 31, tzinfo=timezone.utc)
        self.assertFalse(state.状態().録画の状態("01ABCDEF").発行時刻は死んでいるか(時刻))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#トランスクリプトの列挙-5
    def test_観測した既知件数の最大値を保存して読み直せること(self):
        対象 = state.状態()
        対象.録画の状態("01ABCDEF").既知件数の最大値 = 2
        self.assertEqual(self.保存して読み直す(対象).録画の状態("01ABCDEF").既知件数の最大値, 2)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#処理結果の記録-4
    def test_台帳を最初に観測した日時を保存して読み直せること(self):
        対象 = state.状態()
        観測日時 = datetime(2026, 8, 19, 10, 32, tzinfo=timezone.utc)
        対象.録画の状態("01ABCDEF").初回観測 = 観測日時
        self.assertEqual(self.保存して読み直す(対象).録画の状態("01ABCDEF").初回観測, 観測日時)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/requirements.md#処理結果の記録-3
    def test_記録ファイルへ追記済みの失敗種別を保存して読み直せること(self):
        """同じ失敗を5分ごとに追記し続けないための抑止に使う。"""
        対象 = state.状態()
        対象.録画の状態("01ABCDEF").記録済みにする("expired")
        読み直した = self.保存して読み直す(対象).録画の状態("01ABCDEF")
        self.assertTrue(読み直した.記録済みか("expired"))
        self.assertFalse(読み直した.記録済みか("manual"))


class 状態ファイルに書かないもの(unittest.TestCase):
    """ダウンロードURLが状態ファイルに残らないことを検証する。

    ダウンロードURLは実質ベアラトークンであり、そのURLを知れば会議音声由来の
    内容を第三者が取得できる。死んだURLの同定には発行時刻だけを使う。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.状態ファイル = Path(self.一時ディレクトリ.name) / "state.json"
        self.addCleanup(self.一時ディレクトリ.cleanup)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#セキュリティ
    def test_状態ファイルにurlが含まれないこと(self):
        対象 = state.状態()
        対象.取得済みにする(
            state.トランスクリプトの識別子("01ABCDEF", 0),
            datetime(2026, 8, 19, 10, 35, tzinfo=timezone.utc),
        )
        対象.録画の状態("01ABCDEF").死んだ発行時刻に加える(
            datetime(2026, 8, 19, 10, 31, tzinfo=timezone.utc)
        )
        state.保存する(対象, self.状態ファイル)
        書かれた内容 = self.状態ファイル.read_text(encoding="utf-8")
        self.assertNotIn("http", 書かれた内容)


class 台帳が消えた録画の掃除(unittest.TestCase):
    """台帳が無くなった録画に紐づく状態が片付けられることを検証する。

    死んだ発行時刻の集合は際限なく増えうるため、台帳の消滅を機に落とす。
    ただし取得済みの記録は重複保存を防ぐ用途なので残す。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.状態ファイル = Path(self.一時ディレクトリ.name) / "state.json"
        self.addCleanup(self.一時ディレクトリ.cleanup)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#状態管理
    def test_録画に紐づく状態が削除されること(self):
        対象 = state.状態()
        録画 = 対象.録画の状態("01ABCDEF")
        録画.恒久的失敗の回数 = 2
        録画.進捗なし発行要求の回数 = 3
        録画.既知件数の最大値 = 2
        録画.初回観測 = datetime(2026, 8, 19, tzinfo=timezone.utc)
        録画.記録済みにする("expired")
        録画.死んだ発行時刻に加える(datetime(2026, 8, 19, 10, 31, tzinfo=timezone.utc))

        対象.録画の状態を消す("01ABCDEF")

        新しい状態 = 対象.録画の状態("01ABCDEF")
        self.assertEqual(新しい状態.恒久的失敗の回数, 0)
        self.assertEqual(新しい状態.進捗なし発行要求の回数, 0)
        self.assertEqual(新しい状態.既知件数の最大値, 0)
        self.assertIsNone(新しい状態.初回観測)
        self.assertFalse(新しい状態.記録済みか("expired"))

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#状態管理
    def test_取得済みの記録は削除されないこと(self):
        対象 = state.状態()
        識別子 = state.トランスクリプトの識別子("01ABCDEF", 0)
        対象.取得済みにする(識別子, datetime(2026, 8, 19, 10, 35, tzinfo=timezone.utc))
        対象.録画の状態("01ABCDEF").恒久的失敗の回数 = 1

        対象.録画の状態を消す("01ABCDEF")

        self.assertTrue(対象.取得済みか(識別子))


class 状態の保存が壊れないこと(unittest.TestCase):
    """保存が途中で失敗しても、既存の記録が壊れないことを検証する。

    記録が壊れると取得済み判定が失われ、すでに保存したトランスクリプトを
    取り直そうとする(出力先の同名チェックで止まるが、無駄な通信が出る)。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.状態ファイル = Path(self.一時ディレクトリ.name) / "state.json"
        self.addCleanup(self.一時ディレクトリ.cleanup)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#エラーハンドリング
    def test_保存に失敗しても既存の記録が残ること(self):
        対象 = state.状態()
        対象.取得済みにする("01ABCDEF#0", datetime(2026, 8, 19, tzinfo=timezone.utc))
        state.保存する(対象, self.状態ファイル)
        保存できた内容 = self.状態ファイル.read_bytes()

        対象.取得済みにする("01ZZZZZZ#0", datetime(2026, 8, 20, tzinfo=timezone.utc))
        with mock.patch("json.dumps", side_effect=RuntimeError("書き込み失敗")):
            with self.assertRaises(RuntimeError):
                state.保存する(対象, self.状態ファイル)

        self.assertEqual(self.状態ファイル.read_bytes(), 保存できた内容)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#エラーハンドリング
    def test_保存後に一時ファイルが残らないこと(self):
        state.保存する(state.状態(), self.状態ファイル)
        残ったファイル = [パス.name for パス in self.状態ファイル.parent.iterdir()]
        self.assertEqual(残ったファイル, [self.状態ファイル.name])

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#状態管理
    def test_保存先の親フォルダが無ければ作られること(self):
        深いパス = Path(self.一時ディレクトリ.name) / "まだ無い" / "state.json"
        state.保存する(state.状態(), 深いパス)
        self.assertTrue(深いパス.exists())


class 二重起動の防止(unittest.TestCase):
    """同時に2つの実行が走らないことを検証する。

    前回の実行が長引いて次の起動時刻に達したとき、両方が状態を書くと
    取得済み記録が壊れる。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.ロックファイル = Path(self.一時ディレクトリ.name) / "fetch.lock"
        self.addCleanup(self.一時ディレクトリ.cleanup)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#エラーハンドリング
    def test_ロックが取得できること(self):
        with state.ロック(self.ロックファイル):
            self.assertTrue(self.ロックファイル.exists())

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#エラーハンドリング
    def test_処理の終了時にロックが解放されること(self):
        with state.ロック(self.ロックファイル):
            pass
        self.assertFalse(self.ロックファイル.exists())

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#エラーハンドリング
    def test_例外で抜けてもロックが解放されること(self):
        with self.assertRaises(RuntimeError):
            with state.ロック(self.ロックファイル):
                raise RuntimeError("処理中の失敗")
        self.assertFalse(self.ロックファイル.exists())

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#エラーハンドリング
    def test_ロック中に再度取得しようとすると取得できないこと(self):
        with state.ロック(self.ロックファイル):
            with self.assertRaises(state.先行実行が動作中):
                with state.ロック(self.ロックファイル):
                    pass

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#エラーハンドリング
    def test_異常終了で残ったロックが一定時間経過後に無効として扱われること(self):
        """プロセスが落ちてロックファイルだけ残ると、以降ずっと起動できなくなる。
        古いロックは奪って処理を続ける。
        """
        self.ロックファイル.write_text("99999", encoding="utf-8")
        古い時刻 = time.time() - timedelta(hours=1).total_seconds()
        import os

        os.utime(self.ロックファイル, (古い時刻, 古い時刻))

        with state.ロック(self.ロックファイル, 無効とみなす秒=60):
            self.assertTrue(self.ロックファイル.exists())

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#エラーハンドリング
    def test_しきい値内の新しいロックは奪わないこと(self):
        """境界値。新しいロックまで奪うと二重起動の防止が機能しない。"""
        self.ロックファイル.write_text("99999", encoding="utf-8")
        with self.assertRaises(state.先行実行が動作中):
            with state.ロック(self.ロックファイル, 無効とみなす秒=3600):
                pass


class 状態ファイルの項目名(unittest.TestCase):
    """保存形式が想定どおりであることを検証する。

    人が中を覗いて状況を判断することがあるため、項目名を固定しておく。
    """

    def setUp(self):
        self.一時ディレクトリ = tempfile.TemporaryDirectory()
        self.状態ファイル = Path(self.一時ディレクトリ.name) / "state.json"
        self.addCleanup(self.一時ディレクトリ.cleanup)

    # 仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/design.md#状態管理
    def test_取得済みと録画ごとの状態が分かれて保存されること(self):
        対象 = state.状態()
        対象.取得済みにする("01ABCDEF#0", datetime(2026, 8, 19, tzinfo=timezone.utc))
        対象.録画の状態("01ABCDEF").恒久的失敗の回数 = 1
        state.保存する(対象, self.状態ファイル)
        中身 = json.loads(self.状態ファイル.read_text(encoding="utf-8"))
        self.assertIn("01ABCDEF#0", 中身["fetched"])
        self.assertEqual(中身["recordings"]["01ABCDEF"]["permanent_failures"], 1)


if __name__ == "__main__":
    unittest.main()
