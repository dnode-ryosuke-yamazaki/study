"""1回の実行を組み立てるエントリポイント。

処理の順序で仕様上重要な点が2つある。

- **議事録の保存に成功した時点で処理済みとして記録し、その後の投稿用ファイルの
  書き出しが失敗しても処理済みのままにする。** 投稿の確実さより、議事録の二重生成
  (とTeamsへの再投稿)の防止を優先する(design.md#投稿用ファイルの書き出し)。
- **状態は1件処理するごとに保存する。** 途中で異常終了しても、処理済みの記録が
  失われて再生成につながらないようにする。

対応する仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import claude_runner
import config
import state
import summary_html
import writer

logger = logging.getLogger(__name__)


@dataclass
class 実行結果:
    初回初期化した: bool = False
    対象件数: int = 0
    成功件数: int = 0
    生成失敗件数: int = 0
    対象外化件数: int = 0
    読めなかった件数: int = 0
    投稿失敗件数: int = 0
    中断した: bool = False


def ログを設定する(設定: config.設定) -> None:
    """ログをローカルのファイルへ出す(同期フォルダには置かない)。

    5世代でローテーションする(teams-transcript-fetcherと同じ方式)。
    トランスクリプト・議事録・プロンプトの本文はログに出さない
    (requirements.md#生成手段(claude -p)の制約への対処 [2])。
    """
    ルート = logging.getLogger()
    if ルート.handlers:
        return
    設定.ログファイル.parent.mkdir(parents=True, exist_ok=True)
    ハンドラ = logging.handlers.RotatingFileHandler(
        設定.ログファイル, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    ハンドラ.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    ルート.addHandler(ハンドラ)
    ルート.setLevel(設定.ログレベル)


def 未処理のvtt一覧(入力フォルダ: Path, 現在の状態: state.状態) -> list[Path]:
    """入力フォルダと状態を突き合わせ、処理すべきVTTを名前順で返す。

    仕様: requirements.md#新規トランスクリプトの検知 [1] [2]
    """
    return sorted(
        (
            パス
            for パス in 入力フォルダ.glob("*.vtt")
            if パス.is_file()
            and not 現在の状態.処理済みか(パス.name)
            and not 現在の状態.対象外か(パス.name)
        ),
        key=lambda パス: パス.name,
    )


def vttを読む(パス: Path) -> str:
    """VTTを読む。OneDrive同期の実体化待ちで読めない場合はOSErrorが上がる。

    呼び出し元は読み取り失敗を生成失敗と区別し、状態を変えず次回に持ち越す
    (requirements.md#新規トランスクリプトの検知 [4])。
    """
    return パス.read_text(encoding="utf-8")


def _初回初期化する(設定: config.設定) -> 実行結果:
    """既存VTTを処理済みとして登録するだけで、議事録は生成しない。

    導入前から溜まっている過去分の遡及処理はスコープ外
    (requirements.md#新規トランスクリプトの検知 [3])。
    """
    新しい状態 = state.状態()
    今 = datetime.now(timezone.utc)
    件数 = 0
    if 設定.入力フォルダ.is_dir():
        for パス in 設定.入力フォルダ.glob("*.vtt"):
            新しい状態.処理済みにする(パス.name, 今)
            件数 += 1
    state.保存する(新しい状態, 設定.状態ファイル)
    logger.info("初回実行のため既存VTTを処理済みとして登録した: %d件", 件数)
    return 実行結果(初回初期化した=True)


def _1件を処理する(
    設定: config.設定, 現在の状態: state.状態, vttパス: Path, 結果: 実行結果
) -> None:
    try:
        トランスクリプト = vttを読む(vttパス)
    except OSError as 例外:
        # OneDrive同期の実体化待ちなど。状態を変えず次回に持ち越す。
        logger.info("読み取りの一時的失敗のため次回に持ち越す: %s: %s", vttパス.name, 例外)
        結果.読めなかった件数 += 1
        return

    開始 = time.monotonic()
    生成の結果 = claude_runner.生成する(
        トランスクリプト, vttパス.name, タイムアウト秒=設定.生成タイムアウト秒
    )

    if not 生成の結果.成功:
        回数 = 現在の状態.生成失敗を記録する(vttパス.name)
        logger.warning(
            "生成失敗: %s 分類=%s %s 再試行回数=%d/%d",
            vttパス.name,
            生成の結果.失敗の分類,
            生成の結果.詳細,
            回数,
            設定.再試行上限,
        )
        結果.生成失敗件数 += 1
        if 回数 >= 設定.再試行上限:
            現在の状態.対象外にする(vttパス.name, datetime.now(timezone.utc))
            logger.warning("再試行上限に達したため対象外にする: %s", vttパス.name)
            結果.対象外化件数 += 1
        state.保存する(現在の状態, 設定.状態ファイル)
        return

    議事録パス = writer.議事録を保存する(生成の結果.本文, vttパス.name, 設定.議事録フォルダ)
    現在の状態.処理済みにする(vttパス.name, datetime.now(timezone.utc))
    state.保存する(現在の状態, 設定.状態ファイル)
    logger.info(
        "議事録の保存成功: %s -> %s 生成時間=%.1f秒",
        vttパス.name,
        議事録パス.name,
        time.monotonic() - 開始,
    )
    結果.成功件数 += 1

    try:
        抜粋 = summary_html.要約部分を抽出する(生成の結果.本文)
        html = summary_html.htmlへ変換する(抜粋, 議事録パス.name)
        writer.投稿用に書き出す(html, 設定.投稿フォルダ, datetime.now())
    except OSError as 例外:
        # 議事録は保存済みなので処理済みのまま。投稿だけの失敗として残す。
        logger.warning("投稿用ファイルの書き出し失敗: %s: %s", 議事録パス.name, 例外)
        結果.投稿失敗件数 += 1


def 実行する(設定: config.設定) -> 実行結果:
    """ロック取得後の1回分の実行。"""
    try:
        現在の状態 = state.読み込む(設定.状態ファイル)
    except state.状態を読めなかった as 例外:
        # 一時的な読み取り失敗。何も変更せず次回の定期実行に委ねる。
        logger.info("状態ファイルを一時的に読めないため次回に持ち越す: %s", 例外)
        return 実行結果(中断した=True)
    except state.状態が壊れている as 例外:
        # 初期化すると全VTTが「初回」扱いになり既処理分を再生成してしまうため中断する。
        logger.error("状態ファイルが壊れているため処理を中断する: %s", 例外)
        return 実行結果(中断した=True)

    if 現在の状態 is None:
        return _初回初期化する(設定)

    対象一覧 = 未処理のvtt一覧(設定.入力フォルダ, 現在の状態)
    結果 = 実行結果(対象件数=len(対象一覧))
    logger.info("バッチ開始: 対象=%d件", len(対象一覧))

    for vttパス in 対象一覧:
        try:
            _1件を処理する(設定, 現在の状態, vttパス, 結果)
        except Exception:
            # 1件の想定外の失敗で全体を止めない。次回の定期実行で自然に再開する。
            logger.exception("想定外の例外: %s", vttパス.name)

    logger.info(
        "バッチ終了: 成功=%d 生成失敗=%d 対象外化=%d 持ち越し=%d 投稿失敗=%d",
        結果.成功件数,
        結果.生成失敗件数,
        結果.対象外化件数,
        結果.読めなかった件数,
        結果.投稿失敗件数,
    )
    return 結果


def main() -> int:
    設定 = config.load()
    ログを設定する(設定)
    try:
        with state.ロック(設定.ロックファイル, 無効とみなす秒=設定.ロックを無効とみなす秒):
            実行する(設定)
    except state.先行実行が動作中:
        logger.info("先行の実行が動作中のため何もせず終了する")
        return 0
    except Exception:
        logger.exception("バッチ全体の想定外の例外")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
