import Foundation

/// 前面のアプリが記録しないアプリに当たるか。一覧のアプリ名かバンドルIDのどちらかが一致したら当たる
public func isExcludedApp(name: String?, bundleId: String?, excludedApps: [ExcludedApp]) -> Bool {
    excludedApps.contains { excluded in
        if let name, excluded.name == name { return true }
        if let bundleId, let excludedBundleId = excluded.bundleId, excludedBundleId == bundleId { return true }
        return false
    }
}

/// 前面ウィンドウの題名に、記録しないことばのどれかが含まれるか(部分一致)
public func titleContainsExcludedWord(_ title: String, excludedTitleWords: [String]) -> Bool {
    excludedTitleWords.contains { !$0.isEmpty && title.contains($0) }
}
