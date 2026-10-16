import Foundation

/// 1つの属性の問い合わせ結果。`error` は AXError の値(0 が成功)、`value` は文字列で返ったときの値
public struct AxAttribute: Equatable, Sendable {
    public var error: Int32
    public var value: String?

    public init(error: Int32, value: String?) {
        self.error = error
        self.value = value
    }
}

/// 1回分のアクセシビリティの問い合わせ結果(記録係の AxReader が作る)。問い合わせなかった項目は nil
public struct AxRawResponse: Equatable, Sendable {
    public var trusted: Bool
    public var timedOut: Bool
    public var focusedWindowError: Int32
    public var title: AxAttribute?
    public var selectedSheet: AxAttribute?
    public var focusedElementError: Int32?
    public var role: AxAttribute?
    public var subrole: AxAttribute?

    public init(trusted: Bool, timedOut: Bool, focusedWindowError: Int32, title: AxAttribute?, selectedSheet: AxAttribute?,
                focusedElementError: Int32?, role: AxAttribute?, subrole: AxAttribute?) {
        self.trusted = trusted
        self.timedOut = timedOut
        self.focusedWindowError = focusedWindowError
        self.title = title
        self.selectedSheet = selectedSheet
        self.focusedElementError = focusedElementError
        self.role = role
        self.subrole = subrole
    }
}

/// AXError の値(ApplicationServices の定義と同じ)。RecorderCore は macOS の部品に依存させないため数で持つ
enum AxErrorCode {
    static let success: Int32 = 0
    static let cannotComplete: Int32 = -25204
    static let apiDisabled: Int32 = -25211
}

/// アクセシビリティの応答から、題名・シート名・部品の種類を取り出す。
/// 許可が無い・打ち切った・前面ウィンドウが取れないときは、取れなかった理由を返す(appendix.md「エラーの理由」)
public func parseAxResponse(_ raw: AxRawResponse) -> WindowReadResult {
    guard raw.trusted, raw.focusedWindowError != AxErrorCode.apiDisabled else {
        return .unavailable(.denied)
    }
    // 題名を読めたあとの問い合わせ(シート名・部品)で打ち切ったときは、読めた題名を返す(記録しないことばの判定に使う)
    let titleRead = raw.focusedWindowError == AxErrorCode.success && readValue(raw.title) != nil
    if (raw.timedOut && !titleRead) || raw.focusedWindowError == AxErrorCode.cannotComplete {
        return .unavailable(.timeout)
    }
    guard raw.focusedWindowError == AxErrorCode.success else {
        return .unavailable(.noWindow)
    }
    let role = raw.focusedElementError == AxErrorCode.success ? readValue(raw.role) : nil
    return .read(WindowInfo(
        title: readValue(raw.title) ?? "",
        sheet: readValue(raw.selectedSheet),
        focusRole: role,
        focusSubrole: role == nil ? nil : readValue(raw.subrole)
    ))
}

private func readValue(_ attribute: AxAttribute?) -> String? {
    guard let attribute, attribute.error == AxErrorCode.success else { return nil }
    return attribute.value
}
