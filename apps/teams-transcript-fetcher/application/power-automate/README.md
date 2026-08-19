# Power Automateフローの改造手順

録画を検知して**台帳**を書くようにフロー①を改造する手順です。

**フロー定義そのものはこのリポジトリに置きません。** 定義ファイルにはテナント識別子・接続識別子・ドライブ識別子が含まれ、[design.md#セキュリティ](../../specs/transcript-auto-fetch/design.md#セキュリティ)で「リポジトリのドキュメントへ転記しない」と決めているためです。代わりに、エクスポートした定義を読み込んで書き換えるスクリプト([patch_flow_definition.py](patch_flow_definition.py))を置いています。

## 前提条件 / 権限

| 項目 | 内容 |
|---|---|
| 権限 | 対象フローの編集権限。フローのエクスポート・インポートができること |
| 実行環境 | Python 3(標準ライブラリのみ) |
| 実行場所 | `apps/teams-transcript-fetcher/application/power-automate/` |
| 対象フロー | 「トランスクリプト取得-チーム全体版」(チャネル会議用)と「トランスクリプト取得-Notチャネル会議」(通常会議用)の2本 |
| ネットワーク | Power Automateポータルへのアクセス(手作業) |

> **必ず元のフローを複製してから試してください。** 動かなくなったときに元へ戻せるようにするためです。

## 何が変わるか

| # | 変更 | なぜ |
|---|---|---|
| 1 | トランスクリプト一覧の先頭1件だけを取る箇所を、**全件を配列にする** | 元のフローは `value[0]` しか見ておらず、1つの会議に複数のトランスクリプトがあると取りこぼす |
| 2 | 保存内容をURL単体から**台帳(JSON)**に変える | 項目名は [design.md#ファイルの項目名の取り決め](../../specs/transcript-auto-fetch/design.md#ファイルの項目名の取り決め) |
| 3 | 保存先を**個人OneDriveの台帳置き場**に変える(コネクタは変更しない) | SharePointライブラリの同期設定を不要にする |
| 4 | ファイル名を**録画の識別子 + `.json`** にする | バッチとの唯一の共有点を録画の識別子だけにする |
| 5 | 一覧が空でも、取得に失敗しても**台帳を作る** | 台帳がないとその録画が永久に対象外になる |
| 6 | 通常会議用フローの、**ドライブ識別子をハードコードした呼び出し2件を削除** | 結果を使っていない無駄な呼び出しで、別環境にコピーすると他人のドライブを見に行く |

## 手順

### 1. フローを複製する

Power Automateポータルで対象フローを開き、「名前を付けて保存」で複製します。以降は複製したフローで作業します。

### 2. エクスポートする

複製したフローを「エクスポート → パッケージ (.zip)」で書き出し、zipを展開します。`Microsoft.Flow/flows/<GUID>/definition.json` があるはずです。

### 3. 定義を書き換える

個人OneDriveのサイトURLは、通常会議用フローのトリガーの `dataset` と同じ値です。手で転記せず、エクスポートから読み取って渡します。

```
cd /Users/ryosyamazaki/repo/study/apps/teams-transcript-fetcher/application/power-automate
サイト=$(python3 -c "
import json,sys,pathlib
d=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
print(list(d['properties']['definition']['triggers'].values())[0]['inputs']['parameters']['dataset'])
" "<通常会議用フローのdefinition.jsonのパス>")
python3 patch_flow_definition.py "<チャネル会議用のdefinition.json>" "<出力先>/definition.json" --由来 channel --台帳の保存先サイト "$サイト"
python3 patch_flow_definition.py "<通常会議用のdefinition.json>" "<出力先>/definition.json" --由来 personal --台帳の保存先サイト "$サイト"
```

変更内容が一覧で表示されます。

### 4. zipを作り直してインポートする

展開したフォルダ内の `definition.json` を書き換えたものに差し替え、同じ構成でzipに固め直します。Power Automateの「インポート → パッケージ (.zip)」で取り込みます。

**インポート時に接続(コネクション)の紐付けを求められます。** 既存のSharePointコネクションを選んでください。コネクタは変更していないので、新しい接続の追加は不要です。

### 5. 動作確認

1. 会議を録画して終了する(または録画フォルダにmp4を置く)
2. フローの実行履歴で成功していることを確認する
3. `~/Library/CloudStorage/OneDrive-<テナント>/00_root/auto/transcript/ledger/` に `<録画の識別子>.json` ができていることを確認する
4. 中身に `meetingName` / `siteUrl` / `driveId` / `recordingId` が入っていることを確認する
5. バッチのログ(`~/Library/Application Support/teams-transcript-fetcher/fetch.log`)で台帳が読めていることを確認する

## うまくいかないときに見るところ

### 台帳ファイルができない

フローの実行履歴で「ファイルの作成」を確認します。`folderPath` のフォルダが存在しない場合は失敗します。**先に `ledger/` フォルダを作っておいてください。**

### 台帳の `recordingId` が空になる

トリガーが `{DriveItemId}` を提供していない可能性があります。**この値が取れるかは未確認です**([requirements.md の検証項目](../../specs/transcript-auto-fetch/requirements.md#前提検証項目))。フローの実行履歴でトリガーの出力(raw)を開き、実際に何が入っているかを確認してください。名前が違う場合はスクリプトの `_録画の識別子` を直します。

### 台帳の `recordingCreatedAt` が空になる

トリガーの `Created` が取れていません。**この場合もバッチは動きます**(台帳ファイルの更新時刻で代用する設計のため)。ファイル名の時刻が録画時刻より少し後になるだけです。直したい場合は、実行履歴でトリガーの出力を見て正しい項目名に置き換えてください。

### 台帳の中身が JSON になっていない

「ファイルの作成」の `body` が `@string(outputs('台帳を組み立てる'))` になっているか確認します。`string()` を外すとオブジェクトがそのまま渡り、想定と違う形で保存されます。

### ファイル名に使えない文字が入って失敗する

録画の識別子にファイル名として使えない文字が含まれている場合です。**未確認の項目です**([検証項目#10](../../specs/transcript-auto-fetch/requirements.md#前提検証項目))。この場合は識別子を安全な文字列へ変換する規則を [design.md#識別子とファイル名の規則](../../specs/transcript-auto-fetch/design.md#識別子とファイル名の規則唯一の定義) に追加し、スクリプトとバッチの両方に反映します(**3者で共有する規則なので片方だけ変えてはいけません**)。

## フェーズ2で追加するフロー②

要求置き場を監視してダウンロードURLを発行し直すフローは、まだ作っていません。詳細は [tasks.md](../../specs/transcript-auto-fetch/tasks.md) の T28。
