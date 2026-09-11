"""依頼IDから進行状態を判定する。

専用の状態ファイルは持たず、その依頼IDを含む台帳ファイルの有無と中身から導く
(design.md#状態管理)。表は上から順(作成済み → 作成失敗 → 選択済み → 代替案の提示済み →
代替案の提示中 → 候補到着 → 依頼済み)に当てはめ、最初に一致した行を状態とする。

状態の判定に依頼ファイルの最大の試行番号は使わない(代替案2の依頼を書いた直後に
「依頼済み」へ戻ってしまう)。試行番号は代替案2の台帳を指すためだけに返す。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import ledger
from config import 設定

存在しない = "存在しない"
依頼済み = "依頼済み"
候補到着 = "候補到着"
代替案の提示中 = "代替案の提示中"
代替案の提示済み = "代替案の提示済み"
選択済み = "選択済み"
作成失敗 = "作成失敗"
作成済み = "作成済み"

#: 再試行番号を数え上げるときの安全弁(何度失敗しても開催者の指示ごとに1増えるだけなので、実運用でここに届くことはない)
_再試行番号の探索上限 = 1000


@dataclass
class 進行状態:
    状態: str
    試行番号: int = 1
    再試行番号: int = 0
    代替案2の依頼あり: bool = False
    代替案2の候補を待つ: bool = False
    失敗理由: str = ""
    作成結果: Optional[Any] = None
    選択結果: Optional[Any] = None


def 失敗理由を取り出す(結果ファイル: Any) -> str:
    """フローが書く結果ファイルの失敗理由。正常時は空文字。"""
    if not isinstance(結果ファイル, dict):
        return ""
    理由 = 結果ファイル.get("error")
    if not 理由:
        return ""
    return 理由 if isinstance(理由, str) else str(理由)


def 最後の再試行番号(設定値: 設定, 依頼id: str) -> Optional[int]:
    """その依頼IDの選択結果ファイルのうち最も大きい再試行番号。選択結果が無ければNone。"""
    最後 = None
    for r in range(_再試行番号の探索上限):
        if ledger.選択結果ファイル(設定値, 依頼id, r).is_file():
            最後 = r
        else:
            break
    return 最後


def 判定(設定値: 設定, 依頼id: str) -> 進行状態:
    if not ledger.依頼ファイル(設定値, 依頼id, 1).is_file():
        return 進行状態(状態=存在しない)

    代替案2の依頼あり = ledger.依頼ファイル(設定値, 依頼id, 2).is_file()
    試行番号 = 2 if 代替案2の依頼あり else 1
    共通 = dict(試行番号=試行番号, 代替案2の依頼あり=代替案2の依頼あり)

    再試行 = 最後の再試行番号(設定値, 依頼id)
    if 再試行 is not None:
        選択結果 = ledger.read_json(ledger.選択結果ファイル(設定値, 依頼id, 再試行))
        作成結果 = ledger.read_json(ledger.作成結果ファイル(設定値, 依頼id, 再試行))
        if 作成結果 is not None:
            理由 = 失敗理由を取り出す(作成結果)
            return 進行状態(
                状態=作成失敗 if 理由 else 作成済み,
                再試行番号=再試行, 失敗理由=理由, 作成結果=作成結果, 選択結果=選択結果, **共通,
            )
        return 進行状態(状態=選択済み, 再試行番号=再試行, 選択結果=選択結果, **共通)

    if 代替案2の依頼あり:
        代替案2を待つ = ledger.read_json(ledger.候補ファイル(設定値, 依頼id, 2)) is None
        return 進行状態(
            状態=代替案の提示中 if 代替案2を待つ else 代替案の提示済み,
            代替案2の候補を待つ=代替案2を待つ, **共通,
        )

    if ledger.read_json(ledger.候補ファイル(設定値, 依頼id, 1)) is not None:
        return 進行状態(状態=候補到着, **共通)
    return 進行状態(状態=依頼済み, **共通)
