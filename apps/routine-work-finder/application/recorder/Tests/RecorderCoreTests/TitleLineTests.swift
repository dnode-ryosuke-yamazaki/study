import Testing
@testable import RecorderCore

/// アクセシビリティで読んだ題名・シート名・部品の種類を、記録の行に入れる形に整える処理。
/// 題名の大きさに上限を設けて記録のファイルが膨らみすぎないようにし、取れたものだけを行に入れる。
@Suite("題名・シート名・部品の種類を行の形に整える")
struct TitleLineTests {
    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-5
    /// 否定確認: 上限との比較を `>=` にすると落ちる
    @Test("題名が999字・1,000字なら切り詰めず、印も付けない", arguments: [999, 1_000])
    func titleUpToLimitIsKept(length: Int) {
        let title = String(repeating: "あ", count: length)
        let fields = makeTitleFields(.read(WindowInfo(title: title, sheet: nil, focusRole: nil, focusSubrole: nil)))
        #expect(fields.title == title)
        #expect(!fields.titleTruncated)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-5
    /// 否定確認: 切り詰める長さを999字にすると落ちる
    @Test("題名が1,001字なら先頭の1,000字に切り詰め、切り詰めた印を付ける")
    func titleOverLimitIsTruncated() {
        let title = String(repeating: "あ", count: 1_000) + "い"
        let fields = makeTitleFields(.read(WindowInfo(title: title, sheet: nil, focusRole: nil, focusSubrole: nil)))
        #expect(fields.title == String(repeating: "あ", count: 1_000))
        #expect(fields.titleTruncated)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-1
    @Test("題名だけが取れたときは、題名だけを行に入れ、シート名・部品の種類は入れない")
    func titleOnly() {
        let fields = makeTitleFields(.read(WindowInfo(title: "main.swift — study", sheet: nil, focusRole: nil, focusSubrole: nil)))
        #expect(fields == TitleFields(title: "main.swift — study", titleTruncated: false, sheet: nil,
                                      focusRole: nil, focusSubrole: nil, titleUnavailableReason: nil))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-2
    /// 否定確認: シート名を行に入れないと落ちる
    @Test("Excel のシート名が取れたときは、題名と並べて行に入れる")
    func withSheet() {
        let fields = makeTitleFields(.read(WindowInfo(title: "見積_2026.xlsx", sheet: "集計", focusRole: "AXLayoutArea", focusSubrole: nil)))
        #expect(fields.sheet == "集計")
        #expect(fields.focusRole == "AXLayoutArea")
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-2
    /// 否定確認: 空のシート名をそのまま行に入れると落ちる
    @Test("シート名が空の文字のときは、取れなかったものとして行に入れない")
    func emptySheetIsOmitted() {
        let fields = makeTitleFields(.read(WindowInfo(title: "見積_2026.xlsx", sheet: "", focusRole: nil, focusSubrole: nil)))
        #expect(fields.sheet == nil)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-3
    /// 否定確認: subrole を行に入れないと落ちる
    @Test("部品の種類は role と、あれば subrole を行に入れる")
    func withRoleAndSubrole() {
        let fields = makeTitleFields(.read(WindowInfo(title: "検索", sheet: nil, focusRole: "AXTextField", focusSubrole: "AXSearchField")))
        #expect(fields.focusRole == "AXTextField")
        #expect(fields.focusSubrole == "AXSearchField")
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-3
    @Test("部品の種類が取れなかったアプリ(VS Code・Teams など)は、題名だけを行に入れる")
    func roleUnavailableKeepsTitle() {
        let fields = makeTitleFields(.read(WindowInfo(title: "チャット | Microsoft Teams", sheet: nil, focusRole: nil, focusSubrole: nil)))
        #expect(fields.title == "チャット | Microsoft Teams")
        #expect(fields.focusRole == nil)
        #expect(fields.titleUnavailableReason == nil)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-4
    /// 否定確認: 取れなかった理由を行に入れないと落ちる
    @Test("題名が取れなかったときは、題名・シート名・部品の種類を入れず、取れなかった理由だけを入れる",
          arguments: [TitleUnavailableReason.noWindow, .denied, .timeout])
    func unavailableCarriesReason(reason: TitleUnavailableReason) {
        let fields = makeTitleFields(.unavailable(reason))
        #expect(fields == TitleFields(title: nil, titleTruncated: false, sheet: nil,
                                      focusRole: nil, focusSubrole: nil, titleUnavailableReason: reason))
    }
}
