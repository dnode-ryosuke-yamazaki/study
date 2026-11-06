# 開発フローSkillの回帰テスト(evals)

devflow プラグイン(`claude-plugins/plugins/devflow/skills/`)の開発フローSkillのうち `requirement` / `design` / `spec-review` の3本について、「この入力を渡したら、この形の成果物が返る」ことを promptfoo で採点する。**検査対象は手順書(SKILL.md)そのもの**で、製品コード(Lambda・SDK・バッチ)のテストではない。Skill本文を改修したあとに、成果物の質が落ちていないかを確かめるために回す。

構成は社内標準テンプレート(`add-skeleton/evals/`)の方式を踏襲している(provider・非対話化のシステムプロンプト・fixtureの使い捨て配置)。

## 実施方法(手元のターミナル)

サンドボックス内の Claude Code からは `npm install` も API 通信も通らないため、手元のターミナルで実行する。

```bash
cd /Users/ryosyamazaki/repo/study/claude-plugins/plugins/devflow/evals
npm install                      # 初回のみ(promptfoo を node_modules/ に入れる)
npm run eval -- requirement      # 1カテゴリだけ
npm run eval:all                 # 3カテゴリ順に
cat logs/requirement.promptfoo.log.yaml   # 結果(pass/fail と reason)
```

## 実行条件

- Claude Code にログイン済みであること(`ANTHROPIC_API_KEY` は不要。provider は `apiKeyRequired: false` でローカルのログインを使う)
- 検証対象は各Skillの**最終応答テキストのみ**。`disallowed_tools` で Write / Edit / Bash を無効化しており、実ファイルの書き込みは起きない
- 既存specが前提のケースは `libs/extensions/stage-fixtures.mjs` が `.tmp/<category>-<case>/` に使い捨ての作業ディレクトリ(空のgitリポジトリ)を作り、fixture を配置する。実行後に自動削除する
- Skillは `plugins:`(`type: local`・`path: ..` = devflow プラグインのルート)から読み、`skills:` で対象1本(`devflow:<名前>`)に絞る。`setting_sources: ['user']` により `~/.claude/CLAUDE.md` の全体ルールも同時に読まれる(実運用と同じ条件)。プラグイン配置での再実行は未実施のため、初回は出力に SKILL.md 本文にしかない文言(「JIRAチケット確認」「次のステップ案内」)が現れることで読み込みを確かめる
- 1ケースの実行は Claude の利用枠を消費する(`max_turns: 20`)。頻繫に回すものではなく、Skill本文を変更したときに回す。目安(初回実測 2026-09-11、モデルはセッション既定のOpus): `requirement` 約53秒・約3.1万トークン(生成1.8万+採点1.3万)、`design` 約3分13秒・約10.3万トークン(生成7.6万+採点2.7万)、`spec-review` 約1分51秒。3カテゴリとも初回で全合格
- `skills:` に挙げたSkillの本文は、Skillツールを呼ばなくても最初から読み込まれている(初回実測で `toolCalls: []` のまま、SKILL.md本文にしかない「JIRAチケット確認」「次のステップ案内」の文言が出力に現れた)。つまり検査対象は確かにSKILL.md本文

## 判定基準

`logs/<category>.promptfoo.log.yaml` の各テストの pass/fail と reason を見る。

- `contains-all` / `regex` / `not-icontains-any`: 見出し・番号・禁止語の有無(機械的判定)
- `llm-rubric`: 内容の質(会話に無い方針を推測で書いていないか、全項目がテスト戦略に載っているか、仕込んだ欠陥をレビューが検出したか)
- fail したら reason を読み、Skill側の変更による劣化か、テストケース側の期待値・fixtureのずれかを切り分ける
- **他の Claude Code セッションが開いている間に回すと偽陽性の FAIL になることがある。** 評価中のセッションも手元の「ローカルセッション」として見えるため、別セッションがセッション間メッセージ(他セッションへの確認・依頼)を送ると、評価中のセッションがそれへの返答を最終応答にしてしまい、成果物が採点対象から消える(2026-11-05 の `design` で実測。出力が別セッション study-35 への「返信不要」の説明だけになり、採点者が「design.md / tasks.md の内容が一切含まれていない」と判定した)。reason がこの形なら Skill の劣化ではないので、他セッションを閉じるか送信が落ち着いてから同じカテゴリだけ再実行する
- `npm run eval:all` は最初に fail したカテゴリで止まる(`|| exit 1`)。3本の結果をまとめて見たいときは `npm run eval -- <category>` を3回に分けて回す

## テストの追加

- 新しいカテゴリは `<category>.promptfooconfig.yaml` を足す(`package.json` の変更は不要。`eval:all` に加える場合だけ編集)
- 既存ファイルが前提のケースは `vars.workDir` / `vars.stage` で fixture を配置する(`fixtures/<category>/` に Markdown を追加)
- アサーションは promptfoo 標準のもの([公式](https://www.promptfoo.dev/docs/configuration/expected-outputs/))だけで書く。禁止語の検査は出力全体に当てず、見出しの範囲で許される内容(tasks.md の実装詳細・テスト戦略の備考のライブラリ名など)を巻き込まないよう、必要なら標準の `javascript` 型で対象の見出し区間だけを切り出して判定する(`design` の「処理フローに実装識別子が混ざっていない」が例)
