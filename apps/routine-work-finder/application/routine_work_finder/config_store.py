"""設定ファイル(config.json)の読み書き。形は appendix.md「設定ファイルの形」。

読めない形の見分け方と理由の文字列は、記録係(recorder/Sources/RecorderCore/Config.swift)と同じにする。
"""

import json
import os
from datetime import datetime
from typing import NamedTuple, Optional

DEFAULT_EXCLUDED_APPS = (
    ("パスワード", "com.apple.Passwords"),
    ("キーチェーンアクセス", "com.apple.keychainaccess"),
    ("システム設定", "com.apple.systempreferences"),
)


class ConfigRead(NamedTuple):
    """設定ファイルを読んだ結果。state は "ok" / "missing"(ファイルが無い) / "unreadable"(読めない・形が違う)"""

    state: str
    config: Optional[dict]
    reason: Optional[str]


def default_config():
    """初期値: 記録しないアプリ3つ・空の記録しないことば・終わりの日時なし"""
    return {
        "version": 1,
        "endsAt": None,
        "stoppedAt": None,
        "excludedApps": [{"name": name, "bundleId": bundle_id} for name, bundle_id in DEFAULT_EXCLUDED_APPS],
        "excludedTitleWords": [],
    }


class _FieldError(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def read_config(data_paths):
    if not data_paths.config.exists():
        return ConfigRead("missing", None, None)
    try:
        text = data_paths.config.read_text(encoding="utf-8")
    except OSError:
        return ConfigRead("unreadable", None, "unreadable")
    except UnicodeDecodeError:
        # 記録係と同じく、文字に直せないものも JSON として読めない設定とみなす
        return ConfigRead("unreadable", None, "invalidJson")
    try:
        raw = json.loads(text)
    except ValueError:
        return ConfigRead("unreadable", None, "invalidJson")
    if not isinstance(raw, dict):
        return ConfigRead("unreadable", None, "invalidJson")
    try:
        config = {
            "version": _required(raw, "version", _is_int),
            "endsAt": _required(raw, "endsAt", _is_timestamp, nullable=True),
            "stoppedAt": _optional(raw, "stoppedAt", _is_timestamp),
            "excludedApps": _required(raw, "excludedApps", _is_excluded_apps),
            "excludedTitleWords": _required(raw, "excludedTitleWords", _is_string_list),
        }
        # 省略できる項目。欠けているときは項目を足さず(書き戻しても足さない)、読む側が既定を当てる
        if "micAsMeeting" in raw:
            config["micAsMeeting"] = _required(raw, "micAsMeeting", _is_bool)
    except _FieldError as error:
        return ConfigRead("unreadable", None, error.reason)
    # 付録に載っていない項目も書き戻しで落とさないよう、結果に持たせる
    config.update({key: value for key, value in raw.items() if key not in config})
    return ConfigRead("ok", config, None)


def mic_as_meeting(config):
    """マイクが使用中の時間を会議として数えるか。設定が無い(None)・項目が無いときは数える(既定)"""
    return True if config is None else config.get("micAsMeeting", True)


def write_config(data_paths, config):
    """データフォルダ(700)の config.json.tmp(600)に書いてから config.json へ名前を付け替える"""
    ensure_data_folder(data_paths)
    temporary = data_paths.root / "config.json.tmp"
    text = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(text)
    os.replace(temporary, data_paths.config)


def ensure_data_folder(data_paths):
    """データフォルダが無ければ700で作る"""
    if not data_paths.root.exists():
        data_paths.root.mkdir(parents=True, mode=0o700)
        os.chmod(data_paths.root, 0o700)


def _required(raw, key, check, nullable=False):
    if key not in raw:
        raise _FieldError(f"missingField:{key}")
    value = raw[key]
    if nullable and value is None:
        return None
    if not check(value):
        raise _FieldError(f"invalidType:{key}")
    return value


def _optional(raw, key, check):
    value = raw.get(key)
    if value is None:
        return None
    if not check(value):
        raise _FieldError(f"invalidType:{key}")
    return value


def _is_bool(value):
    return isinstance(value, bool)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _is_string_list(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_excluded_apps(value):
    if not isinstance(value, list):
        return False
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            return False
        if item.get("bundleId") is not None and not isinstance(item.get("bundleId"), str):
            return False
    return True
