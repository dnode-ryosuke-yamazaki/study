"""バッチの設定値とパスの解決。

しきい値・タイムアウトはいずれも仕様承認で確定した値なので、ここ1箇所に集約する。
入出力のパスは「作業フォルダ」1つから導出し、上流(teams-transcript-fetcher)や
Power Automateフローとの受け渡し場所が個別設定でずれないようにする。

対応する仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

#: 作業フォルダを差し替える環境変数。テストと、OneDriveの同期先名が異なる環境のため。
作業フォルダ環境変数 = "MINUTES_GENERATOR_WORK_DIR"

#: 状態フォルダを差し替える環境変数。テスト・手元実行が実物の状態ファイルを汚すと、
#: 実運用の初回判定(初回=既存VTTを生成しない)が壊れるため。
状態フォルダ環境変数 = "MINUTES_GENERATOR_STATE_DIR"

#: 既定の作業フォルダ。`00_root/auto/` を指し、直下にはファイルを置かない
#: (直下のファイル作成は既存のTeams投稿用Power Automateフローが検知するため)。
#: 仕様: requirements.md#OneDriveフォルダの使い方 [1]
既定の作業フォルダ = Path.home() / "Library/CloudStorage/OneDrive-Deloitte(O365D)/00_root/auto"

#: 状態ファイル・ロック・ログの既定の置き場。**同期フォルダの外**に置く
#: (同期フォルダに置くとOneDriveが競合ファイルを作り状態が二重化するため。
#: teams-transcript-fetcherと同じ方針)。仕様: design.md#状態管理
既定の状態フォルダ = Path.home() / "Library/Application Support/meeting-minutes-generator"


@dataclass(frozen=True)
class 設定:
    作業フォルダ: Path
    状態フォルダ: Path

    実行間隔秒: int
    生成タイムアウト秒: int
    再試行上限: int
    ロックを無効とみなす秒: int
    ログレベル: int

    @property
    def 入力フォルダ(self) -> Path:
        """上流のteams-transcript-fetcherがWEBVTTを蓄積するフォルダ。

        仕様: requirements.md#新規トランスクリプトの検知 [1]
        """
        return self.作業フォルダ / "transcript/vtt"

    @property
    def 議事録フォルダ(self) -> Path:
        """生成した議事録Markdownの保存先。仕様: requirements.md#議事録の生成 [3]"""
        return self.作業フォルダ / "minutes"

    @property
    def 投稿フォルダ(self) -> Path:
        """Teams投稿用ファイルの書き出し先。ここへのファイル作成を本機能用に新設する
        Power Automateフローが検知して投稿する。仕様: requirements.md#Teamsへの共有 [1]
        """
        return self.作業フォルダ / "minutesNotice"

    @property
    def 状態ファイル(self) -> Path:
        return self.状態フォルダ / "state.json"

    @property
    def ロックファイル(self) -> Path:
        return self.状態フォルダ / "minutes.lock"

    @property
    def ログファイル(self) -> Path:
        return self.状態フォルダ / "minutes.log"


def load(作業フォルダ: Path | None = None, 状態フォルダ: Path | None = None) -> 設定:
    """設定を組み立てる。

    作業フォルダ・状態フォルダは「引数 → 環境変数 → 既定値」の順で決める。引数を
    最優先にするのは、テストが実物の同期フォルダ・状態ファイルに触れないようにするため。
    """
    if 作業フォルダ is None:
        環境変数の値 = os.environ.get(作業フォルダ環境変数)
        作業フォルダ = Path(環境変数の値) if 環境変数の値 else 既定の作業フォルダ
    if 状態フォルダ is None:
        状態の環境変数の値 = os.environ.get(状態フォルダ環境変数)
        状態フォルダ = Path(状態の環境変数の値) if 状態の環境変数の値 else 既定の状態フォルダ

    return 設定(
        作業フォルダ=作業フォルダ,
        状態フォルダ=状態フォルダ,
        # 仕様: design.md#定期実行と未処理VTTの検知(10分ごと)
        実行間隔秒=600,
        # 仕様: design.md#議事録の生成(タイムアウト15分)
        生成タイムアウト秒=900,
        # 仕様: requirements.md#議事録の生成 [5](上限3回)
        再試行上限=3,
        # 仕様: design.md#定期実行と未処理VTTの検知(古いロックは30分で回収)
        ロックを無効とみなす秒=1800,
        # 仕様: design.md#ログ(観測すべき項目はすべてINFO以上で出す)
        ログレベル=logging.INFO,
    )
