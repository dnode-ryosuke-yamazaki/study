# meeting-setup-automation

チャットで件名・参加者・所要時間・アジェンダを伝えると、参加者全員が空いている候補枠を提示し、選んだ枠でTeams会議を作成して参加者を招待する。空き時間の探索と会議の作成はテナント側のPower Automateフローが担い、Skillとフローは個人OneDrive上のファイル(台帳)で連携する。M365へのAPI認証(アプリ登録・管理者同意)を必要としない。

- 全体像・機能マップ: [specs/architecture.md](specs/architecture.md)
- 仕様: [specs/meeting-scheduling/](specs/meeting-scheduling/)
- Power Automateフローの構築手順: [application/power-automate/README.md](application/power-automate/README.md)
- チャット向けの手順(SKILL.md): `~/.claude/skills/meeting-setup/SKILL.md`(このリポジトリの外。処理はここの `application/` を絶対パスで呼ぶ)

## 前提条件 / 権限

| 項目 | 内容 |
|---|---|
| 実行環境 | macOS。Python 3.11以降(標準ライブラリのみ。追加ライブラリなし)。チャット(Claude Code)のセッションから `main.py` を呼ぶ |
| 必要な権限 | OneDrive同期クライアントにサインイン済みであること。M365への認証はすべて同期クライアントとPower Automateのコネクタに委ねるため、このアプリは資格情報を一切持たない |
| 前提となる稼働 | Power Automateフロー3本(探索・作成・会議設定通知)がオンで、下記の台帳フォルダを監視していること |
| 実行場所 | `apps/meeting-setup-automation/application/` |

**定期実行・無人実行の仕組みは持たない。** チャットからの明示起動のみで、launchdジョブは作らない。

## 開発コマンド

```
cd application
python3 -m unittest discover -s tests -t .
```

テスト名を1件ずつ見たいときは `-v` を付ける。各テストの直前のコメントに、対応する仕様の項目が書かれている。lint・buildコマンドは未整備。`node` が入っていれば、生成する選択画面のJavaScriptの構文検査も同じテストの中で走る。

テストや手元実行で実物のOneDrive同期フォルダ・作業フォルダに触れないよう、環境変数で差し替えられる。

```
MEETING_SETUP_LEDGER_ROOT=/tmp/ms-test/ledger MEETING_SETUP_NOTICE_DIR=/tmp/ms-test/notice MEETING_SETUP_WORK_DIR=/tmp/ms-test/work python3 main.py resume <依頼ID>
```

| 環境変数 | 既定 | 用途 |
|---|---|---|
| `MEETING_SETUP_LEDGER_ROOT` | `~/Library/CloudStorage/OneDrive-.../00_root/auto/meetingSetting` | 台帳フォルダのルート |
| `MEETING_SETUP_NOTICE_DIR` | `.../00_root/auto/teamsNotice/meetingSetting` | Teams通知の書き出し先 |
| `MEETING_SETUP_WORK_DIR` | `~/Library/Application Support/meeting-setup-automation` | 名簿・設定・ログ |
| `MEETING_SETUP_CANDIDATES_TIMEOUT_SEC` / `MEETING_SETUP_RESULT_TIMEOUT_SEC` | 300 | 候補・作成結果の待ち上限(秒)。2つは別々 |
| `MEETING_SETUP_POLL_INTERVAL_SEC` | 5 | 到着確認の間隔(秒) |
| `MEETING_SETUP_SYNC_GRACE_SEC` | 30 | 選択画面を書いた後にOneDrive同期を待つ猶予(秒) |
| `MEETING_SETUP_WEB_VIEWER` / `MEETING_SETUP_WEB_DIR` | (settings.json) | ビューアURLとサーバー相対パスの上書き |

## セットアップ

### 1. 台帳フォルダを作る

個人OneDriveの `00_root/auto/` 配下に次のフォルダを作る。Skillは書き出し時に無ければ作るが、Power Automateのトリガー設定に先に必要になる。

```
auto/
├── meetingSetting/
│   ├── request/         # 依頼(Skillが書く → 探索フローが読む)
│   ├── candidates/      # 候補(探索フローが書く → Skillが読む)
│   ├── selection/       # 選択結果(Skillが書く → 作成フローが読む)
│   ├── result/          # 作成結果(作成フローが書く → Skillが読む)
│   └── html/            # 候補選択画面(Skillが書く → ブラウザで開く)
└── teamsNotice/
    └── meetingSetting/  # Teams通知(Skillが書く → 会議設定通知フローが投稿)
```

同じファイルをSkillとフローの双方から書かない。通知フォルダを台帳と分けているのは、通知フローが台帳を誤検知して投稿しないため。

### 2. メンバー名簿を置く

[application/roster.example.json](application/roster.example.json) を写して `~/Library/Application Support/meeting-setup-automation/roster.json` を作る。**氏名とメールアドレスの対応表は個人情報なので、リポジトリには置かない**(`.gitignore` で守る形にすると書き忘れ1つでコミットされるため、リポジトリの外に置く)。

- `members`: 参加者として指定できる人。`name` は依頼時にチャットで使う表記そのもの。**同じ名前が2人いると解決できない**(黙ってどちらかを選ばない)ので、区別できる表記にする
- `organizer`(任意): 自分。候補が0件のときの代替案1で、自分に仮の予定があることを名前つきで示すために使う。無くても動く(その場合は「開催者(あなた)」と示す)

### 3. ビューアURLの設定値を置く

候補選択画面はOneDrive上のHTMLをブラウザのファイルビューアで開く(ファイルの直リンクはダウンロードになる)。[application/settings.example.json](application/settings.example.json) を写して `~/Library/Application Support/meeting-setup-automation/settings.json` を作る。

値の取り方:

1. ブラウザで OneDrive を開き、`00_root/auto/meetingSetting/html` フォルダまで進む
2. アドレスバーのURLのうち `?` より前が `output_web_viewer`(`https://<テナント>-my.sharepoint.com/personal/<ユーザー>/_layouts/15/onedrive.aspx`)
3. `?id=` の値をデコードしたもの(`/personal/<ユーザー>/Documents/00_root/auto/meetingSetting/html`)が `output_web_dir`。エンコードされたままでも動く(Skill側で一度デコードしてからエンコードする)

設定が無くても機能は動き、通知にはURLの代わりにローカルのファイルパスが載る。

### 4. Power Automateフローを作る

[application/power-automate/README.md](application/power-automate/README.md) に従って、探索フロー・作成フロー・会議設定通知フローの4本を作る。台帳ファイルの形・アクションの入力・つまずく点はそこに書いてある。

### 5. Teams通知の投稿先を登録する

`~/.claude/config/project-profiles.json` の最上位 `user.teams.destinations` に「会議設定通知」を登録する(`folder_path` は `.../00_root/auto/teamsNotice/meetingSetting`、`channel_type` は `private`)。登録後、`teams-post` の一覧に出ることを確認し、テスト投稿してTeams側に表示されることを目視で確認する。

## 使い方(サブコマンド)

チャットからはSkill(`~/.claude/skills/meeting-setup/SKILL.md`)が呼ぶ。手で動かすときは `application/` で実行する。

| サブコマンド | 役割 |
|---|---|
| `main.py submit --subject <件名> --attendee <名前> ... --duration <分> [--agenda <原文>] [--start-date --end-date --time-start --time-end --max-results --weekdays --allow-partial] [--dry-run]` | 名前の解決・受け付け条件の検証・依頼の書き出し。`--dry-run` で書き出さずに内容だけ返す |
| `main.py resume <依頼ID>` | 台帳の状態から続きを進める(候補の待ち・絞り込み・代替案・選択画面と通知・作成結果の待ち・完了の通知)。打ち切った後の再開も同じ |
| `main.py select "<選択画面でコピーした1行>"` | 候補ファイルと突き合わせて選択結果を書き出し、作成結果を待って完了を通知する |
| `main.py retry-create <依頼ID>` | 失敗した会議の作成を同じ枠でやり直す(失敗した作成結果が無ければ何もしない) |

進捗と結果は標準出力に出る(チャットへそのまま貼れる)。ログは標準エラーと `~/Library/Application Support/meeting-setup-automation/meeting-setup.log`(5世代ローテーション)に出る。ログにはメールアドレス・アジェンダ・参加URL・会議本文・他人の予定の件名を出さない。

## 候補が0件のときの代替案

既定の条件(当日から2週間・9:30〜17:30・月〜金・全員空き)で候補が0件のとき、確認を挟まず2つの代替案を調べて1枚の選択画面にまとめる。

- **代替案1(仮の予定を含める)**: 同じ候補ファイルを、仮の予定が入っている参加者を空いているものとみなして絞り直す(探索の依頼は出し直さない)。枠ごとに、仮の予定を持つ参加者(開催者自身を含む)を添える
- **代替案2(期間と時間帯を広げる)**: 期間を当日から3週間、時間帯を9:30〜18:30に広げた依頼を出し直す。依頼時に期間・時間帯を明示的に指定していた項目は広げない。両方指定されていれば代替案2は作らない

**予定の件名は扱わない。** 代替案1で示すのは「誰に仮の予定があるか」までで、その人に重ねてよいかは直接確認して判断する(理由は[requirements.md#スコープ外](specs/meeting-scheduling/requirements.md#スコープ外))。

代替案の依頼は既定の依頼の直後に続くため、フォルダ監視トリガーの検知間隔が絞られて往復が伸び、待ち上限(5分)で打ち切られることがある。打ち切られても台帳は残るので、`resume <依頼ID>` で続きから再開できる。

## 障害時にどのフォルダを見るか

| 症状 | 見る場所 |
|---|---|
| 候補が届かず打ち切られる | `meetingSetting/request/` に依頼があり `candidates/` に無い → 探索フローの実行履歴。OneDrive同期が止まっていないかも確認 |
| 候補が届くが失敗理由が入っている | `candidates/candidates-<依頼ID>-a1.json` の `error` と探索フローの実行履歴 |
| 会議が作られない | `selection/` に選択結果があり `result/` に無い → 作成フローの実行履歴 |
| 作成結果に失敗理由が入っている | `result/result-<依頼ID>.json` の `error`。**再試行の前にTeamsのカレンダーでその枠に会議が既に無いか確かめる**(作成後の処理で失敗した場合は会議だけが残っている) |
| Teamsに通知が来ない | `teamsNotice/meetingSetting/` にファイルが残っている → 会議設定通知フローがオフか監視先違い。消えている → 投稿先チャネルの指定 |
| 選択画面のURLが開けない | 同期の完了を数十秒待って再読込。`settings.json` のビューア設定 |

## 録画とファシリテーターは手動で有効化する

録画の自動開始とファシリテーター機能の有効化は自動化できない。これらはMicrosoft Graphのオンライン会議リソースにしか存在せず、このアプリが使える接続(Office 365 Outlookコネクタ)の権限では到達できないため(調査の内容と再検討の条件は [specs/adr/0001-manual-recording-and-facilitator.md](specs/adr/0001-manual-recording-and-facilitator.md))。会議テンプレートも自動作成した会議には適用されない。

手順: 作成完了の通知(Teamsとチャット)に含まれる**会議オプション画面の直リンク**を開き、「レコーディングを自動的に開始する」と「ファシリテーター」をオンにして保存する。直リンクが取り出せなかった場合は、Teamsのカレンダーで会議を開き「会議のオプション」から同じ設定を行う。トグルは保存後も維持される(実機確認E4)。
