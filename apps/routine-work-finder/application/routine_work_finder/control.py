"""操作スクリプト。記録の操作Skillが呼び、結果を標準出力に JSON で返す(appendix.md「操作スクリプトの呼び方」)。

    python3 -m routine_work_finder.control start --until 2026-10-31T18:00:00+09:00
    python3 -m routine_work_finder.control stop
    python3 -m routine_work_finder.control status
"""

import argparse
import json
import os
import secrets
import sys
from datetime import datetime, timedelta
from pathlib import Path

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

    def ensure_writable(self, write_config=False, inputs=None, memo_append=None, memo_replace=None):
        """データフォルダと control.log(設定を書き換える操作では config.json.tmp、メモを書き足す操作ではメモのフォルダと
        その日のメモのファイル、メモを消す操作ではメモのフォルダの一時ファイルも)に書けるかを、書く前に試して確かめる。
        書けなければ入力ファイルは消さずに残し、その絶対パスを結果に入れる(inputs は {結果のキー: パス})"""
        try:
            config_store.ensure_data_folder(self.paths)
            descriptor = os.open(self.paths.control_log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            os.close(descriptor)
            if write_config:
                probe_replace(self.paths.root / "config.json.tmp")
            if memo_append is not None:
                # 確かめるために作ったフォルダ・ファイルは消す(断ったときに空のものを残さない。書くときに作り直す)
                created_folder = not self.paths.memos.exists()
                if created_folder:
                    self.paths.memos.mkdir(mode=0o700)
                created_file = not memo_append.exists()
                descriptor = os.open(memo_append, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                os.close(descriptor)
                if created_file:
                    memo_append.unlink()
                if created_folder:
                    self.paths.memos.rmdir()
            if memo_replace is not None:
                probe_replace(memo_replace.with_name(memo_replace.name + ".tmp"))
        except OSError as error:
            extra = {key: str(path) for key, path in (inputs or {}).items() if path is not None}
            raise ControlError("dataFolderUnwritable", f"データフォルダに書けません({error.strerror})", **extra) from error

    def load_config_for_update(self):
        """設定を書き換える操作のための読み取り。無ければ初期値、読めなければ断る"""
        result = config_store.read_config(self.paths)
        if result.state == "unreadable":
            raise ControlError("configUnreadable", f"設定ファイルが読めないため書き換えません(理由: {result.reason})。"
                                                   "設定ファイルを直すか消してください")
        return result.config if result.state == "ok" else config_store.default_config()


def probe_replace(temporary):
    """一時ファイルを作って消せるか(名前を付け替えて書き換えられるか)を試す"""
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT, 0o600)
    os.close(descriptor)
    temporary.unlink()


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


def input_path(text):
    return Path(text).expanduser().resolve() if text else None


def read_input_text(path):
    """入力ファイルを読み、読めたら消す。無い・読めないときは badInputFile"""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ControlError("badInputFile", f"入力ファイルが読めません: {path}") from error
    path.unlink(missing_ok=True)
    return text


def read_input_json(path, required_key):
    """--input-file の JSON を読む。形が違えば badInputFile"""
    try:
        content = json.loads(read_input_text(path))
    except ValueError as error:
        raise ControlError("badInputFile", "入力ファイルが JSON として読めません") from error
    if not isinstance(content, dict) or not isinstance(content.get(required_key), str):
        raise ControlError("badInputFile", f"入力ファイルに {required_key} がありません")
    return content


def write_text_replacing(target, text):
    """同じフォルダの一時ファイル(600)に書いてから名前を付け替える"""
    temporary = target.with_name(target.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(text)
    os.replace(temporary, target)


def exclusion_lists(config):
    return {"excludedApps": config["excludedApps"], "excludedTitleWords": config["excludedTitleWords"]}


def app_exists(config, name, bundle_id):
    return any(app["name"] == name or (bundle_id and app.get("bundleId") == bundle_id) for app in config["excludedApps"])


def command_exclude_app(context, args):
    path = input_path(args.input_file)
    context.ensure_writable(write_config=True, inputs={"inputFile": path})
    content = read_input_json(path, "name")
    name = content["name"].strip()
    bundle_id = content.get("bundleId")
    if bundle_id is not None and not isinstance(bundle_id, str):
        raise ControlError("badInputFile", "入力ファイルの bundleId が文字列ではありません")
    if not name:
        raise ControlError("emptyWord", "アプリ名が空です")
    config = context.load_config_for_update()
    if args.action == "add":
        if app_exists(config, name, bundle_id):
            return {"message": f"{name} はすでに記録しないアプリにあります", "notices": [], "data": exclusion_lists(config)}
        config["excludedApps"].append({"name": name, "bundleId": bundle_id})
        message = f"{name} を記録しないアプリに足しました。次の記録から外します"
    else:
        remaining = [app for app in config["excludedApps"] if app["name"] != name]
        if len(remaining) == len(config["excludedApps"]):
            raise ControlError("notFound", f"{name} は記録しないアプリにありません", data=exclusion_lists(config))
        config["excludedApps"] = remaining
        message = f"{name} を記録しないアプリから外しました"
    config_store.write_config(context.paths, config)
    context.log("INFO", f"exclude-app {args.action} count=1")
    return {"message": message, "notices": [], "data": exclusion_lists(config)}


def command_exclude_word(context, args):
    path = input_path(args.input_file)
    context.ensure_writable(write_config=True, inputs={"inputFile": path})
    word = read_input_json(path, "word")["word"].strip()
    if not word:
        raise ControlError("emptyWord", "ことばが空です")
    config = context.load_config_for_update()
    words = config["excludedTitleWords"]
    if args.action == "add":
        if word in words:
            return {"message": f"「{word}」はすでに記録しないことばにあります", "notices": [], "data": exclusion_lists(config)}
        words.append(word)
        message = f"「{word}」を記録しないことばに足しました。次の記録から外します"
    else:
        if word not in words:
            raise ControlError("notFound", f"「{word}」は記録しないことばにありません", data=exclusion_lists(config))
        words.remove(word)
        message = f"「{word}」を記録しないことばから外しました"
    config_store.write_config(context.paths, config)
    context.log("INFO", f"exclude-word {args.action} count=1")
    return {"message": message, "notices": [], "data": exclusion_lists(config)}


def command_exclude_list(context, args):
    """今の一覧を返す。設定ファイルが無ければ初期値を返し、ファイルは作らない"""
    result = config_store.read_config(context.paths)
    if result.state == "unreadable":
        raise ControlError("configUnreadable", f"設定ファイルが読めません(理由: {result.reason})")
    config = result.config if result.state == "ok" else config_store.default_config()
    return {"message": "記録しないアプリ・ことばの一覧です", "notices": [], "data": exclusion_lists(config)}


REQUEST_PHRASE = "/routine-work-finder 記録しないものに次を足してください。"
REQUEST_PREFIXES = {"ことば: ": "words", "アプリ: ": "apps"}


def parse_request(text):
    """依頼文を「ことば」「アプリ」に分ける。1行目が決まり文句でなければ badRequest"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != REQUEST_PHRASE:
        raise ControlError("badRequest", "依頼文の1行目が決まり文句ではないため、何も足しませんでした")
    wanted = {"words": [], "apps": []}
    skipped = []
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        kind = next((key for prefix, key in REQUEST_PREFIXES.items() if line.startswith(prefix)), None)
        value = line.split(": ", 1)[1].strip() if kind else ""
        if kind is None or not value:
            skipped.append(stripped)
        elif value not in wanted[kind]:
            wanted[kind].append(value)
    return wanted, skipped


def command_exclude_add(context, args):
    request_path = input_path(args.request_file)
    bundle_path = input_path(args.bundle_ids_file)
    context.ensure_writable(write_config=True, inputs={"inputFile": request_path, "bundleIdsFile": bundle_path})
    wanted, skipped = parse_request(read_input_text(request_path))
    bundle_ids = {}
    if bundle_path is not None:
        try:
            bundle_ids = json.loads(read_input_text(bundle_path))
        except ValueError as error:
            raise ControlError("badInputFile", "バンドルIDの入力ファイルが JSON として読めません") from error
        if not isinstance(bundle_ids, dict) or not all(isinstance(v, str) for v in bundle_ids.values()):
            raise ControlError("badInputFile", "バンドルIDの入力ファイルの形が違います")
    config = context.load_config_for_update()
    added = {"words": [], "apps": []}
    already = {"words": [], "apps": []}
    for word in wanted["words"]:
        (already if word in config["excludedTitleWords"] else added)["words"].append(word)
    for name in wanted["apps"]:
        (already if app_exists(config, name, None) else added)["apps"].append(name)
    if added["words"] or added["apps"]:
        config["excludedTitleWords"].extend(added["words"])
        config["excludedApps"].extend({"name": name, "bundleId": bundle_ids.get(name)} for name in added["apps"])
        config_store.write_config(context.paths, config)
    context.log("INFO", f"exclude added words={len(added['words'])} apps={len(added['apps'])} "
                        f"alreadyExists={len(already['words']) + len(already['apps'])} skipped={len(skipped)}")
    data = {"added": added, "alreadyExists": already, "skippedLines": skipped, **exclusion_lists(config)}
    return {"message": "記録しないものを足しました。次の記録から外します" if added["words"] or added["apps"]
            else "足すものはありませんでした", "notices": [], "data": data}


MEMO_MAX_LENGTH = 2000


def command_memo(context, args):
    if args.action == "add":
        return memo_add(context, input_path(args.input_file))
    if args.action == "list":
        return memo_list(context)
    return memo_delete(context, args.id)


def memo_add(context, path):
    local = context.now.astimezone(JST)
    memo_file = context.paths.memos / f"{local:%Y-%m-%d}.jsonl"
    context.ensure_writable(inputs={"inputFile": path}, memo_append=memo_file)
    text = read_input_json(path, "text")["text"].strip()
    if not text:
        raise ControlError("emptyText", "メモの文が空です")
    if len(text) > MEMO_MAX_LENGTH:
        raise ControlError("tooLong", f"メモは{MEMO_MAX_LENGTH:,}字までです({len(text):,}字)。短くしてから頼んでください")
    memo = {"id": f"{local:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}", "t": timestamp(local), "text": text}
    if not context.paths.memos.exists():
        context.paths.memos.mkdir(mode=0o700)
        os.chmod(context.paths.memos, 0o700)
    descriptor = os.open(memo_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as file:
        file.write(json.dumps(memo, ensure_ascii=False) + "\n")
    context.log("INFO", "memo add")
    return {"message": "メモを残しました", "notices": [], "data": {"id": memo["id"], "t": memo["t"]}}


def memo_list(context):
    """その週(日本時間の月曜0時からの7日間)のメモを返す"""
    local = context.now.astimezone(JST)
    week_start = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    memos = records.read_memos(context.paths, week_start, week_start + timedelta(days=7))
    return {"message": f"今週のメモは{len(memos)}件です", "notices": [],
            "data": {"memos": [{"id": memo["id"], "t": memo["t"], "text": memo["text"]} for memo in memos]}}


def memo_delete(context, memo_id):
    if not memo_id or not records.MEMO_ID_PATTERN.match(memo_id):
        raise ControlError("badRequest", "メモの番号の形が違います")
    path = context.paths.memos / f"{memo_id[0:4]}-{memo_id[4:6]}-{memo_id[6:8]}.jsonl"
    # メモのフォルダがまだ無ければ消すものも無いため、フォルダは確かめない(番号が見つからないと返す)
    context.ensure_writable(memo_replace=path if context.paths.memos.exists() else None)
    # 行は LF だけで分ける(splitlines はメモの文の中の U+2028 などでも行を割る)
    lines = path.read_text(encoding="utf-8").split("\n") if path.exists() else []
    remaining = [line for line in lines if not _is_memo_line(line, memo_id)]
    if len(remaining) == len(lines):
        raise ControlError("notFound", "その番号のメモはありません")
    write_text_replacing(path, "\n".join(remaining))
    context.log("INFO", "memo delete")
    return {"message": "メモを消しました", "notices": [], "data": {"id": memo_id}}


def _is_memo_line(line, memo_id):
    try:
        return json.loads(line).get("id") == memo_id
    except (ValueError, AttributeError):
        return False


COMMANDS = {
    "start": command_start,
    "stop": command_stop,
    "status": command_status,
    "exclude-app": command_exclude_app,
    "exclude-word": command_exclude_word,
    "exclude-list": command_exclude_list,
    "exclude-add": command_exclude_add,
    "memo": command_memo,
}


def build_parser():
    parser = argparse.ArgumentParser(prog="routine_work_finder.control")
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start")
    start.add_argument("--until")
    subparsers.add_parser("stop")
    subparsers.add_parser("status")
    for name in ("exclude-app", "exclude-word"):
        sub = subparsers.add_parser(name)
        sub.add_argument("action", choices=["add", "remove"])
        sub.add_argument("--input-file", required=True)
    subparsers.add_parser("exclude-list")
    exclude_add = subparsers.add_parser("exclude-add")
    exclude_add.add_argument("--request-file", required=True)
    exclude_add.add_argument("--bundle-ids-file")
    memo = subparsers.add_parser("memo")
    memo.add_argument("action", choices=["add", "list", "delete"])
    memo.add_argument("--input-file")
    memo.add_argument("--id")
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
