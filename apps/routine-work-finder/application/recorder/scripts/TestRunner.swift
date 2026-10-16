// scripts/swiftc_test.sh が使うテストの実行役。swift test では使わない(SwiftPM が自前の実行役を作る)。
import Testing

@main
struct TestRunner {
    static func main() async {
        await Testing.__swiftPMEntryPoint() as Never
    }
}
