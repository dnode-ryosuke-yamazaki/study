"""台帳ファイルの到着待ちと進捗の出力。

待つ相手のファイルは依頼IDから名前が決まるため、フォルダの一覧は取らずその名前のファイルの
有無だけを一定間隔で確かめる(同期フォルダは一覧の取得が許可されないことがある)。現れた
ファイルは想定の形式(JSON)として読めるまで「書き込み中」とみなして待ち続け、上限を超えたら
打ち切る(design.md#往復の待ち合わせと打ち切り)。時計と待ち関数は差し替え可能にして、
テストで実時間を使わない。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

import ledger


@dataclass
class 待ち結果:
    到着: bool
    打ち切り: bool
    内容: Any
    経過秒: float


def _進捗文(対象名: str, 経過秒: float, 上限秒: float) -> str:
    return f"{対象名}の到着を待っています({int(経過秒)}秒経過 / 上限{int(上限秒)}秒)"


def wait_for_json(
    path: Path,
    上限秒: float,
    間隔秒: float,
    対象名: str,
    進捗: Callable[[str], None],
    時計: Callable[[], float] = time.monotonic,
    待つ: Callable[[float], None] = time.sleep,
    確認前: Optional[Callable[[], None]] = None,
) -> 待ち結果:
    """`path` がJSONとして読めるようになるまで待つ。上限を超えたら打ち切り。"""
    結果 = wait_for_all(
        {対象名: (path, 上限秒)}, 間隔秒=間隔秒, 進捗=進捗, 時計=時計, 待つ=待つ, 確認前=確認前
    )
    return 結果[対象名]


def wait_for_all(
    対象: Mapping[str, Tuple[Path, float]],
    間隔秒: float,
    進捗: Callable[[str], None],
    時計: Callable[[], float] = time.monotonic,
    待つ: Callable[[float], None] = time.sleep,
    確認前: Optional[Callable[[], None]] = None,
) -> Dict[str, 待ち結果]:
    """複数のファイルを同時に待つ。待ちごとに別々の上限を適用し、片方が打ち切られても
    もう片方は上限まで待ち続ける(requirements.md#往復の待ち合わせ [5])。

    `対象` は {表示名: (ファイル, 上限秒)}。
    """
    開始 = 時計()
    結果: Dict[str, 待ち結果] = {}
    未到着 = dict(対象)
    while True:
        if 確認前 is not None:
            確認前()
        経過 = 時計() - 開始
        for 名前, (path, 上限秒) in list(未到着.items()):
            内容 = ledger.read_json(path)
            if 内容 is not None:
                結果[名前] = 待ち結果(到着=True, 打ち切り=False, 内容=内容, 経過秒=経過)
                del 未到着[名前]
                continue
            進捗(_進捗文(名前, 経過, 上限秒))
            if 経過 >= 上限秒:
                結果[名前] = 待ち結果(到着=False, 打ち切り=True, 内容=None, 経過秒=経過)
                del 未到着[名前]
        if not 未到着:
            return 結果
        待つ(間隔秒)
