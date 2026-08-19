"""処理結果の記録(`_status.md`)。

**PCの前にいなくても状況が分かるように、OneDrive上に置く**
(requirements.md#処理結果の記録 [2])。Teamsへの通知はDLPで使えないため、
これが唯一の「気づける手段」になる。

**同じ対象の同じ失敗を繰り返し追記しない。** 5分間隔で実行されるため、抑止しないと
1日あたり数百行が同一内容で埋まり、「記録を見て気づく」という目的自体が損なわれる
(同 [3])。記録済みかどうかは取得済み記録側が持つ(state.録画の状態.記録済みか)。

**ダウンロードURLを書かない**(design.md#セキュリティ)。

対応する仕様: requirements.md#処理結果の記録 / design.md#処理結果の記録
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

#: 「要手動確認」の原因を区別するラベル。日常的に出るものと調査が必要なものを
#: 混ぜないため(requirements.md#処理結果の記録 [5])。
ラベル_トランスクリプト0件 = "トランスクリプト0件"
ラベル_件数不足 = "件数不足"
ラベル_取得失敗 = "取得失敗"
ラベル_長期滞留 = "長期滞留"
ラベル_期限切れ = "期限切れ"
ラベル_台帳が不正 = "台帳が不正"
#: ローカルの設定不足。待っても直らないので人が対処する必要がある。
ラベル_設定の問題 = "設定の問題"
#: 台帳の内容を読み取れない状態が続いている。**台帳は退避せず残してある**
#: (requirements.md#エラー時の挙動 [11])。
ラベル_読み取り失敗 = "読み取り失敗"

#: 記録ファイルの先頭に置く見出し。初回作成時のみ書く。
_見出し = "# トランスクリプト取得の記録\n\n"


@dataclass(frozen=True)
class 記録する行:
    """記録ファイルに追記する1件分。"""

    ラベル: str
    会議名: str
    時刻の表示: str
    詳細: str

    def 整形する(self, 実行日時: datetime) -> str:
        return (
            f"- {実行日時.astimezone().strftime('%Y-%m-%d %H:%M')} "
            f"[{self.ラベル}] {self.会議名}({self.時刻の表示}) — {self.詳細}"
        )


def 追記する(記録ファイル: Path, 行たち: list[記録する行], 実行日時: datetime) -> bool:
    """記録ファイルに追記する。書くものが無ければ何もしない。

    追記のみで既存の内容は書き換えない。書くものが1件も無いときにファイルへ
    触れないのは、不要なOneDrive同期を発生させないため。

    戻り値は追記したかどうか。
    """
    if not 行たち:
        return False

    記録ファイル.parent.mkdir(parents=True, exist_ok=True)
    初回 = not 記録ファイル.exists()

    本文 = "".join(f"{行.整形する(実行日時)}\n" for 行 in 行たち)
    with 記録ファイル.open("a", encoding="utf-8") as ファイル:
        if 初回:
            ファイル.write(_見出し)
        ファイル.write(本文)

    logger.info("処理結果を記録した: %d件", len(行たち))
    return True
