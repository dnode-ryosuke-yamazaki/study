"""週次レポートのHTML。

集計・自動化案・作業の要約・記録しない候補・記録の状態を、モックと同じ並びの1枚のHTMLにする。
どの状態の週(通常・自動化案が0件・記録が足りない週・作成に失敗)でも崩れずに読め、
選んだ自動化案と記録しない候補の依頼文をコピーしてチャットに貼れることを確かめる。
"""

import builtins
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from routine_work_finder import config_store, paths
from routine_work_finder.report import aggregate, render_html
from tests import html_support
from tests.html_support import parse

EXCLUSION_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "exclusion_request.txt"
WEEK = "2026-W41"
MONDAY = datetime.fromisoformat("2026-10-05T00:00:00+09:00")
FRIDAY_17 = datetime.fromisoformat("2026-10-09T17:00:00+09:00")
HOUR = 3600


def jst(text):
    return datetime.fromisoformat(text + "+09:00")


def group(app, title, sheet=None, *starts, lines_each=120):
    """starts の各時刻から5秒ごとに lines_each 行ある作業の組(題名が None なら題名の取れなかった組)"""
    lines = []
    for start in starts:
        first = jst(start)
        lines.extend({"time": first + timedelta(seconds=5 * index)} for index in range(lines_each))
    return aggregate.WorkGroup(app, title, sheet, title_known=title is not None, lines=lines)


def week_aggregate(groups=None, totals=None, gaps=(), title_unavailable=()):
    groups = groups if groups is not None else default_groups()
    totals = totals or {aggregate.WORK: int(31.5 * HOUR), aggregate.MEETING: 6 * HOUR,
                        aggregate.AWAY: int(4.2 * HOUR), aggregate.EXCLUDED: int(0.3 * HOUR)}
    return aggregate.WeekAggregate(totals=totals, groups=list(groups), gaps=list(gaps),
                                   title_unavailable=list(title_unavailable), skipped=0)


def default_groups():
    """候補になる組2つ(c1・c2)と、1回だけの組1つ"""
    return [
        group("Microsoft Excel", "進捗管理.xlsx", "案件一覧", "2026-10-05T09:00:00", "2026-10-06T09:00:00"),
        group("Google Chrome", "SAG ボード - Jira", None, "2026-10-05T10:00:00", "2026-10-07T10:00:00", lines_each=60),
        group("Microsoft PowerPoint", "定例資料.pptx", None, "2026-10-09T11:00:00", lines_each=30),
    ]


def proposal(title, candidate_ids, memo_ids=(), effect="大"):
    return {"title": title, "candidateIds": list(candidate_ids), "memoIds": list(memo_ids), "effect": effect,
            "seen": f"{title}の繰り返しが見えた", "idea": f"{title}を自動にする", "reuse": ["jira-progress"]}


def default_proposals():
    return [
        proposal("JIRAの状態を進捗表へ転記する作業", ["c1"]),
        proposal("ボードの確認", ["c2"], effect="中"),
        proposal("勤怠の通知メールのフォルダ分け", [], ["m1"], effect="小"),
    ]


def default_summaries():
    return [
        {"id": "w1", "summary": "進捗表を更新していた。", "estimated": False,
         "examples": [{"t": "2026-10-05T09:05:00+09:00", "text": "表の中で作業"}]},
        {"id": "w2", "summary": "ボードを見ていた。", "estimated": False, "examples": []},
        {"id": "w3", "summary": "定例資料を作っていた。", "estimated": False,
         "examples": [{"t": "2026-10-09T11:00:00+09:00", "text": "スライドを編集"}]},
    ]


def default_exclusions():
    return [
        {"kind": "給与・賞与", "target": "word", "value": "給与明細", "example": "2026年10月分 給与明細 - 勤怠システム",
         "reason": "給与の明細を表示している画面の題名"},
        {"kind": "私用", "target": "app", "value": "家計簿", "example": "10月の支出",
         "reason": "個人の家計を管理するアプリで、中身がほぼ私用"},
    ]


def default_windows():
    return [
        {"id": "t1", "app": "Google Chrome", "title": "2026年10月分 給与明細 - 勤怠システム", "sheet": None, "totalMinutes": 6},
        {"id": "t2", "app": "家計簿", "title": "10月の支出", "sheet": None, "totalMinutes": 4},
    ]


def status_inputs(**overrides):
    values = dict(
        last_kind="sample", last_time=jst("2026-10-09T16:59:55"),
        recorded_days=[MONDAY.date() + timedelta(days=offset) for offset in range(5)],
        memo_dates=[jst("2026-10-06T10:00:00").date(), jst("2026-10-07T10:00:00").date()],
        config=config_store.ConfigRead("ok", {**config_store.default_config(),
                                              "endsAt": "2026-10-30T18:00:00+09:00"}, None),
        retained_weeks=("2026-W38", "2026-W41"),
    )
    values.update(overrides)
    return render_html.StatusInputs(**values)


def report_input(**overrides):
    values = dict(
        week=WEEK, period_start=MONDAY, period_end=FRIDAY_17, partial=False,
        created_at=jst("2026-10-09T17:00:12"), current_week=False,
        aggregate=week_aggregate(), outcome="generated",
        proposals=default_proposals(), summaries=default_summaries(),
        exclusions=default_exclusions(), exclusion_windows=default_windows(),
        status=status_inputs(), unreadable_sources=[],
    )
    values.update(overrides)
    return render_html.ReportInput(**values)


def render(**overrides):
    return parse(render_html.render_report(report_input(**overrides)))


def section(root, heading_id):
    """見出しの id から、その見出しを持つ section を返す"""
    return root.by_id(heading_id).parent


def kv(root):
    """記録の状態の項目名と値の組"""
    dl = root.by_id("rec")
    terms = [element for element in dl.children if getattr(element, "tag", None) in ("dt", "dd")]
    pairs = {}
    for term, value in zip(terms[0::2], terms[1::2]):
        pairs[term.text().split("(")[0].strip()] = value
    return pairs


def script_of(root):
    found = html_support.scripts(root)
    return "\n".join(found)


def node_eval(root, expression, exec_result=True, clipboard="ok"):
    before = f"var __EXEC = {json.dumps(exec_result)}; var __CLIPBOARD = {json.dumps(clipboard)};\n"
    return html_support.run_node(script_of(root), before, f"console.log(JSON.stringify({expression}));")


@unittest.skipIf(html_support.NODE is None, "node が無い")
class ScriptSyntaxTests(unittest.TestCase):
    """レポートに埋め込んだ JavaScript がブラウザで読める(構文が崩れていない)"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#バックログに積む依頼文-1
    def test_スクリプトが1つ以上ありnodeの構文の検査を通る(self):
        """否定確認: ひな形の script の閉じかっこを1つ消すと落ちる"""
        root = render()
        found = html_support.scripts(root)
        self.assertGreaterEqual(len(found), 1)
        for text in found:
            ok, error = html_support.node_check(text)
            self.assertTrue(ok, error)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#UI/UX要件
    def test_題名にscriptの終わりのタグや山かっこがあってもHTMLもスクリプトも崩れない(self):
        """否定確認: 埋め込むデータの < を崩さずに入れると落ちる"""
        nasty = '</script><script>alert(1)</script><b>太字</b> & "引用"'
        groups = [group("Google Chrome", nasty, None, "2026-10-05T09:00:00", "2026-10-06T09:00:00")]
        root = render(
            aggregate=week_aggregate(groups=groups),
            proposals=[proposal(nasty, ["c1"])],
            summaries=[{"id": "w1", "summary": nasty, "estimated": False, "examples": [{"t": "2026-10-05T09:05:00+09:00", "text": nasty}]}],
            exclusions=[{"kind": "私用", "target": "word", "value": "</script>", "example": nasty, "reason": nasty}],
            exclusion_windows=[{"id": "t1", "app": "Google Chrome", "title": nasty, "sheet": None, "totalMinutes": 6}],
        )
        self.assertEqual(len(root.find_all("script")), 1)
        self.assertEqual([b for b in root.find_all("b") if b.text() == "太字"], [])
        ok, error = html_support.node_check(script_of(root))
        self.assertTrue(ok, error)
        self.assertIn(nasty, root.by_id("h-proposals").parent.text())
        self.assertEqual(node_eval(root, "REPORT.proposals[0].title"), nasty)
        self.assertEqual(node_eval(root, "REPORT.exclusions[0].value"), "</script>")


class WeekStateTests(unittest.TestCase):
    """週の状態(通常・自動化案が0件・記録が足りない週・作成に失敗)は自動化案と作業の要約の結果だけで決まる"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#記録しない候補の提案-6
    def test_記録しない候補を作れなかった週も0件の週も状態は変わらない(self):
        """否定確認: 記録しない候補が無いときに状態を「作成に失敗」にすると落ちる"""
        for exclusions in (None, [], default_exclusions()):
            with self.subTest(exclusions=exclusions):
                self.assertEqual(render_html.week_state("generated", default_proposals()), "normal")
                root = render(exclusions=exclusions)
                self.assertEqual(len(root.find_all("input", **{"data-pick": "proposal"})), 3)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-6、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-7、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-8
    def test_結果と自動化案の件数から4つの状態が決まる(self):
        """否定確認: 自動化案が0件の判定を消すと落ちる"""
        self.assertEqual(render_html.week_state("generated", default_proposals()), "normal")
        self.assertEqual(render_html.week_state("generated", []), "empty")
        self.assertEqual(render_html.week_state("insufficient", []), "insufficient")
        self.assertEqual(render_html.week_state("claudeFailed", []), "failed")


class ProposalAreaTests(unittest.TestCase):
    """自動化案の欄。番号・題名・週の時間・効果の下に、見えた繰り返し・自動化の案・使える仕組みを出す"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#UI/UX要件
    def test_案ごとに番号と題名と週の時間と効果と3つの説明が並ぶ(self):
        """否定確認: 週の時間を候補の時間の合計にせず最初の候補だけにすると落ちる"""
        both = proposal("2つの候補をまとめた案", ["c1", "c2"])
        root = render(proposals=[both, default_proposals()[2]])
        items = section(root, "h-proposals").with_class("proposal")
        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertEqual(first.find("label").text(), "1. 2つの候補をまとめた案")
        self.assertEqual(first.find("label").attrs["for"], "pick-1")
        # c1 は 240行(20分)、c2 は 120行(10分) → 0.5h
        self.assertEqual(first.with_class("hours")[0].text(), "週 0.5h")
        self.assertEqual(first.with_class("effect")[0].text(), "効果 大")
        self.assertIn("big", first.with_class("effect")[0].classes())
        self.assertEqual([dt.text() for dt in first.find_all("dt")], ["見えた繰り返し", "自動化の案", "使える仕組み"])
        self.assertEqual([dd.text() for dd in first.find_all("dd")],
                         ["2つの候補をまとめた案の繰り返しが見えた", "2つの候補をまとめた案を自動にする", "jira-progress"])
        self.assertEqual(items[1].with_class("hours")[0].text(), "週の時間は記録では見えない")
        self.assertIn("small", items[1].with_class("effect")[0].classes())

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-6
    def test_自動化案が0件の週は見つからなかったことと候補になる条件を出す(self):
        """否定確認: 0件のときに空の一覧を出すと落ちる"""
        root = render(proposals=[])
        area = section(root, "h-proposals")
        self.assertEqual([p.text() for p in area.with_class("empty")],
                         ["今週は自動化案になる繰り返しが見つかりませんでした。同じ操作が週2回以上あると候補になります。"])
        self.assertIsNone(root.by_id("copy-btn"))
        self.assertEqual(area.with_class("proposal"), [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-7
    def test_記録が足りない週は作業の時間と5時間の条件を理由に出す(self):
        """否定確認: 理由の時間を記録の合計にすると落ちる"""
        totals = {aggregate.WORK: int(1.2 * HOUR), aggregate.MEETING: 600, aggregate.AWAY: 360, aggregate.EXCLUDED: 0}
        root = render(outcome="insufficient", proposals=[], summaries=[], aggregate=week_aggregate(totals=totals))
        self.assertEqual([p.text() for p in section(root, "h-proposals").with_class("empty")],
                         ["今週の作業の記録が1.2時間しかないため、自動化案は作っていません。作業の記録が5時間以上ある週に作ります。"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-8
    def test_作成に失敗した週は失敗したことと週の名前を添えた作り直しの頼み方を出す(self):
        """否定確認: 失敗の文から週の名前を外すと落ちる"""
        root = render(outcome="claudeFailed", proposals=[], summaries=[])
        errors = section(root, "h-proposals").with_class("error")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].find("b").text(), "自動化案を作れませんでした。")
        self.assertIn("チャットで「2026-W41 の定型業務レポートを作り直して」と頼むと作り直せます。", errors[0].text())
        self.assertIsNone(root.by_id("copy-btn"))


class BacklogRequestTests(unittest.TestCase):
    """選んだ自動化案をバックログに積む依頼文のコピー"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#バックログに積む依頼文-1
    def test_案ごとにチェック欄があり最初はどれも選ばれずコピーのボタンは押せない(self):
        """否定確認: ボタンの disabled を外すと落ちる"""
        root = render()
        boxes = root.find_all("input", **{"data-pick": "proposal"})
        self.assertEqual([box.attrs["id"] for box in boxes], ["pick-1", "pick-2", "pick-3"])
        self.assertEqual([box.attrs["data-number"] for box in boxes], ["1", "2", "3"])
        self.assertTrue(all(box.attrs["type"] == "checkbox" and "checked" not in box.attrs for box in boxes))
        button = root.by_id("copy-btn")
        self.assertIn("disabled", button.attrs)
        self.assertEqual(button.text(), "選んだ案をバックログに積む依頼文をコピー")
        self.assertEqual(root.by_id("copy-status").text(), "積みたい案にチェックを入れてください")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#バックログに積む依頼文-2
    def test_依頼文は週の名前と選んだ案の番号と題名を番号の順に並べPJ名を入れない(self):
        """否定確認: 選んだ順のまま並べると落ちる"""
        expected = ("/backlog 定型業務の週次レポート 2026-W41 の自動化案から、次をバックログに積んでください。\n"
                    "1. JIRAの状態を進捗表へ転記する作業\n"
                    "3. 勤怠の通知メールのフォルダ分け")
        self.assertEqual(render_html.backlog_request_text(WEEK, default_proposals(), [3, 1]), expected)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#バックログに積む依頼文-2
    @unittest.skipIf(html_support.NODE is None, "node が無い")
    def test_ひな形のスクリプトが組み立てる依頼文がPythonの組み立てと一字一句同じ(self):
        """否定確認: スクリプトの依頼文の1行目の句点を消すと落ちる"""
        root = render()
        expected = render_html.backlog_request_text(WEEK, default_proposals(), [3, 1])
        self.assertEqual(node_eval(root, "backlogText(REPORT.week, REPORT.proposals, [3, 1])"), expected)


@unittest.skipIf(html_support.NODE is None, "node が無い")
class CopyFallbackTests(unittest.TestCase):
    """コピーは execCommand → クリップボードの機能 → 手で選ぶ欄の順に試す(会議設定の自動化の選択画面と同じ3段構え)"""

    def copy(self, exec_result, clipboard):
        root = render()
        before = f"var __EXEC = {json.dumps(exec_result)}; var __CLIPBOARD = {json.dumps(clipboard)};\n"
        after = """
var ui = { status: __element("s"), manual: __element("m"), manualText: __element("mt") };
copyWithFallback("依頼文の本文", ui);
setTimeout(function () {
  console.log(JSON.stringify({ status: ui.status.textContent, ok: ui.status.className, manualHidden: ui.manual.hidden,
    manualValue: ui.manualText.value, manualSelected: ui.manualText.selected, clipboard: __clipboardText }));
}, 0);
"""
        return html_support.run_node(script_of(root), before, after)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#バックログに積む依頼文-3
    def test_1段目でコピーできたらコピーしたと案内し手で選ぶ欄は出さない(self):
        """否定確認: 1段目の一時的な入力欄を選択しないまま execCommand を呼ぶと落ちる"""
        result = self.copy(True, "none")
        self.assertEqual(result["clipboard"], "依頼文の本文")
        self.assertEqual(result["status"], "コピーしました。Claude Code のチャット欄に貼ってください")
        self.assertEqual(result["ok"], "status ok")
        self.assertTrue(result["manualHidden"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#バックログに積む依頼文-3
    def test_1段目が使えないときはクリップボードの機能でコピーする(self):
        """否定確認: 2段目を呼ばずに手で選ぶ欄へ進むと落ちる"""
        for exec_result in (False, "throw"):
            with self.subTest(exec_result=exec_result):
                result = self.copy(exec_result, "ok")
                self.assertEqual(result["clipboard"], "依頼文の本文")
                self.assertEqual(result["status"], "コピーしました。Claude Code のチャット欄に貼ってください")
                self.assertTrue(result["manualHidden"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#バックログに積む依頼文-4
    def test_どちらでもコピーできないときは依頼文を選択済みの手で選ぶ欄に出す(self):
        """否定確認: コピーの関数の3段目で手で選ぶ欄を開かないようにすると落ちる"""
        for clipboard in ("denied", "none"):
            with self.subTest(clipboard=clipboard):
                result = self.copy(False, clipboard)
                self.assertIsNone(result["clipboard"])
                self.assertFalse(result["manualHidden"])
                self.assertEqual(result["manualValue"], "依頼文の本文")
                self.assertTrue(result["manualSelected"])
                self.assertEqual(result["status"], "コピーできませんでした")


class ManualCopyAreaTests(unittest.TestCase):
    """コピーできなかったときに手で選ぶ欄"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#バックログに積む依頼文-4
    def test_手で選ぶ欄と案内が最初は隠れた形で置かれている(self):
        """否定確認: 手で選ぶ欄の案内の文を消すと落ちる"""
        root = render()
        for manual_id, text_id in (("manual", "manual-text"), ("ex-manual", "ex-manual-text")):
            with self.subTest(manual_id=manual_id):
                manual = root.by_id(manual_id)
                self.assertIn("hidden", manual.attrs)
                self.assertEqual(manual.with_class("status")[0].text(),
                                 "この画面ではコピーが使えませんでした。下の文を選んでコピーし、Claude Code のチャット欄に貼ってください。")
                textarea = root.by_id(text_id)
                self.assertEqual(textarea.tag, "textarea")
                self.assertIn("readonly", textarea.attrs)
                self.assertIs(textarea.parent, manual)


class ExclusionAreaTests(unittest.TestCase):
    """記録しない候補の欄。選んだ候補を記録の操作Skillに足してもらう依頼文をコピーできる"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#記録しない候補の提案-4
    def test_給与明細のことばと家計簿のアプリを選んだ依頼文が共有のfixtureと末尾の改行まで同じ(self):
        """否定確認: 末尾の改行を付けないと落ちる"""
        expected = EXCLUSION_FIXTURE.read_bytes().decode("utf-8")
        self.assertEqual(render_html.exclusion_request_text(default_exclusions(), [1, 2]), expected)
        self.assertEqual(render_html.exclusion_request_text(default_exclusions(), [2, 1]), expected)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#記録しない候補の提案-4
    @unittest.skipIf(html_support.NODE is None, "node が無い")
    def test_ひな形のスクリプトが組み立てる依頼文も共有のfixtureと同じ(self):
        """否定確認: スクリプトのことばとアプリの見出しを入れ替えると落ちる"""
        root = render()
        expected = EXCLUSION_FIXTURE.read_bytes().decode("utf-8")
        self.assertEqual(node_eval(root, "exclusionText(REPORT.exclusions, [2, 1])"), expected)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#記録しない候補の提案-4、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#UI/UX要件
    def test_候補ごとにチェック欄と種類と当たった題名の例と理由があり最初はボタンを押せない(self):
        """否定確認: 当たった題名の例にアプリ名を添えないと落ちる"""
        root = render()
        area = section(root, "h-excl")
        items = area.with_class("proposal")
        self.assertEqual(len(items), 2)
        self.assertEqual([item.find("label").text() for item in items], ["ことば「給与明細」", "アプリ「家計簿」"])
        self.assertEqual([item.with_class("effect")[0].text() for item in items], ["種類 給与・賞与", "種類 私用"])
        self.assertEqual([[dd.text() for dd in item.find_all("dd")] for item in items], [
            ["2026年10月分 給与明細 - 勤怠システム(Google Chrome)", "給与の明細を表示している画面の題名"],
            ["10月の支出(家計簿)", "個人の家計を管理するアプリで、中身がほぼ私用"],
        ])
        boxes = area.find_all("input", **{"data-pick": "exclusion"})
        self.assertEqual([box.attrs["id"] for box in boxes], ["ex-1", "ex-2"])
        self.assertTrue(all("checked" not in box.attrs for box in boxes))
        button = root.by_id("ex-copy-btn")
        self.assertIn("disabled", button.attrs)
        self.assertEqual(button.text(), "選んだ候補を記録しないものに足す依頼文をコピー")
        self.assertIs(root.by_id("ex-manual").parent, area.by_id("excl-area"))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#UI/UX要件
    def test_欄は週の合計と自動化案と時間の使い方のあと記録の状態の前に並ぶ(self):
        """否定確認: 記録しない候補の欄を記録の状態の後ろに置くと落ちる"""
        root = render()
        headings = [h2.attrs.get("id") for h2 in root.find_all("h2")]
        self.assertEqual(headings, ["h-proposals", "h-time", "h-excl", "h-rec"])
        self.assertIsNotNone(root.find("header").by_id("totals"))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#UI/UX要件
    def test_候補が0件の週はありませんと出しチェック欄もボタンも置かない(self):
        """否定確認: 0件のときに空の一覧とボタンを出すと落ちる"""
        root = render(exclusions=[])
        area = section(root, "h-excl")
        self.assertEqual([p.text() for p in area.with_class("empty")], ["今週は記録しない候補はありません。"])
        self.assertIsNone(root.by_id("ex-copy-btn"))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#記録しない候補の提案-6
    def test_候補を作れなかった週は作れなかったことだけを出しほかの欄はそのまま(self):
        """否定確認: 作れなかったときに自動化案の欄まで消すと落ちる"""
        root = render(exclusions=None)
        area = section(root, "h-excl")
        errors = area.with_class("error")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].find("b").text(), "記録しない候補を作れませんでした。")
        self.assertIsNone(root.by_id("ex-copy-btn"))
        self.assertEqual(len(section(root, "h-proposals").with_class("proposal")), 3)


class ReadOnlyTests(unittest.TestCase):
    """週次レポート係は記録のファイルと設定ファイルを読むだけで書き換えない"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#記録しない候補の提案-5
    def test_記録の状態の材料を読んでも記録と設定とメモのファイルは変わらない(self):
        """否定確認: 読むときに設定ファイルを書き込みで開くと落ちる"""
        with tempfile.TemporaryDirectory() as folder:
            data = paths.DataPaths(folder)
            data.records.mkdir()
            data.memos.mkdir()
            record = data.records / "2026-10-06.jsonl"
            record.write_text(json.dumps({"t": "2026-10-06T09:00:00+09:00", "kind": "sample", "app": "Code"}) + "\n", encoding="utf-8")
            memo = data.memos / "2026-10-06.jsonl"
            memo.write_text(json.dumps({"id": "20261006-100000-ab12", "t": "2026-10-06T10:00:00+09:00", "text": "メモ"}) + "\n", encoding="utf-8")
            config_store.write_config(data, config_store.default_config())
            files = [record, memo, data.config]
            before = {path: (path.read_bytes(), os.stat(path).st_mtime_ns) for path in files}
            real_open = builtins.open
            real_os_open = os.open

            def read_only_open(file, mode="r", *args, **kwargs):
                if any(flag in mode for flag in "wax+"):
                    raise AssertionError(f"書き込みで開いた: {file}")
                return real_open(file, mode, *args, **kwargs)

            def read_only_os_open(path, flags, *args, **kwargs):
                if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC):
                    raise AssertionError(f"書き込みで開いた: {path}")
                return real_os_open(path, flags, *args, **kwargs)

            with mock.patch("builtins.open", read_only_open), mock.patch("os.open", read_only_os_open):
                inputs = render_html.read_status_inputs(data, MONDAY, FRIDAY_17)
            self.assertEqual(inputs.config.state, "ok")
            self.assertEqual(len(inputs.memo_dates), 1)
            self.assertEqual({path: (path.read_bytes(), os.stat(path).st_mtime_ns) for path in files}, before)


class TimeUsageTests(unittest.TestCase):
    """時間の使い方の上位10件。各行を押すと作業の要約・主な時間帯・具体例・対応する自動化案が開く"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#作業の要約-4、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#UI/UX要件
    def test_行に要約と主な時間帯と日時付きの具体例と対応する自動化案へのリンクが出る(self):
        """否定確認: リンク先の番号を候補の番号のまま出すと落ちる"""
        proposals = [proposal("ボードの確認", ["c2"]), proposal("転記", ["c1"])]
        root = render(proposals=proposals)
        rows = root.by_id("bars").find_all("details")
        self.assertEqual(len(rows), 3)
        first = rows[0]
        self.assertEqual(first.with_class("name")[0].text(), "Microsoft Excel 進捗管理.xlsx — 案件一覧")
        self.assertEqual(first.with_class("h")[0].text(), "0.3h")
        self.assertEqual(first.with_class("bsum")[0].text(), "進捗表を更新していた。")
        detail = {dt.text(): dd for dt, dd in zip(first.find_all("dt"), first.find_all("dd"))}
        self.assertEqual(detail["主な時間帯"].text(), "月 09:00-09:10、火 09:00-09:10")
        self.assertEqual([li.text() for li in detail["具体例"].find_all("li")], ["表の中で作業(10/5 9:05)"])
        link = detail["自動化案"].find("a")
        self.assertEqual(link.attrs["href"], "#pick-2")
        self.assertEqual(link.text(), "案2「転記」")
        third = {dt.text(): dd for dt, dd in zip(rows[2].find_all("dt"), rows[2].find_all("dd"))}
        self.assertEqual(third["自動化案"].text(), "なし")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#自動化案-8、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#UI/UX要件
    def test_記録が足りない週と作成に失敗した週は要約と具体例の代わりに理由を出す(self):
        """否定確認: 失敗した週でも要約の欄に応答の文を出すと落ちる"""
        for outcome in ("insufficient", "claudeFailed"):
            with self.subTest(outcome=outcome):
                root = render(outcome=outcome, proposals=[], summaries=default_summaries())
                first = root.by_id("bars").find_all("details")[0]
                self.assertEqual(first.with_class("bsum")[0].text(),
                                 "この週は作業の要約を作っていません(自動化案の欄の理由と同じ)。時間帯だけを出しています。")
                detail = {dt.text(): dd for dt, dd in zip(first.find_all("dt"), first.find_all("dd"))}
                self.assertEqual(detail["主な時間帯"].text(), "月 09:00-09:10、火 09:00-09:10")
                self.assertEqual([li.text() for li in detail["具体例"].find_all("li")], ["(要約を作っていないため出していません)"])
                self.assertEqual(detail["自動化案"].text(), "なし")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-5
    def test_題名が取れなかった組は題名の代わりに取れなかったことを出す(self):
        """否定確認: 題名が無い組の名前を空のまま出すと落ちる"""
        groups = [group("Google Chrome", None, None, "2026-10-07T13:10:00")]
        root = render(aggregate=week_aggregate(groups=groups), proposals=[],
                      summaries=[{"id": "w1", "summary": "推定です。", "estimated": True, "examples": []}])
        self.assertEqual(root.by_id("bars").with_class("name")[0].text(), "Google Chrome (題名が取れませんでした)")


class HeadingTests(unittest.TestCase):
    """見出しの「対象: 期間 ／ 作成: 日時」と週の合計"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#UI/UX要件
    def test_金曜17時の週は月曜から金曜までを対象として出す(self):
        """否定確認: 終わりの日を金曜17時ではなく作成の日にすると落ちる"""
        root = render(created_at=jst("2026-10-12T08:00:00"))
        self.assertEqual(root.by_id("period").text(), "対象: 2026年10月5日(月)〜10月9日(金) ／ 作成: 10月12日(月) 08:00")
        self.assertEqual(root.find("title").text(), "定型業務レポート 2026-W41")
        self.assertEqual(root.with_class("eyebrow")[0].text(), "2026-W41 ・ 定型業務レポート")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作り直し-4
    def test_今の週を途中で作り直したときは頼んだ日時までを途中までの記録として出す(self):
        """否定確認: 金曜17時より後に頼んだ依頼も途中までにすると落ちる"""
        end, partial = render_html.report_period_end(MONDAY, jst("2026-10-07T14:30:00"))
        self.assertEqual((end, partial), (jst("2026-10-07T14:30:00"), True))
        self.assertEqual(render_html.report_period_end(MONDAY, jst("2026-10-10T09:00:00")), (FRIDAY_17, False))
        self.assertEqual(render_html.report_period_end(MONDAY, FRIDAY_17), (FRIDAY_17, False))
        root = render(period_end=end, partial=partial, created_at=jst("2026-10-07T14:32:10"), current_week=True)
        self.assertEqual(root.by_id("period").text(),
                         "対象: 2026年10月5日(月)〜10月7日(水) 14:30(途中までの記録) ／ 作成: 10月7日(水) 14:32")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-1、apps/routine-work-finder/specs/weekly-automation-report/requirements.md#UI/UX要件
    def test_週の合計に作業と会議と離席と記録しなかった時間を時間の単位で出す(self):
        """否定確認: 記録しなかった時間を合計から外すと落ちる"""
        root = render()
        spans = root.by_id("totals").find_all("span")
        self.assertEqual([span.text() for span in spans],
                         ["作業 31.5時間", "会議 6.0時間", "離席 4.2時間", "記録しなかった時間 0.3時間"])
        self.assertEqual(len(root.by_id("split").find_all("span")), 4)


class RecordStatusTests(unittest.TestCase):
    """記録の状態。終わりの日時はその週の記録の最後の停止の行から取り、過去の週では今の設定を使わない"""

    def write_lines(self, data, day, lines):
        data.records.mkdir(exist_ok=True)
        with open(data.records / f"{day}.jsonl", "a", encoding="utf-8") as file:
            for line in lines:
                file.write(json.dumps(line) + "\n")

    def status_from(self, lines, current_week=False, config=None):
        with tempfile.TemporaryDirectory() as folder:
            data = paths.DataPaths(folder)
            for line in lines:
                self.write_lines(data, line["t"][:10], [line])
            if config is not None:
                config_store.write_config(data, config)
            inputs = render_html.read_status_inputs(data, MONDAY, FRIDAY_17)
        return kv(render(status=inputs, current_week=current_week))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-6
    def test_週の途中で記録が終わった週は最後の停止の行の時刻を終わった日時として出し理由は出さない(self):
        """否定確認: 最後の停止の行の時刻ではなく今の設定の終わりの日時を出すと落ちる"""
        lines = [{"t": "2026-10-08T17:59:55+09:00", "kind": "sample", "app": "Code"},
                 {"t": "2026-10-08T18:00:00+09:00", "kind": "stop", "reason": "endsAtPassed"}]
        state = self.status_from(lines, config={**config_store.default_config(), "endsAt": "2026-10-30T18:00:00+09:00"})["状態"]
        self.assertEqual(state.with_class("pill")[0].text(), "終了")
        self.assertIn("off", state.with_class("pill")[0].classes())
        self.assertEqual(state.text(), "終了 10月8日(木) 18:00 に終わりました")
        self.assertNotIn("endsAtPassed", state.text())

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-6
    def test_過去の週で最後の行が停止でなければこの週のあとも続けていたと出し今の設定の予定は出さない(self):
        """否定確認: 過去の週でも今の設定の終わりの日時を出すと落ちる"""
        lines = [{"t": "2026-10-09T16:59:55+09:00", "kind": "sample", "app": "Code"}]
        state = self.status_from(lines, config={**config_store.default_config(), "endsAt": "2026-10-30T18:00:00+09:00"})["状態"]
        self.assertEqual(state.text(), "記録中(この週のあとも記録を続けていました)")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-6
    def test_停止の行のあとに開始の行がある週は記録中になる(self):
        """否定確認: 範囲の中に停止の行が1つでもあれば終了にすると落ちる"""
        lines = [{"t": "2026-10-06T12:00:00+09:00", "kind": "stop", "reason": "stopRequested"},
                 {"t": "2026-10-06T13:00:00+09:00", "kind": "start"},
                 {"t": "2026-10-06T13:00:05+09:00", "kind": "sample", "app": "Code"}]
        state = self.status_from(lines)["状態"]
        self.assertEqual(state.with_class("pill")[0].text(), "記録中")
        self.assertNotIn("off", state.with_class("pill")[0].classes())

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-6
    def test_今の週だけ今の設定の終わりの日時を予定として添える(self):
        """否定確認: 今の週でも設定の終わりの日時を出さないようにすると落ちる"""
        lines = [{"t": "2026-10-07T14:00:00+09:00", "kind": "sample", "app": "Code"}]
        state = self.status_from(lines, current_week=True,
                                 config={**config_store.default_config(), "endsAt": "2026-10-30T18:00:00+09:00"})["状態"]
        self.assertEqual(state.text(), "記録中 10月30日(金) 18:00 に終わります")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-8
    def test_設定ファイルが無いときは異常を出さず記録しないアプリの初期値を出し予定は出さない(self):
        """否定確認: 無いときを読めないときと同じ扱いにすると落ちる"""
        lines = [{"t": "2026-10-07T14:00:00+09:00", "kind": "sample", "app": "Code"}]
        status = self.status_from(lines, current_week=True)
        self.assertEqual(status["状態"].text(), "記録中")
        self.assertEqual(status["記録しないアプリ"].text(), "パスワード・キーチェーンアクセス・システム設定")
        self.assertEqual(status["記録しないことば"].text(), "なし")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#レポートの作成と通知-8
    def test_設定ファイルが読めないときは読めないと出し一覧と予定は出さない(self):
        """否定確認: 読めないときに初期値の一覧を出すと落ちる"""
        unreadable = config_store.ConfigRead("unreadable", None, "invalidJson")
        status = kv(render(status=status_inputs(config=unreadable), current_week=True))
        self.assertEqual(status["状態"].text(), "記録中 設定ファイルが読めないため、終わりの予定は出していません")
        self.assertEqual(status["記録しないアプリ"].text(), "設定ファイルが読めない")
        self.assertEqual(status["記録しないことば"].text(), "設定ファイルが読めない")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#UI/UX要件
    def test_記録時間とメモの件数と記録しないことばと残しているデータの範囲を出す(self):
        """否定確認: 残しているデータの週の数を1少なく数えると落ちる"""
        config = {**config_store.default_config(), "excludedTitleWords": ["給与", "評価"]}
        status = kv(render(status=status_inputs(config=config_store.ConfigRead("ok", config, None)), current_week=False))
        self.assertEqual(status["この週の記録"].text(), "42.0時間(5日間)")
        self.assertEqual(status["面倒だった作業のメモ"].text(), "2件(10月6日・10月7日)")
        self.assertEqual(status["記録しないことば"].text(), "給与・評価")
        self.assertEqual(status["残しているデータ"].text(), "2026-W38〜W41 の4週間分(それより古い週は消しています)")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#UI/UX要件
    def test_年をまたいで残しているデータの範囲は両方の年を出す(self):
        """否定確認: 年をまたいでも後ろの年を省くと落ちる"""
        status = kv(render(status=status_inputs(retained_weeks=("2025-W52", "2026-W02"))))
        self.assertEqual(status["残しているデータ"].text(), "2025-W52〜2026-W02 の3週間分(それより古い週は消しています)")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#時間の集計-6
    def test_記録が取れなかった時間帯と合計と題名が取れなかった時間を出す(self):
        """否定確認: 記録が取れなかった時間の合計を出さないと落ちる"""
        gaps = [(jst("2026-10-07T12:05:00"), jst("2026-10-07T12:55:00")),
                (jst("2026-10-08T18:00:00"), jst("2026-10-09T08:30:00"))]
        unavailable = [{"app": "Google Chrome", "reason": "timeout", "seconds": 1800}]
        status = kv(render(aggregate=week_aggregate(gaps=gaps, title_unavailable=unavailable)))
        lost = status["取れなかった時間"]
        lines = [element.text() for element in lost.with_class("warnline")]
        self.assertEqual(lines, ["記録が取れなかった時間: 合計 15.3時間(Macのスリープなど)",
                                 "題名が取れなかった時間: Google Chrome 0.5時間(アプリから応答なし。アプリ名だけ記録)"])
        self.assertEqual([li.text() for li in lost.find_all("li")],
                         ["10月7日(水) 12:05〜12:55", "10月8日(木) 18:00〜10月9日(金) 08:30"])
        none = kv(render(aggregate=week_aggregate()))["取れなかった時間"]
        self.assertEqual(none.text(), "なし")

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-5
    def test_読めなかった既存の作業の記録の名前とサイトと理由を出す(self):
        """否定確認: サイトの名前を出さないと落ちる"""
        failures = [{"source": "confluence", "site": "example.atlassian.net", "reason": "auth"},
                    {"source": "minutes", "site": None, "reason": "missing"}]
        status = kv(render(unreadable_sources=failures))
        self.assertEqual([element.text() for element in status["読めなかった記録"].with_class("warnline")], [
            "Confluence(example.atlassian.net): 認証に失敗したため、この週の Confluence の編集は使わずに作りました",
            "議事録: 議事録の控えのフォルダが見つからないため、この週の議事録は使わずに作りました",
        ])
        partial = [{"source": "jira", "site": "example.atlassian.net", "reason": "request", "status": 400},
                   {"source": "confluence", "site": "example.atlassian.net", "reason": "truncated"}]
        status = kv(render(unreadable_sources=partial))
        self.assertEqual([element.text() for element in status["読めなかった記録"].with_class("warnline")], [
            "JIRA(example.atlassian.net): 検索が受け付けられなかったため、この週の JIRA の更新は使わずに作りました",
            "Confluence(example.atlassian.net): 件数の上限で打ち切られ、この週の Confluence の編集の一部を読めていない恐れがあります。"
            "読めた分で作りました",
        ])
        ok = kv(render(unreadable_sources=[]))["読めなかった記録"]
        self.assertEqual(ok.text(), "なし(JIRA・Confluence・Claude Code の会話・議事録をすべて読めました)")


if __name__ == "__main__":
    unittest.main()
