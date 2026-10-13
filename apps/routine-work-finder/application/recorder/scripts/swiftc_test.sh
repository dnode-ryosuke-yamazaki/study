#!/bin/zsh
# RecorderCore のテストを SwiftPM を通さずに swiftc で回す。
# 正式な実行は scripts/swift_test.sh。swift build / swift test が動かない環境(Claude Code のサンドボックス)向け。
# 使い方: /bin/zsh scripts/swiftc_test.sh [出力先フォルダ]
set -eu

recorder_dir=${0:A:h:h}
out_dir=${1:-${TMPDIR:-/tmp}/rwf-recorder-swiftc}
clt=/Library/Developer/CommandLineTools
frameworks=$clt/Library/Developer/Frameworks
common=(-target arm64-apple-macosx14.0 -module-cache-path $out_dir/module-cache -swift-version 5)

mkdir -p $out_dir

swiftc $common -parse-as-library -emit-library -emit-module -enable-testing \
  -module-name RecorderCore $recorder_dir/Sources/RecorderCore/*.swift \
  -o $out_dir/libRecorderCore.dylib -emit-module-path $out_dir/RecorderCore.swiftmodule

# 記録係の実行ファイルもコンパイルが通ることだけを確かめる(macOS に尋ねる部分はテストを持たない)
swiftc $common -module-name rwf_recorder -I $out_dir -L $out_dir -lRecorderCore \
  -Xlinker -rpath -Xlinker $out_dir \
  $recorder_dir/Sources/rwf-recorder/*.swift -o $out_dir/rwf-recorder

swiftc $common -parse-as-library -module-name RecorderCoreTests \
  -I $out_dir -L $out_dir -lRecorderCore \
  -F $frameworks -framework Testing -plugin-path $clt/usr/lib/swift/host/plugins/testing \
  -Xlinker -rpath -Xlinker $frameworks \
  -Xlinker -rpath -Xlinker $clt/Library/Developer/usr/lib \
  -Xlinker -rpath -Xlinker $out_dir \
  $recorder_dir/Tests/RecorderCoreTests/*.swift $recorder_dir/scripts/TestRunner.swift \
  -o $out_dir/RecorderCoreTests

$out_dir/RecorderCoreTests
