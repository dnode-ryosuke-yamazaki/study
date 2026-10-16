"""記録しない候補の材料の組み立てと応答の検査(design.md「Claude に記録しない候補を作らせる」、「バリデーション」)。

材料は、その週のアプリ名とウィンドウの題名(Excel はシート名も)の組だけ。今の記録しないアプリ・ことばの一覧は
材料に入れず、ここで設定ファイルの一覧を読んで、一覧と重なる候補を手元で捨てる。候補の値はそのまま
記録の操作Skillへの依頼文に入るため、渡した題名の一部か渡したアプリ名で、改行を含まないものだけを残す。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple, Optional

from routine_work_finder import config_store
from routine_work_finder.report import aggregate, materials
from routine_work_finder.report.claude_response import require

KINDS = ("給与・賞与", "人事評価・採用・異動", "他人の個人情報", "認証情報や秘密の情報", "医療・健康", "私用", "社外秘の固有名")
TARGETS = ("word", "app")
REQUIRED = ("kind", "target", "value", "example", "reason")
MAX_EXCLUSIONS = 5
MIN_WORD_LENGTH = 2
VALUE_LIMIT = 50
REASON_LIMIT = 200
PROMPT_PATH = Path(__file__).parent / "prompts" / "exclusions.md"

GENERATED = "generated"
FAILED = "failed"
SKIPPED = "skipped"


@dataclass
class ExclusionMaterials:
    """payload: 標準入力に渡す JSON、windows: 渡した組(アプリ名・題名・シート名)を渡した順に"""

    payload: dict
    windows: list = field(default_factory=list)


class ExclusionList(NamedTuple):
    """手元で読んだ今の記録しないアプリ名とことば"""

    apps: frozenset
    words: tuple


class ExclusionCheck(NamedTuple):
    """kept: 検査を通った候補(応答の順に5件まで)、dropped: 捨てた候補の数"""

    kept: list
    dropped: int


@dataclass
class ExclusionResult:
    """記録しない候補の欄の中身。status は generated(候補0件を含む)/ failed(3回続けて失敗)/ skipped(送る組が無く呼ばなかった)"""

    status: str
    candidates: list = field(default_factory=list)


def build_prompt():
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_exclusion_materials(week_name, week):
    """除外中の行と題名が取れなかった行を除いた行から、組を重複なく時間の長い順に並べる。
    上限を超えたら時間の短い組から減らす"""
    seconds = {}
    for line, category in week.classified:
        if category == aggregate.EXCLUDED or line.get("titleUnavailable") is True or line.get("title") is None:
            continue
        key = (line.get("app"), line["title"], line.get("sheet"))
        seconds[key] = seconds.get(key, 0) + aggregate.SECONDS_PER_LINE
    ordered = sorted(seconds.items(), key=lambda item: -item[1])
    payload = {"week": week_name, "windows": [
        {"id": f"t{index}", "app": app, "title": title, "sheet": sheet, "totalMinutes": materials.minutes(total)}
        for index, ((app, title, sheet), total) in enumerate(ordered, 1)
    ]}
    materials.fit(payload, "windows")
    windows = [{"app": window["app"], "title": window["title"], "sheet": window["sheet"]} for window in payload["windows"]]
    return ExclusionMaterials(payload=payload, windows=windows)


def current_list(config_read) -> Optional[ExclusionList]:
    """設定ファイルが無ければ初期値の一覧、読めない・形が違うときは None(一覧による除外をしない)"""
    if config_read.state == "ok":
        config = config_read.config
    elif config_read.state == "missing":
        config = config_store.default_config()
    else:
        return None
    return ExclusionList(frozenset(app["name"] for app in config["excludedApps"]), tuple(config["excludedTitleWords"]))


def validate_exclusions(parsed, built, current):
    """応答の候補を1件ずつ確かめ、合わない候補を捨てて5件まで残す。必須の項目がそろわなければ失敗の1回"""
    items = parsed.get("exclusions")
    require(isinstance(items, list), "exclusions が一覧ではありません")
    for item in items:
        require(isinstance(item, dict) and all(isinstance(item.get(key), str) for key in REQUIRED),
                "記録しない候補の必須の項目がそろっていません")
    kept, seen_values = [], set()
    for item in items:
        if _acceptable(item, built.windows, current) and item["value"] not in seen_values:
            seen_values.add(item["value"])
            kept.append({
                "kind": item["kind"], "target": item["target"], "value": item["value"], "example": item["example"],
                "exampleApp": _example_app(item["example"], built.windows), "reason": item["reason"][:REASON_LIMIT],
            })
    return ExclusionCheck(kept[:MAX_EXCLUSIONS], len(items) - len(kept[:MAX_EXCLUSIONS]))


def _acceptable(item, windows, current):
    value, example = item["value"], item["example"]
    titles = [window["title"] for window in windows]
    if item["kind"] not in KINDS or item["target"] not in TARGETS:
        return False
    if _has_line_break(value) or len(value) > VALUE_LIMIT or example not in titles:
        return False
    if item["target"] == "word":
        # 例は渡した題名のどれかなので、例に含まれることばは渡した題名の一部でもある
        if len(value) < MIN_WORD_LENGTH or value not in example:
            return False
    elif value not in {window["app"] for window in windows}:
        return False
    if current is not None:
        # 一覧にあることばは例にも含まれるため、次の行の例の照合でも捨てられる。一覧との照合が効くのはアプリ
        listed = current.words if item["target"] == "word" else current.apps
        if value in listed or any(word and word in example for word in current.words):
            return False
    return True


def _has_line_break(value):
    """改行のほか、行を分ける文字(U+2028 など)も改行として扱う"""
    return len((value + "x").splitlines()) > 1


def _example_app(example, windows):
    return next(window["app"] for window in windows if window["title"] == example)
