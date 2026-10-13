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
    ],
    swiftLanguageModes: [.v5]
)
