"""実行係(launchd/digest_runner)の unittest。

テストは apps/digest-platform/application を作業フォルダにして
`python3 -m unittest discover -s tests/runner -t .` で回す。
実行係のパッケージは launchd/ の下にあるため、ここで launchd/ を import の探索先に足す。
"""

import os
import sys

LAUNCHD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "launchd"))
if LAUNCHD_DIR not in sys.path:
    sys.path.insert(0, LAUNCHD_DIR)
