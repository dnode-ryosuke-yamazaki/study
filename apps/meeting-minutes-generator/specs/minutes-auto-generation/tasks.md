# 会議後の議事録自動生成 タスク分解

> TDDで進める。各タスクは 🔴 Red(失敗するテストを書く) → 🟢 Green(最小実装) → 🔵 Refactor の順で進める。

テストは `apps/meeting-minutes-generator/application/tests/` に unittest で書き、`python3 -m unittest discover -s tests -t .` で実行する(teams-transcript-fetcherと同じ)。`claude -p` の呼び出し・OneDriveフォルダはテストではモック・一時ディレクトリに差し替える。

## タスク一覧

### 1. 設定モジュール(config.py)

- OneDriveの入力フォルダ(`auto/transcript/vtt/`)・議事録フォルダ(`auto/minutes/`)・投稿用フォルダ(`auto/teamsNotice/minutesNotice/`)・状態フォルダ(`~/Library/Application Support/meeting-minutes-generator/`)のパス定義
- 環境変数で作業フォルダ一式を差し替えられること(テスト用。teams-transcript-fetcherの `TRANSCRIPT_FETCHER_WORK_DIR` と同じ方式)
- 再試行上限(3回)・`claude -p` タイムアウト(15分)の定義

### 2. 状態ファイルの読み書き(state.py)

- 状態ファイルが無い場合に「初回」と判定できること
- 初回初期化: 渡されたVTT一覧を処理済みとして状態ファイルを新規作成すること
- 処理済み・対象外のVTTを判定できること
- 生成失敗の記録で再試行回数が1増えること
- 再試行回数が上限に達したVTTを対象外として記録すること
- 状態ファイルがJSONとして不正な場合、初期化せずエラーを区別して返すこと(破損検出)
- 書き込みはアトミックに行うこと(一時ファイルに書いてからリネーム)
- 二重起動防止ロックを取得・解放できること。ロックが既に存在する場合は取得失敗を返し、古いロック(30分経過)は回収して取得し直すこと(teams-transcript-fetcherのstate.pyと同じ方式)

### 3. 未処理VTTの検知(generate_minutes.py 内の走査処理)

- `vtt/` のVTT一覧と状態を突き合わせ、処理済み・対象外を除いた未処理一覧を返すこと
- VTT以外の拡張子のファイルを対象にしないこと
- 読み取れないVTT(OSエラー)をスキップし、状態を変更しないこと

### 4. claude -p の起動と生成結果の検証(claude_runner.py)

- トランスクリプト本文と構成指示からプロンプトを組み立てること(会議名・日時のヒントとしてVTTファイル名を含める)。構成指示に「議事録は日本語で書く」「決定事項・TODO・未決事項が0件でも見出しを省略せず『なし』と記載する」を含めること
- subprocessで `claude -p` を起動し標準出力を受け取ること(テストではコマンドをモックする)
- タイムアウト超過を生成失敗として返すこと
- exit code 非0を生成失敗として返すこと
- 生成結果に必須見出し(会議メタ情報、要約、決定事項、TODO、議論の経緯、未決事項・次回議題)が欠けている場合、exit 0でも生成失敗として返すこと
- 失敗理由の分類(タイムアウト・exit非0・検証NG)を返すこと(ログ用)

### 5. 議事録の保存(writer.py 相当)

- 議事録MarkdownをVTTファイル名由来の `.md` ファイル名で議事録フォルダへ保存すること
- 同名ファイルが存在する場合は上書きせず連番付きファイル名で保存すること

### 6. 要約部分の抽出とHTML変換(summary_html.py)

- 議事録Markdownから会議メタ情報・要約・決定事項・TODOの見出しセクションだけを抽出すること(議論の経緯、未決事項・次回議題は含めない)
- 抽出結果をTeamsが解釈できるHTML(見出し・入れ子リスト)に変換すること
- 末尾に全文の置き場所(議事録ファイル名)を案内する一文を付けること
- 投稿用ファイル名を `minutes-YYYYMMDD-HHMMSS.txt` 形式で一意に生成すること

### 7. バッチ本体の結合(generate_minutes.py)

- 二重起動防止ロックが取得できない場合は何もせず終了すること
- 初回実行では既存VTTを処理済み登録だけして生成せずに終了すること
- 未処理VTTを1件ずつ直列に処理し、1件の失敗が他のVTTに影響しないこと
- 生成成功 → 保存 → 処理済み記録 → 投稿用ファイル書き出し、の順で進むこと
- 投稿用ファイルの書き出しに失敗しても処理済みのままとし、WARNINGログを残すこと
- 状態ファイル破損時は処理を中断しERRORログを残すこと
- ログにトランスクリプト・議事録・プロンプトの本文を出さないこと

### 8. launchd定義と運用ドキュメント(テスト対象外)

- `application/launchd/com.example.meeting-minutes-generator.plist`(10分間隔。create-automation-batchの検証済みテンプレートに従う)
- `README.md`: セットアップ手順(plist登録・ログの場所・トラブル対応)、Power Automateフロー(OneDrive `auto/teamsNotice/minutesNotice/` 検知 → 固定チャネルへ投稿)の新設手順
