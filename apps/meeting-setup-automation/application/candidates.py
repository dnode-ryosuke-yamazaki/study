"""候補の絞り込み(曜日・祝日・時間帯・全員空き・重複除外)。

探索フローが返す枠は世界標準時で、時間帯・曜日・祝日の絞り込みは効いていない
(architecture.md#技術的制約)。ここで日本時間に変換してから絞る
(design.md#候補の絞り込みと選択画面の用意 手順3〜6)。

全員空きの判定は出席可能率では行わない。下限を100%にしても仮の予定が入った出席者や
開催者を含む枠が返るため、出席者ごとの空き状況のすべてと開催者の空き状況の両方が
「空き」であることを見る。開催者の空き状況は出席者の一覧には含まれない別の項目で届く。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Dict, List, Optional, Sequence, Tuple

import holidays_jp
import timeutil

空き = "free"
仮 = "tentative"

除外理由_時間帯外 = "時間帯外"
除外理由_祝日 = "祝日"
除外理由_曜日外 = "曜日外"
除外理由_全員空きでない = "全員空きでない"
除外理由_重複 = "重複"
除外理由_上限超過 = "上限超過"
_除外理由一覧 = (除外理由_時間帯外, 除外理由_祝日, 除外理由_曜日外, 除外理由_全員空きでない, 除外理由_重複, 除外理由_上限超過)


@dataclass(frozen=True)
class 絞り込み条件:
    時間帯開始: time
    時間帯終了: time
    対象曜日: Tuple[int, ...]
    全員空き: bool
    上限件数: int

    @classmethod
    def 依頼から(cls, 依頼: dict) -> "絞り込み条件":
        """依頼ファイルの絞り込みの条件(Skillだけが読む区分)から復元する。再開時に同じ条件で絞るため。"""
        f = 依頼["filter"]
        return cls(
            時間帯開始=time.fromisoformat(f["timeWindowStart"]),
            時間帯終了=time.fromisoformat(f["timeWindowEnd"]),
            対象曜日=tuple(int(w) for w in f["weekdays"]),
            全員空き=bool(f["requireAllFree"]),
            上限件数=int(f["maxResults"]),
        )


@dataclass
class 枠:
    開始: datetime  # 日本時間
    終了: datetime  # 日本時間
    出席者空き: List[Tuple[str, str]]  # (メールアドレス, 空き状況)
    開催者空き: str
    試行番号: int
    出席可能率: Optional[float] = None

    @property
    def 仮の参加者(self) -> List[str]:
        return [a for a, s in self.出席者空き if s == 仮]

    @property
    def 開催者が仮(self) -> bool:
        return self.開催者空き == 仮

    @property
    def 空いていない人数(self) -> int:
        人数 = sum(1 for _, s in self.出席者空き if s != 空き)
        if self.開催者空き and self.開催者空き != 空き:
            人数 += 1
        return 人数

    def 全員空きか(self, 仮を空きとみなす: bool) -> bool:
        許す = {空き, 仮} if 仮を空きとみなす else {空き}
        return all(s in 許す for _, s in self.出席者空き) and (self.開催者空き in 許す)

    def 重なる(self, 他: "枠") -> bool:
        return self.開始 < 他.終了 and 他.開始 < self.終了


@dataclass
class 候補の読み取り:
    依頼id: str
    試行番号: int
    枠一覧: List[枠]
    枠が無かった理由: str
    失敗理由: str

    @property
    def 失敗(self) -> bool:
        return bool(self.失敗理由)


@dataclass
class 絞り込み結果:
    採用: List[枠]
    除外内訳: Dict[str, int] = field(default_factory=dict)
    受け取った件数: int = 0


def _空き状況(値) -> str:
    return str(値 or "").strip().lower()


def _枠を読む(項目: dict, 試行番号: int) -> 枠:
    slot = 項目.get("meetingTimeSlot") or {}
    開始 = timeutil.to_jst(timeutil.parse_datetime((slot.get("start") or {}).get("dateTime")))
    終了 = timeutil.to_jst(timeutil.parse_datetime((slot.get("end") or {}).get("dateTime")))
    出席者 = []
    for a in 項目.get("attendeeAvailability") or []:
        アドレス = (((a.get("attendee") or {}).get("emailAddress") or {}).get("address") or "").strip().lower()
        出席者.append((アドレス, _空き状況(a.get("availability"))))
    率 = 項目.get("confidence")
    return 枠(
        開始=開始,
        終了=終了,
        出席者空き=出席者,
        開催者空き=_空き状況(項目.get("organizerAvailability")),
        試行番号=試行番号,
        出席可能率=float(率) if 率 is not None else None,
    )


def 読む(内容: dict) -> 候補の読み取り:
    """候補ファイルから枠の一覧・枠が無かった理由・失敗理由を取り出す。枠は日本時間に変換して持つ。"""
    試行番号 = int(内容.get("attempt") or 1)
    失敗理由 = 内容.get("error") or ""
    if not isinstance(失敗理由, str):
        失敗理由 = str(失敗理由)
    枠一覧: List[枠] = []
    if not 失敗理由:
        for 項目 in 内容.get("meetingTimeSuggestions") or []:
            枠一覧.append(_枠を読む(項目, 試行番号))
    return 候補の読み取り(
        依頼id=str(内容.get("requestId") or ""),
        試行番号=試行番号,
        枠一覧=枠一覧,
        枠が無かった理由=str(内容.get("emptySuggestionsReason") or ""),
        失敗理由=失敗理由,
    )


def _時間帯に収まる(w: 枠, 条件: 絞り込み条件) -> bool:
    if w.終了.date() != w.開始.date():
        return False
    return 条件.時間帯開始 <= w.開始.time() and w.終了.time() <= 条件.時間帯終了


def _祝日にかかる(w: 枠) -> bool:
    return holidays_jp.is_holiday(w.開始.date()) or holidays_jp.is_holiday(w.終了.date())


def 絞り込む(読み: 候補の読み取り, 条件: 絞り込み条件, 仮を空きとみなす: bool = False) -> 絞り込み結果:
    """枠を条件で絞り、開始の早い順に重複を除いて上限件数まで採用する。

    `仮を空きとみなす` は候補が0件のときの代替案1で使う(同じ候補ファイルを絞り直すだけで、
    探索の依頼は出し直さない)。全員空きを求めない条件では空き状況による除外を行わない。
    """
    内訳 = {理由: 0 for 理由 in _除外理由一覧}
    残り: List[枠] = []
    for w in 読み.枠一覧:
        if not _時間帯に収まる(w, 条件):
            内訳[除外理由_時間帯外] += 1
        elif _祝日にかかる(w):
            内訳[除外理由_祝日] += 1
        elif w.開始.weekday() not in 条件.対象曜日:
            内訳[除外理由_曜日外] += 1
        elif 条件.全員空き and not w.全員空きか(仮を空きとみなす):
            内訳[除外理由_全員空きでない] += 1
        else:
            残り.append(w)

    採用: List[枠] = []
    for w in sorted(残り, key=lambda x: (x.開始, x.終了)):
        if any(w.重なる(採用済み) for 採用済み in 採用):
            内訳[除外理由_重複] += 1
        elif len(採用) >= 条件.上限件数:
            内訳[除外理由_上限超過] += 1
        else:
            採用.append(w)
    return 絞り込み結果(採用=採用, 除外内訳=内訳, 受け取った件数=len(読み.枠一覧))
