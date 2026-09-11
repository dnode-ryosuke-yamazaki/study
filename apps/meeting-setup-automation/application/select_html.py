"""候補選択画面(静的HTML)の組み立て・書き出しと、ビューア形式URLの組み立て。

画面は `templates/select.html` の骨格に、ヘッダーとカードを差し込んで作る。JavaScriptは
テンプレート側に静的に置き、カードの値は `data-` 属性で渡す(f文字列でJSを組み立てると
改行を含む値でJSの文字列が壊れる不具合を防ぐ。tasks.md 11)。

クリップボードへ入れる1行は「目印の語 依頼ID a試行番号 #候補番号 開始 終了」。試行番号は
画面全体で1つではなく、その枠が入っていた候補ファイルの試行番号をカードごとに埋め込む
(design.md#画面設計)。
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence
from urllib.parse import quote, unquote

import ledger
import timeutil
from candidates import 枠
from config import 設定

#: 貼られた内容が選択結果かどうかを取り違えずに判定するための目印の語
目印の語 = "MEETING-SELECT"
ラジオボタン名 = "candidate"
_曜日名 = "月火水木金土日"
_テンプレート = Path(__file__).parent / "templates" / "select.html"


@dataclass
class カード:
    枠: 枠
    #: 代替案1の枠にだけ入る「仮の予定あり: <参加者名>」の行
    仮の予定: List[str] = field(default_factory=list)


@dataclass
class セクション:
    見出し: str
    条件: str
    カード一覧: List[カード]


@dataclass
class 書き出し結果:
    ok: bool
    path: Optional[str] = None
    確認済み: bool = False
    error: str = ""


def _空き状況(w: 枠) -> str:
    人数 = w.空いていない人数
    return "全員空き" if 人数 == 0 else f"{人数}人が空いていません"


def _カードhtml(番号: int, 依頼id: str, c: カード) -> str:
    w = c.枠
    日付 = f"{w.開始:%Y-%m-%d}({_曜日名[w.開始.weekday()]})"
    仮 = ""
    if c.仮の予定:
        項目 = "".join(f"<li>{html.escape(s)}</li>" for s in c.仮の予定)
        仮 = f'<ul class="tentative">{項目}</ul>'
    return (
        '<label class="card">'
        f'<input type="radio" name="{ラジオボタン名}" value="{番号}"'
        f' data-request="{html.escape(依頼id)}" data-attempt="{w.試行番号}" data-number="{番号}"'
        f' data-start="{timeutil.format_jst(w.開始)}" data-end="{timeutil.format_jst(w.終了)}">'
        f'<span class="num">候補 {番号}</span>'
        f'<span class="when">{日付} {w.開始:%H:%M}〜{w.終了:%H:%M}</span>'
        f'<div class="avail">{html.escape(_空き状況(w))}</div>'
        f"{仮}"
        "</label>"
    )


def 組み立てる(
    依頼id: str,
    件名: str,
    所要時間分: int,
    参加者数: int,
    セクション一覧: Sequence[セクション],
    緩めた: bool,
) -> str:
    """採用した枠から選択画面のHTMLを組み立てる。候補番号は画面に並べた順の1からの連番。"""
    条件の要約 = " / ".join(s.条件 for s in セクション一覧 if s.条件)
    ヘッダー = (
        "<header>"
        f"<h1>{html.escape(件名)}</h1>"
        "<dl>"
        f"<dt>所要時間</dt><dd>{所要時間分}分</dd>"
        f"<dt>参加者</dt><dd>{参加者数}人</dd>"
        f"<dt>絞り込み条件</dt><dd>{html.escape(条件の要約)}</dd>"
        "</dl>"
        "</header>"
    )
    if 緩めた:
        ヘッダー += (
            '<div class="notice">既定の条件では候補が0件だったため、条件を緩めた候補を示しています。'
            "見出しごとに、どの代替案による候補かと緩めた後の条件を添えています。</div>"
        )

    部分: List[str] = []
    番号 = 0
    for s in セクション一覧:
        部分.append(f"<section><h2>{html.escape(s.見出し)}</h2>")
        if s.条件:
            部分.append(f'<p class="condition">{html.escape(s.条件)}</p>')
        if not s.カード一覧:
            部分.append('<p class="empty">この条件では候補がありませんでした</p>')
        for c in s.カード一覧:
            番号 += 1
            部分.append(_カードhtml(番号, 依頼id, c))
        部分.append("</section>")

    骨格 = _テンプレート.read_text(encoding="utf-8")
    return (
        骨格.replace("<!--TITLE-->", html.escape(f"会議候補の選択: {件名}"))
        .replace("<!--MARKER-->", 目印の語)
        .replace("<!--HEADER-->", ヘッダー)
        .replace("<!--SECTIONS-->", "\n".join(部分))
    )


def _既定の読み(p: Path) -> str:
    return Path(p).read_text(encoding="utf-8")


def 書き出して確認(
    設定値: 設定, 依頼id: str, 内容: str, 読む: Callable[[Path], str] = _既定の読み
) -> 書き出し結果:
    """`select-<依頼ID>.html` としてHTMLフォルダへ書き(同名は上書き)、読み戻して内容とサイズを確認する。"""
    path = ledger.選択画面ファイル(設定値, 依頼id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(内容, encoding="utf-8")
    except OSError as e:
        return 書き出し結果(ok=False, path=str(path), error=f"選択画面を書き出せません: {e}")
    try:
        一致 = 読む(path) == 内容
        サイズ1 = path.stat().st_size
        サイズ2 = len(読む(path).encode("utf-8"))
        確認済み = 一致 and サイズ1 == サイズ2
    except OSError as e:
        return 書き出し結果(ok=True, path=str(path), 確認済み=False, error=f"選択画面を読み戻せません: {e}")
    return 書き出し結果(ok=True, path=str(path), 確認済み=確認済み)


def ビューアurlを組み立てる(ビューア: Optional[str], サーバー相対パス: Optional[str], ファイル名: str) -> Optional[str]:
    """共有ストレージのファイルビューアで開くURL。設定が欠けていればNone。

    ビューアのURLに付随するクエリは落とし、サーバー相対パスは一度デコードしてからエンコードする
    (エンコード済みの値を二重にエンコードしない)。前後のスラッシュの有無は吸収する。
    """
    if not ビューア or not サーバー相対パス:
        return None
    base = ビューア.split("?")[0].rstrip("/")
    directory = "/" + unquote(サーバー相対パス).strip("/")
    file_id = quote(f"{directory}/{ファイル名}", safe="")
    parent = quote(directory, safe="")
    return f"{base}?id={file_id}&parent={parent}"
