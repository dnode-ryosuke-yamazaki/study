---
name: scan-sandbox-sessions
description: 直近のClaude Codeセッションログを遡って、~/.claude/sandbox-limitations.mdにまだ記録されていないサンドボックス/権限エラーの候補がないか棚卸しするときに使う。ユーザーが明示的に依頼したときのみ実行する(定期作業・自動発火しない)。
disable-model-invocation: true
---

> ワークフロー上の位置: 定期作業(開発ループ外)。候補が見つかった場合の追記は`record-sandbox-limitation`スキル(全プロジェクト共通、`~/.claude/skills/record-sandbox-limitation/SKILL.md`)の手順に従う

# 直近セッションのサンドボックス制限棚卸し

`record-sandbox-limitation`スキルは「その場で判明した制限をその都度記録する」スキルだが、記録し忘れたまま流れたセッションを後から拾うためのスキル。会話ログ全体を読み込むと高コストなため、失敗を示す断片だけを安く抜き出す。

## Step1 対象セッションを決める

このプロジェクトのセッションログは `~/.claude/projects/<cwdを/→-に置換したもの>/*.jsonl` に保存されている。

```bash
dir="$HOME/.claude/projects/$(pwd | tr '/' '-')"
ls -t "$dir"/*.jsonl 2>/dev/null | head -10
```

直近10件を対象にする。保存されているファイルが10件未満ならある分すべてを対象にし、その旨をユーザーに伝える(エラーにしない)。

## Step2 各セッションからエラー断片だけを抽出する

セッションログ(JSONL)は1行1メッセージで、ツール実行結果は `type=="user"` のエントリの中の `message.content[].type=="tool_result"` に入っている。ここだけを対象にすることで、Claudeの説明文中に出てくる「Operation not permitted」等の言及(実際のエラーではない)を拾ってしまう誤検知を避ける。

対象ファイルそれぞれに対して実行する:

```bash
jq -r '
  select(.type=="user")
  | . as $e
  | $e.message.content[]?
  | select(.type=="tool_result")
  | (if (.content|type)=="string" then .content
     else ([.content[]? | select(.type=="text") | .text] | join("\n"))
     end) as $text
  | ($text | [scan("(?i)([^\\n]{0,50}(?:operation not permitted|permission denied|connect tunnel failed|unable to access|403 [a-z]+|eacces|enotfound|blocked by (?:the )?sandbox)[^\\n]{0,80})")]) as $hits
  | select(($hits | length) > 0)
  | $hits[][0]
' "$file" | sort -u
```

- 検索パターン(`operation not permitted` 等)は`~/.claude/sandbox-limitations.md`に載っている既知の言い回しをベースにしている。新しい種類の拒否メッセージに気づいたら都度パターンに追加してよい
- `sort -u`で同一ファイル内の重複(同じ警告の連投など)を落とす
- 1ファイルの出力が異常に多い場合は`head -20`等で切ってよい(それでも多い場合はユーザーにセッション数を減らすか確認する)

## Step3 候補を絞り込む

抽出した断片を`~/.claude/sandbox-limitations.md`の「確認済みの制限事項」と突き合わせ、**既に記載済みの内容と実質的に同じものは除外する**(例: `/etc/gitconfig`・`/etc/gitattributes`・GitHubへのCONNECT tunnel 403は既知)。

残った断片が「まだ記録されていない新しい制限の可能性があるもの」の候補になる。

**注意(誤検知)**: 断片の中には、実際のコマンド失敗ではなく、`~/.claude/sandbox-limitations.md`自身や本Skill自身をcat/Readした結果(ドキュメントの文面をそのまま引用しているだけ)が紛れることがある。断片の前後にコマンド名・パス・exit codeなど「実際に失敗した形跡」があるかを見て判断し、単なる引用は候補から除外する。

## Step4 ユーザーに確認する

候補を「どのセッション(ファイル名・日時)で・何をしようとして・どんなエラーが出たか」がわかる形で一覧にして提示し、それぞれ記録してよいか確認する。断片だけでは状況(何のコマンドを実行したか等)が推測になる場合は、その旨を明記し断定しない。

候補がゼロだった場合は「新規候補なし」とだけ報告して終了する。

## Step5 確認が取れたものを記録する

ユーザーが確認した候補について、`record-sandbox-limitation`スキルのStep3〜6(記録内容の確認・追記)に従って`~/.claude/sandbox-limitations.md`に追記する。このスキル自身はコミット・pushを行わない。

## 注意

- セッションログはこのマシン・このユーザーのローカルにしか残らない(他メンバーの環境の制限はここには出てこない)。あくまで「自分が最近気づかずに流してしまった制限」を拾うための補助であり、チーム全体の網羅的な収集手段ではない
- 保持期間設定(`cleanupPeriodDays`)より古いセッションは既に削除されている場合がある
