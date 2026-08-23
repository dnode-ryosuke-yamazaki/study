"""VTTごとの処理状態の記録と、二重起動を防ぐロック。

状態は「未処理(記録なし)」「再試行待ち(生成失敗の記録があり上限未満)」
「処理済み」「対象外(再試行上限に到達)」の4つ。記録されるのは後ろの3つで、
再試行待ちは生成失敗の回数として記録する。

**状態ファイルが壊れていた場合は初期化せず中断する。** 初期化すると全VTTが
「初回」扱いになり、既処理分の議事録を再生成してTeamsへ再投稿してしまうため
(上流のteams-transcript-fetcherが「読めなければ空として扱う」のと逆の判断。
あちらは出力先の同名チェックという第二の防壁があるが、こちらの投稿は
取り消せない)。

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

#: 残ったロックを無効とみなすまでの既定秒数。
#: 仕様: design.md#定期実行と未処理VTTの検知(30分)
既定の無効とみなす秒 = 1800


class 状態が壊れている(Exception):
    """状態ファイルが読めるが内容が不正。初期化せず処理を中断する。"""


class 状態を読めなかった(Exception):
    """一時的な読み取り失敗(アクセス権・I/Oエラー等)。破損と区別し、
    何も変更せず次回実行に委ねる。"""


class 先行実行が動作中(Exception):
    """別の実行がロックを保持している。今回の実行は何もせず終える。"""


def _日時を読む(値: object) -> datetime:
    if isinstance(値, str):
        try:
            読んだ日時 = datetime.fromisoformat(値)
        except ValueError:
            読んだ日時 = None
        if 読んだ日時 is not None:
            if 読んだ日時.tzinfo is None:
                return 読んだ日時.replace(tzinfo=timezone.utc)
            return 読んだ日時.astimezone(timezone.utc)
    # 日時が読めなくても処理済み・対象外の判定には影響しないため、破損扱いにしない。
    return datetime.fromtimestamp(0, tz=timezone.utc)


@dataclass
class 状態:
    #: VTTファイル名 → 議事録の保存が完了した日時
    処理済み: dict[str, datetime] = field(default_factory=dict)
    #: VTTファイル名 → 生成失敗の累積回数(再試行待ちの実体)
    失敗回数: dict[str, int] = field(default_factory=dict)
    #: VTTファイル名 → 対象外にした日時(再試行上限に到達したもの)
    対象外: dict[str, datetime] = field(default_factory=dict)

    def 処理済みにする(self, vtt名: str, 日時: datetime) -> None:
        self.処理済み[vtt名] = 日時
        self.失敗回数.pop(vtt名, None)

    def 処理済みか(self, vtt名: str) -> bool:
        return vtt名 in self.処理済み

    def 生成失敗を記録する(self, vtt名: str) -> int:
        """再試行回数を1増やし、増やした後の回数を返す。

        仕様: requirements.md#議事録の生成 [4]
        """
        self.失敗回数[vtt名] = self.失敗回数.get(vtt名, 0) + 1
        return self.失敗回数[vtt名]

    def 再試行回数(self, vtt名: str) -> int:
        return self.失敗回数.get(vtt名, 0)

    def 対象外にする(self, vtt名: str, 日時: datetime) -> None:
        """再試行上限に達したVTTを以降の実行の対象から外す。

        仕様: requirements.md#議事録の生成 [5]
        """
        self.対象外[vtt名] = 日時

    def 対象外か(self, vtt名: str) -> bool:
        return vtt名 in self.対象外


def 読み込む(状態ファイル: Path) -> 状態 | None:
    """状態を読む。ファイルが無ければ初回実行としてNoneを返す。

    内容が不正な場合は`状態が壊れている`を投げる(初期化しない。理由はモジュール
    docstringを参照)。一時的な読み取り失敗(アクセス権・I/Oエラー等)は破損と
    区別して`状態を読めなかった`を投げる。呼び出し側は前者を中断、後者を次回への
    持ち越しとして扱う。
    """
    try:
        中身 = json.loads(状態ファイル.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except OSError as 例外:
        # アクセス権・I/Oエラー等は内容の破損ではない。次回実行に委ねる。
        raise 状態を読めなかった(f"{状態ファイル} を読めない: {例外}") from 例外
    except (json.JSONDecodeError, UnicodeDecodeError) as 例外:
        raise 状態が壊れている(f"{状態ファイル} の内容が不正: {例外}") from 例外

    if not isinstance(中身, dict):
        raise 状態が壊れている(f"{状態ファイル} の形式が想定と違う")

    読んだ状態 = 状態()
    try:
        for vtt名, 日時の文字列 in (中身.get("processed") or {}).items():
            読んだ状態.処理済み[str(vtt名)] = _日時を読む(日時の文字列)
        for vtt名, 回数 in (中身.get("retry_counts") or {}).items():
            読んだ状態.失敗回数[str(vtt名)] = int(回数)
        for vtt名, 日時の文字列 in (中身.get("excluded") or {}).items():
            読んだ状態.対象外[str(vtt名)] = _日時を読む(日時の文字列)
    except (AttributeError, TypeError, ValueError) as 例外:
        raise 状態が壊れている(f"{状態ファイル} の形式が想定と違う: {例外}") from 例外

    return 読んだ状態


def 保存する(対象: 状態, 状態ファイル: Path) -> None:
    """状態を保存する。

    一時ファイルへ書いてから所定の名前へ移す。途中で失敗しても既存の記録が
    壊れないようにするため(design.md#エラーハンドリング)。
    """
    書き出す中身 = {
        "processed": {名: 日時.isoformat() for 名, 日時 in 対象.処理済み.items()},
        "retry_counts": dict(対象.失敗回数),
        "excluded": {名: 日時.isoformat() for 名, 日時 in 対象.対象外.items()},
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

    1回の実行(生成タイムアウト15分×直列処理)が起動間隔10分を超えるのは正常系で
    あり、ロックが無いと同じVTTの二重生成と状態ファイルの競合が起こる。前回の
    プロセスが異常終了してロックだけ残った場合に備え、一定時間を過ぎたロックは
    無効とみなして奪う。仕様: design.md#定期実行と未処理VTTの検知
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
