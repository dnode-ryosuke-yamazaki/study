import Foundation

/// 状態のファイル(recorder-status.json)の中身。形は appendix.md「状態のファイルの形」
public struct RecorderStatus: Equatable, Sendable {
    public let updatedAt: Date
    public let recording: Bool
    public let tickMillis: Int
    public let configError: String?
    public let lastWriteError: String?
    public let accessibilityGranted: Bool
    public let lastPurgeDate: String?

    public init(updatedAt: Date, recording: Bool, tickMillis: Int, configError: String?, lastWriteError: String?,
                accessibilityGranted: Bool, lastPurgeDate: String?) {
        self.updatedAt = updatedAt
        self.recording = recording
        self.tickMillis = tickMillis
        self.configError = configError
        self.lastWriteError = lastWriteError
        self.accessibilityGranted = accessibilityGranted
        self.lastPurgeDate = lastPurgeDate
    }

    public func json() -> String {
        let fields: [(String, String)] = [
            ("version", "1"),
            ("updatedAt", jsonString(JapanTime.timestamp(updatedAt))),
            ("recording", recording ? "true" : "false"),
            ("tickMillis", String(tickMillis)),
            ("configError", configError.map(jsonString) ?? "null"),
            ("lastWriteError", lastWriteError.map(jsonString) ?? "null"),
            ("accessibilityGranted", accessibilityGranted ? "true" : "false"),
            ("lastPurgeDate", lastPurgeDate.map(jsonString) ?? "null"),
        ]
        return "{" + fields.map { "\(jsonString($0.0)):\($0.1)" }.joined(separator: ",") + "}"
    }
}

/// 状態のファイルを、同じフォルダの一時ファイル(600)に書いてから名前を付け替えて置く
public func writeStatusFile(_ status: RecorderStatus, to url: URL) throws {
    let temporary = url.deletingLastPathComponent().appendingPathComponent(url.lastPathComponent + ".tmp")
    let descriptor = open(temporary.path, O_WRONLY | O_CREAT | O_TRUNC, 0o600)
    guard descriptor >= 0 else {
        throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO)
    }
    let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
    try handle.write(contentsOf: Data((status.json() + "\n").utf8))
    try handle.close()
    guard rename(temporary.path, url.path) == 0 else {
        throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO)
    }
}

/// 文字列を JSON の文字列として書く(日本語はそのまま、/ はエスケープしない)
func jsonString(_ text: String) -> String {
    let data = try! JSONSerialization.data(withJSONObject: text, options: [.fragmentsAllowed, .withoutEscapingSlashes])
    return String(decoding: data, as: UTF8.self)
}
