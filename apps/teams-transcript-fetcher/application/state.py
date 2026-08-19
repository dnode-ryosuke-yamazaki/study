"""取得済み記録と、二重起動を防ぐロック。

**同期フォルダの外に置く**(requirements.md#状態管理 [1])。同期フォルダに置くと
OneDriveが競合ファイルを作り、状態が二重化して取得済み判定が壊れる。置き場所の
決定は config.py が持つ。

記録は「速さとエラー回数の保持」のためのもので、唯一の真実の源ではない。壊れても
出力置き場の同名ファイルの存在チェックが二重取得を防ぐため、読めなければ空として
扱い処理を続ける。

**ダウンロードURLは保存しない。** 死んだURLの同定には発行時刻だけを使う
(design.md#セキュリティ)。

対応する仕様: design.md#状態管理 / design.md#エラーハンドリング
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

#: 録画の識別子と並び順をつなぐ記号。ファイル名には使わないので何でもよい。
_識別子の区切り = "#"

#: 残ったロックを無効とみなすまでの既定秒数。実行間隔(5分)の何倍かの想定。
既定の無効とみなす秒 = 1800


class 先行実行が動作中(Exception):
    """別の実行がロックを保持している。今回の実行は何もせず終える。"""


def トランスクリプトの識別子(録画の識別子: str, 並び順: int) -> str:
    """トランスクリプト1件を指す識別子。

    識別は録画単位ではなくトランスクリプト単位で行う
    (requirements.md#状態管理 [3])。並び順は一覧内の添字。
    """
    return f"{録画の識別子}{_識別子の区切り}{並び順}"


def 発行時刻の鍵(時刻: datetime) -> str:
    """発行時刻を集合に入れるための文字列。

    UTC・ミリ秒までに正規化する(design.md#発行時刻の取り決め)。文字列で持つのは
    浮動小数の丸めで一致判定がぶれるのを避けるため。
    """
    utcの時刻 = 時刻.astimezone(timezone.utc)
    return utcの時刻.isoformat(timespec="milliseconds")


def _日時を読む(値: object) -> datetime | None:
    if not isinstance(値, str) or not 値:
        return None
    try:
        読んだ日時 = datetime.fromisoformat(値)
    except ValueError:
        return None
    if 読んだ日時.tzinfo is None:
        return 読んだ日時.replace(tzinfo=timezone.utc)
    return 読んだ日時.astimezone(timezone.utc)


@dataclass
class 録画の状態:
    """1つの録画について、サイクルを越えて持つ必要がある情報。

    どれも「いつ諦めるか」の判断材料。毎回0に戻ると打ち切りが永久に発火しない。
    """

    #: 恒久的失敗の累積回数。上限に達したら要手動確認(requirements.md#エラー時の挙動 [5])
    恒久的失敗の回数: int = 0
    #: 発行要求を出しても保存が進まなかった実行の連続回数(同 [7])
    進捗なし発行要求の回数: int = 0
    #: 台帳の内容を読み取れなかった実行の連続回数。**読めた時点で0に戻す**(同 [11])
    読み取り失敗の回数: int = 0
    #: 恒久的失敗と判定した発行時刻。**集合**で持つ(単一値だと上書きで穴が開く)
    死んだ発行時刻: set[str] = field(default_factory=set)
    #: 観測した既知件数の最大値。件数を単調非減少に保つための下限
    既知件数の最大値: int = 0
    #: 台帳を最初に観測した日時。長期滞留の判定に使う
    初回観測: datetime | None = None
    #: 記録ファイルへ追記済みの失敗種別。同じ失敗を繰り返し追記しないため
    記録済みの失敗種別: set[str] = field(default_factory=set)

    def 死んだ発行時刻に加える(self, 時刻: datetime) -> None:
        self.死んだ発行時刻.add(発行時刻の鍵(時刻))

    def 発行時刻は死んでいるか(self, 時刻: datetime) -> bool:
        return 発行時刻の鍵(時刻) in self.死んだ発行時刻

    def 記録済みにする(self, 失敗種別: str) -> None:
        self.記録済みの失敗種別.add(失敗種別)

    def 記録済みか(self, 失敗種別: str) -> bool:
        return 失敗種別 in self.記録済みの失敗種別


@dataclass
class 状態:
    #: トランスクリプトの識別子 → 取得日時
    取得済み: dict[str, datetime] = field(default_factory=dict)
    #: 録画の識別子 → 録画の状態
    録画: dict[str, 録画の状態] = field(default_factory=dict)

    def 取得済みにする(self, 識別子: str, 日時: datetime) -> None:
        self.取得済み[識別子] = 日時

    def 取得済みか(self, 識別子: str) -> bool:
        return 識別子 in self.取得済み

    def 録画の状態(self, 録画の識別子: str) -> 録画の状態:
        """録画ごとの状態を返す。無ければ作る。"""
        return self.録画.setdefault(録画の識別子, 録画の状態())

    def 録画の状態を消す(self, 録画の識別子: str) -> None:
        """台帳が削除・退避された録画に紐づく状態を落とす。

        死んだ発行時刻の集合は際限なく増えうるため、台帳の消滅を機に片付ける。
        **取得済みの記録は消さない**(重複保存を防ぐ用途であり、台帳の有無とは
        独立している)。仕様: design.md#状態管理
        """
        self.録画.pop(録画の識別子, None)


def 読み込む(状態ファイル: Path) -> 状態:
    """記録を読む。読めない場合は空として扱い、警告を残して処理を続ける。"""
    try:
        中身 = json.loads(状態ファイル.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return 状態()
    except (json.JSONDecodeError, OSError) as 例外:
        logger.warning("取得済み記録を読めないため空として扱う: %s: %s", 状態ファイル, 例外)
        return 状態()

    if not isinstance(中身, dict):
        logger.warning("取得済み記録の形式が想定と違うため空として扱う: %s", 状態ファイル)
        return 状態()

    読んだ状態 = 状態()

    for 識別子, 日時の文字列 in (中身.get("fetched") or {}).items():
        日時 = _日時を読む(日時の文字列)
        if 日時 is not None:
            読んだ状態.取得済み[識別子] = 日時

    for 録画の識別子, 録画の中身 in (中身.get("recordings") or {}).items():
        if not isinstance(録画の中身, dict):
            continue
        読んだ状態.録画[録画の識別子] = 録画の状態(
            恒久的失敗の回数=int(録画の中身.get("permanent_failures") or 0),
            進捗なし発行要求の回数=int(録画の中身.get("stalled_requests") or 0),
            読み取り失敗の回数=int(録画の中身.get("read_failures") or 0),
            死んだ発行時刻=set(録画の中身.get("dead_issued_at") or []),
            既知件数の最大値=int(録画の中身.get("max_known_count") or 0),
            初回観測=_日時を読む(録画の中身.get("first_seen_at")),
            記録済みの失敗種別=set(録画の中身.get("reported_failures") or []),
        )

    return 読んだ状態


def 保存する(対象: 状態, 状態ファイル: Path) -> None:
    """記録を保存する。

    一時ファイルへ書いてから所定の名前へ移す。途中で失敗しても既存の記録が
    壊れないようにするため(design.md#エラーハンドリング 6)。
    """
    書き出す中身 = {
        "fetched": {識別子: 日時.isoformat() for 識別子, 日時 in 対象.取得済み.items()},
        "recordings": {
            録画の識別子: {
                "permanent_failures": 状況.恒久的失敗の回数,
                "stalled_requests": 状況.進捗なし発行要求の回数,
                "read_failures": 状況.読み取り失敗の回数,
                "dead_issued_at": sorted(状況.死んだ発行時刻),
                "max_known_count": 状況.既知件数の最大値,
                "first_seen_at": 状況.初回観測.isoformat() if 状況.初回観測 else None,
                "reported_failures": sorted(状況.記録済みの失敗種別),
            }
            for 録画の識別子, 状況 in 対象.録画.items()
        },
    }

    # json.dumps を先に済ませる。書き出し中に失敗しても一時ファイルすら作らない。
    文字列 = json.dumps(書き出す中身, ensure_ascii=False, indent=2)

    状態ファイル.parent.mkdir(parents=True, exist_ok=True)
    一時ファイル = 状態ファイル.with_name(状態ファイル.name + ".tmp")
    try:
        一時ファイル.write_text(文字列, encoding="utf-8")
        os.replace(一時ファイル, 状態ファイル)
    finally:
        一時ファイル.unlink(missing_ok=True)


class ロック:
    """二重起動を防ぐロック。`with` で使う。

    前回のプロセスが異常終了してロックファイルだけ残ると、以降ずっと起動できなく
    なる。そのため一定時間を過ぎたロックは無効とみなして奪う。
    仕様: design.md#エラーハンドリング 7
    """

    def __init__(
        self, ロックファイル: Path, *, 無効とみなす秒: int = 既定の無効とみなす秒
    ) -> None:
        self._ロックファイル = ロックファイル
        self._無効とみなす秒 = 無効とみなす秒
        self._取得した = False

    def __enter__(self) -> ロック:
        self._ロックファイル.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._排他的に作る()
        except FileExistsError:
            if not self._古すぎるか():
                raise 先行実行が動作中(f"{self._ロックファイル} が保持されている")
            logger.info(
                "古いロックを無効とみなして奪う: %s(%d秒以上経過)",
                self._ロックファイル,
                self._無効とみなす秒,
            )
            self._ロックファイル.unlink(missing_ok=True)
            self._排他的に作る()
        self._取得した = True
        return self

    def __exit__(self, *例外の情報: object) -> None:
        if self._取得した:
            self._ロックファイル.unlink(missing_ok=True)
            self._取得した = False

    def _排他的に作る(self) -> None:
        記述子 = os.open(self._ロックファイル, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(記述子, "w", encoding="utf-8") as ファイル:
            ファイル.write(str(os.getpid()))

    def _古すぎるか(self) -> bool:
        try:
            経過秒 = time.time() - self._ロックファイル.stat().st_mtime
        except OSError:
            # ちょうど消えた。次の作成で取れる。
            return True
        return 経過秒 >= self._無効とみなす秒
