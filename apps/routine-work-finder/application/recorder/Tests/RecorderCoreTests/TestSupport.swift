import Foundation
@testable import RecorderCore

/// 日本時間の日時の文字列(例 "2026-10-07T18:00:00")から Date を作る
func jst(_ text: String) -> Date {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    guard let date = formatter.date(from: text + "+09:00") else {
        fatalError("日時の形が違う: \(text)")
    }
    return date
}

func config(endsAt: Date?, stoppedAt: Date? = nil) -> ConfigLoadResult {
    .loaded(RecorderConfig(
        version: 1,
        endsAt: endsAt,
        stoppedAt: stoppedAt,
        excludedApps: [],
        excludedTitleWords: []
    ))
}

/// 判定どおりに行を書いたとして、記録係が覚えておく最後の行と「この回に記録したか」を進める
func apply(_ decision: TickDecision, now: Date, to lastLine: LastLine) -> LastLine {
    if let stop = decision.stopLine {
        return LastLine(time: stop.time, isStop: true)
    }
    if decision.recording {
        return LastLine(time: now, isStop: false)
    }
    return lastLine
}

/// テスト用の一時フォルダ。環境変数 TMPDIR があればその下に作る
/// (FileManager の既定の一時フォルダは TMPDIR を見ないため、書き込み先を限られた環境で書けないことがある)
func temporaryDirectory() -> URL {
    let base = ProcessInfo.processInfo.environment["TMPDIR"].map { URL(fileURLWithPath: $0, isDirectory: true) }
        ?? FileManager.default.temporaryDirectory
    let url = base.appendingPathComponent("rwf-tests-\(UUID().uuidString)", isDirectory: true)
    try! FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    return url
}
