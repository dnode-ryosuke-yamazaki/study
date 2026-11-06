#!/usr/bin/env python3
"""実行係の入口。launchd(定時・追い実行)と運営者の手元ターミナル(手動実行)から起動する。

    python3 launchd/runner.py <アプリ名> <系統 publish|review> [--manual]

終了コード: 0=成功・起動しなかった(成功済み・失敗確定の定時の回・ロック中)、1=バッチが一時的な失敗、
2=再試行しても直らない失敗・未登録・実行係自身のエラー。
処理の順は design.md「起動前の判定」「バッチの起動と成否の判定」「再実行の判定と失敗の引き渡し」。
"""

import argparse
import os
import re
import sys
import traceback

LAUNCHD_DIR = os.path.dirname(os.path.abspath(__file__))
if LAUNCHD_DIR not in sys.path:
    sys.path.insert(0, LAUNCHD_DIR)

from digest_runner import calendar as cal  # noqa: E402
from digest_runner import environment, handoff, judge, launch, lock, registry, retention, state, summary_log  # noqa: E402

APP_ROOT = os.path.dirname(LAUNCHD_DIR)
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _parse(argv):
    parser = argparse.ArgumentParser(prog="runner.py", description="digest-platform の実行係")
    parser.add_argument("app")
    parser.add_argument("kind")
    parser.add_argument("--manual", action="store_true")
    return parser.parse_args(argv)


def _say(message):
    print(message, file=sys.stderr)


def main(argv=None, env=None, clock=None, app_root=None, registry_path=None, home=None):
    args = _parse(sys.argv[1:] if argv is None else argv)
    env = dict(os.environ if env is None else env)
    clock = clock or cal.now_jst
    app_root = app_root or APP_ROOT
    registry_path = registry_path or os.path.join(app_root, "launchd", "apps.json")
    home = home or env.get("HOME") or os.path.expanduser("~")
    if not _NAME.match(args.app) or not _NAME.match(args.kind):
        _say(f"アプリ名・系統に使えない文字があります: {args.app} {args.kind}")
        return 2
    data_dir = env.get("DIGEST_DATA_DIR") or os.path.join(home, "Library", "Application Support", "digest", args.app)
    summary = os.path.join(data_dir, f"runner-{args.kind}.log")

    try:
        registration = registry.load(registry_path).get(args.app, args.kind)
    except (registry.Unregistered, registry.RegistryBroken) as e:
        _say(f"未登録: {e}")
        try:
            summary_log.finished(summary, "unregistered", None, None, None, None, None)
        except OSError as log_error:
            _say(f"要約ログに書けません: {log_error}")
        return 2

    lock_dir = os.path.join(data_dir, "lock", args.kind)
    progress = {}
    try:
        if not lock.acquire(lock_dir):
            summary_log.finished(summary, "locked", None, None, None, None, None)
            return 0
    except OSError as e:
        _say(f"ロックを取れません: {type(e).__name__}: {e}")
        return 2
    try:
        run = _Run(args, env, clock, app_root, home, data_dir, summary, registration, progress)
        return run.execute()
    except Exception as e:  # 実行係自身の想定外の例外。試行に数えず実行状態も変えない
        traceback.print_exc(file=sys.stderr)
        try:
            summary_log.warning(summary, "実行係のエラー", f"{type(e).__name__}: {e}")
            summary_log.finished(
                summary, "runner_error", progress.get("date"), progress.get("edition"),
                progress.get("attempt"), progress.get("status"), progress.get("log"),
            )
        except Exception as log_error:
            _say(f"要約ログに書けません: {log_error}")
        return 2
    finally:
        lock.release(lock_dir)


class _Run:
    def __init__(self, args, env, clock, app_root, home, data_dir, summary, registration, progress):
        self.args = args
        self.env = env
        self.clock = clock
        self.app_root = app_root
        self.home = home
        self.data_dir = data_dir
        self.summary = summary
        self.reg = registration
        self.progress = progress
        self.manual = args.manual
        self.context = {"app": args.app, "kind": args.kind, "manual": self.manual, "summary_path": summary}

    def deliver(self, data, failure_kind, final_reason, failed_at, log_path, warning=False):
        failure = handoff.build(self.context, data, failure_kind, final_reason, failed_at, log_path)
        result = handoff.notify(self.judge_fn, failure)
        handoff.record(data, result, failure, warning=warning, summary_path=self.summary)

    def execute(self):
        now = self.clock()
        kind = self.args.kind
        date, edition = cal.resolve(self.reg, now)
        self.progress.update(date=date, edition=edition)
        base = cal.base_date(now).isoformat()

        _deleted, failed = retention.sweep(self.data_dir, now)
        for path in failed:
            summary_log.warning(self.summary, "古い記録を消せません", path)

        self.judge_fn = handoff.resolve_judge_fn(self.env)
        runs_dir = os.path.join(self.data_dir, "runs", kind)
        touched = handoff.expire_stale(runs_dir, base, date, self.judge_fn, self.context, now=now)
        touched += handoff.expire_missing(runs_dir, self.reg, date, now, self.judge_fn, self.context)
        handoff.renotify(runs_dir, date, now, self.judge_fn, self.context, exclude=touched)

        state_path = state.path_for(self.data_dir, kind, date, edition)
        identity = dict(app=self.args.app, kind=kind, date=date, edition=edition, max_attempts=self.reg["maxAttempts"])
        try:
            data = state.load(state_path, **identity)
        except state.StateBroken as e:
            return self.rewrite_corrupt(state_path, identity, now, e)

        status = data["status"]
        scheduled = state.scheduled_attempts(data)
        if status == "succeeded":
            summary_log.finished(self.summary, "already_succeeded", date, edition, None, status, None)
            return 0
        if not self.manual and (status == "failed" or scheduled >= self.reg["maxAttempts"]):
            summary_log.finished(self.summary, "failed_final", date, edition, None, status, None)
            return 0
        return self.launch(data, state_path, now, date, edition, scheduled)

    def rewrite_corrupt(self, state_path, identity, now, error):
        moved = state.quarantine(state_path, now)
        summary_log.warning(self.summary, "壊れた実行状態を退避しました", f"{moved}: {error}")
        data = state.empty(**identity)
        state.set_status(data, "failed", "corrupt")
        self.deliver(data, "permanent_failure", "corrupt", now, self.summary)
        state.save(state_path, data)
        summary_log.finished(
            self.summary, "corrupt_state", identity["date"], identity["edition"], 0, "failed", self.summary,
            became_failed=True,
        )
        return 2

    def launch(self, data, state_path, now, date, edition, scheduled):
        kind = self.args.kind
        number = scheduled + 1
        label = f"manual-{cal.to_jst(now).strftime('%H%M%S')}" if self.manual else str(number)
        shown = "manual" if self.manual else number
        stem = state.file_stem(date, edition)
        log_path = os.path.join(self.data_dir, "logs", kind, f"{stem}-{label}.log")
        claude_io_dir = os.path.join(self.data_dir, "claude-io", kind, stem)
        self.progress.update(attempt=shown, status=data["status"], log=log_path)
        summary_log.started(self.summary, dict(app=self.args.app, kind=kind, date=date, edition=edition, attempt=shown))

        bundle = environment.ca_bundle(self.home)
        header = dict(app=self.args.app, kind=kind, date=date, edition=edition, attempt=label, manual=self.manual,
                      claudeIoDir=claude_io_dir, caBundle=bundle)
        try:
            binaries = environment.find_binaries(self.env, self.home)
            tsx = environment.find_tsx(self.app_root)
        except environment.BinaryNotFound as e:
            launched = launch.not_started(log_path, header, self.reg["command"], self.app_root, str(e))
        else:
            command = [part.replace("{node}", binaries["node"]).replace("{tsx}", tsx) for part in self.reg["command"]]
            batch_env = environment.build(self.env, dict(
                app=self.args.app, kind=kind, date=date, edition=edition, attempt=label, manual=self.manual,
                claude_io_dir=claude_io_dir, data_dir=self.data_dir, binaries=binaries, ca_bundle=bundle,
            ))
            launched = launch.run(command, self.app_root, batch_env, log_path, header=header)

        artifacts = [os.path.join(self.app_root, p) for p in judge.expand_artifacts(self.reg["artifacts"], date, edition)]
        if launched["start_failed"]:
            verdict = {"result": "permanent_failure", "missing": ["exit_code", "marker"] + ["artifact:" + a for a in artifacts], "warnings": []}
        else:
            verdict = judge.evaluate(launched["exit_code"], launched["output_lines"], artifacts,
                                     launched["started_at"], launched["timed_out"])
        result = verdict["result"]
        launch.write_result(log_path, launched, marker="marker" not in verdict["missing"],
                            artifacts_ok=not any(m.startswith("artifact:") for m in verdict["missing"]),
                            result=result, missing=verdict["missing"])

        ended_at = cal.to_jst(launched["ended_at"]).isoformat(timespec="seconds")
        state.add_attempt(data, {
            "no": None if self.manual else number,
            "manual": self.manual,
            "startedAt": cal.to_jst(launched["started_at"]).isoformat(timespec="seconds"),
            "endedAt": ended_at,
            "result": result,
            "missing": verdict["missing"],
            "warnings": verdict["warnings"],
            "logPath": log_path,
        })

        became_failed = False
        if result == "succeeded":
            state.set_status(data, "succeeded")
        elif not self.manual:
            reason = self.final_reason(result, number, now, date)
            if reason:
                state.set_status(data, "failed", reason)
                became_failed = True
            else:
                state.set_status(data, "retry_pending")

        if became_failed:
            self.deliver(data, result, data["finalReason"], ended_at, log_path)
        elif self.manual and result != "succeeded":
            self.deliver(data, result, "manual", ended_at, log_path)
        if result == "succeeded" and verdict["warnings"]:
            self.deliver(data, verdict["warnings"], "warning", ended_at, log_path, warning=True)

        state.save(state_path, data)
        summary_log.finished(self.summary, result, date, edition, shown, data["status"], log_path,
                             became_failed=became_failed)
        if result == "succeeded":
            return 0
        return 2 if result == "permanent_failure" else 1

    def final_reason(self, result, number, now, date):
        """定時の失敗のあと、当日を失敗確定にする理由(再実行待ちなら None)。"""
        if result == "permanent_failure":
            return "permanent"
        if number >= self.reg["maxAttempts"]:
            return "exhausted"
        if now >= cal.last_chance_at(date):
            return "last_chance"
        return None


if __name__ == "__main__":
    sys.exit(main())
