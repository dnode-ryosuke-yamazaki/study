"""実行ファイルの探索と、バッチへ渡す環境変数の組み立て。

launchd は PATH を引き継がないため、node・claude・python3 は plist の環境変数(DIGEST_*_BIN)で
受け取り、無ければ(手動実行)PATH → 既知の候補の順で探す。CAバンドルの2段の探し方も
実行係が自分で持つ(個人の共有ライブラリは参照しない。ADR 0002)。
"""

import os

DEFAULT_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
SYSTEM_CA_BUNDLE = "/etc/ssl/cert.pem"
_NAMES = {"node": ("DIGEST_NODE_BIN", "node"), "claude": ("DIGEST_CLAUDE_BIN", "claude"), "python": ("DIGEST_PYTHON_BIN", "python3")}
_SENSITIVE_PARTS = ("TOKEN", "SECRET", "KEY")
_NOT_FOR_BATCH = ("ANTHROPIC_API_KEY", "DIGEST_HANDOFF_MODULE")


class BinaryNotFound(Exception):
    """node・claude・python3・tsx のどれかが見つからない。"""


def _home(home=None):
    return home or os.path.expanduser("~")


def default_candidates(home=None):
    home = _home(home)
    common = ["/usr/local/bin", "/opt/homebrew/bin"]
    return {
        "node": [os.path.join(d, "node") for d in common],
        "claude": [os.path.join(home, ".local", "bin", "claude"), os.path.join(home, ".claude", "local", "claude")]
        + [os.path.join(d, "claude") for d in common],
        "python": [os.path.join(d, "python3") for d in common],
    }


def _executable(path):
    return bool(path) and os.path.isabs(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def _on_path(name, path_value):
    for folder in (path_value or "").split(os.pathsep):
        if folder:
            candidate = os.path.join(folder, name)
            if _executable(candidate):
                return candidate
    return None


def find_binaries(env, home=None, candidates=None):
    """{"node", "claude", "python"} の絶対パスを返す。見つからなければ BinaryNotFound。"""
    candidates = default_candidates(home) if candidates is None else candidates
    found = {}
    for key, (variable, command) in _NAMES.items():
        path = env.get(variable)
        if not _executable(path):
            path = _on_path(command, env.get("PATH"))
        if path is None:
            path = next((c for c in candidates.get(key, []) if _executable(c)), None)
        if path is None:
            raise BinaryNotFound(f"{command} が見つかりません({variable}・PATH・既知の候補)")
        found[key] = path
    return found


def find_tsx(app_root):
    path = os.path.join(app_root, "node_modules", ".bin", "tsx")
    if not os.path.isfile(path):
        raise BinaryNotFound(f"tsx が見つかりません: {path}")
    return path


def ca_bundle(home=None):
    corporate = os.path.join(_home(home), "Library", "Application Support", "ca-bundle", "ca-bundle.pem")
    return corporate if os.path.isfile(corporate) else SYSTEM_CA_BUNDLE


def _sensitive(name):
    upper = name.upper()
    return name in _NOT_FOR_BATCH or any(part in upper for part in _SENSITIVE_PARTS)


def build(env, context):
    """親の環境から認証に見える変数を落とし、バッチが読む DIGEST_* と PATH・TZ・CAバンドルを足す。"""
    built = {name: value for name, value in env.items() if not _sensitive(name)}
    binaries = context["binaries"]
    front = []
    for key in ("node", "claude"):
        folder = os.path.dirname(binaries[key])
        if folder not in front:
            front.append(folder)
    rest = [p for p in (env.get("PATH") or DEFAULT_PATH).split(os.pathsep) if p and p not in front]
    built.update(
        {
            "DIGEST_APP": context["app"],
            "DIGEST_KIND": context["kind"],
            "DIGEST_DATE": context["date"],
            "DIGEST_EDITION": context["edition"] or "",
            "DIGEST_ATTEMPT": str(context["attempt"]),
            "DIGEST_MANUAL": "1" if context["manual"] else "0",
            "DIGEST_CLAUDE_IO_DIR": context["claude_io_dir"],
            "DIGEST_CLAUDE_BIN": binaries["claude"],
            "DIGEST_DATA_DIR": context["data_dir"],
            "NODE_EXTRA_CA_CERTS": context["ca_bundle"],
            "SSL_CERT_FILE": context["ca_bundle"],
            "TZ": "Asia/Tokyo",
            "PATH": os.pathsep.join(front + rest),
        }
    )
    return built
