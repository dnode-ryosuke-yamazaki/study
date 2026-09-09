"""作成結果の読み取りと、会議本文からの会議オプション画面の直リンクの取り出し。

作成フローは `POST /me/events` の応答をそのまま `event` に入れて作成結果ファイルを書く
(design.md#作成結果ファイルの区分)。直リンクはフローでは取り出さず、ここで会議本文から
機械的に取り出す(requirements.md#録画とファシリテーターの設定 [2])。本文に無い場合は
失敗ではなく「取り出せなかった」として扱う(同 [3])。

作成結果ファイルの形:
    {"requestId": "...", "retry": 0, "error": "", "event": {Graphのイベント応答}}
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import timeutil
from progress import 失敗理由を取り出す

_直リンク = re.compile(r"https://teams\.microsoft\.com/meetingOptions/[^\s\"'<>)]*")
_日本時間のタイムゾーン名 = {"tokyo standard time", "asia/tokyo", "jst", "(utc+09:00) osaka, sapporo, tokyo"}


@dataclass
class 作成結果:
    依頼id: str
    再試行番号: int
    失敗理由: str
    会議id: str = ""
    件名: str = ""
    開始: Optional[datetime] = None
    終了: Optional[datetime] = None
    出席者: List[str] = field(default_factory=list)
    参加url: str = ""
    会議本文: str = ""
    開くリンク: str = ""

    @property
    def 失敗(self) -> bool:
        return bool(self.失敗理由)


def _日時(項目: Optional[dict]) -> Optional[datetime]:
    if not 項目 or not 項目.get("dateTime"):
        return None
    dt = timeutil.parse_datetime(項目["dateTime"])
    tz名 = str(項目.get("timeZone") or "").strip().lower()
    if "+" not in 項目["dateTime"] and not 項目["dateTime"].endswith("Z") and tz名 in _日本時間のタイムゾーン名:
        # Graphはオフセット無しの日時とタイムゾーン名の組で返すため、名前が日本時間なら読み替える
        dt = dt.replace(tzinfo=timeutil.JST)
    return timeutil.to_jst(dt)


def _出席者(一覧) -> List[str]:
    結果 = []
    for a in 一覧 or []:
        e = (a or {}).get("emailAddress") or {}
        名前, アドレス = e.get("name") or "", e.get("address") or ""
        結果.append(f"{名前} <{アドレス}>" if 名前 else アドレス)
    return 結果


def 読む(内容: dict) -> 作成結果:
    失敗理由 = 失敗理由を取り出す(内容)
    ev = 内容.get("event")
    if not isinstance(ev, dict):
        # フローがGraphの応答を包まずにそのまま書いた場合は、ファイル全体をイベントとして読む
        ev = 内容 if isinstance(内容, dict) and ("subject" in 内容 or "id" in 内容) else {}
    online = ev.get("onlineMeeting") or {}
    return 作成結果(
        依頼id=str(内容.get("requestId") or ""),
        再試行番号=int(内容.get("retry") or 0),
        失敗理由=失敗理由,
        会議id=str(ev.get("id") or ""),
        件名=str(ev.get("subject") or ""),
        開始=_日時(ev.get("start")),
        終了=_日時(ev.get("end")),
        出席者=_出席者(ev.get("attendees")),
        参加url=str(online.get("joinUrl") or ev.get("onlineMeetingUrl") or ""),
        会議本文=str((ev.get("body") or {}).get("content") or ""),
        開くリンク=str(ev.get("webLink") or ""),
    )


def 会議オプション直リンク(本文: Optional[str]) -> Optional[str]:
    """会議本文から会議オプション画面のURLを取り出す。複数あれば最初のもの。無ければNone。"""
    if not 本文:
        return None
    m = _直リンク.search(html.unescape(本文))
    return m.group(0).rstrip(".,;") if m else None
