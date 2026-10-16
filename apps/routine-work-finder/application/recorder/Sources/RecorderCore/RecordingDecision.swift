import Foundation

/// 停止の行の理由。appendix.md「操作の記録の行の形」の `reason`
public enum StopReason: String, Sendable {
    case endsAtPassed
    case stopRequested
    case endsAtMissing
}

/// この回に書く停止の行。`time` の日本時間の日付のファイルに書き足す
public struct StopLine: Equatable, Sendable {
    public let time: Date
    public let reason: StopReason

    public init(time: Date, reason: StopReason) {
        self.time = time
        self.reason = reason
    }
}

/// 5秒ごとの1回の判定結果
public struct TickDecision: Equatable, Sendable {
    /// この回に操作の記録の行を書くか
    public let recording: Bool
    /// 操作の記録の前に開始の行を書くか
    public let writeStart: Bool
    /// 書く停止の行。書かないときは nil
    public let stopLine: StopLine?
    /// 状態のファイルの `configError`。設定が読めた回・設定ファイルが無い回は nil
    public let configError: String?
}

/// 設定・今の時刻・最後の行・直前の回に記録したかから、この回に何を書くかを決める(design.md「5秒ごとに操作と題名を記録する」手順2〜4)
public func decideTick(config: ConfigLoadResult, now: Date, lastLine: LastLine, recordedPreviousTick: Bool) -> TickDecision {
    let endsAt: Date?
    let stoppedAt: Date?
    switch config {
    case .unreadable(let reason):
        // 設定が読めない回は停止の行を書かず、「記録していない回」として扱う
        return TickDecision(recording: false, writeStart: false, stopLine: nil, configError: reason)
    case .missing:
        endsAt = nil
        stoppedAt = nil
    case .loaded(let loaded):
        endsAt = loaded.endsAt
        stoppedAt = loaded.stoppedAt
    }

    if let endsAt, now < endsAt {
        return TickDecision(recording: true, writeStart: !recordedPreviousTick, stopLine: nil, configError: nil)
    }

    guard !lastLine.isStop else {
        return TickDecision(recording: false, writeStart: false, stopLine: nil, configError: nil)
    }
    let stopLine: StopLine
    if let endsAt {
        stopLine = StopLine(time: later(lastLine.time, endsAt), reason: .endsAtPassed)
    } else if let stoppedAt {
        stopLine = StopLine(time: later(lastLine.time, stoppedAt), reason: .stopRequested)
    } else {
        stopLine = StopLine(time: now, reason: .endsAtMissing)
    }
    return TickDecision(recording: false, writeStart: false, stopLine: stopLine, configError: nil)
}

private func later(_ lastLineTime: Date?, _ other: Date) -> Date {
    guard let lastLineTime else { return other }
    return max(lastLineTime, other)
}
