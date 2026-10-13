import Foundation
import Testing
@testable import RecorderCore

/// 偽物の環境。時刻・設定・前面のアプリ・題名の読み取りを決め打ちにし、書いた行・状態・ログを覚える
final class FakeEnvironment: RecorderEnvironment {
    var clock: Date
    var config: ConfigLoadResult
    var app: FrontAppInfo? = FrontAppInfo(name: "Microsoft Excel", bundleId: "com.microsoft.Excel")
    var window: WindowReadResult = .read(WindowInfo(title: "見積_2026.xlsx", sheet: "集計", focusRole: "AXLayoutArea", focusSubrole: nil))
    var granted = true
    var initialLastLine: LastLine = .assumedStop
    var failWrites = false
    var purgeResult = PurgeResult(deletedCount: 0, failedPaths: [])

    private(set) var lines: [RecordLine] = []
    private(set) var statuses: [RecorderStatus] = []
    private(set) var logs: [String] = []
    private(set) var windowReads = 0
    private(set) var purges = 0
    private(set) var lastLineReads = 0

    init(now: Date, config: ConfigLoadResult) {
        self.clock = now
        self.config = config
    }

    func now() -> Date { clock }
    func loadConfig() -> ConfigLoadResult { config }
    func frontApp() -> FrontAppInfo? { app }
    func surroundings(for app: FrontAppInfo?) -> Surroundings {
        Surroundings(app: app?.name, bundleId: app?.bundleId, monitor: 1, idleSec: 0.5, locked: false, mic: false, displaySleepPrevented: false)
    }
    func readWindow() -> WindowReadResult {
        windowReads += 1
        return window
    }
    func accessibilityGranted() -> Bool { granted }
    func readLastLine() -> LastLine {
        lastLineReads += 1
        return initialLastLine
    }
    func append(_ line: RecordLine) throws {
        if failWrites { throw POSIXError(.EPERM) }
        lines.append(line)
    }
    func purgeOldFiles(now: Date) -> PurgeResult {
        purges += 1
        return purgeResult
    }
    func writeStatus(_ status: RecorderStatus) throws { statuses.append(status) }
    func log(_ level: LogLevel, _ message: String) { logs.append("\(level.rawValue) \(message)") }
}

/// 5秒ごとの1回分の流れ。設定を読み、記録するかを決め、開始・停止・除外中・通常の行を書き、状態のファイルを書き直す。
/// macOS に尋ねる部分を偽物に差し替えて、記録しない期間・除外中・題名を読む回のそれぞれで何が書かれるかを確かめる
@Suite("記録係の1回分の流れ")
struct RecorderLoopTests {
    let endsAt = jst("2026-10-07T18:00:00")

    func recordingConfig(apps: [ExcludedApp] = [], words: [String] = []) -> ConfigLoadResult {
        .loaded(RecorderConfig(version: 1, endsAt: endsAt, stoppedAt: nil, excludedApps: apps, excludedTitleWords: words))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-1、apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-1
    /// 否定確認: 開始の行を書かずに通常の行だけを書くと落ちる
    @Test("記録している期間の最初の回は、開始の行と、題名・シート名・部品の種類を入れた通常の行を書き、状態を記録中にする")
    func recordingTickWritesStartAndSample() {
        let env = FakeEnvironment(now: jst("2026-10-07T09:00:00"), config: recordingConfig())
        let loop = RecorderLoop(environment: env)
        loop.tick()
        #expect(env.lines.count == 2)
        #expect(env.lines.first == .start(time: jst("2026-10-07T09:00:00")))
        guard case .sample(_, let surroundings, let title) = env.lines.last else {
            Issue.record("通常の行が無い: \(env.lines)")
            return
        }
        #expect(surroundings.app == "Microsoft Excel")
        #expect(title.title == "見積_2026.xlsx")
        #expect(title.sheet == "集計")
        #expect(env.statuses.last?.recording == true)
        #expect(env.statuses.last?.accessibilityGranted == true)
        #expect(env.logs.contains("INFO recording started"))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-1
    @Test("2回目以降の回は開始の行を書かず、通常の行だけを書く")
    func secondTickWritesOnlySample() {
        let env = FakeEnvironment(now: jst("2026-10-07T09:00:00"), config: recordingConfig())
        let loop = RecorderLoop(environment: env)
        loop.tick()
        env.clock = jst("2026-10-07T09:00:05")
        loop.tick()
        #expect(env.lines.count == 3)
        if case .sample = env.lines.dropFirst(2).first {} else { Issue.record("3行目が通常の行でない: \(env.lines)") }
        #expect(env.lastLineReads == 1)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    /// 否定確認: 記録しない回にも通常の行を書くと落ちる
    @Test("記録しない期間の回は、最後の行が停止でなければ停止の行だけを書き、題名を読まず、状態を停止中にする")
    func notRecordingTickWritesOnlyStop() {
        let env = FakeEnvironment(now: jst("2026-10-08T09:00:00"), config: recordingConfig())
        env.initialLastLine = LastLine(time: jst("2026-10-07T17:30:00"), isStop: false)
        RecorderLoop(environment: env).tick()
        #expect(env.lines == [.stop(StopLine(time: endsAt, reason: .endsAtPassed))])
        #expect(env.windowReads == 0)
        #expect(env.statuses.last?.recording == false)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-2
    /// 否定確認: 記録しないアプリでも題名を読むと落ちる
    @Test("記録しないアプリが前面の回は、除外中の行だけを書き、題名を読まない")
    func excludedAppWritesExcludedWithoutReadingTitle() {
        let env = FakeEnvironment(now: jst("2026-10-07T09:00:00"),
                                  config: recordingConfig(apps: [ExcludedApp(name: "パスワード", bundleId: "com.apple.Passwords")]))
        env.app = FrontAppInfo(name: "Passwords", bundleId: "com.apple.Passwords")
        RecorderLoop(environment: env).tick()
        #expect(env.lines == [.start(time: jst("2026-10-07T09:00:00")), .excluded(time: jst("2026-10-07T09:00:00"))])
        #expect(env.windowReads == 0)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-3
    /// 否定確認: 記録しないことばを見ずに通常の行を書くと落ちる
    @Test("題名に記録しないことばが含まれる回は、除外中の行だけを書く")
    func excludedWordWritesExcluded() {
        let env = FakeEnvironment(now: jst("2026-10-07T09:00:00"), config: recordingConfig(words: ["見積"]))
        RecorderLoop(environment: env).tick()
        #expect(env.lines.last == .excluded(time: jst("2026-10-07T09:00:00")))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4、apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-6
    /// 否定確認: 理由が変わらない回にもログを書くと落ちる
    @Test("設定が読めない回は何も書かず、状態に理由を残し、理由のログは変わったときだけ書く")
    func unreadableConfigWritesNothing() {
        let env = FakeEnvironment(now: jst("2026-10-07T09:00:00"), config: .unreadable("invalidJson"))
        let loop = RecorderLoop(environment: env)
        loop.tick()
        env.clock = jst("2026-10-07T09:00:05")
        loop.tick()
        #expect(env.lines.isEmpty)
        #expect(env.statuses.last?.configError == "invalidJson")
        #expect(env.logs.filter { $0.contains("config unreadable") } == ["WARN config unreadable reason=invalidJson"])
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-4
    /// 否定確認: 取れなかった理由を毎回ログに書くと落ちる
    @Test("題名が取れなかった回は印と理由を付けた行を書き、理由のログは変わったときだけ書く")
    func unavailableTitleLogsOnChange() {
        let env = FakeEnvironment(now: jst("2026-10-07T09:00:00"), config: recordingConfig())
        env.window = .unavailable(.denied)
        let loop = RecorderLoop(environment: env)
        loop.tick()
        env.clock = jst("2026-10-07T09:00:05")
        loop.tick()
        env.clock = jst("2026-10-07T09:00:10")
        env.window = .unavailable(.timeout)
        loop.tick()
        guard case .sample(_, _, let title) = env.lines.last else {
            Issue.record("通常の行が無い")
            return
        }
        #expect(title.titleUnavailableReason == .timeout)
        #expect(env.logs.filter { $0.contains("title unavailable") }
                == ["WARN title unavailable reason=denied", "WARN title unavailable reason=timeout"])
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-1
    /// 否定確認: 書き込みに失敗したあとも直前の回に記録したとみなすと落ちる(次の回に開始の行を書き直さない)
    @Test("記録のファイルに書けなかった回は、ログと状態に最後のエラーを残し、次の回に開始の行から書き直す")
    func writeFailureIsReportedAndRetried() {
        let env = FakeEnvironment(now: jst("2026-10-07T09:00:00"), config: recordingConfig())
        env.failWrites = true
        let loop = RecorderLoop(environment: env)
        loop.tick()
        #expect(env.statuses.last?.lastWriteError != nil)
        #expect(env.logs.contains { $0.hasPrefix("ERROR write failed") })

        env.failWrites = false
        env.clock = jst("2026-10-07T09:00:05")
        loop.tick()
        #expect(env.lines.first == .start(time: jst("2026-10-07T09:00:05")))
        #expect(env.statuses.last?.lastWriteError == nil)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#古い記録の削除-1、apps/routine-work-finder/specs/activity-recording/requirements.md#古い記録の削除-2
    /// 否定確認: 同じ日の2回目にも消すと落ちる
    @Test("日付が変わって最初の回だけ古いファイルを消し、消した数をログに、消した日付を状態に残す(止めている間も)")
    func purgesOncePerDayEvenWhenStopped() {
        let env = FakeEnvironment(now: jst("2026-10-29T09:00:00"), config: .missing)
        env.purgeResult = PurgeResult(deletedCount: 3, failedPaths: [])
        let loop = RecorderLoop(environment: env)
        loop.tick()
        env.clock = jst("2026-10-29T09:00:05")
        loop.tick()
        env.clock = jst("2026-10-30T00:00:00")
        loop.tick()
        #expect(env.purges == 2)
        #expect(env.logs.filter { $0.hasPrefix("INFO purge") } == ["INFO purge removed=3", "INFO purge removed=3"])
        #expect(env.statuses.last?.lastPurgeDate == "2026-10-30")
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-8
    @Test("アクセシビリティの許可が無いことを状態に残す")
    func accessibilityNotGrantedIsInStatus() {
        let env = FakeEnvironment(now: jst("2026-10-07T09:00:00"), config: recordingConfig())
        env.granted = false
        RecorderLoop(environment: env).tick()
        #expect(env.statuses.last?.accessibilityGranted == false)
    }
}
