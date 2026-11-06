"""実行係の性能テスト(tests/perf)。毎回の TDD では回さず、単独で回す:

    python3 -m unittest discover -s tests/perf -t .

実行係のパッケージは launchd/ の下にあるため、ここで launchd/ を import の探索先に足す。
"""

import os
import sys

LAUNCHD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "launchd"))
if LAUNCHD_DIR not in sys.path:
    sys.path.insert(0, LAUNCHD_DIR)
