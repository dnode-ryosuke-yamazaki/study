# JIRAチケット自動更新(GitHub Actions連携) タスク分解

> TDDで進める。各タスクは 🔴 Red(失敗するテストを書く) → 🟢 Green(最小実装) → 🔵 Refactor の順で進める。

## セットアップ

- [x] `.github/scripts/jira-sync/`に`package.json`・`tsconfig.json`・テストランナー(vitest)を導入する(テスト対象外、環境構築のみ)

## 1. `extractIssueKey`(ブランチ名からのJIRAキー抽出)

- [x] 🔴 `feature/NMBM-123-add-login`から`NMBM-123`を抽出できることを確認するテストを書く
- [x] 🔴 JIRAキーを含まないブランチ名(例: `feature/add-login`)の場合は`null`を返すことを確認するテストを書く
- [x] 🔴 プロジェクトキーが2種類以上のブランチ(例: `feature/ABC-1-DEF-2-xxx`)では先頭に一致した1件のみを抽出することを確認するテストを書く
- [x] 🟢 `extractIssueKey.ts`を実装する
- [x] 🔵 正規表現・命名を整理する

## 2. `classifyMerge`(仕様承認PR/実装PRの判定)

- [x] 🔴 変更ファイルがすべて`specs/`配下の場合に`spec-only`を返すことを確認するテストを書く
- [x] 🔴 変更ファイルがすべて`apps/*/specs/`配下の場合に`spec-only`を返すことを確認するテストを書く
- [x] 🔴 変更ファイルに1件でもそれ以外のパスが含まれる場合に`implementation`を返すことを確認するテストを書く
- [x] 🟢 `classifyMerge.ts`を実装する
- [x] 🔵 判定ロジックを整理する

## 3. `resolveTransition`(有効な遷移一覧からの遷移解決)

- [x] 🔴 遷移一覧に指定した遷移先ステータス名が含まれる場合、その遷移(id)を返すことを確認するテストを書く
- [x] 🔴 遷移一覧に指定した遷移先ステータス名が含まれない場合、`null`を返すことを確認するテストを書く
- [x] 🟢 `resolveTransition.ts`を実装する
- [x] 🔵 整理する

## 4. `buildComment`(コメント本文組み立て)

- [x] 🔴 PR作成/更新イベント用のコメントに、イベント種別・PRタイトル・URL・変更内容概要・変更ファイル件数が含まれることを確認するテストを書く
- [x] 🔴 PRマージイベント用のコメントに、PRタイトル・URL・変更内容概要が含まれることを確認するテストを書く
- [x] 🟢 `buildComment.ts`を実装する
- [x] 🔵 整理する

## 5. `jiraClient`(JIRA REST API呼び出し)

- [x] 🔴 `addComment`が正しいエンドポイント・認証ヘッダー・ボディでリクエストすることを、HTTPをモックして確認するテストを書く
- [x] 🔴 `getTransitions`が対象チケットの遷移一覧を取得できることを、HTTPをモックして確認するテストを書く
- [x] 🔴 `transitionIssue`が指定した遷移idでリクエストすることを、HTTPをモックして確認するテストを書く
- [x] 🔴 一時的な5xxエラー時に1〜2回リトライした後、最終的に失敗してもエラーをthrowせず失敗を表す結果を返すことを確認するテストを書く
- [x] 🟢 `jiraClient.ts`を実装する
- [x] 🔵 整理する

## 6. `index.ts`(エントリポイント・オーケストレーション)

- [x] 🔴 JIRAキー抽出に失敗した場合、以降の関数(`classifyMerge`/`jiraClient`等)を呼ばずに終了することを、依存関数をモックして確認するテストを書く
- [x] 🔴 JIRA APIトークン(シークレット)が渡っていない場合、処理をスキップして正常終了することを確認するテストを書く(フォークPR対応)
- [x] 🔴 PR作成/更新イベントの場合に、コメント追記と「レビュー中」への遷移試行(存在すれば)を行うことを、依存関数をモックして確認するテストを書く
- [x] 🔴 PRマージイベントの場合に、`classifyMerge`の結果に応じて遷移先ステータス名(「進行中」/「完了」)を切り替えることを、依存関数をモックして確認するテストを書く
- [x] 🔴 JIRA API呼び出しがエラーを返しても、`index.ts`全体としては異常終了(非ゼロ終了コード)しないことを確認するテストを書く
- [x] 🔴 処理開始時にPR番号・イベント種別・抽出したJIRAチケットキー(またはキー抽出失敗)がINFOログとして出力されること、コメント投稿・ステータス遷移の成功/スキップ/失敗が適切なログレベルで出力されることを確認するテストを書く(design.md#ログ)
- [x] 🟢 `index.ts`を実装する
- [x] 🔵 整理する

## 7. ワークフロー定義(テスト対象外・手動確認)

- [x] `.github/workflows/jira-sync.yml`を作成する(`pull_request`の`opened`/`synchronize`/`closed`をトリガーに、他ジョブへの依存を持たない単独ジョブとして`.github/scripts/jira-sync`を実行する)
- [ ] JIRA APIトークンをリポジトリ(または組織)シークレットとして登録する(登録作業自体はユーザー実施)
- [ ] リポジトリのブランチ保護設定(必須ステータスチェック)にjira-syncジョブが含まれていないことを確認する(含まれているとJIRA側の障害がPRマージのブロッカーになってしまうため。登録作業自体はユーザー実施)
- [ ] ドライラン用のテストチケット(またはテスト用JIRAプロジェクト)を使って、実際にPRを作成・更新・マージし、コメント追記・ステータス遷移が意図通り動くことを確認する

## 8. ドキュメント更新

- [x] `.claude/skills/pr/SKILL.md`のブランチ命名規約を`feature/<機能名>` → `feature/<JIRAキー>-<機能名>`に更新する

作業開始時のJIRAチケット確認フロー(`requirement/SKILL.md`・`fix/SKILL.md`への追記)は、study固有のタスクではなくこのPC全体のグローバル方針に基づく対応のため、本specのタスクからは除外した(design.md参照)。グローバル版(`~/.claude/skills/requirement/SKILL.md`・`~/.claude/skills/fix/SKILL.md`)・study版(`.claude/skills/requirement/SKILL.md`・`.claude/skills/fix/SKILL.md`)とも対応済み。
