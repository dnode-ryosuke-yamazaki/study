#!/bin/bash
# SessionStartフック: ローカルmainがorigin/mainより遅れていたら警告をコンテキストに注入する。
# 別セッション・別worktreeでマージされた成果物に気づかず、古いローカル状態を前提に
# 重複作業を始めるのを防ぐ。
#
# このサンドボックス環境向けの調整(移植元との差分):
#   - `git fetch` を行わない。外部ネットワークが遮断されており必ず失敗するため
#     (~/.claude/sandbox-limitations.md 項目1)。比較対象は「ユーザーが手元ターミナルで
#     最後に pull/fetch したときの origin/main」になる。取りこぼしはあるが、
#     手元で main を更新した直後のセッションで遅れを検知できれば目的は果たせる
#   - `GIT_CONFIG_NOSYSTEM=1` を付ける。/etc/gitconfig を読めず git 全般が失敗するため
#     (同 項目5)
export GIT_CONFIG_NOSYSTEM=1

cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0

# テスト用に比較対象を差し替えられるようにする(通常は main と origin/main)
local_ref="${FRESHNESS_LOCAL_REF:-main}"
remote_ref="${FRESHNESS_REMOTE_REF:-origin/main}"

# リモート追跡ブランチが無い(clone直後・fetch未実施)場合は判定しない
git rev-parse --verify --quiet "$remote_ref" >/dev/null 2>&1 || exit 0

behind=$(git rev-list --count "${local_ref}..${remote_ref}" 2>/dev/null)
if [ -z "$behind" ] || [ "$behind" -eq 0 ]; then
  exit 0
fi

recent=$(git log --oneline -5 "${local_ref}..${remote_ref}" 2>/dev/null)

context=$(cat <<EOF
【mainの鮮度警告】ローカルmainは(最後に手元ターミナルでfetch/pullした時点の)origin/mainより ${behind} コミット遅れています。未取り込みのコミット(最新5件):
${recent}
別セッションでマージされた作業と重複しないよう、工程Skill(要件定義・設計・実装・修正)に着手する前に main を最新化し、これから行う作業が上記コミットで既に対応済みでないか確認すること。このサンドボックスからは git pull を実行できないため、ユーザーの手元ターミナルでの実行を依頼する。
EOF
)

jq -n --arg ctx "$context" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'