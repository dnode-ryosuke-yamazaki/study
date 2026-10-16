import Foundation

/// 5秒ごとの行に入れる周りの状態。取れなかった項目は nil(行には null で書く)
public struct Surroundings: Equatable, Sendable {
    public let app: String?
    public let bundleId: String?
    public let monitor: Int?
    public let idleSec: Double?
    public let locked: Bool?
    public let mic: Bool?
    public let displaySleepPrevented: Bool?

    public init(app: String?, bundleId: String?, monitor: Int?, idleSec: Double?, locked: Bool?, mic: Bool?, displaySleepPrevented: Bool?) {
        self.app = app
        self.bundleId = bundleId
        self.monitor = monitor
        self.idleSec = idleSec
        self.locked = locked
        self.mic = mic
        self.displaySleepPrevented = displaySleepPrevented
    }
}

/// 記録のファイルの1行。形は appendix.md「操作の記録の行の形」
public enum RecordLine: Equatable, Sendable {
    case start(time: Date)
    case stop(StopLine)
    /// 記録しないアプリ・ことばに当たった回。アプリ名も題名も持たない
    case excluded(time: Date)
    case sample(time: Date, surroundings: Surroundings, title: TitleFields)

    public var time: Date {
        switch self {
        case .start(let time), .excluded(let time), .sample(let time, _, _): return time
        case .stop(let stop): return stop.time
        }
    }

    /// 改行を含まない1行の JSON。項目は appendix.md の例と同じ順に並べる
    public func jsonLine() -> String {
        var fields: [(String, JSONValue)] = [("t", .string(JapanTime.timestamp(time)))]
        switch self {
        case .start:
            fields.append(("kind", .string("start")))
        case .stop(let stop):
            fields.append(("kind", .string("stop")))
            fields.append(("reason", .string(stop.reason.rawValue)))
        case .excluded:
            fields.append(("kind", .string("excluded")))
        case .sample(_, let surroundings, let title):
            fields.append(("kind", .string("sample")))
            fields.append(("app", .optionalString(surroundings.app)))
            fields.append(("bundleId", .optionalString(surroundings.bundleId)))
            fields.append(("monitor", surroundings.monitor.map { .int($0) } ?? .null))
            fields.append(("idleSec", surroundings.idleSec.map { .tenths($0) } ?? .null))
            fields.append(("locked", surroundings.locked.map { .bool($0) } ?? .null))
            fields.append(("mic", surroundings.mic.map { .bool($0) } ?? .null))
            fields.append(("displaySleepPrevented", surroundings.displaySleepPrevented.map { .bool($0) } ?? .null))
            if let reason = title.titleUnavailableReason {
                fields.append(("titleUnavailable", .bool(true)))
                fields.append(("titleReason", .string(reason.rawValue)))
            }
            if let text = title.title { fields.append(("title", .string(text))) }
            if title.titleTruncated { fields.append(("titleTruncated", .bool(true))) }
            if let sheet = title.sheet { fields.append(("sheet", .string(sheet))) }
            if let role = title.focusRole { fields.append(("focusRole", .string(role))) }
            if let subrole = title.focusSubrole { fields.append(("focusSubrole", .string(subrole))) }
        }
        return "{" + fields.map { "\(JSONValue.string($0.0).encoded):\($0.1.encoded)" }.joined(separator: ",") + "}"
    }
}

private enum JSONValue {
    case string(String)
    case int(Int)
    /// 小数第1位までの数(入力からの秒数)
    case tenths(Double)
    case bool(Bool)
    case null

    static func optionalString(_ text: String?) -> JSONValue {
        text.map { .string($0) } ?? .null
    }

    var encoded: String {
        switch self {
        case .string(let text):
            return jsonString(text)
        case .int(let number):
            return String(number)
        case .tenths(let number):
            return String(format: "%.1f", locale: Locale(identifier: "en_US_POSIX"), number)
        case .bool(let flag):
            return flag ? "true" : "false"
        case .null:
            return "null"
        }
    }
}
