import Foundation
import Testing
@testable import RecorderCore

/// 記録の行を日本時間の日付ごとのファイルに書き足す処理。
/// 記録は自分だけが読めるようにし(フォルダ700・ファイル600)、日付は日本時間で区切る。
@Suite("記録の行を日ごとのファイルに書き足す")
struct DailyFileWriterTests {
    func permissions(_ url: URL) throws -> Int {
        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        return (attributes[.posixPermissions] as? NSNumber)?.intValue ?? -1
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録を残す場所と期間-1
    /// 否定確認: フォルダ・ファイルの権限を指定せずに作ると落ちる
    @Test("記録のフォルダは700、記録のファイルは600で作る")
    func createsWithOwnerOnlyPermissions() throws {
        let records = temporaryDirectory().appendingPathComponent("records")
        try DailyFileWriter(recordsDirectory: records).append(.start(time: jst("2026-10-07T09:00:00")))
        #expect(try permissions(records) == 0o700)
        #expect(try permissions(records.appendingPathComponent("2026-10-07.jsonl")) == 0o600)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#日付と週の基準-1
    /// 否定確認: ファイル名の日付を UTC で求めると落ちる
    @Test("日本時間の23:59:59の行はその日のファイルに、0:00:00の行は翌日のファイルに書く")
    func splitsFilesByJapanDate() throws {
        let records = temporaryDirectory().appendingPathComponent("records")
        let writer = DailyFileWriter(recordsDirectory: records)
        try writer.append(.excluded(time: jst("2026-10-07T23:59:59")))
        try writer.append(.excluded(time: jst("2026-10-08T00:00:00")))
        let first = try String(contentsOf: records.appendingPathComponent("2026-10-07.jsonl"), encoding: .utf8)
        let second = try String(contentsOf: records.appendingPathComponent("2026-10-08.jsonl"), encoding: .utf8)
        #expect(first == #"{"t":"2026-10-07T23:59:59+09:00","kind":"excluded"}"# + "\n")
        #expect(second == #"{"t":"2026-10-08T00:00:00+09:00","kind":"excluded"}"# + "\n")
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-1
    /// 否定確認: 書き足さずに上書きすると落ちる
    @Test("同じ日のファイルには、前の行を残したまま1行ずつ書き足す")
    func appendsToExistingFile() throws {
        let records = temporaryDirectory().appendingPathComponent("records")
        let writer = DailyFileWriter(recordsDirectory: records)
        try writer.append(.start(time: jst("2026-10-07T09:00:00")))
        try writer.append(.excluded(time: jst("2026-10-07T09:00:05")))
        let contents = try String(contentsOf: records.appendingPathComponent("2026-10-07.jsonl"), encoding: .utf8)
        #expect(contents.split(separator: "\n").count == 2)
        #expect(parseLastLine(contents) == LastLine(time: jst("2026-10-07T09:00:05"), isStop: false))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-1
    /// 否定確認: 書きかけの最終行のすぐ後ろに続けて書くと、次の行まで読めない1行になり落ちる
    @Test("前回の最終行が書きかけ(改行で終わらない)なら、改行を補ってから書き足し、書きかけの行は消さない")
    func startsNewLineAfterPartialLastLine() throws {
        let records = temporaryDirectory().appendingPathComponent("records")
        let writer = DailyFileWriter(recordsDirectory: records)
        try writer.append(.start(time: jst("2026-10-07T09:00:00")))
        let file = records.appendingPathComponent("2026-10-07.jsonl")
        let handle = try FileHandle(forWritingTo: file)
        try handle.seekToEnd()
        try handle.write(contentsOf: Data(#"{"t":"2026-10-07T09:00:05+09:00","ki"#.utf8))
        try handle.close()

        try writer.append(.stop(StopLine(time: jst("2026-10-07T18:00:00"), reason: .endsAtPassed)))
        let contents = try String(contentsOf: file, encoding: .utf8)
        #expect(contents.split(separator: "\n").count == 3)
        #expect(contents.contains(#"{"t":"2026-10-07T09:00:05+09:00","ki"# + "\n"))
        #expect(parseLastLine(contents) == LastLine(time: jst("2026-10-07T18:00:00"), isStop: true))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    @Test("停止の行は、その時刻の日本時間の日付のファイルに書く")
    func stopLineGoesToItsOwnDate() throws {
        let records = temporaryDirectory().appendingPathComponent("records")
        try DailyFileWriter(recordsDirectory: records).append(.stop(StopLine(time: jst("2026-10-07T18:00:00"), reason: .endsAtPassed)))
        #expect(FileManager.default.fileExists(atPath: records.appendingPathComponent("2026-10-07.jsonl").path))
    }
}

/// 週次レポート側(Python)の契約テストが読む fixture を、記録係の書く形と同じに保つ。
/// fixture を書き換えるときは RWF_FIXTURE_OUT にフォルダを指定してこのテストを回し、出てきたファイルで置き換える。
@Suite("記録の行の fixture")
struct RecordLineFixtureTests {
    static let fixtureURL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("tests/fixtures/recorder_lines/records.jsonl")

    static func generatedLines() -> String {
        let surroundings = Surroundings(app: "Microsoft Excel", bundleId: "com.microsoft.Excel", monitor: 2,
                                        idleSec: 1.4, locked: false, mic: false, displaySleepPrevented: false)
        let teams = Surroundings(app: "Microsoft Teams", bundleId: "com.microsoft.teams2", monitor: 1,
                                 idleSec: 3.0, locked: false, mic: true, displaySleepPrevented: true)
        let lines: [RecordLine] = [
            .start(time: jst("2026-10-06T09:00:00")),
            .sample(time: jst("2026-10-06T09:00:00"), surroundings: surroundings,
                    title: makeTitleFields(.read(WindowInfo(title: "見積_2026.xlsx", sheet: "集計", focusRole: "AXLayoutArea", focusSubrole: nil)))),
            .sample(time: jst("2026-10-06T09:00:05"), surroundings: teams,
                    title: makeTitleFields(.read(WindowInfo(title: "チャット | Microsoft Teams", sheet: nil, focusRole: nil, focusSubrole: nil)))),
            .sample(time: jst("2026-10-06T09:00:10"), surroundings: teams, title: makeTitleFields(.unavailable(.timeout))),
            .excluded(time: jst("2026-10-06T09:00:15")),
            .stop(StopLine(time: jst("2026-10-06T18:00:00"), reason: .endsAtPassed)),
        ]
        return lines.map { $0.jsonLine() + "\n" }.joined()
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-1
    @Test("記録係が書く行と、契約テスト用の fixture が一致している")
    func fixtureMatchesWriter() throws {
        let generated = Self.generatedLines()
        if let outDir = ProcessInfo.processInfo.environment["RWF_FIXTURE_OUT"] {
            try generated.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("records.jsonl"), atomically: false, encoding: .utf8)
        }
        let fixture = try String(contentsOf: Self.fixtureURL, encoding: .utf8)
        #expect(fixture == generated)
    }
}
