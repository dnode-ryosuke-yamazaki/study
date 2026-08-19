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
class 読めなかった台帳:
    """内容を読み取れなかった台帳。

    **不正な台帳とは扱いが違う。** 中身を見られていないので不正と断定できず、
    退避すると次回読めば取得できるトランスクリプトを捨てることになる。
    同期フォルダの実体化待ちで起こりうる(実機で `Resource deadlock avoided`)。
    仕様: requirements.md#エラー時の挙動 [10]
    """

    パス: Path
    理由: str


@dataclass(frozen=True)
class 読み込み結果:
    有効: list[台帳] = field(default_factory=list)
    不正: list[不正な台帳] = field(default_factory=list)
    読めなかった: list[読めなかった台帳] = field(default_factory=list)


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


def _台帳を1件読む(パス: Path) -> 台帳 | 不正な台帳 | 読めなかった台帳:
    """台帳1件を読む。

    **失敗の分類は「中身を見て判断できたか」で分ける。** 解析できない・項目が
    欠けているは中身を見た結果なので不正、読み取り自体ができなかった場合は
    判断材料がないので「読めなかった」。仕様: design.md#バリデーション
    """
    try:
        中身 = json.loads(パス.read_text(encoding="utf-8"))
        # 更新時刻の取得も同じtryに入れる。ここが外にあると、読めたのに
        # 属性が取れない場合に例外が実行全体へ抜け、他の録画の処理まで止まる。
        更新時刻 = datetime.fromtimestamp(パス.stat().st_mtime, tz=timezone.utc)
    except json.JSONDecodeError as 例外:
        return 不正な台帳(パス=パス, 理由=f"JSONとして解析できない: {例外.msg}")
    except OSError as 例外:
        return 読めなかった台帳(パス=パス, 理由=f"読み取れない: {例外}")

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
        更新時刻=更新時刻,
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


@dataclass(frozen=True)
class 要求:
    """要求置き場のファイル。

    **録画1件につき1ファイル**で、ファイル名は台帳・URLファイルと同じ
    「録画の識別子 + 拡張子」。バッチが書き、フロー②が処理後に削除する。
    仕様: design.md#ファイルの項目名の取り決め
    """

    パス: Path
    録画の識別子: str
    作成時刻: datetime | None


def 要求のパス(要求フォルダ: Path, 録画の識別子: str) -> Path:
    return 要求フォルダ / f"{録画の識別子}{台帳の拡張子}"


def 要求済みか(要求フォルダ: Path, 録画の識別子: str) -> bool:
    """その録画の要求が既にあるか。

    ファイル名が録画の識別子なので存在確認だけで重複要求を防げる。
    """
    return 要求のパス(要求フォルダ, 録画の識別子).exists()


def 要求を書き出す(要求フォルダ: Path, 対象の台帳: 台帳, 作成時刻: datetime) -> Path:
    """発行要求を1件書き出す。

    **ダウンロードURLは含めない**(requirements.md#ダウンロードURLの発行要求 [3])。
    実質ベアラトークンであり、必要のない場所に置かない。

    要求だけで発行に必要な情報が揃うようにしてある。フロー②が台帳を読みに行く
    必要がなくなり、「読んで呼んで書くだけ」の単純な構造で済む。
    """
    中身 = {
        "siteUrl": 対象の台帳.サイトurl,
        "driveId": 対象の台帳.ドライブ識別子,
        "recordingId": 対象の台帳.録画の識別子,
        "createdAt": 作成時刻.astimezone(timezone.utc).isoformat(timespec="milliseconds"),
    }
    要求フォルダ.mkdir(parents=True, exist_ok=True)
    パス = 要求のパス(要求フォルダ, 対象の台帳.録画の識別子)
    # 一時ファイル経由で書く。書き込み途中の要求をフロー②が拾わないようにするため。
    一時ファイル = パス.with_name(パス.name + ".tmp")
    try:
        一時ファイル.write_text(
            json.dumps(中身, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(一時ファイル, パス)
    finally:
        一時ファイル.unlink(missing_ok=True)
    logger.info("発行要求を書き出した: %s", パス.name)
    return パス


def 未処理の要求を読む(要求フォルダ: Path) -> list[要求]:
    """要求置き場に残っている要求を読む。

    残っている＝フロー②がまだ処理していない。滞留の判定に使う。
    """
    try:
        候補 = sorted(要求フォルダ.iterdir())
    except OSError:
        # 要求置き場が無いのは初回など通常のこと。台帳置き場と違い中断しない。
        return []

    要求たち: list[要求] = []
    for パス in 候補:
        if not パス.is_file() or パス.suffix != 台帳の拡張子:
            continue
        識別子 = パス.stem
        try:
            中身 = json.loads(パス.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as 例外:
            # 解析できない要求もフロー②は削除しないため、滞留として退避される。
            logger.warning("要求を解析できない: %s: %s", パス.name, 例外)
            要求たち.append(要求(パス=パス, 録画の識別子=識別子, 作成時刻=None))
            continue
        要求たち.append(
            要求(
                パス=パス,
                録画の識別子=識別子,
                作成時刻=日時を読む(中身.get("createdAt") if isinstance(中身, dict) else None),
            )
        )
    return 要求たち


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

    **結果は3つに分かれる。** 有効・不正・読めなかった。読めなかったものは
    退避せず次回に持ち越す対象で、呼び出し側で扱いを分ける必要がある
    (requirements.md#エラー時の挙動 [10])。
    """
    try:
        候補 = sorted(台帳フォルダ.iterdir())
    except OSError as 例外:
        raise 台帳置き場にアクセスできない(f"{台帳フォルダ}: {例外}") from 例外

    結果 = 読み込み結果(有効=[], 不正=[], 読めなかった=[])
    for パス in 候補:
        # 台帳の拡張子でないものは、OneDriveの一時ファイル等なので黙って無視する。
        if パス.suffix != 台帳の拡張子:
            continue
        # 除外にはディレクトリ判定だけを使う。`is_file()` は属性の取得に失敗しても
        # 偽を返すため、除外条件に使うと**読めない台帳が黙って無視される**。
        if パス.is_dir():
            continue
        読んだもの = _台帳を1件読む(パス)
        if isinstance(読んだもの, 台帳):
            結果.有効.append(読んだもの)
        elif isinstance(読んだもの, 読めなかった台帳):
            結果.読めなかった.append(読んだもの)
        else:
            結果.不正.append(読んだもの)
    return 結果
