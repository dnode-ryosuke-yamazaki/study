"""候補の絞り込み(曜日・祝日・時間帯・全員空き・重複除外)。

探索フローが返す枠は世界標準時で、時間帯・曜日・祝日の絞り込みは効いていない
(architecture.md#技術的制約)。ここで日本時間に変換してから絞る
(design.md#候補の絞り込みと選択画面の用意 手順3〜6)。

全員空きの判定は出席可能率では行わない。下限を100%にしても仮の予定が入った出席者や
開催者を含む枠が返るため、出席者ごとの空き状況のすべてと開催者の空き状況の両方が
「空き」であることを見る。開催者の空き状況は出席者の一覧には含まれない別の項目で届く。

全員空きを求める依頼では、出席者全員が「空き」で開催者だけが「空き」以外の枠を候補から
除外せずに「開催者のみ不在」として別に集める(requirements.md#開催者の予定のみ重なる枠の提示 [1])。
候補には数えず、並び順・枠どうしの重複除外・上限件数だけを候補と同じに揃える(同 [4])。
採用した候補と時間が重なっても除かない(別の区画に出す枠だから)。

仮の予定を空きとみなす絞り直し(代替案1)に入れるのは、開催者以外の参加者のうち仮の予定が
入っている人が1人以上いて、残りの参加者と開催者がいずれも「空き」か「仮」の枠だけ
(同 [3])。開催者だけが仮の枠は開催者のみ不在の側に出し、同じ枠を2つの区画に出さない。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple

import holidays_jp
import timeutil

空き = "free"
仮 = "tentative"

除外理由_時間帯外 = "時間帯外"
除外理由_祝日 = "祝日"
除外理由_曜日外 = "曜日外"
除外理由_全員空きでない = "全員空きでない"
#: 候補からは外すが捨てずに「開催者のみ不在」の一覧に分けた件数(採用には入れない)
除外理由_開催者のみ不在 = "開催者のみ不在"
除外理由_重複 = "重複"
除外理由_上限超過 = "上限超過"
_除外理由一覧 = (
    除外理由_時間帯外, 除外理由_祝日, 除外理由_曜日外, 除外理由_全員空きでない, 除外理由_開催者のみ不在,
    除外理由_重複, 除外理由_上限超過,
)


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

    def 開催者のみ不在か(self) -> bool:
        """出席者全員が「空き」で、開催者の空き状況だけが「空き」以外(仮・予約済み・外出中・他の場所で作業中・不明)。
        requirements.md#開催者の予定のみ重なる枠の提示 [1]
        """
        return all(s == 空き for _, s in self.出席者空き) and self.開催者空き != 空き

    def 代替案1の対象か(self) -> bool:
        """開催者以外の参加者に仮の予定がある人が1人以上いて、残りの参加者と開催者がいずれも「空き」か「仮」。
        requirements.md#開催者の予定のみ重なる枠の提示 [3]
        """
        許す = {空き, 仮}
        return (
            any(s == 仮 for _, s in self.出席者空き)
            and all(s in 許す for _, s in self.出席者空き)
            and self.開催者空き in 許す
        )

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
    #: 出席者全員が空きで開催者だけが空き以外の枠。候補には数えない(requirements.md#開催者の予定のみ重なる枠の提示 [2])
    開催者のみ不在: List[枠] = field(default_factory=list)


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


def 読む(内容: dict, 試行番号: Optional[int] = None) -> 候補の読み取り:
    """候補ファイルから枠の一覧・枠が無かった理由・失敗理由を取り出す。枠は日本時間に変換して持つ。

    枠がどちらの代替案のものかは、読んだ候補ファイルの試行番号で決まる(design.md#依頼ファイルの区分)。
    呼び出し側が `試行番号` を渡した場合はそれを使い、ファイル本文の `attempt` では上書きしない
    (フローが失敗時の結果ファイルなどで `attempt` を書き落としても取り違えないため)。
    """
    if 試行番号 is None:
        試行番号 = int(内容.get("attempt") or 1)
    失敗理由 = 内容.get("error") or ""
    if not isinstance(失敗理由, str):
        失敗理由 = str(失敗理由)
    枠一覧: List[枠] = []
    if not 失敗理由:
        # 「会議の時間を検索 (V2)」の応答は meetingTimeSuggestions。フローが別名で包んだ場合も拾う
        一覧 = 内容.get("meetingTimeSuggestions")
        if 一覧 is None:
            一覧 = 内容.get("suggestions") or 内容.get("value") or []
        for 項目 in 一覧:
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


def _空き状況で振り分ける(w: 枠, 条件: 絞り込み条件, 仮を空きとみなす: bool) -> str:
    """曜日・時間帯・祝日を満たした枠の行き先。「採用候補」「開催者のみ不在」「除外」のいずれか。"""
    if not 条件.全員空き:
        return "採用候補"
    if 仮を空きとみなす:
        # 代替案1。開催者のみ不在の切り出しは既定の絞り込みでだけ行う(同じ枠を2つの区画に出さない)
        return "採用候補" if w.代替案1の対象か() else "除外"
    if w.開催者のみ不在か():
        return "開催者のみ不在"
    return "採用候補" if w.全員空きか(仮を空きとみなす=False) else "除外"


def _並べて揃える(一覧: List[枠], 上限件数: int, 内訳: Optional[Dict[str, int]]) -> List[枠]:
    """開始の早い順に並べ、互いに時間の重なる枠は先のものだけを残し、上限件数まで取る。
    `内訳` を渡した場合だけ重複・上限超過の件数を数える(候補の内訳にだけ入れる)。
    """
    採用: List[枠] = []
    for w in sorted(一覧, key=lambda x: (x.開始, x.終了)):
        if any(w.重なる(採用済み) for 採用済み in 採用):
            if 内訳 is not None:
                内訳[除外理由_重複] += 1
        elif len(採用) >= 上限件数:
            if 内訳 is not None:
                内訳[除外理由_上限超過] += 1
        else:
            採用.append(w)
    return 採用


def 絞り込む(読み: 候補の読み取り, 条件: 絞り込み条件, 仮を空きとみなす: bool = False) -> 絞り込み結果:
    """枠を条件で絞り、開始の早い順に重複を除いて上限件数まで採用する。

    `仮を空きとみなす` は候補が0件のときの代替案1で使う(同じ候補ファイルを絞り直すだけで、
    探索の依頼は出し直さない)。全員空きを求めない条件では空き状況による除外を行わない。

    全員空きを求める既定の絞り込みでは、出席者全員が空きで開催者だけが空き以外の枠を
    「開催者のみ不在」に分けて返す。採用した候補との重なりでは除かない(別の区画に出す枠だから)。
    """
    内訳 = {理由: 0 for 理由 in _除外理由一覧}
    残り: List[枠] = []
    開催者のみ: List[枠] = []
    for w in 読み.枠一覧:
        if not _時間帯に収まる(w, 条件):
            内訳[除外理由_時間帯外] += 1
        elif _祝日にかかる(w):
            内訳[除外理由_祝日] += 1
        elif w.開始.weekday() not in 条件.対象曜日:
            内訳[除外理由_曜日外] += 1
        else:
            行き先 = _空き状況で振り分ける(w, 条件, 仮を空きとみなす)
            if 行き先 == "採用候補":
                残り.append(w)
            elif 行き先 == "開催者のみ不在":
                内訳[除外理由_開催者のみ不在] += 1
                開催者のみ.append(w)
            else:
                内訳[除外理由_全員空きでない] += 1

    採用 = _並べて揃える(残り, 条件.上限件数, 内訳)
    開催者のみ不在 = _並べて揃える(開催者のみ, 条件.上限件数, None)
    return 絞り込み結果(採用=採用, 除外内訳=内訳, 受け取った件数=len(読み.枠一覧), 開催者のみ不在=開催者のみ不在)
