import Foundation
import Testing
@testable import RecorderCore

/// 記録係の性能。毎回の TDD では回さず、全タスク完了後の動作確認と PR 作成前に回す
/// (`/bin/zsh scripts/swift_test.sh --filter RecorderCorePerfTests` か `/bin/zsh scripts/swiftc_test.sh --perf`)
@Suite("記録係の性能")
struct RecorderPerfTests {
    static let longTitle = String(repeating: "見積書_2026年度_第3四半期_", count: 60).prefix(990) + "…"

    func temporaryDirectory() -> URL {
        let base = ProcessInfo.processInfo.environment["TMPDIR"].map { URL(fileURLWithPath: $0, isDirectory: true) }
            ?? FileManager.default.temporaryDirectory
        let url = base.appendingPathComponent("rwf-perf-\(UUID().uuidString)", isDirectory: true)
        try! FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    func sampleLine(at time: Date) -> RecordLine {
        let surroundings = Surroundings(app: "Microsoft Excel", bundleId: "com.microsoft.Excel", monitor: 2, idleSec: 1.4,
                                        locked: false, mic: false, displaySleepPrevented: false)
        let window = WindowReadResult.read(WindowInfo(title: String(Self.longTitle), sheet: "集計", focusRole: "AXLayoutArea", focusSubrole: nil))
        return .sample(time: time, surroundings: surroundings, title: makeTitleFields(window))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#非機能要件-2
    @Test("記録するかの判定・除外の判定・行の組み立てが、1回あたり20ミリ秒以内に終わる")
    func tickDecisionIsFast() {
        let config = RecorderConfig(version: 1, endsAt: Date().addingTimeInterval(3_600), stoppedAt: nil,
                                    excludedApps: (0..<20).map { ExcludedApp(name: "アプリ\($0)", bundleId: "com.example.app\($0)") },
                                    excludedTitleWords: (0..<50).map { "ことば\($0)" })
        let rounds = 200
        let started = Date()
        for index in 0..<rounds {
            let now = Date()
            let decision = decideTick(config: .loaded(config), now: now, lastLine: LastLine(time: now.addingTimeInterval(-5), isStop: false),
                                      recordedPreviousTick: index > 0)
            _ = isExcludedApp(name: "Microsoft Excel", bundleId: "com.microsoft.Excel", excludedApps: config.excludedApps)
            _ = titleContainsExcludedWord(String(Self.longTitle), excludedTitleWords: config.excludedTitleWords)
            if decision.recording {
                _ = sampleLine(at: now).jsonLine()
            }
        }
        let averageMillis = Date().timeIntervalSince(started) * 1_000 / Double(rounds)
        print("1回あたりの判定と行の組み立て: \(String(format: "%.3f", averageMillis)) ミリ秒")
        #expect(averageMillis <= 20)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#非機能要件-3
    @Test("8時間分(5,760行・題名は上限近く)を書いたファイルが約66MB(100MBの2/3)以下に収まる")
    func eightHoursFitsInBudget() throws {
        let records = temporaryDirectory().appendingPathComponent("records")
        let writer = DailyFileWriter(recordsDirectory: records)
        let start = ISO8601DateFormatter().date(from: "2026-10-07T00:30:00Z")!
        for index in 0..<5_760 {
            try writer.append(sampleLine(at: start.addingTimeInterval(TimeInterval(index * 5))))
        }
        let total = try FileManager.default.contentsOfDirectory(at: records, includingPropertiesForKeys: [.fileSizeKey])
            .reduce(0) { $0 + ((try? $1.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0) }
        print("8時間分の記録の大きさ: \(total) バイト(\(String(format: "%.1f", Double(total) / 1_000_000)) MB)")
        #expect(total <= 66_000_000)
    }
}
