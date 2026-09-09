"""メンバー名簿の読み込みと、参加者の名前からメールアドレスへの解決。

名簿は氏名とメールアドレスの対応表(個人情報)なのでGit管理下に置かず、作業フォルダの
`roster.json` から読む(requirements.md#参加者の解決 [1])。登録がない名前・同じ名前が
複数ある名前は解決を試みず、依頼を中断して聞き返す材料として返す(同 [2])。

名簿の形(記入例は `roster.example.json`):
    {
      "organizer": {"name": "自分の名前", "email": "me@example.com"},   # 任意
      "members": [{"name": "山田 太郎", "email": "taro@example.com"}, ...]
    }

`organizer` は候補が0件のときの代替案1で、開催者自身の仮の予定の件名を取りに行くために
使う(無ければ開催者の予定は件名を取りに行かず、その旨を示す)。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


class 名簿エラー(Exception):
    """名簿が無い・読めない。メッセージは利用者向けの日本語。"""


@dataclass
class 解決結果:
    解決済み: List[dict] = field(default_factory=list)
    未解決: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.未解決


@dataclass
class 名簿:
    _件数: Dict[str, int]
    _メール: Dict[str, str]
    organizer_email: Optional[str] = None
    organizer_name: Optional[str] = None

    def resolve_one(self, 名前: str) -> Optional[str]:
        """名前を1件解決する。登録がない・同じ名前が複数ある場合はNone。"""
        キー = 名前.strip()
        if self._件数.get(キー, 0) != 1:
            return None
        return self._メール[キー]

    def resolve(self, 名前一覧) -> 解決結果:
        """複数の名前をまとめて解決する。1件でも解決できなければ全体を失敗として返す。"""
        結果 = 解決結果()
        for 名前 in 名前一覧:
            メール = self.resolve_one(名前)
            if メール is None:
                結果.未解決.append(名前.strip())
            else:
                結果.解決済み.append({"name": 名前.strip(), "email": メール})
        return 結果


def load(path: Path) -> 名簿:
    """`roster.json` を読んで名簿を返す。無い・読めない場合は名簿エラー。"""
    path = Path(path)
    if not path.is_file():
        raise 名簿エラー(
            f"メンバー名簿 {path} が見つかりません。roster.example.json を写して作成してください"
        )
    try:
        内容 = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise 名簿エラー(f"メンバー名簿 {path} を読めません: {e}") from e
    if not isinstance(内容, dict) or not isinstance(内容.get("members"), list):
        raise 名簿エラー(f"メンバー名簿 {path} に members の配列がありません")

    件数: Dict[str, int] = {}
    メール: Dict[str, str] = {}
    for 行 in 内容["members"]:
        if not isinstance(行, dict) or not 行.get("name") or not 行.get("email"):
            raise 名簿エラー(f"メンバー名簿 {path} の members に name/email の無い行があります")
        名前 = str(行["name"]).strip()
        件数[名前] = 件数.get(名前, 0) + 1
        メール[名前] = str(行["email"]).strip()

    開催者 = 内容.get("organizer") or {}
    return 名簿(
        _件数=件数,
        _メール=メール,
        organizer_email=(str(開催者["email"]).strip() if 開催者.get("email") else None),
        organizer_name=(str(開催者["name"]).strip() if 開催者.get("name") else None),
    )
