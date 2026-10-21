# Confluence の応答

このフォルダの fixture は、2026-10-19 に dnode・dxgarage から取った実応答(2026-W41 の週を対象にした検索)を、構造を保って値を置き換えたもの。キーの並び・値の型・入れ子は実応答のまま変えていない。実応答そのもの(`tests/fixtures/_raw/`)は git に入れない。

- `current_user.json`: `GET /wiki/rest/api/user/current` の応答。自分のアカウントIDは `5b10a2844c20165700ede21g`
- `search_version.json`: `GET /wiki/rest/api/content/search`(`expand=version`)の応答。対象の週は 2026-W41。`version.when` は UTC。並びは更新日時の順ではない(実応答と同じ)
  - 1005: 自分が土曜6時30分(日本時間)に直したページ(検索の日付を広げたために入る範囲外)
  - 1003: 自分が金曜17時ちょうどに直したページ(範囲外)
  - 1002: 最後の版が他の人のページ(対象外)
  - 1001: 自分が火曜10時23分(日本時間)に直したページ(範囲内)
  - 1004: 自分が月曜0時ちょうどに直したページ(範囲内)。実応答にある `version.ncsStepVersion` が無い形・`extensions.position` が数値の形の要素を写している(他の4件は `ncsStepVersion` があり `position` が文字列の形)
- `search_empty.json`: 該当するページが無いときの実応答

## 置き換えの規則

- サイト: `example.atlassian.net`。`_links` の URL もこのサイトに直す
- 人: 自分は「利用者A」・`me@example.com`・`5b10a2844c20165700ede21g`、他の人は「利用者B」・`other@example.com`・`712020:00000000-0000-4000-8000-0000000000b2`。同じ人には同じ値を使う。プロフィール画像のパスもこのIDに直す
- ページ: ID は `1001` などの作り物の番号、題名・版のメッセージは作り物の文、スペースは `EXAMPLE`。`ari`・`base64EncodedAri`・`confRev`・`_expandable`・`_links` の中の ID・スペース・題名もこれに合わせて作り直す
- 日時: W41 の範囲の内外の位置づけを保ったまま、作り物の時刻にする。書式(`2026-10-06T01:23:45.678Z`)は実応答のまま。`friendlyWhen` は作り物の日時から作る
- 検索の URL(`_links.self`): 実装が送る CQL を入れ直す
- 残した値: 人や中身を表さない列挙の値(`type`・`status`・`accountType`・`accountStatus`・`locale`・`ncsStepVersionSource`・文字列の `position` など)

## 実物の1件の形を写して足した要素

実応答には次の場面が無かったため、同じ応答の中の実物のページの形を写して値だけ変えた要素を足している。キーの追加・削除・型の変更はしていない。

- 最後の版が他の人のページ(1002): 実応答のページはすべて自分が最後に直したものだった。`version.by` は自分の形を写し、ID・名前・メールを変えた
- 境界ちょうどの時刻(月曜0時ちょうど・金曜17時ちょうど)に直したページ(1003・1004)
