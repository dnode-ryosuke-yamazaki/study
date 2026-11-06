# digest-platform

Digest系5アプリ(ai-dev-digest・news-digest・future-digest・research-digest・trend-digest)の共通基盤。仕様は [specs/architecture.md](specs/architecture.md) を、実行係(バッチの定時起動と成否の記録)の仕様は [specs/batch-runner/](specs/batch-runner/) を参照。

## 前提条件 / 権限

- 実行場所: このMacの手元のターミナル。`launchctl` と `~/Library/LaunchAgents/` への書き込みは Claude Code のサンドボックスからはできないため、plist の生成と登録は運営者が手元で行う
- 必要なツール: Node.js(`node`・`npm`)、Claude Code CLI(`claude`)、Python 3(`python3`。標準ライブラリだけを使い、`requirements.txt` は無い)
- 認証: Claude の呼び出しは運営者の Claude Code のログイン(サブスクリプション)で行う。APIキーはファイル・環境変数に置かない
- 社内プロキシのCAバンドル: `~/Library/Application Support/ca-bundle/ca-bundle.pem` があればそれを、無ければ `/etc/ssl/cert.pem` を実行係が使う
- コマンド中の `research-digest` は例。他のアプリは名前を読み替える

## テスト

初回だけ、手元のターミナルで依存パッケージを入れる(実行係はバッチの起動に `application/node_modules/.bin/tsx` を使うため、定時起動の前にも必要)。

```bash
cd "$HOME/repo/study/apps/digest-platform/application"
npm install
```

TypeScript 側の単体テスト(`tests/batch/`)と型検査。

```bash
cd "$HOME/repo/study/apps/digest-platform/application"
npm test
npm run typecheck
```

実行係(Python)の単体テスト(`tests/runner/`)。

```bash
cd "$HOME/repo/study/apps/digest-platform/application"
python3 -m unittest discover -s tests/runner -t .
```

性能テスト(`tests/perf/`。入口から起動コマンドの直前までが5秒以内かを測る)は毎回の TDD では回さず、単独で回す。

```bash
cd "$HOME/repo/study/apps/digest-platform/application"
python3 -m unittest discover -s tests/perf -t .
```

## plist の生成

`application/launchd/make_plists.py` がアプリ登録表 `application/launchd/apps.json` を読み、アプリ×系統ごとの plist を `~/Library/LaunchAgents/` に書く。

- plist が作られるのは、登録表で `publish.enabled` を `true` にしたアプリの記事公開と、`review.dayOfMonth` に日を入れたアプリの月次見直しだけ。どちらも無ければ何も書かずにその旨を表示する
- 記事公開は 06:30 と再実行の 10:30・14:30・18:30、月次見直しは登録表の日の 07:30 に起動する。登録した直後には起動しない(`RunAtLoad` を書かない)
- ジョブ名は `com.example.digest-<アプリ名>-<系統>`(系統は `publish` か `review`)
- node・claude・python3 の絶対パスを渡す。存在しないパスや、`Versions/3.12` のようにバージョン番号を含むパス(更新で変わる)は理由を表示して生成を止める(終了コード2)。止まったら、表示されたパスを `Versions/Current` などバージョン番号を含まないパスに替えて実行し直す

```bash
cd "$HOME/repo/study/apps/digest-platform/application"
python3 launchd/make_plists.py --node "$(command -v node)" --claude "$(command -v claude)" --python "$(command -v python3)"
```

書いた plist のパスが1行ずつ表示される。出力先を変えたいときは `--out <フォルダ>` を足す(既定は `~/Library/LaunchAgents/`)。

## launchd への登録・解除・即時起動

初めて登録する(research-digest の記事公開の例)。

```bash
cd "$HOME/Library/LaunchAgents"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.example.digest-research-digest-publish.plist"
launchctl print gui/$(id -u)/com.example.digest-research-digest-publish | head -20
```

plist を生成し直したときは、いったん解除してから登録し直す(登録済みのまま `bootstrap` すると失敗する)。

```bash
cd "$HOME/Library/LaunchAgents"
launchctl bootout gui/$(id -u)/com.example.digest-research-digest-publish
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.example.digest-research-digest-publish.plist"
```

今すぐ定時と同じ起動をさせる。手動実行と違い、定時の試行として回数に数えられ、失敗すれば失敗通知も出る(バッチが成功すれば Teams への投稿など本番と同じ外部への書き出しも起きる)。

```bash
cd "$HOME/Library/LaunchAgents"
launchctl kickstart -k gui/$(id -u)/com.example.digest-research-digest-publish
```

止めたままにする。`bootout` だけでは plist が残っているため再ログインで登録が戻る。止めた状態を続けるには `disable` も行う(再開するときは `enable` してから `bootstrap` する)。

```bash
cd "$HOME/Library/LaunchAgents"
launchctl bootout gui/$(id -u)/com.example.digest-research-digest-publish
launchctl disable gui/$(id -u)/com.example.digest-research-digest-publish
```

月次見直しのジョブはジョブ名の末尾が `-review` になる(例: `com.example.digest-research-digest-review`)。

## アプリを有効にするとき

failure-notification(失敗通知の判定関数 `failure_notification`)を実装するまでは、どのアプリも有効にしない。実装前に有効にすると、失敗が確定するたびに判定関数を読み込めず「通知の失敗」(要約ログに WARNING と `RUN-FAILED`)になり、35日間、起動のたびに渡し直しが繰り返される。

各アプリの spec を実装したら、次をまとめて行う。

1. `application/launchd/apps.json` のそのアプリの `publish.enabled` を `true` にする(月次見直しも動かすなら `review.dayOfMonth` に日を入れる)
2. 「plist の生成」のコマンドで plist を生成し直す
3. 「launchd への登録・解除・即時起動」のコマンドで、そのアプリのジョブを登録(登録済みなら解除してから登録)し直す
4. 日次ヘルスチェックの宣言にそのアプリの記事公開を足す。要約ログ `runner-publish.log` を `doneMarker: "RUN-SUCCEEDED"`・`failureMarkers: ["RUN-FAILED"]` で読み、時刻の一覧は `["06:30","10:30","14:30","18:30"]`(plist の起動時刻と一致させる)。月次見直しは稼働判定の対象外なので足さない

## 手動実行

launchd を通さずに手元から実行係を起動する。成否の判定・記録・失敗の引き渡しは定時と同じに行う。

```bash
cd "$HOME/repo/study/apps/digest-platform/application"
python3 launchd/runner.py research-digest publish --manual
```

- 配信日の引数は無い。配信日は定時と同じ規則で決まる(06:30 より前なら前日を基準日とし、基準日から遡って最も近い配信曜日)。そのため、やり直せるのはその配信日が直近の配信曜日である間だけ(毎日のアプリは翌日の 06:30 より前まで、週1回のアプリは次の配信曜日の 06:30 より前まで)
- 失敗が確定した日も、そのまま `--manual` で起動できる(成功すれば成功に変わる)
- 手動実行は再実行の回数に数えず、失敗しても定時の再実行の判定を変えない
- 成功済みの日は手動実行でも起動しない(要約ログに `result=already_succeeded`)
- 月次見直しは再実行しないので、失敗したら系統を `review` にして手動実行で補う
- 終了コード: 0=成功・起動しなかった(成功済み・ロック中)、1=バッチが一時的な失敗、2=再試行しても直らない失敗・未登録・実行係自身のエラー
- シェルに環境変数 `DIGEST_DATA_DIR` が残っていると、記録とログが既定の `~/Library/Application Support/digest/<アプリ名>/` でなくその場所に書かれる。手動実行の前に `unset DIGEST_DATA_DIR` で外しておく

## 成功済みの日をやり直す

成功済みの配信日をもう一度生成し直したいときだけ、その日の実行状態ファイルを消してから手動実行する。消すのは、手動実行が対象にする直近の配信日のファイルだけにする(それより前の配信日のファイルを消すと、次の起動で「記録なし」の失敗として締められ、失敗通知が出ることがある)。消したファイルの試行の記録は戻らない。

対象のファイルを確かめる(research-digest の記事公開の例。ファイル名は `<配信日>.json`、編を持つアプリは `<配信日>-<編>.json`)。

```bash
cd "$HOME/Library/Application Support/digest/research-digest/runs/publish"
ls -l
```

2026-11-07 の回をやり直す例(日付はやり直したい配信日に読み替える)。

```bash
cd "$HOME/Library/Application Support/digest/research-digest/runs/publish"
rm "$HOME/Library/Application Support/digest/research-digest/runs/publish/2026-11-07.json"
cd "$HOME/repo/study/apps/digest-platform/application"
python3 launchd/runner.py research-digest publish --manual
```

## 結果の確かめ方とファイルの場所

アプリごとのデータフォルダ `~/Library/Application Support/digest/<アプリ名>/`(権限700、git 管理外)に置かれる。

| 何か | 場所(research-digest の記事公開の例) |
|---|---|
| 要約ログ(起動ごとの「実行開始」「実行終了」の1行) | `~/Library/Application Support/digest/research-digest/runner-publish.log` |
| 詳細ログ(バッチの出力。定時は `<配信日>[-<編>]-<回>.log`、手動は `<配信日>[-<編>]-manual-<時分秒>.log`) | `~/Library/Application Support/digest/research-digest/logs/publish/` |
| 実行状態ファイル(試行回数・各回の結果・通知済み) | `~/Library/Application Support/digest/research-digest/runs/publish/<配信日>[-<編>].json` |
| Claude の呼び出しの控え(指示文と応答) | `~/Library/Application Support/digest/research-digest/claude-io/publish/<配信日>[-<編>]/` |
| launchd の標準出力・標準エラー | `~/Library/Logs/digest-research-digest-publish.log` |

- 要約ログの成功の行には `RUN-SUCCEEDED`、失敗が確定した行には `RUN-FAILED` が付く
- 実行状態ファイル・詳細ログ・控えは、最後の更新から90日を過ぎると実行係が次の起動時に消す。要約ログと launchd の標準出力は消さない
- 壊れた実行状態ファイルは `<元の名前>.corrupt-<YYYYMMDD-HHMMSS>` に退避される

要約ログの最後の20行を見る。

```bash
cd "$HOME/Library/Application Support/digest/research-digest"
tail -n 20 "$HOME/Library/Application Support/digest/research-digest/runner-publish.log"
```

## データフォルダを Claude Code から読み書きできるようにする

Claude Code の対話セッションからデータフォルダ(ログ・実行状態ファイル)を読み書きするには、`~/.claude/settings.json` の `permissions.additionalDirectories` にデータフォルダを足す(運営者の手元作業。launchd からの実行には不要)。

登録するパスを確かめる。

```bash
cd "$HOME"
echo "$HOME/Library/Application Support/digest"
```

表示されたパスを、`~/.claude/settings.json` の `permissions.additionalDirectories` の配列に1つ足す。既にある要素は消さずに末尾へ追加する(抜粋。運営者が ryosyamazaki の場合)。

```json
{
  "permissions": {
    "additionalDirectories": [
      "/Users/ryosyamazaki/Library/Application Support/digest"
    ]
  }
}
```
