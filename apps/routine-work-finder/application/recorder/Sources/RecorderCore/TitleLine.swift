import Foundation

/// 題名が取れなかった理由。行の `titleReason` に入れる(appendix.md「エラーの理由」)
public enum TitleUnavailableReason: String, Sendable, CaseIterable {
    case noWindow
    case denied
    case timeout
}

/// アクセシビリティで読めた前面ウィンドウの題名・Excel のシート名・カーソルのある部品の種類。読めなかった項目は nil
public struct WindowInfo: Equatable, Sendable {
    public let title: String?
    public let sheet: String?
    public let focusRole: String?
    public let focusSubrole: String?

    public init(title: String?, sheet: String?, focusRole: String?, focusSubrole: String?) {
        self.title = title
        self.sheet = sheet
        self.focusRole = focusRole
        self.focusSubrole = focusSubrole
    }
}

public enum WindowReadResult: Equatable, Sendable {
    case read(WindowInfo)
    case unavailable(TitleUnavailableReason)
}

/// 記録の行に入れる題名まわりの項目(appendix.md「操作の記録の行の形」の title・titleTruncated・sheet・focusRole・focusSubrole・titleReason)
public struct TitleFields: Equatable, Sendable {
    public let title: String?
    public let titleTruncated: Bool
    public let sheet: String?
    public let focusRole: String?
    public let focusSubrole: String?
    public let titleUnavailableReason: TitleUnavailableReason?
}

/// 1つの題名に残す最大の字数(requirements.md#ウィンドウの題名の記録-5)
public let titleCharacterLimit = 1_000

/// 読み取り結果を行に入れる形に整える。題名は上限で切り詰め、シート名・部品の種類は取れたときだけ入れる
public func makeTitleFields(_ result: WindowReadResult) -> TitleFields {
    switch result {
    case .unavailable(let reason):
        return TitleFields(title: nil, titleTruncated: false, sheet: nil,
                           focusRole: nil, focusSubrole: nil, titleUnavailableReason: reason)
    case .read(let info):
        let title = info.title.map { String($0.prefix(titleCharacterLimit)) }
        let truncated = (info.title?.count ?? 0) > titleCharacterLimit
        return TitleFields(title: title, titleTruncated: truncated, sheet: nonEmpty(info.sheet),
                           focusRole: nonEmpty(info.focusRole), focusSubrole: nonEmpty(info.focusSubrole),
                           titleUnavailableReason: nil)
    }
}

private func nonEmpty(_ text: String?) -> String? {
    guard let text, !text.isEmpty else { return nil }
    return text
}
