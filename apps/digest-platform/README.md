# digest-platform

Digest系5アプリの共通基盤。仕様は [specs/architecture.md](specs/architecture.md) を参照。

## 実行係(Python)のテスト

```bash
cd "$HOME/repo/study/apps/digest-platform/application"
python3 -m unittest discover -s tests/runner -t .
```

Python 3 の標準ライブラリだけを使う(`requirements.txt` は無い)。
