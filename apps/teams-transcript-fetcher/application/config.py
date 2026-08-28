"""バッチの設定値とパスの解決。

しきい値・上限はいずれも仕様で根拠付きに決められた値なので、既定値をここ1箇所に
集約する。パスは「作業フォルダ」1つから導出し、Power Automateとの受け渡し場所が
個別設定でずれないようにする。

対応する仕様: apps/teams-transcript-fetcher/specs/transcript-auto-fetch/
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

#: 作業フォルダを差し替える環境変数。テストと、OneDriveの同期先名が異なる環境のため。
作業フォルダ環境変数 = "TRANSCRIPT_FETCHER_WORK_DIR"

#: 既定の作業フォルダ。`00_root/auto/` の直下ではなく `transcript/` 配下に置く
#: (直下のファイル作成はTeams投稿用のPower Automateフローが検知するため)。
#: 仕様: requirements.md#実行環境 [6]
既定の作業フォルダ = (
    Path.home()
    / "Library/CloudStorage/OneDrive-Deloitte(O365D)/00_root/auto/transcript"
)

#: 取得済み記録・ロック・ログの置き場。**同期フォルダの外**であることが要件。
#: 仕様: requirements.md#状態管理 [1]
状態フォルダ = Path.home() / "Library/Application Support/teams-transcript-fetcher"

#: バッチの起動間隔。しきい値を「回数 × 間隔」で説明するために設定として持つ。
既定の実行間隔秒 = 300

#: ダウンロードURLとして許可するホストの接尾辞。
#: 台帳やURLファイルの内容は外部から与えられた文字列として扱い、想定外のホストへ
#: アクセスしないための防御(design.md#セキュリティ)。
#: **実際のホストは未確認**(requirements.md#前提・検証項目 #11)。拒否した場合は
#: ホスト名をログに残すので、初回の実機実行で判明する。
既定の許可するホスト接尾辞 = (".sharepoint.com", ".svc.ms")


@dataclass(frozen=True)
class 設定:
    作業フォルダ: Path

    実行間隔秒: int
    処理上限件数: int
    タイムアウト秒: int
    恒久的失敗の上限: int
    進捗なし発行要求の上限: int
    読み取り失敗を記録するしきい値: int
    長期滞留しきい値日: int
    要求滞留しきい値分: int
    url期限しきい値分: int
    許可するホスト接尾辞: tuple[str, ...]
    ログレベル: int

    # --- 同期停滞の監視(specs/sync-stall-recovery/) ---
    停滞判定しきい値分: int
    実行中断とみなす間隔分: int
    復帰後の猶予分: int
    復旧確認しきい値分: int
    再起動の24時間上限: int
    再通知間隔時間: int
    疎通タイムアウト秒: int
    通常終了を待つ秒: int

    @property
    def 台帳フォルダ(self) -> Path:
        return self.作業フォルダ / "ledger"

    @property
    def 要求フォルダ(self) -> Path:
        return self.作業フォルダ / "request"

    @property
    def urlフォルダ(self) -> Path:
        return self.作業フォルダ / "url"

    @property
    def 出力フォルダ(self) -> Path:
        return self.作業フォルダ / "vtt"

    @property
    def 退避フォルダ(self) -> Path:
        return self.作業フォルダ / "invalid"

    @property
    def 記録ファイル(self) -> Path:
        """処理結果の記録。PCの前にいなくても見られるよう同期される側に置く。

        仕様: requirements.md#処理結果の記録 [2]
        """
        return self.作業フォルダ / "_status.md"

    @property
    def ハートビートファイル(self) -> Path:
        """Power Automateが15分間隔で上書きするハートビート。バッチは読むだけ。

        取得バッチが監視しているのと同じ同期経路にあることが検知の前提。
        仕様: sync-stall-recovery/requirements.md#ハートビートの書き込み [2]
        """
        return self.作業フォルダ / "_heartbeat.txt"

    @property
    def 監視通知フォルダ(self) -> Path:
        """監視通知の書き出し先。構築済みのフローが本文をTeamsへ投稿する。

        仕様: sync-stall-recovery/requirements.md#監視通知 [1]
        """
        return self.作業フォルダ.parent / "teamsNotice" / "monitoring"

    @property
    def 状態ファイル(self) -> Path:
        return 状態フォルダ / "state.json"

    @property
    def 監視記録ファイル(self) -> Path:
        """監視記録。**同期フォルダの外**であることが要件
        (停滞の最中でも読み書きできる必要がある)。
        仕様: sync-stall-recovery/requirements.md#記録 [2]
        """
        return 状態フォルダ / "monitoring.json"

    @property
    def ロックファイル(self) -> Path:
        return 状態フォルダ / "fetch.lock"

    @property
    def ログファイル(self) -> Path:
        return 状態フォルダ / "fetch.log"


def load(作業フォルダ: Path | None = None) -> 設定:
    """設定を組み立てる。

    作業フォルダは「引数 → 環境変数 → 既定値」の順で決める。引数を最優先にするのは、
    テストが実物の同期フォルダに触れないようにするため。
    """
    if 作業フォルダ is None:
        環境変数の値 = os.environ.get(作業フォルダ環境変数)
        作業フォルダ = Path(環境変数の値) if 環境変数の値 else 既定の作業フォルダ

    return 設定(
        作業フォルダ=作業フォルダ,
        実行間隔秒=既定の実行間隔秒,
        # 仕様: requirements.md#処理の順序と上限 [2]
        処理上限件数=20,
        # 仕様: design.md#パフォーマンス
        タイムアウト秒=30,
        # 仕様: requirements.md#エラー時の挙動 [5]
        恒久的失敗の上限=3,
        # 仕様: requirements.md#エラー時の挙動 [7] [8](10回 × 5分 = 約50分)
        進捗なし発行要求の上限=10,
        # 仕様: requirements.md#エラー時の挙動 [11](3回 × 5分 = 約15分)
        読み取り失敗を記録するしきい値=3,
        # 仕様: requirements.md#処理結果の記録 [4]
        長期滞留しきい値日=7,
        # 仕様: requirements.md#ダウンロードURLの発行要求 [5]
        要求滞留しきい値分=30,
        # URLの実寿命は未実測(requirements.md#前提・検証項目 #1)。
        # 実測より短い安全側の暫定値を置き、ログの観測結果で調整する。
        url期限しきい値分=30,
        # 仕様: design.md#セキュリティ(アクセス先URLの検証)
        許可するホスト接尾辞=既定の許可するホスト接尾辞,
        # 仕様: design.md#ログ(観測に使う項目がDEBUGで出るため既定をDEBUGにする)
        ログレベル=logging.DEBUG,
        # 仕様: sync-stall-recovery/requirements.md#停滞判定の閾値 [1]
        # (ハートビート3回分の欠落に相当)
        停滞判定しきい値分=45,
        # 仕様: sync-stall-recovery/requirements.md#スリープ復帰直後の誤検知防止 [1]
        # (5分間隔の3サイクル分を超える空白は稼働の連続性が切れた証拠)
        実行中断とみなす間隔分=15,
        # 仕様: sync-stall-recovery/requirements.md#スリープ復帰直後の誤検知防止 [2]
        # (停滞判定の閾値と揃える。短いと復帰直後の判定が素通りになる)
        復帰後の猶予分=45,
        # 仕様: sync-stall-recovery/requirements.md#再起動の回数制限 [4]
        # (同期再開とハートビート2回分の更新を待つのに十分な時間)
        復旧確認しきい値分=30,
        # 仕様: sync-stall-recovery/requirements.md#再起動の回数制限 [3]
        再起動の24時間上限=2,
        # 仕様: sync-stall-recovery/requirements.md#通知の抑止と限界 [1]
        再通知間隔時間=24,
        # 仕様: sync-stall-recovery/design.md#同期停滞の判定(手順5)
        疎通タイムアウト秒=5,
        # 仕様: sync-stall-recovery/design.md#OneDriveの再起動と復旧確認(手順3)
        通常終了を待つ秒=30,
    )
