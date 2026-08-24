"""要約部分の抽出とHTML変換(タスク6)のテスト。"""

import unittest

import summary_html

議事録の例 = """# 2026-08-24 定例会議 議事録

## 会議メタ情報

- 会議名: 定例会議
- 日時: 2026-08-24
- 参加者: 山田、佐藤

## 要約

進捗確認を行い、リリース日を決めた。

## 決定事項

- リリースは9月1日とする

## TODO

- リリース手順書を書く(担当者候補: 山田)
  - レビューは佐藤

## 議論の経緯

- リリース日について、9月1日案と9月8日案が出て、9月1日に着地した。

## 未決事項・次回議題

- なし
"""


class 要約部分の抽出(unittest.TestCase):
    """フル構成の議事録から、Teamsに投稿する要約部分だけを抜き出せることを検証する。"""

    def setUp(self):
        self.抜粋 = summary_html.要約部分を抽出する(議事録の例)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#teamsへの共有-1
    def test_会議メタ情報と要約と決定事項とTODOが含まれること(self):
        for 見出し in ("会議メタ情報", "要約", "決定事項", "TODO"):
            self.assertIn(f"## {見出し}", self.抜粋)
        self.assertIn("リリースは9月1日とする", self.抜粋)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#teamsへの共有-1
    def test_議論の経緯と未決事項次回議題が含まれないこと(self):
        self.assertNotIn("議論の経緯", self.抜粋)
        self.assertNotIn("未決事項", self.抜粋)
        self.assertNotIn("9月8日案", self.抜粋)


class HTMLへの変換(unittest.TestCase):
    """Teamsはメッセージ本文をHTMLとして解釈しプレーンな改行を無視するため、
    見出し・入れ子リストをHTMLタグに変換することを検証する
    (daily-report-to-teamsで実機確認済みの方式)。
    """

    def setUp(self):
        抜粋 = summary_html.要約部分を抽出する(議事録の例)
        self.html = summary_html.htmlへ変換する(抜粋, "2026-08-24 定例.md")

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#投稿用ファイルの書き出し
    def test_見出しがHTMLの見出しタグになること(self):
        self.assertIn("<h3>決定事項</h3>", self.html)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#投稿用ファイルの書き出し
    def test_箇条書きがリストタグになり入れ子も保たれること(self):
        self.assertIn("<li>リリースは9月1日とする</li>", self.html)
        self.assertIn("<ul><li>レビューは佐藤</li></ul>", self.html.replace("\n", ""))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#teamsへの共有-2
    def test_末尾に全文の置き場所を案内する一文が入ること(self):
        self.assertIn("2026-08-24 定例.md", self.html)
        self.assertIn("全文", self.html)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#セキュリティ
    def test_本文中のタグ文字がエスケープされること(self):
        """トランスクリプト由来の文字列(発言内容)がHTMLとして解釈されると
        投稿の体裁が壊れるため、本文はエスケープする。
        """
        html = summary_html.htmlへ変換する("## 要約\n\n<script>を使う話", "a.md")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()
