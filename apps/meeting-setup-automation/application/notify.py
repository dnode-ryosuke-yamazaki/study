"""通知文の組み立てと、通知フォルダへの書き出し。

Teams通知は通知フォルダ(`auto/teamsNotice/meetingSetting/`)へのファイル書き出しで行い、
同フォルダを監視する会議設定通知フローが投稿する(requirements.md#通知 [1])。HTTPで直接
投稿する経路は持たない(同 [2]。組織のDLPポリシーでブロックされる)。書き出しに失敗しても
例外にせず、チャットへの表示で処理を続ける(同 [3])。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import timeutil
from config import 設定
from result import 作成結果

_曜日名 = "月火水木金土日"

手動有効化の注意 = (
    "録画の自動開始とファシリテーター機能は自動では有効化できません。"
    "会議オプション画面の直リンクを開いて、手動でオンにしてください。"
)
直リンクなしの手順 = (
    "会議本文から会議オプション画面の直リンクを取り出せませんでした(会議は作成されています)。"
    "Teamsのカレンダーでこの会議を開き、「会議のオプション」から録画の自動開始とファシリテーターをオンにしてください。"
)


@dataclass
class 代替案の要約:
    代替案1件数: int
    代替案1の仮の予定: List[str]
    代替案2件数: Optional[int]  # 作らなかった・得られなかった場合はNone
    代替案2の条件: str
    代替案2が得られなかった理由: str
    打ち切りの可能性: bool
    広げなかった項目: List[str] = field(default_factory=list)


@dataclass
class 書き出し結果:
    ok: bool
    path: Optional[str] = None
    error: str = ""


def _日時範囲(開始: Optional[datetime], 終了: Optional[datetime]) -> str:
    if not 開始 or not 終了:
        return "(日時不明)"
    return f"{開始:%Y-%m-%d}({_曜日名[開始.weekday()]}) {開始:%H:%M}〜{終了:%H:%M}"


def 選択画面の通知文(
    件名: str, 候補件数: int, url: Optional[str], htmlパス: Optional[str], 代替案: Optional[代替案の要約] = None
) -> str:
    行 = ["【会議候補が出そろいました】", f"件名: {件名}", f"候補: {候補件数}件"]
    if 代替案 is not None:
        行.append("既定の条件では候補が0件だったため、2つの代替案の候補を示します。")
        行.append(f"- 代替案1(仮の予定を含める): {代替案.代替案1件数}件")
        for s in 代替案.代替案1の仮の予定:
            行.append(f"    {s}")
        if 代替案.打ち切りの可能性:
            行.append("    ※ 探索の応答が要求した件数で打ち切られている可能性があります(打ち切られた集合の外の枠は代替案1に現れません)")
        if 代替案.代替案2件数 is not None:
            行.append(f"- 代替案2(期間と時間帯を広げる): {代替案.代替案2件数}件({代替案.代替案2の条件})")
        elif 代替案.代替案2が得られなかった理由:
            行.append(f"- 代替案2(期間と時間帯を広げる): 得られませんでした。{代替案.代替案2が得られなかった理由}")
        else:
            項目 = "・".join(代替案.広げなかった項目) or "期間・時間帯"
            行.append(f"- 代替案2は作りませんでした({項目}を依頼時に指定されていたため広げていません)")
    if url:
        行.append(f"選択画面: {url}")
        行.append("開けない場合は同期の完了を数十秒待ってから再読込してください。")
    else:
        行.append(f"選択画面(ローカル): {htmlパス}")
        行.append("ビューアURLの設定が無いためファイルパスを示しています。")
    行.append("候補を1つ選んで「選択結果をコピー」し、コピーした1行をチャットに貼ってください。")
    return "\n".join(行)


def 完了の通知文(r: 作成結果, 直リンク: Optional[str]) -> str:
    行 = [
        "【Teams会議を作成しました】",
        f"件名: {r.件名}",
        f"日時: {_日時範囲(r.開始, r.終了)}",
        "出席者: " + (", ".join(r.出席者) if r.出席者 else "(なし)"),
        f"参加URL: {r.参加url or '(取得できませんでした)'}",
    ]
    if 直リンク:
        行.append(f"会議オプション画面: {直リンク}")
    else:
        行.append(直リンクなしの手順)
    行.append(手動有効化の注意)
    if r.開くリンク:
        行.append(f"予定を開く: {r.開くリンク}")
    return "\n".join(行)


def 書き出す(設定値: 設定, 本文: str, 今: Optional[datetime] = None) -> 書き出し結果:
    """通知フォルダへ `meeting-<書き出し時刻>.txt` の一意な名前で書く。失敗しても例外を投げない。"""
    今 = 今 or timeutil.now_jst()
    基本 = f"meeting-{今:%Y%m%d-%H%M%S}"
    try:
        設定値.通知フォルダ.mkdir(parents=True, exist_ok=True)
        path = 設定値.通知フォルダ / f"{基本}.txt"
        n = 1
        while path.exists():
            n += 1
            path = 設定値.通知フォルダ / f"{基本}-{n}.txt"
        path.write_text(本文, encoding="utf-8")
    except OSError as e:
        return 書き出し結果(ok=False, error=f"通知ファイルを書き出せません: {e}")
    return 書き出し結果(ok=True, path=str(path))
