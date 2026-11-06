#!/usr/bin/env python3
"""承認フロントマターを持たない既存specへ、フロントマターを付ける移行スクリプト。

specフォルダを受け取り、requirements.md / design.md / tasks.md のうちフロントマターの
無いファイルに `status` / `approved_date` / `version` を付ける。既定は試し実行で、
判定結果を1ファイル1行のタブ区切りで出すだけ。`--apply` を付けたときだけ書き込む。

判定(--status を指定しない場合):
- requirements.md のステータス行が「実装中」「リリース済み」なら approved / "1.0"。
  承認を経ずに実装へ入らない流れなので、実装に入った spec は承認済みとみなせる。
  approved_date はそのファイルを最後にコミットした日(承認日の推定値)
- それ以外(仕様確認中・ステータス行が無い・引用で書いた旧い行で値が読めない等)は
  機械では決めず「要判断」として出す。`--status approved|draft` を指定して個別に流す

起動: python3 ${CLAUDE_PLUGIN_ROOT}/lib/spec_layout_check/scripts/migrate_approval_frontmatter.py \\
        [--apply] [--status approved|draft] [--approved-date YYYY-MM-DD] <specフォルダ>...

終了コード: 0 = 要判断なし / 1 = 引数の誤り / 2 = 要判断が残っている

仕様: ~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers/
  requirements.md#既存specの扱い-3、appendix.md#承認フロントマターの書式
"""

import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import checks
import markdown_scan

EXIT_DONE = 0
EXIT_USAGE = 1
EXIT_PENDING = 2

FIRST_VERSION = {"approved": "1.0", "draft": "0.1"}
PROGRESS_LINE = re.compile(r"^>?\s*ステータス:\s*(.*)$")
IMPLEMENTED = ("実装中", "リリース済み")

DECIDED = "付ける"
SKIPPED = "移行済み"
PENDING = "要判断"


def progress_label(spec_dir):
    """requirements.md のタイトル直下(最初の `##` より前)にあるステータス行の値。"""
    path = os.path.join(spec_dir, "requirements.md")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            if line.startswith("## "):
                break
            found = PROGRESS_LINE.match(line.strip())
            if found:
                return found.group(1)
    return None


def infer_status(spec_dir):
    """(status, 理由)。決められなければ status は None。"""
    label = progress_label(spec_dir)
    if label is None:
        return None, "requirements.md にステータス行が無い"
    if any(word in label for word in IMPLEMENTED):
        return "approved", "ステータス行が「%s」" % label.split("／")[0].strip()
    return None, "ステータス行が「%s」で承認の有無を読めない" % label.split("／")[0].strip()


def last_commit_date(path):
    """そのファイルを最後にコミットした日(YYYY-MM-DD)。履歴が無ければ None。"""
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1")
    try:
        done = subprocess.run(
            ["git", "log", "-1", "--format=%as", "--", os.path.basename(path)],
            cwd=os.path.dirname(path), env=env, capture_output=True, text=True)
    except OSError:
        return None
    date = done.stdout.strip()
    return date if done.returncode == 0 and date else None


def frontmatter_text(status, version, approved_date=None):
    lines = ["---", "status: %s" % status]
    if approved_date:
        lines.append("approved_date: %s" % approved_date)
    lines.append('version: "%s"' % version)
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def plan_spec(spec_dir, status=None, approved_date=None):
    """1つのspecフォルダの移行計画。[(ファイル名, 判定, 書く内容 or None, 補足)]。"""
    plans = []
    targets = []
    for name in checks.APPROVAL_FILES:
        path = os.path.join(spec_dir, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fp:
            text = fp.read()
        if markdown_scan.scan(text).frontmatter is not None:
            plans.append((name, SKIPPED, None, "フロントマターあり"))
            continue
        targets.append((name, path))

    if not targets:
        return plans

    reason = "--status で指定"
    if status is None:
        status, reason = infer_status(spec_dir)
    for name, path in targets:
        if status is None:
            plans.append((name, PENDING, None, reason))
            continue
        date = None
        note = reason
        if status == "approved":
            date = approved_date or last_commit_date(path)
            if date is None:
                plans.append((name, PENDING, None,
                              "コミット履歴が無く承認日を推定できない(--approved-date で指定)"))
                continue
            if not approved_date:
                note += "。approved_date は最後にコミットした日(推定値)"
        head = frontmatter_text(status, FIRST_VERSION[status], date)
        summary = "status: %s / version: %s%s" % (
            status, FIRST_VERSION[status], " / approved_date: %s" % date if date else "")
        plans.append((name, DECIDED, head, "%s(%s)" % (summary, note)))
    return plans


def apply_plan(spec_dir, plans):
    for name, decision, head, _note in plans:
        if decision != DECIDED:
            continue
        path = os.path.join(spec_dir, name)
        with open(path, encoding="utf-8") as fp:
            text = fp.read()
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(head + text)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="既存specに承認フロントマターを付ける(既定は試し実行)")
    parser.add_argument("--apply", action="store_true", help="判定どおりに書き込む")
    parser.add_argument("--status", choices=("approved", "draft"),
                        help="ステータス行から推定せず、この値で付ける")
    parser.add_argument("--approved-date", help="approved のときの承認日(YYYY-MM-DD)")
    parser.add_argument("spec_dirs", nargs="+", help="specフォルダ")
    args = parser.parse_args(argv)
    if args.approved_date and not checks._is_date(args.approved_date):
        parser.error("--approved-date は YYYY-MM-DD の日付で指定する")
    return args


def main(argv, stdout=None):
    stdout = stdout or sys.stdout
    try:
        args = parse_args(argv)
    except SystemExit:
        return EXIT_USAGE
    pending = False
    for spec_dir in args.spec_dirs:
        spec_dir = os.path.abspath(spec_dir.rstrip("/"))
        plans = plan_spec(spec_dir, args.status, args.approved_date)
        if not plans:
            stdout.write("%s\t-\t%s\t対象ファイルが無い\n" % (spec_dir, PENDING))
            pending = True
            continue
        for name, decision, _head, note in plans:
            stdout.write("%s\t%s\t%s\t%s\n" % (spec_dir, name, decision, note))
            pending = pending or decision == PENDING
        if args.apply:
            apply_plan(spec_dir, plans)
    return EXIT_PENDING if pending else EXIT_DONE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
