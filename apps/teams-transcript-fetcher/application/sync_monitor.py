"""OneDrive同期停滞の検知・自動復旧・監視通知。

「Macは起きているのに同期だけが止まる」事態を、Power Automateが15分間隔で書く
ハートビートファイルの鮮度で検知し、OneDrive同期クライアントを再起動する。
**判定を誤ると正常な同期クライアントを再起動してしまう**ため、迷ったら
「停滞ではない側(再起動しない側)」に倒すのが全体を貫く方針
(requirements.md#ハートビートの異常値の扱い)。

監視の記録は同期フォルダの**外**の `monitoring.json` に持つ。停滞の最中でも
読み書きできる必要があるため(requirements.md#記録 [2])。

対応する仕様: apps/teams-transcript-fetcher/specs/sync-stall-recovery/
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import config
import state

logger = logging.getLogger(__name__)

#: 疎通確認の接続先。**コードに固定したホストのみ**へ接続する(design.md#セキュリティ)。
疎通確認ホスト = "login.microsoftonline.com"
疎通確認ポート = 443

#: 再起動対象のプロセス名。完全一致で特定する(design.md#セキュリティ)。
onedriveプロセス名 = "OneDrive"

#: 通常終了を待つ間のプロセス生存確認の間隔。
_終了確認の間隔秒 = 2

#: ハートビートが読めない理由の区別。停滞判定を止める判断とログの根拠に使う。
種別_存在しない = "存在しない"
種別_読めない = "読めない"
種別_解釈不能 = "解釈不能"

#: 通知する事象の種別(requirements.md#監視通知 [2])。
事象_同期停滞 = "同期停滞"
事象_復旧失敗 = "復旧失敗"
事象_ダウンロード失敗の連続 = "ダウンロード失敗の連続"
事象_台帳読み取り失敗の連続 = "台帳読み取り失敗の連続"
事象_url読み取り失敗の連続 = "URL読み取り失敗の連続"
事象_異常終了の連続 = "バッチ異常終了の連続"


@dataclass(frozen=True)
class 読めないハートビート:
    種別: str
    理由: str


@dataclass(frozen=True)
class 再起動結果:
    成功: bool
    経過: str


@dataclass(frozen=True)
class 通知事象:
    """通知ファイル1件分の材料。

    即時の事象(再起動した)は24時間ごとの抑止対象ではなく、書き出しに成功する
    まで次サイクル以降も再試行される(停滞イベント側の再起動通知済みで管理)。
    継続型の事象(復旧失敗・失敗の連続)はキーで通知済み記録と突き合わせ、
    24時間ごとの再通知に抑える(requirements.md#通知の抑止と限界 [1])。
    """

    種別: str
    キー: str
    検知時刻: datetime
    要点: str
    即時: bool = False


@dataclass
class 停滞イベント:
    """停滞判定が始まってから鮮度が閾値内へ戻るまでの1つの停滞
    (requirements.md#再起動の回数制限 [2])。"""

    開始時刻: datetime
    再起動時刻: datetime | None = None
    復旧失敗判定済み: bool = False
    再起動要点: str | None = None
    再起動通知済み: bool = False


@dataclass
class 監視記録:
    """サイクルを越えて持つ監視の記憶(design.md#状態管理)。"""

    前回実行時刻: datetime | None = None
    復帰時刻: datetime | None = None
    停滞イベント: 停滞イベント | None = None
    再起動履歴: list[datetime] = field(default_factory=list)
    通知済み事象: dict[str, datetime] = field(default_factory=dict)
    異常終了の連続回数: int = 0


def _日時を読む(値: object) -> datetime | None:
    if not isinstance(値, str) or not 値:
        return None
    try:
        読んだ日時 = datetime.fromisoformat(値)
    except ValueError:
        return None
    if 読んだ日時.tzinfo is None:
        return 読んだ日時.replace(tzinfo=timezone.utc)
    return 読んだ日時.astimezone(timezone.utc)


def 読み込む(監視記録ファイル: Path) -> 監視記録:
    """監視記録を読む。読めない場合は空として扱い、警告を残して続行する。

    記録が失われると回数制限・通知抑止の記憶も失われるが、上限は24時間2回と
    安全側のため許容する(design.md#エラーハンドリング)。
    """
    try:
        中身 = json.loads(監視記録ファイル.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return 監視記録()
    except (json.JSONDecodeError, OSError) as 例外:
        logger.warning("監視記録を読めないため空として扱う: %s: %s", 監視記録ファイル, 例外)
        return 監視記録()

    if not isinstance(中身, dict):
        logger.warning("監視記録の形式が想定と違うため空として扱う: %s", 監視記録ファイル)
        return 監視記録()

    イベントの中身 = 中身.get("stall_event")
    イベント = None
    if isinstance(イベントの中身, dict):
        開始時刻 = _日時を読む(イベントの中身.get("started_at"))
        if 開始時刻 is not None:
            イベント = 停滞イベント(
                開始時刻=開始時刻,
                再起動時刻=_日時を読む(イベントの中身.get("restarted_at")),
                復旧失敗判定済み=bool(イベントの中身.get("recovery_failed")),
                再起動要点=イベントの中身.get("restart_notice") or None,
                再起動通知済み=bool(イベントの中身.get("restart_notified")),
            )

    通知済み = {}
    for キー, 値 in (中身.get("notified") or {}).items():
        日時 = _日時を読む(値)
        if 日時 is not None:
            通知済み[キー] = 日時

    return 監視記録(
        前回実行時刻=_日時を読む(中身.get("last_run_at")),
        復帰時刻=_日時を読む(中身.get("resumed_at")),
        停滞イベント=イベント,
        再起動履歴=[
            日時
            for 日時 in (_日時を読む(値) for 値 in (中身.get("restarts") or []))
            if 日時 is not None
        ],
        通知済み事象=通知済み,
        異常終了の連続回数=int(中身.get("consecutive_failures") or 0),
    )


def 保存する(記録: 監視記録, 監視記録ファイル: Path, 現在時刻: datetime) -> None:
    """監視記録を保存する。一時ファイルへ書いてから所定の名前へ移す
    (途中で失敗しても既存の記録を壊さない。design.md#エラーハンドリング)。

    回数制限の判定に使うのは直近24時間だけなので、それより古い再起動履歴は
    保存時に捨てる(design.md#状態管理)。
    """
    残す履歴 = [
        日時 for 日時 in 記録.再起動履歴 if 現在時刻 - 日時 < timedelta(hours=24)
    ]
    書き出す中身 = {
        "last_run_at": 記録.前回実行時刻.isoformat() if 記録.前回実行時刻 else None,
        "resumed_at": 記録.復帰時刻.isoformat() if 記録.復帰時刻 else None,
        "stall_event": (
            {
                "started_at": 記録.停滞イベント.開始時刻.isoformat(),
                "restarted_at": (
                    記録.停滞イベント.再起動時刻.isoformat()
                    if 記録.停滞イベント.再起動時刻
                    else None
                ),
                "recovery_failed": 記録.停滞イベント.復旧失敗判定済み,
                "restart_notice": 記録.停滞イベント.再起動要点,
                "restart_notified": 記録.停滞イベント.再起動通知済み,
            }
            if 記録.停滞イベント
            else None
        ),
        "restarts": [日時.isoformat() for 日時 in 残す履歴],
        "notified": {キー: 日時.isoformat() for キー, 日時 in 記録.通知済み事象.items()},
        "consecutive_failures": 記録.異常終了の連続回数,
    }

    文字列 = json.dumps(書き出す中身, ensure_ascii=False, indent=2)

    監視記録ファイル.parent.mkdir(parents=True, exist_ok=True)
    一時ファイル = 監視記録ファイル.with_name(監視記録ファイル.name + ".tmp")
    try:
        一時ファイル.write_text(文字列, encoding="utf-8")
        os.replace(一時ファイル, 監視記録ファイル)
    finally:
        一時ファイル.unlink(missing_ok=True)


def ハートビートを読む(パス: Path) -> datetime | 読めないハートビート:
    """ハートビートファイルの記載時刻を読む。

    本文は外部由来の文字列として扱い、「ISO 8601の日時文字列1つ」だけを受け付ける
    (design.md#バリデーション、design.md#セキュリティ)。
    """
    try:
        本文 = パス.read_text(encoding="utf-8")
    except FileNotFoundError:
        return 読めないハートビート(種別=種別_存在しない, 理由="ファイルが存在しない")
    except (OSError, UnicodeDecodeError) as 例外:
        return 読めないハートビート(種別=種別_読めない, 理由=str(例外))

    時刻 = _日時を読む(本文.strip())
    if 時刻 is None:
        return 読めないハートビート(
            種別=種別_解釈不能, 理由="本文を日時として解釈できない"
        )
    return 時刻


def 鮮度を求める(記載時刻: datetime, 現在時刻: datetime) -> timedelta:
    """ハートビートの鮮度(記載時刻と現在時刻の差)を返す。

    記載時刻が未来の場合(時計ずれ)は鮮度0とみなし、停滞ではない側に倒す
    (requirements.md#ハートビートの異常値の扱い [3])。
    """
    return max(現在時刻 - 記載時刻, timedelta(0))


def 中断からの復帰か(記録: 監視記録, 現在時刻: datetime, 設定: config.設定) -> bool:
    """スリープ等による実行の中断からの復帰を検知し、復帰時刻を更新する。

    前回実行時刻が無い場合(初回・監視記録の消失)も復帰とみなす
    (design.md#同期停滞の判定)。
    """
    if 記録.前回実行時刻 is not None and 現在時刻 - 記録.前回実行時刻 <= timedelta(
        minutes=設定.実行中断とみなす間隔分
    ):
        return False
    記録.復帰時刻 = 現在時刻
    return True


def 復帰猶予中か(記録: 監視記録, 現在時刻: datetime, 設定: config.設定) -> bool:
    """復帰直後の判定スキップ期間かを返す。

    復帰直後はハートビートが古いのが正常のため、猶予中は停滞判定をしない
    (requirements.md#スリープ復帰直後の誤検知防止 [2])。
    """
    if 記録.復帰時刻 is None:
        return False
    return 現在時刻 - 記録.復帰時刻 <= timedelta(minutes=設定.復帰後の猶予分)


def 疎通があるか(
    設定: config.設定,
    接続する: Callable = socket.create_connection,
) -> bool:
    """M365エンドポイントへのTCP接続で疎通を確認する。

    ネットワーク断はOneDrive再起動では直らない別の異常のため、不通の間は
    停滞と判定しない材料になる(requirements.md#停滞判定の閾値 [2])。
    """
    try:
        接続 = 接続する((疎通確認ホスト, 疎通確認ポート), 設定.疎通タイムアウト秒)
        接続.close()
        return True
    except OSError as 例外:
        logger.info("M365エンドポイントへ疎通できない: %s", 例外)
        return False


def _プロセスを探す(実行する: Callable) -> list[str]:
    """OneDriveのプロセスIDの一覧を返す。名前の完全一致で特定する。"""
    結果 = 実行する(
        ["pgrep", "-x", onedriveプロセス名], capture_output=True, text=True
    )
    if 結果.returncode != 0:
        return []
    return [行 for 行 in 結果.stdout.split() if 行]


def onedriveを再起動する(
    設定: config.設定,
    実行する: Callable = subprocess.run,
    待つ: Callable = time.sleep,
) -> 再起動結果:
    """OneDrive同期クライアントを再起動する。

    通常終了(SIGTERM)を試みて最大30秒待ち、残っていれば強制終了(SIGKILL)する。
    シェルを介さず引数の配列で実行する(design.md#OneDriveの再起動と復旧確認、
    design.md#セキュリティ)。
    """
    プロセスたち = _プロセスを探す(実行する)
    if プロセスたち:
        実行する(["kill", "-TERM", *プロセスたち], capture_output=True, text=True)
        待った秒 = 0
        while 待った秒 < 設定.通常終了を待つ秒:
            待つ(_終了確認の間隔秒)
            待った秒 += _終了確認の間隔秒
            プロセスたち = _プロセスを探す(実行する)
            if not プロセスたち:
                break
        if プロセスたち:
            実行する(["kill", "-KILL", *プロセスたち], capture_output=True, text=True)
            経過 = "強制終了ののち起動"
        else:
            経過 = "通常終了ののち起動"
    else:
        経過 = "プロセス不在のため起動のみ"

    起動 = 実行する(
        ["open", "-gja", onedriveプロセス名], capture_output=True, text=True
    )
    if 起動.returncode != 0:
        return 再起動結果(成功=False, 経過=f"{経過}(起動に失敗: {起動.returncode})")
    return 再起動結果(成功=True, 経過=経過)


def 停滞を判定する(
    記録: 監視記録,
    設定: config.設定,
    現在時刻: datetime,
    疎通確認: Callable[[], bool] | None = None,
    再起動する: Callable[[], 再起動結果] | None = None,
) -> list[通知事象]:
    """毎サイクルの冒頭で停滞判定と復旧を進め、通知すべき事象を返す。

    design.md#同期停滞の判定の手順1〜7と、design.md#OneDriveの再起動と復旧確認の
    手順1〜5を統合する中心関数。判定の結果によらず前回実行時刻を更新する(手順7)。
    """
    if 疎通確認 is None:
        疎通確認 = lambda: 疎通があるか(設定)  # noqa: E731
    if 再起動する is None:
        再起動する = lambda: onedriveを再起動する(設定)  # noqa: E731

    try:
        return _停滞を判定する(記録, 設定, 現在時刻, 疎通確認, 再起動する)
    finally:
        記録.前回実行時刻 = 現在時刻


def _停滞を判定する(
    記録: 監視記録,
    設定: config.設定,
    現在時刻: datetime,
    疎通確認: Callable[[], bool],
    再起動する: Callable[[], 再起動結果],
) -> list[通知事象]:
    if 中断からの復帰か(記録, 現在時刻, 設定):
        空白の表示 = (
            "初回(前回実行時刻なし)"
            if 記録.前回実行時刻 is None
            else f"{(現在時刻 - 記録.前回実行時刻).total_seconds() / 60:.0f}分"
        )
        logger.info(
            "実行の中断からの復帰を検知: 空白=%s 猶予の終了=%s",
            空白の表示,
            (現在時刻 + timedelta(minutes=設定.復帰後の猶予分)).isoformat(),
        )

    if 復帰猶予中か(記録, 現在時刻, 設定):
        logger.info("停滞判定: 復帰猶予中のためスキップ(復帰=%s)", 記録.復帰時刻)
        return []

    読んだ = ハートビートを読む(設定.ハートビートファイル)
    if isinstance(読んだ, 読めないハートビート):
        # 判定を止めるのは、ハートビートフローが未構築・故障している期間に正常な
        # 同期クライアントを誤って再起動しないため。この間は停滞検知が働かないので、
        # 警告で残して後から確認できるようにする
        # (requirements.md#ハートビートの異常値の扱い [1] [2])。
        logger.warning(
            "ハートビートが%s: %s: %s(停滞の判定を行わない)",
            読んだ.種別,
            設定.ハートビートファイル,
            読んだ.理由,
        )
        return []

    鮮度 = 鮮度を求める(読んだ, 現在時刻)
    鮮度の表示 = f"{鮮度.total_seconds() / 60:.0f}分"

    if 鮮度 <= timedelta(minutes=設定.停滞判定しきい値分):
        事象たち: list[通知事象] = []
        if 記録.停滞イベント is not None:
            if (
                not 記録.停滞イベント.再起動通知済み
                and 記録.停滞イベント.再起動要点
                and 記録.停滞イベント.再起動時刻 is not None
            ):
                # 解消する前に、まだ書き出せていない再起動通知があれば最後に積む
                # (design.md#エラーハンドリング: 失敗した書き出しは次サイクルで再試行する)。
                事象たち.append(
                    通知事象(
                        種別=事象_同期停滞,
                        キー=事象_同期停滞,
                        検知時刻=記録.停滞イベント.再起動時刻,
                        要点=記録.停滞イベント.再起動要点,
                        即時=True,
                    )
                )
            logger.info(
                "停滞イベントが解消した: 開始=%s 鮮度=%s",
                記録.停滞イベント.開始時刻,
                鮮度の表示,
            )
            記録.停滞イベント = None
        logger.info("停滞判定: 正常(鮮度=%s)", 鮮度の表示)
        return 事象たち

    if not 疎通確認():
        # ネットワーク断はOneDrive再起動では直らない別の異常。再起動も停滞の
        # 通知もしない(requirements.md#同期停滞の検知 [3])。
        logger.info("停滞判定: 鮮度=%s だがネットワーク不通のため停滞と判定しない", 鮮度の表示)
        return []

    logger.info("停滞判定: 停滞(鮮度=%s・疎通あり)", 鮮度の表示)
    if 記録.停滞イベント is None:
        記録.停滞イベント = 停滞イベント(開始時刻=現在時刻)

    return _復旧を進める(記録, 設定, 現在時刻, 再起動する, 鮮度の表示)


def _復旧を進める(
    記録: 監視記録,
    設定: config.設定,
    現在時刻: datetime,
    再起動する: Callable[[], 再起動結果],
    鮮度の表示: str,
) -> list[通知事象]:
    """再起動と復旧確認(design.md#OneDriveの再起動と復旧確認 手順1〜5)。

    「同期停滞を検知して再起動した」の即時通知は、書き出しに成功するまで
    (通知を評価するが再起動通知済みを立てるまで)ここで積み続け、次サイクル
    以降も再試行する。再起動そのものはイベントにつき1回に留める
    (requirements.md#再起動の回数制限)。
    """
    イベント = 記録.停滞イベント
    復旧失敗の事象 = lambda 要点: 通知事象(  # noqa: E731
        種別=事象_復旧失敗, キー=事象_復旧失敗, 検知時刻=現在時刻, 要点=要点
    )

    def 再起動通知を積む(事象たち: list[通知事象]) -> list[通知事象]:
        if (
            イベント.再起動時刻 is not None
            and not イベント.再起動通知済み
            and イベント.再起動要点
        ):
            事象たち.append(
                通知事象(
                    種別=事象_同期停滞,
                    キー=事象_同期停滞,
                    検知時刻=イベント.再起動時刻,
                    要点=イベント.再起動要点,
                    即時=True,
                )
            )
        return 事象たち

    if イベント.復旧失敗判定済み:
        # 判定済みの間は事象を出し続ける。継続の通知は評価側が24時間ごとに抑える。
        return 再起動通知を積む([復旧失敗の事象(f"復旧失敗が継続中(鮮度={鮮度の表示})")])

    if イベント.再起動時刻 is not None:
        経過 = 現在時刻 - イベント.再起動時刻
        if 経過 <= timedelta(minutes=設定.復旧確認しきい値分):
            # 回復を待つ。未書き出しの再起動通知があれば再試行する。
            return 再起動通知を積む([])
        イベント.復旧失敗判定済み = True
        logger.error(
            "復旧失敗: 再起動から%.0f分を超えても鮮度が閾値内へ戻らない(鮮度=%s)",
            経過.total_seconds() / 60,
            鮮度の表示,
        )
        return 再起動通知を積む(
            [
                復旧失敗の事象(
                    f"再起動から{経過.total_seconds() / 60:.0f}分経過しても回復しない"
                    f"(鮮度={鮮度の表示})"
                )
            ]
        )

    直近24時間 = [
        日時 for 日時 in 記録.再起動履歴 if 現在時刻 - 日時 < timedelta(hours=24)
    ]
    if len(直近24時間) >= 設定.再起動の24時間上限:
        イベント.復旧失敗判定済み = True
        logger.error(
            "復旧失敗: 直近24時間の再起動が上限(%d回)に達しているため再起動しない",
            設定.再起動の24時間上限,
        )
        return [
            復旧失敗の事象(
                f"直近24時間の再起動が上限({設定.再起動の24時間上限}回)に達しているため"
                f"再起動できない(鮮度={鮮度の表示})"
            )
        ]

    結果 = 再起動する()
    イベント.再起動時刻 = 現在時刻
    記録.再起動履歴.append(現在時刻)
    logger.warning(
        "OneDriveを再起動した: %s(このイベントで1回目・直近24時間で%d回目・成功=%s)",
        結果.経過,
        len(直近24時間) + 1,
        結果.成功,
    )
    イベント.再起動要点 = (
        f"ハートビートの鮮度={鮮度の表示} / OneDriveを再起動"
        f"({結果.経過}・直近24時間で{len(直近24時間) + 1}回目)"
    )
    事象たち = 再起動通知を積む([])
    if not 結果.成功:
        イベント.復旧失敗判定済み = True
        事象たち.append(復旧失敗の事象(f"再起動の実行に失敗した({結果.経過})"))
    return 事象たち


def 通知を書き出す(事象: 通知事象, 監視通知フォルダ: Path) -> bool:
    """通知を1事象1ファイルで書き出す。構築済みのフローが本文をそのまま投稿する。

    **本文にダウンロードURL・トランスクリプト本文を書かない**(design.md#セキュリティ)。
    書き出しに失敗しても例外にせず失敗を返す(次のサイクルで再試行される)。
    """
    本文 = (
        f"【{事象.種別}】teams-transcript-fetcher 監視通知\n\n"
        f"- 事象: {事象.種別}\n"
        f"- 検知時刻: {事象.検知時刻.astimezone().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- 状況: {事象.要点}\n"
    )
    基本名 = f"{事象.検知時刻.astimezone().strftime('%Y%m%d-%H%M%S')}_{事象.種別}"
    try:
        監視通知フォルダ.mkdir(parents=True, exist_ok=True)
        for 連番 in range(1, 100):
            名前 = f"{基本名}.md" if 連番 == 1 else f"{基本名}-{連番}.md"
            パス = 監視通知フォルダ / 名前
            try:
                with パス.open("x", encoding="utf-8") as ファイル:
                    ファイル.write(本文)
            except FileExistsError:
                # 同秒・同種別の事象が複数ある場合は連番で回避する。
                continue
            logger.info("監視通知を書き出した: %s(%s)", 名前, 事象.種別)
            return True
        logger.error("監視通知の連番が尽きた: %s", 基本名)
        return False
    except OSError as 例外:
        logger.warning("監視通知を書き出せない: %s: %s", 基本名, 例外)
        return False


def 通知を評価する(
    継続中の事象: list[通知事象],
    即時の事象: list[通知事象],
    記録: 監視記録,
    設定: config.設定,
    現在時刻: datetime,
    書き出す: Callable[[通知事象], bool] | None = None,
) -> None:
    """通知の抑止・24時間ごとの再通知・再発の扱い(design.md#監視通知の書き出し)。

    即時の事象は常に書き出しを試みる。成功した「同期停滞」の事象は呼び出し元の
    停滞イベントに再起動通知済みを立て、以後同じ再起動については積まれなくなる
    (失敗した場合は呼び出し元が次サイクルでも積み直すため、ここでは何もしない)。
    継続型は通知済み記録と突き合わせ、初回と24時間経過のみ書き出す。継続していない
    事象キーは記録から取り除き、解消後の再発を新しい事象として通知できるようにする。
    """
    if 書き出す is None:
        書き出す = lambda 事象: 通知を書き出す(事象, 設定.監視通知フォルダ)  # noqa: E731

    for 事象 in 即時の事象:
        if 書き出す(事象):
            if 事象.種別 == 事象_同期停滞 and 記録.停滞イベント is not None:
                記録.停滞イベント.再起動通知済み = True
        else:
            logger.warning("即時通知の書き出しに失敗した: %s", 事象.種別)

    継続キー = set()
    for 事象 in 継続中の事象:
        継続キー.add(事象.キー)
        最終通知 = 記録.通知済み事象.get(事象.キー)
        if 最終通知 is not None and 現在時刻 - 最終通知 < timedelta(
            hours=設定.再通知間隔時間
        ):
            continue
        if 書き出す(事象):
            記録.通知済み事象[事象.キー] = 現在時刻
        # 失敗した事象は通知済みとして記録せず、次のサイクルで再試行する。

    解消したキー = set(記録.通知済み事象) - 継続キー
    for キー in 解消したキー:
        del 記録.通知済み事象[キー]


def 継続中の事象を集める(
    読んだ状態: state.状態 | None,
    会議名の索引: dict[str, str],
    記録: 監視記録,
    設定: config.設定,
    現在時刻: datetime,
) -> list[通知事象]:
    """既存バッチが数えているカウンタから、継続中の失敗・警告の事象を列挙する。

    回数はいずれも既存バッチが数えている値をそのまま使う(既存の取得ロジックは
    変更しない。design.md#失敗・警告の連続の検知)。台帳が消滅して状態が消えた
    録画は自然に列挙されなくなる。
    """
    事象たち: list[通知事象] = []

    def _録画の事象(種別: str, 録画の識別子: str, 回数の表示: str) -> 通知事象:
        # 事象キーは「種別+録画の識別子」。録画ごとに独立して抑止・解消を扱う。
        会議名 = 会議名の索引.get(録画の識別子, 録画の識別子)
        return 通知事象(
            種別=種別,
            キー=f"{種別}:{録画の識別子}",
            検知時刻=現在時刻,
            要点=f"対象={会議名} / {回数の表示}",
        )

    if 読んだ状態 is not None:
        # 失敗の連続のしきい値(3回)は、既存の「読めない台帳・URLファイルは
        # 3回連続で記録」の閾値と揃える(requirements.md#失敗・警告の連続の通知 [1])。
        連続しきい値 = 設定.読み取り失敗を記録するしきい値
        for 録画の識別子, 録画 in 読んだ状態.録画.items():
            if 録画.恒久的失敗の回数 >= 設定.恒久的失敗の上限:
                事象たち.append(
                    _録画の事象(
                        事象_ダウンロード失敗の連続,
                        録画の識別子,
                        f"恒久的失敗が{録画.恒久的失敗の回数}回に達し要手動確認",
                    )
                )
            if 録画.読み取り失敗の回数 >= 連続しきい値:
                事象たち.append(
                    _録画の事象(
                        事象_台帳読み取り失敗の連続,
                        録画の識別子,
                        f"台帳の読み取り失敗が{録画.読み取り失敗の回数}回連続",
                    )
                )
            if 録画.url読み取り失敗の回数 >= 連続しきい値:
                事象たち.append(
                    _録画の事象(
                        事象_url読み取り失敗の連続,
                        録画の識別子,
                        f"URLファイルの読み取り失敗が{録画.url読み取り失敗の回数}回連続",
                    )
                )

    if 記録.異常終了の連続回数 >= 設定.読み取り失敗を記録するしきい値:
        事象たち.append(
            通知事象(
                種別=事象_異常終了の連続,
                キー=事象_異常終了の連続,
                検知時刻=現在時刻,
                要点=f"バッチの異常終了が{記録.異常終了の連続回数}回連続",
            )
        )

    return 事象たち
