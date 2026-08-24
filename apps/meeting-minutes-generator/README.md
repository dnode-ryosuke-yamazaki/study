# meeting-minutes-generator

Teams会議のトランスクリプト(WEBVTT)から議事録Markdownを `claude -p` で全自動生成し、OneDriveへ保存+要約をTeamsチャネルに自動投稿するローカル実行バッチ。

- 全体像・機能マップ: [specs/architecture.md](specs/architecture.md)
- 仕様: [specs/minutes-auto-generation/](specs/minutes-auto-generation/)
- 上流(トランスクリプトの供給元): [../teams-transcript-fetcher/](../teams-transcript-fetcher/)

## 開発コマンド

```
cd application
python3 -m unittest discover -s tests -t .
```

lint・buildコマンドは未整備です。

テストや手元実行で実物のOneDrive同期フォルダ・状態ファイルに触れないよう、作業フォルダと状態フォルダは環境変数で差し替えられます(状態フォルダを差し替えずに手元実行すると、実運用の初回判定が壊れます):

```
MINUTES_GENERATOR_WORK_DIR=/tmp/minutes-test MINUTES_GENERATOR_STATE_DIR=/tmp/minutes-test-state python3 generate_minutes.py
```

## セットアップ

### 1. 前提を確認する

- 上流の teams-transcript-fetcher が動いており、`00_root/auto/transcript/vtt/` にトランスクリプトが溜まること
- `claude` CLIがログイン済みで、ターミナルから `claude -p "テスト"` が応答すること(バッチはlaunchd経由で `claude -p` を起動します)

### 2. OneDriveフォルダを用意する

`00_root/auto/` 配下に次の2フォルダを作ります(初回実行時にバッチも自動作成しますが、Power Automateフローの設定で先に必要になります)。

```
auto/
├── minutes/                    # 成果物。議事録Markdownがここに溜まる
└── teamsNotice/
    └── minutesNotice/          # Teams投稿用。ここへのファイル作成をPower Automateが検知する
```

**投稿用ファイルの置き場は既存のTeams投稿用フローの監視範囲と重ねないでください。** Teams投稿系のフローは `00_root/auto/teamsNotice/` 配下に投稿先ごとのサブフォルダを持つ運用で(例: 既存のdaily-report用は `teamsNotice/general/`)、本機能もその並びの専用サブフォルダ `minutesNotice/` を使います。

### 3. Teams投稿用のPower Automateフローを新設する

「OneDriveにファイルが作成されたとき」トリガー+Teams「メッセージを投稿する」アクションのフローを作ります(daily-report-to-teamsで実機確認済みの方式)。

1. トリガー: **OneDrive for Business「ファイルが作成されたとき」**、対象フォルダに `00_root/auto/teamsNotice/minutesNotice` を指定し、「ファイル コンテンツを含める」をはいにする。**`auto/teamsNotice/` またはその親を監視する既存フローがある場合は、その「サブフォルダーを含める」がオフであることを確認する**(オンだと議事録ファイルが既存フローにも検知され二重投稿になる)
2. アクション: **Teams「チャットまたはチャネルでメッセージを投稿する」**、投稿者=フローボット、投稿先=投稿したいチーム・チャネル(固定の1チャネル)、メッセージ=トリガーの「ファイル コンテンツ」
3. 保存してオンにする

投稿用ファイルの中身はHTML(Teamsはメッセージ本文をHTMLとして解釈するため)。投稿には要約部分(会議メタ情報・要約・決定事項・TODO。デイリー系会議ではこれに進捗が加わります)だけが含まれ、末尾に議事録全文を開くリンクが付きます。

**フローのメッセージ欄には「ファイル コンテンツ」だけを入れてください。** 保存先パスなどを添える行(例: `履歴保存: /00_root/auto/teamsNotice/minutesNotice/minutes-20260824-160000.txt`)を入れると、投稿の最下部にその行が出ます。バッチはこの行を出力しないため、投稿に出ている場合はフロー側の設定です。消すには Power Automate でフローを編集 → 「チャットまたはチャネルでメッセージを投稿する」アクションを開く → Message欄から該当の行を削除 → 保存、の順に操作してください。

### 4. 定期実行に登録する

`launchd/com.example.meeting-minutes-generator.plist` のプレースホルダを実際のパスに置き換えてから配置します。

**Pythonの実体を絶対パスで埋め込みます。** `/usr/bin/python3` はApple標準の3.9で、このコードは動きません。

```
cd /Users/ryosyamazaki/repo/study/apps/meeting-minutes-generator/application
mkdir -p ~/Library/LaunchAgents ~/Library/Logs
sed -e "s|__ホームディレクトリ__|$HOME|g" -e "s|__PYTHON__|$(which python3)|g" launchd/com.example.meeting-minutes-generator.plist > ~/Library/LaunchAgents/com.example.meeting-minutes-generator.plist
grep -A2 ProgramArguments ~/Library/LaunchAgents/com.example.meeting-minutes-generator.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.meeting-minutes-generator.plist
launchctl list | grep meeting-minutes-generator
```

`grep` の出力で、Pythonのパスが 3.10 以降のものになっていることを確認してください。

### 5. 動作確認

```
tail -f ~/Library/Application\ Support/meeting-minutes-generator/minutes.log
```

10分以内に `バッチ開始:` と `バッチ終了:` の行が出れば動いています。**初回実行は既存VTTを処理済みとして登録するだけで、議事録は生成しません**(過去分の遡及処理はスコープ外)。以降、新しく届いたVTTだけが対象になります。

## 設定の変更

パス・しきい値などの既定値は [application/config.py](application/config.py) にあります。次の値は環境変数で上書きできます(launchdで動かす場合はplistの `EnvironmentVariables` に書きます)。

| 環境変数 | 用途 | 既定値 |
|---|---|---|
| `MINUTES_GENERATOR_WORK_DIR` | 作業フォルダ(OneDriveの `00_root/auto`)の差し替え | OneDrive同期フォルダ |
| `MINUTES_GENERATOR_STATE_DIR` | 状態フォルダの差し替え | `~/Library/Application Support/meeting-minutes-generator` |
| `MINUTES_GENERATOR_CLAUDE` | `claude` の場所を明示指定 | 探索(PATH → 既知のインストール先) |
| `MINUTES_GENERATOR_DAILY_KEYWORDS` | デイリー系会議の判定語(カンマ区切り) | `デイリー,daily,朝会,スタンドアップ,standup` |
| `MINUTES_GENERATOR_WEB_VIEWER` | 議事録を開くファイルビューアのURL | 個人OneDriveの `onedrive.aspx` |
| `MINUTES_GENERATOR_WEB_DIR` | 作業フォルダに対応する共有ストレージのサーバー相対パス | `/personal/.../Documents/00_root/auto` |

**デイリー系会議**(ファイル名に判定語を含む会議)では、議事録に「進捗」の見出しが加わり、担当者ごとに作業実績・作業予定・課題が書かれます。決定事項・TODOには進捗報告以外だけが入ります。

**議事録全文へのリンク**は、共有ストレージのファイルビューアで開く形式のURLです(ファイルを直接指すURLはブラウザ内で表示されず必ずダウンロードになるため)。`MINUTES_GENERATOR_WEB_VIEWER` / `MINUTES_GENERATOR_WEB_DIR` の値は、ブラウザで議事録フォルダを開いたときのアドレスバーから取れます:

- ビューア: `?` より前の部分(例: `https://<テナント>-my.sharepoint.com/personal/<ユーザー>/_layouts/15/onedrive.aspx`)
- サーバー相対パス: `id=` の値をデコードしたもの(例: `/personal/<ユーザー>/Documents/00_root/auto`)。議事録フォルダのパスは末尾に `/minutes` を足したものが自動で使われます

どちらかが空の場合、投稿の末尾はリンクではなくファイル名の案内文になります。

## 解除

```
launchctl bootout gui/$(id -u)/com.example.meeting-minutes-generator
rm ~/Library/LaunchAgents/com.example.meeting-minutes-generator.plist
```

## ログと状態の場所

| 種類 | 場所 | 内容 |
|---|---|---|
| 実行ログ | `~/Library/Application Support/meeting-minutes-generator/minutes.log` | 既定INFO。5世代でローテーション。**トランスクリプト・議事録の本文は出力しません** |
| 状態ファイル | `~/Library/Application Support/meeting-minutes-generator/state.json` | 処理済み・再試行回数・対象外の記録 |
| ロック | `~/Library/Application Support/meeting-minutes-generator/minutes.lock` | 二重起動の防止。最後に処理が進んでから30分を過ぎた残骸は自動回収。処理中は1件ごとに時刻を更新するため、多数のVTTを順に処理する長い実行でも回収されません(1件の処理は生成タイムアウトの15分で必ず打ち切られるため、更新の間隔が30分に達しません) |
| 起動失敗の出力 | `~/Library/Logs/meeting-minutes-generator.{out,err}.log` | Pythonが起動できなかった場合など |

## トラブル対応

### `生成失敗` が繰り返し出る

ログの `分類=` を確認してください。

- `起動失敗` で `claudeコマンドが見つからない` と出る場合: バッチは「環境変数 `MINUTES_GENERATOR_CLAUDE` → PATH → 既知のインストール先(`~/.local/bin/claude`・`~/.claude/local/claude`・`/usr/local/bin`・`/opt/homebrew/bin` 等)」の順に探します。**launchdはログインシェルのPATHを継承しないため、ターミナルで `claude` が動いてもここで失敗することがあります。** どの候補にも無い場合は、`which claude` の結果をplistの `EnvironmentVariables` に `MINUTES_GENERATOR_CLAUDE` として追記してから再登録してください
- `タイムアウト` / `終了コード非0` / その他の `起動失敗`: `claude` CLIの状態を確認してください(ログイン切れなど)。launchdの環境はターミナルと異なるため、`~/Library/Logs/meeting-minutes-generator.err.log` も確認してください
- `検証NG`: 生成結果に必須見出しが欠けています。同じVTTで3回失敗すると対象外になります

### 対象外になったVTTをもう一度処理したい

`state.json` の `excluded` と `retry_counts` から該当のVTTファイル名のエントリを削除すると、次回実行で再度対象になります。

### `状態ファイルが壊れているため処理を中断する` が出る

`state.json` がJSONとして不正です。バッチは意図的に初期化しません(初期化すると既処理分を再生成してTeamsへ再投稿してしまうため)。バックアップやログの `議事録の保存成功:` の行から処理済みのVTT名を復元して `processed` に登録し直すか、全件再投稿を許容できる場合のみ `state.json` を削除して初回初期化からやり直してください(初回初期化はその時点の既存VTTを全件処理済みとして登録します)。
