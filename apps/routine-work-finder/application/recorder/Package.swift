// swift-tools-version:6.0
import PackageDescription

let package = Package(
    name: "rwf-recorder",
    platforms: [.macOS(.v14)],
    targets: [
        .target(name: "RecorderCore"),
        .executableTarget(name: "rwf-recorder", dependencies: ["RecorderCore"]),
        .testTarget(name: "RecorderCoreTests", dependencies: ["RecorderCore"]),
    ],
    swiftLanguageModes: [.v5]
)
