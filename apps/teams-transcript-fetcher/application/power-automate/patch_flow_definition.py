#!/usr/bin/env python3
"""Power Automateフロー①のエクスポート定義を、台帳を書く形に書き換える。

**このスクリプトは元のエクスポートを読み込んで書き換える。** 定義ファイルには
テナント識別子・接続識別子・ドライブ識別子が含まれ、design.md#セキュリティ で
「リポジトリのドキュメントへ転記しない」と決めているため、定義そのものはリポジトリに
置かず、この変換スクリプトだけを置く。

書き換える内容(design.md#録画の検知と台帳の作成(Power Automate フロー①)の
「現行フローからの変更点」):

1. トランスクリプト一覧の先頭1件のみを取る箇所を、一覧全体を配列にする
2. 保存内容をURL単体から録画単位の台帳(JSON)に変える
3. 保存先を個人OneDriveの台帳置き場に変える(コネクタは変更しない)
4. 一覧が空でも、また一覧の取得に失敗しても台帳を作る
5. 通常会議用フローの、格納先の識別子をハードコードしている呼び出し2件を削除し、
   トリガーが提供する値を使う

使い方は同じフォルダの README.md を参照。
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

# 元のフローのアクション名。日本語のまま使われている。
アクション_一覧取得 = "SharePoint_に_HTTP_要求を送信します"
アクション_driveid取得 = "SharePoint_に_HTTP_要求を送信します（DriveId取得用）"
アクション_driveitemid取得 = "SharePoint_に_HTTP_要求を送信します（DriveItemId取得用）"
アクション_作成 = "作成"
アクション_ファイルの作成 = "ファイルの作成"
アクション_変数を初期化 = "変数を初期化する"
アクション_条件 = "条件"

# 新しく足すアクション名。
アクション_url一覧 = "URL一覧を取り出す"
アクション_台帳 = "台帳を組み立てる"

#: トリガーが提供する値。ハードコードした識別子の代わりに使う。
_ドライブ識別子 = "@{triggerOutputs()?['body/{DriveId}']}"
_録画の識別子 = "@{triggerOutputs()?['body/{DriveItemId}']}"


def _アクションの入れ物を探す(定義: dict) -> dict:
    """アクションが入っている辞書を返す。

    チャネル会議用フローは「条件」の中にアクションが入っており、通常会議用フローも
    録画の絞り込みを追加した版では同じ構造になっている。
    """
    actions = 定義["properties"]["definition"]["actions"]
    if アクション_条件 in actions:
        return actions[アクション_条件]["actions"]
    return actions


def _一覧取得のuriを書き換える(入れ物: dict) -> None:
    """一覧取得のURIを、トリガーが提供する値を使う形に統一する。

    通常会議用フローはドライブ識別子をハードコードし、そのために実行している
    一覧取得(DriveId取得用)の結果を使っていない。トリガーの値を使えば、
    その呼び出しとハードコードした値の両方が不要になる。
    """
    一覧取得 = 入れ物[アクション_一覧取得]
    一覧取得["inputs"]["parameters"]["parameters/uri"] = (
        f"_api/v2.1/drives/{_ドライブ識別子}/items/{_録画の識別子}/media/transcripts"
    )
    # 直前のアクションへの依存を外す(削除する呼び出しに依存している場合があるため)。
    一覧取得["runAfter"] = {}


def _不要な呼び出しを削除する(入れ物: dict) -> list[str]:
    """ハードコードした識別子のために実行している呼び出しを削除する。"""
    削除した = []
    for 名前 in (アクション_driveid取得, アクション_driveitemid取得):
        if 名前 in 入れ物:
            del 入れ物[名前]
            削除した.append(名前)
    return 削除した


def _url一覧のアクションを作る() -> dict:
    """一覧の応答からダウンロードURLだけを取り出して配列にする。

    元のフローは `value[0]` で先頭1件しか取っていなかった。Select を使うと
    ループを書かずに全件を配列にできる。

    一覧の取得が失敗した場合も進めるため `runAfter` に Failed を含め、
    `coalesce` で空配列に落とす。こうすると「URLを持たない台帳」ができ、
    フェーズ2の発行要求が拾える(requirements.md#台帳の作成 [5])。
    """
    return {
        "runAfter": {アクション_一覧取得: ["Succeeded", "Failed", "Skipped"]},
        "type": "Select",
        "inputs": {
            "from": f"@coalesce(body('{アクション_一覧取得}')?['value'], json('[]'))",
            "select": "@item()?['temporaryDownloadUrl']",
        },
    }


def _台帳のアクションを作る(サイトurl: str, 由来: str) -> dict:
    """台帳の内容を組み立てる。

    項目名は design.md#ファイルの項目名の取り決め に固定してある。
    バッチ側が読む名前とずれると、例外ではなく「対象が見つからない」という
    静かな失敗になる。

    `recordingCreatedAt` はトリガーの Created を使う。取れない場合はバッチが
    台帳ファイルの更新時刻で代用する設計なので、null でも動く
    (requirements.md#ファイル名 [4])。
    """
    return {
        "runAfter": {アクション_url一覧: ["Succeeded"]},
        "type": "Compose",
        "inputs": {
            "meetingName": "@{triggerBody()?['{Name}']}",
            "siteUrl": サイトurl,
            "driveId": _ドライブ識別子,
            "recordingId": _録画の識別子,
            "recordingCreatedAt": "@{triggerOutputs()?['body/Created']}",
            "source": 由来,
            "issuedAt": "@{utcNow('yyyy-MM-ddTHH:mm:ss.fffZ')}",
            "urls": f"@body('{アクション_url一覧}')",
        },
    }


def _ファイルの作成を書き換える(
    入れ物: dict, 台帳の保存先サイト: str, 台帳フォルダ: str
) -> None:
    """保存先と保存内容を台帳に変える。コネクタは変更しない。

    ファイル名は「録画の識別子 + .json」。
    仕様: design.md#識別子とファイル名の規則(唯一の定義)
    """
    ファイルの作成 = 入れ物[アクション_ファイルの作成]
    ファイルの作成["runAfter"] = {アクション_台帳: ["Succeeded"]}
    パラメータ = ファイルの作成["inputs"]["parameters"]
    パラメータ["dataset"] = 台帳の保存先サイト
    パラメータ["folderPath"] = 台帳フォルダ
    パラメータ["name"] = f"{_録画の識別子}.json"
    パラメータ["body"] = f"@string(outputs('{アクション_台帳}'))"


def 書き換える(
    元の定義: dict,
    *,
    由来: str,
    台帳の保存先サイト: str,
    台帳フォルダ: str,
) -> tuple[dict, list[str]]:
    """定義を書き換えた新しい辞書と、変更内容の説明を返す。"""
    定義 = copy.deepcopy(元の定義)
    入れ物 = _アクションの入れ物を探す(定義)

    変更点: list[str] = []

    足りないアクション = [
        名前
        for 名前 in (アクション_一覧取得, アクション_ファイルの作成)
        if 名前 not in 入れ物
    ]
    if 足りないアクション:
        raise SystemExit(
            "想定したアクションが見つかりません: " + ", ".join(足りないアクション)
        )

    削除した = _不要な呼び出しを削除する(入れ物)
    if 削除した:
        変更点.append(
            "ハードコードした識別子のための呼び出しを削除: " + ", ".join(削除した)
        )

    _一覧取得のuriを書き換える(入れ物)
    変更点.append("一覧取得のURIをトリガーが提供する値を使う形に統一")

    # 先頭1件だけを取り出していた Compose は Select に置き換える。
    if アクション_作成 in 入れ物:
        del 入れ物[アクション_作成]
        変更点.append(f"先頭1件のみを取り出す「{アクション_作成}」を削除")

    入れ物[アクション_url一覧] = _url一覧のアクションを作る()
    変更点.append(f"「{アクション_url一覧}」を追加(一覧全件を配列にする)")

    入れ物[アクション_台帳] = _台帳のアクションを作る(台帳の保存先サイト, 由来)
    変更点.append(f"「{アクション_台帳}」を追加(台帳の内容を組み立てる)")

    _ファイルの作成を書き換える(入れ物, 台帳の保存先サイト, 台帳フォルダ)
    変更点.append("保存先を個人OneDriveの台帳置き場に変更し、内容を台帳にした")

    # 使っていない変数の初期化は残しておく(消しても動くが、差分を最小にする)。
    if アクション_変数を初期化 in 定義["properties"]["definition"]["actions"]:
        変更点.append(f"「{アクション_変数を初期化}」はそのまま残した(差分を最小にする)")

    return 定義, 変更点


def main() -> int:
    引数の解析 = argparse.ArgumentParser(description=__doc__)
    引数の解析.add_argument("入力", type=Path, help="元の definition.json のパス")
    引数の解析.add_argument("出力", type=Path, help="書き換えた定義の出力先")
    引数の解析.add_argument(
        "--由来",
        required=True,
        choices=("channel", "personal"),
        help="台帳の source に入れる値",
    )
    引数の解析.add_argument(
        "--台帳の保存先サイト",
        required=True,
        help="個人OneDriveのサイトURL（元の通常会議用フローのトリガーの dataset と同じ値）",
    )
    引数の解析.add_argument(
        "--台帳フォルダ",
        default="/Documents/00_root/auto/transcript/ledger",
        help="台帳置き場のフォルダパス",
    )
    引数 = 引数の解析.parse_args()

    元の定義 = json.loads(引数.入力.read_text(encoding="utf-8"))
    新しい定義, 変更点 = 書き換える(
        元の定義,
        由来=引数.由来,
        台帳の保存先サイト=引数.台帳の保存先サイト,
        台帳フォルダ=引数.台帳フォルダ,
    )

    引数.出力.parent.mkdir(parents=True, exist_ok=True)
    引数.出力.write_text(
        json.dumps(新しい定義, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    print(f"書き換えました: {引数.出力}")
    for 説明 in 変更点:
        print(f"  - {説明}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
