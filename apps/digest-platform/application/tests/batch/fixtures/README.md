# Claude の呼び出しの契約 fixture

`claude -p --output-format json` が標準出力に返す封筒の実応答。`batch/claude.ts` の分類(成功・一時的な失敗・利用枠切れ)の契約テストで使う。**テストを通すために中身を書き換えない**(通らないときは実装か仕様が実物と合っていない)。

| ファイル | 由来 | 確かめた範囲 |
|---|---|---|
| `claude-version.txt` | `claude --version` の実出力 | 2.1.263(`--permission-prompts none` が使える 2.1.259 以降) |
| `claude-ok.json` | 「こんにちは」とだけ答えさせた実応答 | `is_error` が偽、`api_error_status` が null、`result` の最終行が `CLAUDE-CALL-OK` |
| `claude-error.json` | 存在しないモデル名を `--model` に指定した実応答 | `is_error` が真、`api_error_status` が 404、`subtype` は `success` のまま(`subtype` では成否を判定できない) |
| `claude-tools-check.json` | `/etc/hosts` を Read で読ませる指示を `--tools "WebSearch,WebFetch"` 付きで送った実応答 | Read が使えない旨の応答になり、`--tools` の絞り込みがこのMacで効く。警告(MCP サーバーのブロック)は標準エラーに出て、標準出力は JSON だけ |
| `claude-quota.json` | **派生**。`claude-error.json` の `api_error_status` を 429 に、`result` を利用枠切れの文言(`usage limit` を含む)に書き換え、`session_id`・`uuid` を 0 埋めしたもの | 利用枠切れは実機で起こせないため、封筒の形(項目名)だけが実応答由来。文言と 429 は仮定で、実機で利用枠切れに当たったときの封筒を保存して置き換える |

3つの実応答はどれも標準出力をそのまま保存し、`python3 -c 'import json; json.load(open(...))'` で JSON として読めることを確かめた。
