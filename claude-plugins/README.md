# claude-plugins(ローカルマーケットプレイス `study-plugins`)

個人リポジトリ(study・automations・pj-risk-check)でだけ有効化する Claude Code プラグインの置き場。社内標準の AI 駆動開発ハーネスを使う PJ では登録せず、標準のフェーズ Skill をそのまま使う(分断管理。経緯は `doc/adr/` ではなく個人の差分精査レポートに記録)。

```
claude-plugins/
├── .claude-plugin/marketplace.json   # マーケットプレイス定義(name: study-plugins)
└── plugins/
    └── devflow/                      # 開発フロー一式(呼び名は /devflow:<名前>)
        ├── .claude-plugin/plugin.json
        ├── skills/<名前>/SKILL.md    # 工程Skill 13本
        ├── agents/<名前>.md          # レビューAgent 4体(Agentツールでは devflow:<名前>)
        ├── hooks/                    # hooks.json(SessionStart)と check-implementation-marker.sh(別ブランチ向けの実装中マーカー警告。管理設定下では実行されない)
        ├── dev-flow.md               # 開発フロー共通ルール(specの置き場所・コミット粒度・1工程1セッション。引き継ぎ書式と実現性確認はホームの session-handoff.md / feasibility-check.md)
        ├── test-policy.md            # テストの種類・量・完了条件
        ├── jira-ticket-check.md      # 着手時のJIRAチケット確認
        ├── quality-standards/        # レビューのチェックリスト(base / company の2層。project層は各リポジトリ側)
        ├── lib/spec_layout_check/    # 仕様書の層分け検査スクリプトとそのテスト
        └── evals/                    # promptfoo による Skill の回帰テスト(手元のターミナルで実行)
```

## 登録と有効化(初回・マシンごと)

```bash
claude plugin validate /Users/ryosyamazaki/repo/study/claude-plugins
claude plugin marketplace add /Users/ryosyamazaki/repo/study/claude-plugins
claude plugin install devflow@study-plugins --scope project   # 対象リポジトリで実行(.claude/settings.json の enabledPlugins に記録される)
```

- ローカルディレクトリのマーケットプレイスはコピーされず **in-place で読まれる**。ファイルを編集したら、次のセッション開始または `/reload-plugins` で反映される(`claude plugin update` は不要)
- 有効化はプロジェクト単位(`<repo>/.claude/settings.json` の `"enabledPlugins": {"devflow@study-plugins": true}`)。ユーザー設定(`~/.claude/settings.json`)には書かない。標準ハーネスの PJ で誤って有効化しないため
- Skill 本文からの同梱ファイル参照は `${CLAUDE_PLUGIN_ROOT}/...`(Claude が読み込み時に絶対パスへ展開する)。プラグイン外のホーム側資産(`~/.claude/local-specs/`・`~/.claude/config/agent-routing.json`・`~/.claude/CLAUDE.md` など)は `~/.claude/...` の絶対パスのまま参照する

## 検査とテスト

```bash
cd /Users/ryosyamazaki/repo/study/claude-plugins/plugins/devflow
python3 -m unittest discover -s lib/spec_layout_check/tests -p 'test_*.py'   # 層分け検査と手順書の構造検証
cd evals && npm install && npm run eval -- requirement                         # Skill の回帰テスト(手元のターミナルのみ)
```
