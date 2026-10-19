"""データフォルダとファイルの場所(appendix.md「データフォルダの構成」)"""

import os
from pathlib import Path

# 同期フォルダの目印。生の記録をクラウドへ上げないよう、データフォルダがこの下を指していたら断る
SYNC_FOLDER_MARKERS = (
    "/Library/CloudStorage/",
    "/Library/Mobile Documents/",
    "/OneDrive",
    "/Dropbox",
    "/Google Drive",
    "/Box/",
)


class SyncFolderError(Exception):
    """データフォルダが同期フォルダの下を指している"""


class DataPaths:
    def __init__(self, root):
        self.root = Path(root)
        self.config = self.root / "config.json"
        self.status = self.root / "recorder-status.json"
        self.control_log = self.root / "control.log"
        self.records = self.root / "records"
        self.memos = self.root / "memos"
        # 週次レポート係が使うファイル(weekly-automation-report の appendix.md「週次レポート係が使うファイル」)
        self.report_state = self.root / "report-state.json"
        self.report_lock = self.root / "report.lock"
        self.reports = self.root / "reports"
        self.requests = self.root / "requests"


def data_paths(environ=None, home=None):
    """データフォルダの場所。既定は ~/Library/Application Support/routine-work-finder。
    テストなどで場所を変えるときは環境変数 RWF_DATA_DIR で指定する"""
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    root = Path(environ.get("RWF_DATA_DIR") or home / "Library" / "Application Support" / "routine-work-finder")
    text = str(root) + "/"
    if any(marker in text for marker in SYNC_FOLDER_MARKERS):
        raise SyncFolderError(f"データフォルダが同期フォルダの下を指しています: {root}")
    return DataPaths(root)
