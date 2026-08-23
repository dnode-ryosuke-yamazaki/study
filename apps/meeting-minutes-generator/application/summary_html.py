"""議事録Markdownからの要約部分の抽出と、Teams投稿用HTMLへの変換。

Teamsはメッセージ本文をHTMLとして解釈し、プレーンな改行を無視する
(daily-report-to-teamsで実機確認済み)。そのため見出し・箇条書きをHTMLタグへ
変換して書き出す。

対応する仕様: requirements.md#Teamsへの共有 / design.md#投稿用ファイルの書き出し
"""

from __future__ import annotations

import html as _html

#: Teamsに投稿する見出し。議論の経緯、未決事項・次回議題は投稿に含めない。
#: 仕様: requirements.md#Teamsへの共有 [1]
投稿する見出し = ("会議メタ情報", "要約", "決定事項", "TODO")

#: 箇条書きの入れ子1段に相当するインデント幅。
_インデント幅 = 2


def 要約部分を抽出する(議事録: str) -> str:
    """議事録Markdownから、投稿する見出しのセクションだけを抜き出す。

    セクションの区切りは `##` の見出し行。タイトル(`#`)は含めない(投稿本文の
    先頭は会議メタ情報から始める)。
    """
    抜粋の行: list[str] = []
    採用中 = False
    for 行 in 議事録.splitlines():
        文字列 = 行.strip()
        if 文字列.startswith("##"):
            見出し名 = 文字列.lstrip("#").strip()
            採用中 = 見出し名 in 投稿する見出し
        elif 文字列.startswith("#"):
            採用中 = False
        if 採用中:
            抜粋の行.append(行)
    return "\n".join(抜粋の行).strip() + "\n"


def htmlへ変換する(抜粋: str, 議事録ファイル名: str) -> str:
    """要約部分のMarkdownをTeams向けHTMLに変換し、全文の案内を末尾に添える。

    本文はすべてエスケープする(トランスクリプト由来の文字列がタグとして解釈
    されると投稿の体裁が壊れるため。design.md#セキュリティ)。
    仕様: requirements.md#Teamsへの共有 [1] [2]
    """
    部品: list[str] = []
    開いているリストの深さ = 0

    def リストを閉じる(深さまで: int) -> None:
        nonlocal 開いているリストの深さ
        while 開いているリストの深さ > 深さまで:
            部品.append("</ul>")
            開いているリストの深さ -= 1

    for 行 in 抜粋.splitlines():
        文字列 = 行.strip()
        if not 文字列:
            continue
        if 文字列.startswith("#"):
            リストを閉じる(0)
            部品.append(f"<h3>{_html.escape(文字列.lstrip('#').strip())}</h3>")
        elif 文字列.startswith(("- ", "* ")):
            インデント = len(行) - len(行.lstrip(" "))
            深さ = インデント // _インデント幅 + 1
            リストを閉じる(深さ)
            while 開いているリストの深さ < 深さ:
                部品.append("<ul>")
                開いているリストの深さ += 1
            部品.append(f"<li>{_html.escape(文字列[2:].strip())}</li>")
        else:
            リストを閉じる(0)
            部品.append(f"<p>{_html.escape(文字列)}</p>")

    リストを閉じる(0)
    部品.append(
        "<p>全文はOneDriveの議事録フォルダの"
        f"「{_html.escape(議事録ファイル名)}」を参照してください。</p>"
    )
    return "\n".join(部品)
