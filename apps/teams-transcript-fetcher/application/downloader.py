"""ダウンロードURLへのアクセスと、応答の分類。

**バッチが行う外部通信はここだけ**(requirements.md#実行環境 [2])。

ダウンロードURLは事前認証済みのため、**認証ヘッダを付けずにアクセスする**
(付けると失敗する)。標準ライブラリの `urllib.request` を使い、実行時の外部依存を
ゼロに保つ(design.md#外部ライブラリの方針)。

**URLをログや失敗理由に出さない。** 実質ベアラトークンであり、そのURLを知れば
会議音声由来の内容を第三者が取得できる(design.md#セキュリティ)。

対応する仕様:
- requirements.md#エラー時の挙動
- design.md#バリデーション / design.md#エラーハンドリング 2
"""

from __future__ import annotations

import logging
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: WEBVTTファイルの識別行。これで始まらない応答はトランスクリプトではない。
webvttの識別子 = b"WEBVTT"

#: UTF-8のBOM。付いていたら取り除く(requirements.md#ファイル名 [7])。
_bom = b"\xef\xbb\xbf"

#: 期限切れと判断するステータス。同じURLでは二度と成功しない。
恒久的とみなすステータス = (401, 403, 404)

#: 既定の信頼ストアが空だったときに探す証明書バンドルの候補。
#: macOSでpython.org版のPythonを使うと、既定の信頼ストアが空になる。
#: `SSL_CERT_FILE` を手で設定させると「ターミナルでは動くのにlaunchdでは
#: 動かない」という分かりにくい状態を招くため、バッチ自身で探す。
_証明書バンドルの候補 = ("/etc/ssl/cert.pem", "/usr/local/etc/openssl/cert.pem")

_ssl文脈: ssl.SSLContext | None = None


class urlが不正(Exception):
    """アクセスしてよいURLの条件を満たさない。通信せずに失敗として扱う。"""


@dataclass(frozen=True)
class 成功:
    #: 応答本文。BOMを取り除いたバイト列。改行は応答のまま保持する。
    本文: bytes


@dataclass(frozen=True)
class 恒久的失敗:
    """同じURLでのリトライを行わない失敗(requirements.md#エラー時の挙動 [1] [2])。"""

    理由: str
    ステータス: int | None = None


@dataclass(frozen=True)
class 一時的失敗:
    """次回の定期実行で自然にリトライされる失敗(同 [4])。"""

    理由: str
    ステータス: int | None = None
    #: ローカルの設定不足が原因で、待っても直らない失敗。
    #: 分類は一時的失敗のまま(URLを使い潰さない)だが、人が対処しないと
    #: 永久に進まないため記録ファイルに残す必要がある。
    設定の問題: bool = False


結果 = 成功 | 恒久的失敗 | 一時的失敗


def urlを検証する(url: str, 許可するホスト接尾辞: tuple[str, ...]) -> None:
    """アクセスしてよいURLかを確かめる。だめなら `urlが不正` を投げる。

    台帳やURLファイルの内容は外部から与えられた文字列として扱う。検証しないと、
    書き換えられたファイルによって想定外のホストへ通信させられる。
    仕様: design.md#バリデーション / design.md#セキュリティ
    """
    try:
        解析結果 = urllib.parse.urlsplit(url)
    except ValueError as 例外:
        raise urlが不正(f"URLとして解釈できない: {例外}") from 例外

    if 解析結果.scheme != "https":
        # スキームはURL全体を出さずに済む情報なのでログに残してよい。
        logger.warning("HTTPSでないURLを拒否した: scheme=%s", 解析結果.scheme or "(なし)")
        raise urlが不正(f"HTTPSでない: scheme={解析結果.scheme or '(なし)'}")

    ホスト = (解析結果.hostname or "").lower()
    if not _許可されたホストか(ホスト, 許可するホスト接尾辞):
        # 実際のホストは未確認(requirements.md#前提・検証項目 #11)。
        # 拒否した事実とホスト名を残すことで、初回の実機実行で正しい許可リストが分かる。
        logger.warning("許可していないホストのURLを拒否した: host=%s", ホスト or "(なし)")
        raise urlが不正(f"許可していないホスト: {ホスト or '(なし)'}")


def _許可されたホストか(ホスト: str, 許可するホスト接尾辞: tuple[str, ...]) -> bool:
    """接尾辞の直前がドット境界であることまで確かめる。

    単純な文字列の後方一致だと `evil-sharepoint.com` が通ってしまう。
    """
    for 接尾辞 in 許可するホスト接尾辞:
        正規化した接尾辞 = 接尾辞.lower()
        if ホスト == 正規化した接尾辞.lstrip("."):
            return True
        if ホスト.endswith(正規化した接尾辞):
            return True
    return False


def _証明書バンドルを探す() -> str | None:
    """使える証明書バンドルのパスを返す。見つからなければ None。

    certifi があれば使うが、**依存はしていない**。無くても動くようにするため
    「あれば使う」だけの扱いにしてある(design.md#外部ライブラリの方針)。
    """
    候補: list[str] = []
    try:
        import certifi  # noqa: PLC0415 — 無くてもよい任意の候補
    except ImportError:
        pass
    else:
        候補.append(certifi.where())
    候補.extend(_証明書バンドルの候補)

    for パス in 候補:
        if os.path.isfile(パス) and os.access(パス, os.R_OK):
            return パス
    return None


def ssl文脈を用意する() -> ssl.SSLContext:
    """TLSの検証に使う文脈を組み立てる(初回のみ)。

    既定の信頼ストアが空の場合(macOSのpython.org版Pythonで起きる)だけ、
    バンドルを探して読み込む。見つからなければ空のまま返し、実際の失敗は
    「設定の問題」として記録される。
    """
    global _ssl文脈
    if _ssl文脈 is not None:
        return _ssl文脈

    文脈 = ssl.create_default_context()
    if 文脈.cert_store_stats()["x509_ca"] == 0:
        バンドル = _証明書バンドルを探す()
        if バンドル:
            文脈.load_verify_locations(cafile=バンドル)
            logger.info("既定の信頼ストアが空のため証明書バンドルを読み込んだ: %s", バンドル)
        else:
            logger.error(
                "証明書バンドルが見つからない。TLSの検証に失敗する見込み。"
                "READMEの「証明書のセットアップ」を確認すること"
            )
    _ssl文脈 = 文脈
    return 文脈


def _証明書の検証に失敗したか(例外: BaseException) -> bool:
    """TLS証明書の検証に失敗したかを判定する。

    macOSでpython.org版のPythonを使うと、システムの証明書ストアを見ないため
    この失敗が起きる。**待っても直らない**ので、通信エラーと同じ「黙って
    リトライ」で済ませると、利用者は「何も起きない」ことしか分からない。
    """
    if isinstance(例外, ssl.SSLCertVerificationError):
        return True
    理由 = getattr(例外, "reason", None)
    if isinstance(理由, ssl.SSLCertVerificationError):
        return True
    return "CERTIFICATE_VERIFY_FAILED" in str(例外)


def 取得する(
    url: str, *, タイムアウト秒: int, 許可するホスト接尾辞: tuple[str, ...]
) -> 結果:
    """ダウンロードURLからトランスクリプトを取得し、結果を分類して返す。

    本文がWEBVTTかどうかの確認まで含めて「成功」とする。ステータスコードだけを
    見ていると、期限切れのURLが返すエラーページをトランスクリプトとして保存し、
    しかも取得済みとして記録してしまう(台帳も消えるため復旧できない)。
    """
    try:
        urlを検証する(url, 許可するホスト接尾辞)
    except urlが不正 as 例外:
        return 恒久的失敗(理由=str(例外))

    # 認証ヘッダを付けない。事前認証済みURLに付けると失敗する。
    要求 = urllib.request.Request(url, method="GET")

    try:
        with urllib.request.urlopen(
            要求, timeout=タイムアウト秒, context=ssl文脈を用意する()
        ) as 応答:
            本文 = 応答.read()
    except urllib.error.HTTPError as 例外:
        if 例外.code in 恒久的とみなすステータス:
            return 恒久的失敗(理由=f"HTTP {例外.code}(期限切れと判断)", ステータス=例外.code)
        return 一時的失敗(理由=f"HTTP {例外.code}", ステータス=例外.code)
    except urllib.error.URLError as 例外:
        return 一時的失敗(
            理由=f"接続できない: {例外.reason}",
            設定の問題=_証明書の検証に失敗したか(例外),
        )
    except TimeoutError:
        return 一時的失敗(理由=f"タイムアウト({タイムアウト秒}秒)")
    except OSError as 例外:
        return 一時的失敗(理由=f"通信エラー: {例外}")

    if 本文.startswith(_bom):
        本文 = 本文[len(_bom) :]

    if not 本文.startswith(webvttの識別子):
        return 恒久的失敗(
            理由=(
                "応答本文がWEBVTTではない"
                f"(先頭 {本文[:16]!r}、{len(本文)}バイト)"
            )
        )

    return 成功(本文=本文)
