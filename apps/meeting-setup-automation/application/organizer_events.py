"""開催者の予定の依頼(範囲の算出と書き出し)、開催者の予定ファイルの読み取り、予定と枠の突き合わせ、
表示の行の組み立て、取得できなかったときの理由の文。

参加者全員が空きで開催者だけが空き以外の枠(開催者のみ不在)について、開催者自身の既定カレンダーを
読む専用フロー(開催者予定フロー)に依頼を出し、返った予定を枠と突き合わせて「どの予定が重なるか」を
判断材料として整える(design.md#開催者の予定のみ重なる枠の提示)。

- 依頼は依頼1件につき1ファイル。範囲は枠の最小の開始から最大の終了まで(世界標準時、`Z` 付き)
- 予定ファイルからは件名・空き状況の種別・非公開かどうか・開始・終了だけを読み、本文・出席者・場所は読まない
- 突き合わせは両方を世界標準時に揃え、`予定.start < 枠.end かつ 予定.end > 枠.start` を重なりとする。
  `showAs` が `free` の予定は示さない。繰り返し予定は回ごとに展開されて届くので、1件ずつ突き合わせる
- 非公開(`private`・`confidential`)の予定は件名の代わりに「非公開の予定」と示す
- 取得できなくても枠の提示は止めない。理由の文はここで決める(待ち上限・フローの失敗・依頼の書き出し失敗)
- ログには予定の件名を出さず、件数と取得の成否だけを残す(design.md#セキュリティ)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Sequence

import ledger
import timeutil
from candidates import 枠, 空き
from config import 設定

logger = logging.getLogger("meeting_setup")

非公開の件名 = "非公開の予定"
_非公開の値 = {"private", "confidential"}
_種別の表示語 = {
    "free": "空き",
    "tentative": "仮",
    "busy": "予約済み",
    "oof": "外出中",
    "workingelsewhere": "他の場所で作業中",
}
_曜日名 = "月火水木金土日"


def _正規化(値) -> str:
    return str(値 or "").strip().lower()


def 種別の表示語(show_as: str) -> str:
    """`tentative`→仮、`busy`→予約済み、`oof`→外出中、`workingElsewhere`→他の場所で作業中、それ以外→不明。"""
    return _種別の表示語.get(_正規化(show_as), "不明")


# ---------------------------------------------------------------------------
# 取得できなかったときの理由の文(requirements.md#開催者の予定のみ重なる枠の提示 [6])
# ---------------------------------------------------------------------------


def 理由_待ち上限(上限秒: int) -> str:
    上限 = f"{上限秒 // 60}分" if 上限秒 % 60 == 0 else f"{上限秒}秒"
    return f"待ち上限({上限})を超えました"


def 理由_フロー失敗(失敗理由: str) -> str:
    return f"開催者予定フローが失敗を返しました: {失敗理由}"


def 理由_書き出し失敗(エラー: str) -> str:
    return f"開催者の予定の依頼を書き出せませんでした: {エラー}"


# ---------------------------------------------------------------------------
# 依頼(design.md#開催者の予定の依頼ファイルの区分)
# ---------------------------------------------------------------------------


@dataclass
class 書き出し結果:
    ok: bool
    path: Optional[str] = None
    既にあった: bool = False
    error: str = ""


def _utc文字列(dt: datetime) -> str:
    return dt.astimezone(timeutil.UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def 依頼を組み立てる(依頼id: str, 枠一覧: Sequence[枠]) -> Optional[dict]:
    """開催者のみ不在の枠の最小の開始から最大の終了までを範囲にした依頼。枠が無ければNone。"""
    if not 枠一覧:
        return None
    return {
        "requestId": 依頼id,
        "rangeStart": _utc文字列(min(w.開始 for w in 枠一覧)),
        "rangeEnd": _utc文字列(max(w.終了 for w in 枠一覧)),
    }


def 依頼を書き出す(設定値: 設定, 依頼id: str, 枠一覧: Sequence[枠]) -> 書き出し結果:
    """開催者の予定の依頼フォルダへ `organizer-events-request-<依頼ID>.json` として書く。

    同じ依頼IDの依頼が既にあれば書き直さない(取得は依頼1件につき1回)。書き出しに失敗しても例外を投げない。
    """
    依頼 = 依頼を組み立てる(依頼id, 枠一覧)
    if 依頼 is None:
        return 書き出し結果(ok=False, error="開催者の予定のみ重なる枠が無いため依頼を書き出しません")
    path = ledger.開催者の予定の依頼ファイル(設定値, 依頼id)
    if path.is_file():
        return 書き出し結果(ok=True, path=str(path), 既にあった=True)
    try:
        ledger.write_json(path, 依頼)
    except OSError as e:
        return 書き出し結果(ok=False, path=str(path), error=理由_書き出し失敗(str(e)))
    logger.info(
        "開催者の予定の依頼を書き出しました: 依頼ID=%s 範囲=%s〜%s 対象の枠=%d件",
        依頼id, 依頼["rangeStart"], 依頼["rangeEnd"], len(枠一覧),
    )
    return 書き出し結果(ok=True, path=str(path))


# ---------------------------------------------------------------------------
# 予定ファイルの読み取り(design.md#開催者の予定ファイルの区分)
# ---------------------------------------------------------------------------


@dataclass
class 予定:
    件名: str
    #: `showAs` を前後の空白を除き小文字に揃えた値。知らない値はそのまま持ち、表示語は「不明」になる
    種別: str
    非公開: bool
    開始: datetime  # 世界標準時
    終了: datetime  # 世界標準時

    @property
    def 表示する件名(self) -> str:
        return 非公開の件名 if self.非公開 else self.件名


@dataclass
class 予定の読み取り:
    依頼id: str
    予定一覧: List[予定]
    失敗理由: str

    @property
    def 失敗(self) -> bool:
        return bool(self.失敗理由)


def _予定を読む(項目: dict) -> 予定:
    開始 = timeutil.parse_datetime(((項目.get("start") or {}).get("dateTime")))
    終了 = timeutil.parse_datetime(((項目.get("end") or {}).get("dateTime")))
    return 予定(
        件名=str(項目.get("subject") or "") or "(件名なし)",
        種別=_正規化(項目.get("showAs")),
        非公開=_正規化(項目.get("sensitivity")) in _非公開の値,
        開始=開始.astimezone(timeutil.UTC),
        終了=終了.astimezone(timeutil.UTC),
    )


def 読む(内容, 依頼id: str) -> 予定の読み取り:
    """開催者の予定ファイルから予定の一覧を取り出す。

    `requestId` が依頼IDと一致しないファイルは受け付けない。`error` が空でなければ失敗として返す。
    開始か終了が読めない予定は飛ばす(件数だけログに残す)。本文・出席者・場所は読まない。
    """
    if not isinstance(内容, dict):
        return 予定の読み取り(依頼id, [], "開催者の予定ファイルの形式が違います")
    実際 = str(内容.get("requestId") or "")
    if 実際 != 依頼id:
        return 予定の読み取り(依頼id, [], f"開催者の予定ファイルの依頼IDが一致しません(期待: {依頼id}、実際: {実際 or '(なし)'})")
    失敗理由 = 内容.get("error") or ""
    if not isinstance(失敗理由, str):
        失敗理由 = str(失敗理由)
    if 失敗理由:
        return 予定の読み取り(依頼id, [], 失敗理由)
    一覧 = 内容.get("events")
    if not isinstance(一覧, list):
        return 予定の読み取り(依頼id, [], "開催者の予定ファイルの events が配列ではありません")
    予定一覧: List[予定] = []
    飛ばした = 0
    for 項目 in 一覧:
        if not isinstance(項目, dict):
            飛ばした += 1
            continue
        try:
            予定一覧.append(_予定を読む(項目))
        except (ValueError, TypeError, AttributeError):
            飛ばした += 1
    if 飛ばした:
        logger.warning("開催者の予定の読み取り: 依頼ID=%s 読めない予定を飛ばしました=%d件", 依頼id, 飛ばした)
    return 予定の読み取り(依頼id, 予定一覧, "")


# ---------------------------------------------------------------------------
# 突き合わせと表示(design.md#開催者の予定のみ重なる枠の提示 手順4〜7)
# ---------------------------------------------------------------------------


def 重なる予定(w: 枠, 予定一覧: Sequence[予定]) -> List[予定]:
    """世界標準時で `予定.開始 < 枠.終了 かつ 予定.終了 > 枠.開始` の予定を開始時刻順に返す。`free` の予定は除く。"""
    枠開始 = w.開始.astimezone(timeutil.UTC)
    枠終了 = w.終了.astimezone(timeutil.UTC)
    重なり = [p for p in 予定一覧 if p.種別 != 空き and p.開始 < 枠終了 and p.終了 > 枠開始]
    return sorted(重なり, key=lambda p: (p.開始, p.終了))


def 予定の行(p: 予定, w: 枠) -> str:
    """「<件名> HH:MM〜HH:MM(<種別>)」。枠の日と異なる日付にかかる予定は日付も添える。時刻は日本時間。"""
    開始 = timeutil.to_jst(p.開始)
    終了 = timeutil.to_jst(p.終了)
    枠の日 = w.開始.date()
    if 開始.date() == 枠の日 and 終了.date() == 枠の日:
        時刻 = f"{開始:%H:%M}〜{終了:%H:%M}"
    else:
        時刻 = f"{開始:%m/%d %H:%M}〜{終了:%m/%d %H:%M}"
    return f"{p.表示する件名} {時刻}({種別の表示語(p.種別)})"


def 枠の表示行(w: 枠, 予定一覧: Optional[Sequence[予定]], 理由: str = "") -> List[str]:
    """枠1つぶんのカード・通知に載せる行。取得できなかった場合(`予定一覧` が None)は理由の行1つにする。"""
    if 予定一覧 is None:
        return [f"開催者の予定を取得できませんでした({理由})"]
    重なり = 重なる予定(w, 予定一覧)
    if not 重なり:
        return [f"重なる予定は見つかりませんでした(空き状況: {種別の表示語(w.開催者空き)})"]
    return [予定の行(p, w) for p in 重なり]


def 通知の行(w: 枠, 行一覧: Sequence[str]) -> str:
    """通知文とチャットに出す「・MM/DD(曜) HH:MM〜HH:MM — <行>、<行>」。"""
    return f"・{w.開始:%m/%d}({_曜日名[w.開始.weekday()]}) {w.開始:%H:%M}〜{w.終了:%H:%M} — " + "、".join(行一覧)
