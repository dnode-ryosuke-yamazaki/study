"""コマンドの入口。依頼の書き出し(submit)・再開(resume)・選択結果の受け取り(select)・作成の再試行(retry-create)。

チャットでのやり取りはSKILL.mdが担い、ファイルの読み書きと判定はこのサブコマンドが担う
(design.md#手順の担い手)。どのサブコマンドも進捗と結果を標準出力に出し、チャットへそのまま
貼れる形にする。あわせて作業フォルダのログファイルへ追記する(design.md#ログ)。ログには
メールアドレス・アジェンダ本文・参加URL・会議本文・他人の予定の件名を出さない。

`resume` は依頼IDだけを受け取り、台帳の有無から進行状態を判定してその続きを進める
(design.md#状態管理)。打ち切った後の再開も、依頼の直後の待ちも同じサブコマンドで行う。
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import date, datetime, time as dtime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import candidates
import config
import detail
import ledger
import notify
import progress
import request
import result as result_mod
import roster
import select_html
import selection
import timeutil
import wait_for

logger = logging.getLogger("meeting_setup")

見出し_既定 = "候補"
見出し_代替案1 = "代替案1: 仮の予定を含める"
見出し_代替案2 = "代替案2: 期間と時間帯を広げる"
条件_代替案1 = "期間・時間帯・曜日は既定のまま。仮の予定が入っている参加者を空いているものとみなす"

再試行の案内 = (
    "会議の作成に成功した直後の処理で失敗した場合は会議だけが残っていることがあります。"
    "Teamsのカレンダーでこの枠に会議が既に作られていないかを確かめたうえで、"
    "同じ枠でやり直す場合は `retry-create <依頼ID>` を指示してください(自動では再試行しません)。"
)
打ち切りの案内 = (
    "待ちを打ち切りました。台帳は残しているので、後から `resume <依頼ID>` で続きから再開できます。"
    "フロー側の異常のほかに、OneDrive同期が止まっている可能性も切り分け先になります。"
)


@dataclass
class 実行環境:
    """テストで差し替える依存(設定・日付・時計・出力先)。"""

    設定: config.設定
    今日: date
    出力: Callable[[str], None] = print
    時計: Callable[[], float] = time.monotonic
    待つ: Callable[[float], None] = time.sleep
    名簿パス: Optional[Path] = None

    def 名簿ファイル(self) -> Path:
        return self.名簿パス or self.設定.名簿ファイル


# ---------------------------------------------------------------------------
# ログ(design.md#ログ)
# ---------------------------------------------------------------------------


_この関数が付けたハンドラ: List[logging.Handler] = []
_設定済みのログファイル: Optional[str] = None


def ログを設定(設定値: config.設定) -> None:
    """標準エラーと作業フォルダのログファイル(5世代ローテーション)へ出す。標準出力はチャット向けの文に使う。

    付け外しするのは自分で付けたハンドラだけにして、同じログファイルへの2回目以降の呼び出しでは
    付け直さない(呼ぶたびに新しいファイルハンドラを開くと、前のものが閉じられないまま積み上がる)。
    """
    global _設定済みのログファイル
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if _この関数が付けたハンドラ and _設定済みのログファイル == str(設定値.ログファイル):
        for h in _この関数が付けたハンドラ:
            if h not in logger.handlers:
                logger.addHandler(h)
        return
    for h in _この関数が付けたハンドラ:
        logger.removeHandler(h)
        h.close()
    _この関数が付けたハンドラ.clear()
    _設定済みのログファイル = str(設定値.ログファイル)
    書式 = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    stderr = logging.StreamHandler(sys.stderr)
    stderr.setFormatter(書式)
    logger.addHandler(stderr)
    _この関数が付けたハンドラ.append(stderr)
    try:
        設定値.作業フォルダ.mkdir(parents=True, exist_ok=True)
        ファイル = RotatingFileHandler(設定値.ログファイル, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
        ファイル.setFormatter(書式)
        logger.addHandler(ファイル)
        _この関数が付けたハンドラ.append(ファイル)
    except OSError as e:  # ログが書けなくても処理は止めない
        logger.warning("ログファイルを開けません: %s", e)


# ---------------------------------------------------------------------------
# 共通の小さな道具
# ---------------------------------------------------------------------------


def _名前表(依頼: dict) -> Dict[str, str]:
    表 = {}
    for a in (依頼.get("meeting") or {}).get("attendees") or []:
        e = a.get("emailAddress") or {}
        if e.get("address"):
            表[str(e["address"]).lower()] = str(e.get("name") or e["address"])
    return 表


def _名簿を読む(env: 実行環境) -> Optional[roster.名簿]:
    try:
        return roster.load(env.名簿ファイル())
    except roster.名簿エラー:
        return None


def _枠の表示(w: candidates.枠) -> str:
    return f"{w.開始:%Y-%m-%d} {w.開始:%H:%M}〜{w.終了:%H:%M}"


def _件名の表示(情報: detail.件名情報) -> str:
    if 情報.取得できない:
        return f"(件名を取得できません: {情報.理由})"
    if 情報.非公開 and not 情報.件名一覧:
        return "(非公開の予定)"
    表示 = "、".join(情報.件名一覧)
    if 情報.非公開:
        表示 += "、ほか非公開の予定"
    return 表示


def _仮の予定の表示(
    w: candidates.枠, 詳細: Optional[detail.予定詳細の読み取り], 名前表: Dict[str, str], 名簿: Optional[roster.名簿]
) -> List[str]:
    """代替案1のカードに添える「参加者名: 件名」の一覧。"""
    対象 = list(w.仮の参加者)
    開催者メール = 名簿.organizer_email.lower() if (名簿 and 名簿.organizer_email) else None
    if w.開催者が仮 and 開催者メール:
        対象.append(開催者メール)
    行 = []
    for 情報 in detail.枠に重なる仮の予定(詳細, w, 対象):
        if 開催者メール and 情報.アドレス == 開催者メール:
            名前 = f"{名簿.organizer_name or '開催者'}(開催者)"
        else:
            名前 = 名前表.get(情報.アドレス, 情報.アドレス)
        行.append(f"{名前}: {_件名の表示(情報)}")
    if w.開催者が仮 and not 開催者メール:
        行.append("開催者(あなた): 仮の予定あり(名簿に開催者の記載が無いため件名は取りに行きません。ご自身のカレンダーを確認してください)")
    return 行


def _待つ(env: 実行環境, 依頼id: str, 対象: Dict[str, tuple]) -> Dict[str, wait_for.待ち結果]:
    """待ちの開始と進捗を、チャット(標準出力)とログの両方に出す(design.md#ログ)。"""
    logger.info("待ちの開始: 依頼ID=%s 対象=%s", 依頼id, "、".join(対象))

    def 進捗(文: str) -> None:
        env.出力(文)
        logger.info("待ちの進捗: 依頼ID=%s %s", 依頼id, 文)

    return wait_for.wait_for_all(対象, 間隔秒=env.設定.確認間隔秒, 進捗=進捗, 時計=env.時計, 待つ=env.待つ)


# ---------------------------------------------------------------------------
# submit
# ---------------------------------------------------------------------------

_曜日の別名 = {
    "月": 0, "火": 1, "水": 2, "木": 3, "金": 4, "土": 5, "日": 6,
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}


def 曜日を解釈(値: Optional[str]) -> Optional[tuple]:
    """`月,水` `mon,wed` `0,2` のいずれの書き方でも受け付ける。"""
    if not 値:
        return None
    結果 = []
    for 部分 in 値.replace("、", ",").split(","):
        部分 = 部分.strip().lower()
        if not 部分:
            continue
        if 部分.isdigit():
            結果.append(int(部分))
        elif 部分 in _曜日の別名:
            結果.append(_曜日の別名[部分])
        elif all(c in _曜日の別名 for c in 部分):  # 「月水金」のような連結
            結果.extend(_曜日の別名[c] for c in 部分)
        else:
            raise ValueError(f"曜日として解釈できません: {部分}")
    return tuple(dict.fromkeys(結果))


def _依頼内容の提示(依頼: dict, 参加者名: Sequence[str]) -> str:
    m = 依頼["meeting"]
    行 = [
        "【依頼内容の確認】",
        f"依頼ID: {依頼['requestId']}",
        f"件名: {m['subject']}",
        f"参加者({len(参加者名)}人): {', '.join(参加者名)}",
        f"所要時間: {m['durationMinutes']}分",
        f"探索条件: {request.条件の要約(依頼)}、提示する候補は最大{依頼['filter']['maxResults']}件",
        "アジェンダ: " + ("あり" if m.get("agenda") else "なし(会議本文には未定である旨を書きます)"),
    ]
    if 依頼.get("specified"):
        行.append(f"開催者が指定した項目: {', '.join(依頼['specified'])}(候補が0件のとき、指定した期間・時間帯は広げません)")
    return "\n".join(行)


def cmd_submit(args, env: 実行環境) -> int:
    設定値 = env.設定
    名簿 = None
    try:
        名簿 = roster.load(env.名簿ファイル())
    except roster.名簿エラー as e:
        env.出力(str(e))
        return 2
    解決 = 名簿.resolve(args.attendee)
    if not 解決.ok:
        logger.warning("名前の解決に失敗: %d件", len(解決.未解決))
        env.出力("名簿で解決できない名前があるため依頼を送りません: " + ", ".join(解決.未解決))
        env.出力("名簿に登録されている表記で指定し直してください(同じ名前が複数ある場合も解決できません)")
        return 2

    アジェンダ = args.agenda or ""
    if args.agenda_file:
        try:
            アジェンダ = Path(args.agenda_file).read_text(encoding="utf-8")
        except OSError as e:
            env.出力(f"アジェンダのファイルを読めません: {e}")
            return 2
    try:
        条件 = request.依頼条件(
            件名=args.subject,
            参加者=解決.解決済み,
            所要時間分=args.duration,
            アジェンダ=アジェンダ,
            期間開始=date.fromisoformat(args.start_date) if args.start_date else None,
            期間終了=date.fromisoformat(args.end_date) if args.end_date else None,
            時間帯開始=dtime.fromisoformat(args.time_start) if args.time_start else None,
            時間帯終了=dtime.fromisoformat(args.time_end) if args.time_end else None,
            候補件数=args.max_results,
            対象曜日=曜日を解釈(args.weekdays),
            全員空き=False if args.allow_partial else None,
        )
    except ValueError as e:
        env.出力(f"探索条件を解釈できません: {e}")
        return 2

    不備 = request.検証(条件, 設定値, env.今日)
    if 不備:
        env.出力("依頼を受け付けられません。次の項目を直してください:")
        for 項目 in 不備:
            env.出力(f"- {項目}")
        return 2

    依頼id = args.request_id or request.依頼idを生成(datetime.combine(env.今日, timeutil.now_jst().time(), tzinfo=timeutil.JST))
    依頼 = request.組み立て(条件, 設定値, env.今日, 依頼id)
    env.出力(_依頼内容の提示(依頼, [p["name"] for p in 解決.解決済み]))
    if args.dry_run:
        env.出力("(--dry-run のため依頼は書き出していません。内容に誤りがなければ --dry-run を外して実行してください)")
        return 0
    書き出し = request.書き出す(設定値, 依頼)
    if not 書き出し.ok:
        logger.error("台帳ファイルの書き出し失敗: 依頼ID=%s 種類=依頼", 依頼id)
        env.出力(書き出し.error)
        return 1
    logger.info(
        "依頼を書き出しました: 依頼ID=%s 試行=%d 参加者=%d人 条件=%s",
        依頼id, 1, len(解決.解決済み), request.条件の要約(依頼),
    )
    env.出力(f"依頼を書き出しました(依頼ID: {依頼id})。続けて `resume {依頼id}` で候補の到着を待ちます。")
    return 0


# ---------------------------------------------------------------------------
# resume
# ---------------------------------------------------------------------------


def _候補を待つ(env: 実行環境, 依頼id: str, 試行番号: int) -> wait_for.待ち結果:
    結果 = _待つ(env, 依頼id, {f"候補(試行{試行番号})": (ledger.候補ファイル(env.設定, 依頼id, 試行番号), env.設定.候補待ち上限秒)})
    return 結果[f"候補(試行{試行番号})"]


def _選択画面を用意(
    env: 実行環境,
    依頼: dict,
    セクション一覧: List[select_html.セクション],
    緩めた: bool,
    代替案要約: Optional[notify.代替案の要約],
    追記: Sequence[str] = (),
) -> int:
    設定値 = env.設定
    依頼id = 依頼["requestId"]
    候補件数 = sum(len(s.カード一覧) for s in セクション一覧)
    html = select_html.組み立てる(
        依頼id=依頼id,
        件名=依頼["meeting"]["subject"],
        所要時間分=依頼["meeting"]["durationMinutes"],
        参加者数=len(依頼["meeting"]["attendees"]),
        セクション一覧=セクション一覧,
        緩めた=緩めた,
    )
    書き出し = select_html.書き出して確認(設定値, 依頼id, html)
    if not 書き出し.ok:
        logger.error("台帳ファイルの書き出し失敗: 依頼ID=%s 種類=選択画面", 依頼id)
        env.出力(書き出し.error)
        return 1
    logger.info("選択画面を書き出しました: 依頼ID=%s 候補件数=%d 読み戻し確認=%s", 依頼id, 候補件数, 書き出し.確認済み)
    if 設定値.同期猶予秒 > 0:
        env.出力(f"選択画面を書き出しました。OneDriveの同期を{設定値.同期猶予秒}秒待ちます...")
        env.待つ(設定値.同期猶予秒)
    url = select_html.ビューアurlを組み立てる(設定値.ビューアurl, 設定値.サーバー相対パス, Path(書き出し.path).name)
    文 = notify.選択画面の通知文(依頼["meeting"]["subject"], 候補件数, url, 書き出し.path, 代替案要約)
    for 行 in 追記:
        文 += "\n" + 行
    通知 = notify.書き出す(設定値, 文)
    if not 通知.ok:
        logger.error("台帳ファイルの書き出し失敗: 依頼ID=%s 種類=通知", 依頼id)
        env.出力(f"Teams通知は書き出せませんでした({通知.error})。チャットの表示で続けます。")
    env.出力(文)
    env.出力(f"選択画面でコピーした1行をチャットに貼ってください(`select` で受け取ります)。依頼ID: {依頼id}")
    return 0


def _候補を処理(env: 実行環境, 依頼: dict, 候補内容: dict) -> int:
    依頼id = 依頼["requestId"]
    読み = candidates.読む(候補内容, 試行番号=1)
    if 読み.失敗:
        logger.error("フローからの失敗理由: 依頼ID=%s 理由=%s", 依頼id, 読み.失敗理由)
        env.出力(f"探索フローが失敗を返しました: {読み.失敗理由}")
        env.出力("フロー側の実行履歴を確認してください。条件を変えて依頼し直す場合は `submit` からやり直します。")
        return 1
    条件 = candidates.絞り込み条件.依頼から(依頼)
    結果 = candidates.絞り込む(読み, 条件)
    logger.info(
        "候補の絞り込み: 依頼ID=%s 受け取り=%d 採用=%d 内訳=%s",
        依頼id, 結果.受け取った件数, len(結果.採用), 結果.除外内訳,
    )
    if 結果.採用:
        セクション = select_html.セクション(
            見出し=見出し_既定, 条件=request.条件の要約(依頼),
            カード一覧=[select_html.カード(枠=w) for w in 結果.採用],
        )
        return _選択画面を用意(env, 依頼, [セクション], 緩めた=False, 代替案要約=None)
    env.出力(
        f"既定の条件では候補が0件でした(受け取った枠 {結果.受け取った件数}件"
        + (f"、フローの理由: {読み.枠が無かった理由}" if 読み.枠が無かった理由 else "")
        + ")。確認を挟まず2つの代替案を調べます。"
    )
    return _代替案を開始(env, 依頼, 読み)


def _代替案を開始(env: 実行環境, 依頼: dict, 読み: candidates.候補の読み取り) -> int:
    設定値 = env.設定
    依頼id = 依頼["requestId"]
    名簿 = _名簿を読む(env)
    条件 = candidates.絞り込み条件.依頼から(依頼)
    代替1 = request.代替案1を組み立てる(
        読み, 条件, 要求件数=int(依頼["search"]["maxCandidates"]),
        開催者メール=名簿.organizer_email if 名簿 else None,
    )
    待ち対象: Dict[str, tuple] = {}
    伝える: List[str] = []

    if 代替1.採用 and 代替1.件名を取りに行く対象:
        書き出し = detail.書き出す(設定値, detail.依頼を組み立てる(依頼id, 代替1.採用, 代替1.件名を取りに行く対象))
        if 書き出し.ok:
            待ち対象["予定詳細"] = (ledger.予定詳細ファイル(設定値, 依頼id), 設定値.予定詳細待ち上限秒)
        else:
            logger.error("台帳ファイルの書き出し失敗: 依頼ID=%s 種類=予定詳細の依頼", 依頼id)
            伝える.append(f"仮の予定の件名は取りに行けませんでした({書き出し.error})。件名なしで示します。")

    代替2依頼 = request.代替案2の依頼を組み立てる(依頼, 設定値, env.今日)
    if 代替2依頼 is not None:
        書き出し = request.書き出す(設定値, 代替2依頼)
        if 書き出し.ok:
            logger.info("依頼を書き出しました: 依頼ID=%s 試行=2 条件=%s", 依頼id, request.条件の要約(代替2依頼))
            待ち対象["代替案2の候補"] = (ledger.候補ファイル(設定値, 依頼id, 2), 設定値.候補待ち上限秒)
        else:
            logger.error("台帳ファイルの書き出し失敗: 依頼ID=%s 種類=依頼(試行2)", 依頼id)
            伝える.append(f"代替案2の依頼を書き出せませんでした({書き出し.error})。")

    if not 待ち対象 and not 代替1.採用:
        return _相談(env, 依頼, 代替2依頼 if 代替2依頼 is not None and ledger.依頼ファイル(設定値, 依頼id, 2).is_file() else None, 代替1.打ち切りの可能性, 伝える)

    if 待ち対象:
        env.出力("代替案の結果を待ちます(既定の依頼の直後に続くため、往復が伸びて上限で打ち切られることがあります。打ち切られても `resume` で続きから再開できます)。")
        _待つ(env, 依頼id, 待ち対象)
    return _代替案をまとめる(env, 依頼, 伝える)


def _相談(env: 実行環境, 依頼: dict, 代替2依頼: Optional[dict], 打ち切りの可能性: bool, 伝える: Sequence[str]) -> int:
    一覧 = request.試した条件(依頼, 代替2依頼)
    logger.warning("どちらの代替案も0件: 依頼ID=%s 試した条件=%d通り", 依頼["requestId"], len(一覧))
    env.出力("候補が見つかりませんでした。試した条件:")
    for 行 in 一覧:
        env.出力(f"- {行}")
    広げなかった = request.広げなかった項目(依頼)
    if 広げなかった:
        env.出力(f"依頼時に指定されていたため広げなかった項目: {'・'.join(広げなかった)}")
    if 打ち切りの可能性:
        env.出力("※ 探索の応答が要求した件数で打ち切られている可能性があります(打ち切られた集合の外の枠は代替案1に現れません)")
    for 行 in 伝える:
        env.出力(行)
    env.出力("これ以上は自動で条件を緩めません。参加者・期間・所要時間のどれを緩めるかを決めて、`submit` で依頼し直してください。")
    return 0


def _代替案をまとめる(env: 実行環境, 依頼: dict, 伝える: Optional[List[str]] = None) -> int:
    """代替案の台帳から代替案1と代替案2の両方を絞り直し、1枚の選択画面にまとめる(design.md 手順7・12)。"""
    設定値 = env.設定
    依頼id = 依頼["requestId"]
    伝える = list(伝える or [])
    名簿 = _名簿を読む(env)
    名前表 = _名前表(依頼)
    条件 = candidates.絞り込み条件.依頼から(依頼)

    候補1 = ledger.read_json(ledger.候補ファイル(設定値, 依頼id, 1))
    読み1 = candidates.読む(候補1, 試行番号=1) if 候補1 is not None else candidates.候補の読み取り(依頼id, 1, [], "", "")
    代替1 = request.代替案1を組み立てる(
        読み1, 条件, 要求件数=int(依頼["search"]["maxCandidates"]),
        開催者メール=名簿.organizer_email if 名簿 else None,
    )

    詳細 = None
    if ledger.予定詳細依頼ファイル(設定値, 依頼id).is_file():
        内容 = ledger.read_json(ledger.予定詳細ファイル(設定値, 依頼id))
        if 内容 is None:
            伝える.append("仮の予定の件名(予定詳細)は待ち上限内に届かなかったため、件名なしで示しています。`resume` で再開すると取り直せます。")
        else:
            詳細 = detail.読む(内容)
            if 詳細.失敗:
                logger.error("フローからの失敗理由: 依頼ID=%s 理由=%s", 依頼id, 詳細.失敗理由)
                伝える.append(f"予定詳細フローが失敗を返したため件名なしで示しています: {詳細.失敗理由}")
            else:
                logger.info("予定詳細の取得: 依頼ID=%s 対象=%d人 件名取得=%d人", 依頼id, len(詳細.参加者ごと), detail.件名を取得できた人数(詳細))
    仮の予定の行: List[str] = []
    カード1 = []
    for i, w in enumerate(代替1.採用, start=1):
        表示 = _仮の予定の表示(w, 詳細, 名前表, 名簿)
        カード1.append(select_html.カード(枠=w, 仮の予定=表示))
        for s in 表示:
            仮の予定の行.append(f"候補{i} {_枠の表示(w)}: {s}")

    代替2依頼 = ledger.read_json(ledger.依頼ファイル(設定値, 依頼id, 2))
    代替2件数: Optional[int] = None
    代替2理由 = ""
    カード2 = []
    if 代替2依頼 is not None:
        候補2 = ledger.read_json(ledger.候補ファイル(設定値, 依頼id, 2))
        if 候補2 is None:
            代替2理由 = "待ち上限内に候補が届かなかったため打ち切りました。`resume` で再開すると続きから待てます。"
        else:
            読み2 = candidates.読む(候補2, 試行番号=2)
            if 読み2.失敗:
                logger.error("フローからの失敗理由: 依頼ID=%s 理由=%s(代替案2)", 依頼id, 読み2.失敗理由)
                代替2理由 = f"探索フローが失敗を返しました: {読み2.失敗理由}"
            else:
                結果2 = candidates.絞り込む(読み2, candidates.絞り込み条件.依頼から(代替2依頼))
                代替2件数 = len(結果2.採用)
                カード2 = [select_html.カード(枠=w) for w in 結果2.採用]
    logger.info(
        "代替案の提示: 依頼ID=%s 代替案1=%d件 代替案2=%s 代替案2を作った=%s",
        依頼id, len(カード1), 代替2件数 if 代替2件数 is not None else "-", 代替2依頼 is not None,
    )

    セクション一覧 = [select_html.セクション(見出し=見出し_代替案1, 条件=条件_代替案1, カード一覧=カード1)]
    if 代替2依頼 is not None:
        条件文 = request.条件の要約(代替2依頼) + (f"(得られませんでした: {代替2理由})" if 代替2理由 else "")
        セクション一覧.append(select_html.セクション(見出し=見出し_代替案2, 条件=条件文, カード一覧=カード2))

    if not カード1 and not カード2:
        if 代替2依頼 is not None and 代替2理由:
            伝える.append(f"代替案2: {代替2理由}")
        return _相談(env, 依頼, 代替2依頼, 代替1.打ち切りの可能性, 伝える)

    要約 = notify.代替案の要約(
        代替案1件数=len(カード1),
        代替案1の仮の予定=仮の予定の行,
        代替案2件数=代替2件数,
        代替案2の条件=request.条件の要約(代替2依頼) if 代替2依頼 is not None else "",
        代替案2が得られなかった理由=代替2理由,
        打ち切りの可能性=代替1.打ち切りの可能性,
        広げなかった項目=request.広げなかった項目(依頼),
    )
    return _選択画面を用意(env, 依頼, セクション一覧, 緩めた=True, 代替案要約=要約, 追記=伝える)


def _作成失敗を伝える(env: 実行環境, 状態: progress.進行状態, 依頼id: str) -> int:
    logger.error("フローからの失敗理由: 依頼ID=%s 理由=%s(作成結果 再試行%d)", 依頼id, 状態.失敗理由, 状態.再試行番号)
    枠 = selection.選択した枠(状態.選択結果)
    env.出力("【会議の作成に失敗しました】" + (f"(枠: {枠})" if 枠 else ""))
    env.出力(f"失敗理由: {状態.失敗理由}")
    env.出力(再試行の案内.replace("<依頼ID>", 依頼id))
    return 0


def _完了を伝える(env: 実行環境, 作成内容: dict, 通知する: bool) -> int:
    r = result_mod.読む(作成内容)
    直リンク = result_mod.会議オプション直リンク(r.会議本文)
    if 直リンク is None:
        logger.warning("直リンクを取り出せない: 依頼ID=%s", r.依頼id)
    logger.info("会議の作成完了: 依頼ID=%s 会議ID=%s", r.依頼id, r.会議id)
    文 = notify.完了の通知文(r, 直リンク)
    if 通知する:
        通知 = notify.書き出す(env.設定, 文)
        if not 通知.ok:
            logger.error("台帳ファイルの書き出し失敗: 依頼ID=%s 種類=通知", r.依頼id)
            env.出力(f"Teams通知は書き出せませんでした({通知.error})。チャットの表示で続けます。")
    env.出力(文)
    return 0


def _作成結果を待つ(env: 実行環境, 依頼id: str, 再試行番号: int) -> int:
    結果 = _待つ(env, 依頼id, {"作成結果": (ledger.作成結果ファイル(env.設定, 依頼id, 再試行番号), env.設定.作成結果待ち上限秒)})["作成結果"]
    if 結果.打ち切り:
        logger.warning("待ち上限で打ち切り: 依頼ID=%s 対象=作成結果 経過=%d秒", 依頼id, 結果.経過秒)
        env.出力(打ち切りの案内.replace("<依頼ID>", 依頼id))
        return 0
    状態 = progress.判定(env.設定, 依頼id)
    if 状態.状態 == progress.作成失敗:
        return _作成失敗を伝える(env, 状態, 依頼id)
    return _完了を伝える(env, 結果.内容, 通知する=True)


def cmd_resume(args, env: 実行環境) -> int:
    設定値 = env.設定
    依頼id = args.request_id
    状態 = progress.判定(設定値, 依頼id)
    env.出力(f"依頼ID {依頼id} の状態: {状態.状態}")

    if 状態.状態 == progress.存在しない:
        env.出力("この依頼IDの依頼ファイルが見つかりません。依頼IDを確かめてください。")
        return 2
    if 状態.状態 == progress.作成済み:
        return _完了を伝える(env, 状態.作成結果, 通知する=False)
    if 状態.状態 == progress.作成失敗:
        return _作成失敗を伝える(env, 状態, 依頼id)
    if 状態.状態 == progress.選択済み:
        return _作成結果を待つ(env, 依頼id, 状態.再試行番号)

    依頼 = ledger.read_json(ledger.依頼ファイル(設定値, 依頼id, 1))
    if 依頼 is None:
        env.出力("依頼ファイルを読めません。")
        return 1

    if 状態.状態 == progress.依頼済み:
        待ち = _候補を待つ(env, 依頼id, 1)
        if 待ち.打ち切り:
            logger.warning("待ち上限で打ち切り: 依頼ID=%s 対象=候補 経過=%d秒", 依頼id, 待ち.経過秒)
            env.出力(打ち切りの案内.replace("<依頼ID>", 依頼id))
            return 0
        return _候補を処理(env, 依頼, 待ち.内容)

    if 状態.状態 == progress.候補到着:
        return _候補を処理(env, 依頼, ledger.read_json(ledger.候補ファイル(設定値, 依頼id, 1)))

    if 状態.状態 == progress.代替案の提示中:
        待ち対象: Dict[str, tuple] = {}
        if 状態.予定詳細を待つ:
            待ち対象["予定詳細"] = (ledger.予定詳細ファイル(設定値, 依頼id), 設定値.予定詳細待ち上限秒)
        if 状態.代替案2の候補を待つ:
            待ち対象["代替案2の候補"] = (ledger.候補ファイル(設定値, 依頼id, 2), 設定値.候補待ち上限秒)
        _待つ(env, 依頼id, 待ち対象)
        return _代替案をまとめる(env, 依頼)

    # 代替案の提示済み
    return _代替案をまとめる(env, 依頼)


# ---------------------------------------------------------------------------
# select / retry-create
# ---------------------------------------------------------------------------


def cmd_select(args, env: 実行環境) -> int:
    設定値 = env.設定
    行 = selection.読み取る(" ".join(args.text))
    if 行 is None:
        logger.warning("選択結果の読み取りに失敗: 種類=読み取れない")
        env.出力("選択結果として読み取れませんでした。選択画面の「選択結果をコピー」でコピーした1行をそのまま貼ってください。")
        return 2
    依頼id = 行.依頼id
    判定 = selection.書き出せるか(設定値, 依頼id)
    if 判定.種別 == selection.作成済み:
        env.出力("この依頼の会議は既に作成済みです。作り直しません。")
        return _完了を伝える(env, 判定.作成結果, 通知する=False)
    if 判定.種別 == selection.作成失敗:
        return _作成失敗を伝える(env, progress.判定(設定値, 依頼id), 依頼id)
    if 判定.種別 == selection.選択結果あり:
        env.出力("この依頼の選択結果は既に書き出されています(二重に作成しません)。作成結果の到着を待ちます。")
        return _作成結果を待つ(env, 依頼id, 判定.再試行番号)

    突き合わせ = selection.突き合わせる(設定値, 行)
    if not 突き合わせ.ok:
        logger.warning("選択結果の読み取りに失敗: 依頼ID=%s 種類=候補と不一致", 依頼id)
        env.出力(突き合わせ.error)
        return 2
    依頼 = ledger.read_json(ledger.依頼ファイル(設定値, 依頼id, 1))
    if 依頼 is None:
        env.出力(f"依頼ID {依頼id} の依頼ファイルが見つかりません。")
        return 2
    書き出し = selection.書き出す(設定値, selection.選択結果を組み立てる(依頼, 突き合わせ.枠))
    if not 書き出し.ok:
        logger.error("台帳ファイルの書き出し失敗: 依頼ID=%s 種類=選択結果", 依頼id)
        env.出力(書き出し.error)
        return 1
    logger.info("選択結果を書き出しました: 依頼ID=%s 候補番号=%d", 依頼id, 行.候補番号)
    if detail.削除(設定値, 依頼id):
        logger.info("予定詳細ファイルを削除しました: 依頼ID=%s", 依頼id)
    env.出力(f"候補{行.候補番号}({_枠の表示(突き合わせ.枠)})で選択結果を書き出しました。作成フローの結果を待ちます。")
    return _作成結果を待つ(env, 依頼id, 0)


def cmd_retry_create(args, env: 実行環境) -> int:
    設定値 = env.設定
    依頼id = args.request_id
    判定 = selection.書き出せるか(設定値, 依頼id)
    if 判定.種別 != selection.作成失敗:
        env.出力(f"依頼ID {依頼id} には失敗した作成結果が無いため、再試行は行いません(状態: {判定.種別})。")
        return 0
    env.出力(再試行の案内.replace("<依頼ID>", 依頼id))
    書き出し = selection.再試行を書き出す(設定値, 依頼id)
    if not 書き出し.ok:
        env.出力(書き出し.error)
        return 1
    logger.info("選択結果を書き出しました(再試行): 依頼ID=%s 再試行=%d", 依頼id, 書き出し.再試行番号)
    env.出力(f"再試行番号 {書き出し.再試行番号} の選択結果を書き出しました。作成フローの結果を待ちます。")
    return _作成結果を待つ(env, 依頼id, 書き出し.再試行番号)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="main.py", description="空き時間からの会議候補提示とTeams会議の自動作成")
    p.add_argument("--today", help=argparse.SUPPRESS)  # テスト用: 当日の日付(YYYY-MM-DD)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("submit", help="依頼を組み立てて書き出す")
    s.add_argument("--subject", required=True)
    s.add_argument("--attendee", action="append", required=True, help="参加者の名前(名簿の表記)。繰り返し指定")
    s.add_argument("--duration", type=int, required=True, help="所要時間(分)")
    s.add_argument("--agenda", help="アジェンダの原文")
    s.add_argument("--agenda-file", help="アジェンダの原文を書いたファイル")
    s.add_argument("--start-date", help="探索期間の開始日(YYYY-MM-DD)")
    s.add_argument("--end-date", help="探索期間の終了日(YYYY-MM-DD)")
    s.add_argument("--time-start", help="時間帯の開始(HH:MM)")
    s.add_argument("--time-end", help="時間帯の終了(HH:MM)")
    s.add_argument("--max-results", type=int, help="提示する候補の上限件数")
    s.add_argument("--weekdays", help="対象とする曜日(例: 月,水,金 / mon,wed / 0,2,4)")
    s.add_argument("--allow-partial", action="store_true", help="一部不在の枠も候補に含める")
    s.add_argument("--dry-run", action="store_true", help="書き出さずに依頼の内容だけを返す")
    s.add_argument("--request-id", help=argparse.SUPPRESS)  # テスト用
    s.set_defaults(func=cmd_submit)

    r = sub.add_parser("resume", help="依頼IDの続きを進める(候補の待ち・絞り込み・選択画面・作成結果の待ち)")
    r.add_argument("request_id")
    r.set_defaults(func=cmd_resume)

    se = sub.add_parser("select", help="貼られた選択結果を受け取り、会議の作成まで進める")
    se.add_argument("text", nargs="+", help="選択画面でコピーした1行")
    se.set_defaults(func=cmd_select)

    rc = sub.add_parser("retry-create", help="失敗した会議の作成を同じ枠でやり直す")
    rc.add_argument("request_id")
    rc.set_defaults(func=cmd_retry_create)
    return p


def main(argv: Optional[Sequence[str]] = None, env: Optional[実行環境] = None) -> int:
    args = parser().parse_args(argv)
    if env is None:
        try:
            設定値 = config.load()
        except config.設定エラー as e:
            print(str(e))
            return 2
        env = 実行環境(設定=設定値, 今日=timeutil.now_jst().date())
    if args.today:
        env.今日 = date.fromisoformat(args.today)
    ログを設定(env.設定)
    try:
        return args.func(args, env)
    except Exception:  # 想定外の例外は経過をそのまま出して終了する(台帳は残る)
        logger.error("想定外の例外:\n%s", traceback.format_exc())
        env.出力("想定外のエラーで終了しました。台帳ファイルは残っているため、同じ依頼IDで `resume` から再開できます。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
