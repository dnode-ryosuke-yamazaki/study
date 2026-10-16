"""週次レポートの保存と Teams への通知。

HTML をローカルの控えと OneDrive の決まったフォルダに週の名前で保存し、ビューア形式のリンク付きで Teams に知らせる。
保存と通知はそれぞれ10秒あけて3回まで試し、それでも失敗した週は結果として返す(後から自動ではやり直さない)。
実際の OneDrive には書かず一時フォルダで、Teams への通知は偽物に差し替えて確かめる。
"""

import os
import re
import shutil
import stat
import tempfile
import unittest
from datetime import date
from pathlib import Path

from routine_work_finder.report import publish, render_html
from tests.html_support import parse

VIEWER = "https://example-my.sharepoint.com/personal/someone_example_com/_layouts/15/onedrive.aspx"
WEB_DIR = "/personal/someone_example_com/Documents/00_root/auto"
URL_W41 = ("https://example-my.sharepoint.com/personal/someone_example_com/_layouts/15/onedrive.aspx"
           "?id=%2Fpersonal%2Fsomeone_example_com%2FDocuments%2F00_root%2Fauto%2FroutineWorkFinder%2F2026-W41.html"
           "&parent=%2Fpersonal%2Fsomeone_example_com%2FDocuments%2F00_root%2Fauto%2FroutineWorkFinder")
HTML_TEXT = "<!DOCTYPE html><p>週次レポート</p>\n"


class FakeNotifier:
    """Teams への通知の偽物。results の順に、成功(True)・失敗(False)・例外("raise")を返す"""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, skill_name, kind, content):
        self.calls.append((skill_name, kind, content))
        result = self.results.pop(0) if self.results else True
        if result == "raise":
            raise OSError("書き出せない")
        return {"success": result} if result else {"success": False, "reason": "投稿先候補を解決できません"}


class FakeCopy:
    """OneDrive への書き込みの偽物。最初の failures 回は失敗し、そのあとは本物の書き込みをする"""

    def __init__(self, failures):
        self.failures = failures
        self.calls = 0

    def __call__(self, source, dest):
        self.calls += 1
        if self.calls <= self.failures:
            raise OSError(35, "Resource deadlock avoided")
        publish.onedrive_write.copy_file(source, dest)


def fragment_lines(body):
    """通知の本文を HTML 断片として読み、タグの対応を確かめたうえで <br> で分けた行の文字を返す"""
    root = parse(body)
    tags = {element.tag for element in root.iter()} - {"#root"}
    if not tags <= {"br", "a"}:
        raise AssertionError(f"思わぬタグ: {tags}")
    lines, current = [], []
    for child in root.children:
        if getattr(child, "tag", None) == "br":
            lines.append("".join(current))
            current = []
        else:
            current.append(child.text() if hasattr(child, "text") else child)
    lines.append("".join(current))
    return lines


class PublishTestCase(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        self.local_dir = self.folder / "data" / "reports"
        self.onedrive_dir = self.folder / "auto" / "routineWorkFinder"
        (self.folder / "auto").mkdir()
        self.sleeps = []

    def publish(self, week="2026-W41", state="normal", count=3, notifier=None, copy=None, html_text=HTML_TEXT):
        return publish.publish_report(
            html_text, week, state, count, local_dir=self.local_dir, onedrive_dir=self.onedrive_dir,
            viewer=VIEWER, web_dir=WEB_DIR, notifier=notifier or FakeNotifier(True), sleep=self.sleeps.append,
            copy=copy or publish.onedrive_write.copy_file)


class WeekNameTests(unittest.TestCase):
    """週の名前は ISO の週番号。年をまたぐ週は、その週の木曜が属する年の番号になる"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-3
    def test_年をまたぐ週の名前とファイル名(self):
        """否定確認: 年を日付の年のまま使うと落ちる"""
        self.assertEqual(publish.week_name(date(2026, 10, 5)), "2026-W41")
        self.assertEqual(publish.week_name(date(2026, 12, 31)), "2026-W53")
        self.assertEqual(publish.week_name(date(2027, 1, 1)), "2026-W53")
        self.assertEqual(publish.week_name(date(2027, 1, 4)), "2027-W01")
        self.assertEqual(publish.week_name(date(2025, 12, 29)), "2026-W01")
        self.assertEqual(publish.report_file_name("2026-W53"), "2026-W53.html")


class SaveTests(PublishTestCase):
    """ローカルの控えと OneDrive の保存先に週の名前で保存する"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-3
    def test_控えとOneDriveの保存先に週の名前で同じ中身を書く(self):
        """否定確認: OneDrive の保存先のファイル名から週の名前を外すと落ちる"""
        result = self.publish(week="2026-W53")
        local = self.local_dir / "2026-W53.html"
        self.assertEqual(local.read_text(encoding="utf-8"), HTML_TEXT)
        self.assertEqual((self.onedrive_dir / "2026-W53.html").read_text(encoding="utf-8"), HTML_TEXT)
        self.assertEqual(result.local_path, local)
        self.assertTrue(result.saved)
        self.assertFalse(result.save_failed)
        self.assertEqual(stat.S_IMODE(os.stat(self.local_dir).st_mode), 0o700)
        self.assertEqual(self.sleeps, [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-3
    def test_同じ週をもう一度作ると控えも保存先も上書きする(self):
        """否定確認: 2回目の中身を書かずに前の中身を残すと落ちる"""
        self.publish()
        self.publish(html_text="<p>作り直し</p>")
        self.assertEqual((self.local_dir / "2026-W41.html").read_text(encoding="utf-8"), "<p>作り直し</p>")
        self.assertEqual((self.onedrive_dir / "2026-W41.html").read_text(encoding="utf-8"), "<p>作り直し</p>")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-3
    def test_保存に2回失敗しても10秒あけて3回目で書ければ保存できた週になる(self):
        """否定確認: 書き直しの回数を2回までにすると落ちる"""
        copy = FakeCopy(failures=2)
        notifier = FakeNotifier(True)
        result = self.publish(copy=copy, notifier=notifier)
        self.assertTrue(result.saved)
        self.assertEqual(copy.calls, 3)
        self.assertEqual(self.sleeps, [10, 10])
        self.assertEqual(fragment_lines(notifier.calls[0][2])[0], "【定型業務の週次レポート】")
        self.assertEqual(fragment_lines(notifier.calls[0][2])[1], "週: 2026-W41")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-7、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-4
    def test_3回とも保存に失敗したら控えを残し保存に失敗した本文だけを知らせて結果に返す(self):
        """否定確認: 保存に失敗しても基本の本文を送ると落ちる"""
        copy = FakeCopy(failures=3)
        notifier = FakeNotifier(True)
        result = self.publish(copy=copy, notifier=notifier)
        self.assertFalse(result.saved)
        self.assertTrue(result.save_failed)
        self.assertTrue(result.notified)
        self.assertEqual(copy.calls, 3)
        self.assertEqual(self.sleeps, [10, 10])
        self.assertTrue((self.local_dir / "2026-W41.html").exists())
        self.assertEqual(len(notifier.calls), 1)
        self.assertEqual(notifier.calls[0][2], publish.save_failed_body("2026-W41", self.local_dir / "2026-W41.html"))


class ViewerUrlTests(unittest.TestCase):
    """ビューア形式のリンク(議事録の自動生成と同じビューアの基点とWebパスの下の routineWorkFinder)"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-4
    def test_ビューアの基点にファイルとフォルダのパスを付けたリンクになる(self):
        """否定確認: フォルダのパスをエンコードせずに付けると落ちる"""
        self.assertEqual(publish.viewer_url("2026-W41", VIEWER, WEB_DIR), URL_W41)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-4
    def test_アドレスバーから写した設定のクエリとエンコード済みのパスを直す(self):
        """否定確認: ビューアの基点についてきたクエリを落とさないと落ちる"""
        url = publish.viewer_url("2026-W41", VIEWER + "?view=0", "/personal/someone_example_com/Documents/00_root/auto/")
        self.assertEqual(url, URL_W41)
        spaced = publish.build_viewer_url(VIEWER, "/personal/a/Documents/my%20folder", "x.html")
        self.assertIn("parent=%2Fpersonal%2Fa%2FDocuments%2Fmy%20folder", spaced)


class NotificationBodyTests(unittest.TestCase):
    """Teams の通知の本文(HTML 断片。値はエスケープする)"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-4
    def test_基本の本文は週の名前と自動化案の件数とビューア形式のリンク(self):
        """否定確認: リンクの & をエスケープせずに入れると落ちる"""
        body = publish.base_body("2026-W41", "normal", 3, URL_W41)
        self.assertEqual(fragment_lines(body), ["【定型業務の週次レポート】", "週: 2026-W41", "自動化案: 3件", "レポート: 2026-W41.html"])
        link = parse(body).find("a")
        self.assertEqual(link.attrs["href"], URL_W41)
        self.assertEqual(link.text(), "2026-W41.html")
        self.assertIn("&amp;parent=", body)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-4
    def test_状態に合わせて自動化案の行だけを置き換える(self):
        """否定確認: 作成に失敗した行から週の名前を外すと落ちる"""
        expected = {
            "empty": "自動化案: 今週は見つかりませんでした",
            "insufficient": "自動化案: 記録が5時間未満のため作っていません",
            "failed": "自動化案: 作成に失敗しました。チャットで「2026-W41 の定型業務レポートを作り直して」と頼むと作り直せます",
        }
        for state, line in expected.items():
            with self.subTest(state=state):
                lines = fragment_lines(publish.base_body("2026-W41", state, 0, URL_W41))
                self.assertEqual(lines, ["【定型業務の週次レポート】", "週: 2026-W41", line, "レポート: 2026-W41.html"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-4
    def test_リンクがhttpsで始まらないときはリンクにせずファイル名だけを出す(self):
        """否定確認: https で始まるかを確かめずにリンクにすると落ちる"""
        body = publish.base_body("2026-W41", "normal", 1, "javascript:alert(1)")
        self.assertIsNone(parse(body).find("a"))
        self.assertEqual(fragment_lines(body)[-1], "レポート: 2026-W41.html")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-4
    def test_本文全体を置き換える5つの本文は基本の行を出さない(self):
        """否定確認: 保存に失敗した本文の控えの場所をエスケープせずに入れると落ちる"""
        log = "~/Library/Logs/routine-work-finder-report.log"
        local = Path("/Users/someone/Library/Application Support/routine-work-finder/reports/<a&b>/2026-W41.html")
        bodies = {
            "保存に失敗": (publish.save_failed_body("2026-W41", local), [
                "【定型業務の週次レポート】",
                f"2026-W41 のレポートを OneDrive に保存できませんでした。控え: {local}",
                "チャットで「2026-W41 の定型業務レポートを作り直して」と頼むと作り直せます"]),
            "思わぬ失敗": (publish.unexpected_failure_body("2026-W41"), [
                "【定型業務の週次レポート】",
                f"2026-W41 の週次レポートの作成に失敗しました。ログ: {log}",
                "チャットで「2026-W41 の定型業務レポートを作り直して」と頼むと作り直せます"]),
            "思わぬ失敗(週が決まる前)": (publish.unexpected_failure_before_week_body(), [
                "【定型業務の週次レポート】",
                f"週次レポートの作成に失敗しました(対象の週を決める前に止まりました)。ログ: {log}"]),
            "状態のファイルを退避": (publish.state_backed_up_body(Path("/data/report-state.broken-20261009-170003.json")), [
                "【定型業務の週次レポート】",
                "週次レポート係の状態のファイルが読めなかったため退避して続けました。退避先: /data/report-state.broken-20261009-170003.json",
                "同じ週のレポートが重ねて届くことがあります"]),
            "作り直しで記録が0件": (publish.remake_no_records_body("2026-W42"), [
                "【定型業務の週次レポート】",
                "2026-W42 は記録が0件のため作り直せませんでした"]),
        }
        for name, (body, expected) in bodies.items():
            with self.subTest(name=name):
                self.assertEqual(fragment_lines(body), expected)
                self.assertFalse(any(line.startswith(("週: ", "自動化案: ", "レポート: ")) for line in fragment_lines(body)))
        self.assertIn("&lt;a&amp;b&gt;", bodies["保存に失敗"][0])
        self.assertIsNone(re.search(r"\d{4}-W\d{2}", bodies["思わぬ失敗(週が決まる前)"][0]))


class NotifyRetryTests(PublishTestCase):
    """Teams への通知は10秒あけて3回まで送り、後からは送り直さない"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-4
    def test_2回失敗しても3回目で送れれば通知できた週になる(self):
        """否定確認: 共通部品が失敗を返したときを成功に数えると落ちる"""
        notifier = FakeNotifier(False, "raise", True)
        self.assertTrue(publish.send_notification("本文", notifier=notifier, sleep=self.sleeps.append))
        self.assertEqual([call[:2] for call in notifier.calls], [("routine-work-finder", "weekly-report")] * 3)
        self.assertEqual(self.sleeps, [10, 10])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-4、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-7
    def test_3回とも失敗したら通知できなかった週として返し4回目は送らない(self):
        """否定確認: 送る回数を4回にすると落ちる"""
        notifier = FakeNotifier(False, False, False, True)
        result = self.publish(notifier=notifier)
        self.assertTrue(result.saved)
        self.assertFalse(result.notified)
        self.assertEqual(len(notifier.calls), 3)
        self.assertEqual(self.sleeps, [10, 10])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-4
    def test_保存できた週はビューア形式のリンク付きの基本の本文を送る(self):
        """否定確認: 送る本文に自動化案の件数を渡さないと落ちる"""
        notifier = FakeNotifier(True)
        result = self.publish(notifier=notifier, count=2)
        self.assertTrue(result.notified)
        self.assertEqual(result.url, URL_W41)
        self.assertEqual(notifier.calls, [("routine-work-finder", "weekly-report", publish.base_body("2026-W41", "normal", 2, URL_W41))])


class ExclusionsNotInNotificationTests(PublishTestCase):
    """記録しない候補は Teams の通知に載せない"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#記録しない候補の提案-8
    def test_通知の本文に記録しない候補の値と題名が入らない(self):
        """否定確認: 本文にレポートの中身を入れると落ちる"""
        from tests.test_report_render_html import default_exclusions, report_input
        report = report_input()
        html_text = render_html.render_report(report)
        notifier = FakeNotifier(True)
        self.publish(notifier=notifier, html_text=html_text, count=len(report.proposals))
        body = notifier.calls[0][2]
        for item in default_exclusions():
            for key in ("value", "example", "reason", "kind"):
                self.assertNotIn(item[key], body)
        self.assertNotIn("記録しない", body)


if __name__ == "__main__":
    unittest.main()
