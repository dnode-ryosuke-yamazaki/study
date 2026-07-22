# Claude Code サンドボックスの制限事項

## 概要

このリポジトリを Claude Code（VSCode拡張経由）で操作する際、ツール実行はサンドボックス化されており、組織のセキュリティ制限により一部の操作が実行できない。以下は実際に確認した制限事項と、試したが効果がなかった対処法をまとめたものである。同じ制限に当たるメンバーが再度同じ調査を繰り返さないよう記録する。

検証日: 2026-07-15〜16 / 環境: VSCode拡張（FleetView）経由の Claude Code

## 確認済みの制限事項

### 1. 外部ネットワークへのアクセスが不可

Bashツール等からの外部ネットワークアクセスは既定で全てブロックされている（`github.com` を含む）。以下の操作が失敗する。

- `git push` / `git fetch` など、リモート（GitHub）に対する通信を伴う操作
  - 例: `fatal: unable to access 'https://github.com/...': CONNECT tunnel failed, response 403`
- `gh` CLI によるPR作成・操作（そもそも `gh` 自体が未インストールでもあった）
- 任意URLへの `curl` / WebFetch 相当の取得

### 2. 機密情報が疑われるファイルの読み取りが不可

パターンに一致するファイルは読み取りが拒否される（意図された制限であり、回避を試みるべきではない）。

- `.env`, `.env.*`, `*secret*`, `*password*`, `*credential*`, `*token*`, `*.pem`, `*.key`, `*.pfx`, `*.crt`
- `.ssh`, `.aws`, `.azure`, `.kube`, `.npmrc`, `.pypirc`, `.netrc`, `credentials`, `vault` 配下

### 3. 書き込み可能なパスが限定される

書き込みは `.claude/` の一部・スクラッチパッド・一時ディレクトリなど許可リストに載ったパスのみ可能。それ以外への書き込みは拒否される。

### 4. プロセス情報の取得が不可

`ps aux` などプロセス一覧の取得コマンドは `operation not permitted` で失敗する。

### 5. `/etc/gitconfig` の読み取りが不可

`git` コマンド実行時にシステム全体の gitconfig（`/etc/gitconfig`）へのアクセスが拒否され、`git status` 等が失敗することがある。`GIT_CONFIG_NOSYSTEM=1` を環境変数として渡すことで回避可能（ネットワーク制限とは無関係の別問題）。

### 6. Bash経由での `.claude/skills/` への書き込みが不可（Write/Editツールは可）

Bashツールで `.claude/skills/` 配下に `mkdir` や `touch` を実行すると `Operation not permitted` で失敗する（`.claude/hooks/` や `settings.json` など他の設定系パスも同様に保護対象）。

- 一方、WriteツールやEditツールで同じパスにファイルを作成・編集する操作は成功した。
- ツールによって書き込み制限の掛かり方が異なるため、「Bashで書き込めない = 完全に書き込み不可」ではない点に注意。設定・スキル・フックなど自己書き換えにつながるファイルは、意図的にBash経由の一括操作から保護されている可能性がある。

## 試したが効果がなかった対処（ネットワーク制限について）

以下をすべて試したが、`github.com` へのアクセスは解除されなかった。

1. プロジェクトローカル設定 `.claude/settings.local.json` に `sandbox.network.allowedDomains` で `github.com` / `api.github.com` / `*.githubusercontent.com` を許可
2. ユーザー設定 `~/.claude/settings.json` に同様の設定を追加
3. VSCodeの「Developer: Reload Window」でウィンドウをリロード
4. VSCodeを完全終了してから再起動（2回実施）
5. 組織管理設定ファイル `/Library/Application Support/ClaudeCode/managed-settings.json` の存在確認 → 存在しない（このファイルによる上書きではない）

→ このFleetView/VSCode拡張環境のネットワーク制限は、Claude Code標準のsettings.jsonベースの `sandbox.network.allowedDomains` では解除できない、より外側のレイヤー（組織のネットワーク境界など）で強制されていると考えられる。`dangerouslyDisableSandbox` パラメータも存在するが組織ポリシーで無効化されており使用不可。

## 推奨する運用

ネットワークアクセスを要する操作（`git push`、PR作成、外部APIへのリクエスト等）は、Claude Codeのツール経由ではなく、**手元のターミナル（Terminal.app / iTermなど、サンドボックス外）で手動実行する**。

- push: `git push origin <branch>`
- PR作成: `gh pr create ...`（`gh` 未導入の場合は push 後に表示されるURL、またはGitHub Web UIから作成）

Claude Codeには、ローカルの差分レビュー（`git diff` ベース）や、pushする前のコミット内容の確認など、ネットワーク不要な作業を任せるとよい。

## 備考

- この制限は環境・バージョンによって変わる可能性がある。将来的にネットワークアクセスが解禁された場合は、このドキュメントを更新すること。
- ネットワーク許可設定（`sandbox.network.allowedDomains`）自体は無効ではなかった可能性もあり、単に本環境では別レイヤーの制限が優先されているだけかもしれない。今後 Claude Code や社内環境の更新があった際は再検証すること。
