import ApplicationServices
import Foundation
import RecorderCore

/// アクセシビリティで前面ウィンドウの題名・Excel のシート名・カーソルのある部品の種類を尋ねる。
/// 読む属性は appendix.md「アクセシビリティの読み方」の8つだけ。前面ウィンドウの中を深く走査せず、
/// 部品の中の文字を返す属性は読まず、相手のアプリには何も書き込まない。問い合わせは合わせて1秒で打ち切る
enum AxReader {
    static let budget: TimeInterval = 1.0
    static let excelBundleId = "com.microsoft.Excel"
    static let maxChildrenToScan = 40

    static func isTrusted() -> Bool {
        AXIsProcessTrusted()
    }

    static func read(app: FrontApp) -> AxRawResponse {
        guard isTrusted() else {
            return AxRawResponse(trusted: false, timedOut: false, focusedWindowError: AXError.apiDisabled.rawValue,
                                 title: nil, selectedSheet: nil, focusedElementError: nil, role: nil, subrole: nil)
        }
        var session = Session(deadline: Date().addingTimeInterval(budget))
        let appElement = AXUIElementCreateApplication(app.processIdentifier)

        let window = session.copy(appElement, kAXFocusedWindowAttribute)
        var title: AxAttribute?
        var sheet: AxAttribute?
        if window.error == .success, let windowElement = element(window.value) {
            title = session.copyString(windowElement, kAXTitleAttribute)
            if app.bundleId == excelBundleId {
                sheet = selectedSheet(of: windowElement, session: &session)
            }
        }

        var role: AxAttribute?
        var subrole: AxAttribute?
        let focused = session.copy(appElement, kAXFocusedUIElementAttribute)
        if focused.error == .success, let focusedElement = element(focused.value) {
            role = session.copyString(focusedElement, kAXRoleAttribute)
            subrole = session.copyString(focusedElement, kAXSubroleAttribute)
        }

        return AxRawResponse(trusted: true, timedOut: session.timedOut, focusedWindowError: window.error.rawValue,
                             title: title, selectedSheet: sheet, focusedElementError: focused.error.rawValue,
                             role: role, subrole: subrole)
    }

    /// 前面ウィンドウの子を1段だけ見てタブ群を探し、選ばれているタブの題名を返す
    private static func selectedSheet(of window: AXUIElement, session: inout Session) -> AxAttribute? {
        let children = session.copy(window, kAXChildrenAttribute)
        guard children.error == .success, let items = children.value as? [AXUIElement] else { return nil }
        for child in items.prefix(maxChildrenToScan) {
            guard session.copyString(child, kAXRoleAttribute)?.value == kAXTabGroupRole else { continue }
            let tabs = session.copy(child, kAXTabsAttribute)
            guard tabs.error == .success, let tabItems = tabs.value as? [AXUIElement] else { return nil }
            for tab in tabItems where isSelected(session.copy(tab, kAXValueAttribute).value) {
                return session.copyString(tab, kAXTitleAttribute)
            }
            return nil
        }
        return nil
    }

    private static func isSelected(_ value: CFTypeRef?) -> Bool {
        (value as? Bool) ?? (value as? NSNumber)?.boolValue ?? false
    }

    private static func element(_ value: CFTypeRef?) -> AXUIElement? {
        guard let value, CFGetTypeID(value) == AXUIElementGetTypeID() else { return nil }
        return (value as! AXUIElement)
    }

    /// 1回分の問い合わせの残り時間を管理する。残り時間を各問い合わせの上限にし、使い切ったら以後は尋ねない
    private struct Session {
        let deadline: Date
        var timedOut = false

        mutating func copy(_ element: AXUIElement, _ attribute: String) -> (error: AXError, value: CFTypeRef?) {
            let remaining = deadline.timeIntervalSinceNow
            guard !timedOut, remaining > 0 else {
                timedOut = true
                return (.cannotComplete, nil)
            }
            AXUIElementSetMessagingTimeout(element, Float(remaining))
            var value: CFTypeRef?
            let error = AXUIElementCopyAttributeValue(element, attribute as CFString, &value)
            if error == .cannotComplete, deadline.timeIntervalSinceNow <= 0 {
                timedOut = true
            }
            return (error, value)
        }

        mutating func copyString(_ element: AXUIElement, _ attribute: String) -> AxAttribute? {
            let result = copy(element, attribute)
            if timedOut { return nil }
            return AxAttribute(error: result.error.rawValue, value: result.value as? String)
        }
    }
}
