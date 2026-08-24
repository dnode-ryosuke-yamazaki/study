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

投稿用ファイルの中身はHTML(Teamsはメッセージ本文をHTMLとして解釈するため)。投稿には要約部分(会議メタ情報・要約・決定事項・TODO)だけが含まれ、末尾に全文の議事録ファイルへの案内が付きます。

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
| ロック | `~/Library/Application Support/meeting-minutes-generator/minutes.lock` | 二重起動の防止。30分を過ぎた残骸は自動回収 |
| 起動失敗の出力 | `~/Library/Logs/meeting-minutes-generator.{out,err}.log` | Pythonが起動できなかった場合など |

## トラブル対応

### `生成失敗` が繰り返し出る

ログの `分類=` を確認してください。

- `タイムアウト` / `終了コード非0` / `起動失敗`: `claude` CLIの状態を確認してください(ログイン切れ、パスが通っていない等)。launchdの環境はターミナルと異なるため、`~/Library/Logs/meeting-minutes-generator.err.log` も確認してください
- `検証NG`: 生成結果に必須見出しが欠けています。同じVTTで3回失敗すると対象外になります

### 対象外になったVTTをもう一度処理したい

`state.json` の `excluded` と `retry_counts` から該当のVTTファイル名のエントリを削除すると、次回実行で再度対象になります。

### `状態ファイルが壊れているため処理を中断する` が出る

`state.json` がJSONとして不正です。バッチは意図的に初期化しません(初期化すると既処理分を再生成してTeamsへ再投稿してしまうため)。バックアップやログの `議事録の保存成功:` の行から処理済みのVTT名を復元して `processed` に登録し直すか、全件再投稿を許容できる場合のみ `state.json` を削除して初回初期化からやり直してください(初回初期化はその時点の既存VTTを全件処理済みとして登録します)。
