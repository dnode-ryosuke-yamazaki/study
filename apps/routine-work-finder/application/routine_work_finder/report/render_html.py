"""週次レポートのHTMLを作る(design.md「レポートのHTMLを作る」)。

集計・自動化案・作業の要約・記録しない候補・記録の状態を、ひな形 templates/report.html に流し込んで
モック(specs/weekly-automation-report/mock.html)と同じ並びの1枚のHTMLにする。
文字列はすべて HTML のエスケープをしてから入れ、スクリプトが読むデータは JSON にして < を崩して埋め込む。

自動化案・作業の要約・記録しない候補は、appendix.md「Claude の応答の形」の検査を通った値を受け取る。
自動化案が0件の週は、集計の候補の全数とその週のメモの件数で「候補もメモも無い週」と「候補かメモがあった週」の文を分ける。
自動化案の candidateIds の c<n> は集計の候補(aggregate の candidates)の n 番目、
作業の要約の id の w<n> は上位10件(aggregate の top)の n 番目を指す(材料を組み立てたときの番号)。
"""

import html
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from routine_work_finder import config_store, records
from routine_work_finder.report import aggregate

JST = timezone(timedelta(hours=9))
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "report.html"
WEEKDAYS = "月火水木金土日"
EFFECT_CLASSES = {"大": "big", "中": "mid", "小": "small"}
CATEGORY_PARTS = (
    (aggregate.WORK, "作業", "var(--work)"),
    (aggregate.MEETING, "会議", "var(--mid)"),
    (aggregate.AWAY, "離席", "var(--away)"),
    (aggregate.EXCLUDED, "記録しなかった時間", "var(--danger)"),
)
TITLE_REASONS = {
    "timeout": "アプリから応答なし",
    "denied": "読み取りの許可がない",
    "noWindow": "前面のウィンドウが取れない",
}
SOURCE_NAMES = {"jira": "JIRA", "confluence": "Confluence", "claudeCode": "Claude Code の会話", "minutes": "議事録"}
# 「この週の〜は使わずに作りました」に入れる語。英字で始まる語は前に空白を入れる
SOURCE_USES = {"jira": " JIRA の更新", "confluence": " Confluence の編集", "claudeCode": " Claude Code の会話",
               "minutes": "議事録"}
FAILURE_REASONS = {
    "auth": "認証に失敗したため",
    "network": "通信に失敗したため",
    "request": "検索が受け付けられなかったため",
    "format": "応答の形が想定と違ったため",
    "config": "PJプロファイルが読めないため",
    "missing": "議事録の控えのフォルダが見つからないため",
    "unreadable": "読めなかったため",
}
ESTIMATED_MARK = "(推定)"
NO_SUMMARY = "この週は作業の要約を作っていません(自動化案の欄の理由と同じ)。時間帯だけを出しています。"
NO_EXAMPLES = "(要約を作っていないため出していません)"
MANUAL_GUIDE = "この画面ではコピーが使えませんでした。下の文を選んでコピーし、Claude Code のチャット欄に貼ってください。"
BACKLOG_HEAD = "/backlog 定型業務の週次レポート {week} の自動化案から、次をバックログに積んでください。"
EXCLUSION_HEAD = "/routine-work-finder 記録しないものに次を足してください。"


@dataclass
class StatusInputs:
    """記録の状態のために記録・メモ・設定のファイルから読んだもの(読むだけで書き換えない)"""

    last_kind: Optional[str]          # 対象の範囲の最後の行の種類
    last_time: Optional[datetime]     # その行の時刻
    recorded_days: list               # 開始・停止を除いた行がある日
    memo_dates: list                  # 範囲のメモの日(メモ1件ごとに1つ)
    config: config_store.ConfigRead   # 操作の記録の設定ファイルを読んだ結果
    retained_weeks: Optional[tuple]   # 残している記録のいちばん古い週といちばん新しい週の名前


@dataclass
class ReportInput:
    week: str                          # 週の名前(例: 2026-W41)
    period_start: datetime             # 対象の始まり(月曜0時)
    period_end: datetime               # 対象の終わり(金曜17時か、途中までの作り直しの終わり)
    partial: bool                      # 今の週を途中で作り直したか
    created_at: datetime               # 作成の日時
    current_week: bool                 # 対象の週が今の週か
    aggregate: aggregate.WeekAggregate
    outcome: str                       # generated / insufficient / claudeFailed
    proposals: list                    # 検査済みの自動化案(表示の順)
    summaries: list                    # 検査済みの作業の要約の items
    exclusions: Optional[list]         # 検査済みの記録しない候補(表示の順)。作れなかったときは None
    exclusion_windows: list            # 記録しない候補の材料の windows(当たった題名のアプリ名に使う)
    status: StatusInputs
    unreadable_sources: list           # 読めなかった既存の作業の記録 {source, site, reason}


def week_name(moment):
    """ISO の週番号の週の名前(例: 2026-W41)。日付は日本時間で見る"""
    day = moment.astimezone(JST).date() if isinstance(moment, datetime) else moment
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def week_state(outcome, proposals):
    """週の状態。自動化案と作業の要約の結果(claude_calls の status。5時間未満かの判定はそちらで行う)だけで決め、
    記録しない候補は見ない"""
    if outcome == "insufficient":
        return "insufficient"
    if outcome == "claudeFailed":
        return "failed"
    return "normal" if proposals else "empty"


def report_period_end(monday, requested_at):
    """作り直しの範囲の終わりと、途中までの記録か。依頼を受け付けた日時と金曜17時の早い方"""
    friday_17 = monday + timedelta(days=4, hours=17)
    if requested_at < friday_17:
        return requested_at.astimezone(JST), True
    return friday_17, False


def backlog_request_text(week, proposals, selected_numbers):
    """依頼文(バックログに積む)。ひな形の backlogText と同じ形"""
    lines = [f"{number}. {item['title']}" for number, item in enumerate(proposals, start=1) if number in selected_numbers]
    return BACKLOG_HEAD.format(week=week) + "\n" + "\n".join(lines)


def exclusion_request_text(exclusions, selected_numbers):
    """依頼文(記録しないものに足す)。ひな形の exclusionText と同じ形で、末尾に改行1つ"""
    lines = [f"{_target_label(item['target'])}: {item['value']}"
             for number, item in enumerate(exclusions, start=1) if number in selected_numbers]
    return EXCLUSION_HEAD + "\n" + "\n".join(lines) + "\n"


def read_status_inputs(data_paths, start, end):
    """記録の状態の材料を読む。記録・メモ・設定のファイルは読むだけで書き換えない"""
    lines = records.read_records(data_paths, start, end).lines
    last = lines[-1] if lines else None
    days = sorted({line["time"].date() for line in lines if line["kind"] not in aggregate.NOT_COUNTED_KINDS})
    memos = records.read_memos(data_paths, start, end)
    return StatusInputs(
        last_kind=last["kind"] if last else None,
        last_time=last["time"] if last else None,
        recorded_days=days,
        memo_dates=[memo["time"].date() for memo in memos],
        config=config_store.read_config(data_paths),
        retained_weeks=_retained_weeks(data_paths),
    )


def _retained_weeks(data_paths):
    folder = data_paths.records
    names = sorted(path.name for path in (folder.iterdir() if folder.exists() else [])
                   if records.FILE_NAME_PATTERN.match(path.name))
    if not names:
        return None
    first, last = (datetime.fromisoformat(name[:10]).date() for name in (names[0], names[-1]))
    return week_name(first), week_name(last)


def render_report(report):
    """1枚のHTMLを返す"""
    state = week_state(report.outcome, report.proposals)
    template = TEMPLATE.read_text(encoding="utf-8")
    parts = {
        "<!--TITLE-->": _e(f"定型業務レポート {report.week}"),
        "<!--EYEBROW-->": _e(f"{report.week} ・ 定型業務レポート"),
        "<!--PERIOD-->": _e(_period_text(report)),
        "<!--TOTALS-->": _totals_html(report.aggregate.totals),
        "<!--PROPOSALS-->": _proposals_html(report, state),
        "<!--SPLIT-->": _split_html(report.aggregate.totals),
        "<!--LEGEND-->": _legend_html(report.aggregate.totals),
        "<!--BARS-->": _bars_html(report, state),
        "<!--EXCLUSIONS-->": _exclusions_html(report),
        "<!--RECORD_STATUS-->": _status_html(report),
        "/*REPORT_DATA*/": _script_data(report, state),
    }
    for marker, value in parts.items():
        template = template.replace(marker, value)
    return template


def _e(text):
    return html.escape(str(text), quote=True)


def _hours(seconds):
    return f"{seconds / 3600:.1f}"


def _date_label(moment, with_year=False):
    local = moment.astimezone(JST)
    year = f"{local.year}年" if with_year else ""
    return f"{year}{local.month}月{local.day}日({WEEKDAYS[local.weekday()]})"


def _datetime_label(moment):
    local = moment.astimezone(JST)
    return f"{_date_label(local)} {local:%H:%M}"


def _period_text(report):
    start = report.period_start.astimezone(JST)
    end = report.period_end.astimezone(JST)
    end_label = _date_label(end, with_year=end.year != start.year)
    if report.partial:
        end_label = f"{end_label} {end:%H:%M}(途中までの記録)"
    return f"対象: {_date_label(start, with_year=True)}〜{end_label} ／ 作成: {_datetime_label(report.created_at)}"


def _totals_html(totals):
    return "".join(f"<span>{name} <b>{_hours(totals[key])}</b>時間</span>" for key, name, _ in CATEGORY_PARTS)


def _split_html(totals):
    total = sum(totals[key] for key, _, _ in CATEGORY_PARTS)
    return "".join(
        f'<span style="width:{(totals[key] / total * 100) if total else 0:.1f}%;background:{color}"></span>'
        for key, _, color in CATEGORY_PARTS)


def _legend_html(totals):
    return "".join(f'<span><i style="background:{color}"></i>{name} {_hours(totals[key])}h</span>'
                   for key, name, color in CATEGORY_PARTS)


def _candidate_ids(week):
    """集計の候補の番号(c1・c2…)と組"""
    return {f"c{index}": candidate for index, candidate in enumerate(week.candidates, start=1)}


def _proposal_seconds(item, candidates):
    found = [candidates[candidate_id].seconds for candidate_id in item["candidateIds"] if candidate_id in candidates]
    return sum(found) if found else None


def _proposals_html(report, state):
    if state == "empty":
        candidates, memos = len(report.aggregate.candidates), len(report.status.memo_dates)
        if not candidates and not memos:
            return '<p class="empty">今週は自動化案になる繰り返しが見つかりませんでした。同じ操作が週2回以上あると候補になります。</p>'
        return (f'<p class="empty">繰り返しの候補が{candidates}件、面倒だった作業のメモが{memos}件ありましたが、'
                f"Claude は自動化案にしませんでした。チャットで「{_e(report.week)} の定型業務レポートを作り直して」と頼むと、"
                "作り直しで案が出ることがあります。</p>")
    if state == "insufficient":
        work = _hours(report.aggregate.totals[aggregate.WORK])
        return (f'<p class="empty">今週の作業の記録が{work}時間しかないため、自動化案は作っていません。'
                "作業の記録が5時間以上ある週に作ります。</p>")
    if state == "failed":
        return ('<p class="error"><b>自動化案を作れませんでした。</b> 分析の途中でClaudeの呼び出しが3回続けて失敗しました。'
                f"時間の使い方と記録の状態は下に出ています。チャットで「{_e(report.week)} の定型業務レポートを作り直して」"
                "と頼むと作り直せます。</p>")
    candidates = _candidate_ids(report.aggregate)
    items = []
    for number, item in enumerate(report.proposals, start=1):
        seconds = _proposal_seconds(item, candidates)
        hours = "週の時間は記録では見えない" if seconds is None else f"週 {_hours(seconds)}h"
        effect, importance = item["effect"], item["importance"]
        items.append(
            '<li class="proposal">'
            f'<input type="checkbox" id="pick-{number}" data-pick="proposal" data-number="{number}">'
            '<div class="ptitle">'
            f'<label for="pick-{number}">{number}. {_e(item["title"])}</label>'
            f'<span class="hours">{hours}</span>'
            f'<span class="effect importance {EFFECT_CLASSES.get(importance, "small")}">重要度 {_e(importance)}</span>'
            f'<span class="effect {EFFECT_CLASSES.get(effect, "small")}">効果 {_e(effect)}</span>'
            "</div>"
            '<dl class="pbody">'
            f'<dt>重要度の根拠</dt><dd>{_e(item["importanceReason"])}</dd>'
            f'<dt>見えた繰り返し</dt><dd>{_e(item["seen"])}</dd>'
            f'<dt>自動化の案</dt><dd>{_e(item["idea"])}</dd>'
            f'<dt>使える仕組み</dt><dd>{_e("、".join(item["reuse"]))}</dd>'
            "</dl>"
            "</li>")
    return (f'<ul class="proposals">{"".join(items)}</ul>'
            + _copy_controls("copy-btn", "copy-status", "manual", "manual-text",
                             "選んだ案をバックログに積む依頼文をコピー", "積みたい案にチェックを入れてください"))


def _copy_controls(button_id, status_id, manual_id, text_id, label, idle):
    return ('<div class="actions">'
            f'<button type="button" id="{button_id}" disabled>{label}</button>'
            f'<span class="status" id="{status_id}">{idle}</span>'
            "</div>"
            f'<div class="manual" id="{manual_id}" hidden>'
            f'<span class="status">{MANUAL_GUIDE}</span>'
            f'<textarea id="{text_id}" readonly></textarea>'
            "</div>")


def _group_name(group):
    if not group.title_known or group.title is None:
        return "(題名が取れませんでした)"
    return f"{group.title} — {group.sheet}" if group.sheet else group.title


def _example_label(example):
    local = datetime.fromisoformat(example["t"]).astimezone(JST)
    return f"{example['text']}({local.month}/{local.day} {local.hour}:{local.minute:02d})"


def _proposal_link(group, report, candidates):
    """その組を候補に含む最初の自動化案の番号と題名"""
    for number, item in enumerate(report.proposals, start=1):
        if any(candidates[candidate_id].group is group for candidate_id in item["candidateIds"] if candidate_id in candidates):
            return number, item["title"]
    return None


def _bars_html(report, state):
    top = report.aggregate.top
    if not top:
        return ""
    longest = top[0].seconds or 1
    with_summary = state in ("normal", "empty")
    summaries = {item["id"]: item for item in report.summaries} if with_summary else {}
    candidates = _candidate_ids(report.aggregate)
    rows = []
    for index, group in enumerate(top):
        summary = summaries.get(f"w{index + 1}")
        if summary:
            # 推定で書いた要約には印を付ける(requirements.md 作業の要約[5])
            summary_text = (ESTIMATED_MARK if summary["estimated"] else "") + _e(summary["summary"])
        else:
            summary_text = "" if with_summary else _e(NO_SUMMARY)
        if summary:
            examples = [_e(_example_label(example)) for example in summary["examples"]]
        else:
            examples = [] if with_summary else [_e(NO_EXAMPLES)]
        link = _proposal_link(group, report, candidates) if state == "normal" else None
        link_html = f'<a href="#pick-{link[0]}">案{link[0]}「{_e(link[1])}」</a>' if link else "なし"
        rows.append(
            f'<li><details id="bar-{index}">'
            "<summary>"
            f'<span class="name">{_e(group.app)} <small>{_e(_group_name(group))}</small></span>'
            f'<span class="track"><span class="fill" style="width:{group.seconds / longest * 100:.1f}%"></span></span>'
            f'<span class="h">{_hours(group.seconds)}h</span>'
            "</summary>"
            '<div class="bardetail">'
            f'<p class="bsum">{summary_text}</p>'
            '<dl class="kv">'
            f'<dt>主な時間帯</dt><dd>{_e("、".join(group.main_times))}</dd>'
            f'<dt>具体例</dt><dd><ul class="ex">{"".join(f"<li>{example}</li>" for example in examples)}</ul></dd>'
            f"<dt>自動化案</dt><dd>{link_html}</dd>"
            "</dl>"
            "</div>"
            "</details></li>")
    return "".join(rows)


def _target_label(target):
    return "ことば" if target == "word" else "アプリ"


def _example_app(item, windows):
    for window in windows:
        if window.get("title") == item["example"]:
            return window.get("app")
    return None


def _exclusions_html(report):
    if report.exclusions is None:
        return ('<p class="error"><b>記録しない候補を作れませんでした。</b> '
                "Claudeの呼び出しが3回続けて失敗しました。ほかの欄はそのまま出ています。</p>")
    if not report.exclusions:
        return '<p class="empty">今週は記録しない候補はありません。</p>'
    items = []
    for number, item in enumerate(report.exclusions, start=1):
        app = _example_app(item, report.exclusion_windows)
        example = f"{item['example']}({app})" if app else item["example"]
        items.append(
            '<li class="proposal">'
            f'<input type="checkbox" id="ex-{number}" data-pick="exclusion" data-number="{number}">'
            '<div class="ptitle">'
            f'<label for="ex-{number}">{_target_label(item["target"])}「{_e(item["value"])}」</label>'
            f'<span class="effect small">種類 {_e(item["kind"])}</span>'
            "</div>"
            '<dl class="pbody">'
            f"<dt>当たった題名の例</dt><dd>{_e(example)}</dd>"
            f'<dt>理由</dt><dd>{_e(item["reason"])}</dd>'
            "</dl>"
            "</li>")
    return (f'<ul class="proposals">{"".join(items)}</ul>'
            + _copy_controls("ex-copy-btn", "ex-copy-status", "ex-manual", "ex-manual-text",
                             "選んだ候補を記録しないものに足す依頼文をコピー", "外したい候補にチェックを入れてください"))


def _warn(text):
    return f'<span class="warnline">{_e(text)}</span>'


def _state_html(report):
    status = report.status
    if status.last_kind == "stop":
        return f'<span class="pill off">終了</span> {_e(_datetime_label(status.last_time))} に終わりました'
    if not report.current_week:
        return '<span class="pill">記録中</span>(この週のあとも記録を続けていました)'
    config = status.config
    if config.state == "unreadable":
        return '<span class="pill">記録中</span> ' + _warn("設定ファイルが読めないため、終わりの予定は出していません")
    ends_at = config.config.get("endsAt") if config.state == "ok" else None
    if ends_at:
        return f'<span class="pill">記録中</span> {_e(_datetime_label(datetime.fromisoformat(ends_at)))} に終わります'
    return '<span class="pill">記録中</span>'


def _recorded_html(report):
    total = sum(report.aggregate.totals[key] for key, _, _ in CATEGORY_PARTS)
    days = report.status.recorded_days
    if report.partial:
        start = report.period_start.astimezone(JST)
        end = report.period_end.astimezone(JST)
        span = f"{start.month}月{start.day}日〜{end.month}月{end.day}日 {end:%H:%M}"
    elif len(days) == 1:
        span = f"{days[0].month}月{days[0].day}日のみ"
    else:
        span = f"{len(days)}日間"
    return _e(f"{_hours(total)}時間({span})")


def _memos_html(dates):
    if not dates:
        return "なし"
    unique = sorted(set(dates))
    return _e(f"{len(dates)}件(" + "・".join(f"{day.month}月{day.day}日" for day in unique) + ")")


def _excluded_lists(config):
    if config.state == "unreadable":
        return _warn("設定ファイルが読めない"), _warn("設定ファイルが読めない")
    values = config.config if config.state == "ok" else config_store.default_config()
    apps = "・".join(app["name"] for app in values["excludedApps"]) or "なし"
    words = "・".join(values["excludedTitleWords"]) or "なし"
    return _e(apps), _e(words)


def _range_label(start, end):
    if start.date() == end.date():
        return f"{_datetime_label(start)}〜{end:%H:%M}"
    return f"{_datetime_label(start)}〜{_datetime_label(end)}"


def _lost_html(week):
    parts = []
    if week.gaps:
        parts.append(_warn(f"記録が取れなかった時間: 合計 {_hours(week.gap_seconds)}時間(Macのスリープなど)"))
        ranges = "".join(f"<li>{_e(_range_label(start.astimezone(JST), end.astimezone(JST)))}</li>" for start, end in week.gaps)
        parts.append(f'<ul class="ex">{ranges}</ul>')
    for item in week.title_unavailable:
        reason = TITLE_REASONS.get(item["reason"], "理由が分からない")
        parts.append(_warn(f"題名が取れなかった時間: {item['app']} {_hours(item['seconds'])}時間({reason}。アプリ名だけ記録)"))
    return "".join(parts) or "なし"


def _retained_html(retained):
    if not retained:
        return "なし"
    first, last = retained
    last_label = last[5:] if first[:4] == last[:4] else last
    first_monday = datetime.fromisocalendar(int(first[:4]), int(first[6:]), 1)
    last_monday = datetime.fromisocalendar(int(last[:4]), int(last[6:]), 1)
    weeks = (last_monday - first_monday).days // 7 + 1
    return _e(f"{first}〜{last_label} の{weeks}週間分(それより古い週は消しています)")


def _unreadable_html(failures):
    if not failures:
        return "なし(JIRA・Confluence・Claude Code の会話・議事録をすべて読めました)"
    lines = []
    for failure in failures:
        source = failure.get("source")
        name = SOURCE_NAMES.get(source, str(source))
        if failure.get("site"):
            name = f"{name}({failure['site']})"
        use = SOURCE_USES.get(source, name)
        if failure.get("reason") == "truncated":
            lines.append(_warn(f"{name}: 件数の上限で打ち切られ、この週の{use}の一部を読めていない恐れがあります。読めた分で作りました"))
            continue
        reason = FAILURE_REASONS.get(failure.get("reason"), f"読めなかったため(理由: {failure.get('reason')})")
        lines.append(_warn(f"{name}: {reason}、この週の{use}は使わずに作りました"))
    return "<br>".join(lines)


def _mic_html(config):
    """集計で使った設定(run_report が同じ読み取りの結果から決める)に合わせた文。読めずに既定で数えたときは理由を添える"""
    if config.state == "unreadable":
        return _warn("設定ファイルが読めないため、使用中は会議として数えました")
    if config_store.mic_as_meeting(config.config):
        return "使用中は会議として数えました"
    return "会議として数えず、作業か離席に分けました"


def _status_html(report):
    apps, words = _excluded_lists(report.status.config)
    rows = [
        ("状態", _state_html(report)),
        ("この週の記録", _recorded_html(report)),
        ("面倒だった作業のメモ", _memos_html(report.status.memo_dates)),
        ("記録しないアプリ", apps),
        ("記録しないことば<br><small>(題名に含まれると記録しない)</small>", words),
        ("マイクの扱い", _mic_html(report.status.config)),
        ("取れなかった時間", _lost_html(report.aggregate)),
        ("残しているデータ", _retained_html(report.status.retained_weeks)),
        ("読めなかった記録", _unreadable_html(report.unreadable_sources)),
    ]
    return "".join(f"<dt>{term}</dt><dd>{value}</dd>" for term, value in rows)


def _script_data(report, state):
    """スクリプトが読むデータ。依頼文の組み立てに要る週の名前・案の番号と題名・候補の番号と値だけを入れる"""
    proposals = report.proposals if state == "normal" else []
    exclusions = report.exclusions or []
    data = {
        "week": report.week,
        "proposals": [{"number": number, "title": item["title"]} for number, item in enumerate(proposals, start=1)],
        "exclusions": [{"number": number, "target": item["target"], "value": item["value"]}
                       for number, item in enumerate(exclusions, start=1)],
    }
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
