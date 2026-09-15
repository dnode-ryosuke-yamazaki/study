"""会社のセキュリティプロキシ配下でTLSの検証に使う文脈を組み立てる。

**このファイルは正本と写しの2箇所に同じ内容で置かれている。**

- 正本: ``~/.claude/lib/ca_bundle_tls.py``
- 写し: ``<study>/apps/teams-transcript-fetcher/application/ca_bundle_tls.py``

片方だけを直すと、もう片方が古い挙動のまま取り残される。2026-09-10に実際に
これが起き、トランスクリプトの取得が5日間止まった。ズレは正本側のテスト
``lib/tests/test_ca_bundle_tls_copies.py`` が検出する(内容が1バイトでも
違うと落ちる)。**直すときは必ず両方を同じ内容にすること。**

写し先のstudyは実行時の外部依存をゼロに保つ方針のため、**標準ライブラリだけで
完結させる。** 同じ理由で、このファイルは他のモジュールをimportしない。

呼び出し側は組み立てた文脈を自分で使い回す(このモジュールは覚えない)。
"""

from __future__ import annotations

import logging
import os
import ssl

#: 運用者が置く証明書バンドル。**候補の中で最優先で使う。**
#: 会社のセキュリティプロキシはTLSを差し替えるため、その中間CAを信頼していないと
#: 検証に失敗する。このCAはmacOSのシステムキーチェーンにしかなく、
#: ``/etc/ssl/cert.pem`` にも certifi にも入っていない。運用者が次の2行で
#: 「システムのバンドル + キーチェーンのCA」を1つにまとめて置く。
#:   cat /etc/ssl/cert.pem > "~/Library/Application Support/ca-bundle/ca-bundle.pem"
#:   security find-certificate -a -p /Library/Keychains/System.keychain >> (同じファイル)
運用者が置く証明書バンドル = "~/Library/Application Support/ca-bundle/ca-bundle.pem"

#: 運用者のバンドルが無いときに探す候補。
#: macOSでpython.org版のPythonを使うと、既定の信頼ストアが空になる。
#: ``SSL_CERT_FILE`` を手で設定させると「ターミナルでは動くのにlaunchdでは
#: 動かない」という分かりにくい状態を招くため、呼び出し側が自分で探す。
証明書バンドルの候補 = ("/etc/ssl/cert.pem", "/usr/local/etc/openssl/cert.pem")


def 証明書バンドルの候補を並べる() -> list[str]:
    """優先度の高い順に候補のパスを返す。

    運用者のバンドルを先頭に置く。certifi やOS標準のバンドルを先に採用すると、
    差し替えられた証明書のチェーンを検証できず
    「self-signed certificate in certificate chain」で落ちる。

    certifi があれば候補に加えるが、**依存はしていない**(あれば使うだけ)。
    """
    候補: list[str] = [os.path.expanduser(運用者が置く証明書バンドル)]
    try:
        import certifi  # noqa: PLC0415 — 無くてもよい任意の候補
    except ImportError:
        pass
    else:
        候補.append(certifi.where())
    候補.extend(証明書バンドルの候補)
    return 候補


def 証明書バンドルを探す(候補: list[str] | None = None) -> str | None:
    """読み込める証明書バンドルのパスを返す。見つからなければ None。"""
    if 候補 is None:
        候補 = 証明書バンドルの候補を並べる()
    for パス in 候補:
        if os.path.isfile(パス) and os.access(パス, os.R_OK):
            return パス
    return None


def ssl文脈を組み立てる(logger: logging.Logger | None = None) -> ssl.SSLContext:
    """TLSの検証に使う文脈を組み立てて返す。

    既定の信頼ストアが空の場合(macOSのpython.org版Pythonで起きる)だけ、
    バンドルを探して読み込む。見つからなければ空のまま返し、実際の失敗は
    呼び出し側が「設定の問題」として記録する。
    """
    文脈 = ssl.create_default_context()
    # Python 3.13以降は VERIFY_X509_STRICT が既定で有効になり、keyUsage拡張を
    # 持たないCA証明書(会社のセキュリティプロキシのCA)がチェーンに居ると
    # 「CA cert does not include key usage extension」で検証に失敗する。
    # ホスト名・有効期限・チェーンの検証は維持したまま、CA証明書の拡張フィールドの
    # 厳格チェックだけを外す。
    文脈.verify_flags &= ~ssl.VERIFY_X509_STRICT
    if 文脈.cert_store_stats()["x509_ca"] == 0:
        バンドル = 証明書バンドルを探す()
        if バンドル:
            if logger:
                logger.info(
                    "既定の信頼ストアが空のため証明書バンドルを読み込んだ: %s", バンドル
                )
            文脈.load_verify_locations(cafile=バンドル)
        elif logger:
            logger.error(
                "証明書バンドルが見つからない。TLSの検証に失敗する見込み。"
                "READMEの「証明書のセットアップ」を確認すること"
            )
    return 文脈
