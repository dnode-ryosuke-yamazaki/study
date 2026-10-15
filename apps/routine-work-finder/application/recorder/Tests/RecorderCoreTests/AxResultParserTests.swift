import Foundation
import Testing
@testable import RecorderCore

/// アクセシビリティの応答から題名・シート名・部品の種類を取り出し、取れなかったときは理由を分ける処理。
/// 実機の応答(tests/fixtures/ax/。題名・シート名は置き換え済み)を入力にして、各アプリの形を読めることを確かめる。
@Suite("アクセシビリティの応答を読み取る")
struct AxResultParserTests {
    static let fixturesDirectory = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("tests/fixtures/ax")

    static func fixture(_ name: String) throws -> [AxRawResponse] {
        let data = try Data(contentsOf: fixturesDirectory.appendingPathComponent("\(name).json"))
        let items = try #require(JSONSerialization.jsonObject(with: data) as? [[String: Any]])
        return try items.map { try #require(AxRawResponse(fixture: $0)) }
    }

    func info(_ result: WindowReadResult) -> WindowInfo? {
        if case .read(let info) = result { return info }
        return nil
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-1、apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-2、apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-3
    /// 否定確認: 選択中タブの題名をシート名に入れないと落ちる
    @Test("Excel の応答から、題名・選択中のシート名・表の部品の種類を読み取る")
    func excel() throws {
        let read = try #require(info(parseAxResponse(Self.fixture("excel")[0])))
        #expect(read == WindowInfo(title: "TITLE", sheet: "SHEET", focusRole: "AXLayoutArea", focusSubrole: nil))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-3
    @Test("Chrome の応答から、Webページと入力欄の部品の種類を読み取る")
    func chrome() throws {
        let responses = try Self.fixture("chrome")
        #expect(info(parseAxResponse(responses[0]))?.focusRole == "AXTextField")
        #expect(info(parseAxResponse(responses[1]))?.focusRole == "AXWebArea")
        #expect(info(parseAxResponse(responses[1]))?.sheet == nil)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-3
    @Test("Outlook の応答から、メールの一覧と本文の部品の種類を読み取り、カーソルが無い瞬間は題名だけにする")
    func outlook() throws {
        let responses = try Self.fixture("outlook")
        #expect(info(parseAxResponse(responses[0]))?.focusRole == "AXTable")
        #expect(info(parseAxResponse(responses[1])) == WindowInfo(title: "TITLE", sheet: nil, focusRole: nil, focusSubrole: nil))
        #expect(info(parseAxResponse(responses[2]))?.focusRole == "AXWebArea")
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-3
    /// 否定確認: 部品が取れないとき(値が無い)を題名が取れないと扱うと落ちる
    @Test("VS Code・Teams の応答は部品の種類が無いので、題名だけを読み取る", arguments: ["vscode", "teams"])
    func electronAppsHaveTitleOnly(name: String) throws {
        let read = try #require(info(parseAxResponse(Self.fixture(name)[0])))
        #expect(read == WindowInfo(title: "TITLE", sheet: nil, focusRole: nil, focusSubrole: nil))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-1
    @Test("前面ウィンドウはあるが題名が読めないときは、空の題名として読み取る")
    func unreadableTitleIsEmpty() throws {
        var raw = try Self.fixture("vscode")[0]
        raw.title = AxAttribute(error: -25212, value: nil)
        #expect(info(parseAxResponse(raw))?.title == "")
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-4
    /// 否定確認: 前面ウィンドウの取得の失敗を見ずに題名を読むと落ちる
    @Test("前面ウィンドウが取れないときは、前面ウィンドウなしを理由にする")
    func noWindow() throws {
        var raw = try Self.fixture("vscode")[0]
        raw.focusedWindowError = -25212
        raw.title = nil
        #expect(parseAxResponse(raw) == .unavailable(.noWindow))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-4
    /// 否定確認: 許可の有無を最初に見ないと落ちる
    @Test("アクセシビリティの許可が無いときは、許可なしを理由にする")
    func denied() throws {
        var raw = try Self.fixture("excel")[0]
        raw.trusted = false
        #expect(parseAxResponse(raw) == .unavailable(.denied))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-4
    /// 否定確認: 打ち切りの印を見ないと落ちる
    @Test("題名を読む前に1秒で打ち切ったとき、または相手が応答しなかったときは、打ち切りを理由にする")
    func timeout() throws {
        var raw = try Self.fixture("chrome")[0]
        raw.timedOut = true
        raw.title = AxAttribute(error: -25204, value: nil)
        #expect(parseAxResponse(raw) == .unavailable(.timeout))

        var noResponse = try Self.fixture("chrome")[1]
        noResponse.focusedWindowError = -25204
        #expect(parseAxResponse(noResponse) == .unavailable(.timeout))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-4、apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-3
    /// 否定確認: 題名を読めたあとの打ち切りでも題名を捨てると、記録しないことばで判定できず落ちる
    @Test("題名を読めたあとのシート名・部品の問い合わせで打ち切ったときは、読めた題名を返し、読めなかった項目は空にする")
    func timeoutAfterTitleKeepsTitle() throws {
        var raw = try Self.fixture("excel")[0]
        raw.timedOut = true
        raw.selectedSheet = AxAttribute(error: -25204, value: nil)
        raw.focusedElementError = -25204
        #expect(parseAxResponse(raw) == .read(WindowInfo(title: "TITLE", sheet: nil, focusRole: nil, focusSubrole: nil)))
    }
}
