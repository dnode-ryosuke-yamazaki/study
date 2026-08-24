"""会議の性質(デイリー系か・実尺)の判定と、そこから導く見出し構成・要約の上限。

議事録の構成は会議種別で変わる。**「claudeに指示する見出し」「生成結果を検証する
見出し」「Teamsに投稿する見出し」の3つが、必ずこの1つの判定結果から導かれる**
ようにしている。3つがずれると、生成した議事録が毎回検証NGになって再試行上限で
対象外化する(検証と指示のずれ)か、投稿から見出しが丸ごと落ちる(投稿とのずれ)。

対応する仕様: requirements.md#会議種別による構成の切り替え /
requirements.md#議事録の記載内容 [6][7] / design.md#議事録の生成
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

#: 通常の会議の必須見出し。仕様: requirements.md#議事録の生成 [2]
通常の必須見出し = (
    "会議メタ情報",
    "要約",
    "決定事項",
    "TODO",
    "議論の経緯",
    "未決事項・次回議題",
)

#: デイリー系会議の必須見出し。進捗が主役になるため要約と決定事項の間に挟む。
#: 仕様: requirements.md#会議種別による構成の切り替え [2]
デイリーの必須見出し = (
    "会議メタ情報",
    "要約",
    "進捗",
    "決定事項",
    "TODO",
    "議論の経緯",
    "未決事項・次回議題",
)

#: Teams投稿に含めない見出し。投稿する見出しは必須見出しからこれらを除いて導く。
#: 仕様: requirements.md#Teamsへの共有 [1]
投稿しない見出し = ("議論の経緯", "未決事項・次回議題")

#: WEBVTTの表示時間のうち終了時刻。`hh:mm:ss.mmm` と `mm:ss.mmm` の両方を許す。
_終了時刻 = re.compile(r"-->\s*(\d{1,3}):(\d{2})(?::(\d{2}))?[.,](\d{1,3})")


@dataclass(frozen=True)
class 要約の上限:
    """要約の分量の上限。点数は文言のまま指示に埋め込む。"""

    点数: str
    字数: int


def 要約の上限を決める(実尺分: int | None) -> 要約の上限:
    """会議の実尺から要約の分量上限を3段階で決める。

    短い会議で上限が緩いと要約が要約にならず、長い会議で厳しすぎると要点が落ちる。
    実尺が分からない場合は最も厳しい段に倒す(投稿が読めることを優先する)。
    仕様: requirements.md#議事録の記載内容 [6] [7]
    """
    if 実尺分 is None or 実尺分 <= 30:
        return 要約の上限(点数="3〜5点", 字数=300)
    if 実尺分 <= 60:
        return 要約の上限(点数="最大7点", 字数=500)
    return 要約の上限(点数="最大10点", 字数=800)


def 会議の実尺分(トランスクリプト: str) -> int | None:
    """トランスクリプトのタイムスタンプから会議の実尺(分)を求める。

    表示時間の終了時刻の最大値を採る。タイムスタンプが1つも読めない場合はNone
    (実尺不明)を返す。仕様: requirements.md#議事録の記載内容 [7]
    """
    最大秒 = None
    for 時, 分, 秒, ミリ秒 in _終了時刻.findall(トランスクリプト):
        if 秒:
            合計 = int(時) * 3600 + int(分) * 60 + int(秒)
        else:
            # `mm:ss.mmm` 形式。WEBVTTは時の桁の省略を許す。
            合計 = int(時) * 60 + int(分)
        最大秒 = 合計 if 最大秒 is None else max(最大秒, 合計)
    return None if 最大秒 is None else 最大秒 // 60


@dataclass(frozen=True)
class 会議の性質:
    """1つの会議について、議事録の構成を決めるのに必要なことだけを持つ。"""

    デイリー系: bool
    実尺分: int | None

    @property
    def 必須見出し(self) -> tuple[str, ...]:
        """この会議の議事録に必ず立てる見出し(指示と検証の両方がこれを使う)。"""
        return デイリーの必須見出し if self.デイリー系 else 通常の必須見出し

    @property
    def 投稿する見出し(self) -> tuple[str, ...]:
        """Teams投稿に含める見出し。必須見出しから導くので追随漏れが起きない。"""
        return tuple(h for h in self.必須見出し if h not in 投稿しない見出し)

    @property
    def 要約の上限(self) -> 要約の上限:
        return 要約の上限を決める(self.実尺分)

    @property
    def 種別の名前(self) -> str:
        """ログ用の表示名。"""
        return "デイリー系" if self.デイリー系 else "通常"


def 見極める(vtt名: str, トランスクリプト: str, 判定語: Sequence[str]) -> 会議の性質:
    """VTTのファイル名と内容から会議の性質を決める。

    デイリー系かどうかは上流(teams-transcript-fetcher)が付けるファイル名の
    会議名部分で判定する。大文字小文字を区別しないのは「共通インフラDaily」の
    ように英字の表記が揺れるため。仕様: requirements.md#会議種別による構成の切り替え [1]
    """
    小文字のvtt名 = vtt名.lower()
    デイリー系 = any(語 and 語.lower() in 小文字のvtt名 for 語 in 判定語)
    return 会議の性質(デイリー系=デイリー系, 実尺分=会議の実尺分(トランスクリプト))
