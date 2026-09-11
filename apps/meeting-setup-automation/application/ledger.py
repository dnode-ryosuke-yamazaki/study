"""台帳ファイルの名前の決め方と、JSONの読み書き。

依頼IDを唯一の共有点として、依頼・候補・選択結果・作成結果・選択画面を
対応付ける(requirements.md#台帳ファイルの扱い [2])。フローが書くファイルの名前は
読んだファイルの名前の先頭を置き換えただけで決まる(design.md#power-automateフローの役割)
ため、番号の解釈はここだけが持つ。

フォルダの一覧は取らない(同期フォルダは一覧の取得が許可されないことがあるため)。
どのファイルも依頼IDから名前が決まるので、名前を直接指定して有無を見る。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from config import 設定


def 依頼ファイル(設定値: 設定, 依頼id: str, 試行番号: int) -> Path:
    return 設定値.依頼フォルダ / f"request-{依頼id}-a{試行番号}.json"


def 候補ファイル(設定値: 設定, 依頼id: str, 試行番号: int) -> Path:
    return 設定値.候補フォルダ / f"candidates-{依頼id}-a{試行番号}.json"


def _再試行接尾辞(再試行番号: int) -> str:
    return f"-r{再試行番号}" if 再試行番号 > 0 else ""


def 選択結果ファイル(設定値: 設定, 依頼id: str, 再試行番号: int = 0) -> Path:
    return 設定値.選択結果フォルダ / f"selection-{依頼id}{_再試行接尾辞(再試行番号)}.json"


def 作成結果ファイル(設定値: 設定, 依頼id: str, 再試行番号: int = 0) -> Path:
    return 設定値.作成結果フォルダ / f"result-{依頼id}{_再試行接尾辞(再試行番号)}.json"


def 選択画面ファイル(設定値: 設定, 依頼id: str) -> Path:
    return 設定値.htmlフォルダ / f"select-{依頼id}.html"


def read_json(path: Path) -> Optional[Any]:
    """JSONファイルを読む。無い・読めない・途中まで書かれている場合はNone(「まだ来ていない」扱い)。"""
    path = Path(path)
    try:
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def write_json(path: Path, data: Any) -> None:
    """JSONを書く。親フォルダが無ければ作る。失敗はOSErrorとして呼び出し元に伝える。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
