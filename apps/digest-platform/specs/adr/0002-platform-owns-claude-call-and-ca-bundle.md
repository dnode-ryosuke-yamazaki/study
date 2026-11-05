# 0002. Claude の起動と CAバンドルの探し方を共通基盤が自前で持つ

## ステータス

Accepted (2026-11-05)。[0001](0001-local-only-platform.md) の「実装言語と置き場所」のうち「Claude の起動・CAバンドルは既存の shell / Python の部品を呼ぶ」を改定する。実行係を Python で書くこと、Teams 投稿に既存の teams-post の投稿先の仕組みを使うことは変えない

## コンテキスト

[0001](0001-local-only-platform.md) は、このMacの既存の自動化と同じ型に乗せるため、外側の実行係・Claude の起動・Teams 投稿・CAバンドルを既存の shell / Python の部品(`~/.claude/skills/create-automation-batch/templates/claude_headless.sh`・`~/.claude/lib/ca_bundle_tls.py` など)で行うとしていた。

batch-runner の設計で次が分かった。

- 既存の部品は運営者個人の `~/.claude/` 配下にあり、study リポジトリの外にある。`apps/digest-platform/` のコードがそこを参照すると、リポジトリだけでは動かず、テストもリポジトリの中で閉じない
- `claude_headless.sh` は macOS 標準の `/bin/bash` 3.2 向けで、Claude の応答の JSON 封筒の分類(利用枠切れの見分け)や実行状態ファイルの読み書きを書くには向かない。アプリのバッチは TypeScript で、Claude の呼び出し(材料の標準入力・封筒の分類・控えの書き出し)はバッチの中の手順なので、shell を挟むと成否の情報が往復で欠ける
- CAバンドルの探し方は「`~/Library/Application Support/ca-bundle/ca-bundle.pem` があればそれ、無ければ `/etc/ssl/cert.pem`」の2段で、写すのに10行かからない

## 決定

- **Claude の起動**: 共通基盤の TypeScript 部品 `apps/digest-platform/application/batch/claude.ts` が `claude -p` を起動する。5アプリのバッチはこの部品だけを使う。既存の `claude_headless.sh`・`~/.claude/lib/claude_headless.py` は呼ばない
- **CAバンドル**: 実行係(Python)が2段の探し方を自分で持ち、バッチへ `NODE_EXTRA_CA_CERTS`・`SSL_CERT_FILE` で渡す。`~/.claude/lib/ca_bundle_tls.py` は import しない
- **型は揃える**: 既存の自動化と同じ考え方(launchd の `StartCalendarInterval`、`mkdir` のロック、成功マーカーによる成否判定、要約ログの行頭 ISO 8601 時刻)は踏襲する。揃えるのは「型」であって「ファイルの参照」ではない
- **変えないもの**: Teams 投稿は既存の teams-post の投稿先の仕組み(OneDrive の監視フォルダ → Power Automate)に乗せる。投稿先の設定はリポジトリの外(`~/.claude/config/`)にあり、これは環境の設定であって部品の参照ではない

## 検討した選択肢

| 選択肢 | 利点 | 欠点・リスク | 結果 |
|---|---|---|---|
| 既存の shell / Python の部品を呼ぶ(0001 の案) | 稼働実績のある部品を使い回せる | リポジトリが `~/.claude/` に依存する。shell(bash 3.2)で封筒の分類が書きにくい。TypeScript のバッチと shell の間で失敗の種類が欠ける | 棄却 |
| 共通基盤が自前の部品を持つ(採用) | リポジトリの中で完結し、テストもリポジトリで閉じる。Claude の呼び出し規約を TypeScript の1部品に集められる | 2段の探し方と呼び出しの規約を1回写す。既存部品の改良が自動では入らない | 採用 |
| `~/.claude/lib` をリポジトリに同梱(コピー)する | 既存部品の型をそのまま持てる | 個人向けの部品(PJプロファイル・Keychain など)が混ざり、要らないものまで抱える | 棄却 |

## 影響

- architecture.md の「採用技術」を、実行係と配信サーバーは Python 3 標準ライブラリ、Claude の起動はバッチ側の TypeScript 部品、CAバンドルは実行係が自前で探す、に書き換える
- batch-runner の design.md の決定事項「CAバンドルの探し方」「Claude の呼び出し部品の置き場所」がこの判断に従う
- 既存の部品の改良(CAバンドルの置き場所の変更など)があったときは、この共通基盤にも手で反映する。置き場所は README に書く
- 将来この判断を見直す場合の再検討先: 共通基盤の部品をリポジトリ横断の共有パッケージに切り出す必要が出たとき(ほかのアプリも `claude -p` を TypeScript から呼ぶようになったとき)

## AI利用記録

| AIが提示した案 | 根拠 | 人の検証 | 結果 |
|---|---|---|---|
| 共通基盤が自前の部品を持ち `~/.claude/lib` を参照しない | リポジトリの外への依存と bash 3.2 の制約 | 仕様レビューで 0001・architecture.md との食い違いが指摘され、運営者が「新ADRで見直す」を選んだ | 採用 |
| design を既存部品を呼ぶ形に戻す | 0001 と architecture.md を変えずに済む | 運営者が選ばなかった | 棄却 |
