# teams-transcript-fetcher

Teams会議の録画から生成されるトランスクリプト(WEBVTT)を自動収集し、OneDriveへ蓄積するローカル実行バッチ。

- 全体像: [specs/architecture.md](specs/architecture.md)
- 仕様: [specs/transcript-auto-fetch/](specs/transcript-auto-fetch/)

## 前提条件 / 権限

| 項目 | 内容 |
|---|---|
| 実行環境 | macOS。**Python 3.11以降**(末尾 `Z` の日時を解釈できるバージョン)。**Apple標準の `/usr/bin/python3`(3.9)では動きません** |
| TLS証明書 | python.org版のPythonは**macOSのシステム証明書ストアを使わない**が、**バッチが自分で証明書バンドルを探す**ため通常は設定不要。見つからない場合の対処は下記「証明書が見つからない場合」 |
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

## 監視しているTeamsチーム

**どのフローがどのサイトを見ているかの一覧。** 障害時にどのフローを見ればよいかを切り分けるために使う。チームを追加したら必ず1行足す。

| Power Automateのフロー | 監視しているサイト | 由来(台帳の `source`) |
|---|---|---|
| トランスクリプト取得-チーム全体版-台帳版 | `<テナント>.sharepoint.com/sites/Teams115` | `channel` |
| トランスクリプト取得-Notチャネル会議-台帳版 | 個人OneDrive の `Recordings` | `personal` |
| トランスクリプトURL発行-フロー2 | (要求置き場。サイトに依存しない) | — |

**チャネル会議は1サイトにつきフローが1本必要**(トリガーが1つのサイトしか監視できないため)。追加の手順は `extend-teams-automation` Skill、または [power-automate/README.md](application/power-automate/README.md) の「別のTeamsチームを追加する」を参照。

**バッチとフロー②は追加のたびに変更する必要はない。** 台帳を集める場所はどのチームでも同じ。

## セットアップ

### 0. 証明書について(通常は何もしなくてよい)

python.org からインストールしたPythonは、macOSのシステム証明書ストアを使いません。**バッチは既定の信頼ストアが空だった場合に証明書バンドルを自分で探すため、通常は設定不要です。** 何を読み込んだかは実行ログに残ります。

```
既定の信頼ストアが空のため証明書バンドルを読み込んだ: /Users/.../certifi/cacert.pem
```

探す順番は「`certifi`(あれば)→ `/etc/ssl/cert.pem` → `/usr/local/etc/openssl/cert.pem`」です。**`certifi` に依存はしていません**(あれば使うだけで、無くても動きます)。

#### 証明書が見つからない場合

ログに次が出た場合だけ対処が必要です。

```
証明書バンドルが見つからない。TLSの検証に失敗する見込み。
```

この場合は次のいずれかを行ってください。

```
sudo /Applications/Python\ 3.*/Install\ Certificates.command
```

`3.*` は入っているPythonのバージョンに展開されます。

管理者権限が使えない場合は、`certifi` をユーザー領域に入れれば自動で拾われます。

```
python3 -m pip install --user certifi
```

なお証明書の問題で取得できない状態は、記録ファイルに `[設定の問題]` として1回だけ残ります。**待っても直らない失敗が「何も起きない」で終わらないようにしてあります。**

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

Pythonはplistに `/Library/Frameworks/Python.framework/Versions/Current/bin/python3` と書いてあり、置き換えは不要です。`Current` はpython.org版のインストーラが最新版へ張り替えるsymlinkなので、Pythonを上げても指し先が残ります。

```
cd /Users/ryosyamazaki/repo/study/apps/teams-transcript-fetcher/application
mkdir -p ~/Library/LaunchAgents ~/Library/Logs
sed -e "s|__ホームディレクトリ__|$HOME|g" launchd/com.example.teams-transcript-fetcher.plist > ~/Library/LaunchAgents/com.example.teams-transcript-fetcher.plist
/Library/Frameworks/Python.framework/Versions/Current/bin/python3 -V
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.teams-transcript-fetcher.plist
launchctl list | grep teams-transcript-fetcher
```

`python3 -V` が 3.11 以降を表示することを確認してください。`launchctl list` の2列目は最後の終了コードで、`0` なら正常です。

**Pythonのパスをバージョン番号込み(`Versions/3.13/...` など)に書き換えないでください。** Pythonを上げた時点で指し先が消え、launchdがプロセスを起動できなくなります。このとき `fetch.log` にも `~/Library/Logs/teams-transcript-fetcher.err.log` にも1行も残らず、外からは静かに止まっているようにしか見えません(`launchctl list` の2列目が `78` になるのが唯一の手がかりです)。

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

**中身が正常な台帳がここへ出ていた場合は、バッチ側の不具合です。** 2026-08-19に、OneDriveの実体化待ちで読み取れなかった正常な台帳が退避される不具合がありました(修正済み)。

### `[読み取り失敗]`

台帳が15分(3回)以上読み取れない状態が続いています。**この場合、台帳は退避されず `ledger/` に残っています**(読めていない中身を不正と断定できないため)。読めるようになれば自動的に取得されます。

1. `ledger/` の該当ファイルが「常にこのデバイス上に保持」になっているか確認します(フォルダを右クリック → 該当メニュー)
2. OneDriveの同期が止まっていないか確認します
3. `fetch.log` の `台帳を読み取れないため次回に持ち越す:` の行で理由を確認します。`Resource deadlock avoided` は実体化待ち、`Permission denied` は権限の問題です

## URLの再発行(フェーズ2)

**実装済みで、実機の通し確認も完了しています**(2026-08-19)。PCが停止している間にURLの期限が切れた録画も、録画の作成時点でトランスクリプトが未生成だった録画も取得できます。

バッチが「有効なURLがない」と判定すると `request/` に発行要求を書き、フロー②(1分間隔)が一覧を取り直してURLを `url/` に発行し、次のバッチがそれで取得します。

正常に動いたときのログはこう出ます。

```
発行を要求した: 録画=... 理由=発行から30分を超えている 累積=1回
URLの鮮度: 録画=... 出所=url置き場 発行からの経過=4.9分
取得成功: 録画=... 出力=....vtt 1972バイト 発行からの経過=4.9分
全件を保存し終えたため台帳を削除した: 録画=...
```

**`出所=url置き場` がこの経路を通った証拠です**(`出所=台帳` はフロー①が発行したURLをそのまま使った場合)。

残る対象外は「全件を保存し終えた後にトランスクリプトが増えたケース」だけです([specs/transcript-auto-fetch/requirements.md](specs/transcript-auto-fetch/requirements.md) のスコープ外)。

### 動かないときの切り分け

1. `request/` にファイルが残り続けている → フロー②が動いていない(オフ、または監視先が違う)
2. `request/` は消えるが `url/` ができない → フロー②の実行履歴で一覧取得の応答を確認する
3. `url/` はできるが取得されない → `url/` の中身の `recordingId` がファイル名と一致しているか確認する
