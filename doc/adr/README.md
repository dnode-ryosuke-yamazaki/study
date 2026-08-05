# Architecture Decision Records (ADR)

このディレクトリには、リポジトリ構成やアーキテクチャに関する重要な意思決定を記録します。

## 一覧

| # | タイトル | ステータス |
|---|---|---|
| [0001](0001-multi-app-monorepo-layout.md) | 複数アプリを収容するモノレポ構成への移行 | Accepted |
| [0002](0002-jira-automation-via-github-actions.md) | GitHub ActionsによるJIRAチケット自動更新 | Accepted |

## 書き方

- 1決定 = 1ファイル。ファイル名は `NNNN-短いタイトル.md`（連番は4桁、既存の最大値+1）
- 構成: `ステータス` / `コンテキスト` / `決定` / `影響`
- 決定を覆す場合は既存ファイルを書き換えず、新しいADRを追加してステータスを `Superseded by NNNN` に更新する
