# 申し送り

## 完了したこと

- README.md を更新済み:
  - 「ディレクトリ構成」ツリーに `apps/<app-name>/specs/`(architecture.md・adr/・`<feature-name>/`を含む)、リポジトリ直下 `specs/`、`CLAUDE.md`(AGENTS.mdはそのシンボリックリンクである旨の注記付き)を追加
  - specs/の詳しい規約はCLAUDE.mdへのリンクのみ置き、規約本文は二重に書かない
  - 「アプリ一覧」表の「詳細」列を3アプリともREADME.mdに統一し、architecture.mdがあるteams-transcript-fetcher/meeting-minutes-generatorのみ「アーキテクチャ」列にリンクを追加(notes-apiは`-`)
  - 「新しいアプリを追加するときは」の手順に `apps/<app-name>/specs/` の作成と、README.mdへのテスト・lint・buildコマンド記載を追加
- 実際のディレクトリ構成を確認済み(調査結果):
  - `apps/notes-api/`: `infra/`, `application/`, `README.md` のみ。`specs/` ディレクトリは無い
  - `apps/teams-transcript-fetcher/`: `README.md`, `application/`, `specs/architecture.md`, `specs/transcript-auto-fetch/`(requirements/design/tasks), `specs/sync-stall-recovery/`(requirements/design/tasks)
  - `apps/meeting-minutes-generator/`: `README.md`, `application/`, `specs/architecture.md`, `specs/minutes-auto-generation/`(requirements/design/tasks)
  - どのアプリにも `apps/<app-name>/specs/adr/` は実在しない(現時点でアプリ内ADRはゼロ件)
  - リポジトリ直下 `specs/jira-automation/`(requirements.md/design.md/tasks.md/README-dryrun-test.md)が実在。CLAUDE.mdの「特定のappsに属さない横断CI/tooling機能」の例
  - `CLAUDE.md` と `AGENTS.md`(`CLAUDE.md`へのシンボリックリンク)がリポジトリ直下に実在

## 残作業

なし。タスクは完遂した。

## 次の一手

なし(完遂)。

## 判断したこと(人に確認できなかった点)

- **notes-api に `specs/` が無い扱い**: ツリー図には `apps/<app-name>/specs/` を汎用パターンとして載せるが、アプリ一覧表の「アーキテクチャ」列は実在するファイルだけにリンクし、notes-api の行は空欄(`-`)にする。architecture.mdを新規作成する指示は本タスクの範囲外と判断
- **`apps/<app-name>/specs/adr/` の扱い**: 実在するADRディレクトリが1つも無いため、ツリー図では「(任意)」注記付きの汎用パターンとして記載するに留め、実データへのリンクは張らない
- **specs/ 配下の individual feature フォルダ名(例: transcript-auto-fetch)はツリーに列挙しない**: ツリーは構成パターンの説明が目的であり、個別機能名を書くと保守負荷が上がるため `<feature-name>/` のプレースホルダ表記に統一
