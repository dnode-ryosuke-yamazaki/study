"""依頼IDの生成、依頼の組み立て・バリデーション・書き出し、候補が0件のときの代替案2の依頼。

依頼ファイルは次の区分を持つ(design.md#依頼ファイルの区分)。

- 依頼の識別(`requestId`・`attempt`)
- 会議の内容(`meeting`: 件名・所要時間・必須出席者・アジェンダの原文)
- 探索の指示(`search`: フローが読む。期間・出席可能率の下限・返してほしい最大件数)
- 絞り込みの条件(`filter`: Skillだけが読む。時間帯・対象曜日・全員空き・提示する上限件数)
- 開催者が指定した項目(`specified`: Skillだけが読む。代替案2で広げてよい項目を決める)

探索条件の判断はすべてSkillに置き、フローには「渡された条件で探す」だけをさせる
(design.md 設計判断2)。
"""

from __future__ import annotations

import copy
import secrets
import string
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import List, Optional, Sequence

import candidates
import ledger
import timeutil
from config import 設定

#: 全員空きを求めない指示を受けたときの出席可能率の下限。100のままだと一部不在の枠が
#: フローから返らない(requirements.md#候補探索の既定条件 [3]、design.md#依頼ファイルの区分)。
一部不在を許す出席可能率下限 = 50

#: 開催者が指定した項目の名前(依頼ファイルの `specified` に書く値)
指定項目_期間 = "period"
指定項目_時間帯 = "timeWindow"
指定項目_候補件数 = "maxResults"
指定項目_曜日 = "weekdays"
指定項目_全員空き = "allFree"


@dataclass
class 依頼条件:
    """チャットで受け取った依頼。探索条件はNoneなら「指定なし」(既定値を使う)。"""

    件名: str
    参加者: List[dict]  # {"name": ..., "email": ...}
    所要時間分: int
    アジェンダ: str = ""
    期間開始: Optional[date] = None
    期間終了: Optional[date] = None
    時間帯開始: Optional[time] = None
    時間帯終了: Optional[time] = None
    候補件数: Optional[int] = None
    対象曜日: Optional[Sequence[int]] = None
    全員空き: Optional[bool] = None


@dataclass
class 書き出し結果:
    ok: bool
    path: Optional[str] = None
    error: str = ""


def 依頼idを生成(今: Optional[datetime] = None) -> str:
    """「年月日-時分秒-乱数4文字」。同じ秒に複数生成しても乱数で重ならない(36^4=約168万通り)。"""
    今 = 今 or timeutil.now_jst()
    文字 = string.digits + string.ascii_lowercase
    乱数 = "".join(secrets.choice(文字) for _ in range(4))
    return f"{今:%Y%m%d-%H%M%S}-{乱数}"


def _期間(条件: 依頼条件, 設定値: 設定, 今日: date):
    開始 = 条件.期間開始 if 条件.期間開始 is not None else 今日
    終了 = 条件.期間終了 if 条件.期間終了 is not None else 今日 + timedelta(days=設定値.既定の探索期間日数)
    return 開始, 終了


def _時間帯(条件: 依頼条件, 設定値: 設定):
    開始 = 条件.時間帯開始 if 条件.時間帯開始 is not None else 設定値.既定の時間帯開始
    終了 = 条件.時間帯終了 if 条件.時間帯終了 is not None else 設定値.既定の時間帯終了
    return 開始, 終了


def _分(t: time) -> int:
    return t.hour * 60 + t.minute


def 指定した項目(条件: 依頼条件) -> List[str]:
    """開催者が明示的に指定した項目の一覧。既定値と同じ値でも指定として扱う。"""
    一覧 = []
    if 条件.期間開始 is not None or 条件.期間終了 is not None:
        一覧.append(指定項目_期間)
    if 条件.時間帯開始 is not None or 条件.時間帯終了 is not None:
        一覧.append(指定項目_時間帯)
    if 条件.候補件数 is not None:
        一覧.append(指定項目_候補件数)
    if 条件.対象曜日 is not None:
        一覧.append(指定項目_曜日)
    if 条件.全員空き is not None:
        一覧.append(指定項目_全員空き)
    return 一覧


def 検証(条件: 依頼条件, 設定値: 設定, 今日: date) -> List[str]:
    """受け付け条件(requirements.md#依頼内容の受け付け条件 [1]〜[5])を確かめ、満たしていない項目を返す。

    参加者の人数では弾かない([8])。アジェンダは任意([6])。
    """
    不備: List[str] = []
    開始, 終了 = _期間(条件, 設定値, 今日)
    帯開始, 帯終了 = _時間帯(条件, 設定値)
    帯の長さ分 = _分(帯終了) - _分(帯開始)
    候補件数 = 条件.候補件数 if 条件.候補件数 is not None else 設定値.既定の候補件数

    if 条件.所要時間分 < 設定値.所要時間の下限分:
        不備.append(f"所要時間は{設定値.所要時間の下限分}分以上にしてください(指定: {条件.所要時間分}分)")
    elif 帯の長さ分 > 0 and 条件.所要時間分 > 帯の長さ分:
        不備.append(
            f"所要時間({条件.所要時間分}分)が探索する時間帯の長さ({帯の長さ分}分)に収まりません"
        )
    if 開始 > 終了:
        不備.append(f"探索期間の開始日({開始})が終了日({終了})より後になっています")
    if 開始 < 今日:
        不備.append(f"探索期間の開始日({開始})が当日({今日})より前になっています")
    上限 = 今日 + timedelta(days=設定値.探索期間の上限日数)
    if 終了 > 上限:
        不備.append(f"探索期間の終了日({終了})は当日から3週間以内({上限}まで)にしてください")
    if 帯の長さ分 <= 0:
        # 差が所要時間未満の場合([4]後半)は所要時間の側([1])で報告済みなので重ねて出さない
        不備.append(f"時間帯の開始({帯開始:%H:%M})が終了({帯終了:%H:%M})以降になっています")
    if 候補件数 < 1:
        不備.append(f"候補件数は1件以上にしてください(指定: {候補件数})")
    return 不備


def 組み立て(条件: 依頼条件, 設定値: 設定, 今日: date, 依頼id: str, 試行番号: int = 1) -> dict:
    """依頼ファイルの内容を組み立てる。日時は日本時間のオフセット付きで書く。"""
    開始, 終了 = _期間(条件, 設定値, 今日)
    帯開始, 帯終了 = _時間帯(条件, 設定値)
    全員空き = True if 条件.全員空き is None else bool(条件.全員空き)
    曜日 = list(条件.対象曜日) if 条件.対象曜日 is not None else list(設定値.既定の対象曜日)
    候補件数 = 条件.候補件数 if 条件.候補件数 is not None else 設定値.既定の候補件数
    return {
        "requestId": 依頼id,
        "attempt": 試行番号,
        "meeting": {
            "subject": 条件.件名,
            "durationMinutes": 条件.所要時間分,
            # 探索フローが「会議の時間を検索 (V2)」の必須出席者に渡す形(メールアドレスの配列)
            "requiredAttendees": [p["email"] for p in 条件.参加者],
            # 選択結果へ引き継ぐ形(Graphの出席者の形。作成フローが配列を組み替えずに使える)
            "attendees": [
                {"emailAddress": {"address": p["email"], "name": p["name"]}, "type": "required"}
                for p in 条件.参加者
            ],
            "agenda": 条件.アジェンダ or "",
        },
        "search": {
            "start": timeutil.format_jst(datetime.combine(開始, time.min, tzinfo=timeutil.JST)),
            "end": timeutil.format_jst(datetime.combine(終了, time(23, 59, 59), tzinfo=timeutil.JST)),
            "minimumAttendeePercentage": (
                設定値.既定の出席可能率下限 if 全員空き else 一部不在を許す出席可能率下限
            ),
            "maxCandidates": 設定値.フローに返させる最大件数,
        },
        "filter": {
            "timeWindowStart": 帯開始.strftime("%H:%M"),
            "timeWindowEnd": 帯終了.strftime("%H:%M"),
            "weekdays": 曜日,
            "requireAllFree": 全員空き,
            "maxResults": 候補件数,
        },
        "specified": 指定した項目(条件),
    }


def 書き出す(設定値: 設定, 依頼: dict) -> 書き出し結果:
    """依頼フォルダへ `request-<依頼ID>-a<試行番号>.json` として書く。失敗しても例外を投げない。"""
    path = ledger.依頼ファイル(設定値, 依頼["requestId"], 依頼["attempt"])
    try:
        ledger.write_json(path, 依頼)
    except OSError as e:
        return 書き出し結果(ok=False, path=str(path), error=f"依頼ファイルを書き出せません: {e}")
    return 書き出し結果(ok=True, path=str(path))


# ---------------------------------------------------------------------------
# 候補が0件のときの代替案(requirements.md#候補が0件のときの代替案の提示)
# ---------------------------------------------------------------------------


@dataclass
class 代替案1結果:
    """同じ候補ファイルを仮の予定を空きとみなして絞り直した結果。探索の依頼は出し直さない。"""

    採用: List[candidates.枠]
    打ち切りの可能性: bool
    絞り込み: candidates.絞り込み結果


def 代替案2を作れるか(依頼: dict) -> bool:
    """開催者が探索期間と時間帯の両方を明示的に指定していれば、広げられる項目が無いので作らない。"""
    指定 = set(依頼.get("specified") or [])
    return not ({指定項目_期間, 指定項目_時間帯} <= 指定)


def 広げなかった項目(依頼: dict) -> List[str]:
    """開催者の指定のため代替案2で広げなかった項目(表示用)。"""
    指定 = set(依頼.get("specified") or [])
    一覧 = []
    if 指定項目_期間 in 指定:
        一覧.append("期間")
    if 指定項目_時間帯 in 指定:
        一覧.append("時間帯")
    return 一覧


def 代替案2の依頼を組み立てる(依頼: dict, 設定値: 設定, 今日: date) -> Optional[dict]:
    """期間を当日から3週間、時間帯を9時30分から18時30分に広げた試行番号2の依頼。

    開催者が明示的に指定した項目は広げない。対象曜日・全員空き・候補件数・会議の内容は
    元の依頼のまま引き継ぐ。広げられる項目が1つも無ければNone。
    """
    if not 代替案2を作れるか(依頼):
        return None
    指定 = set(依頼.get("specified") or [])
    代替 = copy.deepcopy(依頼)
    代替["attempt"] = 2
    if 指定項目_期間 not in 指定:
        終了 = 今日 + timedelta(days=設定値.代替案の探索期間日数)
        代替["search"]["start"] = timeutil.format_jst(datetime.combine(今日, time.min, tzinfo=timeutil.JST))
        代替["search"]["end"] = timeutil.format_jst(datetime.combine(終了, time(23, 59, 59), tzinfo=timeutil.JST))
    if 指定項目_時間帯 not in 指定:
        代替["filter"]["timeWindowStart"] = 設定値.代替案の時間帯開始.strftime("%H:%M")
        代替["filter"]["timeWindowEnd"] = 設定値.代替案の時間帯終了.strftime("%H:%M")
    return 代替


def 代替案1を組み立てる(
    読み: candidates.候補の読み取り,
    条件: candidates.絞り込み条件,
    要求件数: int,
) -> 代替案1結果:
    """同じ候補ファイルを仮の予定を空きとみなす条件で絞り直す。

    代替案1が0件で受け取った枠が要求件数と同数なら、応答が件数で打ち切られている可能性を
    添える([7])。
    """
    絞り込み = candidates.絞り込む(読み, 条件, 仮を空きとみなす=True)
    打ち切り = not 絞り込み.採用 and 読み.枠一覧 and len(読み.枠一覧) == 要求件数
    return 代替案1結果(採用=絞り込み.採用, 打ち切りの可能性=bool(打ち切り), 絞り込み=絞り込み)


def 条件の要約(依頼: dict) -> str:
    """依頼ファイルの探索の指示と絞り込みの条件を1行にする(選択画面・通知・チャット用)。"""
    s = 依頼["search"]
    f = 依頼["filter"]
    曜日名 = "月火水木金土日"
    曜日 = "".join(曜日名[int(w)] for w in f["weekdays"])
    空き = "全員空きのみ" if f["requireAllFree"] else "一部不在の枠も含む"
    return (
        f"期間 {s['start'][:10]}〜{s['end'][:10]}、時間帯 {f['timeWindowStart']}〜{f['timeWindowEnd']}、"
        f"曜日 {曜日}、{空き}"
    )


def 試した条件(元の依頼: dict, 代替案2の依頼: Optional[dict]) -> List[str]:
    """両方の代替案とも0件のときに開催者へ報告する、試した条件の一覧([6])。"""
    一覧 = [
        f"既定の条件: {条件の要約(元の依頼)}(仮の予定は空きとみなさない)",
        "代替案1: 同じ条件で仮の予定を空きとみなす",
    ]
    if 代替案2の依頼 is not None:
        一覧.append(f"代替案2: {条件の要約(代替案2の依頼)}(仮の予定は空きとみなさない)")
    return 一覧
