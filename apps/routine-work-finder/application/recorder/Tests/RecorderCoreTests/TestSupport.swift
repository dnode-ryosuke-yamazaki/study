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

extension AxRawResponse {
    /// tests/fixtures/ax/ の1件(タスク1の確認用プログラムが書いた形)から作る。打ち切りは確認用プログラムでは起きていないので false
    init?(fixture: [String: Any]) {
        func attribute(_ raw: Any?) -> AxAttribute? {
            guard let object = raw as? [String: Any], let error = object["error"] as? Int else { return nil }
            return AxAttribute(error: Int32(error), value: object["value"] as? String)
        }
        guard let trusted = fixture["trusted"] as? Bool, let windowError = fixture["focusedWindowError"] as? Int else { return nil }
        let sheet = fixture["sheet"] as? [String: Any]
        self.init(
            trusted: trusted,
            timedOut: false,
            focusedWindowError: Int32(windowError),
            title: attribute(fixture["title"]),
            selectedSheet: attribute(sheet?["selectedTitle"]),
            focusedElementError: (fixture["focusedElementError"] as? Int).map(Int32.init),
            role: attribute(fixture["role"]),
            subrole: attribute(fixture["subrole"])
        )
    }
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
