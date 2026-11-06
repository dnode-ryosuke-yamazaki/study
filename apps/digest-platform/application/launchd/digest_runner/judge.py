"""終了コード・成功マーカー・生成物の3点による成否の判定と失敗の種類。

結果は succeeded / temporary_failure / permanent_failure / timeout。終了コード2は
再試行しても直らない失敗、打ち切りは timeout(一時的な失敗の一種)、それ以外は一時的な失敗。
"""

import os
import re

SUCCESS_MARKER = "DIGEST-BATCH-OK"
_WARN = re.compile(r"^DIGEST-BATCH-WARN (\S+)\s*$")


def expand_artifacts(patterns, date, edition):
    """{date}・{edition}(編があれば -<編>)・{yearMonth} を埋める。"""
    values = {"date": date, "edition": f"-{edition}" if edition else "", "yearMonth": date[:7]}
    return [p.format(**values) for p in patterns]


def _last_line(output_lines):
    for line in reversed(output_lines):
        if line.strip():
            return line.strip()
    return None


def _written_after(path, started_at):
    try:
        return os.stat(path).st_mtime > started_at.timestamp()
    except OSError:
        return False


def evaluate(exit_code, output_lines, artifacts, started_at, timed_out):
    """{"result", "missing", "warnings"} を返す。warnings は成功のときだけ集める。"""
    missing = []
    if timed_out or exit_code != 0:
        missing.append("exit_code")
    if _last_line(output_lines) != SUCCESS_MARKER:
        missing.append("marker")
    for path in artifacts:
        if not _written_after(path, started_at):
            missing.append("artifact:" + path)
    if not missing:
        warnings = [m.group(1) for m in (_WARN.match(line.strip()) for line in output_lines) if m]
        return {"result": "succeeded", "missing": [], "warnings": warnings}
    if timed_out:
        result = "timeout"
    elif exit_code == 2:
        result = "permanent_failure"
    else:
        result = "temporary_failure"
    return {"result": result, "missing": missing, "warnings": []}
