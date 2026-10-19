"""週次レポート係の入口(design.md「週次レポートを作って届ける」「作り直しの依頼を受けて作り直す」4〜7、「エラーハンドリング」)。

    python3 -m routine_work_finder.report.run_report

launchd が金曜17時と作り直しの依頼のフォルダの変化で起動する。ロックを取り、週次レポート係の状態のファイル
(report-state.json)から定期の作成の対象の週の一覧を先に決め、作り直しの依頼を古い順に処理してから対象の週を
古い順に作る。ロックを外す前に依頼のフォルダをもう一度見る。

- 定期の作成は成功でも失敗でも結果を状態のファイルの weeks に書き、weeks にある週はもう作らない。作り直しは書かない
- weeks に無く金曜17時を過ぎた週の依頼は、作り直しではなく定期の作成として作り、対象の週の一覧から除く
- 思わぬ例外は全体を囲んでログと Teams に出し、定期の作成の途中なら weeks に failed と書き、
  作り直しの依頼の処理中ならその依頼ファイルを消す。ロックは必ず外す
- ログは appendix.md「ログの書式」。題名・依頼文・メモの文・Claude の応答の中身は書かない
"""

import json
import logging
import os
import shutil
import sys
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from routine_work_finder import config_store, paths, records, weeks
from routine_work_finder.report import (
    aggregate,
    claude_calls,
    exclusions,
    materials,
    onedrive_write,
    publish,
    render_html,
)

LOGGER = logging.getLogger("routine_work_finder.report")
STATE_VERSION = 1
LOCK_STALE_AFTER = timedelta(hours=2)
OWNER_FILE = "owner.json"

GENERATED = claude_calls.GENERATED
INSUFFICIENT = claude_calls.INSUFFICIENT
CLAUDE_FAILED = claude_calls.CLAUDE_FAILED
SAVE_FAILED = "saveFailed"
FAILED = "failed"
NO_RECORDS = "noRecords"
RESULTS = (GENERATED, INSUFFICIENT, CLAUDE_FAILED, SAVE_FAILED, FAILED, NO_RECORDS)

TRIGGER_SCHEDULE = "schedule"
TRIGGER_REQUEST = "request"
LOG_LEVELS = {"WARNING": "WARN", "CRITICAL": "ERROR"}


def _read_atlassian(start, end):
    from routine_work_finder.report import sources_atlassian
    return sources_atlassian.read_atlassian(start, end)


def _read_claude_code(start, end):
    from routine_work_finder.report import sources_claude_code
    return sources_claude_code.read_claude_code(start, end)


def _read_minutes(start, end):
    from routine_work_finder.report import sources_minutes
    return sources_minutes.read_minutes(start, end)


def process_alive(pid):
    """そのプロセスが動いているか(権限が無くても存在すれば動いているとみなす)"""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@dataclass
class Deps:
    """外とのやりとり。テストでは偽物に差し替える。notifier・run_headless が None なら共通部品の既定を使う"""

    data_paths: paths.DataPaths
    now: Callable[[], datetime] = weeks.now
    read_atlassian: Callable = _read_atlassian
    read_claude_code: Callable = _read_claude_code
    read_minutes: Callable = _read_minutes
    collect_reusable: Callable[[], list] = materials.collect_reusable
    run_headless: Callable | None = None
    notifier: Callable | None = None
    sleep: Callable[[float], None] = time.sleep
    onedrive_dir: Path = publish.ONEDRIVE_DIR
    copy: Callable = onedrive_write.copy_file
    pid: int = field(default_factory=os.getpid)
    pid_alive: Callable[[int], bool] = process_alive


class Outcome(NamedTuple):
    """1週分の作成の結果。result は weeks に書く値、notified は Teams に知らせられたか"""

    result: str
    notified: bool


def timestamp(moment):
    return weeks.to_tokyo(moment).isoformat(timespec="seconds")


def _write_json(path, value):
    """一時ファイル(600)に書いてから名前を付け替える"""
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, path)


# ロック


class Lock:
    """フォルダを作れたら実行できる形のロック。中の owner.json に pid と日時を書く。
    2時間より古く、かつ pid のプロセスが動いていないロックは捨てる。owner.json が無い・読めないときは
    フォルダの更新日時が2時間より古ければ捨てる"""

    def __init__(self, deps):
        self.deps = deps
        self.folder = deps.data_paths.report_lock
        self.held = False

    def acquire(self):
        config_store.ensure_data_folder(self.deps.data_paths)
        for attempt in (1, 2):
            try:
                self.folder.mkdir(mode=0o700)
            except FileExistsError:
                if attempt == 1 and self._stale():
                    LOGGER.warning("lock stale removed")
                    shutil.rmtree(self.folder, ignore_errors=True)
                    continue
                return False
            self.held = True
            self.refresh()
            return True
        return False

    def refresh(self):
        """持ち主の日時を今に書き直す(依頼を1件処理するたびに呼ぶ)"""
        _write_json(self.folder / OWNER_FILE, {"pid": self.deps.pid, "at": timestamp(self.deps.now())})

    def release(self):
        if self.held:
            shutil.rmtree(self.folder, ignore_errors=True)
            self.held = False

    def _stale(self):
        now = weeks.to_tokyo(self.deps.now())
        owner = self._owner()
        if owner is not None:
            pid, at = owner
            return now - at > LOCK_STALE_AFTER and not self.deps.pid_alive(pid)
        try:
            modified = self.folder.stat().st_mtime
        except FileNotFoundError:
            return True
        return now.timestamp() - modified > LOCK_STALE_AFTER.total_seconds()

    def _owner(self):
        try:
            raw = json.loads((self.folder / OWNER_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(raw, dict):
            return None
        pid, at = raw.get("pid"), _parse_moment(raw.get("at"))
        if not isinstance(pid, int) or isinstance(pid, bool) or at is None:
            return None
        return pid, at


def _parse_moment(text):
    """時差付きの日時を読む。時差が無ければ日本時間とみなす。読めなければ None"""
    if not isinstance(text, str):
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return weeks.to_tokyo(parsed)


# 週次レポート係の状態のファイル


def valid_state(raw):
    if not isinstance(raw, dict) or raw.get("version") != STATE_VERSION or not isinstance(raw.get("weeks"), dict):
        return False
    for name, entry in raw["weeks"].items():
        if weeks.parse_week_name(name) is None or not isinstance(entry, dict) or entry.get("result") not in RESULTS:
            return False
    return True


def target_weeks(done, now):
    """定期の作成の対象の週を古い順に。weeks の最後の週より後で、金曜17時を過ぎ、月曜が28日以内の週。
    weeks が空なら直近に過ぎた金曜17時の週だけ"""
    latest = weeks.latest_closed_week(now)
    if not done:
        return [latest]
    last = max(weeks.parse_week_name(name) for name in done)
    return [week for week in weeks.weeks_between(last, latest) if weeks.within_retention(week, now)]


# 作り直しの依頼


class InvalidRequest(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def read_request(path):
    """依頼ファイルを読み、(週, 依頼を受け付けた日時) を返す。形が読めなければ InvalidRequest"""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise InvalidRequest("json") from None
    if not isinstance(raw, dict):
        raise InvalidRequest("json")
    week = weeks.parse_week_name(raw.get("week"))
    if week is None:
        raise InvalidRequest("week")
    requested_at = _parse_moment(raw.get("requestedAt"))
    if requested_at is None:
        raise InvalidRequest("requestedAt")
    return week, requested_at


def _request_files(folder):
    if not folder.exists():
        return []
    return sorted(path for path in folder.iterdir()
                  if path.is_file() and path.suffix == ".json" and not path.name.startswith("."))


# 組み上げ


class Runner:
    def __init__(self, deps, lock):
        self.deps = deps
        self.paths = deps.data_paths
        self.lock = lock
        self.done = {}
        self.week = None             # 処理中の週(思わぬ失敗の本文に使う)
        self.periodic = False        # 定期の作成の途中か
        self.request_path = None     # 処理中の依頼ファイル

    def run(self):
        self.done = self.load_state()
        targets = target_weeks(self.done, self.deps.now())
        LOGGER.info("targets weeks=%s", ",".join(week.name for week in targets) or "-")
        self.process_requests(targets)
        for week in list(targets):
            self.build_periodic(week, TRIGGER_SCHEDULE)
        # ロックを外す前に依頼のフォルダをもう一度見る。対象の週の一覧は決め直さない
        while self.process_requests(targets):
            pass

    # 状態のファイル

    def load_state(self):
        path = self.paths.report_state
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            raw = None
        if valid_state(raw):
            return dict(raw["weeks"])
        backup = self.paths.root / f"report-state.broken-{weeks.to_tokyo(self.deps.now()):%Y%m%d-%H%M%S}.json"
        os.replace(path, backup)
        LOGGER.warning("state unreadable backup=%s", backup)
        self.notify(publish.state_backed_up_body(backup))
        return {}

    def record(self, week, outcome):
        self.done[week.name] = {"result": outcome.result, "at": timestamp(self.deps.now()), "notified": outcome.notified}
        _write_json(self.paths.report_state, {"version": STATE_VERSION, "weeks": self.done})
        LOGGER.info("state week=%s result=%s notified=%s", week.name, outcome.result, str(outcome.notified).lower())

    # 依頼

    def process_requests(self, targets):
        """依頼を古い順に1件ずつ処理する。処理した数を返す"""
        handled = 0
        for path in _request_files(self.paths.requests):
            self.request_path = path
            self.handle_request(path, targets)
            self.request_path = None
            self.lock.refresh()
            handled += 1
        return handled

    def handle_request(self, path, targets):
        try:
            week, requested_at = read_request(path)
        except InvalidRequest as error:
            LOGGER.warning("request invalid file=%s reason=%s", path.name, error.reason)
            self.remove_request(path)
            return
        if week.name not in self.done and weeks.is_closed(week, self.deps.now()):
            if week in targets:
                targets.remove(week)
            self.build_periodic(week, TRIGGER_REQUEST)
        else:
            self.build_remake(week, requested_at)
        self.remove_request(path)

    def remove_request(self, path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        LOGGER.info("request removed file=%s", path.name)

    # 1週分の作成

    def build_periodic(self, week, trigger):
        self.week, self.periodic = week, True
        LOGGER.info("start trigger=%s kind=schedule week=%s", trigger, week.name)
        outcome = self.build(week, week.closing, partial=False, notify_no_records=trigger == TRIGGER_REQUEST)
        self.record(week, outcome)
        self.week, self.periodic = None, False

    def build_remake(self, week, requested_at):
        self.week = week
        end, partial = render_html.report_period_end(week.monday, requested_at)
        LOGGER.info("start trigger=request kind=remake week=%s partial=%s", week.name, str(partial).lower())
        self.build(week, end, partial=partial, notify_no_records=True)
        self.week = None

    def build(self, week, end, partial, notify_no_records):
        """手順5〜14。範囲は月曜0時から end まで"""
        start = week.monday
        status = render_html.read_status_inputs(self.paths, start, end)
        if status.last_kind is None:
            LOGGER.info("skip week=%s reason=noRecords", week.name)
            notified = self.notify(publish.remake_no_records_body(week.name)) if notify_no_records else False
            return Outcome(NO_RECORDS, notified)
        week_aggregate = aggregate.aggregate_week(self.paths, start, end)
        totals = week_aggregate.totals
        LOGGER.info("rows read=%d skipped=%d work=%dm meeting=%dm away=%dm excluded=%dm",
                    len(week_aggregate.classified), week_aggregate.skipped,
                    *(totals[key] // 60 for key in aggregate.CATEGORIES))
        memos = records.read_memos(self.paths, start, end)
        source_records, failures = self.read_sources(start, end)
        results = claude_calls.generate_week(
            week.name, start, end, week_aggregate, memos, source_records, self.deps.collect_reusable(), status.config,
            run_headless=self.deps.run_headless, logger=LOGGER)
        now = self.deps.now()
        report = render_html.ReportInput(
            week=week.name,
            period_start=start,
            period_end=end,
            partial=partial,
            created_at=now,
            current_week=week == weeks.current_week(now),
            aggregate=week_aggregate,
            outcome=results.status,
            proposals=results.proposals,
            summaries=results.summaries,
            exclusions=None if results.exclusions.status == exclusions.FAILED else results.exclusions.candidates,
            exclusion_windows=exclusions.build_exclusion_materials(week.name, week_aggregate).windows,
            status=status,
            unreadable_sources=failures,
        )
        published = publish.publish_report(
            render_html.render_report(report), week.name, render_html.week_state(results.status, results.proposals),
            len(results.proposals), local_dir=self.paths.reports, onedrive_dir=self.deps.onedrive_dir,
            notifier=self.deps.notifier, sleep=self.deps.sleep, copy=self.deps.copy)
        result = SAVE_FAILED if published.save_failed else results.status
        LOGGER.info("week=%s result=%s saved=%s notified=%s", week.name, result, str(published.saved).lower(),
                    str(published.notified).lower())
        return Outcome(result, published.notified)

    def read_sources(self, start, end):
        """4つの既存の作業の記録を独立に読む。読めなかった記録は使わずに名前と理由を控える"""
        found, failures = [], []
        readers = (
            (("jira", "confluence"), self.deps.read_atlassian, lambda result: result.jira + result.confluence),
            (("claudeCode",), self.deps.read_claude_code, lambda result: result.requests),
            (("minutes",), self.deps.read_minutes, lambda result: result.minutes),
        )
        for sources, reader, pick in readers:
            try:
                result = reader(start, end)
                picked = list(pick(result))
                failed = list(result.failures)
            except Exception as error:  # 1つの記録の思わぬ失敗でレポートを止めない
                LOGGER.warning("source=%s failed reason=unexpected error=%s", ",".join(sources), type(error).__name__)
                failures.extend({"source": source, "site": None, "reason": "unreadable"} for source in sources)
                continue
            for source in sources:
                LOGGER.info("source=%s count=%d", source, sum(1 for record in picked if record.get("source") == source))
            for failure in failed:
                LOGGER.warning("source=%s site=%s failed reason=%s", failure.get("source"), failure.get("site") or "-",
                               failure.get("reason"))
            found.extend(picked)
            failures.extend(failed)
        return found, failures

    # 通知と思わぬ失敗

    def notify(self, body):
        return publish.send_notification(body, notifier=self.deps.notifier, sleep=self.deps.sleep)

    def handle_unexpected(self, error):
        frame = traceback.extract_tb(error.__traceback__)[-1] if error.__traceback__ else None
        where = f"{Path(frame.filename).name}:{frame.lineno}" if frame else "-"
        LOGGER.error("unexpected error=%s where=%s week=%s", type(error).__name__, where,
                     self.week.name if self.week else "-")
        body = (publish.unexpected_failure_body(self.week.name) if self.week
                else publish.unexpected_failure_before_week_body())
        notified = _notify_safely(body, self.deps)
        if self.periodic and self.week is not None:
            try:
                self.record(self.week, Outcome(FAILED, notified))
            except Exception as write_error:  # 状態のファイルに書けなくてもロックは外す
                LOGGER.error("state write failed error=%s", type(write_error).__name__)
        if self.request_path is not None:
            try:
                self.remove_request(self.request_path)
            except OSError as remove_error:
                LOGGER.error("request remove failed file=%s error=%s", self.request_path.name, type(remove_error).__name__)


def _notify_safely(body, deps):
    try:
        return publish.send_notification(body, notifier=deps.notifier, sleep=deps.sleep)
    except Exception as error:  # 通知の部品が読み込めないときも、ロックを外すところまで進める
        LOGGER.error("notify failed error=%s", type(error).__name__)
        return False


def run(deps):
    """ロックを取って組み上げた手順を動かす。終了コード(思わぬ例外で止まったら1)を返す"""
    began = time.monotonic()
    lock = Lock(deps)
    try:
        acquired = lock.acquire()
    except Exception as error:
        LOGGER.error("lock failed error=%s", type(error).__name__)
        _notify_safely(publish.unexpected_failure_before_week_body(), deps)
        return 1
    if not acquired:
        LOGGER.info("skip reason=locked")
        return 0
    runner = Runner(deps, lock)
    code = 0
    try:
        runner.run()
    except Exception as error:
        runner.handle_unexpected(error)
        code = 1
    finally:
        lock.release()
    LOGGER.info("done seconds=%d", round(time.monotonic() - began))
    return code


# ログ


class LogFormatter(logging.Formatter):
    """appendix.md「ログの書式」: 日本時間の日時・レベル(INFO / WARN / ERROR)・英語の短い文と キー=値"""

    def format(self, record):
        moment = datetime.fromtimestamp(record.created, weeks.tokyo()).isoformat(timespec="seconds")
        level = LOG_LEVELS.get(record.levelname, record.levelname)
        return f"{moment} {level} {record.getMessage()}"


def configure_logging(stream=None):
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(LogFormatter())
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False
    return handler


def main():
    configure_logging()
    onedrive_write.allow_dataless_materialization()
    try:
        data_paths = paths.data_paths()
    except paths.SyncFolderError:
        LOGGER.error("data folder rejected reason=syncFolder")
        _notify_safely(publish.unexpected_failure_before_week_body(), Deps(data_paths=None))
        return 1
    return run(Deps(data_paths=data_paths))


if __name__ == "__main__":
    sys.exit(main())
