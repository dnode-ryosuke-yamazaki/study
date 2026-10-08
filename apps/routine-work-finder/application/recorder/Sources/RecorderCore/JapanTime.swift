import Foundation

/// 記録の日付・時刻は日本時間で決める(requirements.md#日付と週の基準)
public enum JapanTime {
    public static let timeZone = TimeZone(identifier: "Asia/Tokyo")!

    /// 記録のファイル名に使う日本時間の日付(例 "2026-10-07")
    public static func dateString(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = timeZone
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    /// 時差付きの ISO 8601 の文字列(例 "2026-10-07T18:00:00+09:00")を読む。読めなければ nil
    public static func parseTimestamp(_ text: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: text)
    }
}
