"""週次レポートの保存と Teams への通知(design.md「週次レポートを作って届ける」13・14、「エラーハンドリング」)。

HTML をローカルの控え reports/<週の名前>.html に書き、OneDrive の保存先 00_root/auto/routineWorkFinder/ へ
同じ名前で書く(同期フォルダへの書き方は onedrive_write.py)。保存できたらビューア形式のリンク付きで
Teams の自分宛てに知らせる。保存と通知はそれぞれ10秒あけて3回まで試し、それでも失敗した週は結果として返す。
後から自動ではやり直さない。通知の本文の形は appendix.md「Teams の通知の本文」。
記録しない候補とレポートの中身は通知の本文に入れない。
"""

import html
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote

from routine_work_finder.report import onedrive_write
from routine_work_finder.report.render_html import week_name

__all__ = ["PublishResult", "publish_report", "send_notification", "week_name", "report_file_name", "viewer_url",
           "build_viewer_url", "base_body", "save_failed_body", "unexpected_failure_body",
           "unexpected_failure_before_week_body", "state_backed_up_body", "remake_no_records_body"]

LOGGER = logging.getLogger("routine_work_finder.report")
LIB_DIR = Path.home() / ".claude" / "lib"

SKILL_NAME = "routine-work-finder"
NOTIFY_KIND = "weekly-report"
ATTEMPTS = 3
RETRY_WAIT_SECONDS = 10
FOLDER_NAME = "routineWorkFinder"
ONEDRIVE_DIR = Path.home() / "Library" / "CloudStorage" / "OneDrive-Deloitte(O365D)" / "00_root" / "auto" / FOLDER_NAME
# ビューアの基点とWebパスは、議事録の自動生成(studyリポジトリ apps/meeting-minutes-generator/application/config.py の
# 既定のビューアURL・既定の作業フォルダのWebパス)と同じ値を使う
VIEWER_URL = "https://jpdeloitte-my.sharepoint.com/personal/ryosuke_yamazaki_tohmatsu_co_jp/_layouts/15/onedrive.aspx"
WEB_DIR = "/personal/ryosuke_yamazaki_tohmatsu_co_jp/Documents/00_root/auto"
LOG_LABEL = "~/Library/Logs/routine-work-finder-report.log"
HEAD = "【定型業務の週次レポート】"


@dataclass
class PublishResult:
    """saved: OneDrive に保存できたか、notified: Teams に知らせられたか、local_path: ローカルの控え、url: ビューア形式のリンク"""

    saved: bool
    notified: bool
    local_path: Path
    url: Optional[str]

    @property
    def save_failed(self):
        return not self.saved


def report_file_name(week):
    return f"{week}.html"


def build_viewer_url(viewer, web_dir, filename):
    """共有ストレージのファイルビューアで開くURLを組み立てる。
    ~/.claude/skills/sprint-review-generator/scripts/sprint_review/notify.py の build_viewer_url と同じ形
    (ビューアについてきたクエリを落とし、エンコード済みのディレクトリは元に戻してから付ける)"""
    base = viewer.split("?")[0].rstrip("/")
    directory = "/" + unquote(web_dir).strip("/")
    file_id = quote(f"{directory}/{filename}", safe="")
    parent = quote(directory, safe="")
    return f"{base}?id={file_id}&parent={parent}"


def viewer_url(week, viewer=VIEWER_URL, web_dir=WEB_DIR):
    return build_viewer_url(viewer, f"{unquote(web_dir).rstrip('/')}/{FOLDER_NAME}", report_file_name(week))


def _e(text):
    return html.escape(str(text), quote=True)


def _remake_hint(week):
    return f"チャットで「{_e(week)} の定型業務レポートを作り直して」と頼むと作り直せます"


def base_body(week, state, proposal_count, url, candidate_count=0, memo_count=0):
    """基本の本文。state は週の状態(normal / empty / insufficient / failed)で、自動化案の行だけが変わる。
    自動化案が0件の週は、候補の数(集計の候補の全数)とメモの数のどちらかが1件以上なら、候補はあったが案にならなかった行にする"""
    empty_line = "自動化案: 今週は見つかりませんでした"
    if candidate_count or memo_count:
        empty_line = (f"自動化案: 候補 {int(candidate_count)}件・メモ {int(memo_count)}件がありましたが案になりませんでした。"
                      f"チャットで「{_e(week)} の定型業務レポートを作り直して」と頼むと出ることがあります")
    proposal_line = {
        "empty": empty_line,
        "insufficient": "自動化案: 記録が5時間未満のため作っていません",
        "failed": f"自動化案: 作成に失敗しました。{_remake_hint(week)}",
    }.get(state, f"自動化案: {int(proposal_count)}件")
    name = _e(report_file_name(week))
    # リンクの URL は https:// で始まるものだけを使う(design.md「セキュリティ」)
    link = f'<a href="{_e(url)}">{name}</a>' if url and url.startswith("https://") else name
    return f"{HEAD}<br>週: {_e(week)}<br>{proposal_line}<br>レポート: {link}"


def save_failed_body(week, local_path):
    return (f"{HEAD}<br>{_e(week)} のレポートを OneDrive に保存できませんでした。控え: {_e(local_path)}"
            f"<br>{_remake_hint(week)}")


def unexpected_failure_body(week):
    return f"{HEAD}<br>{_e(week)} の週次レポートの作成に失敗しました。ログ: {LOG_LABEL}<br>{_remake_hint(week)}"


def unexpected_failure_before_week_body():
    return f"{HEAD}<br>週次レポートの作成に失敗しました(対象の週を決める前に止まりました)。ログ: {LOG_LABEL}"


def state_backed_up_body(backup_path):
    return (f"{HEAD}<br>週次レポート係の状態のファイルが読めなかったため退避して続けました。退避先: {_e(backup_path)}"
            "<br>同じ週のレポートが重ねて届くことがあります")


def remake_no_records_body(week):
    return f"{HEAD}<br>{_e(week)} は記録が0件のため作り直せませんでした"


def _default_notifier():
    if str(LIB_DIR) not in sys.path:
        # 先頭に入れると ~/.claude/lib/tests がこのアプリの tests を覆い隠すため末尾に足す
        sys.path.append(str(LIB_DIR))
    from atlassian_rest.teams_notify import notify_teams
    return notify_teams


def send_notification(body, notifier=None, sleep=time.sleep):
    """Teams の自分宛てに本文を送る。10秒あけて3回まで試し、送れたら真"""
    notifier = notifier or _default_notifier()
    for attempt in range(1, ATTEMPTS + 1):
        try:
            result = notifier(SKILL_NAME, NOTIFY_KIND, body)
            reason = None if isinstance(result, dict) and result.get("success") is True else "notSent"
        except Exception as error:  # 共通部品の外の思わぬ失敗も送り直しの対象にする
            reason = type(error).__name__
        if reason is None:
            LOGGER.info("notify ok=true attempt=%d", attempt)
            return True
        LOGGER.warning("notify ok=false attempt=%d reason=%s", attempt, reason)
        if attempt < ATTEMPTS:
            sleep(RETRY_WAIT_SECONDS)
    LOGGER.error("notify failed attempts=%d", ATTEMPTS)
    return False


def _write_local(local_dir, name, html_text):
    """ローカルの控えを書く。フォルダは700、ファイルは600"""
    local_dir = Path(local_dir)
    if not local_dir.exists():
        local_dir.mkdir(parents=True, mode=0o700)
        os.chmod(local_dir, 0o700)
    path = local_dir / name
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(html_text)
    return path


def _save_to_onedrive(local_path, onedrive_dir, copy, sleep):
    dest = Path(onedrive_dir) / local_path.name
    for attempt in range(1, ATTEMPTS + 1):
        try:
            dest.parent.mkdir(exist_ok=True)
            copy(local_path, dest)
        except OSError as error:
            LOGGER.warning("save onedrive ok=false attempt=%d errno=%s", attempt, error.errno)
            if attempt < ATTEMPTS:
                sleep(RETRY_WAIT_SECONDS)
            continue
        LOGGER.info("save onedrive ok=true attempt=%d path=%s", attempt, dest)
        return True
    LOGGER.error("save onedrive failed attempts=%d", ATTEMPTS)
    return False


def publish_report(html_text, week, state, proposal_count, local_dir, onedrive_dir=ONEDRIVE_DIR,
                   viewer=VIEWER_URL, web_dir=WEB_DIR, notifier=None, sleep=time.sleep, copy=onedrive_write.copy_file,
                   candidate_count=0, memo_count=0):
    """控えと OneDrive に保存し、Teams に知らせる。保存に失敗したら基本の本文の代わりに「保存に失敗」の本文を送る。
    state は週の状態(render_html.week_state の値)、proposal_count は自動化案の件数、
    candidate_count と memo_count は集計の候補の全数とその週のメモの件数(自動化案が0件の週の行に使う)"""
    name = report_file_name(week)
    local_path = _write_local(local_dir, name, html_text)
    LOGGER.info("save local path=%s", local_path)
    saved = _save_to_onedrive(local_path, onedrive_dir, copy, sleep)
    url = viewer_url(week, viewer, web_dir) if saved else None
    body = (base_body(week, state, proposal_count, url, candidate_count, memo_count) if saved
            else save_failed_body(week, local_path))
    notified = send_notification(body, notifier=notifier, sleep=sleep)
    return PublishResult(saved=saved, notified=notified, local_path=local_path, url=url)
