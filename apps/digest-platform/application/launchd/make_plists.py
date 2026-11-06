#!/usr/bin/env python3
"""アプリ登録表(launchd/apps.json)から、アプリ×系統ごとの launchd の plist を生成する。

    python3 launchd/make_plists.py --node <絶対パス> --claude <絶対パス> --python <絶対パス> [--out <フォルダ>]

記事公開は有効の印が真のアプリだけ、06:30 と(上限が2回以上なら)10:30・14:30・18:30。月次見直しは
登録表の日の 07:30。RunAtLoad は書かない(登録した直後に記事公開が走って通知が出るのを防ぐ)。
書式の正は specs/batch-runner/appendix.md「plist」。登録(launchctl bootstrap)は運営者が手元で行う。
"""

import argparse
import os
import plistlib
import re
import sys
import tempfile

LAUNCHD_DIR = os.path.dirname(os.path.abspath(__file__))
if LAUNCHD_DIR not in sys.path:
    sys.path.insert(0, LAUNCHD_DIR)

from digest_runner import environment, registry  # noqa: E402

ALL_WEEKDAYS = set(range(7))
PUBLISH_FIRST = (6, 30)
PUBLISH_RETRIES = ((10, 30), (14, 30), (18, 30))
REVIEW_TIME = (7, 30)
LAUNCHD_PATH = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
_VERSIONED = re.compile(r"\d+\.\d+")


class InvalidPlist(Exception):
    """生成した plist が読み直せない、または書いてはいけないキーを持つ。"""


def label(app, kind):
    return f"com.example.digest-{app}-{kind}"


def check_binary(path):
    """問題があれば理由の文を返す。"""
    if not os.path.isabs(path):
        return f"絶対パスではありません: {path}"
    if not os.path.exists(path):
        return f"存在しません: {path}"
    if _VERSIONED.search(path):
        return f"バージョン番号を含むパスは更新で変わるため使えません(Versions/Current などに変えてください): {path}"
    return None


def _intervals(kind, spec):
    if kind == "review":
        hour, minute = REVIEW_TIME
        return [{"Day": spec["dayOfMonth"], "Hour": hour, "Minute": minute}]
    times = [PUBLISH_FIRST] + (list(PUBLISH_RETRIES) if spec["maxAttempts"] >= 2 else [])
    if set(spec["weekdays"]) == ALL_WEEKDAYS:
        return [{"Hour": h, "Minute": m} for h, m in times]
    return [{"Weekday": w, "Hour": h, "Minute": m} for w in sorted(set(spec["weekdays"])) for h, m in times]


def build(app, kind, spec, binaries, home, ca_bundle):
    log = os.path.join(home, "Library", "Logs", f"digest-{app}-{kind}.log")
    return {
        "Label": label(app, kind),
        "ProgramArguments": [binaries["python"], os.path.join(LAUNCHD_DIR, "runner.py"), app, kind],
        "StartCalendarInterval": _intervals(kind, spec),
        "EnvironmentVariables": {
            "HOME": home,
            "PATH": LAUNCHD_PATH,
            "TZ": "Asia/Tokyo",
            "DIGEST_NODE_BIN": binaries["node"],
            "DIGEST_CLAUDE_BIN": binaries["claude"],
            "DIGEST_PYTHON_BIN": binaries["python"],
            "NODE_EXTRA_CA_CERTS": ca_bundle,
            "SSL_CERT_FILE": ca_bundle,
        },
        "ProcessType": "Background",
        "StandardOutPath": log,
        "StandardErrorPath": log,
    }


def generate(reg, binaries, home):
    """{ファイル名: plist の dict} を返す。有効でない記事公開・日が未定の月次見直しは作らない。"""
    bundle = environment.ca_bundle(home)
    plists = {}
    for app in reg.apps():
        for kind in registry.KINDS:
            try:
                spec = reg.get(app, kind)
            except registry.Unregistered:
                continue
            plists[label(app, kind) + ".plist"] = build(app, kind, spec, binaries, home, bundle)
    return plists


def checked_bytes(plist):
    """plist を XML にし、標準の読み取りで読み直して検査したバイト列を返す。"""
    try:
        data = plistlib.dumps(plist, fmt=plistlib.FMT_XML)
        again = plistlib.loads(data)
    except (TypeError, ValueError, OverflowError) as e:
        raise InvalidPlist(f"{plist.get('Label')}: {type(e).__name__}: {e}") from e
    if again != plist or "RunAtLoad" in again:
        raise InvalidPlist(f"{plist.get('Label')}: 読み直した内容が違うか RunAtLoad を含みます")
    return data


def _write(path, data):
    folder = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".plist.", dir=folder)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv=None, registry_path=None, home=None):
    parser = argparse.ArgumentParser(prog="make_plists.py", description="アプリ登録表から launchd の plist を生成する")
    parser.add_argument("--node", required=True)
    parser.add_argument("--claude", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--out")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    home = home or os.path.expanduser("~")
    out = args.out or os.path.join(home, "Library", "LaunchAgents")
    registry_path = registry_path or os.path.join(LAUNCHD_DIR, "apps.json")

    binaries = {"node": args.node, "claude": args.claude, "python": args.python}
    problems = [p for p in (check_binary(path) for path in binaries.values()) if p]
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 2
    try:
        reg = registry.load(registry_path)
        rendered = {name: checked_bytes(p) for name, p in generate(reg, binaries, home).items()}
    except (registry.RegistryBroken, InvalidPlist) as e:
        print(f"生成できません: {e}", file=sys.stderr)
        return 2
    os.makedirs(out, exist_ok=True)
    for name, data in rendered.items():
        _write(os.path.join(out, name), data)
        print(os.path.join(out, name))
    if not rendered:
        print("有効なアプリ×系統がありません(登録表の publish.enabled・review.dayOfMonth を確かめてください)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
