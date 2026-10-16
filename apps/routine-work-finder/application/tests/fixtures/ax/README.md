# アクセシビリティの実機応答

2026-10-07 に、launchd から起動した確認用プログラム(署名済み・アクセシビリティの一覧でオン)で、前面のアプリごとに読んだ応答。アプリごとに形の違う行だけを残している。

- 題名・シート名は `TITLE`・`SHEET` に置き換え、元の文字数を `length` に残している。role 名は実機の値のまま
- `*Error` と `error` は `AXUIElementCopyAttributeValue` の戻り値(`AXError` の数値)。`0` は成功、`-25212` は値が無い(`kAXErrorNoValue`)、`-25205` はその属性を持たない(`kAXErrorAttributeUnsupported`)
- `sheet` は前面ウィンドウの子(`kAXChildrenAttribute`)から role が `AXTabGroup` のものを探した結果。`selectedTitle` は `kAXTabsAttribute` の中で `kAXValueAttribute` が真のタブの `kAXTitleAttribute`
- `elapsedMs` は1行分の問い合わせの所要ミリ秒。問い合わせごとに1秒の上限を付けて測った値で、合計1秒の打ち切りはかけていない
- VS Code・Teams は、カーソルのある部品(`kAXFocusedUIElementAttribute`)が常に `-25212` で返る
