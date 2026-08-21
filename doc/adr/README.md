# Architecture Decision Records (ADR)

このディレクトリには、**複数アプリにまたがる**技術選定・方針(DB・ホスティング・認証基盤・CI基盤・リポジトリ構成など)の意思決定を記録します。

1つのアプリ内だけで完結する設計判断は、ここではなく `apps/<app-name>/specs/adr/` に置き、**アプリごとに`0001`から**独立して採番します(判断の範囲での使い分け・書き方は `.claude/skills/architecture-workflow/SKILL.md` の「ADRの置き場所」を参照)。

仕様書(requirements.md/design.md/architecture.md)には常に最新仕様だけを書き、変更の経緯・決定理由はこちらのADRに分離します。**ADRは履歴を残す場所、仕様書は現状だけを書く場所**という役割分担です。

## 一覧

| # | タイトル | ステータス |
|---|---|---|
| [0001](0001-multi-app-monorepo-layout.md) | 複数アプリを収容するモノレポ構成への移行 | Accepted |
| [0002](0002-jira-automation-via-github-actions.md) | GitHub ActionsによるJIRAチケット自動更新 | Accepted |

## 書き方

- 1決定 = 1ファイル。ファイル名は `NNNN-短いタイトル.md`（連番は4桁、既存の最大値+1）
- 構成: `ステータス` / `コンテキスト` / `決定` / `影響`
- 決定を覆す場合は既存ファイルを書き換えず、新しいADRを追加してステータスを `Superseded by NNNN` に更新する
