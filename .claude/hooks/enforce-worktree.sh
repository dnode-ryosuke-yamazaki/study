#!/bin/bash
# PreToolUse(Bash)フック: 作業ディレクトリ内でのブランチ切り替えをブロックし、
# 代わりにgit worktreeを使うようClaudeに指示する(1 worktree = 1ブランチ運用の強制)。
# 詳細は .claude/skills/parallel-work/SKILL.md を参照。
#
# 許可: mainへの切り替え / mainからの新規ブランチ作成 / git checkout -- <file> のファイル復元
# 判定方法: コマンドを ; & | と改行でセグメントに分割し、「セグメント先頭がgitで
# サブコマンドがcheckout/switch」のものだけを検査する(コミットメッセージ等の
# 文中に該当語句が書いてあるだけでは反応しない)。1つでも不正な切り替えがあればブロック

cmd=$(jq -r '.tool_input.command // empty')

current=$(git branch --show-current 2>/dev/null)
deny=0

while IFS= read -r seg; do
  # セグメント先頭がgitで、サブコマンドがcheckout/switchのものだけ検査
  echo "$seg" | grep -qE '^ *git( +-C +[^ ]+)? +(checkout|switch)\b' || continue

  # ファイル復元(git checkout -- <path> / git checkout <ref> -- <path>)は切り替えではないので許可
  echo "$seg" | grep -qE ' -- ' && continue

  # 切り替え先を抽出(-b/-c/--createの後ろ、またはサブコマンド直後の引数)
  target=$(echo "$seg" | sed -nE 's/^ *git( +-C +[^ ]+)? +(checkout|switch) +(-b +|-c +|--create +)?([^ ]+).*/\4/p')

  # mainへの切り替えは許可(マージ後にmainを更新する等の正常フロー)
  [ "$target" = "main" ] && continue

  # mainから新規ブランチを作るのは通常の機能開発の始め方なので許可
  if echo "$seg" | grep -qE '(checkout +-b|switch +-c|switch +--create)' && [ "$current" = "main" ]; then
    continue
  fi

  deny=1
done <<< "$(echo "$cmd" | tr ';&|' '\n')"

[ "$deny" -eq 0 ] && exit 0

# ブロックし、worktreeへ誘導(この理由はClaudeに渡り、自動でworktree作成に切り替わる)
cat <<EOF
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"このディレクトリでのブランチ切り替えは禁止(1 worktree = 1ブランチ運用)。代わりにgit worktreeを作成して作業すること。既存ブランチ: git worktree add ../study-<機能名> <ブランチ名> / 新規ブランチ: git worktree add ../study-<機能名> -b feature/<機能名>。作成後は対象アプリのセットアップ手順(未追跡ファイルのコピー・依存関係のインストール)に従って環境を整える。詳細: .claude/skills/parallel-work/SKILL.md"}}
EOF
