---
name: autopilot
description: 新機能(/devflow:requirement起点)または小規模なバグ修正・既存機能改修(/devflow:fix起点)の工程を確認なしで連結し、実装PRの提示まで完走する自動運転モード。新機能起点は要件ヒアリングと仕様承認PRレビューの2箇所、fix起点は仕様変更を伴う場合のみその2箇所で対話する(伴わない場合は対話なし)。小規模・低リスクの変更だけが対象で、ユーザーが明示起動する。「autopilotで」「自動で最後まで」のような自然文の指示でも起動対象になる。/devflow:design・/devflow:implementation など途中の工程からの起動も可能(起動前監査でリスクを明示してから自走する)。「ノンストップで」「nonstopモードで」のように明示指定すると、仕様承認PRのレビュー・承認も自動化し要件ヒアリング(またはfixの入口確認)以外は一切対話しない「ノンストップモード」になる(主にnight-batch経由の夜間無人実行での利用を想定)。
---

> ワークフロー上の位置: [/devflow:requirement](${CLAUDE_PLUGIN_ROOT}/skills/requirement/SKILL.md)または[/devflow:fix](${CLAUDE_PLUGIN_ROOT}/skills/fix/SKILL.md)で始まる開発フロー全体を貫く**モードSkill**。各工程の手順はすべて既存の工程Skill([/devflow:requirement](${CLAUDE_PLUGIN_ROOT}/skills/requirement/SKILL.md)・[/devflow:design](${CLAUDE_PLUGIN_ROOT}/skills/design/SKILL.md)・[/devflow:spec-review](${CLAUDE_PLUGIN_ROOT}/skills/spec-review/SKILL.md)・[/devflow:pr](${CLAUDE_PLUGIN_ROOT}/skills/pr/SKILL.md)・[/devflow:implementation](${CLAUDE_PLUGIN_ROOT}/skills/implementation/SKILL.md)・[/devflow:implementation-review](${CLAUDE_PLUGIN_ROOT}/skills/implementation-review/SKILL.md)・[/devflow:resolve](${CLAUDE_PLUGIN_ROOT}/skills/resolve/SKILL.md)・[/devflow:fix](${CLAUDE_PLUGIN_ROOT}/skills/fix/SKILL.md))に従い、本Skillは「どこで止まり、どこを自走するか」だけを定める(手順の二重メンテをしない)

# この環境での前提

- **push・PR作成・CI確認・マージは自走の対象外。** このサンドボックスからGitHubへの通信は遮断されている(`~/.claude/sandbox-limitations.md`)。加えてGitHub Appによるクラウド経由でのGitHub操作は組織ポリシーにより利用できないため、night-batch経由のクラウドroutines実行であってもこの制約は変わらない。実行環境(ローカルサンドボックス・クラウドroutines)によらず、該当箇所ではコマンド一式をまとめて提示し、ユーザーの実行結果の報告を待つ(下記「引き継ぎポイント」)。提示の形式は**手元ターミナル向けのコマンドブロック**が既定(`~/.claude/handoff-commands.md`の「GitHub操作の引き継ぎ」節が正)
- **委譲先のAgentは既存の4つ**(spec-reviewer / code-reviewer / implementer / impl-pr-reviewer。Agentツールの`subagent_type`は`devflow:<名前>`)。designer・resolver・release-checker相当のAgentが無いため、**設計([/devflow:design](${CLAUDE_PLUGIN_ROOT}/skills/design/SKILL.md))とレビュー指摘対応([/devflow:resolve](${CLAUDE_PLUGIN_ROOT}/skills/resolve/SKILL.md))はメインスレッドが自分で行う**
- **リリース確認工程(release-check)は無い。** 実装PRのマージ後は[/devflow:pr](${CLAUDE_PLUGIN_ROOT}/skills/pr/SKILL.md)の完了時案内(本番反映の確認・ブランチ/worktreeの掃除)で終える

# 前提条件

- **小規模・低リスクの変更にだけ使う。** 課金・請求に関わる計算、個人情報の扱いが変わる変更、本番インフラ(Terraform)の破壊的変更、影響範囲の読めない変更には使わない(通常フローで工程ごとに確認する)。対象として適切か迷ったら、自走を始める前にユーザーに確認する
- **対象範囲**: 新機能([/devflow:requirement](${CLAUDE_PLUGIN_ROOT}/skills/requirement/SKILL.md)起点)、または小規模なバグ修正・既存機能改修([/devflow:fix](${CLAUDE_PLUGIN_ROOT}/skills/fix/SKILL.md)起点)。[/devflow:fix](${CLAUDE_PLUGIN_ROOT}/skills/fix/SKILL.md)のStep1で「新規spec作成が必要」と判定された場合は、以降「フロー(新機能起点)」に合流する
- **JIRAチケットの確認は省略しない。** 起点の工程Skill(/devflow:requirement・/devflow:fix)が定めるJIRAチケット確認(`${CLAUDE_PLUGIN_ROOT}/jira-ticket-check.md`)は対話①の中で通常どおり行う
- **推奨モデル: Sonnet。** メインスレッドのモデルはフロー途中で自動では切り替えられず、既存Skillの「次フェーズのモデル」運用(工程ごとに人が切り替える)がこのモードでは使えない。対象が小規模である前提なので、発動時(遅くとも自動運転宣言の時点)に`/model`でSonnetへ切り替えることを案内する

# 対話ポイントと引き継ぎポイント

自走を止める箇所は2種類ある。混同しないよう区別して扱う。

**対話ポイント(判断を仰ぐ・ユーザーの承認が要る)**

1. [/devflow:requirement](${CLAUDE_PLUGIN_ROOT}/skills/requirement/SKILL.md)の要件ヒアリング、または[/devflow:fix](${CLAUDE_PLUGIN_ROOT}/skills/fix/SKILL.md)の入口確認(設計の分かれ道になる事項の確認もここに含める。下記「ヒアリングの範囲」)
2. 仕様承認PRでの一括レビューと承認(複数回のやりとり可)

fix起点で仕様変更・スコープ判断のいずれも伴わない純粋なバグ・軽微な変更は、**対話なしで完走することがある**。

「ノンストップモード」(下記)を明示指定した場合は、対話ポイント②も自動承認となり対話ポイントは①のみになる。

**引き継ぎポイント(環境制約。判断ではなく実行の代行を頼む)**

- `git push` / PR作成 / CI結果の確認 / マージ / マージ後の`git pull`
- 該当箇所では[/devflow:pr](${CLAUDE_PLUGIN_ROOT}/skills/pr/SKILL.md)の共通ルールに従い、コピペ可能なコマンドブロック1つにまとめて提示し、実行結果(PRのURL・CI結果)の報告を待つ。**待っている間は「完了」と報告しない**(セッションを閉じてよいとも書かない)
- 報告を受けたら、そこから先の工程は再び自走する
- 「ノンストップモード」(下記)では、推測マーカーの扱いが変わり、単一タスク前提での引き継ぎポイントの扱いが明確になる(下記「ノンストップモード」節参照)

# 任意の工程からの起動(途中からの自走)

[/devflow:requirement](${CLAUDE_PLUGIN_ROOT}/skills/requirement/SKILL.md)・[/devflow:fix](${CLAUDE_PLUGIN_ROOT}/skills/fix/SKILL.md)からの起動(下記「フロー」の最初から)が最も安全だが、それ以外の工程からも起動できる。「ここから自走して」のように、一部の工程が既に完了した状態で指示された場合がこれにあたる。

**起動前監査(必須)**: 起点より前のステップを飛ばして自走を始める前に、それらのステップが実際に満たされているかを、会話の記憶ではなく確認可能な証跡(gitコマンド・ファイル内容)で確認する。証跡で確認できない、または満たされていない項目があれば、**どの前提が欠けているためどんなリスクがあるかを具体的に列挙してから**、その項目だけユーザーに確認するか、通常ルール(このSkillの自動化を使わず都度人が確認する運用)にフォールバックする。「確認できないが恐らく大丈夫」で自走を始めない。

なお`gh pr list`・`git fetch`はこの環境では実行できないため、監査はローカルで完結する手段(`git log --all --oneline -- <パス>`・`git branch -a`・`git worktree list`・ファイルの内容確認)で行い、それで判断がつかない項目はユーザーに直接確認する。

| 起動する工程 | 確認する前提 | 満たされない場合のリスクと対応 |
|---|---|---|
| [/devflow:design](${CLAUDE_PLUGIN_ROOT}/skills/design/SKILL.md) | 対象specの要件ヒアリング4項目(誰の・何ができる・ビジネスルール根拠・スコープ外)が会話で確認済みか。requirements.mdの記述だけでは、それが実際の会話に基づくか判別できない場合がある | [/devflow:requirementの会話ドリブン原則](${CLAUDE_PLUGIN_ROOT}/skills/requirement/SKILL.md)に反したまま設計が進むリスク。確証が持てなければ4項目が埋まっているか確認し、埋まっていなければヒアリングからやり直す(対話①に合流) |
| [/devflow:spec-review](${CLAUDE_PLUGIN_ROOT}/skills/spec-review/SKILL.md) | 3点セットが揃っているか。design.mdの必須見出し・必須相当の図が埋まっているか | 未完成の仕様をレビューに掛け、指摘なしのまま承認PRへ進むリスク。欠けていれば先に[/devflow:design](${CLAUDE_PLUGIN_ROOT}/skills/design/SKILL.md)へ戻る |
| [/devflow:pr](${CLAUDE_PLUGIN_ROOT}/skills/pr/SKILL.md)(仕様承認PR) | spec-reviewが🟢のみで通っているか | 指摘未対応のままPRを出すリスク。通っていなければ先に[/devflow:resolve](${CLAUDE_PLUGIN_ROOT}/skills/resolve/SKILL.md)で対応する |
| [/devflow:implementation](${CLAUDE_PLUGIN_ROOT}/skills/implementation/SKILL.md) | 仕様承認PRがユーザーの明示的なOKでマージ済みか(ユーザーからのマージ報告、または`git log origin/main`での確認) | 未承認のままコードを書き始めるリスク。未マージなら例外停止し承認を待つ(通常の前提条件どおり) |
| [/devflow:implementation-review](${CLAUDE_PLUGIN_ROOT}/skills/implementation-review/SKILL.md) | 対象アプリのテストが通っているか(コマンドは`apps/<アプリ名>/README.md`のような対象プロジェクトのドキュメントで確認する) | 壊れた状態のままレビューに進むリスク。通っていなければ先に直す |
| [/devflow:pr](${CLAUDE_PLUGIN_ROOT}/skills/pr/SKILL.md)(実装PR) | [/devflow:implementation-review](${CLAUDE_PLUGIN_ROOT}/skills/implementation-review/SKILL.md)が🟢のみか、impl-pr-reviewerが❌なしか | 指摘を残したままPRを出すリスク。満たしていなければ先に[/devflow:resolve](${CLAUDE_PLUGIN_ROOT}/skills/resolve/SKILL.md)で対応する |

上記いずれの工程から始める場合も、起動前監査を通過した後は「フロー(新機能起点)」または「フロー(fix起点)」の該当ステップ番号以降をそのまま踏襲する(対話ポイント・引き継ぎポイント・例外停止の基準は変わらない。新しい判断基準を都度作らない)。途中工程から起動する場合も、起動指示にノンストップモードの明示があれば下記「ノンストップモード」節の分岐に従う。

# ノンストップモード

自然文の起動指示(ユーザーの依頼文、またはnight-batch経由で渡された自己完結プロンプトの指示文)に、autopilotの起動を示す語句(「autopilotで」「自動で最後まで」等)に加えて、ノンストップモードを明示する語句(例:「ノンストップで」「nonstopモードで」)が含まれる場合、以降「フロー(新機能起点)」「フロー(fix起点)」を通常モードではなく本節の分岐で実行する。含まれない場合は通常モードのまま、本節は参照しない(既存動作を変えない)。[/devflow:design](${CLAUDE_PLUGIN_ROOT}/skills/design/SKILL.md)・[/devflow:implementation](${CLAUDE_PLUGIN_ROOT}/skills/implementation/SKILL.md)など途中の工程から起動された場合も、起動指示にノンストップモードの明示があるかで同様に判定する(「任意の工程からの起動」の起動前監査の手順自体は変えない)。

対話ポイント①(要件ヒアリング、または/devflow:fixの入口確認)は通常のautopilotと同様に維持し、ここでのみユーザーとの対話が発生する。それ以外に、通常モードと動作が変わる点(対話ポイント②の自動承認、例外停止条件の自己解決、推測マーカーの扱い)と、動作は変わらないが明確化しておく点(引き継ぎポイントの単一タスク前提、完了報告への追記)を、以下の見出しで定める。

## 対話ポイント②の自動承認

「フロー(新機能起点)」ステップ4〜6、「フロー(fix起点)」ステップ3(仕様変更ありの分岐)における仕様承認PRのレビュー・承認は次のとおり自動化する。

1. 通常モードと同様に仕様承認PRの本文を用意し、push〜PR作成のコマンドブロックを提示してユーザーに実行を依頼する。PR本文の「判断に迷った点・レビューしてほしい点」に推測箇所の一覧を明記する点も変えない。
2. spec-reviewerエージェントによる仕様レビューを実行する。指摘が🔴/🟡を含む場合は[/devflow:resolve](${CLAUDE_PLUGIN_ROOT}/skills/resolve/SKILL.md)で対応し再レビューする。ただし対応に要件・ビジネスルールの変更を要する指摘が出た場合は、下記「例外停止条件の自己解決」の手順に従う。
3. 指摘が🟢のみになった時点で、ユーザーの回答(明示的なOK)を待たずに自動承認とみなし、次の承認処理(手順4)へ進む。
4. 承認処理では、通常モードで行う「マージ前に全推測マーカーを削除する」手順を省略し、推測マーカーが残っていてもそのままpush・マージのコマンドブロックを提示する(下記「推測マーカーの扱い」)。

## 例外停止条件の自己解決

下記「例外停止」6条件のうち、次の5条件に限り自己解決を優先する判定に変える(**着手前チェックでの重複進行中ブランチ・worktree検知は対象外**。理由は次項)。

- 要件・仕様どおりに実装できない事情の判明
- レビュー指摘対応が要件・ビジネスルールの変更を要する
- CIの失敗がリトライで解消しない
- 本番インフラの破壊的変更・データ移行が必要と判明
- (fix起点)実装判断に確信が持てない

1. いずれかに該当した場合、まず安全に選べる代替策があるかを検討する。代替策の例: 仕様・実装上の合理的な代替案を選ぶ、CIのリトライ上限内で再試行する、など。
2. 代替策がある場合は、その代替策を選び対象箇所に【推測】マーカーを付けて自走を継続する。requirements.md・design.mdへの書き足しが必要な場合はここで追記する(fix起点で仕様変更を伴わない場合は実装PR本文の「判断に迷った点」への記載で代替する、既存の推測マーカー運用と同じ)。
3. 代替策がない場合(本番インフラへの破壊的変更が実際に避けられない、要件・仕様の矛盾が推測では埋められない、など安全に選べる代替策が存在しないケース)は、通常モードの例外停止と同様にそのタスクの自走を打ち切る。状況・検討した代替策とそれを選ばなかった理由・打ち切り理由をまとめて報告し、ユーザーの指示を待つ(勝手に要件・仕様を書き換えたり、危険な変更を推測で強行したりしない)。
4. CI失敗については、自動リトライの上限を3回に拡大する(通常モードの1回から拡大)。3回リトライしても解消しない場合は「打ち切り」ではなく「既知事項として明記し前進する」に分類し、実装PR本文に失敗しているテスト・チェックを明記した上で、そのタスクの完走自体は止めずに進められるところまで進める。
5. 委譲先エージェント(spec-reviewer/code-reviewer/implementer/impl-pr-reviewer)からの中断報告も、「要件・仕様どおりに実装できない事情の判明」として上記の代替策判定の対象に含める。

**着手前チェック([parallel-work](${CLAUDE_PLUGIN_ROOT}/skills/parallel-work/SKILL.md)の重複検出)での重複進行中ブランチ・worktree検知は、上記の自己解決の対象外とする。** 検知した時点で、通常モードと同様にそのタスクの自走を完全に停止し、別のブランチ名・worktreeへ無断で切り替えて継続することはしない。parallel-work Skillの「重複が疑わしい対象に気づいたら新規着手を保留しユーザーに報告する」ルールとの整合を優先し、無断でブランチを切り替えて同じ対象へ二重着手する事故を防ぐための安全弁である。検知した状況をまとめて報告し、ユーザーの指示を待つ。

## 推測マーカーの扱い

- 仕様承認PRを自動承認で進める場合、通常モードのマージ前「全マーカー削除」手順(`grep -rn '【推測】' <spec配置ディレクトリ>` で残りゼロを確認してからマージする手順)を省略し、マーカーが残った状態のままpush・マージのコマンドブロックを提示する。引き継ぎコマンド提示時のメッセージに、「人が朝マージを実行する際、PR差分に残る【推測】マーカーが実質的な最終レビュー機会になる」旨を明記する。
- 対象が仕様承認PR方式(study等、specをリポジトリにコミットするプロジェクト)の場合、「フロー(新機能起点)」ステップ7、または「フロー(fix起点)」ステップ4で実装用のfeatureブランチを作成した直後・TDD着手前に、そのブランチ上で`grep -rn '【推測】' <spec配置ディレクトリ>`で残りゼロになるまで推測マーカーを解消するコミットを作成する(mainへ直接コミットしない。チャット承認方式のプロジェクトはspecがリポジトリにコミットされないため対象外)。

## 引き継ぎポイント(単一タスク前提)

push/PR作成/CI確認/マージなどの引き継ぎポイントに到達するたびに、通常モードと同様にコマンド一式をコピペ可能な1ブロックにまとめて提示し、実行結果の報告を受けたらそこから先の工程へ自走を続ける(通常モードと同じ挙動)。1つのタスクの中には複数の引き継ぎポイント(仕様承認PRのpush・マージ、実装PRのpush・マージ等)があり、その都度この手順で再開する。

本Skillの1回の起動は常に単一タスクであることを前提とする。**この前提が意味を持つのは、実装PR作成後の最後の引き継ぎポイントに到達したときだけ**である。複数タスクのキュー処理(他に着手可能なタスクが渡されていれば次のタスクへ進む)はnight-batch(別Skill、未実装。spec: `~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/night-batch/`)側の責務であり、本Skillはそのタスクの完了報告をもって自走を終了し、自分で次のタスクには進まない。

引き継ぎコマンドの実行結果を待っている間は「完了」と報告しない(通常モードの注意書きを維持する)。マージ後にユーザーに残す作業は、既存の[/devflow:pr](${CLAUDE_PLUGIN_ROOT}/skills/pr/SKILL.md)の完了時案内(本番反映の確認・ブランチ/worktreeの掃除)の範囲を超えて増やさない。

## 完了報告への追記

「フロー(新機能起点)」ステップ10・「フロー(fix起点)」ステップ7の完了報告に、「ノンストップモードで自動判断した箇所の一覧」(対話ポイント②の自動承認有無・例外停止条件で代替策を選んだ箇所とその内容・CIリトライ回数・copilot担当からclaude担当へ読み替えたタスク番号とその理由)を追加でまとめて記載する。このSkillはシステムログを持たないMarkdown手順書のため、チャット上のこの報告がログの代替になる。タスクを打ち切った場合(代替策なしで例外停止した場合)は、通常モードの例外停止報告と同じ形式で、検討した代替策・それを選ばなかった理由・打ち切り理由を明記して報告する。

# フロー(新機能起点)

各ステップの手順・テンプレートはリンク先の工程Skillに従う。

1. **要件定義(対話①)**: [/devflow:requirement](${CLAUDE_PLUGIN_ROOT}/skills/requirement/SKILL.md)をそのまま実施する(JIRAチケット確認・Step0の入口判断・ヒアリングも通常どおり)。ヒアリングは要件に閉じず、設計の分かれ道になる事項もここで合わせて確認する(下記「ヒアリングの範囲」)
2. **自動運転宣言**: ヒアリング完了後、「ここから仕様承認PRの提示まで自走する」と宣言し、以降はユーザー確認なしで進む
3. **設計**: [/devflow:design](${CLAUDE_PLUGIN_ROOT}/skills/design/SKILL.md)に従いメインスレッドがdesign.md・tasks.mdを作成する。ヒアリングで確認できていない細部は質問せず妥当な推測で補い、推測で決めた箇所には推測マーカーを付ける(下記「推測マーカー」)
4. **仕様レビュー**: [/devflow:spec-review](${CLAUDE_PLUGIN_ROOT}/skills/spec-review/SKILL.md)(spec-reviewerエージェント)。🔴/🟡は[/devflow:resolve](${CLAUDE_PLUGIN_ROOT}/skills/resolve/SKILL.md)で対応し再レビューする。ただし対応に要件・ビジネスルールの変更が必要な指摘は例外停止(下記)
5. **仕様承認PR(対話②+引き継ぎ)**: [/devflow:pr](${CLAUDE_PLUGIN_ROOT}/skills/pr/SKILL.md)で仕様承認PRの本文を用意し、push〜PR作成のコマンドブロックを提示してユーザーに実行を依頼する。PR本文の「判断に迷った点・レビューしてほしい点」に**推測箇所の一覧**を明記し、一括レビューを依頼する。指摘はセッション上・PRコメントのどちらで受けてもよく、[/devflow:resolve](${CLAUDE_PLUGIN_ROOT}/skills/resolve/SKILL.md)で修正して再提示する(何往復してもよい)。**ノンストップモードでは「ノンストップモード」節の「対話ポイント②の自動承認」に従う**
6. **承認処理(引き継ぎ)**: ユーザーの明示的なOKを得たら、残っている推測マーカーを全て削除するコミットを作り(`grep -rn '【推測】' <spec配置ディレクトリ>` で残りゼロを確認する)、push・マージのコマンドをまとめて提示する。マージ完了の報告を受けてから次へ進む。**ノンストップモードでは「ノンストップモード」節の「推測マーカーの扱い」に従う(全マーカー削除の手順を省略する)**
7. **実装**: マージ後、新しいfeatureブランチを切り([/devflow:pr](${CLAUDE_PLUGIN_ROOT}/skills/pr/SKILL.md)共通ルール)、[/devflow:implementation](${CLAUDE_PLUGIN_ROOT}/skills/implementation/SKILL.md)に従いTDDで実装する。並行作業中など委譲したい事情があればimplementerエージェントに委譲してよい。architecture.mdを持つ対象では、実装に着手する前に機能マップの状態列を「実装中」に更新し表を提示する(下記「機能マップ(状態列)の更新」)
8. **実装レビュー**: [/devflow:implementation-review](${CLAUDE_PLUGIN_ROOT}/skills/implementation-review/SKILL.md)(code-reviewerエージェント)。🔴/🟡は[/devflow:resolve](${CLAUDE_PLUGIN_ROOT}/skills/resolve/SKILL.md)で対応し再レビューする。仕様の変更が必要な指摘は例外停止
9. **実装PR(引き継ぎ)**: [/devflow:pr](${CLAUDE_PLUGIN_ROOT}/skills/pr/SKILL.md)(impl-pr-reviewerチェック→PR本文作成)。push〜PR作成〜CI確認のコマンドブロックを提示し、ユーザーの実行結果の報告を待つ。CIが失敗した場合は原因の修正を1回だけ自動で試み、それでも失敗するなら例外停止する。**ノンストップモードでは「ノンストップモード」節の「例外停止条件の自己解決」に従い、リトライ上限を3回に拡大し、3回失敗しても打ち切らずPR本文に既知事項として明記して完走する**
10. **完了報告**: マージ済みの報告を受けたら、[/devflow:pr](${CLAUDE_PLUGIN_ROOT}/skills/pr/SKILL.md)の完了時案内に従って本番反映の確認手順とブランチ/worktreeの掃除を案内し、全工程のサマリをまとめて報告する — 作成したspec、PRのURL2件、テスト件数、自動対応したレビュー指摘の一覧、更新後の機能マップ(architecture.mdを持つ対象の場合)、例外停止の有無。**ノンストップモードでは「ノンストップモード」節の「完了報告への追記」に従う**

# ヒアリングの範囲

対話①では/devflow:requirementの要件ヒアリングに加えて、**設計(design.md)の分かれ道になる事項**も先に確認する。ここで聞いておくほど推測マーカーが減り、仕様承認PRでの一括レビューが軽くなる。

- **聞くもの**(設計への影響が大きい事項):
  - 分岐パターンが多く、どのパターンを扱うかで処理フローが大きく変わる事項
  - パターンの切り替えによって提供する機能・エンドポイント・画面が大きく変わる事項(新しい画面が増える場合は[/devflow:requirementの要件ヒアリング](${CLAUDE_PLUGIN_ROOT}/skills/requirement/SKILL.md)のワイヤーフレーム3案での選定と画面モックでの確認に従う。どちらも対話①の中で行う)
  - 誤った推測のまま進むと手戻りが大きい事項(データの保存有無・既存機能への影響範囲・インフラ構成の変更有無など)
- **聞かないもの**(推測で進めてマーカーを付ける): メッセージ文言・ログの粒度・表示順など、PRレビューで軽く直せる細部
- 聞き方は[/devflow:requirementの要件ヒアリング](${CLAUDE_PLUGIN_ROOT}/skills/requirement/SKILL.md)と同じく一度に全部聞かず重要な順に、回答を受けたら残りが埋まっているか確認して往復する。**今回の機能に「聞くもの」に該当する事項がある限り、それらが確認できるまでステップ2(自動運転宣言)に進まない**(見切り発車で自走を始めない)。確認した内容は要件ならrequirements.mdへ、設計判断ならdesign.mdへ反映する(確認済みなのでマーカーは付けない)

# フロー(fix起点)

各ステップの手順・テンプレートはリンク先の工程Skillに従う。新機能起点との違いは、design.md/tasks.mdを作る独立した設計工程がなく、[/devflow:fix](${CLAUDE_PLUGIN_ROOT}/skills/fix/SKILL.md)のStep2(3点セットへの影響洗い出し)がその役割を兼ねる点。

1. **入口確認・影響洗い出し(対話①)**: [/devflow:fix](${CLAUDE_PLUGIN_ROOT}/skills/fix/SKILL.md)のStep1(JIRAチケット確認・新規spec vs 既存spec更新の判定)・Step2(既存コードの確認・3点セットへの影響洗い出し・承認要否判定)を実施する。ユーザーの依頼内容だけで判断できない曖昧な点(再現条件・期待する挙動の絞り込みなど)があればここで確認する。判断できる場合は対話なしで次に進めてよい。Step1で新規spec相当と判定した場合は「フロー(新機能起点)」の対話①(要件ヒアリング)に合流する
2. **自動運転宣言**: Step2完了後、「ここから自走する」と宣言し、以降はユーザー確認なしで進む
3. **分岐(仕様承認ゲート)**:
   - **仕様変更あり**(ビジネスルール変更・スコープ外だった項目への対応など): 3点セットを更新し、[/devflow:pr](${CLAUDE_PLUGIN_ROOT}/skills/pr/SKILL.md)の仕様承認PRの手順で本文とコマンドブロックを提示する。PR本文の「判断に迷った点・レビューしてほしい点」に**推測箇所の一覧**を明記し、一括レビューを依頼する(**対話②**、新機能起点と同じ運用)。ユーザーの明示的なOK+推測マーカー残りゼロを確認してからマージのコマンドを提示する。**ノンストップモードでは「ノンストップモード」節の「対話ポイント②の自動承認」「推測マーカーの扱い」に従う**
   - **仕様変更なし**(純粋なバグ・軽微な変更): 対話②は発生させず、そのまま次のステップへ進む
4. **TDD修正**: [/devflow:fix](${CLAUDE_PLUGIN_ROOT}/skills/fix/SKILL.md) Step3(再現テスト→修正)を実施する。architecture.mdを持つ対象で対象specがリリース済みなら、着手前に機能マップの状態列を「実装中」に戻し表を提示する。ヒアリングで確認できていない実装上の判断(文言・ログ粒度など)は質問せず妥当な推測で補ってよいが、合理的な選択肢が複数あり自信を持って決められない場合は例外停止する
5. **実装レビュー**: [/devflow:implementation-review](${CLAUDE_PLUGIN_ROOT}/skills/implementation-review/SKILL.md)(code-reviewerエージェント)。🔴/🟡は[/devflow:resolve](${CLAUDE_PLUGIN_ROOT}/skills/resolve/SKILL.md)で対応し再レビューする。仕様の変更が必要な指摘は例外停止
6. **実装PR(引き継ぎ)**: [/devflow:pr](${CLAUDE_PLUGIN_ROOT}/skills/pr/SKILL.md)(impl-pr-reviewerチェック→PR本文作成)。ステップ4で確認なしに決めた判断があれば、PR本文の「判断に迷った点」に明記する。push〜PR作成〜CI確認のコマンドブロックを提示し、実行結果の報告を待つ。CIが失敗した場合は原因の修正を1回だけ自動で試み、それでも失敗するなら例外停止する。**ノンストップモードでは「ノンストップモード」節の「例外停止条件の自己解決」に従い、リトライ上限を3回に拡大し、3回失敗しても打ち切らずPR本文に既知事項として明記して完走する**
7. **完了報告**: マージ済みの報告を受けたら、[/devflow:pr](${CLAUDE_PLUGIN_ROOT}/skills/pr/SKILL.md)の完了時案内に従って本番反映の確認手順とブランチ/worktreeの掃除を案内し、全工程のサマリをまとめて報告する — 修正内容、PRのURL(仕様変更ありの場合2件・なしの場合1件)、テスト件数、自動対応したレビュー指摘の一覧、更新後の機能マップ(architecture.mdを持つ対象の場合)、確認なしで決めた判断点の一覧、例外停止の有無。**ノンストップモードでは「ノンストップモード」節の「完了報告への追記」に従う**

# copilot担当タスクの扱い(agent-routing)

tasks.mdに`【担当: copilot】`が付いたタスクへ到達したときの扱い。`~/.claude/config/agent-routing.json`が無いプロジェクト・マシンではこの節ごと不要。手順の本体は[/devflow:implementation](${CLAUDE_PLUGIN_ROOT}/skills/implementation/SKILL.md)の「Copilotへの委任」に従い、本節はautopilot特有の分岐だけを定める。

**通常モード**:

1. [/devflow:implementation](${CLAUDE_PLUGIN_ROOT}/skills/implementation/SKILL.md)の「委任の実行」手順1〜6(承認確認・実体の導入確認・Redテストの用意・委任ブランチとworktreeの作成・コマンドブロックの提示・セッション上限ぶんの暫定計上)までを行い、**Copilot CLIの完了を待たずに**後続のclaude担当タスクへ進む。この提示は上記「引き継ぎポイント」と異なり実行結果の報告を待たない。委任基準の「依存の葉であること」により、後続タスクが委任中のタスクの成果物に依存しないことが担保されている
2. 1回の走行に複数のcopilot担当タスク(または組)がある場合、取り込みが済んでいない委任も手順1の暫定計上によって有効残量へ反映されている。次の委任へ進む前に、まず[/devflow:design](${CLAUDE_PLUGIN_ROOT}/skills/design/SKILL.md)の「クレジット残量の記録」の手順1〜3で記録を有効にする前処理を行い(リセット日を越えた記録で判断しないため)、そのうえで有効残量を再計算し、**委任用閾値を割っていればそれ以降の委任コマンドブロックを提示せず**claude担当として実装する
3. 委任結果の取り込みは[/devflow:implementation-review](${CLAUDE_PLUGIN_ROOT}/skills/implementation-review/SKILL.md)の開始時に行う(前提条件に定義済み)。実消費は委任worktreeの`copilot-usage.json`から読み取り、プラン値の貼り付けはユーザーに求めない

**ノンストップモード**: copilot担当タスクをclaude担当に読み替えてClaudeが実装し、完走を優先する(夜間はユーザーが委任コマンドを手元実行できないため)。委任を提示しないので暫定計上も行わない。読み替えたタスク番号と理由は完了報告の「自動判断した箇所の一覧」に含める。

# 機能マップ(状態列)の更新 — 委譲してもメインスレッドが必ず行う

対象specがarchitecture.mdを持つ場合(architecture-workflow採用プロジェクト)、[architecture-workflow](${CLAUDE_PLUGIN_ROOT}/skills/architecture-workflow/SKILL.md)の「更新タイミング」で定める機能マップの状態列更新を、実装をimplementerエージェントに委譲しても**委譲対象から外し、メインスレッドが自分の責務として実行する**(implementerは仕様外の変更をしない設計のため、構造上メインスレッドの仕事になる)。architecture.mdを持たない単一specの場合、この節は不要。

自走中に見落としやすいポイントなので、フロー中の該当ステップ(新機能起点ステップ7・10、fix起点ステップ4・7)で省略しない。いずれのタイミングでも「ファイルを直すだけ」で終わらせず、**更新後の機能マップ全体を該当工程の報告にチャット上で貼る**(セッションを閉じる前にユーザーが全体進捗を1画面で把握できることが目的)。

# 推測マーカー

- **対象**: ヒアリング・入口確認で確認していないのに設計判断(fix起点では実装判断を含む)として決めた事項(メッセージ文言・ログ粒度・エラー時の扱い・スコープの線引きなど)。design.mdだけでなく、requirements.mdに要件として書き足す場合も同様。fix起点で仕様変更を伴わない場合はrequirements.md/design.mdへの書き足しがないため、実装PR本文の「判断に迷った点」への記載で代替する
- **書き方**: その箇条書き・文の末尾に `【推測】` を付ける
- **削除**: 仕様承認PRでユーザーのOKが出たら、マージ前に全マーカーを削除する(`grep -rn '【推測】' <spec配置ディレクトリ>` で残りゼロを確認してからマージを依頼する)。レビュー往復の中でユーザーが確認・修正した箇所は、その時点でマーカーを外してよい(ノンストップモードでは「ノンストップモード」節「推測マーカーの扱い」のとおり、この削除手順を省略する)

# 例外停止

次のいずれかに当たったら自走をやめ、状況と選択肢をまとめて報告してユーザーの指示を待つ(勝手に要件・仕様を書き換えて進まない)。正常系では発動しない安全弁であり、対話ポイントを増やすものではない。ノンストップモードでは、このうち5条件(重複進行中ブランチ・worktree検知を除く)を「ノンストップモード」節「例外停止条件の自己解決」の分岐に差し替える。

- 要件・仕様どおりに実装できない事情が判明した(implementerの中断報告、仕様の矛盾・不足の発見を含む)
- レビュー指摘への対応が要件・ビジネスルールの変更を要する
- 着手前チェック([parallel-work](${CLAUDE_PLUGIN_ROOT}/skills/parallel-work/SKILL.md)の重複検出)で同じspecを扱う進行中ブランチ・worktreeを検知した
- CIの失敗が自動対応(1回)で解消しない
- 本番インフラ(Terraform)の破壊的変更・データ移行が必要と分かった
- (fix起点)実装上の判断に合理的な選択肢が複数あり、確信を持って決められない

# 完了時の次ステップ案内

完了報告をもって終了。本番で問題が見つかった場合は[/devflow:fix](${CLAUDE_PLUGIN_ROOT}/skills/fix/SKILL.md)へ(自動運転はここまで。修正は通常フローで行う)。
