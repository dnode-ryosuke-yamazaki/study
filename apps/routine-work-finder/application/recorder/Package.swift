// swift-tools-version:6.0
import PackageDescription

let package = Package(
    name: "rwf-recorder",
    platforms: [.macOS(.v14)],
    targets: [
        .target(name: "RecorderCore"),
        .executableTarget(name: "rwf-recorder", dependencies: ["RecorderCore"]),
        // Fixtures は操作スクリプトが書き出した設定ファイル。テストが #filePath から読むのでビルドには含めない
        .testTarget(name: "RecorderCoreTests", dependencies: ["RecorderCore"], exclude: ["Fixtures"]),
        // 性能テスト。毎回の TDD では回さない(scripts/swift_test.sh は既定で外す)
        .testTarget(name: "RecorderCorePerfTests", dependencies: ["RecorderCore"]),
    ],
    swiftLanguageModes: [.v5]
)
