---
name: pr
description: 実装PRを作成するときに使う。テンプレート、作成前チェック(impl-pr-reviewer・CI)、仕様承認PR方式のプロジェクト向けの仕様承認PRを扱う。仕様の承認は既定ではチャット上の明示的な承認(詳細は/devflow:spec-review参照)。プロジェクトが独自の`.claude/skills/pr/SKILL.md`を持つ場合はそちらを優先する。
---

> ワークフロー上の位置: [/devflow:implementation-review](../implementation-review/SKILL.md) → **/devflow:pr(本Skill・実装PR)** → ユーザーがGitHub UIでマージ → 本番反映確認・ブランチ掃除(手動)。仕様承認PR方式のプロジェクトでは、[/devflow:spec-review](../spec-review/SKILL.md) → **本Skill(仕様承認PR)** → 承認後 [/devflow:implementation](../implementation/SKILL.md) の経路もここで扱う。全体フロー・モデル対応表は[dev-flow.md](../../dev-flow.md)を参照

# 前提条件

- **実装PR**: [/devflow:implementation-review](../implementation-review/SKILL.md)で指摘なし(🟢のみ)の結果を得ていること。レビュー未実施なら/devflow:implementation-reviewから始める
- **仕様承認PR**(仕様承認PR方式のプロジェクトのみ): [/devflow:spec-review](../spec-review/SKILL.md)で指摘なし(🟢のみ)の結果を得ていること

# 共通ルール

- 作業は必ず`feature/<機能名>`(JIRAチケットがある場合は`feature/<JIRAキー>-<機能名>`)ブランチで行い、mainに直接pushしない(マージ後の後続作業も同様に新しいブランチを切る)。複数の作業を並行して進める場合は[parallel-work](../parallel-work/SKILL.md)(worktree)を使い、ブランチの切り替えはしない
- ブランチの作成・コミットはローカルのgit操作のみで完結するため、ユーザーへの確認なしで進めてよい
- **`gh`コマンドには常に`-R <owner>/<repo>`を明示する**(`gh repo set-default`が未設定/環境ごとにリセットされる場合があり、"No default remote repository has been set"で失敗することがあるため)。`<owner>/<repo>`は`git remote get-url origin`から取得できるURL(例: `https://github.com/<owner>/<repo>`)の該当部分を使う。`gh pr create`・`gh pr checks`・`gh pr view`・`gh pr merge`など、対象リポジトリを扱うすべての`gh`呼び出しに付ける
- **`-R`を付けた既存PRを扱うサブコマンドには、PRの指定(ブランチ名/PR番号/URL)も必ず添える。** `-R`併用時はローカルのカレントブランチからの自動解決が効かなくなり、`argument required when using the --repo flag`で失敗する。`gh pr merge`・`gh pr checks`・`gh pr view`・`gh pr close`等が該当する(`gh pr create`は`--head`があるため対象外)
  - **`feature/<機能名>`(ブランチ名)をそのまま渡すのが既定の解決策。** PR番号は作成するまで分からないが、ブランチ名は事前に分かっているため、PR作成〜マージを1つのコマンドブロックに連結する場合でも使える:
    ```bash
    gh pr merge -R <owner>/<repo> feature/<機能名> --squash --delete-branch
    ```
  - PR番号を使うのは、PR作成後にユーザーから番号の報告を受けている場合に限る
- **push・PR作成・CI確認・マージはこのサンドボックスから実行できない**(GitHubへの通信が遮断されており、`gh`は認証情報も読めない。詳細は`~/.claude/sandbox-limitations.md`)。**試さずに**、以下の手順でユーザーに引き継ぐ。引き継ぎブロックは**手元ターミナル向けのコマンドブロック**を既定にする(形式・添える説明は`~/.claude/handoff-commands.md`の「GitHub操作の引き継ぎ」節が正。ブロックの中は実行コマンドだけにし、説明はブロックの外に書く):
  1. コミットまで済ませ、`push`→PR作成→CI確認を1つの依頼文ブロックにまとめて提示する(本文テンプレートは下記)。**コマンド部分は必ず先頭に対象リポジトリの絶対パスへの`cd`を入れる**(Copilot・ターミナルのどちらで実行されてもカレントディレクトリがこちらの作業ディレクトリと一致している保証はなく、別リポジトリで実行されると`src refspec ... does not match any`・`No commits between ...`で失敗するため)。この`cd`はマージ・ブランチ掃除など後続のブロックにも毎回付ける。**指示文はコードブロックの外に書き、ブロックの中は実行コマンドだけにする**(ブロックをターミナルへ貼ったときに指示文の行が`command not found`になるため):
     ```
     cd <リポジトリの絶対パス>

     git push -u origin feature/<機能名>

     gh pr create -R <owner>/<repo> --title "<タイトル>" --body "$(cat <<'EOF'
     <本文>
     EOF
     )"

     gh pr checks -R <owner>/<repo> feature/<機能名>
     ```
     `gh pr checks`にブランチ名を添えているのは、共通ルールの「`-R`併用時はPRの指定が必須」に従うため。
     **実装PRの場合は、この雛形に[Copilotレビュアーの指定(agent-routing)](#copilotレビュアーの指定agent-routing)の2行(`cd`の直後の`gh auth status`と、`gh pr create`直後のレビュアー指定)を足す。**仕様承認PRには足さない。
     `gh`が使えない場合は、pushすると表示されるcompare URL、またはGitHub Web UIからPRを作成してもらう
  2. 実行結果(PRのURL・CI結果)をユーザーから報告してもらう(Copilotの出力をそのまま貼り戻してもらえばよい)
  3. 報告を受けたら、PRのURLを装飾なしの単独行で明示したうえで「マージ前に確認しますか?」と一言だけ確認する
  4. ユーザーの返答で分岐する:
     - 「確認不要です」等、確認不要の意思表示があれば、その場でマージ〜ブランチ掃除の依頼文ブロックをまとめて提示する(指示文はブロックの外):
       ```
       cd <リポジトリの絶対パス>

       gh pr merge -R <owner>/<repo> feature/<機能名> --merge --delete-branch
       ```
       (マージ方式(`--merge`/`--squash`/`--rebase`)は対象リポジトリの既存履歴に合わせる。`--delete-branch`によりローカル・リモート双方の作業ブランチが自動削除され`main`に切り替わる。PRの指定にPR番号ではなくブランチ名を使う理由は共通ルールを参照)
     - 「確認します」等の返答であれば一旦待ち、後で「マージしました」等の報告を受けてから、ローカルの同期確認(`git status`・`git log`、必要なら`git pull`)と次のステップの案内に進む
- ユーザーへの報告にはPR番号だけでなく完全なURLを明記する。URLは装飾なしの単独行に置く(`**`や括弧・日本語をURLに連結するとリンク検出が巻き込んで開けなくなる)
- mainへのマージはユーザーがGitHub UI上でdiffを確認するか、上記の確認フローを経て行う想定であり、こちらから無条件に直接マージは実行しない

# 仕様承認PR(仕様承認PR方式のプロジェクトのみ)

specをリポジトリにコミットする例外リポジトリのうち、承認方式が仕様承認PRと指定されているプロジェクト(`~/.claude/config/project-profiles.json`の`github.repos`でカレントリポジトリの絶対パスに一致するエントリが`approval: "pr"`を持つもの。例: study。この判定はPJの解決(依頼文でのPJ名指定・デフォルトPJ)を経由せず、カレントリポジトリの絶対パスだけで行う例外。詳細は[project-profile](~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/project-profile/design.md#開発フローskillの例外リポジトリパスでの解決)・[dev-flow.md](../../dev-flow.md#specの置き場所ローカル専用リポジトリにコミットしない))では、3点セット(requirements.md/design.md/tasks.md)と、作成した場合は画面モック mock.html・appendix.md を含めてPRを出し、ユーザーの確認・承認(マージ)を得るまでコード(テストを含む)は書き始めない。

この段階ではrequirements.mdのタイトル直下に`ステータス: 仕様確認中(未実装) ／ 優先度: …`のラベル1行を入れる(引用`>`にはしない)。これは「テスト不要」という恒久的な判断ではなく、「まだ実装していないだけ」という一時的な状態を表す。実装(🔴Redのテスト)に着手したら「実装中」に書き換える。

**承認状態のフロントマター**(値の遷移の正は[dev-flow.mdの「承認状態のフロントマター」](../../dev-flow.md#承認状態のフロントマター)):

- PRに載せる3点セットのフロントマターは `status: in-review` にする(承認後の改訂なら、直したファイルだけが `in-review` で version は上げたまま。直していないファイルは `approved` のまま)。`approved` のままPRに出さない
- ユーザーの承認(GitHubのApprove、または「承認します」の明示)を確認したら、**マージの前に**同じPRへ「`in-review` のファイルを `status: approved` にし、`approved_date` に承認日を足す。version が `0.x` なら `"1.0"` にする」1コミットを足し、そのコミットごとマージする。マージ後の main で仕様書が `in-review` のまま残らないようにするため。コミットのメッセージは `docs(spec): <spec名> の仕様承認をフロントマターに記録する` の形にする
- 承認前に修正依頼が出たら、直すファイルを `draft` に戻して直し、出し直す時点で `in-review` に戻す

本文テンプレート:

```markdown
## 概要
(何のための機能か1〜2行)

## 作成・更新したspec
- (specのリポジトリ内パス。requirements.md / design.md / tasks.md / appendix.md / mock.html。mock.html があればプレビューのArtifactのURLも添える)

## 判断に迷った点・レビューしてほしい点
- (仕様の分かれ道になった判断と、その根拠)

## 次のステップ
承認・マージ後、/devflow:implementation でTDD実装に着手します(承認までコードは書きません)。
```

# 実装PR

PR作成前にimpl-pr-reviewerエージェント(Agentツールの`subagent_type`は`devflow:impl-pr-reviewer`。定義は`${CLAUDE_PLUGIN_ROOT}/agents/impl-pr-reviewer.md`)でチェックし、❌を解消してから作成する(承認フロントマター・ステータスのラベルの値の書き換え漏れ・CIの横断チェック)。仕様とテストの対応確認は[/devflow:implementation-review](../implementation-review/SKILL.md)のcode-reviewerが既に行っているため、ここでは繰り返さない([dev-flow.md](../../dev-flow.md#仕様とテストの対応確認は-code-reviewer-に一本化)参照)。

## Copilotレビュアーの指定(agent-routing)

`~/.claude/config/agent-routing.json`があり、対象リポジトリがリモートを持つ場合、実装PRのコマンドブロックに次を含める。設定が無ければ不要。リモートを持たないローカルgitリポジトリ(`~/.claude`等)では、そもそもPR工程が存在しないため発生しない。

1. ブロックの`cd`の直後に`gh auth status`を置き、「レビュー用アカウントで認証されていなければそこで止めて報告してほしい」旨をブロックの外の文章に書く(`gh`の認証アカウントがレビュー用アカウントでないと、意図しない側のクレジットが消費されるか失敗するため)
2. PR作成の直後に、Copilotをレビュアーに指定する1行を加える。**ログイン名には`@`を必ず付ける**:
   ```bash
   gh pr edit -R <owner>/<repo> <PR番号> --add-reviewer @copilot
   ```
   - `@`を落とした`--add-reviewer copilot`は、ただのユーザー名として解決されて`Could not resolve user with login 'copilot'`で失敗する
   - この構文には**gh v2.88.0以降**が必要
   - `gh api -X POST repos/<owner>/<repo>/pulls/<PR番号>/requested_reviewers -f "reviewers[]=copilot-pull-request-reviewer[bot]"`は使わない。エラーも出ないまま何も起きない
3. **成否を`requested_reviewers`で判定しない。**指定が成功していてもこの配列は`{"users":[],"teams":[]}`のままで、Copilotはここに現れない。確認が要るときはタイムラインのイベントを見る:
   ```bash
   gh api repos/<owner>/<repo>/issues/<PR番号>/timeline --jq '.[] | select(.event=="review_requested") | {actor: .actor.login, requested: .requested_reviewer.login}' | cat
   ```
   `{"actor":"<レビュー用アカウント>","requested":"Copilot"}`が出ていればリクエストは通っている
4. レビュアー指定は**残量によらず常に付ける**。レビュー用アカウントの残量はキャッシュに持たず、判定も行わない(PRレビューはdiffを読む単発処理で委任より大幅に軽く、Copilot CLIは委任用アカウントにログインしたまま維持されるため同じ経路でレビュー用アカウントの残量を読めない)
5. **仕様承認PRのコマンドブロックにはこの行を加えない**(仕様承認PRはClaudeレビューのみ)

利用条件(公式ドキュメント): 個人アカウントが所有するリポジトリでは、レビュー用アカウントのプランが**Copilot Pro / Pro+ / Max**のいずれかであること(Copilot Freeは対象外)。組織所有のリポジトリでは、組織のCopilotポリシーで「Copilot code review」が有効であること。レビュー1回ごとにAIクレジットを消費する(Lite相当で$0.05〜$1、Balanced相当で$0.25〜$5)。`dnode-ryosuke-yamazaki/study`(個人アカウント所有)では2026-09-11に実動作を確認済み。

## Copilotのレビュー結果の取り込み

レビュアーに指定しただけでは指摘が誰にも読まれない。**CIの確認とマージの間に、Copilotのレビューを読んで採否を判断する工程を必ず挟む**。

1. **レビューは即座には返らない。**指定を受けてGitHub Actions上で`Running Copilot Code Review`というrunが走り、完了して初めてレビューが載る(指定から3分後もまだ`in_progress`だった実測あり)。`gh pr checks --watch`が抜けたタイミングで出揃っているとは限らないため、runの完了を確かめてから取り出す。CI確認のコマンドブロックに次の3行を足す:
   ```bash
   gh run list -R <owner>/<repo> --limit 5 --json name,status,conclusion,createdAt | cat
   gh pr view -R <owner>/<repo> <ブランチ名> --json reviews --jq '.reviews[] | {author: .author.login, state: .state, body: .body}' | cat
   gh api repos/<owner>/<repo>/pulls/<PR番号>/comments --jq '.[] | {path: .path, line: .line, body: .body}' | cat
   ```
   1行目で`Running Copilot Code Review`が`completed`になっているかを見る。`in_progress`のままなら、数分置いて同じブロックをもう一度実行してもらう。2行目がレビュー全体の所見(著者は`copilot-pull-request-reviewer`、stateは`COMMENTED`。総評・ファイル単位のサマリ表・抑制されたコメントが`<details>`入りの長文で入る)、3行目が行単位の指摘。**3行とも出す**(行単位のコメントに最も具体的な指摘が入るため、`--json reviews`だけでは判断材料が足りない)
2. 貼り戻された指摘を、Claudeが1件ずつ**採否判断**する。この時点でcode-reviewerによるレビューは通過済みなので、Copilotの指摘は「別の目による追加の観点」として扱い、鵜呑みにしない。判断の区分は[/devflow:resolve](../resolve/SKILL.md)と同じ**✅修正 / 💬回答 / ⏭見送り**
3. 採用した指摘は[/devflow:resolve](../resolve/SKILL.md)で直し、テストを通してから追加コミットをpushする(PRは開いたまま)。見送った指摘は理由を添えてチャットでユーザーに報告する。**PR上でCopilotに返信はしない**(往復させても判断材料が増えないため)
4. 採否の一覧(何件出て、何件直し、何件見送ったか)を完了報告に含める

## 本文の組み立て

- **リポジトリに`.github/PULL_REQUEST_TEMPLATE.md`がある場合はそちらを優先する。** そのテンプレートの見出し・チェック項目の様式に従って本文を書き、下記の手元テンプレートは、リポジトリ側に無い節(関連spec・AIが生成・変更した範囲 など)を補う目的でだけ使う。リポジトリ側テンプレートのチェック項目は空欄で残さず、根拠を示せるものだけチェックする(「人が記入する」と明示された欄はAIが代わりに記入しない)
- 無い場合は下記の手元テンプレートをそのまま使う
- どちらの場合も「AIが生成・変更した範囲」と「人が検証した範囲と方法」は省略しない(AI起因の変更を後から説明できるようにするため)

本文テンプレート:

```markdown
## 概要
(何を実装・修正したか1〜2行)

## 関連spec
- (specのパス。ローカルミラーなら絶対パス、リポジトリにコミットする例外リポジトリならリポジトリ内パス)
- (仕様の承認: 「チャット上でユーザーの承認済み(YYYY-MM-DD)」または「仕様承認PR #NN でマージ済み」)

## 変更内容
- (主な変更点の箇条書き)

## テスト
- (該当プロジェクトのテストコマンド): ✅ n件パス
- 否定確認: (壊してRedを確かめた項目。例: 生成HTMLのscript構文・候補0件の分岐)
- 静的検査: ruff / bandit / pip-audit の結果(未導入の道具は「未導入」と書く)
- 変異テスト(試行中の場合のみ): 変更ファイルでの生存数と、生き残った変異が意図的かの説明
- 性能テスト(宣言している場合のみ): tests/perf/ の結果

## 動作確認
- (実際に確認した内容。design.mdの「テスト戦略」で環境スモークを宣言した項目がある場合は、tasks.md末尾の確認チェックリスト3項目の結果を転記する。無人実行・定期実行するもので未了の項目があれば、未了であることと外れたときの影響を書く)

## AIが生成・変更した範囲
- (Claude Codeが生成・変更したファイル・機能の範囲。変更の全部なら「本PRの変更はすべてClaude Codeが生成(仕様はユーザーが承認済み)」と書き、人が手で直した箇所があればそれを分けて書く)

## 人が検証した範囲と方法
- (ユーザー自身が確かめた範囲と方法。例: 手元ターミナルでの起動確認、画面の目視、CIの結果確認。この時点で未検証なら「未検証(マージ前にレビューで確認)」と明記し、AIの確認結果を人の検証として書かない)
```

# 完了時の次ステップ案内

- 仕様承認PR → 作成されたPRのURLを確認し、ユーザーの承認・マージ後に[/devflow:implementation](../implementation/SKILL.md)へ進むことを案内する。**次セッションへの/devflow:implementation引き継ぎプロンプトを用意する前に、対象tasks.mdの先頭に`> 実装中: session ...`マーカーが既に付いていないか確認する**(他セッションが同じspecへ実装着手済みの可能性があるため)。マーカーがあれば、そのまま次セッションへ引き継がず、まずユーザーに状況を確認する
- 実装PR → 作成されたPRのURLを確認し、ユーザーのマージ後に本番反映の確認([dev-flow.mdの「マージ後のリリース確認チェックリスト」](../../dev-flow.md#マージ後のリリース確認チェックリスト)に従う)と、不要になったブランチ・worktreeの掃除(`git worktree remove`・`git branch -d`)を行うことを案内する
- 本番反映の確認まで済んだら、対象specの requirements.md のステータスのラベルの値を「リリース済み」に書き換える(行ごと消さず、優先度も残す。例: `ステータス: リリース済み ／ 優先度: 高`)。ラベルの3つの値と書き換えるタイミングの正は[区分け表のファイル](../../quality-standards/base/spec-layout.md)
- あわせて、対象プロジェクト/アプリが`architecture.md`を持つ場合は機能マップの状態列を「リリース済み」に更新し、**更新後の表をこの完了報告にそのまま貼って提示する**([architecture-workflow](../architecture-workflow/SKILL.md)の「更新タイミング」参照)。requirements.md のラベルと機能マップの状態列は同じ3段階なので、片方だけを直さない
