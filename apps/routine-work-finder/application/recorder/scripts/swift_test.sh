#!/bin/zsh
# 記録係のテストを swift test で回す(正式な実行方法)。
# Command Line Tools の swift test は、Swift Testing のマクロ部品(TestingMacros)の場所をコンパイラに渡し忘れることがあり、
# `plugin for module 'TestingMacros' not found` でビルドが失敗する(同じパッケージでも通る回と落ちる回がある)。
# 場所を明示すると毎回通るため、ここで指定する。
# 使い方: /bin/zsh scripts/swift_test.sh [swift test に渡す引数]
#   引数なし: 性能テスト(RecorderCorePerfTests)を除いて回す
#   性能テスト: /bin/zsh scripts/swift_test.sh --filter RecorderCorePerfTests
set -eu

cd ${0:A:h:h}
plugin_dir=$(xcode-select -p)/usr/lib/swift/host/plugins/testing
if (( $# == 0 )); then
  set -- --skip RecorderCorePerfTests
fi
exec swift test -Xswiftc -plugin-path -Xswiftc $plugin_dir "$@"
