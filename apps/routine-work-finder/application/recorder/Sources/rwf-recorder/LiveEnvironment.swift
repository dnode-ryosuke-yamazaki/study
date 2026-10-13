import Foundation
import RecorderCore

/// 本番の環境。macOS に尋ね、データフォルダ(~/Library/Application Support/routine-work-finder)に書く
final class LiveEnvironment: RecorderEnvironment {
    let dataDirectory: URL
    let recordsDirectory: URL
    let memosDirectory: URL
    let configURL: URL
    let statusURL: URL
    private var currentApp: FrontApp?
    private var cachedConfig: (modified: Date, result: ConfigLoadResult)?

    init(home: URL = FileManager.default.homeDirectoryForCurrentUser) {
        dataDirectory = home.appendingPathComponent("Library/Application Support/routine-work-finder", isDirectory: true)
        recordsDirectory = dataDirectory.appendingPathComponent("records", isDirectory: true)
        memosDirectory = dataDirectory.appendingPathComponent("memos", isDirectory: true)
        configURL = dataDirectory.appendingPathComponent("config.json")
        statusURL = dataDirectory.appendingPathComponent("recorder-status.json")
    }

    func now() -> Date { Date() }

    /// 設定ファイルの更新日時が前回と同じなら、読み直さずに前回の結果を使う
    func loadConfig() -> ConfigLoadResult {
        guard let attributes = try? FileManager.default.attributesOfItem(atPath: configURL.path),
              let modified = attributes[.modificationDate] as? Date
        else {
            cachedConfig = nil
            return RecorderCore.loadConfig(at: configURL)
        }
        if let cachedConfig, cachedConfig.modified == modified {
            return cachedConfig.result
        }
        let result = RecorderCore.loadConfig(at: configURL)
        cachedConfig = (modified, result)
        return result
    }

    func frontApp() -> FrontAppInfo? {
        currentApp = SystemProbe.frontApp()
        return currentApp.map { FrontAppInfo(name: $0.name, bundleId: $0.bundleId) }
    }

    func surroundings(for app: FrontAppInfo?) -> Surroundings {
        SystemProbe.surroundings(for: currentApp)
    }

    func readWindow() -> WindowReadResult {
        guard let currentApp else { return .unavailable(.noWindow) }
        return parseAxResponse(AxReader.read(app: currentApp))
    }

    func accessibilityGranted() -> Bool {
        AxReader.isTrusted()
    }

    func readLastLine() -> LastLine {
        RecorderCore.readLastLine(recordsDirectory: recordsDirectory)
    }

    func append(_ line: RecordLine) throws {
        try ensureDataDirectory()
        try DailyFileWriter(recordsDirectory: recordsDirectory).append(line)
    }

    func purgeOldFiles(now: Date) -> PurgeResult {
        RecorderCore.purgeOldFiles(directories: [recordsDirectory, memosDirectory], now: now)
    }

    func writeStatus(_ status: RecorderStatus) throws {
        try ensureDataDirectory()
        try writeStatusFile(status, to: statusURL)
    }

    /// ログは標準エラーに書く(launchd が ~/Library/Logs/routine-work-finder-recorder.log へ流す)
    func log(_ level: LogLevel, _ message: String) {
        let line = "\(JapanTime.timestamp(now())) \(level.rawValue) \(message)\n"
        FileHandle.standardError.write(Data(line.utf8))
    }

    private func ensureDataDirectory() throws {
        guard !FileManager.default.fileExists(atPath: dataDirectory.path) else { return }
        try FileManager.default.createDirectory(at: dataDirectory, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
    }
}
