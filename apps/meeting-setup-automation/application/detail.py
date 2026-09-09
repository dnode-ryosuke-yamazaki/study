"""予定詳細の依頼の書き出しと、予定詳細から枠に重なる仮の予定の件名を取り出す処理。

候補が0件のときの代替案1で、仮の予定を持つ参加者について「重ねてよいか」の判断材料として
予定の件名を示す(requirements.md#候補が0件のときの代替案の提示 [2][3])。予定の本文と出席者は
扱わない。予定詳細ファイルは選択が済んだ時点で削除する(design.md#セキュリティ)。

予定詳細ファイルの形(予定詳細フローが書く。詳細は power-automate/README.md):
    {
      "requestId": "...", "error": "",
      "attendees": [
        {"address": "b@example.com", "calendarFound": true,
         "events": [{"subject": "...", "showAs": "tentative", "sensitivity": "normal",
                     "isRecurring": false,
                     "start": {"dateTime": "2026-09-10T01:00:00.0000000", "timeZone": "UTC"},
                     "end": {...}}]},
        {"address": "c@example.com", "calendarFound": false, "events": []}
      ]
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence

import ledger
import timeutil
from candidates import 枠
from config import 設定

理由_未共有 = "カレンダーが共有されていない(開催者のカレンダー一覧に無い)ため件名を取得できません"
理由_繰り返し = "繰り返し予定のため件名を取得できません"
理由_件名なし = "重なる仮の予定の件名を取得できませんでした"
理由_取得失敗 = "予定詳細を取得できませんでした"


@dataclass
class 書き出し結果:
    ok: bool
    path: Optional[str] = None
    error: str = ""


@dataclass
class 予定:
    件名: str
    状態: str
    非公開: bool
    繰り返し: bool
    開始: datetime  # 日本時間
    終了: datetime  # 日本時間


@dataclass
class 参加者の予定:
    アドレス: str
    カレンダーあり: bool
    予定一覧: List[予定] = field(default_factory=list)


@dataclass
class 予定詳細の読み取り:
    依頼id: str
    失敗理由: str
    参加者ごと: Dict[str, 参加者の予定]

    @property
    def 失敗(self) -> bool:
        return bool(self.失敗理由)


@dataclass
class 件名情報:
    """1つの枠について、仮の予定を持つ参加者1人ぶんの表示内容。件名は非公開なら持たない。"""

    アドレス: str
    件名一覧: List[str] = field(default_factory=list)
    非公開: bool = False
    取得できない: bool = False
    理由: str = ""


def 依頼を組み立てる(依頼id: str, 枠一覧: Sequence[枠], 対象アドレス: Sequence[str]) -> dict:
    """代替案1で残った枠すべてを含む範囲と、件名を取りに行く参加者で予定詳細の依頼を作る。"""
    開始 = min(w.開始 for w in 枠一覧)
    終了 = max(w.終了 for w in 枠一覧)
    return {
        "requestId": 依頼id,
        "attendees": list(対象アドレス),
        "start": timeutil.format_jst(開始),
        "end": timeutil.format_jst(終了),
    }


def 書き出す(設定値: 設定, 依頼: dict) -> 書き出し結果:
    path = ledger.予定詳細依頼ファイル(設定値, 依頼["requestId"])
    try:
        ledger.write_json(path, 依頼)
    except OSError as e:
        return 書き出し結果(ok=False, path=str(path), error=f"予定詳細の依頼ファイルを書き出せません: {e}")
    return 書き出し結果(ok=True, path=str(path))


def _繰り返しか(項目: dict) -> bool:
    if 項目.get("isRecurring") is True or 項目.get("seriesMasterId"):
        return True
    recurrence = 項目.get("recurrence")
    if recurrence and str(recurrence).strip().lower() not in ("none", "null"):
        return True
    return str(項目.get("type") or "").lower() in ("seriesmaster", "occurrence", "exception")


def _予定を読む(項目: dict) -> Optional[予定]:
    try:
        開始 = timeutil.to_jst(timeutil.parse_datetime((項目.get("start") or {}).get("dateTime")))
        終了 = timeutil.to_jst(timeutil.parse_datetime((項目.get("end") or {}).get("dateTime")))
    except (ValueError, AttributeError, TypeError):
        return None
    return 予定(
        件名=str(項目.get("subject") or ""),
        状態=str(項目.get("showAs") or "").strip().lower(),
        非公開=str(項目.get("sensitivity") or "").strip().lower() in ("private", "confidential"),
        繰り返し=_繰り返しか(項目),
        開始=開始,
        終了=終了,
    )


def 読む(内容: dict) -> 予定詳細の読み取り:
    失敗理由 = 内容.get("error") or ""
    参加者ごと: Dict[str, 参加者の予定] = {}
    for a in 内容.get("attendees") or []:
        アドレス = str(a.get("address") or "").strip().lower()
        if not アドレス:
            continue
        予定一覧 = [p for p in (_予定を読む(e) for e in a.get("events") or []) if p is not None]
        参加者ごと[アドレス] = 参加者の予定(
            アドレス=アドレス, カレンダーあり=bool(a.get("calendarFound", True)), 予定一覧=予定一覧
        )
    return 予定詳細の読み取り(
        依頼id=str(内容.get("requestId") or ""),
        失敗理由=失敗理由 if isinstance(失敗理由, str) else str(失敗理由),
        参加者ごと=参加者ごと,
    )


def 件名を取得できた人数(読み: 予定詳細の読み取り) -> int:
    """画面・通知に件名を示せる参加者の数。ログに出す件数で、件名そのものは出さない(design.md#ログ)。

    非公開の予定と繰り返し予定は件名を示さないため、数にも含めない(利用者が見る結果と
    ログの数字を一致させる)。
    """
    return sum(
        1
        for p in 読み.参加者ごと.values()
        if p.カレンダーあり and any(e.件名 and not e.非公開 and not e.繰り返し for e in p.予定一覧)
    )


def 枠に重なる仮の予定(読み: Optional[予定詳細の読み取り], w: 枠, 対象アドレス: Sequence[str]) -> List[件名情報]:
    """枠と時間が重なる仮の予定を参加者ごとに選ぶ。予定詳細が無い・失敗のときは全員「取得できない」。"""
    一覧: List[件名情報] = []
    for アドレス in 対象アドレス:
        アドレス = アドレス.strip().lower()
        if 読み is None or 読み.失敗:
            一覧.append(件名情報(アドレス=アドレス, 取得できない=True, 理由=理由_取得失敗))
            continue
        参加者 = 読み.参加者ごと.get(アドレス)
        if 参加者 is None or not 参加者.カレンダーあり:
            一覧.append(件名情報(アドレス=アドレス, 取得できない=True, 理由=理由_未共有))
            continue
        重なる = [p for p in 参加者.予定一覧 if p.状態 == "tentative" and p.開始 < w.終了 and w.開始 < p.終了]
        件名 = [p.件名 for p in 重なる if not p.繰り返し and not p.非公開 and p.件名]
        非公開 = any(p.非公開 for p in 重なる if not p.繰り返し)
        if 件名 or 非公開:
            一覧.append(件名情報(アドレス=アドレス, 件名一覧=件名, 非公開=非公開))
        elif any(p.繰り返し for p in 重なる):
            一覧.append(件名情報(アドレス=アドレス, 取得できない=True, 理由=理由_繰り返し))
        else:
            一覧.append(件名情報(アドレス=アドレス, 取得できない=True, 理由=理由_件名なし))
    return 一覧


def 削除(設定値: 設定, 依頼id: str) -> bool:
    """予定詳細ファイルを削除する。無ければFalse(例外にしない)。"""
    path = ledger.予定詳細ファイル(設定値, 依頼id)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True
