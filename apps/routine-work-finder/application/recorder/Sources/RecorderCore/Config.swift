import Foundation

/// 記録しないアプリ。アプリ名かバンドルIDのどちらかが一致したら除外する
public struct ExcludedApp: Equatable, Sendable {
    public let name: String
    public let bundleId: String?

    public init(name: String, bundleId: String?) {
        self.name = name
        self.bundleId = bundleId
    }
}

/// 設定ファイル(config.json)の中身。形は appendix.md「設定ファイルの形」
public struct RecorderConfig: Equatable, Sendable {
    public let version: Int
    public let endsAt: Date?
    public let stoppedAt: Date?
    public let excludedApps: [ExcludedApp]
    public let excludedTitleWords: [String]

    public init(version: Int, endsAt: Date?, stoppedAt: Date?, excludedApps: [ExcludedApp], excludedTitleWords: [String]) {
        self.version = version
        self.endsAt = endsAt
        self.stoppedAt = stoppedAt
        self.excludedApps = excludedApps
        self.excludedTitleWords = excludedTitleWords
    }
}

/// 設定を読んだ結果。ファイルが無い(`missing`)と、読めない・形が違う(`unreadable`)を区別する
public enum ConfigLoadResult: Equatable, Sendable {
    case loaded(RecorderConfig)
    case missing
    /// 状態のファイルの `configError` に書く理由(例 "invalidJson" / "missingField:endsAt" / "invalidType:endsAt")
    case unreadable(String)
}

private struct ConfigFieldError: Error {
    let reason: String
}

public func parseConfig(_ data: Data) -> ConfigLoadResult {
    guard let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else {
        return .unreadable("invalidJson")
    }
    do {
        let version: Int = try requiredField(object, "version") { $0 as? Int }
        let endsAt: Date? = try requiredField(object, "endsAt", nullable: true) { parseDate($0) }
        let stoppedAt: Date? = try optionalField(object, "stoppedAt") { parseDate($0) }
        let excludedApps: [ExcludedApp] = try requiredField(object, "excludedApps") { parseExcludedApps($0) }
        let excludedTitleWords: [String] = try requiredField(object, "excludedTitleWords") { $0 as? [String] }
        return .loaded(RecorderConfig(
            version: version,
            endsAt: endsAt,
            stoppedAt: stoppedAt,
            excludedApps: excludedApps,
            excludedTitleWords: excludedTitleWords
        ))
    } catch let error as ConfigFieldError {
        return .unreadable(error.reason)
    } catch {
        return .unreadable("invalidJson")
    }
}

/// 設定ファイルを読む。ファイルが無ければ `missing`(「終わりの日時が無い」として扱う)
public func loadConfig(at url: URL) -> ConfigLoadResult {
    guard FileManager.default.fileExists(atPath: url.path) else {
        return .missing
    }
    guard let data = try? Data(contentsOf: url) else {
        return .unreadable("unreadable")
    }
    return parseConfig(data)
}

private func requiredField<T>(_ object: [String: Any], _ key: String, convert: (Any) -> T?) throws -> T {
    guard let raw = object[key] else {
        throw ConfigFieldError(reason: "missingField:\(key)")
    }
    guard let value = convert(raw) else {
        throw ConfigFieldError(reason: "invalidType:\(key)")
    }
    return value
}

/// 必須だが null を許す項目(endsAt)
private func requiredField<T>(_ object: [String: Any], _ key: String, nullable: Bool, convert: (Any) -> T?) throws -> T? {
    guard let raw = object[key] else {
        throw ConfigFieldError(reason: "missingField:\(key)")
    }
    if raw is NSNull {
        return nil
    }
    guard let value = convert(raw) else {
        throw ConfigFieldError(reason: "invalidType:\(key)")
    }
    return value
}

/// 欠けていても null とみなす項目(stoppedAt)
private func optionalField<T>(_ object: [String: Any], _ key: String, convert: (Any) -> T?) throws -> T? {
    guard let raw = object[key], !(raw is NSNull) else {
        return nil
    }
    guard let value = convert(raw) else {
        throw ConfigFieldError(reason: "invalidType:\(key)")
    }
    return value
}

private func parseDate(_ raw: Any) -> Date? {
    (raw as? String).flatMap(JapanTime.parseTimestamp)
}

private func parseExcludedApps(_ raw: Any) -> [ExcludedApp]? {
    guard let items = raw as? [Any] else { return nil }
    var apps: [ExcludedApp] = []
    for item in items {
        guard let entry = item as? [String: Any], let name = entry["name"] as? String else { return nil }
        let bundleId = entry["bundleId"]
        if let bundleId, !(bundleId is NSNull), !(bundleId is String) { return nil }
        apps.append(ExcludedApp(name: name, bundleId: bundleId as? String))
    }
    return apps
}
