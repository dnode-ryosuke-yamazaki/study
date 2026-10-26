"""claude -p の呼び出し・応答の検査・3回までの呼び直し(design.md「Claude に自動化案と作業の要約を作らせる」5・6・8・9、
「Claude に記録しない候補を作らせる」、「バリデーション」)。

1週あたり、自動化案・作業の要約・記録しない候補の3回を呼ぶ。作業が5時間未満の週は記録しない候補だけを呼ぶ。
記録しない候補は前の2回と独立に呼び、片方の失敗でもう片方を出せなくしない。
claude -p は失敗しても終了コード0を返すことがあるため、応答の JSON が検査を通ったときだけ成功とする。
ログには種類・何回目か・成否・失敗の分類・所要秒数・材料の字数だけを書き、材料と応答の中身は書かない。
材料と応答は Claude とのやり取りの控え(claude_io)にだけ残す。
"""

import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from routine_work_finder.report import aggregate, claude_io, exclusions, materials
from routine_work_finder.report.claude_response import ResponseError, parse_json_object, require

TIMEOUT_SECONDS = 600
MAX_ATTEMPTS = 3
MIN_WORK_SECONDS = 5 * 60 * 60
MAX_PROPOSALS = 5
MAX_EXAMPLES = 3
TITLE_LIMIT = 60
TEXT_LIMIT = 400
SUMMARY_LIMIT = 200
EFFECTS = ("大", "中", "小")
NO_REUSE = "なし(新しく作る)"
PROPOSAL_FIELDS = {"title": str, "candidateIds": list, "memoIds": list, "effect": str, "seen": str, "idea": str, "reuse": list}
SUMMARY_FIELDS = {"id": str, "summary": str, "estimated": bool, "examples": list}
PROMPTS_DIR = Path(__file__).parent / "prompts"
LIB_DIR = Path.home() / ".claude" / "lib"
LOGGER = logging.getLogger("routine_work_finder.report")

GENERATED = "generated"
INSUFFICIENT = "insufficient"
CLAUDE_FAILED = "claudeFailed"

# run_headless の失敗の分類(日本語)をログの英語の短い名前に直す
HEADLESS_REASONS = {"起動失敗": "launch", "タイムアウト": "timeout", "終了コード非0": "exitCode"}


@dataclass
class ClaudeResults:
    """status: 自動化案と作業の要約の結果(generated / insufficient / claudeFailed)。
    proposals: 自動化案(番号の順)、summaries: 作業の要約(上位の順)、exclusions: 記録しない候補の欄"""

    status: str
    proposals: list = field(default_factory=list)
    summaries: list = field(default_factory=list)
    exclusions: exclusions.ExclusionResult = None


def build_prompt(name):
    """自動化案(proposals)か作業の要約(summaries)の指示文。共通の決まりのあとに種類ごとの頼みごとを続ける"""
    return (PROMPTS_DIR / "common.md").read_text(encoding="utf-8") + "\n" + (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def has_enough_work(totals):
    """作業の記録が5時間以上あれば自動化案と作業の要約を作る(5時間未満かの判定はここだけで行う)"""
    return totals.get(aggregate.WORK, 0) >= MIN_WORK_SECONDS


def generate_week(week_name, start, end, week, memos, records, reusable, config_read, run_headless=None, logger=None,
                  store=None):
    """1週間分の自動化案・作業の要約・記録しない候補を作る。records は4つの既存の作業の記録をつないだ一覧。
    store は Claude とのやり取りの控え(無ければ残さない)"""
    run_headless = run_headless or _default_run_headless()
    logger = logger or LOGGER
    store = store or claude_io.ExchangeStore.disabled()
    if not has_enough_work(week.totals):
        result = ClaudeResults(INSUFFICIENT)
    else:
        result = _proposals_and_summaries(week_name, start, end, week, memos, records, reusable, run_headless, logger, store)
    result.exclusions = _exclusions(week_name, week, config_read, run_headless, logger, store)
    return result


def _proposals_and_summaries(week_name, start, end, week, memos, records, reusable, run_headless, logger, store):
    automation = materials.build_automation_materials(week_name, week, memos, records, reusable)
    proposals = call_with_retries("proposals", build_prompt("proposals"), automation.payload,
                                  lambda parsed: validate_proposals(parsed, automation), run_headless, logger, store)
    if proposals is None:
        return ClaudeResults(CLAUDE_FAILED)
    summary = materials.build_summary_materials(week_name, week, memos, records)
    summaries = call_with_retries("summaries", build_prompt("summaries"), summary.payload,
                                  lambda parsed: validate_summaries(parsed, summary, start, end, proposals), run_headless, logger,
                                  store)
    if summaries is None:
        return ClaudeResults(CLAUDE_FAILED)
    return ClaudeResults(GENERATED, proposals, summaries)


def _exclusions(week_name, week, config_read, run_headless, logger, store):
    built = exclusions.build_exclusion_materials(week_name, week)
    if not built.windows:
        return exclusions.ExclusionResult(exclusions.SKIPPED)
    current = exclusions.current_list(config_read)
    checked = call_with_retries("exclusions", exclusions.build_prompt(), built.payload,
                                lambda parsed: exclusions.validate_exclusions(parsed, built, current), run_headless, logger,
                                store)
    if checked is None:
        return exclusions.ExclusionResult(exclusions.FAILED)
    logger.info("exclusions kept=%d dropped=%d", len(checked.kept), checked.dropped)
    return exclusions.ExclusionResult(exclusions.GENERATED, checked.kept)


def call_with_retries(name, prompt, payload, validate, run_headless, logger=None, store=None):
    """同じ材料で3回まで呼び、検査を通った値を返す。3回続けて失敗したら None。
    呼ぶ前に指示文と材料、受け取ったら検査の前に本文と成否を控え(store)に書く"""
    logger = logger or LOGGER
    store = store or claude_io.ExchangeStore.disabled()
    stdin_text = materials.serialize(payload)
    store.save_prompt(name, prompt)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        began = time.monotonic()
        reason, detail, value = None, None, None
        store.save_materials(name, attempt, stdin_text)
        result = run_headless(prompt, stdin_text, TIMEOUT_SECONDS)
        if not result.success:
            reason = HEADLESS_REASONS.get(result.failure_category, "headless")
            detail = result.detail or None
        else:
            store.save_response(name, attempt, result.output)
            try:
                value = validate(parse_json_object(result.output))
            except ResponseError as error:
                reason, detail = error.reason, str(error)
        seconds = round(time.monotonic() - began)
        store.save_result(name, attempt, reason is None, reason, detail, seconds, len(stdin_text))
        if reason is None:
            logger.info("claude call=%s attempt=%d ok=true seconds=%d chars=%d", name, attempt, seconds, len(stdin_text))
            return value
        logger.warning("claude call=%s attempt=%d ok=false reason=%s seconds=%d chars=%d",
                       name, attempt, reason, seconds, len(stdin_text))
    logger.error("claude call=%s failed attempts=%d", name, MAX_ATTEMPTS)
    return None


def validate_proposals(parsed, built):
    """自動化案の応答を確かめ、結び付いた候補の合計の時間が長い順に5件まで残す。メモだけの案は時間を None として後ろへ"""
    items = parsed.get("proposals")
    require(isinstance(items, list), "proposals が一覧ではありません")
    proposals = []
    for item in items:
        _require_fields(item, PROPOSAL_FIELDS, "自動化案")
        require(item["effect"] in EFFECTS, "効果が大・中・小のどれでもありません")
        require(all(isinstance(value, str) for value in item["reuse"]), "使える仕組みが文字の一覧ではありません")
        # 番号は文字であることを先に確かめる(リストや dict が入ると in の照合が TypeError になり、失敗の1回に数えられない)
        require(all(isinstance(value, str) and value in built.candidates for value in item["candidateIds"]),
                "渡していない候補の番号があります")
        require(all(isinstance(value, str) and value in built.memo_ids for value in item["memoIds"]),
                "渡していないメモの番号があります")
        if not item["candidateIds"] and not item["memoIds"]:
            continue
        candidate_ids = list(dict.fromkeys(item["candidateIds"]))
        proposals.append({
            "title": item["title"][:TITLE_LIMIT],
            "candidateIds": candidate_ids,
            "memoIds": list(dict.fromkeys(item["memoIds"])),
            "effect": item["effect"],
            "seen": item["seen"][:TEXT_LIMIT],
            "idea": item["idea"][:TEXT_LIMIT],
            "reuse": _reuse(item["reuse"], built.reusable_names),
            "seconds": sum(built.candidates[value].seconds for value in candidate_ids) if candidate_ids else None,
        })
    proposals.sort(key=lambda proposal: (proposal["seconds"] is None, -(proposal["seconds"] or 0)))
    kept = proposals[:MAX_PROPOSALS]
    for number, proposal in enumerate(kept, 1):
        proposal["number"] = number
        proposal["groups"] = [built.candidates[value].group for value in proposal["candidateIds"]]
    return kept


def validate_summaries(parsed, built, start, end, proposals):
    """作業の要約の応答を確かめ、渡した項目の順に返す。各項目に組と、結び付いた自動化案の番号を付ける"""
    items = parsed.get("items")
    require(isinstance(items, list), "items が一覧ではありません")
    answered = {}
    for item in items:
        _require_fields(item, SUMMARY_FIELDS, "作業の要約")
        answered.setdefault(item["id"], item)
    require(all(item_id in answered for item_id in built.items), "渡した項目の番号がそろっていません")
    summaries = []
    for item_id, group in built.items.items():
        item = answered[item_id]
        summaries.append({
            "id": item_id,
            "group": group,
            "summary": item["summary"][:SUMMARY_LIMIT],
            "estimated": item["estimated"] or not group.title_known,
            "examples": _examples(item["examples"], start, end),
            "proposalNumbers": [proposal["number"] for proposal in proposals
                                if any(linked is group for linked in proposal["groups"])],
        })
    return summaries


def _require_fields(item, fields, label):
    require(isinstance(item, dict), f"{label}の項目がオブジェクトではありません")
    for key, kind in fields.items():
        require(isinstance(item.get(key), kind), f"{label}の必須の項目 {key} がありません")


def _reuse(names, reusable_names):
    """一覧に無い名前は「なし(新しく作る)」に置き換える。一覧の名前があればそれだけを残す"""
    replaced = list(dict.fromkeys(name if name in reusable_names else NO_REUSE for name in names))
    known = [name for name in replaced if name != NO_REUSE]
    return known or [NO_REUSE]


def _examples(examples, start, end):
    """日時が週の範囲にある具体例だけを3件まで。形の違う具体例も捨てる"""
    kept = []
    for example in examples:
        if not isinstance(example, dict) or not isinstance(example.get("text"), str):
            continue
        when = _parse_time(example.get("t"))
        if when is not None and start <= when < end:
            kept.append({"t": example["t"], "text": example["text"]})
    return kept[:MAX_EXAMPLES]


def _parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _default_run_headless():
    if str(LIB_DIR) not in sys.path:
        # 先頭に入れると ~/.claude/lib/tests がこのアプリの tests を覆い隠すため末尾に足す
        sys.path.append(str(LIB_DIR))
    import claude_headless

    return claude_headless.run_headless
