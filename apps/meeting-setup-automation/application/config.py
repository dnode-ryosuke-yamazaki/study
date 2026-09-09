"""設定値とパスの解決。

台帳フォルダ・通知フォルダ・作業フォルダの位置、待ち時間の上限、既定の探索条件は
仕様で根拠付きに決められた値なので、既定値をここ1箇所に集約する。テストと環境差のため
環境変数で差し替えられる。ビューアURLは個人のテナントを含むためリポジトリには置かず、
作業フォルダの `settings.json`(または環境変数)から読む。

対応する仕様: apps/meeting-setup-automation/specs/meeting-scheduling/
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Mapping, Optional

台帳ルート環境変数 = "MEETING_SETUP_LEDGER_ROOT"
通知フォルダ環境変数 = "MEETING_SETUP_NOTICE_DIR"
作業フォルダ環境変数 = "MEETING_SETUP_WORK_DIR"
候補待ち上限環境変数 = "MEETING_SETUP_CANDIDATES_TIMEOUT_SEC"
予定詳細待ち上限環境変数 = "MEETING_SETUP_DETAIL_TIMEOUT_SEC"
作成結果待ち上限環境変数 = "MEETING_SETUP_RESULT_TIMEOUT_SEC"
確認間隔環境変数 = "MEETING_SETUP_POLL_INTERVAL_SEC"
同期猶予環境変数 = "MEETING_SETUP_SYNC_GRACE_SEC"
ビューアurl環境変数 = "MEETING_SETUP_WEB_VIEWER"
サーバー相対パス環境変数 = "MEETING_SETUP_WEB_DIR"

#: OneDrive同期フォルダの `00_root/auto/` 配下。台帳は `meetingSetting/`、通知は
#: `teamsNotice/meetingSetting/` に分ける(通知フローが台帳を誤検知しないため)。
#: 仕様: requirements.md#台帳ファイルの扱い [1][4]
_同期ルート = Path.home() / "Library/CloudStorage/OneDrive-Deloitte(O365D)/00_root/auto"
既定の台帳ルート = _同期ルート / "meetingSetting"
既定の通知フォルダ = _同期ルート / "teamsNotice" / "meetingSetting"

#: メンバー名簿・ログ・ビューア設定の置き場。同期フォルダの外、かつGit管理外。
#: 仕様: requirements.md#参加者の解決 [1]
既定の作業フォルダ = Path.home() / "Library/Application Support/meeting-setup-automation"


class 設定エラー(Exception):
    """環境変数や設定ファイルの値が解釈できない。メッセージは利用者向けの日本語。"""


@dataclass(frozen=True)
class 設定:
    台帳ルート: Path
    通知フォルダ: Path
    作業フォルダ: Path

    #: 3つの待ちの上限は別々に持つ(実測の結果、別の値になりうるため)。
    #: 仕様: requirements.md#往復の待ち時間の上限 [1][2]
    候補待ち上限秒: int
    予定詳細待ち上限秒: int
    作成結果待ち上限秒: int
    確認間隔秒: int
    同期猶予秒: int

    ビューアurl: Optional[str]
    サーバー相対パス: Optional[str]

    # --- 既定の探索条件(requirements.md#候補探索の既定条件 [1][2]) ---
    既定の探索期間日数: int = 14
    既定の時間帯開始: time = time(9, 30)
    既定の時間帯終了: time = time(17, 30)
    既定の候補件数: int = 5
    既定の対象曜日: tuple = (0, 1, 2, 3, 4)
    既定の出席可能率下限: int = 100
    #: フローには上限件数より多めに返させ、Skill側で絞る(design.md 設計判断2)
    フローに返させる最大件数: int = 50

    # --- 代替案2の条件(requirements.md#候補が0件のときの代替案の提示 [1]) ---
    代替案の探索期間日数: int = 21
    代替案の時間帯開始: time = time(9, 30)
    代替案の時間帯終了: time = time(18, 30)

    #: 所要時間の下限(requirements.md#依頼内容の受け付け条件 [1])
    所要時間の下限分: int = 5

    @property
    def 探索期間の上限日数(self) -> int:
        """終了日は当日から3週間以内(代替案2の期間と同じ)。requirements.md#依頼内容の受け付け条件 [3]"""
        return self.代替案の探索期間日数

    @property
    def 依頼フォルダ(self) -> Path:
        return self.台帳ルート / "request"

    @property
    def 候補フォルダ(self) -> Path:
        return self.台帳ルート / "candidates"

    @property
    def 予定詳細依頼フォルダ(self) -> Path:
        return self.台帳ルート / "detailRequest"

    @property
    def 予定詳細フォルダ(self) -> Path:
        return self.台帳ルート / "detail"

    @property
    def 選択結果フォルダ(self) -> Path:
        return self.台帳ルート / "selection"

    @property
    def 作成結果フォルダ(self) -> Path:
        return self.台帳ルート / "result"

    @property
    def htmlフォルダ(self) -> Path:
        return self.台帳ルート / "html"

    @property
    def 名簿ファイル(self) -> Path:
        return self.作業フォルダ / "roster.json"

    @property
    def 設定ファイル(self) -> Path:
        return self.作業フォルダ / "settings.json"

    @property
    def ログファイル(self) -> Path:
        return self.作業フォルダ / "meeting-setup.log"


def _整数(environ: Mapping[str, str], 名前: str, 既定: int, 下限: Optional[int] = None) -> int:
    値 = environ.get(名前)
    if 値 is None or 値 == "":
        return 既定
    try:
        数 = int(値)
    except ValueError as e:
        raise 設定エラー(f"環境変数 {名前} の値 {値!r} を整数として読めません") from e
    if 下限 is not None and 数 < 下限:
        raise 設定エラー(f"環境変数 {名前} の値 {値!r} は {下限} 以上である必要があります")
    return 数


def _ビューア設定(作業フォルダ: Path) -> dict:
    ファイル = 作業フォルダ / "settings.json"
    if not ファイル.is_file():
        return {}
    try:
        値 = json.loads(ファイル.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise 設定エラー(f"設定ファイル {ファイル} を読めません: {e}") from e
    if not isinstance(値, dict):
        raise 設定エラー(f"設定ファイル {ファイル} はオブジェクトである必要があります")
    return 値


def load(environ: Optional[Mapping[str, str]] = None) -> 設定:
    """環境変数(既定は `os.environ`)と作業フォルダの設定ファイルから設定を組み立てる。"""
    env = os.environ if environ is None else environ
    作業フォルダ = Path(env.get(作業フォルダ環境変数) or 既定の作業フォルダ)
    ファイル設定 = _ビューア設定(作業フォルダ)
    ビューア = env.get(ビューアurl環境変数) or ファイル設定.get("output_web_viewer") or None
    相対パス = env.get(サーバー相対パス環境変数) or ファイル設定.get("output_web_dir") or None
    return 設定(
        台帳ルート=Path(env.get(台帳ルート環境変数) or 既定の台帳ルート),
        通知フォルダ=Path(env.get(通知フォルダ環境変数) or 既定の通知フォルダ),
        作業フォルダ=作業フォルダ,
        候補待ち上限秒=_整数(env, 候補待ち上限環境変数, 300),
        予定詳細待ち上限秒=_整数(env, 予定詳細待ち上限環境変数, 300),
        作成結果待ち上限秒=_整数(env, 作成結果待ち上限環境変数, 300),
        # 0以下だと待ちが休みなく回り続けるため下限を置く(design.md#往復の待ち合わせと打ち切り)
        確認間隔秒=_整数(env, 確認間隔環境変数, 5, 下限=1),
        同期猶予秒=_整数(env, 同期猶予環境変数, 30),
        ビューアurl=ビューア,
        サーバー相対パス=相対パス,
    )
