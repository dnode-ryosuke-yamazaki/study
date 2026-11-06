"""バッチの起動・詳細ログへの出力・60分の打ち切り。

バッチは新しいプロセスグループで起動し、上限を過ぎたらグループに TERM を送り、
5秒待って残っていれば KILL を送る。詳細ログの先頭にはパスと識別子だけを書き、
環境変数の一覧は書かない(書式は appendix「詳細ログの先頭と末尾」)。
"""

import os
import signal
import subprocess
import threading
import time

from . import calendar as cal
from .state import ensure_private_dir

BATCH_TIMEOUT_SECONDS = 60 * 60
KILL_GRACE_SECONDS = 5


def now():
    return cal.now_jst()


def _stamp(moment):
    return moment.isoformat(timespec="seconds")


def _open_log(log_path):
    ensure_private_dir(os.path.dirname(log_path))
    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.chmod(log_path, 0o600)
    return fd


def _write(fd, text):
    os.write(fd, text.encode("utf-8"))


def _header_text(started_at, header, command, cwd):
    edition = header.get("edition") or "-"
    manual = "true" if header.get("manual") else "false"
    return (
        "=== digest runner ===\n"
        f"startedAt={_stamp(started_at)}\n"
        f"app={header['app']} kind={header['kind']} date={header['date']} edition={edition}"
        f" attempt={header['attempt']} manual={manual}\n"
        f"command={' '.join(command)}\n"
        f"cwd={cwd}\n"
        f"claudeIoDir={header.get('claudeIoDir', '-')}\n"
        f"caBundle={header.get('caBundle', '-')}\n"
        "=== batch output ===\n"
    )


def _group_alive(pgid):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _stop_group(proc):
    pgid = proc.pid
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + KILL_GRACE_SECONDS
    while time.monotonic() < deadline:
        proc.poll()
        if proc.returncode is not None and not _group_alive(pgid):
            break
        time.sleep(0.1)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def run(command, cwd, env, log_path, timeout_seconds=BATCH_TIMEOUT_SECONDS, header=None):
    """バッチを1回動かし、終了コード・打ち切りかどうか・開始と終了の時刻・標準出力の行と最終行を返す。"""
    fd = _open_log(log_path)
    started_at = now()
    lines = []
    result = {
        "exit_code": None,
        "timed_out": False,
        "start_failed": False,
        "started_at": started_at,
        "ended_at": started_at,
        "output_lines": lines,
        "last_line": None,
    }
    try:
        if header is not None:
            _write(fd, _header_text(started_at, header, command, cwd))
        try:
            proc = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=fd,
                start_new_session=True,
            )
        except OSError as e:
            result["start_failed"] = True
            result["ended_at"] = now()
            _write(fd, f"起動に失敗しました: {type(e).__name__}: {e}\n")
            return result

        def pump():
            for raw in iter(proc.stdout.readline, b""):
                os.write(fd, raw)
                lines.append(raw.decode("utf-8", "replace").rstrip("\r\n"))

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        try:
            proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            result["timed_out"] = True
            _stop_group(proc)
        reader.join(timeout=KILL_GRACE_SECONDS)
        proc.stdout.close()
        result["exit_code"] = proc.returncode
        result["ended_at"] = now()
        non_empty = [line for line in lines if line.strip()]
        result["last_line"] = non_empty[-1].strip() if non_empty else None
        return result
    finally:
        os.close(fd)


def write_result(log_path, launched, marker, artifacts_ok, result, missing):
    """詳細ログの末尾に、終了時刻・終了コード・成功マーカーと生成物の有無・判定結果を書く。"""
    exit_code = launched.get("exit_code")
    text = (
        "=== result ===\n"
        f"endedAt={_stamp(launched['ended_at'])} exitCode={'-' if exit_code is None else exit_code}"
        f" marker={'ok' if marker else 'missing'} artifacts={'ok' if artifacts_ok else 'missing'} result={result}\n"
    )
    if missing:
        text += f"missing={','.join(missing)}\n"
    fd = _open_log(log_path)
    try:
        _write(fd, text)
    finally:
        os.close(fd)


def not_started(log_path, header, command, cwd, reason):
    """バッチを起動できなかった(実行ファイルが見つからない等)ことを詳細ログに書き、run と同じ形の結果を返す。"""
    fd = _open_log(log_path)
    started_at = now()
    try:
        _write(fd, _header_text(started_at, header, command, cwd))
        _write(fd, f"起動に失敗しました: {reason}\n")
    finally:
        os.close(fd)
    return {
        "exit_code": None,
        "timed_out": False,
        "start_failed": True,
        "started_at": started_at,
        "ended_at": now(),
        "output_lines": [],
        "last_line": None,
    }
