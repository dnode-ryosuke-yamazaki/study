---
name: spec-review
description: 仕様3点セット(requirements.md/design.md/tasks.md)をレビューし、指摘なしになったらチャット上でユーザーの明示的な承認を得るときに使う。チェックリスト・指摘の重要度基準・フィードバックテンプレート・承認ゲートの運用を含む。プロジェクトが独自の`.claude/skills/spec-review/SKILL.md`を持つ場合はそちらを優先する。
---

> ワークフロー上の位置: [/devflow:design](../design/SKILL.md) → **/devflow:spec-review(本Skill)** → 指摘あり: [/devflow:resolve](../resolve/SKILL.md) / 指摘なし: 承認(チャット承認、または仕様承認PR方式なら[/devflow:pr](../pr/SKILL.md)の仕様承認PR) → [/devflow:implementation](../implementation/SKILL.md)。全体フロー・モデル対応表は[dev-flow.md](../../dev-flow.md)を参照

# 前提条件

- 対象spec(ローカルミラーパス、[dev-flow.md](../../dev-flow.md#specの置き場所ローカル専用リポジトリにコミットしない)参照)の`requirements.md`が存在すること。なければ[/devflow:requirement](../requirement/SKILL.md)から始める
- design.md/tasks.mdが存在すること(分岐のない単純な機能でrequirements.mdのみと判断した場合を除く。判断基準は[/devflow:design](../design/SKILL.md))。未作成なら[/devflow:design](../design/SKILL.md)から始める
- レビュー対象が[/devflow:test-design](../test-design/SKILL.md)の`system-test.md`(spec横断の総合試験仕様書)の場合は、上記に代えて対象範囲の全specが承認済みであること。spec-reviewerには対象がsystem-test.mdであることと対象specの一覧を伝える(チェックリストは[base/spec-review.md](../../quality-standards/base/spec-review.md)の「system-test.md」節)

# 起動前の機械検査

spec-reviewerを起動する**前に**、メインスレッドが層分けの検査スクリプトを対象specフォルダに対して実行する(spec-reviewerは読み取り専用のまま保ち、検査結果は入力として渡す)。

```
python3 ${CLAUDE_PLUGIN_ROOT}/lib/spec_layout_check/scripts/check_spec_layout.py <specフォルダの絶対パス>
```

同じ変更で architecture.md を直した場合は、**architecture.md のあるフォルダ(specフォルダの1階層上の `specs/`)も渡してもう1回実行する**。specフォルダを渡す検査では architecture.md は対象に入らない。

終了コードごとの扱い:

| 終了コード | 意味 | 扱い |
|---|---|---|
| 0 | 違反なし | 「機械検査: 違反なし」と、出力末尾の人が読む文字数・目印別の行数を起動指示に添える |
| 1 | 違反あり | 標準出力の違反一覧をそのまま起動指示に添える。spec-reviewerは違反1件を🔴の指摘1件として報告に含める(要点の文言や目印の正しさは判断しない)。同じspecの中に旧形式のファイルが混ざっていると種別 `旧形式` の行も一覧に並ぶが、これは「そのファイルは層分けの検査の対象外」という情報なので🔴には数えない。ただし種別 `フロントマター無し` の行は、1でも2でも🔴1件として数える(下の2の行) |
| 2 | 違反は無いが、旧形式かフロントマター無しのファイルがある | **この工程に来るspecは直前の[/devflow:requirement](../requirement/SKILL.md)・[/devflow:design](../design/SKILL.md)が新形式で書いたものなので、2が返ったら旧形式ではなく書きかけ**(畳みか出所の目印がまだ1つも入っていない。両者は文字面が同じで機械では見分けられない)。🔴1件として[/devflow:resolve](../resolve/SKILL.md)へ戻し、骨格の畳みと目印を入れてから検査し直す。旧形式の既存specを直している途中なら、先に[/devflow:fix](../fix/SKILL.md)の新形式化を済ませる。種別 `フロントマター無し` の行も同じく書きかけで、ファイルごとに🔴1件として戻す(既存specなら[dev-flow.mdの移行手順](../../dev-flow.md#フロントマターを持たない既存specの移行)で付けてから検査し直す) |
| 3 | 区分け表が読めない | 検査を中断した旨を🔴1件としてレビュー結果に含め、spec-reviewerは通常どおり起動する。直す対象は対象specではなく`quality-standards/base/spec-layout.md`の側 |

**スクリプトを起動できない場合**(Pythonが無い・パスが違う)も、🔴1件(原因: 起動失敗)としてレビュー結果に含め、spec-reviewerによるレビューは続ける。検査が動かなかったことを「違反なし」と取り違えさせないため、検査を飛ばして黙って進めない。

いずれの場合も、検査の実施有無・違反件数・旧形式とフロントマター無しの判定・人が読む文字数・目印別の行数を、報告の「参照したチェックリスト」欄に1行で残す。

あわせて `--visible` を付けてもう一度実行し、**承認者が実際に目にする行だけ**を spec-reviewer の起動指示に添える。エージェントには「この行だけを読んで意味が取れない箇所・主語が抜けている箇所・目的の書かれていない成果物を挙げよ」と伝える(仕様書を書いた本人は自分の文脈で読めてしまうため、文脈を持たない読み手として読ませる)。

```
python3 ${CLAUDE_PLUGIN_ROOT}/lib/spec_layout_check/scripts/check_spec_layout.py --visible <specフォルダの絶対パス>
```

# レビューの実施方法

レビューはspec-reviewerエージェント(Agentツールの`subagent_type`は`devflow:spec-reviewer`。定義は`${CLAUDE_PLUGIN_ROOT}/agents/spec-reviewer.md`)を起動して行う。仕様を書いたメインスレッドの文脈から切り離し、新鮮な目でレビューするため。

- エージェントには対象specのローカルミラーパスを伝えて起動する
- エージェントの報告(フィードバックテンプレート形式)は要約せずそのままユーザーに提示する
- エージェントの既定モデルはSonnet([dev-flow.md](../../dev-flow.md)のモデル対応表参照)。複雑なロジックが絡み見落としのコストが大きい設計に限り、起動時に`model: opus`で上書きしてよい

レビューの注意事項・チェックリスト・重要度基準・フィードバックテンプレートは[quality-standards/base/spec-review.md](../../quality-standards/base/spec-review.md)にあり、エージェントが直接読んで従う(会社標準・プロジェクト固有の追加項目があればcompany層・project層も合成する。合成ルールは[quality-standards/README.md](../../quality-standards/README.md))。**メインスレッドはこれらのファイルを読まない**(エージェントだけが使う内容を本体から分離し、二重読み込みを避けている)。エージェントを使えない状況でメインスレッドが直接レビューする場合のみ読み、同じ内容に従う。

# 仕様承認ゲート(チャットでの明示的承認)

指摘なし(🟢のみ)になったら、3点セットのフロントマターを `status: in-review` にしてから、3点セット(またはその要点)をユーザーに提示し(appendix.md・画面モック mock.html があればそれも含め、モックはプレビューのArtifactのURLで示す)、**明示的な承認の返答を得るまで実装(テストを含む)に着手しない**。「承認します」「これで進めて」のような明確な意思表示を待つ。曖昧な返答(質問・様子見のコメントのみ)は承認とみなさない。

- ユーザーから修正依頼があれば、直すファイルのフロントマターを `status: draft` に戻し(`version` は変えない)、指摘として扱い[/devflow:resolve](../resolve/SKILL.md)で対応するか、内容次第で[/devflow:requirement](../requirement/SKILL.md)・[/devflow:design](../design/SKILL.md)に戻る
- ユーザーが**合意した覚えのない〔合意〕**の行を指摘した場合は🔴1件として扱い、[/devflow:resolve](../resolve/SKILL.md)で`〔提案〕`へ直してから改めて承認を求める(目印が本当に会話で決めたことを指しているかは機械では検査できず、承認者の目視だけが頼りになる)
- 承認を得たら、`in-review` のファイルのフロントマターを `status: approved` にし、`approved_date` に承認日(`YYYY-MM-DD`)を足す。`version` が `0.x` なら `"1.0"` にし、承認後の改訂(`1.1` など)を再承認したときはそのままにする。承認の記録はこのフロントマターが持つ。書き換えたら機械検査をもう一度実行し、`フロントマター不正` が出ないことを確かめる。値の遷移の正は[dev-flow.mdの「承認状態のフロントマター」](../../dev-flow.md#承認状態のフロントマター)
- requirements.md のステータスのラベルは「仕様確認中(未実装)」のままにする(「実装中」に変えるのは最初の🔴Redテストが書けた時点。[/devflow:implementation](../implementation/SKILL.md)参照)。**ラベルの値に承認日や補足を足さない**(例: `ステータス: 仕様確認中(未実装) ／ 優先度: 高`)。承認日はラベルではなくフロントマターの `approved_date` に書く

**仕様承認PR方式のプロジェクト**: specをリポジトリにコミットする例外リポジトリ(`~/.claude/config/project-profiles.json`の`github.repos`でカレントリポジトリの絶対パスに一致するエントリが`approval: "pr"`を持つもの。例: study。この判定はPJの解決(依頼文でのPJ名指定・デフォルトPJ)を経由せず、カレントリポジトリの絶対パスだけで行う例外。詳細は[project-profile](~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/project-profile/design.md#開発フローskillの例外リポジトリパスでの解決)・[dev-flow.md](../../dev-flow.md#specの置き場所ローカル専用リポジトリにコミットしない))では、チャット承認の代わりに[/devflow:pr](../pr/SKILL.md)の「仕様承認PR」を作成し、ユーザーの承認・マージをもって承認とする。承認までコード(テストを含む)を書かない点は同じ。フロントマターは `in-review` でPRに載せ、`approved` への書き換えは[/devflow:pr](../pr/SKILL.md)がマージ前に行う。

# 完了時の次ステップ案内

- 🔴/🟡の指摘がある → [/devflow:resolve](../resolve/SKILL.md)で修正後、本Skillで再レビュー
- 指摘なし(🟢のみ) → 上記の承認ゲートに従いユーザーの承認を得て、3点セットのフロントマターが `approved` になったうえで[/devflow:implementation](../implementation/SKILL.md)へ進む
