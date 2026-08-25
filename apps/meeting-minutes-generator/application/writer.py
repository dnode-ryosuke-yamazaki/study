"""議事録・控え・投稿用ファイルの書き出しと、控えのバックフィル。

議事録は同期フォルダの外の「控え」にも同じ名前・同じ内容で書き出す。OneDriveの
同期フォルダは、macOSが項目ごとに管理するアプリへのアクセス許可が付いた項目しか
読めないため(許可の付与は端末の管理設定により行えない)、議事録を入力に使う
下流のツールは控えを読む。**控えの失敗で議事録の保存とTeams共有を落とさない。**

対応する仕様: design.md#議事録の保存 / design.md#控えのバックフィル /
design.md#投稿用ファイルの書き出し / requirements.md#議事録のローカル控え
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class 保存の結果:
    #: OneDriveの議事録フォルダに保存したパス。
    保存先: Path
    #: 控えに書けた場合のパス。書かなかった・書けなかった場合は None。
    控え: Path | None = None
    #: 控えの書き出しに失敗した理由(ログ用)。成功時・控えなしのときは None。
    控えの失敗: str | None = None


@dataclass(frozen=True)
class バックフィルの結果:
    写した件数: int = 0
    #: 読み取れずに飛ばした議事録の件数。
    飛ばした件数: int = 0
    #: 議事録フォルダ自体を読めなかったか(アクセス許可が無い場合)。
    読めなかった: bool = False


def 議事録を保存する(
    本文: str, vtt名: str, 議事録フォルダ: Path, 控えフォルダ: Path | None = None
) -> 保存の結果:
    """議事録Markdownを、元のVTTと対応が分かる名前で保存する。

    同名ファイルが既にある場合は上書きせず連番を付ける(再生成や同名会議の
    再録画で既存の議事録を黙って失わないため)。仕様: design.md#議事録の保存

    控えフォルダを渡した場合は、**保存した名前そのまま**(連番が付いた場合はその
    名前)で控えにも同じ内容を書く。控えに同じ名前があれば上書きする(名前の対応を
    保つことを優先する。控え側で別の連番を付けるとOneDrive側に無い名前が生まれ、
    下流のツールが同じ会議を別物として扱う)。仕様: requirements.md#議事録のローカル控え [2][6]
    """
    議事録フォルダ.mkdir(parents=True, exist_ok=True)
    元の名前 = Path(vtt名).stem
    保存先 = 議事録フォルダ / f"{元の名前}.md"
    連番 = 2
    while 保存先.exists():
        保存先 = 議事録フォルダ / f"{元の名前}-{連番}.md"
        連番 += 1
    保存先.write_text(本文, encoding="utf-8")

    if 控えフォルダ is None:
        return 保存の結果(保存先=保存先)
    try:
        控えフォルダ.mkdir(parents=True, exist_ok=True)
        控え = 控えフォルダ / 保存先.name
        控え.write_text(本文, encoding="utf-8")
    except OSError as 例外:
        # 控えは下流のツール向けの写しなので、これを理由に議事録の保存を失敗に
        # しない。落ちた控えは次回実行のバックフィルで回復する。
        # 仕様: requirements.md#議事録のローカル控え [3][4]
        return 保存の結果(保存先=保存先, 控えの失敗=str(例外))
    return 保存の結果(保存先=保存先, 控え=控え)


def 控えをバックフィルする(議事録フォルダ: Path, 控えフォルダ: Path) -> バックフィルの結果:
    """控えに無い議事録を控えへ写す。

    控えに同じ名前がある議事録は触らない(通常の保存で書いた控えを上書きしないため)。
    議事録フォルダの一覧取得が権限で失敗した場合は「読めなかった」として返す(この
    環境では許可が無く読めないことがあり、異常ではない)。個別の議事録の読み取り
    失敗はその1件を飛ばす。仕様: design.md#控えのバックフィル
    """
    if not 議事録フォルダ.is_dir():
        return バックフィルの結果()
    try:
        一覧 = sorted(
            (パス for パス in 議事録フォルダ.iterdir() if パス.suffix == ".md"),
            key=lambda パス: パス.name,
        )
    except OSError:
        return バックフィルの結果(読めなかった=True)

    写した = 0
    飛ばした = 0
    for パス in 一覧:
        控え = 控えフォルダ / パス.name
        if 控え.exists():
            continue
        try:
            本文 = パス.read_text(encoding="utf-8")
            控えフォルダ.mkdir(parents=True, exist_ok=True)
            控え.write_text(本文, encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            飛ばした += 1
            continue
        写した += 1
    return バックフィルの結果(写した件数=写した, 飛ばした件数=飛ばした)


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
