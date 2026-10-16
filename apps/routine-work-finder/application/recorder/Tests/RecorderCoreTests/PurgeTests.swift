import Foundation
import Testing
@testable import RecorderCore

/// 4週間(28日)より古い記録・メモのファイルを消す処理。題名に入る業務の情報を手元に溜め続けないため、
/// 記録を止めている間も日付が変わるたびに古い分を消す。
@Suite("4週間より古い記録を消す")
struct PurgeTests {
    let now = jst("2026-10-29T09:00:00")

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#古い記録の削除-1、apps/routine-work-finder/specs/activity-recording/requirements.md#記録を残す場所と期間-2
    /// 否定確認: 28日前と比べる不等号を `<=` にすると落ちる
    @Test("今日から27日前・28日前のファイルは残し、29日前のファイルを消す対象にする")
    func selectsFilesOlderThan28Days() {
        let names = ["2026-10-02.jsonl", "2026-10-01.jsonl", "2026-09-30.jsonl"]
        #expect(selectFilesToPurge(names: names, now: now) == ["2026-09-30.jsonl"])
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#古い記録の削除-1
    /// 否定確認: 日付の形で絞らないと落ちる
    @Test("ファイル名が日付の形でないファイルは、古くても消す対象にしない")
    func ignoresNonDateFiles() {
        let names = ["2026-01-01.jsonl.bak", "notes.jsonl", "2026-1-1.jsonl", "2026-01-01.json", "2026-01-01.jsonl"]
        #expect(selectFilesToPurge(names: names, now: now) == ["2026-01-01.jsonl"])
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#日付と週の基準-1
    /// 否定確認: 28日の数え方を UTC の日付にすると落ちる
    @Test("28日は日本時間の日付で数える(日本時間の朝8時台は UTC ではまだ前日)")
    func countsDaysInJapanTime() {
        let earlyMorning = jst("2026-10-29T08:30:00")
        #expect(selectFilesToPurge(names: ["2026-10-01.jsonl", "2026-09-30.jsonl"], now: earlyMorning) == ["2026-09-30.jsonl"])
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#古い記録の削除-2
    /// 否定確認: 前回消した日付と比べずに毎回消す判定にすると落ちる
    @Test("前回消した日付と今日の日付が違う回(起動した最初の回を含む)だけ、消す判定になる")
    func purgesOnlyOnFirstTickOfDay() {
        #expect(shouldPurge(now: now, lastPurgeDate: nil))
        #expect(shouldPurge(now: now, lastPurgeDate: "2026-10-28"))
        #expect(!shouldPurge(now: now, lastPurgeDate: "2026-10-29"))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#古い記録の削除-2
    @Test("記録を止めている日でも、日付が変わった最初の回に古い記録とメモのファイルを消し、新しい分は残す")
    func purgesRecordsAndMemosWhileStopped() throws {
        let data = temporaryDirectory()
        let records = data.appendingPathComponent("records")
        let memos = data.appendingPathComponent("memos")
        for directory in [records, memos] {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            for name in ["2026-09-30.jsonl", "2026-10-01.jsonl", "keep.txt"] {
                try "x".write(to: directory.appendingPathComponent(name), atomically: false, encoding: .utf8)
            }
        }
        let stopped = decideTick(config: .loaded(RecorderConfig(version: 1, endsAt: nil, stoppedAt: nil, excludedApps: [], excludedTitleWords: [])),
                                 now: now, lastLine: .assumedStop, recordedPreviousTick: false)
        #expect(!stopped.recording)
        #expect(shouldPurge(now: now, lastPurgeDate: "2026-10-28"))

        let result = purgeOldFiles(directories: [records, memos], now: now)
        #expect(result.deletedCount == 2)
        #expect(result.failedPaths.isEmpty)
        for directory in [records, memos] {
            let remaining = try FileManager.default.contentsOfDirectory(atPath: directory.path).sorted()
            #expect(remaining == ["2026-10-01.jsonl", "keep.txt"])
        }
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#古い記録の削除-1
    @Test("フォルダがまだ無いときは、何も消さずに終わる")
    func missingDirectoryIsFine() {
        let result = purgeOldFiles(directories: [temporaryDirectory().appendingPathComponent("memos")], now: now)
        #expect(result.deletedCount == 0)
        #expect(result.failedPaths.isEmpty)
    }
}
