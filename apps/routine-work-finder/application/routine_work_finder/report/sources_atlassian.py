"""全PJのサイトから、その週の JIRA の自分の更新と Confluence の自分の編集を読む。

PJプロファイルに登録したすべてのPJから JIRA と Confluence のサイトを集め、同じサイトは1回だけ読む。
通信と認証は ~/.claude/lib/atlassian_rest を使う(変更しない)。読めなかったサイトはレポートを止めずに
記録の名前・サイト・理由として控える(design.md「既存の作業の記録を読み込む」1〜3・7、
appendix.md「JIRA と Confluence の検索の形」)。

例外の文言には URL・トークン・本文を入れない。ログに書くのは記録の名前・サイト・理由だけにする。
"""

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

LIB_DIR = Path.home() / ".claude" / "lib"
if str(LIB_DIR) not in sys.path:
    # 先頭に入れると ~/.claude/lib/tests がこのアプリの tests を覆い隠すため末尾に足す
    sys.path.append(str(LIB_DIR))

from atlassian_rest import client
from atlassian_rest.auth import TokenNotFoundError, get_api_token
from atlassian_rest.config import ConfigError, get_token_meta_for_host

JST = timezone(timedelta(hours=9))
PROFILES_PATH = Path.home() / ".claude" / "config" / "project-profiles.json"
JQL_TEMPLATE = 'issue in updatedBy(currentUser(), "{start}", "{end}") ORDER BY updated DESC'
CQL_TEMPLATE = 'type = page AND contributor = currentUser() AND lastmodified >= "{start}" AND lastmodified < "{end}"'
# 共通部品の search_pages は展開と件数を指定できないため、送る直前の URL に足す
CONFLUENCE_SEARCH_PATH = "/wiki/rest/api/content/search?"
CONFLUENCE_SEARCH_EXTRA = "&expand=version&limit=100"

__all__ = ["AtlassianResult", "Deps", "ProfileConfigError", "TokenNotFoundError", "read_atlassian"]


class ProfileConfigError(Exception):
    """PJプロファイルが読めない・形が違う"""


class FormatError(Exception):
    """応答の形が想定と違う"""


def load_profiles(path=PROFILES_PATH):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProfileConfigError(type(error).__name__) from None
    if not isinstance(data, dict) or not isinstance(data.get("profiles"), dict):
        raise ProfileConfigError("profiles がありません")
    return data


def _email_for(host):
    return get_token_meta_for_host(host)["email"]


@dataclass
class Deps:
    """外とのやりとり。テストでは偽物に差し替える。http_request が None なら共通部品の既定の通信を使う"""

    load_profiles: Callable[[], dict] = load_profiles
    get_email: Callable[[str], str] = _email_for
    get_token: Callable[[str], str] = get_api_token
    http_request: Callable | None = None


@dataclass
class AtlassianResult:
    """jira: 自分の変更(項目ごと)、confluence: 自分が最後に編集したページ、failures: 読めなかったサイト"""

    jira: list = field(default_factory=list)
    confluence: list = field(default_factory=list)
    failures: list = field(default_factory=list)


def read_atlassian(start, end, deps=None):
    """start 以上 end 未満(日本時間)に自分が変えた JIRA の項目と、自分が最後に編集した Confluence のページを読む"""
    deps = deps or Deps()
    result = AtlassianResult()
    try:
        jira_sites, confluence_sites = collect_sites(deps.load_profiles())
    except ProfileConfigError:
        result.failures = [_failure("jira", None, "config"), _failure("confluence", None, "config")]
        return result
    for host in jira_sites:
        result.jira.extend(_read_site("jira", host, start, end, deps, result.failures))
    for host in confluence_sites:
        result.confluence.extend(_read_site("confluence", host, start, end, deps, result.failures))
    result.jira.sort(key=lambda record: record["time"])
    result.confluence.sort(key=lambda record: record["time"])
    return result


def collect_sites(profile_data):
    """PJプロファイルの全PJから、JIRA と Confluence を持つサイトをそれぞれ重なりなく集める"""
    profiles = profile_data.get("profiles") if isinstance(profile_data, dict) else None
    if not isinstance(profiles, dict):
        raise ProfileConfigError("profiles がありません")
    jira_sites, confluence_sites = [], []
    for name in sorted(profiles):
        atlassian = profiles[name].get("atlassian") if isinstance(profiles[name], dict) else None
        if not isinstance(atlassian, dict) or not isinstance(atlassian.get("host"), str) or not atlassian["host"]:
            continue
        host = atlassian["host"]
        if "jira" in atlassian and host not in jira_sites:
            jira_sites.append(host)
        if "confluence" in atlassian and host not in confluence_sites:
            confluence_sites.append(host)
    return jira_sites, confluence_sites


def _failure(source, site, reason):
    return {"source": source, "site": site, "reason": reason}


def _read_site(source, host, start, end, deps, failures):
    """1サイト分を読む。失敗したらそのサイトの分は使わず、理由を控えて空を返す"""
    try:
        email = deps.get_email(host)
        token = deps.get_token(host)
        if source == "jira":
            return _read_jira(host, email, token, start, end, deps.http_request)
        return _read_confluence(host, email, token, start, end, deps.http_request)
    except (client.AuthenticationError, TokenNotFoundError, ConfigError):
        reason = "auth"
    except (client.RestDataError, FormatError):
        reason = "format"
    except client.RestApiError:
        reason = "network"
    failures.append(_failure(source, host, reason))
    return []


def _search_dates(start, end):
    """検索の日付は前後1日を広げる(Atlassian のプロフィールの時刻帯と日本時間のずれを吸収する)"""
    first = start.astimezone(JST).date() - timedelta(days=1)
    last = end.astimezone(JST).date() + timedelta(days=1)
    return first, last


def _account_id(host, email, token, path, http_request):
    transport = http_request or client._default_http_request
    headers = client._basic_auth_header(email, token)
    _status, body = client._request_with_retry(transport, "GET", f"https://{host}{path}", headers)
    account_id = body.get("accountId") if isinstance(body, dict) else None
    if not isinstance(account_id, str) or not account_id:
        raise FormatError("自分のアカウントIDが読めません")
    return account_id


def _read_jira(host, email, token, start, end, http_request):
    me = _account_id(host, email, token, "/rest/api/3/myself", http_request)
    first, last = _search_dates(start, end)
    jql = JQL_TEMPLATE.format(start=first.isoformat(), end=last.isoformat())
    issues = client.search_issues(
        f"https://{host}", email, token, jql, fields=["summary"], expand="changelog", http_request=http_request
    )
    records = []
    for issue in issues:
        key, summary, histories = _issue_parts(issue)
        for history in histories:
            when, author, items = _history_parts(history)
            if author != me or not start <= when < end:
                continue
            for item in items:
                records.append({
                    "source": "jira", "site": host, "key": key, "summary": summary,
                    "field": item["field"], "from": item["fromString"], "to": item["toString"], "time": when,
                })
    return records


def _issue_parts(issue):
    if not isinstance(issue, dict):
        raise FormatError("チケットの形が違います")
    key = issue.get("key")
    fields = issue.get("fields")
    summary = fields.get("summary") if isinstance(fields, dict) else None
    changelog = issue.get("changelog")
    histories = changelog.get("histories") if isinstance(changelog, dict) else None
    if not isinstance(key, str) or not isinstance(summary, str) or not isinstance(histories, list):
        raise FormatError("チケットのキー・題名・変更履歴が読めません")
    return key, summary, histories


def _history_parts(history):
    if not isinstance(history, dict):
        raise FormatError("変更履歴の形が違います")
    when = _parse_time(history.get("created"))
    author = history.get("author")
    # 作者の無い変更(作者が消えたものなど)は自分の変更ではないとして扱う
    author_id = author.get("accountId") if isinstance(author, dict) else None
    items = history.get("items")
    if not isinstance(items, list):
        raise FormatError("変更の項目が読めません")
    checked = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("field"), str):
            raise FormatError("変更の項目の形が違います")
        for name in ("fromString", "toString"):
            if item.get(name) is not None and not isinstance(item.get(name), str):
                raise FormatError("変更前後の値の形が違います")
        checked.append({"field": item["field"], "fromString": item.get("fromString"), "toString": item.get("toString")})
    return when, author_id, checked


def _parse_time(value):
    if not isinstance(value, str):
        raise FormatError("日時が文字列ではありません")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise FormatError("日時が読めません") from None
    if parsed.tzinfo is None:
        raise FormatError("日時に時刻帯がありません")
    return parsed.astimezone(JST)


def _with_version(http_request):
    """Confluence の検索に版の情報の展開と件数を足して送る通信"""
    transport = http_request or client._default_http_request

    def request(method, url, headers, body):
        if CONFLUENCE_SEARCH_PATH in url:
            url = url + CONFLUENCE_SEARCH_EXTRA
        return transport(method, url, headers, body)

    return request


def _read_confluence(host, email, token, start, end, http_request):
    me = _account_id(host, email, token, "/wiki/rest/api/user/current", http_request)
    first, last = _search_dates(start, end)
    cql = CQL_TEMPLATE.format(start=first.isoformat(), end=(last + timedelta(days=1)).isoformat())
    pages = client.search_pages(f"https://{host}", email, token, cql, http_request=_with_version(http_request))
    records = []
    for page in pages:
        title, when, author = _page_parts(page)
        if author == me and start <= when < end:
            records.append({"source": "confluence", "site": host, "title": title, "time": when})
    return records


def _page_parts(page):
    if not isinstance(page, dict) or not isinstance(page.get("title"), str):
        raise FormatError("ページの題名が読めません")
    version = page.get("version")
    if not isinstance(version, dict) or not isinstance(version.get("by"), dict):
        raise FormatError("ページの版の情報が読めません")
    return page["title"], _parse_time(version.get("when")), version["by"].get("accountId")
