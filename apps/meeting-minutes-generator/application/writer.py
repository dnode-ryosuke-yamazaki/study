"""議事録と投稿用ファイルの書き出し。

対応する仕様: design.md#議事録の保存 / design.md#投稿用ファイルの書き出し
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def 議事録を保存する(本文: str, vtt名: str, 議事録フォルダ: Path) -> Path:
    """議事録Markdownを、元のVTTと対応が分かる名前で保存する。

    同名ファイルが既にある場合は上書きせず連番を付ける(再生成や同名会議の
    再録画で既存の議事録を黙って失わないため)。仕様: design.md#議事録の保存
    """
    議事録フォルダ.mkdir(parents=True, exist_ok=True)
    元の名前 = Path(vtt名).stem
    保存先 = 議事録フォルダ / f"{元の名前}.md"
    連番 = 2
    while 保存先.exists():
        保存先 = 議事録フォルダ / f"{元の名前}-{連番}.md"
        連番 += 1
    保存先.write_text(本文, encoding="utf-8")
    return 保存先


def 投稿用に書き出す(html: str, 投稿フォルダ: Path, 日時: datetime) -> Path:
    """Teams投稿用ファイルを一意な名前で書き出す。

    OneDriveの「ファイル作成時」トリガーは新規作成のみ検知し上書きでは発火しない
    ため、名前の一意性が投稿の成立条件(requirements.md#OneDriveフォルダの使い方 [2])。
    同じ秒に複数書き出す場合は連番で衝突を避ける。
    """
    投稿フォルダ.mkdir(parents=True, exist_ok=True)
    基本名 = f"minutes-{日時.strftime('%Y%m%d-%H%M%S')}"
    書き出し先 = 投稿フォルダ / f"{基本名}.txt"
    連番 = 2
    while 書き出し先.exists():
        書き出し先 = 投稿フォルダ / f"{基本名}-{連番}.txt"
        連番 += 1
    書き出し先.write_text(html, encoding="utf-8")
    return 書き出し先
