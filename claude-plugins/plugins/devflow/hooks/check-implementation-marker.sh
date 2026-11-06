#!/bin/bash
# SessionStart hook (ドーマント実装): 現在のブランチ名から機能名を推測し、対応する
# tasks.mdに「他ブランチ向けの実装中マーカー」が既にあれば警告をコンテキストに注入する。
# ブロックはしない(警告止まり)。
#
# 背景: 仕様レビュー担当セッションと実装担当セッションが互いの存在を知らないまま
# 同じ仕様書に同時着手したニアミス(study-cf重複事例)の再発防止策の一部。
# マーカー行そのものは/implementationが実装着手時にtasks.md先頭へ追記する
# (`> 実装中: session <name>, branch: <branch>, started: <ISO8601>`)。
#
# 置き場所: devflow プラグインの hooks/hooks.json(SessionStart)から起動する(P-03 で ~/.claude/hooks/ から移動)。
# 未検証: 組織の管理設定(allowManagedHooksOnly)ではユーザー定義 hook と同様にプラグイン hook も実行されないため、
# 実機での動作確認ができていない。移動の目的は整理であって実効性の確保ではない。
# 将来ポリシーが変わってhooksが有効になった場合は、update-configスキルの
# 「Constructing a Hook」の手順(pipe-test・jq -eでのスキーマ検証・発火確認)を先に踏むこと。

set -uo pipefail

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
branch=$(git -C "$repo_root" branch --show-current 2>/dev/null)
[ -z "$branch" ] && exit 0

feature_name="${branch#feature/}"
# ブランチ名が feature/<JIRAキー>-<機能名> 形式の場合、機能名だけの候補も作る
feature_name_no_ticket=$(printf '%s' "$feature_name" | sed -E 's/^[A-Z][A-Z0-9]*-[0-9]+-//')

mirror_root="$HOME/.claude/local-specs${repo_root}/specs"

candidates=()
for name in "$feature_name" "$feature_name_no_ticket"; do
  candidates+=("$repo_root/specs/$name/tasks.md")
  candidates+=("$repo_root"/apps/*/specs/"$name"/tasks.md)
  candidates+=("$mirror_root/$name/tasks.md")
done

warnings=""
for f in "${candidates[@]}"; do
  [ -f "$f" ] || continue
  marker_line=$(grep -E '^> 実装中: session' "$f" 2>/dev/null | head -1)
  [ -z "$marker_line" ] && continue
  marker_branch=$(printf '%s' "$marker_line" | sed -n 's/.*branch: \([^,]*\),.*/\1/p')
  if [ -n "$marker_branch" ] && [ "$marker_branch" != "$branch" ]; then
    warnings="${warnings}- ${f}\n  ${marker_line}\n"
  fi
done

if [ -n "$warnings" ]; then
  msg="⚠️ 現在のブランチ(${branch})に対応しそうなspecに、別ブランチ向けの実装中マーカーが見つかりました。並行セッションと同じ仕様に同時着手していないか確認してください。\n${warnings}"
  jq -n --arg msg "$msg" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $msg}}'
fi

exit 0
