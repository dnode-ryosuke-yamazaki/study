import Foundation

/// 前面のアプリの表示名とバンドルID
public struct FrontAppInfo: Equatable, Sendable {
    public let name: String?
    public let bundleId: String?

    public init(name: String?, bundleId: String?) {
        self.name = name
        self.bundleId = bundleId
    }
}

/// ログのレベル(appendix.md「ログの書式」)
public enum LogLevel: String, Sendable {
    case info = "INFO"
    case warn = "WARN"
    case error = "ERROR"
}

/// 記録係が外の世界に尋ねる・書き込む部分。本番は macOS とデータフォルダ、テストは偽物を渡す
public protocol RecorderEnvironment: AnyObject {
    func now() -> Date
    /// 設定ファイルを読む(更新日時が変わっていなければ前回の結果を返してよい)
    func loadConfig() -> ConfigLoadResult
    func frontApp() -> FrontAppInfo?
    func surroundings(for app: FrontAppInfo?) -> Surroundings
    /// 今の前面のアプリの、前面ウィンドウの題名・シート名・部品の種類を読む
    func readWindow() -> WindowReadResult
    func accessibilityGranted() -> Bool
    /// いちばん新しい記録のファイルの最後の行。起動した最初の回だけ呼ぶ
    func readLastLine() -> LastLine
    func append(_ line: RecordLine) throws
    func purgeOldFiles(now: Date) -> PurgeResult
    func writeStatus(_ status: RecorderStatus) throws
    func log(_ level: LogLevel, _ message: String)
}

/// 5秒ごとの1回分の流れ(design.md「5秒ごとに操作と題名を記録する」「4週間より古い記録を消す」)
public final class RecorderLoop {
    let environment: RecorderEnvironment
    private var lastLine: LastLine?
    private var recordedPreviousTick = false
    private var lastPurgeDate: String?
    private var lastConfigError: String?
    private var lastLoadedConfig: RecorderConfig?
    private var lastTitleReason: TitleUnavailableReason?
    private var lastWriteError: String?

    public init(environment: RecorderEnvironment) {
        self.environment = environment
    }

    public func tick() {
        let started = environment.now()
        let now = started
        if lastLine == nil {
            environment.log(.info, "recorder started")
            lastLine = environment.readLastLine()
        }
        purgeIfDayChanged(now: now)

        let config = environment.loadConfig()
        let decision = decideTick(config: config, now: now, lastLine: lastLine ?? .assumedStop,
                                  recordedPreviousTick: recordedPreviousTick)
        logConfigErrorChange(decision.configError)
        logConfigReload(config)

        var wroteAll = true
        if let stop = decision.stopLine {
            if write(.stop(stop)) {
                lastLine = LastLine(time: stop.time, isStop: true)
                environment.log(.info, "recording stopped reason=\(stop.reason.rawValue)")
            }
        }
        if decision.recording, case .loaded(let loaded) = config {
            wroteAll = recordSample(now: now, config: loaded, writeStart: decision.writeStart)
        }
        recordedPreviousTick = decision.recording && wroteAll

        let elapsed = Int((environment.now().timeIntervalSince(started) * 1000).rounded())
        let status = RecorderStatus(updatedAt: now, recording: decision.recording, tickMillis: elapsed,
                                    configError: decision.configError, lastWriteError: lastWriteError,
                                    accessibilityGranted: environment.accessibilityGranted(), lastPurgeDate: lastPurgeDate)
        do {
            try environment.writeStatus(status)
        } catch {
            environment.log(.error, "status write failed error=\(describe(error))")
        }
    }

    /// 開始の行(必要なら)と、除外中または通常の行を書く。すべて書けたら true
    private func recordSample(now: Date, config: RecorderConfig, writeStart: Bool) -> Bool {
        if writeStart {
            guard write(.start(time: now)) else { return false }
            // 続く行が書けなくても、終わりの日時を過ぎたら停止の行で期間を閉じられるよう、開始の行を最後の行として覚える
            lastLine = LastLine(time: now, isStop: false)
            environment.log(.info, "recording started")
        }
        let app = environment.frontApp()
        let line: RecordLine
        if isExcludedApp(name: app?.name, bundleId: app?.bundleId, excludedApps: config.excludedApps) {
            line = .excluded(time: now)
        } else {
            let surroundings = environment.surroundings(for: app)
            let window = environment.readWindow()
            logTitleReasonChange(window)
            if case .read(let info) = window, let title = info.title,
               titleContainsExcludedWord(title, excludedTitleWords: config.excludedTitleWords) {
                line = .excluded(time: now)
            } else {
                line = .sample(time: now, surroundings: surroundings, title: makeTitleFields(window))
            }
        }
        guard write(line) else { return false }
        lastLine = LastLine(time: now, isStop: false)
        return true
    }

    private func write(_ line: RecordLine) -> Bool {
        do {
            try environment.append(line)
            lastWriteError = nil
            return true
        } catch {
            let message = describe(error)
            lastWriteError = message
            environment.log(.error, "write failed error=\(message)")
            return false
        }
    }

    private func purgeIfDayChanged(now: Date) {
        guard shouldPurge(now: now, lastPurgeDate: lastPurgeDate) else { return }
        let result = environment.purgeOldFiles(now: now)
        environment.log(.info, "purge removed=\(result.deletedCount)")
        if !result.failedPaths.isEmpty {
            // データフォルダの中の「フォルダ名/ファイル名」だけを書く(ファイル名は日付だけ)
            let names = result.failedPaths.map { path in
                let url = URL(fileURLWithPath: path)
                return "\(url.deletingLastPathComponent().lastPathComponent)/\(url.lastPathComponent)"
            }
            environment.log(.warn, "purge failed count=\(names.count) files=\(names.joined(separator: ","))")
        }
        lastPurgeDate = JapanTime.dateString(now)
    }

    private func logConfigErrorChange(_ configError: String?) {
        guard configError != lastConfigError else { return }
        if let configError {
            environment.log(.warn, "config unreadable reason=\(configError)")
        } else {
            environment.log(.info, "config readable")
        }
        lastConfigError = configError
    }

    /// 読めた設定の中身が前回読めたものから変わったときだけ書く(起動して最初に読んだときは書かない)
    private func logConfigReload(_ config: ConfigLoadResult) {
        guard case .loaded(let loaded) = config else { return }
        if let lastLoadedConfig, lastLoadedConfig != loaded {
            environment.log(.info, "config reloaded")
        }
        lastLoadedConfig = loaded
    }

    private func logTitleReasonChange(_ window: WindowReadResult) {
        var reason: TitleUnavailableReason?
        if case .unavailable(let current) = window { reason = current }
        guard reason != lastTitleReason else { return }
        if let reason {
            environment.log(.warn, "title unavailable reason=\(reason.rawValue)")
        } else {
            environment.log(.info, "title available")
        }
        lastTitleReason = reason
    }

    private func describe(_ error: Error) -> String {
        if let posix = error as? POSIXError { return "errno\(posix.code.rawValue)" }
        let nsError = error as NSError
        return "\(nsError.domain)#\(nsError.code)"
    }
}
