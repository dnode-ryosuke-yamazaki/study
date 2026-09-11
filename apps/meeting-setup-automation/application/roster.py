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

`organizer` は候補が0件のときの代替案1で、開催者自身に仮の予定があることを名前つきで
示すために使う(無ければ「開催者(あなた)」と示す)。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_敬称 = ("さん", "サン")
_空白 = re.compile(r"[\s\u3000]+")
#: 「姓, 名」形式の登録を空白区切りで打っても同じ名前として扱うため、照合キーから落とす
_読点 = re.compile(r"[,、]")


class 名簿エラー(Exception):
    """名簿が無い・読めない。メッセージは利用者向けの日本語。"""


def _照合キー(名前: str) -> str:
    """打ち方の違いを吸収した比較用の文字列。空白をすべて落とし、大文字小文字を揃える。

    敬称はここでは外さない。名簿の登録名が敬称で終わる場合(「ハッサン」など)に、
    索引側で外すと別人と潰れてしまうため、外すのは問い合わせ側だけにする。
    """
    return _読点.sub("", _空白.sub("", 名前.strip())).casefold()


def _敬称を外した照合キー(名前: str) -> Optional[str]:
    """末尾の敬称を落とした照合キー。敬称が付いていなければNone。"""
    キー = _照合キー(名前)
    for 敬称 in _敬称:
        照合 = _照合キー(敬称)
        if キー.endswith(照合) and len(キー) > len(照合):
            return キー[: -len(照合)]
    return None


def _姓と名(フルネーム: str) -> Tuple[str, str]:
    """氏名を姓と名に割る。区切りは空白(全角・半角)。西洋名の姓に付く読点は落とす。

    3語以上の氏名(ミドルネームを含む場合など)は、最初の語を姓、最後の語を名として扱う。
    """
    語 = [w for w in _空白.split(フルネーム.strip()) if w]
    if len(語) < 2:
        return (語[0].rstrip(",、").strip() if 語 else ""), ""
    return 語[0].rstrip(",、").strip(), 語[-1].strip()


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
    #: フルネームの照合キー -> 該当する人({"name": フルネーム, "email": ...})の一覧
    _フルネーム: Dict[str, List[dict]]
    #: 姓だけ・名だけの照合キー -> 該当する人の一覧
    _姓名: Dict[str, List[dict]]
    organizer_name: Optional[str] = None

    def _該当(self, 名前: str) -> List[dict]:
        """打たれた文字列に該当する人を集める。打たれたとおりの照合を、敬称を外した照合より先に見る。

        同じ照合キーではフルネームでの一致と姓・名での一致を**統合**して数える。
        片方を優先して打ち切ると、区切りの無い登録名(「大西」)が同姓の別人
        (「大西 潤哉」)を隠して1人に確定してしまい、同姓の別人を黙って招待する
        (requirements.md#参加者の解決 [2])。
        """
        for キー in (_照合キー(名前), _敬称を外した照合キー(名前)):
            if not キー:
                continue
            該当: List[dict] = []
            for 索引 in (self._フルネーム, self._姓名):
                for 人 in 索引.get(キー, []):
                    if not any(x["email"].casefold() == 人["email"].casefold() for x in 該当):
                        該当.append(人)
            if 該当:
                return 該当
        return []

    def resolve_one(self, 名前: str) -> Optional[str]:
        """名前を1件解決する。登録がない・複数人が該当する場合はNone。"""
        人 = self.一人に定める(名前)
        return 人["email"] if 人 else None

    def 一人に定める(self, 名前: str) -> Optional[dict]:
        """該当が1人ならその人({"name": フルネーム, "email": ...})を返す。定まらなければNone。"""
        該当 = self._該当(名前)
        return dict(該当[0]) if len(該当) == 1 else None

    def 候補(self, 名前: str) -> List[dict]:
        """複数人が該当したときの候補(フルネームとメールアドレス)。1人に定まる名前・登録が無い名前は空。"""
        該当 = self._該当(名前)
        return list(該当) if len(該当) > 1 else []

    def resolve(self, 名前一覧) -> 解決結果:
        """複数の名前をまとめて解決する。1件でも解決できなければ全体を失敗として返す。"""
        結果 = 解決結果()
        for 名前 in 名前一覧:
            表示 = 名前.strip()
            人 = self.一人に定める(名前)
            if 人 is None:
                if 表示 not in 結果.候補一覧:
                    結果.未解決.append(表示)
                    結果.候補一覧[表示] = self.候補(名前)
            elif not any(x["email"].casefold() == 人["email"].casefold() for x in 結果.解決済み):
                # 打たれた文字列ではなく名簿のフルネームを返す。姓だけ・敬称付きの指定を
                # 許した以上、確認提示が入力の反響になっていると誤解決に気づけない。
                # 同じ人を姓だけとフルネームで二重に挙げても1人として扱う
                結果.解決済み.append(人)
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

    フルネーム索引: Dict[str, List[dict]] = {}
    姓名索引: Dict[str, List[dict]] = {}

    def _積む(索引: Dict[str, List[dict]], キー: str, 人: dict) -> None:
        該当 = 索引.setdefault(キー, [])
        if not any(x["email"].casefold() == 人["email"].casefold() for x in 該当):
            該当.append(人)

    for 行 in 内容["members"]:
        if not isinstance(行, dict) or not 行.get("name") or not 行.get("email"):
            raise 名簿エラー(f"メンバー名簿 {path} の members に name/email の無い行があります")
        人 = {"name": str(行["name"]).strip(), "email": str(行["email"]).strip()}
        if not 人["name"] or not 人["email"]:
            # 空白だけの値を通すと、別人が同じ空文字のメールで1人に潰れて先勝ちで解決されてしまう
            raise 名簿エラー(f"メンバー名簿 {path} の members に name/email が空白だけの行があります")
        _積む(フルネーム索引, _照合キー(人["name"]), 人)
        姓, 名 = _姓と名(人["name"])
        for 部分 in (姓, 名):
            if 部分:
                _積む(姓名索引, _照合キー(部分), 人)

    開催者 = 内容.get("organizer") or {}
    return 名簿(
        _フルネーム=フルネーム索引,
        _姓名=姓名索引,
        organizer_name=(str(開催者["name"]).strip() if 開催者.get("name") else None),
    )
