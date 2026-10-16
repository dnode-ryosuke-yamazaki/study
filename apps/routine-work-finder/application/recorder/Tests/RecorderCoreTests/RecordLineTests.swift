import Foundation
import Testing
@testable import RecorderCore

/// 記録係が書く1行の形。週次レポートと状態の確認がこの形を読むため、形は記録係の中でここ1か所で決める。
/// 記録しないアプリ・ことばに当たった回は、アプリ名も題名も行に残さない。
@Suite("記録の行の形")
struct RecordLineTests {
    let time = jst("2026-10-06T10:15:05")
    let surroundings = Surroundings(app: "Microsoft Excel", bundleId: "com.microsoft.Excel", monitor: 2,
                                    idleSec: 1.4, locked: false, mic: false, displaySleepPrevented: false)

    func object(_ line: RecordLine) throws -> [String: Any] {
        let text = line.jsonLine()
        #expect(!text.contains("\n"))
        return try #require(JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any])
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-1、apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-1
    @Test("通常の行は、時刻(日本時間)・アプリ・周りの状態と、取れた題名・シート名・部品の種類を1行の JSON にする")
    func sampleLine() throws {
        let fields = makeTitleFields(.read(WindowInfo(title: "見積_2026.xlsx", sheet: "集計", focusRole: "AXLayoutArea", focusSubrole: nil)))
        let line = RecordLine.sample(time: time, surroundings: surroundings, title: fields)
        #expect(line.jsonLine() == #"{"t":"2026-10-06T10:15:05+09:00","kind":"sample","app":"Microsoft Excel","bundleId":"com.microsoft.Excel","monitor":2,"idleSec":1.4,"locked":false,"mic":false,"displaySleepPrevented":false,"title":"見積_2026.xlsx","sheet":"集計","focusRole":"AXLayoutArea"}"#)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-2、apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-3
    /// 否定確認: 除外中の行にアプリ名を足すと落ちる
    @Test("除外中の行は、時刻と除外中の印だけで、アプリ名も題名も入れない")
    func excludedLineHasOnlyTimeAndKind() throws {
        let fields = try object(.excluded(time: time))
        #expect(Set(fields.keys) == ["t", "kind"])
        #expect(fields["kind"] as? String == "excluded")
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-4
    /// 否定確認: 取れなかった行に title を書くと落ちる
    @Test("題名が取れなかった行は、題名を書かず、取れなかった印と理由を持つ")
    func unavailableTitleLine() throws {
        let line = RecordLine.sample(time: time, surroundings: surroundings, title: makeTitleFields(.unavailable(.timeout)))
        let fields = try object(line)
        #expect(fields["title"] == nil)
        #expect(fields["titleUnavailable"] as? Bool == true)
        #expect(fields["titleReason"] as? String == "timeout")
        #expect(fields["app"] as? String == "Microsoft Excel")
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-5、apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-3
    /// 否定確認: 切り詰めた印を書き出さないと落ちる
    @Test("切り詰めた題名には印を付け、subrole があれば部品の種類と並べて書く")
    func truncatedTitleAndSubrole() throws {
        let long = String(repeating: "あ", count: 1_001)
        let line = RecordLine.sample(time: time, surroundings: surroundings,
                                     title: makeTitleFields(.read(WindowInfo(title: long, sheet: nil, focusRole: "AXTextField", focusSubrole: "AXSearchField"))))
        let fields = try object(line)
        #expect(fields["titleTruncated"] as? Bool == true)
        #expect(fields["focusSubrole"] as? String == "AXSearchField")
        #expect(fields["sheet"] == nil)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-1
    @Test("周りの状態が取れなかった項目は null にする")
    func unavailableSurroundingsAreNull() throws {
        let empty = Surroundings(app: "Finder", bundleId: nil, monitor: nil, idleSec: nil, locked: nil, mic: nil, displaySleepPrevented: nil)
        let fields = try object(.sample(time: time, surroundings: empty, title: makeTitleFields(.unavailable(.noWindow))))
        for key in ["bundleId", "monitor", "idleSec", "locked", "mic", "displaySleepPrevented"] {
            #expect(fields[key] is NSNull, "\(key)")
        }
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    @Test("開始の行と停止の行は、時刻と種類(停止は理由も)だけを持つ")
    func startAndStopLines() {
        #expect(RecordLine.start(time: time).jsonLine() == #"{"t":"2026-10-06T10:15:05+09:00","kind":"start"}"#)
        #expect(RecordLine.stop(StopLine(time: time, reason: .endsAtPassed)).jsonLine()
                == #"{"t":"2026-10-06T10:15:05+09:00","kind":"stop","reason":"endsAtPassed"}"#)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-1
    @Test("入力からの秒数は小数第1位までにする")
    func idleSecondsAreRounded() throws {
        let rough = Surroundings(app: "Code", bundleId: "com.microsoft.VSCode", monitor: 1, idleSec: 12.3456,
                                 locked: false, mic: false, displaySleepPrevented: false)
        let fields = try object(.sample(time: time, surroundings: rough, title: makeTitleFields(.unavailable(.denied))))
        #expect(fields["idleSec"] as? Double == 12.3)
    }
}
