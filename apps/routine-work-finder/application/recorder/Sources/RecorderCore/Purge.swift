import Foundation

/// 記録・メモを残す日数(requirements.md#古い記録の削除-1)
public let retentionDays = 28

public struct PurgeResult: Equatable, Sendable {
    public let deletedCount: Int
    /// 消せなかったファイル。ログに書き、翌日にもう一度試す
    public let failedPaths: [String]
}

/// 消す対象のファイル名を選ぶ。日付の形のファイルのうち、日付が今日(日本時間)の28日前より古いもの
public func selectFilesToPurge(names: [String], now: Date) -> [String] {
    let cutoff = cutoffDateString(now: now)
    return names.filter { name in
        name.range(of: recordFileNamePattern, options: .regularExpression) != nil
            && String(name.prefix(10)) < cutoff
    }
}

/// 日付が変わって最初の回(起動した最初の回を含む)か。記録を止めているかどうかには依らない
public func shouldPurge(now: Date, lastPurgeDate: String?) -> Bool {
    lastPurgeDate != JapanTime.dateString(now)
}

/// 各フォルダから古いファイルを消す。フォルダが無ければ何もしない
public func purgeOldFiles(directories: [URL], now: Date) -> PurgeResult {
    var deleted = 0
    var failed: [String] = []
    for directory in directories {
        guard let names = try? FileManager.default.contentsOfDirectory(atPath: directory.path) else { continue }
        for name in selectFilesToPurge(names: names, now: now) {
            let path = directory.appendingPathComponent(name).path
            do {
                try FileManager.default.removeItem(atPath: path)
                deleted += 1
            } catch {
                failed.append(path)
            }
        }
    }
    return PurgeResult(deletedCount: deleted, failedPaths: failed)
}

/// 今日(日本時間)の28日前の日付。これより古い日付のファイルを消す
private func cutoffDateString(now: Date) -> String {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = JapanTime.timeZone
    let today = calendar.startOfDay(for: now)
    let cutoff = calendar.date(byAdding: .day, value: -retentionDays, to: today)!
    return JapanTime.dateString(cutoff)
}
