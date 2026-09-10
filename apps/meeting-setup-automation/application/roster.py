"""メンバー名簿の読み込みと、参加者の名前からメールアドレスへの解決。

名簿は氏名とメールアドレスの対応表(個人情報)なのでGit管理下に置かず、作業フォルダの
`roster.json` から読む(requirements.md#参加者の解決 [1])。照合は表記のゆれを吸収し、
姓と名の区切りの違い・敬称の有無・姓だけ・名だけの指定を同じ人物への指定として扱う(同 [4])。
該当が1人に定まらない名前は解決を試みず、依頼を中断して聞き返す材料として返す(同 [2])。
複数人が該当した場合は、その候補のフルネームとメールアドレスを添えて返す(同 [5])。

表記のゆれは名簿データではなくこのモジュールで展開する。名簿にゆれを展開して持たせると、
「鈴木」で複数該当したときに元のフルネームを復元できず、候補を示せなくなるため。

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


_敬称 = ("さん", "サン")


class 名簿エラー(Exception):
    """名簿が無い・読めない。メッセージは利用者向けの日本語。"""


def _照合キー(名前: str) -> str:
    """打ち方の違いを吸収した比較用の文字列。空白を落とし、敬称を外し、大文字小文字を揃える。"""
    キー = 名前.strip().replace("\u3000", "").replace(" ", "")
    for 敬称 in _敬称:
        if キー.endswith(敬称) and len(キー) > len(敬称):
            キー = キー[: -len(敬称)]
            break
    return キー.casefold()


def _姓と名(フルネーム: str) -> tuple:
    """氏名を姓と名に割る。区切りは全角・半角スペース。西洋名の姓に付く読点は落とす。"""
    for 区切り in ("\u3000", " "):
        if 区切り in フルネーム:
            姓, 名 = フルネーム.split(区切り, 1)
            return 姓.rstrip(",、").strip(), 名.strip()
    return フルネーム.rstrip(",、").strip(), ""


def _その人を指しうる表記(フルネーム: str) -> set:
    """フルネーム全体・姓だけ・名だけ。ここで広げても、複数人に当たる表記は解決されない。"""
    姓, 名 = _姓と名(フルネーム)
    表記 = {フルネーム}
    if 姓:
        表記.add(姓)
    if 名:
        表記.add(名)
    return {_照合キー(v) for v in 表記 if v.strip()}


@dataclass
class 解決結果:
    解決済み: List[dict] = field(default_factory=list)
    未解決: List[str] = field(default_factory=list)
    #: 未解決の名前ごとの候補({名前: [{"name": フルネーム, "email": ...}, ...]})。
    #: 登録が無い名前は空リスト。チャットへの表示にだけ使い、ログには出さない(design.md#セキュリティ)
    候補一覧: Dict[str, List[dict]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.未解決


@dataclass
class 名簿:
    #: 照合用の表記 -> その表記に該当する人({"name": フルネーム, "email": ...})の一覧
    _表記: Dict[str, List[dict]]
    organizer_email: Optional[str] = None
    organizer_name: Optional[str] = None

    def _該当(self, 名前: str) -> List[dict]:
        return self._表記.get(_照合キー(名前), [])

    def resolve_one(self, 名前: str) -> Optional[str]:
        """名前を1件解決する。登録がない・複数人が該当する場合はNone。"""
        該当 = self._該当(名前)
        return 該当[0]["email"] if len(該当) == 1 else None

    def 候補(self, 名前: str) -> List[dict]:
        """複数人が該当したときの候補(フルネームとメールアドレス)。1人に定まる名前・登録が無い名前は空。"""
        該当 = self._該当(名前)
        return list(該当) if len(該当) > 1 else []

    def resolve(self, 名前一覧) -> 解決結果:
        """複数の名前をまとめて解決する。1件でも解決できなければ全体を失敗として返す。"""
        結果 = 解決結果()
        for 名前 in 名前一覧:
            表示 = 名前.strip()
            メール = self.resolve_one(名前)
            if メール is None:
                結果.未解決.append(表示)
                結果.候補一覧[表示] = self.候補(名前)
            else:
                結果.解決済み.append({"name": 表示, "email": メール})
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

    表記: Dict[str, List[dict]] = {}
    for 行 in 内容["members"]:
        if not isinstance(行, dict) or not 行.get("name") or not 行.get("email"):
            raise 名簿エラー(f"メンバー名簿 {path} の members に name/email の無い行があります")
        人 = {"name": str(行["name"]).strip(), "email": str(行["email"]).strip()}
        for キー in _その人を指しうる表記(人["name"]):
            該当 = 表記.setdefault(キー, [])
            if not any(x["email"].casefold() == 人["email"].casefold() for x in 該当):
                該当.append(人)

    開催者 = 内容.get("organizer") or {}
    return 名簿(
        _表記=表記,
        organizer_email=(str(開催者["email"]).strip() if 開催者.get("email") else None),
        organizer_name=(str(開催者["name"]).strip() if 開催者.get("name") else None),
    )
