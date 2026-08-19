# teams-transcript-fetcher

Teams会議の録画から生成されるトランスクリプト(WEBVTT)を自動収集し、OneDriveへ蓄積するローカル実行バッチ。

- 全体像: [specs/architecture.md](specs/architecture.md)
- 仕様: [specs/transcript-auto-fetch/](specs/transcript-auto-fetch/)

## 前提条件 / 権限

| 項目 | 内容 |
|---|---|
| 実行環境 | macOS。**Python 3.11以降**(末尾 `Z` の日時を解釈できるバージョン)。**Apple標準の `/usr/bin/python3`(3.9)では動きません** |
| TLS証明書 | python.org版のPythonは**macOSのシステム証明書ストアを使わない**ため、初回に付属スクリプトの実行が必要(下記「証明書のセットアップ」) |
| 追加ライブラリ | **なし。** 実行用・開発用ともに標準ライブラリのみ |
| 必要な権限 | OneDrive同期クライアントにサインイン済みであること。M365への認証はすべて同期クライアントに委ねるため、このバッチは資格情報を一切持たない |
| 前提となる稼働 | Power Automateのフロー①(録画の検知と台帳の作成)が動作していること |
| 実行場所 | `apps/teams-transcript-fetcher/application/` |

**このバッチはPCが稼働している間しか動きません。** 取りこぼしの解消はPower Automate側のURL再発行に依存します(フェーズ2)。

## コマンド

いずれも `apps/teams-transcript-fetcher/application/` で実行します。

**テスト**

```
python3 -m unittest discover -s tests -t .
```

テスト名を1件ずつ日本語で見たいときは `-v` を付けます。各テストの直前のコメントに、対応する仕様の項目が書かれています。

**1回だけ手で実行する(動作確認)**

```
python3 fetch_transcripts.py
```

**テスト用の作業フォルダで実行する(実物の同期フォルダに触れない)**

```
TRANSCRIPT_FETCHER_WORK_DIR=/tmp/transcript-test python3 fetch_transcripts.py
```

lint・buildコマンドは未整備です。

## セットアップ

### 0. 証明書のセットアップ(python.org版のPythonを使う場合・1回だけ)

python.org からインストールしたPythonは、macOSのシステム証明書ストアを使いません。この状態でダウンロードURLへアクセスすると次のエラーになります。

```
[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate
```

付属のスクリプトを1回実行すれば解決します(バージョン番号は使用中のものに合わせてください)。

```
"/Applications/Python 3.13/Install Certificates.command"
```

**このスクリプトは Python 自身の証明書設定を行うもので、このバッチが `certifi` を import するわけではありません。** バッチのコードは標準ライブラリのみで動きます。

### 1. OneDriveの作業フォルダを用意する

既定の場所は `~/Library/CloudStorage/OneDrive-Deloitte(O365D)/00_root/auto/transcript/` です。この配下に次のフォルダができます(バッチが必要に応じて作ります)。

```
transcript/
├── ledger/     # Power Automateが作成、バッチが削除・退避
├── request/    # バッチが作成、Power Automateが削除(滞留時はバッチが退避)
├── url/        # Power Automateが作成、バッチが削除
├── vtt/        # 成果物。トランスクリプトがここに溜まる
├── invalid/    # 壊れた台帳・滞留した要求の退避先
└── _status.md  # 処理結果と失敗の記録
```

**`00_root/auto/` の直下には置かないでください。** 直下のファイル作成はTeams投稿用のPower Automateフローが検知するため、意図しない投稿が発生します。

### 2. 「常にこのデバイス上に保持」を設定する

`ledger/` と `url/` を Finder で右クリックし、**「常にこのデバイス上に保持」** を選びます。OneDriveの Files On-Demand で「オンラインのみ」の状態だと、オフライン時にバッチが読めません。

### 3. 定期実行に登録する

`launchd/com.example.teams-transcript-fetcher.plist` の `__ホームディレクトリ__` を実際のパスに置き換えてから配置します。

**Pythonの実体を絶対パスで埋め込みます。** `/usr/bin/python3` はApple標準の3.9で、このコードは動きません。

```
cd /Users/ryosyamazaki/repo/study/apps/teams-transcript-fetcher/application
mkdir -p ~/Library/LaunchAgents ~/Library/Logs
sed -e "s|__ホームディレクトリ__|$HOME|g" -e "s|__PYTHON__|$(which python3)|g" launchd/com.example.teams-transcript-fetcher.plist > ~/Library/LaunchAgents/com.example.teams-transcript-fetcher.plist
grep -A2 ProgramArguments ~/Library/LaunchAgents/com.example.teams-transcript-fetcher.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.teams-transcript-fetcher.plist
launchctl list | grep teams-transcript-fetcher
```

`grep` の出力で、Pythonのパスが 3.11 以降のものになっていることを確認してください。

### 4. 動作確認

```
tail -f ~/Library/Application\ Support/teams-transcript-fetcher/fetch.log
```

5分以内に `実行開始:` と `実行終了:` の行が出れば動いています。台帳が0件でも実行はされます。

## 解除

```
launchctl bootout gui/$(id -u)/com.example.teams-transcript-fetcher
rm ~/Library/LaunchAgents/com.example.teams-transcript-fetcher.plist
```

## ログとレポートの場所

| 種類 | 場所 | 内容 |
|---|---|---|
| 実行ログ | `~/Library/Application Support/teams-transcript-fetcher/fetch.log` | 既定DEBUG。5世代でローテーション。**URLとトランスクリプト本文は出力しません** |
| 処理結果の記録 | 作業フォルダの `_status.md` | 失敗した対象。OneDrive上にあるのでPCの前にいなくても見られます |
| 取得済み記録 | `~/Library/Application Support/teams-transcript-fetcher/state.json` | 同期フォルダの**外**に置きます(同期すると競合ファイルで壊れるため) |
| 起動失敗の出力 | `~/Library/Logs/teams-transcript-fetcher.{out,err}.log` | Pythonが起動できなかった場合など |

## 運用: 記録に何か出たときの対処

`_status.md` に行が追記されたときの対処です。**同じ対象の同じ失敗は1回しか追記されません**(5分間隔で実行されるため、抑止しないと同じ内容で埋まります)。

### `[トランスクリプト0件]`

**この行は日常的に出る想定です。** その会議で文字起こしが有効になっていなかった場合、録画はあってもトランスクリプトが生成されません。台帳は作られるので、要求が出続けても保存は進みません。

対処: そのまま放置しても実害はありませんが、`ledger/` の該当ファイルを `invalid/` へ移すと終端します。ファイル名は録画の識別子です。

### `[取得失敗]`

調査が必要です。ダウンロードURLへのアクセスが繰り返し失敗しています。

**まず `fetch.log` に `CERTIFICATE_VERIFY_FAILED` が出ていないか確認してください。** 出ていればバッチの問題ではなく、上記「証明書のセットアップ」が済んでいないだけです(この場合は一時的失敗に分類されるので、`[取得失敗]` にはなりません)。

1. `fetch.log` で該当の録画の `恒久的失敗:` の行を探し、理由を確認します
2. **`許可していないホストのURLを拒否した: host=...`** が出ている場合は、`config.py` の `既定の許可するホスト接尾辞` にそのホストを追加します(実際のホストは未確認のため、初回はここで判明する想定です)
3. **`応答本文がWEBVTTではない`** が出ている場合は、URLの期限切れかアクセス権の問題です。会議の録画からトランスクリプトを手動でダウンロードしてください
4. 対処後は `state.json` の該当録画のエントリを消すと、次回から再試行されます

### `[件数不足]`

調査が必要です。既知の件数分のダウンロードURLがいつまでも揃いません。`fetch.log` の `既知件数=` と `URL数=` を比べ、差が続いているかを確認してください。

### `[長期滞留]`

7日以上処理されていない台帳があります。Power Automateのフローが停止している可能性が高いので、フローの実行履歴を確認してください。

### `[台帳が不正]`

`invalid/` に退避された台帳を開き、必要な項目(`meetingName` / `siteUrl` / `driveId` / `recordingId`)が入っているか確認してください。フロー①の改造で項目名を間違えた場合にここへ出ます。確認後は削除して構いません。

## まだ実装していないこと(フェーズ2)

現在はフェーズ1です。**Power AutomateがダウンロードURLを発行し直す経路がまだありません。** そのため次の場合は取得できません。

- PCが停止している間にURLの期限が切れた録画
- 録画の作成時点でトランスクリプトが未生成だった録画

フェーズ2で追加するのは、バッチが `request/` に発行要求を書き、Power Automateのフロー②がそれを見てURLを発行する経路です。詳細は [specs/transcript-auto-fetch/tasks.md](specs/transcript-auto-fetch/tasks.md) の T23〜T28。
