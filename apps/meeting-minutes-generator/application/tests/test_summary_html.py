"""要約部分の抽出とHTML変換(タスク6・タスク12)のテスト。"""

import unittest

import meeting_profile
import summary_html

判定語 = ("デイリー",)
通常の性質 = meeting_profile.見極める("定例会議.vtt", "WEBVTT", 判定語)
デイリーの性質 = meeting_profile.見極める("デイリーMTG.vtt", "WEBVTT", 判定語)

議事録の例 = """# 2026-08-24 定例会議 議事録

## 会議メタ情報

- 会議名: 定例会議
- 日時: 2026-08-24
- 参加者: 山田、佐藤

## 要約

- 進捗を確認し、リリース日を9月1日に決めた。

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

デイリー議事録の例 = """# デイリーMTG 議事録

## 会議メタ情報

- 会議名: デイリーMTG

## 要約

- 各自の進捗を共有し、検証環境の権限不足を課題として確認した。

## 進捗

### 山田

- 作業実績: 議事録生成バッチの実機確認
- 作業予定: TODO起票の要件整理
- 課題: なし

### 佐藤

- 作業実績: API結合テストの環境準備
- 作業予定: 結合テストの実施
- 課題: 検証環境の権限が未付与

## 決定事項

- 権限申請は山田が代行する

## TODO

- 権限申請を出す(担当者候補: 山田)

## 議論の経緯

- 権限申請の窓口について確認した。

## 未決事項・次回議題

- なし
"""


class 要約部分の抽出(unittest.TestCase):
    """フル構成の議事録から、Teamsに投稿する要約部分だけを抜き出せることを検証する。"""

    def setUp(self):
        self.抜粋 = summary_html.要約部分を抽出する(議事録の例, 通常の性質.投稿する見出し)

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


class デイリー系議事録の抽出(unittest.TestCase):
    """デイリー系では進捗が投稿の主役になるため、担当者ごとの小見出しを含む
    進捗セクションがそのまま抜き出せることを検証する。
    """

    def setUp(self):
        self.抜粋 = summary_html.要約部分を抽出する(
            デイリー議事録の例, デイリーの性質.投稿する見出し
        )

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#teamsへの共有-1
    def test_進捗が抜粋に含まれること(self):
        self.assertIn("## 進捗", self.抜粋)
        self.assertIn("### 山田", self.抜粋)
        self.assertIn("作業実績: API結合テストの環境準備", self.抜粋)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#投稿用ファイルの書き出し
    def test_担当者の小見出しでセクションが打ち切られないこと(self):
        """`###` を `##` と同じ扱いにすると、進捗の途中で抽出が止まり
        決定事項・TODOが投稿から丸ごと落ちる。
        """
        self.assertIn("## 決定事項", self.抜粋)
        self.assertIn("## TODO", self.抜粋)
        self.assertIn("権限申請を出す", self.抜粋)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#teamsへの共有-1
    def test_議論の経緯が含まれないこと(self):
        self.assertNotIn("議論の経緯", self.抜粋)


class HTMLへの変換(unittest.TestCase):
    """Teamsはメッセージ本文をHTMLとして解釈しプレーンな改行を無視するため、
    見出し・入れ子リストをHTMLタグに変換することを検証する
    (daily-report-to-teamsで実機確認済みの方式)。
    """

    def setUp(self):
        抜粋 = summary_html.要約部分を抽出する(議事録の例, 通常の性質.投稿する見出し)
        self.html = summary_html.htmlへ変換する(抜粋, "2026-08-24 定例.md")

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#投稿用ファイルの書き出し
    def test_見出しがHTMLの見出しタグになること(self):
        self.assertIn("<h3>決定事項</h3>", self.html)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#投稿用ファイルの書き出し
    def test_担当者の小見出しが1段下の見出しタグになること(self):
        抜粋 = summary_html.要約部分を抽出する(
            デイリー議事録の例, デイリーの性質.投稿する見出し
        )
        html = summary_html.htmlへ変換する(抜粋, "デイリー.md")
        self.assertIn("<h3>進捗</h3>", html)
        self.assertIn("<h4>山田</h4>", html)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#投稿用ファイルの書き出し
    def test_箇条書きがリストタグになり入れ子も保たれること(self):
        self.assertIn("<li>リリースは9月1日とする</li>", self.html)
        self.assertIn("<ul><li>レビューは佐藤</li></ul>", self.html.replace("\n", ""))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/design.md#セキュリティ
    def test_本文中のタグ文字がエスケープされること(self):
        """トランスクリプト由来の文字列(発言内容)がHTMLとして解釈されると
        投稿の体裁が壊れるため、本文はエスケープする。
        """
        html = summary_html.htmlへ変換する("## 要約\n\n<script>を使う話", "a.md")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)


class 議事録全文へのリンク(unittest.TestCase):
    """投稿から議事録全文をクリックで開けることを検証する。

    共有ストレージのファイルを直接指すURLはブラウザ内で表示されずダウンロードに
    なるため、ファイルビューアで開く形式のURLを組み立てる。
    """

    ビューア = "https://example-my.sharepoint.com/personal/me/_layouts/15/onedrive.aspx"
    Webフォルダ = "/personal/me/Documents/00_root/auto/minutes"

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録全文へのリンク-1
    def test_ビューアURLにファイルと親フォルダが含まれること(self):
        url = summary_html.ビューアURLを組み立てる(self.ビューア, self.Webフォルダ, "会議.md")
        self.assertTrue(url.startswith(self.ビューア + "?"))
        self.assertIn("id=%2Fpersonal%2Fme%2FDocuments%2F00_root%2Fauto%2Fminutes%2F", url)
        self.assertIn("parent=%2Fpersonal%2Fme%2FDocuments%2F00_root%2Fauto%2Fminutes", url)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録全文へのリンク-2
    def test_ビューアURLに付いてきたクエリが落とされること(self):
        """設定値はブラウザのアドレスバーからコピーされる前提。落とさないと `?` が二重になる。"""
        url = summary_html.ビューアURLを組み立てる(
            self.ビューア + "?view=1", self.Webフォルダ, "会議.md"
        )
        self.assertEqual(url.count("?"), 1)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録全文へのリンク-2
    def test_エンコード済みのパスが二重にエンコードされないこと(self):
        url = summary_html.ビューアURLを組み立てる(
            self.ビューア, "/personal/me/Shared%20Documents/minutes", "会議.md"
        )
        self.assertIn("Shared%20Documents", url)
        self.assertNotIn("%2520", url)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#teamsへの共有-2
    def test_末尾にファイル名を表示テキストとするリンクが入ること(self):
        リンク = summary_html.議事録へのリンク(self.ビューア, self.Webフォルダ, "会議.md")
        html = summary_html.htmlへ変換する("## 要約\n\n- はい", "会議.md", 全文リンク=リンク)
        self.assertIn('<a href="', html)
        self.assertIn(">会議.md</a>", html)
        self.assertIn("全文", html)

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録全文へのリンク-3
    def test_設定が欠けている場合はリンクを作らないこと(self):
        self.assertIsNone(summary_html.議事録へのリンク("", self.Webフォルダ, "会議.md"))
        self.assertIsNone(summary_html.議事録へのリンク(self.ビューア, "", "会議.md"))

    # 仕様: apps/meeting-minutes-generator/specs/minutes-auto-generation/requirements.md#議事録全文へのリンク-3
    def test_リンクが無い場合はファイル名の案内文になること(self):
        html = summary_html.htmlへ変換する("## 要約\n\n- はい", "会議.md", 全文リンク=None)
        self.assertNotIn("<a href", html)
        self.assertIn("会議.md", html)
        self.assertIn("全文", html)


if __name__ == "__main__":
    unittest.main()
