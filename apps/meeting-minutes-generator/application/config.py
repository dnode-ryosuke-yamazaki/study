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

#: デイリー系の判定語を差し替える環境変数(カンマ区切り)。
判定語環境変数 = "MINUTES_GENERATOR_DAILY_KEYWORDS"

#: 議事録全文へのリンクの組み立て元を差し替える環境変数。
ビューア環境変数 = "MINUTES_GENERATOR_WEB_VIEWER"
Webパス環境変数 = "MINUTES_GENERATOR_WEB_DIR"

#: 定期進捗確認の会議を見分ける語。ファイル名に含まれていればデイリー系として扱う
#: (大文字小文字は区別しない)。仕様: requirements.md#会議種別による構成の切り替え [1]
既定のデイリー判定語 = ("デイリー", "daily", "朝会", "スタンドアップ", "standup")

#: 議事録をブラウザで開くためのファイルビューアのURL。共有ストレージのファイルを
#: 直接指すURLはブラウザ内で表示されずダウンロードになるため、ビューアで開く形式の
#: URLを組み立てる。仕様: requirements.md#議事録全文へのリンク [1]
既定のビューアURL = (
    "https://jpdeloitte-my.sharepoint.com/personal/"
    "ryosuke_yamazaki_tohmatsu_co_jp/_layouts/15/onedrive.aspx"
)

#: 作業フォルダに対応する、共有ストレージ上のサーバー相対パス。ローカルの同期先
#: (作業フォルダ)とは別物なので、Web側の1つの起点としてここに持つ。
既定の作業フォルダのWebパス = (
    "/personal/ryosuke_yamazaki_tohmatsu_co_jp/Documents/00_root/auto"
)

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

    デイリー判定語: tuple[str, ...]
    ビューアURL: str
    作業フォルダのWebパス: str

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
        Power Automateフローが検知して投稿する。Teams投稿系の検知フォルダを
        `teamsNotice/` 配下に集約する。仕様: requirements.md#Teamsへの共有 [1]
        """
        return self.作業フォルダ / "teamsNotice/minutesNotice"

    @property
    def 議事録フォルダのWebパス(self) -> str:
        """議事録フォルダの、共有ストレージ上のサーバー相対パス。

        ローカルの議事録フォルダと同じく作業フォルダから導き、Web側とローカル側で
        置き場所がずれないようにする。仕様: requirements.md#議事録全文へのリンク [2]
        """
        if not self.作業フォルダのWebパス:
            return ""
        return f"/{self.作業フォルダのWebパス.strip('/')}/minutes"

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
        # 仕様: requirements.md#会議種別による構成の切り替え [1]
        デイリー判定語=_判定語を決める(),
        # 仕様: requirements.md#議事録全文へのリンク [2]
        ビューアURL=os.environ.get(ビューア環境変数) or 既定のビューアURL,
        作業フォルダのWebパス=os.environ.get(Webパス環境変数) or 既定の作業フォルダのWebパス,
    )


def _判定語を決める() -> tuple[str, ...]:
    """デイリー系の判定語を「環境変数 → 既定値」の順で決める。

    環境変数はカンマ区切り。空要素は捨て、結果が空になる場合は既定値を使う
    (設定ミスで判定が静かに無効化されるのを避ける)。
    """
    指定 = os.environ.get(判定語環境変数, "")
    語 = tuple(部分.strip() for 部分 in 指定.split(",") if 部分.strip())
    return 語 or 既定のデイリー判定語
