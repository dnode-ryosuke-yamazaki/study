#!/bin/bash
# 記録係をビルドし、自己署名の証明書で署名して決まった場所に置き、launchd の設定ファイルを置く。
# 作り直すたびに同じ手順で置き直す。署名の証明書と識別子が同じなので、アクセシビリティの許可は付け直さなくてよい。
# launchd への登録(bootout → bootstrap)は、このスクリプトのあとに手元のターミナルで行う(README のセットアップ)。
# 変数名は ASCII だけにする(launchd から動く /bin/bash 3.2 の制約に合わせる)。
set -eu

application_dir="$(cd "$(dirname "$0")/.." && pwd)"
recorder_dir="$application_dir/recorder"
data_dir="$HOME/Library/Application Support/routine-work-finder"
bin_dir="$data_dir/bin"
recorder_path="$bin_dir/rwf-recorder"
plist_name="com.example.routine-work-finder-recorder.plist"
plist_path="$HOME/Library/LaunchAgents/com.example.routine-work-finder-recorder.plist"

cd "$recorder_dir"
swift build -c release --product rwf-recorder
build_dir="$(swift build -c release --show-bin-path)"

mkdir -p "$bin_dir"
chmod 700 "$data_dir"
cp "$build_dir/rwf-recorder" "$recorder_path"
codesign --force --sign "routine-work-finder code signing" --identifier com.example.routine-work-finder.recorder "$recorder_path"
codesign --verify --verbose "$recorder_path"

mkdir -p "$HOME/Library/LaunchAgents"
sed "s|__HOME__|$HOME|g" "$application_dir/launchd/$plist_name" > "$plist_path"
plutil -lint "$plist_path"

echo "記録係を置きました: $recorder_path"
echo "launchd の設定ファイルを置きました: $plist_path"
