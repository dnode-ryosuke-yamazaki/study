"""失敗通知(failure-notification)への引き渡し。

12項目の組み立て・判定関数のモジュールの解決(DIGEST_HANDOFF_MODULE)・結果の記録と、
起動のたびに行う締め(前日以前の未着手と再実行待ち・記録の無い直前の配信日・通知できなかった記録の渡し直し)。

判定関数の契約(failure-notification が実装する。appendix「失敗通知に渡す項目と返る項目」):

    def judge_and_notify(failure: dict) -> dict:
        # failure: app・kind・date・edition・attempt・maxAttempts・manual・failureKind・
        #          finalReason・failedAt・alreadyNotified・logPath の12項目
        # 戻り値: {"notified": bool, "reason": "notified" | "already_notified" | "write_failed"}
"""

import datetime as dt
import importlib
import os

from . import calendar as cal
from . import state as st
from . import summary_log

DEFAULT_MODULE = "failure_notification"
FUNCTION_NAME = "judge_and_notify"
NOT_DELIVERED = ("write_failed", "notify_error")
RENOTIFY_DAYS = 35
_REASONS = ("notified", "already_notified", "write_failed")


def _stamp(value):
    if isinstance(value, dt.datetime):
        return cal.to_jst(value).isoformat(timespec="seconds")
    return value


def build(context, state, failure_kind, final_reason, failed_at, log_path):
    """失敗通知に渡す12項目の dict を作る。"""
    if isinstance(failure_kind, (list, tuple)):
        failure_kind = "+".join(failure_kind)
    warning = final_reason == "warning"
    return {
        "app": state["app"],
        "kind": state["kind"],
        "date": state["date"],
        "edition": state.get("edition"),
        "attempt": st.scheduled_attempts(state),
        "maxAttempts": state.get("maxAttempts"),
        "manual": bool(context.get("manual")),
        "failureKind": failure_kind,
        "finalReason": final_reason,
        "failedAt": _stamp(failed_at),
        "alreadyNotified": bool(state.get("warningNotified") if warning else state.get("notified")),
        "logPath": log_path,
    }


def module_name(env):
    return env.get("DIGEST_HANDOFF_MODULE") or DEFAULT_MODULE


def resolve_judge_fn(env):
    """判定関数を返す。モジュールは呼ばれたときに読み込む(読み込めなければ notify が通知の失敗にする)。"""
    name = module_name(env)

    def judge(failure):
        module = importlib.import_module(name)
        return getattr(module, FUNCTION_NAME)(failure)

    return judge


def notify(judge_fn, failure):
    """{"notified", "reason"} を返す。関数が落ちた・契約と違う形を返したときは notify_error(error に型とメッセージ)。"""
    try:
        result = judge_fn(dict(failure))
    except Exception as e:  # 失敗通知の失敗で実行係自身は落とさない
        return {"notified": False, "reason": "notify_error", "error": f"{type(e).__name__}: {e}"}
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("notified"), bool)
        or result.get("reason") not in _REASONS
    ):
        return {"notified": False, "reason": "notify_error", "error": f"契約と違う戻り値: {result!r}"[:300]}
    return {"notified": result["notified"], "reason": result["reason"]}


def record(state, result, failure, warning=False, summary_path=None):
    """結果を実行状態に書く。通知できなかったら渡した12項目を残し、要約ログに RUN-FAILED 付きの WARNING を書く。"""
    notified_key, reason_key, last_key = (
        ("warningNotified", "warningNotifyReason", "lastWarningHandoff")
        if warning
        else ("notified", "notifyReason", "lastHandoff")
    )
    state[notified_key] = bool(state.get(notified_key)) or bool(result.get("notified"))
    state[reason_key] = result["reason"]
    if result["reason"] in NOT_DELIVERED:
        state[last_key] = dict(failure)
        if summary_path:
            what = "失敗通知の書き出し失敗" if result["reason"] == "write_failed" else "失敗通知の失敗"
            detail = (
                f"app={failure.get('app')} kind={failure.get('kind')} date={failure.get('date')}"
                f" edition={failure.get('edition') or '-'} finalReason={failure.get('finalReason')}"
            )
            if result.get("error"):
                detail += f" error={result['error']}"
            summary_log.warning(summary_path, what, detail, failed=True)
    else:
        state[last_key] = None


def _records(runs_dir):
    """runs/<系統>/ の実行状態ファイル(退避済み・書きかけの一時ファイルを除く)のパスを名前順に返す。"""
    try:
        names = sorted(os.listdir(runs_dir))
    except FileNotFoundError:
        return []
    return [os.path.join(runs_dir, n) for n in names if n.endswith(".json") and not n.startswith(".")]


def _deliver(context, data, failure, warning=False):
    result = notify(context["judge_fn"], failure)
    record(data, result, failure, warning=warning, summary_path=context["summary_path"])
    return result


def expire_stale(runs_dir, base_date, exclude_date, judge_fn, context, now=None):
    """配信日が基準日より前(今回の配信日を除く)で未着手・再実行待ちのまま残った記録を失敗確定にして渡す。"""
    now = now or cal.now_jst()
    ctx = dict(context, judge_fn=judge_fn)
    touched = []
    for path in _records(runs_dir):
        try:
            data = st.read(path)
        except st.StateBroken as e:
            summary_log.warning(context["summary_path"], "壊れた記録を飛ばしました", f"{path}: {e}")
            continue
        if data["date"] >= base_date or data["date"] == exclude_date:
            continue
        if data["status"] not in ("pending", "retry_pending"):
            continue
        last = st.last_attempt(data)
        if last is not None:
            failure_kind, failed_at, log_path = last.get("result"), last.get("endedAt"), last.get("logPath")
        else:
            failure_kind, failed_at, log_path = "temporary_failure", now, context["summary_path"]
        st.set_status(data, "failed", "expired")
        failure = build(context, data, failure_kind, "expired", failed_at, log_path)
        _deliver(ctx, data, failure)
        st.save(path, data)
        summary_log.finished(
            context["summary_path"], "expired", data["date"], data.get("edition"),
            st.scheduled_attempts(data), "failed", log_path, became_failed=True,
        )
        touched.append(path)
    return touched


def expire_missing(runs_dir, registration, current_date, now, judge_fn, context):
    """今回の配信日の直前の配信日に記録が無く、その 18:30 を過ぎていれば「記録なし」の失敗確定を作って渡す。
    直前の配信日が要約ログの最初の「実行開始」の配信日より前(アプリを有効にする前の回)か、
    「実行開始」が1行も無いときは締めない。"""
    if registration["kind"] != "publish":
        return []
    first_started = summary_log.first_started_date(context["summary_path"])
    if first_started is None:
        return []
    previous = cal.previous_delivery_date(registration, current_date)
    if previous < first_started:
        return []
    edition = cal.edition_for(registration, previous)
    path = os.path.join(runs_dir, st.file_stem(previous, edition) + ".json")
    if os.path.exists(path) or now < cal.last_chance_at(previous):
        return []
    data = st.empty(registration["app"], registration["kind"], previous, edition, registration["maxAttempts"])
    st.set_status(data, "failed", "missed")
    failure = build(context, data, "temporary_failure", "missed", now, context["summary_path"])
    _deliver(dict(context, judge_fn=judge_fn), data, failure)
    st.save(path, data)
    summary_log.finished(
        context["summary_path"], "missed", previous, edition, 0, "failed", context["summary_path"], became_failed=True,
    )
    return [path]


def _within(failed_at, now, days=RENOTIFY_DAYS):
    try:
        moment = dt.datetime.fromisoformat(failed_at)
    except (TypeError, ValueError):
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=cal.JST)
    return now - moment <= dt.timedelta(days=days)


def renotify(runs_dir, current_date, now, judge_fn, context, exclude=()):
    """配信日が今回より前で、通知できずに残した12項目がある記録を、そのまま渡し直す。渡し直した記録のパスを返す。"""
    ctx = dict(context, judge_fn=judge_fn)
    excluded = set(exclude)
    renotified = []
    for path in _records(runs_dir):
        if path in excluded:
            continue
        try:
            data = st.read(path)
        except st.StateBroken:
            continue  # 同じ起動の前日以前の締めで WARNING を書いている
        if data["date"] >= current_date:
            continue
        changed = False
        sent = []
        left = data.get("lastHandoff")
        if left and data["status"] == "succeeded":
            data["lastHandoff"] = None  # 成功で終わった日の手動の失敗は渡し直さない
            changed = True
        elif left and data["status"] == "failed" and not data["notified"] and _within(left.get("failedAt"), now):
            failure = dict(left, alreadyNotified=bool(data["notified"]))
            _deliver(ctx, data, failure)
            sent.append(failure)
            changed = True
        left = data.get("lastWarningHandoff")
        if left and not data.get("warningNotified") and st.has_warnings(data) and _within(left.get("failedAt"), now):
            failure = dict(left, alreadyNotified=bool(data.get("warningNotified")))
            _deliver(ctx, data, failure, warning=True)
            sent.append(failure)
            changed = True
        if changed:
            st.save(path, data)
        for failure in sent:
            summary_log.finished(
                context["summary_path"], "renotified", data["date"], data.get("edition"),
                failure.get("attempt"), data["status"], failure.get("logPath"),
            )
        if sent:
            renotified.append(path)
    return renotified
