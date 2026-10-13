"""操作スクリプト。記録の操作Skillが呼び、結果を標準出力に JSON で返す(appendix.md「操作スクリプトの呼び方」)。

    python3 -m routine_work_finder.control start --until 2026-10-31T18:00:00+09:00
    python3 -m routine_work_finder.control stop
    python3 -m routine_work_finder.control status
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

from routine_work_finder import config_store, paths, records

JST = records.JST
RECORDER_STALE_AFTER = timedelta(seconds=30)
SECONDS_PER_LINE = 5
MAX_GAPS = 3
NOTICE_RECORDER_NOT_RUNNING = "記録係が動いていません。README のセットアップの手順で、記録係を launchd に登録してください"
NOTICE_ACCESSIBILITY = "システム設定の「プライバシーとセキュリティ → アクセシビリティ」で記録係(rwf-recorder)をオンにしてください"


class ControlError(Exception):
    """操作を断る。error は結果の "error" に入れる値"""

    def __init__(self, error, message, **extra):
        super().__init__(message)
        self.error = error
        self.message = message
        self.extra = extra


class Context:
    def __init__(self, data_paths, now):
        self.paths = data_paths
        self.now = now

    def log(self, level, message):
        """control.log に1行書き足す(appendix.md「ログの書式」)。ことば・アプリ名・メモの文は書かない"""
        descriptor = os.open(self.paths.control_log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as file:
            file.write(f"{timestamp(self.now)} {level} {message}\n")

    def ensure_writable(self, write_config=False):
        """データフォルダと control.log(設定を書き換える操作では config.json.tmp も)に書けるかを、書く前に試して確かめる"""
        try:
            config_store.ensure_data_folder(self.paths)
            descriptor = os.open(self.paths.control_log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            os.close(descriptor)
            if write_config:
                probe = self.paths.root / "config.json.tmp"
                descriptor = os.open(probe, os.O_WRONLY | os.O_CREAT, 0o600)
                os.close(descriptor)
                probe.unlink()
        except OSError as error:
            raise ControlError("dataFolderUnwritable", f"データフォルダに書けません({error.strerror})") from error

    def load_config_for_update(self):
        """設定を書き換える操作のための読み取り。無ければ初期値、読めなければ断る"""
        result = config_store.read_config(self.paths)
        if result.state == "unreadable":
            raise ControlError("configUnreadable", f"設定ファイルが読めないため書き換えません(理由: {result.reason})。"
                                                   "設定ファイルを直すか消してください")
        return result.config if result.state == "ok" else config_store.default_config()


def timestamp(moment):
    return moment.astimezone(JST).isoformat(timespec="seconds")


def parse_timestamp(text):
    """時差付きの日時を読む。時差が無ければ日本時間とみなす。読めなければ None"""
    try:
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=JST) if parsed.tzinfo is None else parsed


def read_recorder_status(data_paths):
    try:
        status = json.loads(data_paths.status.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return status if isinstance(status, dict) else None


def recorder_running(status, now):
    updated_at = parse_timestamp(status.get("updatedAt")) if status else None
    return updated_at is not None and now - updated_at < RECORDER_STALE_AFTER


def recorder_notices(data_paths, now):
    status = read_recorder_status(data_paths)
    notices = []
    if not recorder_running(status, now):
        notices.append(NOTICE_RECORDER_NOT_RUNNING)
    if status is not None and status.get("accessibilityGranted") is False:
        notices.append(NOTICE_ACCESSIBILITY)
    return notices


def describe_moment(moment):
    local = moment.astimezone(JST)
    return f"{local.month}月{local.day}日 {local:%H:%M}"


def command_start(context, args):
    if args.until is None or parse_timestamp(args.until) is None:
        raise ControlError("missingEndsAt", "終わりの日時を教えてください(例: 10月31日18時まで)")
    ends_at = parse_timestamp(args.until)
    if ends_at <= context.now:
        raise ControlError("pastEndsAt", f"{describe_moment(ends_at)} は過去の日時です。これから先の終わりの日時を教えてください")
    context.ensure_writable(write_config=True)
    config = context.load_config_for_update()
    config["endsAt"] = timestamp(ends_at)
    config["stoppedAt"] = None
    config_store.write_config(context.paths, config)
    context.log("INFO", f"start endsAt={config['endsAt']}")
    return {"message": f"{describe_moment(ends_at)} まで記録します",
            "notices": recorder_notices(context.paths, context.now),
            "data": {"endsAt": config["endsAt"]}}


def command_stop(context, args):
    context.ensure_writable(write_config=True)
    config = context.load_config_for_update()
    config["endsAt"] = None
    config["stoppedAt"] = timestamp(context.now)
    config_store.write_config(context.paths, config)
    context.log("INFO", "stop")
    return {"message": "記録を止めました", "notices": [], "data": {"stoppedAt": config["stoppedAt"]}}


def command_status(context, args):
    """状態を返す。何も書かない(design.md「記録を始める・止める・状態を確かめる」手順8)"""
    now = context.now
    config_read = config_store.read_config(context.paths)
    ends_at = parse_timestamp(config_read.config["endsAt"]) if config_read.state == "ok" and config_read.config["endsAt"] else None
    status = read_recorder_status(context.paths)
    local_now = now.astimezone(JST)
    today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_lines = records.read_records(context.paths, today, now).lines
    recorded_seconds = sum(SECONDS_PER_LINE for line in today_lines if line["kind"] in ("sample", "excluded"))
    gaps = records.find_gaps(context.paths, today - timedelta(days=1), now)
    latest_gaps = [{"start": timestamp(start), "end": timestamp(end)} for start, end in reversed(gaps)][:MAX_GAPS]
    if config_read.state == "unreadable":
        config_error = config_read.reason
    else:
        config_error = status.get("configError") if status else None
    recording = ends_at is not None and ends_at > now
    data = {
        "recording": recording,
        "endsAt": timestamp(ends_at) if ends_at else None,
        "todayRecordedSeconds": recorded_seconds,
        "gaps": latest_gaps,
        "recorderRunning": recorder_running(status, now),
        "accessibilityGranted": status.get("accessibilityGranted") if status else None,
        "configError": config_error,
    }
    return {"message": status_message(data), "notices": recorder_notices(context.paths, now), "data": data}


def status_message(data):
    if data["configError"]:
        return f"設定ファイルが読めません(理由: {data['configError']})。設定ファイルを直すか消してください"
    if data["recording"]:
        ends_at = parse_timestamp(data["endsAt"])
        return f"記録中です({describe_moment(ends_at)} まで)"
    return "停止中です"


COMMANDS = {"start": command_start, "stop": command_stop, "status": command_status}


def build_parser():
    parser = argparse.ArgumentParser(prog="routine_work_finder.control")
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start")
    start.add_argument("--until")
    subparsers.add_parser("stop")
    subparsers.add_parser("status")
    return parser


def run(argv, now=None, environ=None):
    """引数を受けて操作し、結果の dict を返す。テストからは now と environ(RWF_DATA_DIR)を渡す"""
    now = now or datetime.now(JST)
    try:
        args = build_parser().parse_args(argv)
    except SystemExit:
        return {"ok": False, "error": "badRequest", "message": "操作スクリプトの呼び方が違います"}
    try:
        context = Context(paths.data_paths(environ=environ), now)
        result = COMMANDS[args.command](context, args)
    except paths.SyncFolderError as error:
        return {"ok": False, "error": "dataFolderUnwritable", "message": str(error)}
    except ControlError as error:
        return {"ok": False, "error": error.error, "message": error.message, **error.extra}
    return {"ok": True, **result}


def main(argv=None, now=None, environ=None):
    result = run(sys.argv[1:] if argv is None else argv, now=now, environ=environ)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
