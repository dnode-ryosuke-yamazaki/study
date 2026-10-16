"""週次レポートが、全PJのサイトから JIRA の自分の更新と Confluence の自分の編集を読む(契約)

チケットとページの作業を作業の要約と自動化案の材料にするため、その週に自分が変えた分だけを
日本時間の月曜0時〜金曜17時で取り出す。読めなかったサイトはレポートを止めずに控える。
"""

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

from routine_work_finder.report import sources_atlassian

# 共通部品(~/.claude/lib)は読み込み先の場所を足したあとの sources_atlassian から借りる
client = sources_atlassian.client

JST = timezone(timedelta(hours=9))
FIXTURES = Path(__file__).resolve().parent / "fixtures"
WEEK_START = datetime(2026, 10, 5, 0, 0, tzinfo=JST)
WEEK_END = datetime(2026, 10, 9, 17, 0, tzinfo=JST)

MYSELF = "/rest/api/3/myself"
JIRA_SEARCH = "/rest/api/3/search/jql"
CURRENT_USER = "/wiki/rest/api/user/current"
CONFLUENCE_SEARCH = "/wiki/rest/api/content/search"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def jst(text):
    return datetime.fromisoformat(text + "+09:00")


def profiles(*entries):
    """PJプロファイルの形(PJ名 → atlassian 区分)。entries は (PJ名, サイト, JIRAあり, Confluenceあり)"""
    result = {}
    for name, host, has_jira, has_confluence in entries:
        atlassian = {"host": host, "mcpServer": "atlassian"}
        if has_jira:
            atlassian["jira"] = {"projectKey": "SAG"}
        if has_confluence:
            atlassian["confluence"] = {"spaceKey": "EXAMPLE"}
        result[name] = {"atlassian": atlassian}
    return {"defaultProfile": entries[0][0], "profiles": result}


def normal_site():
    return {
        MYSELF: fixture("jira/myself.json"),
        JIRA_SEARCH: fixture("jira/search_changelog.json"),
        CURRENT_USER: fixture("confluence/current_user.json"),
        CONFLUENCE_SEARCH: fixture("confluence/search_version.json"),
    }


class FakeAtlassian:
    """サイトとパスごとに決めた応答を返す偽物の通信。呼ばれた URL を控える"""

    def __init__(self, sites):
        self.sites = sites
        self.calls = []

    def __call__(self, method, url, headers, body):
        parsed = urlparse(url)
        self.calls.append((parsed.netloc, parsed.path, parse_qs(parsed.query)))
        answer = self.sites[parsed.netloc][parsed.path]
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, tuple):
            return answer[0], copy.deepcopy(answer[1])
        return 200, copy.deepcopy(answer)

    def queries(self, host, path):
        return [query for site, called, query in self.calls if site == host and called == path]


class AtlassianSourceTestCase(unittest.TestCase):
    def setUp(self):
        # 通信の失敗の再試行を待たない(共通部品の待ち時間だけを0にする)
        patcher = mock.patch.object(client, "_NETWORK_RETRY_INTERVAL_SECONDS", 0)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(client, "_RETRY_INTERVAL_SECONDS", 0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def read(self, transport, profile_data=None):
        profile_data = profile_data or profiles(("SAG", "example.atlassian.net", True, True))
        deps = sources_atlassian.Deps(
            load_profiles=lambda: profile_data,
            get_email=lambda host: "me@example.com",
            get_token=lambda host: "dummy-token",
            http_request=transport,
        )
        return sources_atlassian.read_atlassian(WEEK_START, WEEK_END, deps)


class JiraContractTests(AtlassianSourceTestCase):
    """JIRA の検索と変更履歴の応答から、その週の自分の変更を読む"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-1
    def test_その週に自分が変えた項目だけを変更前後の値と日時つきで古い順に読む(self):
        """新しい順に並んだ変更履歴から、他の人・自動化の変更と範囲の外の変更を除き、古い順に並べ直す。
        否定確認: 日時での並べ直しを外すと落ちる"""
        result = self.read(FakeAtlassian({"example.atlassian.net": normal_site()}))
        self.assertEqual(result.failures, [])
        self.assertEqual(
            [(r["key"], r["summary"], r["field"], r["from"], r["to"], r["time"]) for r in result.jira],
            [
                ("SAG-130", "議事録TODOの起票", "assignee", None, "利用者A", jst("2026-10-05T00:00:00")),
                ("SAG-123", "進捗表の更新", "status", "対応中", "レビュー中", jst("2026-10-06T14:05:10")),
                ("SAG-123", "進捗表の更新", "duedate", "2026-10-10 00:00:00.0", "2026-10-17 00:00:00.0", jst("2026-10-06T14:05:10")),
                ("SAG-130", "議事録TODOの起票", "labels", "議事録", "", jst("2026-10-09T16:59:59")),
            ],
        )
        self.assertTrue(all(r["source"] == "jira" and r["site"] == "example.atlassian.net" for r in result.jira))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-1
    def test_範囲は日本時間の月曜0時を含み金曜17時ちょうどを含まない(self):
        """否定確認: 終わりの比較を「以下」にすると金曜17時ちょうどの変更が入って落ちる"""
        result = self.read(FakeAtlassian({"example.atlassian.net": normal_site()}))
        times = [r["time"] for r in result.jira]
        self.assertIn(jst("2026-10-05T00:00:00"), times)
        self.assertNotIn(jst("2026-10-09T17:00:00"), times)
        self.assertNotIn(jst("2026-10-04T23:50:00"), times)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-1
    def test_検索は週の前後1日を広げた日付で題名と変更履歴を取る(self):
        transport = FakeAtlassian({"example.atlassian.net": normal_site()})
        self.read(transport)
        [query] = transport.queries("example.atlassian.net", JIRA_SEARCH)
        self.assertEqual(query["jql"], ['issue in updatedBy(currentUser(), "2026-10-04", "2026-10-10") ORDER BY updated DESC'])
        self.assertEqual(query["fields"], ["summary"])
        self.assertEqual(query["expand"], ["changelog"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-1
    def test_該当するチケットが無い週は失敗にせず0件で返す(self):
        site = normal_site()
        site[JIRA_SEARCH] = fixture("jira/search_empty.json")
        result = self.read(FakeAtlassian({"example.atlassian.net": site}))
        self.assertEqual(result.jira, [])
        self.assertEqual(result.failures, [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-1
    def test_チケットの題名や変更履歴が欠けた応答はそのサイトを形の違いとして控える(self):
        """否定確認: 欠けた項目を読み飛ばして続けると落ちる"""
        for remove in ("fields", "changelog", "histories", "created", "items"):
            with self.subTest(欠けた項目=remove):
                body = fixture("jira/search_changelog.json")
                issue = body["issues"][0]
                if remove in ("fields", "changelog"):
                    del issue[remove]
                elif remove == "histories":
                    del issue["changelog"]["histories"]
                else:
                    del issue["changelog"]["histories"][2][remove]
                site = normal_site()
                site[JIRA_SEARCH] = body
                result = self.read(FakeAtlassian({"example.atlassian.net": site}))
                self.assertEqual(result.jira, [])
                self.assertIn({"source": "jira", "site": "example.atlassian.net", "reason": "format"}, result.failures)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-1
    def test_チケットの一覧そのものが無い応答は形の違いとして控える(self):
        site = normal_site()
        site[JIRA_SEARCH] = {"isLast": True}
        result = self.read(FakeAtlassian({"example.atlassian.net": site}))
        self.assertEqual(result.failures, [{"source": "jira", "site": "example.atlassian.net", "reason": "format"}])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-1
    def test_値の型が違う応答はそのサイトを形の違いとして控える(self):
        """否定確認: 日時の読み取りの失敗を握りつぶすと落ちる"""
        cases = {
            "変更履歴が一覧でない": lambda issue: issue["changelog"].__setitem__("histories", {"0": {}}),
            "日時が読めない": lambda issue: issue["changelog"]["histories"][2].__setitem__("created", "2026/10/06 14:05"),
            "日時に時刻帯が無い": lambda issue: issue["changelog"]["histories"][2].__setitem__("created", "2026-10-06T14:05:10.000"),
            "題名が文字列でない": lambda issue: issue["fields"].__setitem__("summary", 123),
            "変更後の値が文字列でない": lambda issue: issue["changelog"]["histories"][2]["items"][0].__setitem__("toString", 5),
        }
        for label, breaker in cases.items():
            with self.subTest(label):
                body = fixture("jira/search_changelog.json")
                breaker(body["issues"][0])
                site = normal_site()
                site[JIRA_SEARCH] = body
                result = self.read(FakeAtlassian({"example.atlassian.net": site}))
                self.assertEqual(result.jira, [])
                self.assertIn({"source": "jira", "site": "example.atlassian.net", "reason": "format"}, result.failures)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-1
    def test_時間切れが続いたサイトは通信の失敗として控える(self):
        site = normal_site()
        site[JIRA_SEARCH] = TimeoutError("timed out")
        result = self.read(FakeAtlassian({"example.atlassian.net": site}))
        self.assertEqual(result.jira, [])
        self.assertIn({"source": "jira", "site": "example.atlassian.net", "reason": "network"}, result.failures)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-1
    def test_自分のアカウントが確かめられないサイトは変更履歴を読まずに控える(self):
        """否定確認: 自分のアカウントIDが読めないときに止めずに続けると落ちる"""
        site = normal_site()
        site[MYSELF] = {"displayName": "利用者A"}
        transport = FakeAtlassian({"example.atlassian.net": site})
        result = self.read(transport)
        self.assertEqual(result.jira, [])
        self.assertIn({"source": "jira", "site": "example.atlassian.net", "reason": "format"}, result.failures)
        self.assertEqual(transport.queries("example.atlassian.net", JIRA_SEARCH), [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-1
    def test_全PJのサイトを集め同じサイトは1回だけ読みJIRAの無いPJのサイトは検索しない(self):
        """否定確認: サイトの重ね合わせを外すと同じサイトを2回検索して落ちる"""
        data = profiles(
            ("SAG", "example.atlassian.net", True, True),
            ("NMBM", "example.atlassian.net", True, True),
            ("study(個人)", "personal.atlassian.net", False, True),
        )
        transport = FakeAtlassian({"example.atlassian.net": normal_site(), "personal.atlassian.net": normal_site()})
        result = self.read(transport, data)
        self.assertEqual(len(transport.queries("example.atlassian.net", JIRA_SEARCH)), 1)
        self.assertEqual(transport.queries("personal.atlassian.net", JIRA_SEARCH), [])
        self.assertEqual(len(result.jira), 4)


class ConfluenceContractTests(AtlassianSourceTestCase):
    """Confluence の検索の応答から、その週に自分が最後に編集したページを読む"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-2
    def test_最後の版が自分で範囲内のページの題名と日本時間の更新日時を古い順に読む(self):
        """否定確認: 版の作者の確かめを外すと他の人が直したページが入って落ちる"""
        result = self.read(FakeAtlassian({"example.atlassian.net": normal_site()}))
        self.assertEqual(result.failures, [])
        self.assertEqual(
            [(r["title"], r["time"]) for r in result.confluence],
            [("月曜0時ちょうどに直したページ", jst("2026-10-05T00:00:00")),
             ("定型業務の洗い出しの作業ページ", jst("2026-10-06T10:23:45.678000"))],
        )
        self.assertTrue(all(r["source"] == "confluence" and r["site"] == "example.atlassian.net" for r in result.confluence))

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-2
    def test_検索は週の前後1日を広げた日付で版の情報を展開して取る(self):
        transport = FakeAtlassian({"example.atlassian.net": normal_site()})
        self.read(transport)
        [query] = transport.queries("example.atlassian.net", CONFLUENCE_SEARCH)
        self.assertEqual(
            query["cql"],
            ['type = page AND contributor = currentUser() AND lastmodified >= "2026-10-04" AND lastmodified < "2026-10-11"'],
        )
        self.assertEqual(query["expand"], ["version"])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-2
    def test_該当するページが無い週は失敗にせず0件で返す(self):
        site = normal_site()
        site[CONFLUENCE_SEARCH] = fixture("confluence/search_empty.json")
        result = self.read(FakeAtlassian({"example.atlassian.net": site}))
        self.assertEqual(result.confluence, [])
        self.assertEqual(result.failures, [])

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-2
    def test_版の情報や題名が欠けた応答はそのサイトを形の違いとして控える(self):
        for remove in ("version", "title", "by", "when"):
            with self.subTest(欠けた項目=remove):
                body = fixture("confluence/search_version.json")
                page = body["results"][0]
                if remove in ("version", "title"):
                    del page[remove]
                else:
                    del page["version"][remove]
                site = normal_site()
                site[CONFLUENCE_SEARCH] = body
                result = self.read(FakeAtlassian({"example.atlassian.net": site}))
                self.assertEqual(result.confluence, [])
                self.assertIn({"source": "confluence", "site": "example.atlassian.net", "reason": "format"}, result.failures)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-2
    def test_一覧が無い応答や値の型が違う応答はそのサイトを形の違いとして控える(self):
        cases = {
            "一覧が無い": lambda body: body.pop("results"),
            "日時が文字列でない": lambda body: body["results"][0]["version"].__setitem__("when", 1760000000),
            "作者が辞書でない": lambda body: body["results"][0]["version"].__setitem__("by", "利用者A"),
        }
        for label, breaker in cases.items():
            with self.subTest(label):
                body = fixture("confluence/search_version.json")
                breaker(body)
                site = normal_site()
                site[CONFLUENCE_SEARCH] = body
                result = self.read(FakeAtlassian({"example.atlassian.net": site}))
                self.assertEqual(result.confluence, [])
                self.assertIn({"source": "confluence", "site": "example.atlassian.net", "reason": "format"}, result.failures)

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-2
    def test_時間切れが続いたサイトは通信の失敗として控える(self):
        site = normal_site()
        site[CONFLUENCE_SEARCH] = TimeoutError("timed out")
        result = self.read(FakeAtlassian({"example.atlassian.net": site}))
        self.assertEqual(result.confluence, [])
        self.assertIn({"source": "confluence", "site": "example.atlassian.net", "reason": "network"}, result.failures)
        # JIRA は同じサイトでも独立に読む
        self.assertEqual(len(result.jira), 4)


class PartialFailureTests(AtlassianSourceTestCase):
    """サイトの一部が読めなくても、読めたサイトの分でレポートを作る"""

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-5
    def test_認証に失敗したサイトだけを控え読めたサイトの分は使う(self):
        """否定確認: 1サイトの失敗で全体を止めると落ちる"""
        broken = normal_site()
        broken[JIRA_SEARCH] = (401, {})
        broken[CONFLUENCE_SEARCH] = (403, {})
        data = profiles(("SAG", "example.atlassian.net", True, True), ("NMBM", "broken.atlassian.net", True, True))
        result = self.read(FakeAtlassian({"example.atlassian.net": normal_site(), "broken.atlassian.net": broken}), data)
        self.assertEqual(len(result.jira), 4)
        self.assertEqual(len(result.confluence), 2)
        self.assertEqual(
            sorted(result.failures, key=lambda f: f["source"]),
            [{"source": "confluence", "site": "broken.atlassian.net", "reason": "auth"},
             {"source": "jira", "site": "broken.atlassian.net", "reason": "auth"}],
        )

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-5
    def test_キーチェーンにトークンが無いサイトは認証の失敗として控える(self):
        data = profiles(("SAG", "example.atlassian.net", True, True))
        deps = sources_atlassian.Deps(
            load_profiles=lambda: data,
            get_email=lambda host: "me@example.com",
            get_token=mock.Mock(side_effect=sources_atlassian.TokenNotFoundError("未登録")),
            http_request=FakeAtlassian({"example.atlassian.net": normal_site()}),
        )
        result = sources_atlassian.read_atlassian(WEEK_START, WEEK_END, deps)
        self.assertEqual(result.jira, [])
        self.assertEqual(result.confluence, [])
        self.assertEqual(
            sorted(result.failures, key=lambda f: f["source"]),
            [{"source": "confluence", "site": "example.atlassian.net", "reason": "auth"},
             {"source": "jira", "site": "example.atlassian.net", "reason": "auth"}],
        )

    # 仕様: apps/routine-work-finder/specs/weekly-automation-report/requirements.md#既存の作業の記録の取り込み-5
    def test_PJプロファイルが読めないときはJIRAとConfluenceの両方を設定の失敗として控える(self):
        deps = sources_atlassian.Deps(
            load_profiles=mock.Mock(side_effect=sources_atlassian.ProfileConfigError("読めない")),
            get_email=lambda host: "me@example.com",
            get_token=lambda host: "dummy-token",
            http_request=FakeAtlassian({}),
        )
        result = sources_atlassian.read_atlassian(WEEK_START, WEEK_END, deps)
        self.assertEqual(
            sorted(result.failures, key=lambda f: f["source"]),
            [{"source": "confluence", "site": None, "reason": "config"},
             {"source": "jira", "site": None, "reason": "config"}],
        )


if __name__ == "__main__":
    unittest.main()
