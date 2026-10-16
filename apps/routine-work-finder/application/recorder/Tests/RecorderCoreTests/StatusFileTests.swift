import Foundation
import Testing
@testable import RecorderCore

/// 記録係が5秒ごとに書き直す状態のファイル。状態の確認(操作スクリプト)が読むため、
/// 書きかけを読まれないよう一時ファイルに書いてから名前を付け替える
@Suite("状態のファイル")
struct StatusFileTests {
    let status = RecorderStatus(updatedAt: jst("2026-10-06T10:15:05"), recording: true, tickMillis: 42, configError: nil,
                                lastWriteError: nil, accessibilityGranted: true, lastPurgeDate: "2026-10-06")

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-6
    @Test("状態のファイルの形は、更新日時(日本時間)・記録中か・所要ミリ秒・設定の読めなかった理由・最後の書き込みエラー・許可・最後に消した日付")
    func jsonShape() {
        #expect(status.json() == #"{"version":1,"updatedAt":"2026-10-06T10:15:05+09:00","recording":true,"tickMillis":42,"configError":null,"lastWriteError":null,"accessibilityGranted":true,"lastPurgeDate":"2026-10-06"}"#)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-6
    /// 否定確認: 一時ファイルを残したまま名前を付け替えないと落ちる
    @Test("一時ファイルに書いてから名前を付け替え、600で置き、一時ファイルは残さない")
    func writesViaTemporaryFile() throws {
        let directory = temporaryDirectory()
        let url = directory.appendingPathComponent("recorder-status.json")
        try writeStatusFile(status, to: url)
        try writeStatusFile(status, to: url)
        #expect(try String(contentsOf: url, encoding: .utf8) == status.json() + "\n")
        let permissions = try FileManager.default.attributesOfItem(atPath: url.path)[.posixPermissions] as? NSNumber
        #expect(permissions?.intValue == 0o600)
        #expect(try FileManager.default.contentsOfDirectory(atPath: directory.path) == ["recorder-status.json"])
    }
}
