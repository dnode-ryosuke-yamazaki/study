# 品質基準の3層合成読み

レビューAgent(spec-reviewer・code-reviewer)が使うチェックリストは、**base(このSkill群の既定)→ company(会社標準)→ project(プロジェクト固有)** の3層で構成する。3層とも「同じ工程用のファイルが存在すれば読み、チェックリストへ追加する」だけの単純な合成で、上位層が下位層を書き換えたり無効化したりはしない(**すべて加算。除外・上書きはできない**)。

## ディレクトリ構成

```
${CLAUDE_PLUGIN_ROOT}/quality-standards/
    base/
        spec-review.md            # /devflow:spec-reviewの既定チェックリスト(旧skills/spec-review/references/checklist.md)
        implementation-review.md  # /devflow:implementation-reviewの既定チェックリスト(旧skills/implementation-review/references/checklist.md)
    company/
        spec-review.md            # 会社標準(全社共通)の追加チェック項目。無ければこのファイルごと無い
        implementation-review.md  # 同上

<プロジェクトルート>/.claude/quality-standards/
    spec-review.md                # このプロジェクト固有の追加チェック項目。無ければこのファイルごと無い
    implementation-review.md      # 同上
```

工程名(`spec-review`・`implementation-review`)ごとにファイルを分け、3層とも同じファイル名を使う。新しい工程にレビューAgentを追加する場合は、3層それぞれに同名のファイルを置ける形にする(company/projectは無ければ作らなくてよい)。

## 各層の役割

- **base/**: このSkill群が既定で要求する最小限の品質基準。指摘の重要度基準・フィードバックテンプレート・「好みの問題は指摘しない」等のレビュー実施ルールもここが正で、company/projectには持たせない(手続き面はbaseに一本化する)
- **company/**: 会社・組織全体で追加したいチェック項目が出てきたら、この配下に工程名と同じファイル名で置く。全プロジェクトのレビューに自動的に反映される。**ファイルを置くだけでよく、既存Skill・Agentの変更は不要**
- **project(プロジェクト側`.claude/quality-standards/`)**: そのプロジェクト固有の追加チェック項目(例: このプロジェクトはアクセシビリティ必須)。そのプロジェクトのリポジトリで管理し、他プロジェクトには影響しない

## company/project層のファイルの書き方

company/projectのファイルは、baseのような手続き文書ではなく、**追加のチェック項目だけを列挙する**。書式:

```markdown
# <会社名 または プロジェクト名>品質基準追加分 — <spec-review または implementation-review>

## 追加チェックリスト
- [ ] (追加したい観点。base側チェックリストの見出し(例: `## design.md`)に対応付けられる場合はその見出し名を添える)
- [ ] ...
```

重要度基準・フィードバックテンプレートの形式はbase/を継承する(company/project側では再定義しない)。追加項目に個別の重要度(🔴/🟡/🟢)を明記したい場合は箇条書きの先頭に付ける(例: `- [ ] 🔴 ...`)。指定が無い場合、レビューAgentはbaseの重要度基準に照らして判断する。

## レビューAgentの読み方

spec-reviewer・code-reviewerは、対象の工程に対応する3層のファイルを**base→company→project**の順に読み、存在するものだけを合成してチェックリストとする(company/projectが存在しない場合は読まずスキップし、エラーにしない)。project層のパスは、レビュー対象のspecが属するプロジェクトルート(ローカルミラー配置なら`~/.claude/local-specs/<プロジェクトルート>/`が指す元のプロジェクトルート、例外リポジトリなら`~/.claude/config/project-profiles.json`のいずれかのPJの`github.repos`に登録されたリポジトリルート)を基準に`.claude/quality-standards/<工程名>.md`を探す。

具体的な読み込み手順・パス解決は各Agent定義(`${CLAUDE_PLUGIN_ROOT}/agents/spec-reviewer.md`・`${CLAUDE_PLUGIN_ROOT}/agents/code-reviewer.md`)を正とする。
