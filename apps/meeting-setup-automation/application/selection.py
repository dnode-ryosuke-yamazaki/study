"""貼られた選択結果の読み取り・候補ファイルとの突き合わせ・選択結果ファイルの書き出し、アジェンダの整形。

貼られた内容をそのまま信じず、候補ファイルの枠と時点として突き合わせてから書き出す
(design.md#セキュリティ)。候補番号は表示用の連番なので突き合わせには使わない。選択結果は
1つの再試行番号につき1回しか書き出さず、作成に成功した依頼IDには書き出さない
(design.md#エラーハンドリング「二重の会議作成を防ぐ」)。

選択結果ファイルの形(作成フローがこれだけで会議を作れる内容。台帳の日時はオフセット付きで書き、
フロー側で末尾のオフセットを落として `timeZone: Tokyo Standard Time` と組み合わせる。
出席者はGraphの出席者の形で書き、フロー側で配列を組み替えずに渡せるようにする):
    {"requestId": "...", "retry": 0,
     "meeting": {"subject": ..., "start": "2026-09-10T10:00:00+09:00", "end": "2026-09-10T11:00:00+09:00",
                 "bodyHtml": "<h3>アジェンダ</h3>...", "attendees": [{"emailAddress": {...}, "type": "required"}],
                 "isOnlineMeeting": true, "onlineMeetingProvider": "teamsForBusiness"}}
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import candidates
import ledger
import progress
import timeutil
from config import 設定
from select_html import 目印の語

タイムゾーン名 = "Tokyo Standard Time"

書き出せる = "書き出せる"
選択結果あり = "選択結果あり"
作成済み = "作成済み"
作成失敗 = "作成失敗"

_行 = re.compile(
    re.escape(目印の語)
    + r"\s+(?P<id>\S+)\s+a(?P<attempt>\d+)\s+#(?P<number>\d+)\s+(?P<start>\S+)\s+(?P<end>\S+)"
)
_箇条書き = re.compile(r"^\s*(?:[-*・●○]|\d+[.)、])\s*(.*)$")


@dataclass
class 選択行:
    依頼id: str
    試行番号: int
    候補番号: int
    開始: datetime
    終了: datetime


@dataclass
class 突き合わせ結果:
    ok: bool
    枠: Optional[candidates.枠] = None
    error: str = ""


@dataclass
class 書き出し判定:
    種別: str
    再試行番号: int = 0
    失敗理由: str = ""
    作成結果: Optional[dict] = None


@dataclass
class 書き出し結果:
    ok: bool
    path: Optional[str] = None
    error: str = ""
    再試行番号: int = 0


def 読み取る(text: Optional[str]) -> Optional[選択行]:
    """貼られた文字列から選択結果の1行を読み取る。目印の語を起点にし、読み取れなければNone。"""
    if not text:
        return None
    m = _行.search(text)
    if not m:
        return None
    try:
        return 選択行(
            依頼id=m.group("id"),
            試行番号=int(m.group("attempt")),
            候補番号=int(m.group("number")),
            開始=timeutil.to_jst(timeutil.parse_datetime(m.group("start"))),
            終了=timeutil.to_jst(timeutil.parse_datetime(m.group("end"))),
        )
    except ValueError:
        return None


def 突き合わせる(設定値: 設定, 行: 選択行) -> 突き合わせ結果:
    """貼られた試行番号の候補ファイルを開き、開始・終了が一致する枠が1つあることを確かめる(時点で比較)。"""
    内容 = ledger.read_json(ledger.候補ファイル(設定値, 行.依頼id, 行.試行番号))
    if 内容 is None:
        return 突き合わせ結果(ok=False, error=f"依頼ID {行.依頼id} の試行番号 {行.試行番号} の候補ファイルが見つかりません")
    読み = candidates.読む(内容)
    一致 = [w for w in 読み.枠一覧 if w.開始 == 行.開始 and w.終了 == 行.終了]
    if len(一致) != 1:
        return 突き合わせ結果(
            ok=False,
            error=f"貼られた枠({timeutil.format_jst(行.開始)}〜{timeutil.format_jst(行.終了)})と一致する候補が候補ファイルにありません。"
            "選択画面でコピーした1行をそのまま貼ってください",
        )
    return 突き合わせ結果(ok=True, 枠=一致[0])


def アジェンダを整形(原文: Optional[str]) -> str:
    """アジェンダの原文を見出しと箇条書きのHTMLにする。空なら無いことが分かる本文にする。"""
    行一覧 = [l.rstrip() for l in (原文 or "").splitlines()]
    行一覧 = [l for l in 行一覧 if l.strip()]
    if not 行一覧:
        return "<h3>アジェンダ</h3><p>アジェンダは未定です(依頼時に指定がありませんでした)</p>"
    部分: List[str] = ["<h3>アジェンダ</h3>"]
    箇条: List[str] = []

    def flush():
        if 箇条:
            部分.append("<ul>" + "".join(f"<li>{s}</li>" for s in 箇条) + "</ul>")
            箇条.clear()

    for l in 行一覧:
        m = _箇条書き.match(l)
        if m:
            箇条.append(html.escape(m.group(1).strip()))
        else:
            flush()
            部分.append(f"<p>{html.escape(l.strip())}</p>")
    flush()
    return "".join(部分)


def 選択結果を組み立てる(依頼: dict, 枠: candidates.枠, 再試行番号: int = 0) -> dict:
    """選択結果ファイルの内容。物理会議室(リソース)は含めない。"""
    meeting = 依頼["meeting"]
    return {
        "requestId": 依頼["requestId"],
        "retry": 再試行番号,
        "meeting": {
            "subject": meeting["subject"],
            "start": timeutil.format_jst(枠.開始),
            "end": timeutil.format_jst(枠.終了),
            "timeZone": タイムゾーン名,
            "bodyHtml": アジェンダを整形(meeting.get("agenda")),
            "attendees": [dict(a, type="required") for a in meeting["attendees"]],
            "isOnlineMeeting": True,
            "onlineMeetingProvider": "teamsForBusiness",
        },
    }


def 選択した枠(選択結果: Optional[dict]) -> str:
    """選択結果ファイルから枠の表示(開始〜終了)を作る。読めなければ空文字。"""
    m = (選択結果 or {}).get("meeting") or {}
    if m.get("start") and m.get("end"):
        return f"{m['start']} 〜 {m['end']}"
    return ""


def 書き出せるか(設定値: 設定, 依頼id: str) -> 書き出し判定:
    """その依頼IDに選択結果を新しく書き出してよいかを、台帳の状態から判定する。"""
    状態 = progress.判定(設定値, 依頼id)
    if 状態.状態 == progress.作成済み:
        return 書き出し判定(種別=作成済み, 再試行番号=状態.再試行番号, 作成結果=状態.作成結果)
    if 状態.状態 == progress.作成失敗:
        return 書き出し判定(種別=作成失敗, 再試行番号=状態.再試行番号, 失敗理由=状態.失敗理由, 作成結果=状態.作成結果)
    if 状態.状態 == progress.選択済み:
        return 書き出し判定(種別=選択結果あり, 再試行番号=状態.再試行番号)
    return 書き出し判定(種別=書き出せる)


def 書き出す(設定値: 設定, 選択結果: dict) -> 書き出し結果:
    再試行番号 = int(選択結果.get("retry") or 0)
    path = ledger.選択結果ファイル(設定値, 選択結果["requestId"], 再試行番号)
    try:
        ledger.write_json(path, 選択結果)
    except OSError as e:
        return 書き出し結果(ok=False, path=str(path), error=f"選択結果ファイルを書き出せません: {e}", 再試行番号=再試行番号)
    return 書き出し結果(ok=True, path=str(path), 再試行番号=再試行番号)


def 再試行を書き出す(設定値: 設定, 依頼id: str) -> 書き出し結果:
    """失敗した作成結果がある依頼に限り、再試行番号を1つ増やした選択結果を前回と同じ内容で書き出す。"""
    判定 = 書き出せるか(設定値, 依頼id)
    if 判定.種別 != 作成失敗:
        return 書き出し結果(ok=False, error=f"依頼ID {依頼id} には失敗した作成結果が無いため、再試行は行いません(状態: {判定.種別})")
    前回 = ledger.read_json(ledger.選択結果ファイル(設定値, 依頼id, 判定.再試行番号))
    if 前回 is None:
        return 書き出し結果(ok=False, error=f"依頼ID {依頼id} の前回の選択結果を読めません")
    次 = dict(前回, retry=判定.再試行番号 + 1)  # 内容は前回と同じ。再試行番号だけを増やす
    return 書き出す(設定値, 次)
