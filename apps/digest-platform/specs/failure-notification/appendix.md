# 失敗通知 付録(書式)

## 本文

投稿用ファイル `<投稿先フォルダ>/post-<YYYYMMDD-HHMMSS>[-<連番2〜1000>].txt`(UTF-8。中身は HTML断片)。

失敗のとき:

```html
<b>【失敗】news-digest</b><br>ジョブ: 記事公開 2026-11-06<br>失敗日時: 2026-11-06 06:42<br>ログ: ~/Library/Application Support/digest/news-digest/logs/publish/2026-11-06-1.log
```

警告のとき:

```html
<b>【警告】news-digest</b><br>ジョブ: 記事公開 2026-11-06(公開は成功、新着の送り出しに失敗)<br>失敗日時: 2026-11-06 06:42<br>ログ: ~/Library/Application Support/digest/news-digest/logs/publish/2026-11-06-1.log
```

| 部分 | 中身 |
|---|---|
| 件名 | `<b>【失敗】<アプリ名></b>`。確定の理由が `warning` なら `【警告】` |
| ジョブ | `ジョブ: <系統の日本語名> <配信日>[ <編>]`。系統の日本語名は `publish`→記事公開、`review`→月次見直し。編が `null` なら付けない。編は識別子をそのまま書く |
| 警告の定型句 | 確定の理由が `warning` のとき、ジョブの末尾に `(公開は成功、新着の送り出しに失敗)` |
| 失敗日時 | `失敗日時: <YYYY-MM-DD HH:MM>`(日本時間) |
| ログ | `ログ: <ログのパス>`。ホームフォルダで始まるときは `~` に置き換える。リンクにしない |

- 行の区切りは `<br>`。改行文字は入れない
- 件名以外の値はすべて `html.escape` をかけてから埋める
- 上の例の値はダミー

## 投稿先の設定

`~/.claude/config/project-profiles.json` のうち読むところ(teams-post と同じ):

```json
{
  "user": {
    "teams": {
      "destinations": {
        "Digest監視": {
          "folder_path": "<監視スレッドの投稿先フォルダの絶対パス>",
          "channel_type": "private"
        }
      }
    }
  }
}
```

- 表示名 `Digest監視` の `folder_path` だけを使う。`channel_type` は読まない

## 宣言の条目

`~/.claude/config/automation-health-check.json` の `jobs` に足す条目。項目の意味は日次ヘルスチェックの README「宣言の項目(1ジョブ)」が正。

毎日のアプリの記事公開:

```json
{
  "name": "digest news-digest 記事公開",
  "label": "com.example.digest-news-digest-publish",
  "description": "news-digest の記事を作って公開する(失敗すると監視スレッドに届く)",
  "trigger": {"type": "calendar", "times": ["06:30", "10:30", "14:30", "18:30"]},
  "evidence": {
    "format": "log",
    "path": "~/Library/Application Support/digest/news-digest/runner-publish.log",
    "doneMarker": "RUN-SUCCEEDED",
    "failureMarkers": ["RUN-FAILED"]
  }
}
```

週1回のアプリの記事公開と全アプリの月次見直し(上との違いだけ):

```json
{
  "name": "digest research-digest 月次見直し",
  "label": "com.example.digest-research-digest-review",
  "description": "research-digest の月次見直し案を作る(毎月<日>日)",
  "trigger": {"type": "calendar", "times": ["07:30"]},
  "notAlwaysScheduled": true,
  "_notAlwaysScheduledComment": "配信曜日・見直しの日にしか動かないため、日々の稼働判定はしない",
  "evidence": {
    "format": "log",
    "path": "~/Library/Application Support/digest/research-digest/runner-review.log",
    "doneMarker": "RUN-SUCCEEDED",
    "failureMarkers": ["RUN-FAILED"]
  }
}
```

- `label` は `make_plists.label(<アプリ名>, <系統>)` の値
- `times` は記事公開なら 06:30・10:30・14:30・18:30、月次見直しなら 07:30(`make_plists.py` の起動時刻と同じ)
- `_notAlwaysScheduledComment` は既存の条目(夜間バッチなど)と同じく `_` で始まる注記のキーで、日次ヘルスチェックは読まない。宣言ファイルを開いた人に印を付けた理由を伝えるために置く
- 週1回のアプリの記事公開の `description` は「<アプリ名> の記事を作って公開する(<曜日>曜日)」

## 宣言の生成スクリプトの使い方

```
python3 launchd/make_health_declarations.py            # 条目を標準出力に出すだけ
python3 launchd/make_health_declarations.py --apply    # 宣言ファイルへ反映する
```

- 作業フォルダは `apps/digest-platform/application`
- `--apply` の控えは `~/.claude/config/automation-health-check.json.bak-<YYYYMMDD-HHMMSS>`
- 反映の対象は `label` が `com.example.digest-` で始まる条目だけ
