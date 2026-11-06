"""層分け検査にかかる時間の性能テスト。

/spec-review はレビューのたびにこの検査を回すため、待たされると検査を飛ばす動機が
生まれる。実物のspec(spec-reading-layers)で所要時間を測る。TDDの毎サイクルでは
回さず、全タスク完了後の動作確認とPR作成前に1回だけ回す。

実行:
    python3 -m unittest lib/spec_layout_check/tests/perf/test_check_time.py

仕様: ~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers/
  requirements.md#非機能要件-2、design.md#テスト戦略(非機能要件-2)
"""
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

# 要件は5秒以内。余裕を持って2/3の3秒を閾値にする(要件ぎりぎりで合格させない)
TIME_LIMIT_SECONDS = 3.0

SCRIPT = (Path(__file__).resolve().parents[2] / "scripts" / "check_spec_layout.py")
SPEC_DIR = Path(os.path.expanduser(
    "~/.claude/local-specs/Users/ryosyamazaki/.claude/specs/spec-reading-layers"))


class 検査の所要時間(unittest.TestCase):
    """実物のspec1つぶんの検査が、待たされない時間で終わることを確かめる。"""

    # 仕様: requirements.md#非機能要件-2
    def test_1specの検査が閾値の秒数以内に終わること(self):
        self.assertTrue(SPEC_DIR.exists(), "対象specが見つからない: %s" % SPEC_DIR)
        started = time.monotonic()
        done = subprocess.run([sys.executable, str(SCRIPT), str(SPEC_DIR)],
                              capture_output=True, text=True)
        elapsed = time.monotonic() - started
        self.assertIn(done.returncode, (0, 1, 2), done.stderr)
        self.assertLess(elapsed, TIME_LIMIT_SECONDS,
                        "検査に %.2f 秒かかった(閾値 %.1f 秒)" % (elapsed, TIME_LIMIT_SECONDS))


if __name__ == "__main__":
    unittest.main()
