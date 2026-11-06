"""runs/・logs/・claude-io/ の中で最後の更新から90日を過ぎたファイルの掃除。

要約ログ(runner-<系統>.log)・ロック・読者データは対象外。空になったフォルダも消す
(消した結果空になったもの、または最後の更新から90日を過ぎた空のフォルダ)。
"""

import os

TARGETS = ("runs", "logs", "claude-io")
RETENTION_DAYS = 90


def sweep(data_dir, now, days=RETENTION_DAYS):
    """(消したパスの一覧, 消せなかったパスの一覧) を返す。"""
    cutoff = now.timestamp() - days * 86400
    deleted, failed = [], []
    for target in TARGETS:
        root = os.path.join(data_dir, target)
        if not os.path.isdir(root):
            continue
        for folder, dirs, files in os.walk(root, topdown=False):
            emptied = False
            for name in files:
                path = os.path.join(folder, name)
                try:
                    if os.lstat(path).st_mtime >= cutoff:
                        continue
                    os.unlink(path)
                    deleted.append(path)
                    emptied = True
                except OSError:
                    failed.append(path)
            if folder == root:
                continue
            try:
                if not os.listdir(folder) and (emptied or os.stat(folder).st_mtime < cutoff):
                    os.rmdir(folder)
            except OSError:
                pass
    return deleted, failed
