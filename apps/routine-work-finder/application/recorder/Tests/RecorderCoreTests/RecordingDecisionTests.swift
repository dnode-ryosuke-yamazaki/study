import Foundation
import Testing
@testable import RecorderCore

/// 記録係が5秒ごとの回に「記録するか」「開始・停止の行を書くか」を決める判定。
/// 終わりの日時を過ぎたら必ず止まり、記録している期間が停止の行で閉じることで、
/// 読む側が記録していた時間と止めていた時間を取り違えないようにする。
@Suite("記録を始める・止める判定")
struct RecordingDecisionTests {
    let endsAt = jst("2026-10-07T18:00:00")
    let recordingLine = LastLine(time: jst("2026-10-07T17:59:55"), isStop: false)

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    /// 否定確認: 終わりの日時との比較を逆向き(`now > endsAt`)にすると落ちる
    @Test("終わりの日時の1秒前は記録を続ける")
    func oneSecondBeforeEndsAtKeepsRecording() {
        let decision = decideTick(config: config(endsAt: endsAt), now: jst("2026-10-07T17:59:59"),
                                  lastLine: recordingLine, recordedPreviousTick: true)
        #expect(decision.recording)
        #expect(decision.stopLine == nil)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    /// 否定確認: 終わりの日時との比較を `now <= endsAt` にすると落ちる
    @Test("終わりの日時ちょうどで記録を止め、終わりの日時を過ぎた理由の停止の行を書く")
    func exactlyAtEndsAtStops() {
        let decision = decideTick(config: config(endsAt: endsAt), now: endsAt,
                                  lastLine: recordingLine, recordedPreviousTick: true)
        #expect(!decision.recording)
        #expect(decision.stopLine == StopLine(time: endsAt, reason: .endsAtPassed))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    @Test("終わりの日時の1秒後も記録しない")
    func oneSecondAfterEndsAtStops() {
        let decision = decideTick(config: config(endsAt: endsAt), now: jst("2026-10-07T18:00:01"),
                                  lastLine: recordingLine, recordedPreviousTick: true)
        #expect(!decision.recording)
        #expect(decision.stopLine?.reason == .endsAtPassed)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    /// 否定確認: 最後の行が停止かどうかを見ずに停止の行を書くと落ちる
    @Test("終わりの日時を過ぎたあと何回判定しても、停止の行は1回だけ書く")
    func stopLineIsWrittenOnlyOnce() {
        var lastLine = recordingLine
        var stopCount = 0
        for second in [0, 5, 10, 15] {
            let now = endsAt.addingTimeInterval(TimeInterval(second))
            let decision = decideTick(config: config(endsAt: endsAt), now: now,
                                      lastLine: lastLine, recordedPreviousTick: false)
            if decision.stopLine != nil { stopCount += 1 }
            lastLine = apply(decision, now: now, to: lastLine)
        }
        #expect(stopCount == 1)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    @Test("記録係が起動し直した最初の回に終わりの日時を過ぎていて、最後の行が停止でなければ停止の行を書く")
    func firstTickAfterRelaunchClosesRecordingPeriod() {
        let decision = decideTick(config: config(endsAt: endsAt), now: jst("2026-10-08T09:00:00"),
                                  lastLine: recordingLine, recordedPreviousTick: false)
        #expect(decision.stopLine?.reason == .endsAtPassed)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    @Test("設定が読めなかった回のあと、読めるようになった回が記録しない状態なら停止の行を書く")
    func firstReadableTickAfterUnreadableClosesRecordingPeriod() {
        let lineBeforeUnreadable = LastLine(time: jst("2026-10-07T16:59:55"), isStop: false)
        let unreadable = decideTick(config: .unreadable("invalidJson"), now: jst("2026-10-07T17:00:00"),
                                    lastLine: lineBeforeUnreadable, recordedPreviousTick: true)
        let lastLine = apply(unreadable, now: jst("2026-10-07T17:00:00"), to: lineBeforeUnreadable)
        let readable = decideTick(config: config(endsAt: nil, stoppedAt: jst("2026-10-07T17:10:00")),
                                  now: jst("2026-10-07T17:20:00"),
                                  lastLine: lastLine, recordedPreviousTick: unreadable.recording)
        #expect(readable.stopLine == StopLine(time: jst("2026-10-07T17:10:00"), reason: .stopRequested))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    @Test("最後の行がすでに停止の行なら、記録しない回でも停止の行を書かない")
    func noStopLineWhenAlreadyStopped() {
        let decision = decideTick(config: config(endsAt: endsAt), now: jst("2026-10-08T09:00:00"),
                                  lastLine: LastLine(time: endsAt, isStop: true), recordedPreviousTick: false)
        #expect(!decision.recording)
        #expect(decision.stopLine == nil)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4、apps/routine-work-finder/specs/activity-recording/requirements.md#日付と週の基準-1
    /// 否定確認: 停止の行の時刻をその回の時刻にすると落ちる
    @Test("水曜18時終了で水曜17時30分に閉じて木曜9時に開いた場合、停止の行は水曜18時で水曜のファイルに書く")
    func stopLineTimeIsEndsAtWhenMacWasClosed() {
        let decision = decideTick(config: config(endsAt: endsAt), now: jst("2026-10-08T09:00:00"),
                                  lastLine: LastLine(time: jst("2026-10-07T17:30:00"), isStop: false),
                                  recordedPreviousTick: false)
        #expect(decision.stopLine?.time == endsAt)
        #expect(decision.stopLine.map { JapanTime.dateString($0.time) } == "2026-10-07")
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    /// 否定確認: 遅い方ではなく常に終わりの日時を使うと落ちる
    @Test("最後の行が終わりの日時より後なら、停止の行は最後の行の時刻にする")
    func stopLineTimeIsLastLineWhenLater() {
        let last = jst("2026-10-07T18:00:03")
        let decision = decideTick(config: config(endsAt: endsAt), now: jst("2026-10-07T18:00:05"),
                                  lastLine: LastLine(time: last, isStop: false), recordedPreviousTick: true)
        #expect(decision.stopLine?.time == last)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    @Test("止める依頼で止めた場合、停止の行は止めた日時と最後の行の遅い方にする")
    func stopRequestedUsesLaterOfStoppedAtAndLastLine() {
        let stoppedAt = jst("2026-10-07T15:00:00")
        let earlierLine = decideTick(config: config(endsAt: nil, stoppedAt: stoppedAt), now: jst("2026-10-07T15:00:04"),
                                     lastLine: LastLine(time: jst("2026-10-07T14:59:58"), isStop: false),
                                     recordedPreviousTick: true)
        #expect(earlierLine.stopLine == StopLine(time: stoppedAt, reason: .stopRequested))

        let laterLineTime = jst("2026-10-07T15:00:02")
        let laterLine = decideTick(config: config(endsAt: nil, stoppedAt: stoppedAt), now: jst("2026-10-07T15:00:04"),
                                   lastLine: LastLine(time: laterLineTime, isStop: false), recordedPreviousTick: true)
        #expect(laterLine.stopLine == StopLine(time: laterLineTime, reason: .stopRequested))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    /// 否定確認: endsAtMissing の時刻を最後の行の時刻にすると落ちる
    @Test("終わりの日時も止めた日時も無い場合は、終わりの日時が無い理由で、その回の時刻の停止の行を書く")
    func bothNullStopsWithEndsAtMissingAtNow() {
        let now = jst("2026-10-07T12:00:00")
        let decision = decideTick(config: config(endsAt: nil, stoppedAt: nil), now: now,
                                  lastLine: LastLine(time: jst("2026-10-07T09:00:00"), isStop: false),
                                  recordedPreviousTick: false)
        #expect(decision.stopLine == StopLine(time: now, reason: .endsAtMissing))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    /// 否定確認: 直前の回を見ずに毎回開始の行を書くと落ちる
    @Test("記録している期間に入った最初の回だけ開始の行を書く")
    func startLineOnlyOnFirstRecordingTick() {
        let first = decideTick(config: config(endsAt: endsAt), now: jst("2026-10-07T09:00:00"),
                               lastLine: .assumedStop, recordedPreviousTick: false)
        let second = decideTick(config: config(endsAt: endsAt), now: jst("2026-10-07T09:00:05"),
                                lastLine: LastLine(time: jst("2026-10-07T09:00:00"), isStop: false),
                                recordedPreviousTick: first.recording)
        #expect(first.recording && first.writeStart)
        #expect(second.recording && !second.writeStart)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    /// 否定確認: 設定が読めない回に停止の行を書くと落ちる
    @Test("設定が読めない回は記録せず、停止の行も書かず、理由を状態に残す。読めるようになった回は開始の行を書く")
    func unreadableConfigWritesNothingThenStartsAgain() {
        let unreadable = decideTick(config: .unreadable("missingField:endsAt"), now: jst("2026-10-07T10:00:00"),
                                    lastLine: recordingLine, recordedPreviousTick: true)
        #expect(!unreadable.recording)
        #expect(unreadable.stopLine == nil)
        #expect(!unreadable.writeStart)
        #expect(unreadable.configError == "missingField:endsAt")

        let readable = decideTick(config: config(endsAt: endsAt), now: jst("2026-10-07T10:00:05"),
                                  lastLine: recordingLine, recordedPreviousTick: unreadable.recording)
        #expect(readable.recording && readable.writeStart)
        #expect(readable.configError == nil)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    /// 否定確認: 設定ファイルが無い場合を「設定が読めない」と同じ扱いにすると落ちる
    @Test("設定ファイルが無い回は、最後の行が停止でなければ終わりの日時が無い理由の停止の行を書き、読めないとは扱わない")
    func missingConfigStopsWithEndsAtMissing() {
        let now = jst("2026-10-07T10:00:00")
        let decision = decideTick(config: .missing, now: now, lastLine: recordingLine, recordedPreviousTick: true)
        #expect(!decision.recording)
        #expect(decision.stopLine == StopLine(time: now, reason: .endsAtMissing))
        #expect(decision.configError == nil)

        let alreadyStopped = decideTick(config: .missing, now: now,
                                        lastLine: LastLine(time: jst("2026-10-07T09:00:00"), isStop: true),
                                        recordedPreviousTick: false)
        #expect(alreadyStopped.stopLine == nil)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-5
    @Test("止める依頼で終わりの日時が消えると、終わりの日時より前でも記録を止める")
    func stopRequestStopsBeforeEndsAt() {
        let decision = decideTick(config: config(endsAt: nil, stoppedAt: jst("2026-10-07T11:00:00")),
                                  now: jst("2026-10-07T11:00:03"), lastLine: recordingLine, recordedPreviousTick: true)
        #expect(!decision.recording)
        #expect(decision.stopLine?.reason == .stopRequested)
    }
}
