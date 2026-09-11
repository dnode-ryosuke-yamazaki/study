"""日時の解釈と日本時間への変換。

候補ファイルの時刻は世界標準時で届く(オフセット無しの
`2026-09-10T01:00:00.0000000` や末尾 `Z`)。台帳に書く日時は日本時間のオフセット付き
ISO 8601 に揃える(design.md#データ設計台帳ファイル)。日付・曜日・時間帯の判定は
必ず `to_jst` で変換した後に行う(design.md#候補の絞り込みと選択画面の用意 手順3)。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
UTC = timezone.utc

_小数秒 = re.compile(r"(\.\d+)(?=(Z|[+-]\d{2}:?\d{2})?$)")


def parse_datetime(値: str) -> datetime:
    """ISO 8601風の文字列を解釈する。オフセットが無ければ世界標準時とみなす。

    Graphは小数秒を7桁で返すことがあるため、小数部は落として解釈する(枠の判定に秒未満は要らない)。
    """
    if not isinstance(値, str) or not 値.strip():
        raise ValueError(f"日時として解釈できません: {値!r}")
    文字列 = 値.strip()
    if 文字列.endswith("Z"):
        文字列 = 文字列[:-1] + "+00:00"
    文字列 = _小数秒.sub("", 文字列)
    dt = datetime.fromisoformat(文字列)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def to_jst(dt: datetime) -> datetime:
    """日本時間に変換する。tz情報の無いdatetimeは世界標準時とみなす。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(JST)


def format_jst(dt: datetime) -> str:
    """台帳に書く形(日本時間・オフセット付き・秒まで)にする。"""
    return to_jst(dt).replace(microsecond=0).isoformat()


def now_jst() -> datetime:
    return datetime.now(JST)
