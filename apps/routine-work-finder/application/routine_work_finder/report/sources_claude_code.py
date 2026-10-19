"""Claude Code の会話の記録から、その週に人が打った依頼文を読む。

`~/.claude/projects/<フォルダ>/<sessionId>.jsonl` のうち、更新日時が対象の週の月曜以降のファイルだけを
1行ずつ読む。サブエージェントの会話のフォルダ(`<sessionId>/subagents/`)は読まない。選ぶ条件・依頼文の形・
伏せ字の規則は appendix.md「会話の記録から依頼文を選ぶ条件」「伏せ字の規則」が正
(design.md「既存の作業の記録を読み込む」4・5・7)。

形の違う行・読めないファイルは1件ずつ読み飛ばして数え、会話の記録のフォルダそのものが読めないときだけ
記録の失敗として控える。依頼文以外(ツールの結果・コマンドの出力)は持たない。
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

JST = timezone(timedelta(hours=9))
PROJECTS_FOLDER = Path.home() / ".claude" / "projects"
TEXT_LIMIT = 200
HEADLESS = "sdk-cli"
HUMAN = "human"
# 出どころの印(origin)が無い行のうち、人の入力ではない行の本文の始まり
NOT_TYPED_PREFIXES = ("<task-notification>", "<local-command-stdout>", "<local-command-stderr>", "<command-name>")
SLASH_PREFIX = "<command-message>"
# VS Code の拡張が自動で付ける知らせ(開いているファイル・選んだ行など)。人が打った文ではない
IDE_NOTICE = re.compile(r"<(ide_[^\s>]*)>.*?</\1>", re.DOTALL)
COMMAND_NAME = re.compile(r"<command-name>(.*?)</command-name>", re.DOTALL)
COMMAND_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TOKEN_LIKE = re.compile(r"[A-Za-z0-9_\-+/=]{24,}")


class _BadField(Exception):
    """依頼文の候補の行で、判定や依頼文に使う項目の形が違う"""


@dataclass
class ClaudeCodeResult:
    """requests: その週の依頼文(時刻の順)、skipped: 読み飛ばした行・ファイルの数(理由ごと)、failures: 読めなかった記録"""

    requests: list = field(default_factory=list)
    skipped: dict = field(default_factory=dict)
    failures: list = field(default_factory=list)


def read_claude_code(start, end, folder=PROJECTS_FOLDER):
    """日時が start 以上 end 未満(日本時間)の、人が打った依頼文を読む"""
    result = ClaudeCodeResult()
    folder = Path(folder)
    try:
        projects = sorted(path for path in folder.iterdir() if path.is_dir())
    except OSError:
        result.failures.append(_failure("unreadable"))
        return result

    skipped = Counter()
    for path in _session_files(projects, start, skipped):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            skipped["unreadable"] += 1
            continue
        # 本文に U+2028 などがそのまま入るため、splitlines() でなく改行だけで分ける
        for raw in text.split("\n"):
            if not raw.strip():
                continue
            try:
                line = json.loads(raw)
            except ValueError:
                skipped["badLine"] += 1
                continue
            if not isinstance(line, dict):
                skipped["badLine"] += 1
                continue
            try:
                request = _request(line, start, end)
            except _BadField:
                skipped["badField"] += 1
                continue
            if request is not None:
                result.requests.append(request)
    result.requests.sort(key=lambda request: request["time"])
    result.skipped = dict(skipped)
    return result


def _failure(reason):
    return {"source": "claudeCode", "site": None, "reason": reason}


def _session_files(projects, start, skipped):
    """会話のフォルダの直下の会話のファイルのうち、更新日時が start 以降のもの(サブエージェントのフォルダは見ない)"""
    since = start.timestamp()
    for project in projects:
        try:
            paths = sorted(path for path in project.iterdir() if path.suffix == ".jsonl" and path.is_file())
        except OSError:
            skipped["unreadable"] += 1
            continue
        for path in paths:
            try:
                modified = path.stat().st_mtime
            except OSError:
                skipped["unreadable"] += 1
                continue
            if modified >= since:
                yield path


def _request(line, start, end):
    """依頼文として選ぶ行なら材料の形、選ばない行なら None。候補の行の形が違えば _BadField"""
    if line.get("type") != "user" or "toolUseResult" in line:
        return None
    if line.get("isMeta") is True or line.get("isSidechain") is True or line.get("isCompactSummary") is True:
        return None
    if line.get("entrypoint") == HEADLESS:
        return None
    body = _body(line.get("message"))
    if not body:  # 文章の要素が無い、または知らせを取り除くと空になる
        return None
    if not _typed_by_human(line, body):
        return None
    when = _time(line.get("timestamp"))
    if not start <= when < end:
        return None
    cwd = line.get("cwd")
    if not isinstance(cwd, str) or not PurePosixPath(cwd).name:
        raise _BadField
    text = _slash_command(body) if body.startswith(SLASH_PREFIX) else body
    return {"source": "claudeCode", "repo": PurePosixPath(cwd).name, "text": mask(text[:TEXT_LIMIT]), "time": when}


def _body(message):
    """文字列ならそのまま、配列なら文章の要素を改行でつないだものから、VS Code の拡張の知らせを取り除き
    前後の空白と改行を詰めたもの。文章の要素が無い配列は None"""
    if not isinstance(message, dict):
        raise _BadField
    content = message.get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        texts = [part.get("text") for part in content if isinstance(part, dict) and part.get("type") == "text"]
        if not texts:
            return None
        if not all(isinstance(text, str) for text in texts):
            raise _BadField
        text = "\n".join(texts)
    else:
        raise _BadField
    return IDE_NOTICE.sub("", text).strip()


def _typed_by_human(line, body):
    """出どころの印がある行は人の入力の印だけ。無い行(古い形式)は知らせ・ローカルのコマンドの本文でないもの"""
    if "origin" in line:
        origin = line["origin"]
        return isinstance(origin, dict) and origin.get("kind") == HUMAN
    return not body.startswith(NOT_TYPED_PREFIXES)


def _time(value):
    """ISO の日時(UTC の Z 付きなど時差つき)を日本時間に直す。読めない・時差が無ければ _BadField"""
    if not isinstance(value, str):
        raise _BadField
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        raise _BadField from None
    if when.tzinfo is None:
        raise _BadField
    return when.astimezone(JST)


def _slash_command(body):
    """スラッシュコマンドで打った依頼を「コマンド名 引数」の形にする(引数が空ならコマンド名だけ)"""
    name = COMMAND_NAME.search(body)
    if name is None:
        raise _BadField
    args = COMMAND_ARGS.search(body)
    args = args.group(1) if args else ""
    return f"{name.group(1)} {args}" if args else name.group(1)


def mask(text):
    """メールアドレス、次に英字と数字の両方を含む24字以上の続きを伏せる(appendix.md「伏せ字の規則」)"""
    text = EMAIL.sub("[メール]", text)
    return TOKEN_LIKE.sub(_mask_token, text)


def _mask_token(matched):
    value = matched.group(0)
    if any(char.isascii() and char.isalpha() for char in value) and any(char.isdigit() for char in value):
        return "[伏せ字]"
    return value
