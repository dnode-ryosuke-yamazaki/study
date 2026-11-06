"""アプリ登録表(launchd/apps.json)の読み取りと検証。

登録表はアプリごとに記事公開(publish)と月次見直し(review)の登録を持つ。
書式の正は specs/batch-runner/appendix.md「アプリ登録表」。
"""

import copy
import json

KINDS = ("publish", "review")

_PUBLISH_REQUIRED = ("enabled", "weekdays", "editionByWeekday", "maxAttempts", "command", "artifacts")
_REVIEW_REQUIRED = ("dayOfMonth", "maxAttempts", "command", "artifacts")


class Unregistered(Exception):
    """アプリ×系統の登録が無い(記事公開が有効でない・月次見直しの日が未定を含む)。"""


class RegistryBroken(Exception):
    """登録表が読めない・JSON として壊れている・必須項目が欠けている。"""


class Registry:
    def __init__(self, data):
        self._data = data

    def apps(self):
        return list(self._data["apps"].keys())

    def raw(self):
        return copy.deepcopy(self._data)

    def get(self, app, kind):
        """アプリ×系統の登録を返す。起動の対象でなければ Unregistered。"""
        entry = self._data["apps"].get(app)
        if entry is None:
            raise Unregistered(f"未登録のアプリです: {app}")
        spec = entry.get(kind) if kind in KINDS else None
        if spec is None:
            raise Unregistered(f"未登録の系統です: {app} {kind}")
        if kind == "publish" and spec["enabled"] is not True:
            raise Unregistered(f"記事公開が有効になっていません: {app}")
        if kind == "review" and spec["dayOfMonth"] is None:
            raise Unregistered(f"月次見直しの日が未定です: {app}")
        result = copy.deepcopy(spec)
        result["app"] = app
        result["kind"] = kind
        return result


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise RegistryBroken(f"登録表を読めません: {path}: {type(e).__name__}: {e}") from e
    _validate(data)
    return Registry(data)


def _validate(data):
    if not isinstance(data, dict) or not isinstance(data.get("apps"), dict):
        raise RegistryBroken("登録表に apps がありません")
    for app, entry in data["apps"].items():
        if not isinstance(entry, dict):
            raise RegistryBroken(f"{app} の登録が壊れています")
        for kind, required in (("publish", _PUBLISH_REQUIRED), ("review", _REVIEW_REQUIRED)):
            spec = entry.get(kind)
            if spec is None:
                continue
            if not isinstance(spec, dict):
                raise RegistryBroken(f"{app} {kind} の登録が壊れています")
            missing = [key for key in required if key not in spec]
            if missing:
                raise RegistryBroken(f"{app} {kind} に必須項目がありません: {', '.join(missing)}")
            _validate_common(app, kind, spec)
            if kind == "publish":
                _validate_publish(app, spec)
            else:
                _validate_review(app, spec)


def _validate_common(app, kind, spec):
    if not isinstance(spec["maxAttempts"], int) or isinstance(spec["maxAttempts"], bool) or spec["maxAttempts"] < 1:
        raise RegistryBroken(f"{app} {kind} の maxAttempts が不正です")
    if not isinstance(spec["command"], list) or not spec["command"] or not all(isinstance(c, str) for c in spec["command"]):
        raise RegistryBroken(f"{app} {kind} の command が不正です")
    if not isinstance(spec["artifacts"], list) or not all(isinstance(a, str) for a in spec["artifacts"]):
        raise RegistryBroken(f"{app} {kind} の artifacts が不正です")


def _validate_publish(app, spec):
    if not isinstance(spec["enabled"], bool):
        raise RegistryBroken(f"{app} publish の enabled が不正です")
    weekdays = spec["weekdays"]
    if (
        not isinstance(weekdays, list)
        or not weekdays
        or not all(isinstance(w, int) and not isinstance(w, bool) and 0 <= w <= 6 for w in weekdays)
    ):
        raise RegistryBroken(f"{app} publish の weekdays が不正です")
    editions = spec["editionByWeekday"]
    if editions is not None and not isinstance(editions, dict):
        raise RegistryBroken(f"{app} publish の editionByWeekday が不正です")


def _validate_review(app, spec):
    day = spec["dayOfMonth"]
    if day is not None and (not isinstance(day, int) or isinstance(day, bool) or not 1 <= day <= 31):
        raise RegistryBroken(f"{app} review の dayOfMonth が不正です")
