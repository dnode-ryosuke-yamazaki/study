"""OneDrive同期停滞の検知と自動復旧(tasks.md T2〜T10)のテスト。

時刻・プロセス操作・ネットワークはすべて引数で注入し、実プロセス・実ネットワークに
触れない。
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
import state
import sync_monitor


def _時刻(文字列: str) -> datetime:
    return datetime.fromisoformat(文字列).replace(tzinfo=timezone.utc)


基準時刻 = _時刻("2026-08-28 12:00:00")


class 監視記録の読み書き(unittest.TestCase):
    """監視記録(monitoring.json)の永続化を検証する。

    再起動の回数制限と再通知の抑止は、サイクルを越えた記憶が正しく残ることが前提。
    記録が壊れたときに全体を止めないことも要件になっている。
    """

    def setUp(self):
        self.フォルダ = tempfile.TemporaryDirectory()
        self.addCleanup(self.フォルダ.cleanup)
        self.パス = Path(self.フォルダ.name) / "monitoring.json"

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#状態管理
    def test_ファイルが無い場合は空の記録として読めること(self):
        記録 = sync_monitor.読み込む(self.パス)
        self.assertIsNone(記録.前回実行時刻)
        self.assertIsNone(記録.停滞イベント)
        self.assertEqual(記録.再起動履歴, [])
        self.assertEqual(記録.通知済み事象, {})
        self.assertEqual(記録.異常終了の連続回数, 0)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#エラーハンドリング
    def test_壊れたjsonは空の記録として扱い例外にしないこと(self):
        """記録が失われても、上限は24時間2回と安全側のため続行が許容されている。"""
        self.パス.write_text("{ こわれた", encoding="utf-8")
        記録 = sync_monitor.読み込む(self.パス)
        self.assertIsNone(記録.前回実行時刻)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#記録-1
    def test_保存して読み直すと全項目が保たれること(self):
        記録 = sync_monitor.監視記録(
            前回実行時刻=基準時刻,
            復帰時刻=基準時刻 - timedelta(minutes=10),
            停滞イベント=sync_monitor.停滞イベント(
                開始時刻=基準時刻 - timedelta(hours=1),
                再起動時刻=基準時刻 - timedelta(minutes=50),
                復旧失敗判定済み=True,
                再起動要点="ハートビートの鮮度=47分 / OneDriveを再起動(通常終了・直近24時間で1回目)",
                再起動通知済み=False,
            ),
            再起動履歴=[基準時刻 - timedelta(hours=2)],
            通知済み事象={"復旧失敗": 基準時刻 - timedelta(hours=1)},
            異常終了の連続回数=2,
        )
        sync_monitor.保存する(記録, self.パス, 基準時刻)
        読んだ = sync_monitor.読み込む(self.パス)
        self.assertEqual(読んだ.前回実行時刻, 記録.前回実行時刻)
        self.assertEqual(読んだ.復帰時刻, 記録.復帰時刻)
        self.assertEqual(読んだ.停滞イベント.開始時刻, 記録.停滞イベント.開始時刻)
        self.assertEqual(読んだ.停滞イベント.再起動時刻, 記録.停滞イベント.再起動時刻)
        self.assertTrue(読んだ.停滞イベント.復旧失敗判定済み)
        self.assertEqual(読んだ.停滞イベント.再起動要点, 記録.停滞イベント.再起動要点)
        self.assertFalse(読んだ.停滞イベント.再起動通知済み)
        self.assertEqual(読んだ.再起動履歴, 記録.再起動履歴)
        self.assertEqual(読んだ.通知済み事象, 記録.通知済み事象)
        self.assertEqual(読んだ.異常終了の連続回数, 2)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#エラーハンドリング
    def test_再起動通知済みがtrueの場合も保たれること(self):
        記録 = sync_monitor.監視記録(
            停滞イベント=sync_monitor.停滞イベント(
                開始時刻=基準時刻, 再起動時刻=基準時刻, 再起動通知済み=True,
            )
        )
        sync_monitor.保存する(記録, self.パス, 基準時刻)
        読んだ = sync_monitor.読み込む(self.パス)
        self.assertTrue(読んだ.停滞イベント.再起動通知済み)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#状態管理
    def test_旧形式のstall_eventにrestart_notifiedが無くても読めること(self):
        """フィールド追加前に保存された記録を読んだ場合の後方互換性。"""
        中身 = {
            "stall_event": {
                "started_at": 基準時刻.isoformat(),
                "restarted_at": 基準時刻.isoformat(),
                "recovery_failed": False,
            }
        }
        self.パス.write_text(json.dumps(中身), encoding="utf-8")
        読んだ = sync_monitor.読み込む(self.パス)
        self.assertIsNone(読んだ.停滞イベント.再起動要点)
        self.assertFalse(読んだ.停滞イベント.再起動通知済み)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#状態管理
    def test_保存時に24時間より古い再起動履歴が捨てられること(self):
        """回数制限の判定に使うのは直近24時間だけなので、古い履歴は残さない。"""
        記録 = sync_monitor.監視記録(
            再起動履歴=[
                基準時刻 - timedelta(hours=25),
                基準時刻 - timedelta(hours=23),
            ]
        )
        sync_monitor.保存する(記録, self.パス, 基準時刻)
        読んだ = sync_monitor.読み込む(self.パス)
        self.assertEqual(読んだ.再起動履歴, [基準時刻 - timedelta(hours=23)])


class ハートビートの読み取り(unittest.TestCase):
    """ハートビートファイルの解釈を検証する。

    ハートビートの本文は外部由来の文字列として扱い、日時1つだけを受け付ける。
    読めない場合の区別(存在しない・読めない・解釈不能)は、停滞判定を止める
    判断とログの根拠になる。
    """

    def setUp(self):
        self.フォルダ = tempfile.TemporaryDirectory()
        self.addCleanup(self.フォルダ.cleanup)
        self.パス = Path(self.フォルダ.name) / "_heartbeat.txt"

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#バリデーション
    def test_utcのiso形式を読めること(self):
        self.パス.write_text("2026-08-28T12:00:00Z", encoding="utf-8")
        self.assertEqual(sync_monitor.ハートビートを読む(self.パス), 基準時刻)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#バリデーション
    def test_オフセット付きの日時をutcへ正規化して読めること(self):
        self.パス.write_text("2026-08-28T21:00:00+09:00", encoding="utf-8")
        self.assertEqual(sync_monitor.ハートビートを読む(self.パス), 基準時刻)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#バリデーション
    def test_タイムゾーンが無い日時はutcとみなすこと(self):
        self.パス.write_text("2026-08-28T12:00:00", encoding="utf-8")
        self.assertEqual(sync_monitor.ハートビートを読む(self.パス), 基準時刻)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#バリデーション
    def test_前後の空白と改行は無視すること(self):
        self.パス.write_text("  2026-08-28T12:00:00Z\n", encoding="utf-8")
        self.assertEqual(sync_monitor.ハートビートを読む(self.パス), 基準時刻)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#ハートビートの異常値の扱い-1
    def test_ファイルが存在しない場合は存在しないと区別されること(self):
        結果 = sync_monitor.ハートビートを読む(self.パス)
        self.assertIsInstance(結果, sync_monitor.読めないハートビート)
        self.assertEqual(結果.種別, sync_monitor.種別_存在しない)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#ハートビートの異常値の扱い-1
    def test_読み取りが失敗する場合は読めないと区別されること(self):
        self.パス.mkdir()  # ファイルの位置にフォルダがあると読み取り自体が失敗する
        結果 = sync_monitor.ハートビートを読む(self.パス)
        self.assertIsInstance(結果, sync_monitor.読めないハートビート)
        self.assertEqual(結果.種別, sync_monitor.種別_読めない)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#ハートビートの異常値の扱い-1
    def test_日時として解釈できない本文は解釈不能と区別されること(self):
        self.パス.write_text("きのうのひる", encoding="utf-8")
        結果 = sync_monitor.ハートビートを読む(self.パス)
        self.assertIsInstance(結果, sync_monitor.読めないハートビート)
        self.assertEqual(結果.種別, sync_monitor.種別_解釈不能)


class 鮮度の計算(unittest.TestCase):
    """ハートビートの鮮度(記載時刻と現在時刻の差)の計算を検証する。"""

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#同期停滞の検知-1
    def test_記載時刻と現在時刻の差が鮮度になること(self):
        鮮度 = sync_monitor.鮮度を求める(基準時刻 - timedelta(minutes=30), 基準時刻)
        self.assertEqual(鮮度, timedelta(minutes=30))

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#ハートビートの異常値の扱い-3
    def test_未来の記載時刻は鮮度0とみなすこと(self):
        """時計ずれで未来になった場合、停滞ではない側に倒して誤った再起動を防ぐ。"""
        鮮度 = sync_monitor.鮮度を求める(基準時刻 + timedelta(minutes=10), 基準時刻)
        self.assertEqual(鮮度, timedelta(0))


class 実行の中断検知と復帰猶予(unittest.TestCase):
    """スリープ等による実行の中断の検知と、復帰直後の判定スキップを検証する。

    復帰直後はハートビートが古いのが正常であり、猶予なしに判定すると
    スリープ明けのたびに誤って再起動してしまう。
    """

    def setUp(self):
        self.設定 = config.load(作業フォルダ=Path("/tmp/dummy-work"))

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#同期停滞の判定バッチ毎サイクルの冒頭
    def test_前回実行時刻が無い初回は復帰とみなすこと(self):
        記録 = sync_monitor.監視記録()
        self.assertTrue(sync_monitor.中断からの復帰か(記録, 基準時刻, self.設定))
        self.assertEqual(記録.復帰時刻, 基準時刻)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#スリープ復帰直後の誤検知防止-1
    def test_14分の間隔は継続とみなすこと(self):
        記録 = sync_monitor.監視記録(前回実行時刻=基準時刻 - timedelta(minutes=14))
        self.assertFalse(sync_monitor.中断からの復帰か(記録, 基準時刻, self.設定))

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#スリープ復帰直後の誤検知防止-1
    def test_16分の間隔は中断からの復帰とみなすこと(self):
        記録 = sync_monitor.監視記録(前回実行時刻=基準時刻 - timedelta(minutes=16))
        self.assertTrue(sync_monitor.中断からの復帰か(記録, 基準時刻, self.設定))
        self.assertEqual(記録.復帰時刻, 基準時刻)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#スリープ復帰直後の誤検知防止-2
    def test_復帰から44分は猶予中であること(self):
        記録 = sync_monitor.監視記録(復帰時刻=基準時刻 - timedelta(minutes=44))
        self.assertTrue(sync_monitor.復帰猶予中か(記録, 基準時刻, self.設定))

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#スリープ復帰直後の誤検知防止-2
    def test_復帰から46分は猶予が明けていること(self):
        記録 = sync_monitor.監視記録(復帰時刻=基準時刻 - timedelta(minutes=46))
        self.assertFalse(sync_monitor.復帰猶予中か(記録, 基準時刻, self.設定))


class ネットワーク疎通の確認(unittest.TestCase):
    """M365エンドポイントへの疎通確認を検証する。

    ネットワーク断はOneDrive再起動では直らない別の異常であり、
    不通の間は停滞と判定しないことが要件になっている。
    """

    def setUp(self):
        self.設定 = config.load(作業フォルダ=Path("/tmp/dummy-work"))

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#同期停滞の判定バッチ毎サイクルの冒頭
    def test_接続できれば疎通ありと判定すること(self):
        class 接続の記録:
            引数 = None

            def close(self):
                pass

        def 接続する(宛先, timeout):
            接続の記録.引数 = (宛先, timeout)
            return 接続の記録()

        self.assertTrue(sync_monitor.疎通があるか(self.設定, 接続する=接続する))
        # 接続先はコードに固定したホストのみ(design.md#セキュリティ)
        self.assertEqual(
            接続の記録.引数, (("login.microsoftonline.com", 443), 5)
        )

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#停滞判定の閾値-2
    def test_接続の失敗は不通と判定すること(self):
        def 接続する(宛先, timeout):
            raise OSError("接続できない")

        self.assertFalse(sync_monitor.疎通があるか(self.設定, 接続する=接続する))


class _コマンドの記録:
    """OneDrive再起動が実行するコマンドを捕まえ、プロセスの生死を演じる偽物。"""

    def __init__(self, 生きているプロセス: list[str], 終了で消える: bool = True,
                 起動が失敗する: bool = False):
        self.生きているプロセス = list(生きているプロセス)
        self.終了で消える = 終了で消える
        self.起動が失敗する = 起動が失敗する
        self.実行したコマンド: list[list[str]] = []

    def __call__(self, コマンド, **_引数):
        self.実行したコマンド.append(list(コマンド))

        class _結果:
            returncode = 0
            stdout = ""

        結果 = _結果()
        if コマンド[0] == "pgrep":
            if self.生きているプロセス:
                結果.stdout = "\n".join(self.生きているプロセス) + "\n"
            else:
                結果.returncode = 1
        elif コマンド[0] == "kill":
            if "-TERM" in コマンド and self.終了で消える:
                self.生きているプロセス = []
            if "-KILL" in コマンド:
                self.生きているプロセス = []
        elif コマンド[0] == "open":
            if self.起動が失敗する:
                結果.returncode = 1
        return 結果


class onedriveの再起動(unittest.TestCase):
    """OneDrive同期クライアントの再起動手順を検証する。

    通常終了を試みてから強制終了に落とす方式。別プロセスの誤終了を防ぐため
    プロセス名の完全一致で特定し、シェルを介さず引数の配列で実行する。
    """

    def setUp(self):
        self.設定 = config.load(作業フォルダ=Path("/tmp/dummy-work"))
        self.待った秒: list[float] = []

    def _待つ(self, 秒: float):
        self.待った秒.append(秒)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#onedriveの再起動と復旧確認バッチ
    def test_通常終了で消えた場合は強制終了せず起動すること(self):
        実行 = _コマンドの記録(生きているプロセス=["123"], 終了で消える=True)
        結果 = sync_monitor.onedriveを再起動する(self.設定, 実行する=実行, 待つ=self._待つ)
        self.assertTrue(結果.成功)
        コマンド名 = [c[0] for c in 実行.実行したコマンド]
        self.assertNotIn(["kill", "-KILL", "123"], 実行.実行したコマンド)
        self.assertIn("open", コマンド名)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#onedriveの再起動と復旧確認バッチ
    def test_通常終了で消えない場合は強制終了に落とすこと(self):
        実行 = _コマンドの記録(生きているプロセス=["123"], 終了で消える=False)
        結果 = sync_monitor.onedriveを再起動する(self.設定, 実行する=実行, 待つ=self._待つ)
        self.assertTrue(結果.成功)
        self.assertIn(["kill", "-KILL", "123"], 実行.実行したコマンド)
        # 通常終了を待つ時間は設定(30秒)を超えない
        self.assertLessEqual(sum(self.待った秒), self.設定.通常終了を待つ秒)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#onedriveの再起動と復旧確認バッチ
    def test_プロセスが不在なら終了手順を飛ばして起動のみ行うこと(self):
        実行 = _コマンドの記録(生きているプロセス=[])
        結果 = sync_monitor.onedriveを再起動する(self.設定, 実行する=実行, 待つ=self._待つ)
        self.assertTrue(結果.成功)
        コマンド名 = [c[0] for c in 実行.実行したコマンド]
        self.assertNotIn("kill", コマンド名)
        self.assertIn("open", コマンド名)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#onedriveの再起動と復旧確認バッチ
    def test_起動の失敗は失敗として返ること(self):
        """起動失敗は「復旧失敗」の通知事象の材料になるため、握りつぶさない。"""
        実行 = _コマンドの記録(生きているプロセス=[], 起動が失敗する=True)
        結果 = sync_monitor.onedriveを再起動する(self.設定, 実行する=実行, 待つ=self._待つ)
        self.assertFalse(結果.成功)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#セキュリティ
    def test_プロセスの特定が名前の完全一致であること(self):
        実行 = _コマンドの記録(生きているプロセス=[])
        sync_monitor.onedriveを再起動する(self.設定, 実行する=実行, 待つ=self._待つ)
        pgrep = next(c for c in 実行.実行したコマンド if c[0] == "pgrep")
        self.assertIn("-x", pgrep)
        self.assertIn("OneDrive", pgrep)


class 停滞判定とイベント管理(unittest.TestCase):
    """停滞判定から再起動・復旧確認までの中心の流れを検証する。

    誤検知(不要な再起動)と検知漏れ(停滞の放置)の両方を防ぐ分岐が
    仕様の中心のため、主要な分岐を1つずつ固定する。
    """

    def setUp(self):
        self.フォルダ = tempfile.TemporaryDirectory()
        self.addCleanup(self.フォルダ.cleanup)
        self.設定 = config.load(作業フォルダ=Path(self.フォルダ.name) / "transcript")
        self.設定.作業フォルダ.mkdir(parents=True)
        self.再起動の呼び出し = 0
        self.再起動の結果 = sync_monitor.再起動結果(成功=True, 経過="通常終了")
        self.疎通 = True

    def _ハートビートを書く(self, 時刻: datetime):
        self.設定.ハートビートファイル.write_text(時刻.isoformat(), encoding="utf-8")

    def _疎通確認(self) -> bool:
        return self.疎通

    def _再起動する(self) -> sync_monitor.再起動結果:
        self.再起動の呼び出し += 1
        return self.再起動の結果

    def _判定する(self, 記録: sync_monitor.監視記録, 現在時刻: datetime = 基準時刻):
        return sync_monitor.停滞を判定する(
            記録,
            self.設定,
            現在時刻,
            疎通確認=self._疎通確認,
            再起動する=self._再起動する,
        )

    def _稼働中の記録(self, **引数) -> sync_monitor.監視記録:
        """中断や猶予に引っかからない、5分前に実行済みの記録。"""
        return sync_monitor.監視記録(
            前回実行時刻=基準時刻 - timedelta(minutes=5), **引数
        )

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#停滞判定の閾値-1
    def test_鮮度が閾値内なら何も起きないこと(self):
        self._ハートビートを書く(基準時刻 - timedelta(minutes=30))
        記録 = self._稼働中の記録()
        self.assertEqual(self._判定する(記録), [])
        self.assertEqual(self.再起動の呼び出し, 0)
        self.assertIsNone(記録.停滞イベント)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#同期停滞の判定バッチ毎サイクルの冒頭
    def test_鮮度が閾値内へ戻ると停滞イベントが解消すること(self):
        self._ハートビートを書く(基準時刻 - timedelta(minutes=10))
        記録 = self._稼働中の記録(
            停滞イベント=sync_monitor.停滞イベント(開始時刻=基準時刻 - timedelta(hours=1))
        )
        self.assertEqual(self._判定する(記録), [])
        self.assertIsNone(記録.停滞イベント)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#同期停滞の検知-4
    def test_復帰猶予中は鮮度が古くても停滞と判定しないこと(self):
        self._ハートビートを書く(基準時刻 - timedelta(hours=2))
        記録 = self._稼働中の記録(復帰時刻=基準時刻 - timedelta(minutes=10))
        self.assertEqual(self._判定する(記録), [])
        self.assertEqual(self.再起動の呼び出し, 0)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#ハートビートの異常値の扱い-1
    def test_ハートビートが無い場合は停滞と判定しないこと(self):
        記録 = self._稼働中の記録()
        self.assertEqual(self._判定する(記録), [])
        self.assertEqual(self.再起動の呼び出し, 0)
        self.assertIsNone(記録.停滞イベント)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#同期停滞の検知-3
    def test_鮮度超過でもネットワーク不通なら停滞と判定しないこと(self):
        self._ハートビートを書く(基準時刻 - timedelta(hours=2))
        self.疎通 = False
        記録 = self._稼働中の記録()
        self.assertEqual(self._判定する(記録), [])
        self.assertEqual(self.再起動の呼び出し, 0)
        self.assertIsNone(記録.停滞イベント)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#onedriveの自動再起動-1
    def test_停滞と判定したら再起動して即時通知の事象が積まれること(self):
        self._ハートビートを書く(基準時刻 - timedelta(hours=2))
        記録 = self._稼働中の記録()
        事象たち = self._判定する(記録)
        self.assertEqual(self.再起動の呼び出し, 1)
        self.assertEqual(len(事象たち), 1)
        self.assertEqual(事象たち[0].種別, sync_monitor.事象_同期停滞)
        self.assertTrue(事象たち[0].即時)
        self.assertIsNotNone(記録.停滞イベント)
        self.assertEqual(記録.停滞イベント.再起動時刻, 基準時刻)
        self.assertEqual(記録.再起動履歴, [基準時刻])

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#再起動の回数制限-1
    def test_同一イベントでは2回目の再起動を行わないこと(self):
        self._ハートビートを書く(基準時刻 - timedelta(hours=2))
        記録 = self._稼働中の記録(
            停滞イベント=sync_monitor.停滞イベント(
                開始時刻=基準時刻 - timedelta(minutes=20),
                再起動時刻=基準時刻 - timedelta(minutes=15),
            )
        )
        事象たち = self._判定する(記録)
        self.assertEqual(self.再起動の呼び出し, 0)
        # 再起動から30分以内は回復を待つ(通知もまだ出さない)
        self.assertEqual(事象たち, [])

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#再起動の回数制限-4
    def test_再起動から30分を超えて回復しない場合は復旧失敗になること(self):
        self._ハートビートを書く(基準時刻 - timedelta(hours=2))
        記録 = self._稼働中の記録(
            停滞イベント=sync_monitor.停滞イベント(
                開始時刻=基準時刻 - timedelta(minutes=40),
                再起動時刻=基準時刻 - timedelta(minutes=31),
            )
        )
        事象たち = self._判定する(記録)
        self.assertEqual(len(事象たち), 1)
        self.assertEqual(事象たち[0].種別, sync_monitor.事象_復旧失敗)
        self.assertFalse(事象たち[0].即時)
        self.assertTrue(記録.停滞イベント.復旧失敗判定済み)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#再起動の回数制限-3
    def test_直近24時間で2回再起動済みなら再起動せず復旧失敗になること(self):
        self._ハートビートを書く(基準時刻 - timedelta(hours=2))
        記録 = self._稼働中の記録(
            再起動履歴=[
                基準時刻 - timedelta(hours=3),
                基準時刻 - timedelta(hours=1),
            ]
        )
        事象たち = self._判定する(記録)
        self.assertEqual(self.再起動の呼び出し, 0)
        self.assertEqual(len(事象たち), 1)
        self.assertEqual(事象たち[0].種別, sync_monitor.事象_復旧失敗)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#再起動の回数制限-3
    def test_24時間より前の再起動は回数制限に数えないこと(self):
        self._ハートビートを書く(基準時刻 - timedelta(hours=2))
        記録 = self._稼働中の記録(
            再起動履歴=[
                基準時刻 - timedelta(hours=25),
                基準時刻 - timedelta(hours=26),
            ]
        )
        事象たち = self._判定する(記録)
        self.assertEqual(self.再起動の呼び出し, 1)
        self.assertEqual(事象たち[0].種別, sync_monitor.事象_同期停滞)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#onedriveの再起動と復旧確認バッチ
    def test_再起動の実行自体が失敗した場合も復旧失敗になること(self):
        self._ハートビートを書く(基準時刻 - timedelta(hours=2))
        self.再起動の結果 = sync_monitor.再起動結果(成功=False, 経過="起動失敗")
        記録 = self._稼働中の記録()
        事象たち = self._判定する(記録)
        種別たち = [事象.種別 for 事象 in 事象たち]
        self.assertIn(sync_monitor.事象_復旧失敗, 種別たち)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#同期停滞の判定バッチ毎サイクルの冒頭
    def test_判定の結果によらず前回実行時刻が更新されること(self):
        self._ハートビートを書く(基準時刻 - timedelta(minutes=5))
        記録 = self._稼働中の記録()
        self._判定する(記録)
        self.assertEqual(記録.前回実行時刻, 基準時刻)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#エラーハンドリング
    def test_未書き出しの再起動通知は次サイクルでも積まれ続けること(self):
        """前回の書き出しが失敗して再起動通知済みが立っていない場合、
        再起動を繰り返さずに同じ通知だけを積み直す(実機で発生を確認したバグの回帰)。"""
        self._ハートビートを書く(基準時刻 - timedelta(hours=2))
        記録 = self._稼働中の記録(
            停滞イベント=sync_monitor.停滞イベント(
                開始時刻=基準時刻 - timedelta(minutes=20),
                再起動時刻=基準時刻 - timedelta(minutes=15),
                再起動要点="ハートビートの鮮度=47分 / OneDriveを再起動(通常終了・直近24時間で1回目)",
            )
        )
        事象たち = self._判定する(記録)
        self.assertEqual(self.再起動の呼び出し, 0)
        self.assertEqual(len(事象たち), 1)
        self.assertEqual(事象たち[0].種別, sync_monitor.事象_同期停滞)
        self.assertTrue(事象たち[0].即時)
        self.assertEqual(事象たち[0].検知時刻, 基準時刻 - timedelta(minutes=15))

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#エラーハンドリング
    def test_書き出し済みの再起動通知は再度積まれないこと(self):
        self._ハートビートを書く(基準時刻 - timedelta(hours=2))
        記録 = self._稼働中の記録(
            停滞イベント=sync_monitor.停滞イベント(
                開始時刻=基準時刻 - timedelta(minutes=20),
                再起動時刻=基準時刻 - timedelta(minutes=15),
                再起動要点="ハートビートの鮮度=47分 / OneDriveを再起動(通常終了・直近24時間で1回目)",
                再起動通知済み=True,
            )
        )
        事象たち = self._判定する(記録)
        self.assertEqual(事象たち, [])

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#エラーハンドリング
    def test_解消する前に未書き出しの再起動通知を最後に積むこと(self):
        self._ハートビートを書く(基準時刻 - timedelta(minutes=10))
        記録 = self._稼働中の記録(
            停滞イベント=sync_monitor.停滞イベント(
                開始時刻=基準時刻 - timedelta(hours=1),
                再起動時刻=基準時刻 - timedelta(minutes=20),
                再起動要点="ハートビートの鮮度=47分 / OneDriveを再起動(通常終了・直近24時間で1回目)",
            )
        )
        事象たち = self._判定する(記録)
        self.assertEqual(len(事象たち), 1)
        self.assertEqual(事象たち[0].種別, sync_monitor.事象_同期停滞)
        self.assertIsNone(記録.停滞イベント)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#エラーハンドリング
    def test_書き出し済みの再起動通知は解消時に再度積まれないこと(self):
        self._ハートビートを書く(基準時刻 - timedelta(minutes=10))
        記録 = self._稼働中の記録(
            停滞イベント=sync_monitor.停滞イベント(
                開始時刻=基準時刻 - timedelta(hours=1),
                再起動時刻=基準時刻 - timedelta(minutes=20),
                再起動要点="ハートビートの鮮度=47分 / OneDriveを再起動(通常終了・直近24時間で1回目)",
                再起動通知済み=True,
            )
        )
        事象たち = self._判定する(記録)
        self.assertEqual(事象たち, [])
        self.assertIsNone(記録.停滞イベント)


class 通知の書き出し(unittest.TestCase):
    """監視通知ファイルの書き出しを検証する。

    構築済みのPower Automateフローが本文をそのままTeamsへ投稿するため、
    本文だけで事象が分かる必要がある。
    """

    def setUp(self):
        self.フォルダ = tempfile.TemporaryDirectory()
        self.addCleanup(self.フォルダ.cleanup)
        self.通知フォルダ = Path(self.フォルダ.name) / "monitoring"
        self.事象 = sync_monitor.通知事象(
            種別=sync_monitor.事象_同期停滞,
            キー="同期停滞",
            検知時刻=基準時刻,
            要点="ハートビートの鮮度=120分 / 再起動を実行(直近24時間で1回目)",
            即時=True,
        )

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#監視通知-4
    def test_本文に事象の種類と検知時刻と要点が含まれること(self):
        self.assertTrue(sync_monitor.通知を書き出す(self.事象, self.通知フォルダ))
        書かれた = list(self.通知フォルダ.glob("*.md"))
        self.assertEqual(len(書かれた), 1)
        本文 = 書かれた[0].read_text(encoding="utf-8")
        self.assertIn("同期停滞", 本文)
        self.assertIn("鮮度=120分", 本文)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#監視で使うファイルと置き場
    def test_ファイル名が日時と事象種別で構成されること(self):
        sync_monitor.通知を書き出す(self.事象, self.通知フォルダ)
        名前 = list(self.通知フォルダ.glob("*.md"))[0].name
        self.assertRegex(名前, r"^\d{8}-\d{6}_同期停滞\.md$")

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#監視通知の書き出しバッチサイクルの最後
    def test_書き出しに失敗した場合は例外にせず失敗を返すこと(self):
        """失敗した事象は通知済みとして記録せず、次のサイクルで再試行される。"""
        (Path(self.フォルダ.name) / "monitoring").write_text("", encoding="utf-8")
        self.assertFalse(sync_monitor.通知を書き出す(self.事象, self.通知フォルダ))


class 通知の抑止と再通知(unittest.TestCase):
    """同一事象の再通知の抑止・24時間ごとの再通知・再発の扱いを検証する。

    5分間隔で実行されるため、抑止しないと同じ通知が毎サイクル飛び、
    通知を見て気づくという目的自体が損なわれる。
    """

    def setUp(self):
        self.設定 = config.load(作業フォルダ=Path("/tmp/dummy-work"))
        self.書き出した: list[sync_monitor.通知事象] = []
        self.書き出しが成功する = True

    def _書き出す(self, 事象: sync_monitor.通知事象) -> bool:
        if not self.書き出しが成功する:
            return False
        self.書き出した.append(事象)
        return True

    def _継続の事象(self, キー: str = "復旧失敗") -> sync_monitor.通知事象:
        return sync_monitor.通知事象(
            種別=sync_monitor.事象_復旧失敗, キー=キー, 検知時刻=基準時刻, 要点="-"
        )

    def _評価する(self, 継続中, 即時, 記録, 現在時刻=基準時刻):
        sync_monitor.通知を評価する(
            継続中, 即時, 記録, self.設定, 現在時刻, 書き出す=self._書き出す
        )

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#監視通知-2
    def test_初回の継続事象は通知され最終通知時刻が記録されること(self):
        記録 = sync_monitor.監視記録()
        self._評価する([self._継続の事象()], [], 記録)
        self.assertEqual(len(self.書き出した), 1)
        self.assertEqual(記録.通知済み事象, {"復旧失敗": 基準時刻})

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#通知の抑止と限界-1
    def test_継続中の事象は23時間では再通知しないこと(self):
        記録 = sync_monitor.監視記録(
            通知済み事象={"復旧失敗": 基準時刻 - timedelta(hours=23)}
        )
        self._評価する([self._継続の事象()], [], 記録)
        self.assertEqual(self.書き出した, [])

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#通知の抑止と限界-1
    def test_継続中の事象は25時間で再通知されること(self):
        記録 = sync_monitor.監視記録(
            通知済み事象={"復旧失敗": 基準時刻 - timedelta(hours=25)}
        )
        self._評価する([self._継続の事象()], [], 記録)
        self.assertEqual(len(self.書き出した), 1)
        self.assertEqual(記録.通知済み事象["復旧失敗"], 基準時刻)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#監視通知-3
    def test_解消した事象は記録から取り除かれ再発時に新規通知されること(self):
        記録 = sync_monitor.監視記録(
            通知済み事象={"復旧失敗": 基準時刻 - timedelta(hours=1)}
        )
        # 解消(継続中の事象に含まれない)
        self._評価する([], [], 記録)
        self.assertEqual(記録.通知済み事象, {})
        # 再発 → 抑止されず新しい事象として通知される
        self._評価する([self._継続の事象()], [], 記録, 現在時刻=基準時刻 + timedelta(hours=1))
        self.assertEqual(len(self.書き出した), 1)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#監視通知の書き出しバッチサイクルの最後
    def test_書き出しに失敗した事象は通知済みとして記録しないこと(self):
        """記録しないことで、次のサイクルで自然に再試行される。"""
        self.書き出しが成功する = False
        記録 = sync_monitor.監視記録()
        self._評価する([self._継続の事象()], [], 記録)
        self.assertEqual(記録.通知済み事象, {})

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#監視通知の書き出しバッチサイクルの最後
    def test_即時の事象は抑止せず常に書き出されること(self):
        """再起動の通知は同一イベントで1回しか発生しないため、抑止の対象にしない。"""
        即時 = sync_monitor.通知事象(
            種別=sync_monitor.事象_同期停滞, キー="同期停滞", 検知時刻=基準時刻,
            要点="-", 即時=True,
        )
        記録 = sync_monitor.監視記録()
        self._評価する([], [即時], 記録)
        self.assertEqual(len(self.書き出した), 1)
        # 即時の事象は通知済み記録に入れない(継続の管理対象ではない)
        self.assertEqual(記録.通知済み事象, {})

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#エラーハンドリング
    def test_同期停滞の即時通知が成功すると停滞イベントに再起動通知済みが記録されること(self):
        イベント = sync_monitor.停滞イベント(
            開始時刻=基準時刻, 再起動時刻=基準時刻, 再起動要点="-"
        )
        即時 = sync_monitor.通知事象(
            種別=sync_monitor.事象_同期停滞, キー="同期停滞", 検知時刻=基準時刻,
            要点="-", 即時=True,
        )
        記録 = sync_monitor.監視記録(停滞イベント=イベント)
        self._評価する([], [即時], 記録)
        self.assertTrue(記録.停滞イベント.再起動通知済み)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#エラーハンドリング
    def test_同期停滞の即時通知が失敗すると再起動通知済みが立たないこと(self):
        """実機でOneDrive再起動直後の書き込みタイムアウトにより発生を確認したケース。
        次サイクルでも同じ通知を再試行できるよう、失敗時は立てない。"""
        イベント = sync_monitor.停滞イベント(
            開始時刻=基準時刻, 再起動時刻=基準時刻, 再起動要点="-"
        )
        即時 = sync_monitor.通知事象(
            種別=sync_monitor.事象_同期停滞, キー="同期停滞", 検知時刻=基準時刻,
            要点="-", 即時=True,
        )
        記録 = sync_monitor.監視記録(停滞イベント=イベント)
        self.書き出しが成功する = False
        self._評価する([], [即時], 記録)
        self.assertFalse(記録.停滞イベント.再起動通知済み)


class 失敗と警告の連続の検知(unittest.TestCase):
    """既存バッチが数えているカウンタから、継続中の事象を列挙する処理を検証する。

    同一の失敗・警告が3回連続した状態は一過性ではないため、
    通知して人が気づけるようにする。
    """

    def setUp(self):
        self.設定 = config.load(作業フォルダ=Path("/tmp/dummy-work"))

    def _集める(self, 読んだ状態, 監視記録=None, 会議名の索引=None):
        return sync_monitor.継続中の事象を集める(
            読んだ状態,
            会議名の索引 or {},
            監視記録 or sync_monitor.監視記録(),
            self.設定,
            基準時刻,
        )

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#失敗警告の連続の通知-1
    def test_恒久的失敗が上限に達した録画が事象として列挙されること(self):
        状態 = state.状態()
        状態.録画の状態("rec-1").恒久的失敗の回数 = 3
        事象たち = self._集める(状態, 会議名の索引={"rec-1": "定例会議"})
        self.assertEqual(len(事象たち), 1)
        self.assertEqual(事象たち[0].種別, sync_monitor.事象_ダウンロード失敗の連続)
        self.assertEqual(事象たち[0].キー, "ダウンロード失敗の連続:rec-1")
        self.assertIn("定例会議", 事象たち[0].要点)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#失敗警告の連続の通知-1
    def test_しきい値未満のカウンタは事象にならないこと(self):
        状態 = state.状態()
        状態.録画の状態("rec-1").恒久的失敗の回数 = 2
        状態.録画の状態("rec-1").読み取り失敗の回数 = 2
        状態.録画の状態("rec-1").url読み取り失敗の回数 = 2
        self.assertEqual(self._集める(状態), [])

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#失敗警告の連続の通知-1
    def test_台帳の読み取り失敗が3回連続した録画が事象として列挙されること(self):
        状態 = state.状態()
        状態.録画の状態("rec-2").読み取り失敗の回数 = 3
        事象たち = self._集める(状態)
        self.assertEqual(len(事象たち), 1)
        self.assertEqual(事象たち[0].種別, sync_monitor.事象_台帳読み取り失敗の連続)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#失敗警告の連続の通知-1
    def test_urlの読み取り失敗が3回連続した録画が事象として列挙されること(self):
        状態 = state.状態()
        状態.録画の状態("rec-3").url読み取り失敗の回数 = 3
        事象たち = self._集める(状態)
        self.assertEqual(len(事象たち), 1)
        self.assertEqual(事象たち[0].種別, sync_monitor.事象_url読み取り失敗の連続)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#失敗警告の連続の通知-1
    def test_バッチの異常終了が3回連続すると事象として列挙されること(self):
        事象たち = self._集める(
            state.状態(), 監視記録=sync_monitor.監視記録(異常終了の連続回数=3)
        )
        self.assertEqual(len(事象たち), 1)
        self.assertEqual(事象たち[0].種別, sync_monitor.事象_異常終了の連続)

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/design.md#失敗警告の連続の検知バッチ取得サイクルの後
    def test_台帳が消滅して状態が消えた録画は事象に含まれないこと(self):
        """要手動確認が解消(台帳を退避)されれば、事象も自然に消える。"""
        状態 = state.状態()
        状態.録画の状態("rec-1").恒久的失敗の回数 = 3
        状態.録画の状態を消す("rec-1")
        self.assertEqual(self._集める(状態), [])

    # 仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/requirements.md#失敗警告の連続の通知-1
    def test_取得サイクルが状態を読めなかった場合は録画由来の事象を列挙しないこと(self):
        """取得サイクルの失敗時(状態なし)でも、監視側の検知は例外にしない。"""
        事象たち = sync_monitor.継続中の事象を集める(
            None, {}, sync_monitor.監視記録(), self.設定, 基準時刻
        )
        self.assertEqual(事象たち, [])


if __name__ == "__main__":
    unittest.main()
