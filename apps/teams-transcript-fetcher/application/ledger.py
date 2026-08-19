"""台帳の読み取りとバリデーション。

台帳はPower Automateが書きバッチが読む受け渡し口。項目名がずれると例外ではなく
「対象が見つからない」という静かな失敗になるため、項目名は design.md の
「ファイルの項目名の取り決め」に固定してある。

**台帳に対して行うのは削除と退避のみで、内容は書き換えない**
(requirements.md#未取得の判定(バッチ) [3])。このモジュールは読み取り専用。

対応する仕様:
- design.md#ファイルの項目名の取り決め
- design.md#台帳の読み取りと使用するURLの一覧の決定(バッチ)
- design.md#バリデーション
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

台帳の拡張子 = ".json"

#: これが欠けているとURLの発行にも出力ファイル名の組み立てにも進めない。
必須項目 = ("meetingName", "siteUrl", "driveId", "recordingId")


class 台帳置き場にアクセスできない(Exception):
    """台帳置き場を列挙できない。

    「台帳が0件」と区別する必要がある。同期フォルダが見つからない状態で
    「0件だから何もしない」と扱うと、異常に気づかないまま静かに止まる。
    仕様: design.md#エラーハンドリング 5(全体を中断する条件)
    """


@dataclass(frozen=True)
class 台帳:
    パス: Path
    会議名: str
    サイトurl: str
    ドライブ識別子: str
    録画の識別子: str
    更新時刻: datetime
    録画の作成日時: datetime | None = None
    由来: str | None = None
    発行時刻: datetime | None = None
    #: 添字が「一覧内の並び順」。空なら「URLを持たない台帳」。
    url一覧: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class 不正な台帳:
    パス: Path
    理由: str


@dataclass(frozen=True)
class 読み込み結果:
    有効: list[台帳] = field(default_factory=list)
    不正: list[不正な台帳] = field(default_factory=list)


def 日時を読む(値: object) -> datetime | None:
    """ISO 8601 の文字列をUTCの日時にする。

    Power Automateは末尾 `Z` の表記で書くが、`datetime.fromisoformat` は
    Python 3.11 以降なら `Z` を解釈できる。解釈できない値は「無い」ものとして扱う
    (台帳全体を不正にするほどの項目ではなく、時刻は代用できる)。
    仕様: design.md#発行時刻の取り決め
    """
    if not isinstance(値, str) or not 値:
        return None
    try:
        解釈した日時 = datetime.fromisoformat(値)
    except ValueError:
        return None
    if 解釈した日時.tzinfo is None:
        return 解釈した日時.replace(tzinfo=timezone.utc)
    return 解釈した日時.astimezone(timezone.utc)


def _url一覧を読む(値: object) -> list[str]:
    """URLの配列を取り出す。配列でない・文字列以外が混ざる場合は落とす。"""
    if not isinstance(値, list):
        return []
    return [要素 for 要素 in 値 if isinstance(要素, str) and 要素]


def _台帳を1件読む(パス: Path) -> 台帳 | 不正な台帳:
    try:
        中身 = json.loads(パス.read_text(encoding="utf-8"))
    except json.JSONDecodeError as 例外:
        return 不正な台帳(パス=パス, 理由=f"JSONとして解析できない: {例外.msg}")
    except OSError as 例外:
        return 不正な台帳(パス=パス, 理由=f"読み取れない: {例外}")

    if not isinstance(中身, dict):
        return 不正な台帳(パス=パス, 理由="JSONのオブジェクトではない")

    欠けている項目 = [項目 for 項目 in 必須項目 if not 中身.get(項目)]
    if 欠けている項目:
        return 不正な台帳(
            パス=パス, 理由="必須項目が欠けている: " + ", ".join(欠けている項目)
        )

    return 台帳(
        パス=パス,
        会議名=中身["meetingName"],
        サイトurl=中身["siteUrl"],
        ドライブ識別子=中身["driveId"],
        録画の識別子=中身["recordingId"],
        更新時刻=datetime.fromtimestamp(パス.stat().st_mtime, tz=timezone.utc),
        録画の作成日時=日時を読む(中身.get("recordingCreatedAt")),
        由来=中身.get("source"),
        発行時刻=日時を読む(中身.get("issuedAt")),
        url一覧=_url一覧を読む(中身.get("urls")),
    )


@dataclass(frozen=True)
class url情報:
    """URL置き場のファイルの内容。

    台帳と同じ意味の `issuedAt` と `urls` を持つ。添字が並び順。
    仕様: design.md#ファイルの項目名の取り決め
    """

    パス: Path
    発行時刻: datetime | None
    url一覧: list[str]


def url情報を読む(urlフォルダ: Path, 録画の識別子: str) -> url情報 | None:
    """URL置き場からその録画のURLファイルを読む。無ければ None。

    壊れていても None として扱う。台帳側にURLが残っていればそれを使えるし、
    無ければ「要発行」になって再発行されるため、ここで止める理由がない。
    """
    パス = urlフォルダ / f"{録画の識別子}{台帳の拡張子}"
    try:
        中身 = json.loads(パス.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as 例外:
        logger.warning("URLファイルを読めないため無いものとして扱う: %s: %s", パス.name, 例外)
        return None

    if not isinstance(中身, dict):
        logger.warning("URLファイルの形式が想定と違う: %s", パス.name)
        return None

    return url情報(
        パス=パス,
        発行時刻=日時を読む(中身.get("issuedAt")),
        url一覧=_url一覧を読む(中身.get("urls")),
    )


def 退避する(パス: Path, 退避フォルダ: Path) -> Path:
    """不正なファイルを退避先へ移す。

    削除すると原因調査の材料が失われ、放置すると毎サイクル読み直されて記録が
    埋まる。バッチが所有するフォルダへ移すことで、終端を作りつつ内容を残す。
    仕様: design.md#台帳と要求のライフサイクル
    """
    退避フォルダ.mkdir(parents=True, exist_ok=True)
    移動先 = 退避フォルダ / パス.name
    # 同名が既にある場合は上書きせず連番を足す(前回の退避内容を消さないため)。
    連番 = 1
    while 移動先.exists():
        移動先 = 退避フォルダ / f"{パス.stem}_{連番}{パス.suffix}"
        連番 += 1
    os.replace(パス, 移動先)
    logger.warning("不正なファイルを退避した: %s -> %s", パス.name, 移動先.name)
    return 移動先


def 台帳を読み込む(台帳フォルダ: Path) -> 読み込み結果:
    """台帳置き場のすべての台帳を読む。

    1件が不正でも他の台帳は読む(requirements.md#エラー時の挙動 [9])。
    台帳置き場そのものを列挙できない場合だけ例外を投げ、呼び出し側で
    全体を中断させる。
    """
    try:
        候補 = sorted(台帳フォルダ.iterdir())
    except OSError as 例外:
        raise 台帳置き場にアクセスできない(f"{台帳フォルダ}: {例外}") from 例外

    結果 = 読み込み結果(有効=[], 不正=[])
    for パス in 候補:
        # 台帳の拡張子でないものは、OneDriveの一時ファイル等なので黙って無視する。
        if not パス.is_file() or パス.suffix != 台帳の拡張子:
            continue
        読んだもの = _台帳を1件読む(パス)
        if isinstance(読んだもの, 台帳):
            結果.有効.append(読んだもの)
        else:
            結果.不正.append(読んだもの)
    return 結果
