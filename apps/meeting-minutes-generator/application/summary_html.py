"""議事録Markdownからの要約部分の抽出と、Teams投稿用HTMLへの変換。

Teamsはメッセージ本文をHTMLとして解釈し、プレーンな改行を無視する
(daily-report-to-teamsで実機確認済み)。そのため見出し・箇条書きをHTMLタグへ
変換して書き出す。

末尾に添える議事録全文へのリンクは、共有ストレージの**ファイルビューアで開く形式**
のURLにする。ファイルを直接指すURLはブラウザ内で表示されず必ずダウンロードになる
(sprint-review-generator / retro-check と同じ前提)。

対応する仕様: requirements.md#Teamsへの共有 / requirements.md#議事録全文へのリンク /
design.md#投稿用ファイルの書き出し
"""

from __future__ import annotations

import html as _html
from collections.abc import Sequence
from urllib.parse import quote, unquote

#: 箇条書きの入れ子1段に相当するインデント幅。
_インデント幅 = 2


def _見出しの深さ(文字列: str) -> int:
    """行頭の `#` の数を返す。見出しでなければ0。"""
    return len(文字列) - len(文字列.lstrip("#"))


def 要約部分を抽出する(議事録: str, 投稿する見出し: Sequence[str]) -> str:
    """議事録Markdownから、投稿する見出しのセクションだけを抜き出す。

    セクションの区切りは `##`(深さ2)の見出し行だけ。`###` 以下の小見出し
    (デイリー系の進捗にある担当者名)はセクションの内側として扱う。ここを
    区切りと数えると、進捗の途中で抽出が止まり決定事項・TODOが投稿から落ちる。
    タイトル(`#`)は含めない(投稿本文の先頭は会議メタ情報から始める)。
    """
    抜粋の行: list[str] = []
    採用中 = False
    for 行 in 議事録.splitlines():
        文字列 = 行.strip()
        深さ = _見出しの深さ(文字列)
        if 深さ == 2:
            採用中 = 文字列.lstrip("#").strip() in 投稿する見出し
        elif 深さ == 1:
            採用中 = False
        if 採用中:
            抜粋の行.append(行)
    return "\n".join(抜粋の行).strip() + "\n"


def ビューアURLを組み立てる(ビューア: str, web相対フォルダ: str, ファイル名: str) -> str:
    """共有ストレージのファイルビューアで開くURLを組み立てる。

    設定値はブラウザのアドレスバーからコピーされることを前提に、ビューア側に
    付いてきたクエリを落とし、エンコード済みのフォルダパスは一度戻してから
    エンコードする(そのまま組み立てると `?` が二重になる・`%20` が `%2520` になる)。
    仕様: requirements.md#議事録全文へのリンク [2]
    """
    基点 = ビューア.split("?")[0].rstrip("/")
    フォルダ = "/" + unquote(web相対フォルダ).strip("/")
    ファイルのid = quote(f"{フォルダ}/{ファイル名}", safe="")
    親 = quote(フォルダ, safe="")
    return f"{基点}?id={ファイルのid}&parent={親}"


def 議事録へのリンク(ビューア: str, web相対フォルダ: str, ファイル名: str) -> str | None:
    """議事録全文へのリンクURL。組み立てに必要な設定が欠けていればNoneを返す。

    設定漏れで投稿そのものを失敗させない(リンクの代わりにファイル名を案内する)。
    仕様: requirements.md#議事録全文へのリンク [3]
    """
    if not ビューア or not web相対フォルダ:
        return None
    return ビューアURLを組み立てる(ビューア, web相対フォルダ, ファイル名)


def htmlへ変換する(抜粋: str, 議事録ファイル名: str, 全文リンク: str | None = None) -> str:
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
        見出しの深さ = _見出しの深さ(文字列)
        if 見出しの深さ:
            リストを閉じる(0)
            # `##` は見出し、`###` 以下(進捗の担当者名)は1段下の見出しにする。
            タグ = "h3" if 見出しの深さ <= 2 else "h4"
            部品.append(f"<{タグ}>{_html.escape(文字列.lstrip('#').strip())}</{タグ}>")
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
    表示名 = _html.escape(議事録ファイル名)
    if 全文リンク:
        部品.append(f'<p>全文: <a href="{_html.escape(全文リンク)}">{表示名}</a></p>')
    else:
        部品.append(f"<p>全文はOneDriveの議事録フォルダの「{表示名}」を参照してください。</p>")
    return "\n".join(部品)
