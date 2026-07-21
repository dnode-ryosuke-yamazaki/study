#!/bin/bash
# UserPromptSubmitフック: すべてのユーザー入力に「開発作業なら該当する工程Skillを
# 起動してから作業する」というルーティング指示をコンテキストとして注入する。
# 工程の判定はスクリプトの語彙マッチではなくメインスレッドのモデルに任せる
# (日本語の自由入力をスクリプトで分類するのは脆いため、ここでは指示の注入だけを行う)。
# 詳細は .claude/skills/README.md の「ワークフローへの自動ルーティング」を参照。

prompt=$(jq -r '.prompt // empty')

# /で始まる入力はユーザーが工程Skillを明示的に選んでいるため注入しない
case "$prompt" in
  /*) exit 0 ;;
esac

context=$(cat <<'EOF'
【ワークフロー・ルーティング】この依頼が開発作業(機能追加・既存機能の修正・仕様作成・レビュー・指摘対応・PR作成)に該当する場合、必ず該当する工程Skill(.claude/skills/README.md参照)をSkillツールで起動してから作業を始めること。
- 入口の判定: 新しい機能・アプリ → /requirement、既存機能のバグ・小規模改修 → /fix、方針の壁打ち → /consult
- 工程の途中の依頼(「実装して」「レビューして」等)は、そのSkill冒頭の「前提条件」を確認し、前工程の成果物が揃っていなければ上流の工程Skillから始める(要件定義より前にコードを書かない)
- 定期作業(振り返り)はユーザーが `/retrospective` のように明示起動する。自律起動はできないので、ここでは扱わない
- どの工程にも該当しない依頼(質問・調査・説明のみ)はSkillを起動せずそのまま回答してよい
EOF
)

jq -n --arg ctx "$context" '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $ctx}}'
