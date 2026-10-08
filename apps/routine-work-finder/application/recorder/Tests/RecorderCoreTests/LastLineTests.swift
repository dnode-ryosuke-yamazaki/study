import Foundation
import Testing
@testable import RecorderCore

/// 記録係が起動した最初の回に、前回までの記録の最後の行を読む処理。
/// ここで最後の行が停止でないと分かれば、止まっている状態の最初の回に停止の行を書いて期間を閉じられる。
@Suite("起動したときに前回の記録の最後の行を読む")
struct LastLineTests {
    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    @Test("最後の行の時刻と、停止の行かどうかを読み取る")
    func readsLastLine() {
        let contents = """
        {"t":"2026-10-07T09:00:00+09:00","kind":"start"}
        {"t":"2026-10-07T09:00:05+09:00","kind":"sample","app":"Code"}

        """
        #expect(parseLastLine(contents) == LastLine(time: jst("2026-10-07T09:00:05"), isStop: false))
        let stopped = contents + #"{"t":"2026-10-07T18:00:00+09:00","kind":"stop","reason":"endsAtPassed"}"# + "\n"
        #expect(parseLastLine(stopped) == LastLine(time: jst("2026-10-07T18:00:00"), isStop: true))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    /// 否定確認: 最終行だけを見て、読めなければ停止とみなすと落ちる
    @Test("最終行が書きかけなら飛ばして1つ前の行を使う")
    func skipsPartialLastLine() {
        let contents = """
        {"t":"2026-10-07T09:00:00+09:00","kind":"start"}
        {"t":"2026-10-07T09:00:05+09:00","kind":"sample"}
        {"t":"2026-10-07T09:00:10+09:00","ki
        """
        #expect(parseLastLine(contents) == LastLine(time: jst("2026-10-07T09:00:05"), isStop: false))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    @Test("読める行が1つも無ければ停止の行とみなす")
    func noReadableLineIsStop() {
        #expect(parseLastLine("") == .assumedStop)
        #expect(parseLastLine("{\"t\":\"2026-10\n") == .assumedStop)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    @Test("記録のファイルが無ければ停止の行とみなす")
    func noRecordFileIsStop() {
        let directory = temporaryDirectory()
        #expect(readLastLine(recordsDirectory: directory) == .assumedStop)
        #expect(readLastLine(recordsDirectory: directory.appendingPathComponent("records")) == .assumedStop)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    /// 否定確認: いちばん古い日付のファイルを選ぶ、または日付の形のファイルに絞らないと落ちる
    @Test("いちばん新しい日付の記録のファイルを読み、日付の形でないファイルは見ない")
    func readsNewestDatedFile() throws {
        let directory = temporaryDirectory()
        try #"{"t":"2026-10-06T18:00:00+09:00","kind":"stop","reason":"endsAtPassed"}"#
            .write(to: directory.appendingPathComponent("2026-10-06.jsonl"), atomically: false, encoding: .utf8)
        try #"{"t":"2026-10-07T09:00:05+09:00","kind":"sample"}"#
            .write(to: directory.appendingPathComponent("2026-10-07.jsonl"), atomically: false, encoding: .utf8)
        try #"{"t":"2026-10-09T09:00:00+09:00","kind":"stop","reason":"endsAtPassed"}"#
            .write(to: directory.appendingPathComponent("2026-10-09.jsonl.bak"), atomically: false, encoding: .utf8)
        #expect(readLastLine(recordsDirectory: directory) == LastLine(time: jst("2026-10-07T09:00:05"), isStop: false))
    }
}
