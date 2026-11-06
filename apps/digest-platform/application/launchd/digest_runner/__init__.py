"""digest-platform の実行係(batch-runner)。

launchd(または運営者の手元ターミナル)から launchd/runner.py 経由で起動され、
アプリのバッチを起動して成否を判定し、実行状態ファイルと要約ログに残す。
Python 3 の標準ライブラリだけを使う(個人の共有ライブラリは参照しない)。
"""
