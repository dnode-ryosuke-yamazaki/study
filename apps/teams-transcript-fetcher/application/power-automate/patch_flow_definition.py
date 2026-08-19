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
import re
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

# 録画の識別子の取り方は、元のフローがどちらの方式で動いていたかに合わせる。
#
# **簡素化して壊した経験がある。** 個人OneDriveのトリガーは {DriveId} /
# {DriveItemId} を提供せず、これらを使うと空文字になる(2026-08-19に実機で確認)。
# 元のフローがファイル名から項目を検索していたのはそのためだった。
方式_トリガー = "trigger"      # チャネル会議用: トリガーが識別子を提供する
方式_パス検索 = "path-lookup"  # 通常会議用: ファイル名から項目を検索する

#: トリガーが識別子を提供する場合の参照。
_トリガーのドライブ識別子 = "@{triggerOutputs()?['body/{DriveId}']}"
_トリガーの録画の識別子 = "@{triggerOutputs()?['body/{DriveItemId}']}"

#: 項目検索の結果から録画の識別子を取り出す参照。
_検索結果の録画の識別子 = f"@{{body('{アクション_driveitemid取得}')?['id']}}"


def _アクションの入れ物を探す(定義: dict) -> dict:
    """アクションが入っている辞書を返す。

    チャネル会議用フローは「条件」の中にアクションが入っており、通常会議用フローも
    録画の絞り込みを追加した版では同じ構造になっている。
    """
    actions = 定義["properties"]["definition"]["actions"]
    if アクション_条件 in actions:
        return actions[アクション_条件]["actions"]
    return actions


def _方式を判定する(入れ物: dict) -> str:
    """元のフローがどちらの方式で識別子を得ていたかを判定する。

    項目検索の呼び出しがあれば、そのフローのトリガーは識別子を提供していない
    (だからわざわざ検索していた)。動いていた方式を保つ。
    """
    return 方式_パス検索 if アクション_driveitemid取得 in 入れ物 else 方式_トリガー


def _ハードコードされたドライブ識別子(入れ物: dict) -> str:
    """一覧取得のURIに埋め込まれたドライブ識別子を取り出す。

    値そのものはリポジトリに書かない(design.md#セキュリティ)。元の定義から
    読み取って台帳に入れる。
    """
    uri = 入れ物[アクション_一覧取得]["inputs"]["parameters"]["parameters/uri"]
    見つかった = re.search(r"_api/v2\.1/drives/([^/'\s]+)/items/", uri)
    if not 見つかった:
        raise SystemExit(
            "一覧取得のURIからドライブ識別子を読み取れません。"
            "URIの形が想定と違う可能性があります。"
        )
    return 見つかった.group(1)


def _一覧取得のuriを書き換える(入れ物: dict) -> None:
    """一覧取得のURIを、トリガーが提供する値を使う形に統一する。

    通常会議用フローはドライブ識別子をハードコードし、そのために実行している
    一覧取得(DriveId取得用)の結果を使っていない。トリガーの値を使えば、
    その呼び出しとハードコードした値の両方が不要になる。
    """
    一覧取得 = 入れ物[アクション_一覧取得]
    一覧取得["inputs"]["parameters"]["parameters/uri"] = (
        f"_api/v2.1/drives/{_トリガーのドライブ識別子}"
        f"/items/{_トリガーの録画の識別子}/media/transcripts"
    )
    一覧取得["runAfter"] = {}


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


def _台帳のアクションを作る(
    サイトurl: str, 由来: str, ドライブ識別子: str, 録画の識別子: str
) -> dict:
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
            "driveId": ドライブ識別子,
            "recordingId": 録画の識別子,
            "recordingCreatedAt": "@{triggerOutputs()?['body/Created']}",
            "source": 由来,
            "issuedAt": "@{utcNow('yyyy-MM-ddTHH:mm:ss.fffZ')}",
            "urls": f"@body('{アクション_url一覧}')",
        },
    }


def _ファイルの作成を書き換える(
    入れ物: dict, 台帳の保存先サイト: str, 台帳フォルダ: str, 録画の識別子: str
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
    パラメータ["name"] = f"{録画の識別子}.json"
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

    方式 = _方式を判定する(入れ物)

    if 方式 == 方式_トリガー:
        # トリガーが識別子を提供するフロー(チャネル会議用)。
        ドライブ識別子 = _トリガーのドライブ識別子
        録画の識別子 = _トリガーの録画の識別子
        _一覧取得のuriを書き換える(入れ物)
        変更点.append("識別子はトリガーが提供する値を使う(元のフローと同じ方式)")
    else:
        # ファイル名から項目を検索するフロー(通常会議用)。
        # **この方式を保つ。** 個人OneDriveのトリガーは識別子を提供せず、
        # トリガーの値を使うと空文字になる(2026-08-19に実機で確認)。
        ドライブ識別子 = _ハードコードされたドライブ識別子(入れ物)
        録画の識別子 = _検索結果の録画の識別子
        変更点.append(
            "識別子はファイル名からの項目検索で得る(元のフローと同じ方式)。"
            "一覧取得のURIは変更しない"
        )
        削除した = [名前 for 名前 in (アクション_driveid取得,) if 名前 in 入れ物]
        for 名前 in 削除した:
            del 入れ物[名前]
        if 削除した:
            変更点.append(
                "結果を使っていない呼び出しのみ削除: " + ", ".join(削除した)
            )
            # 検索の呼び出しが削除したものに依存していたら外す。
            入れ物[アクション_driveitemid取得]["runAfter"] = {}

    # 先頭1件だけを取り出していた Compose は Select に置き換える。
    if アクション_作成 in 入れ物:
        del 入れ物[アクション_作成]
        変更点.append(f"先頭1件のみを取り出す「{アクション_作成}」を削除")

    入れ物[アクション_url一覧] = _url一覧のアクションを作る()
    変更点.append(f"「{アクション_url一覧}」を追加(一覧全件を配列にする)")

    入れ物[アクション_台帳] = _台帳のアクションを作る(
        台帳の保存先サイト, 由来, ドライブ識別子, 録画の識別子
    )
    変更点.append(f"「{アクション_台帳}」を追加(台帳の内容を組み立てる)")

    _ファイルの作成を書き換える(
        入れ物, 台帳の保存先サイト, 台帳フォルダ, 録画の識別子
    )
    変更点.append("保存先を個人OneDriveの台帳置き場に変更し、内容を台帳にした")

    # 使っていない変数の初期化は残しておく(消しても動くが、差分を最小にする)。
    if アクション_変数を初期化 in 定義["properties"]["definition"]["actions"]:
        変更点.append(f"「{アクション_変数を初期化}」はそのまま残した(差分を最小にする)")

    return 定義, 変更点


# --- フロー②(ダウンロードURLの発行)の生成 -----------------------------------
#
# フロー①の定義を土台にする。接続・HTTP呼び出し・URL一覧の取り出しがそのまま
# 使えるため、新規に書き起こすより間違いが少ない。
#
# 仕様: design.md#ダウンロードURLの発行(Power Automate フロー②・フェーズ2)

アクション_要求の中身 = "要求の中身を取得する"
アクション_要求の解析 = "要求を解析する"
アクション_要求の削除 = "要求を削除する"

#: 解析した要求から値を取り出す参照。
_要求のサイト = f"@{{body('{アクション_要求の解析}')?['siteUrl']}}"
_要求のドライブ = f"@{{body('{アクション_要求の解析}')?['driveId']}}"
_要求の録画 = f"@{{body('{アクション_要求の解析}')?['recordingId']}}"


def _要求のスキーマ() -> dict:
    """要求ファイルの形。項目名は design.md#ファイルの項目名の取り決め に従う。"""
    return {
        "type": "object",
        "properties": {
            "siteUrl": {"type": "string"},
            "driveId": {"type": "string"},
            "recordingId": {"type": "string"},
            "createdAt": {"type": "string"},
        },
    }


def フロー2を作る(
    フロー1の定義: dict,
    *,
    作業サイト: str,
    要求フォルダ: str,
    urlフォルダ: str,
    フロー名: str,
) -> tuple[dict, list[str]]:
    """フロー①の定義からフロー②を組み立てる。

    フロー②は「要求を読んで、一覧を取得して、URLを書いて、要求を消す」だけ。
    要求は録画1件につき1ファイルなので繰り返し処理が不要で、この単純さが
    1ファイル方式を選んだ理由でもある。
    """
    定義 = copy.deepcopy(フロー1の定義)
    変更点: list[str] = []

    プロパティ = 定義["properties"]
    プロパティ["displayName"] = フロー名
    中身 = プロパティ["definition"]

    元の入れ物 = _アクションの入れ物を探す(定義)
    一覧取得 = copy.deepcopy(元の入れ物[アクション_一覧取得])
    ファイルの作成 = copy.deepcopy(元の入れ物[アクション_ファイルの作成])
    コネクタ = 一覧取得["inputs"]["host"]

    # トリガーは要求置き場の監視に変える。元のトリガーの host / authentication を
    # そのまま使うことで、接続の紐付けを崩さない。
    元のトリガー名, 元のトリガー = next(iter(中身["triggers"].items()))
    トリガー = copy.deepcopy(元のトリガー)
    トリガー["inputs"]["parameters"] = {
        "dataset": 作業サイト,
        "table": "Documents",
        "folderPath": 要求フォルダ,
    }
    中身["triggers"] = {元のトリガー名: トリガー}
    変更点.append(f"トリガーの監視先を要求置き場に変更: {要求フォルダ}")

    # 要求の中身を読む。トリガー(プロパティのみ)は中身をくれないため必要。
    要求の中身 = {
        "runAfter": {},
        "type": "OpenApiConnection",
        "inputs": {
            "parameters": {
                "dataset": 作業サイト,
                "id": "@{triggerOutputs()?['body/{Identifier}']}",
            },
            "host": {**コネクタ, "operationId": "GetFileContent"},
            "authentication": "@parameters('$authentication')",
        },
    }

    要求の解析 = {
        "runAfter": {アクション_要求の中身: ["Succeeded"]},
        "type": "ParseJson",
        "inputs": {
            "content": f"@body('{アクション_要求の中身}')",
            "schema": _要求のスキーマ(),
        },
    }

    # 一覧取得は要求に書かれた識別子を使う。フロー①と違い、どのフローの
    # 由来でも同じ形で扱える(要求だけで発行に必要な情報が揃っているため)。
    一覧取得["runAfter"] = {アクション_要求の解析: ["Succeeded"]}
    一覧取得["inputs"]["parameters"]["dataset"] = _要求のサイト
    一覧取得["inputs"]["parameters"]["parameters/uri"] = (
        f"_api/v2.1/drives/{_要求のドライブ}/items/{_要求の録画}/media/transcripts"
    )

    url一覧 = _url一覧のアクションを作る()

    # URLファイルの中身。項目名は台帳と同じ意味で揃える。
    url内容 = {
        # **条件の中の最初のアクションなので runAfter は空にする。**
        # Power Automateでは条件の中のアクションは条件の中のアクションしか
        # 参照できない。外側の「URL一覧を取り出す」を指定するとインポートで
        # 「must belong to same level」と拒否される。
        "runAfter": {},
        "type": "Compose",
        "inputs": {
            "recordingId": _要求の録画,
            "issuedAt": "@{utcNow('yyyy-MM-ddTHH:mm:ss.fffZ')}",
            "urls": f"@body('{アクション_url一覧}')",
        },
    }

    # 一覧が空のときはURLファイルを作らない。台帳が残り、次回また要求される。
    ファイルの作成["runAfter"] = {アクション_台帳: ["Succeeded"]}
    ファイルの作成["inputs"]["parameters"] = {
        "dataset": 作業サイト,
        "folderPath": urlフォルダ,
        "name": f"{_要求の録画}.json",
        "body": f"@string(outputs('{アクション_台帳}'))",
    }

    条件 = {
        "runAfter": {アクション_url一覧: ["Succeeded"]},
        "type": "If",
        "expression": {"not": {"equals": [f"@length(body('{アクション_url一覧}'))", 0]}},
        "actions": {アクション_台帳: url内容, アクション_ファイルの作成: ファイルの作成},
        "else": {"actions": {}},
    }

    # 要求の削除は最後。処理できなかった要求は残り、バッチが滞留として退避する。
    要求の削除 = {
        "runAfter": {アクション_条件: ["Succeeded"]},
        "type": "OpenApiConnection",
        "inputs": {
            "parameters": {
                "dataset": 作業サイト,
                "id": "@{triggerOutputs()?['body/{Identifier}']}",
            },
            "host": {**コネクタ, "operationId": "DeleteFile"},
            "authentication": "@parameters('$authentication')",
        },
    }

    中身["actions"] = {
        アクション_要求の中身: 要求の中身,
        アクション_要求の解析: 要求の解析,
        アクション_一覧取得: 一覧取得,
        アクション_url一覧: url一覧,
        アクション_条件: 条件,
        アクション_要求の削除: 要求の削除,
    }
    変更点.append("要求の中身を読んで解析するアクションを追加")
    変更点.append("一覧取得を要求に書かれた識別子を使う形に変更")
    変更点.append(f"URLファイルの保存先を設定: {urlフォルダ}")
    変更点.append("一覧が空のときはURLファイルを作らない(条件で囲む)")
    変更点.append("処理後に要求を削除するアクションを追加")

    return 定義, 変更点


def main() -> int:
    引数の解析 = argparse.ArgumentParser(description=__doc__)
    引数の解析.add_argument("入力", type=Path, help="元の definition.json のパス")
    引数の解析.add_argument("出力", type=Path, help="書き換えた定義の出力先")
    引数の解析.add_argument(
        "--由来",
        choices=("channel", "personal"),
        help="台帳の source に入れる値(フロー①のときは必須)",
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
    引数の解析.add_argument(
        "--フロー2",
        action="store_true",
        help="フロー①の定義からフロー②(ダウンロードURLの発行)を作る",
    )
    引数の解析.add_argument("--フロー名", default="トランスクリプトURL発行")
    引数 = 引数の解析.parse_args()

    元の定義 = json.loads(引数.入力.read_text(encoding="utf-8"))

    if 引数.フロー2:
        作業サイト = 引数.台帳の保存先サイト
        台帳の親 = 引数.台帳フォルダ.rsplit("/", 1)[0]
        新しい定義, 変更点 = フロー2を作る(
            元の定義,
            作業サイト=作業サイト,
            要求フォルダ=f"{台帳の親}/request",
            urlフォルダ=f"{台帳の親}/url",
            フロー名=引数.フロー名,
        )
    else:
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
