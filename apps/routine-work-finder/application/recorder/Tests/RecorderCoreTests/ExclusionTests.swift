import Testing
@testable import RecorderCore

/// 記録しないアプリ・ことばの判定。パスワード管理などのアプリや、給与・人事などのことばを含む画面を
/// 記録に残さないための守り。当たった回は時刻と「除外中」の印だけの行になる。
@Suite("記録しないアプリ・ことばに当たるかの判定")
struct ExclusionTests {
    let excludedApps = [
        ExcludedApp(name: "パスワード", bundleId: "com.apple.Passwords"),
        ExcludedApp(name: "家計簿", bundleId: nil),
    ]

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-2
    /// 否定確認: アプリ名の比較を外すと落ちる
    @Test("アプリ名が一覧と一致したら、バンドルIDが違っても記録しないアプリに当たる")
    func matchesByName() {
        #expect(isExcludedApp(name: "家計簿", bundleId: "com.example.kakeibo", excludedApps: excludedApps))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-2
    /// 否定確認: バンドルIDの比較を外すと落ちる
    @Test("バンドルIDが一覧と一致したら、表示名が違っても記録しないアプリに当たる")
    func matchesByBundleId() {
        #expect(isExcludedApp(name: "Passwords", bundleId: "com.apple.Passwords", excludedApps: excludedApps))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#操作の記録-2
    /// 否定確認: バンドルIDが分からないもの同士(nil と nil)を一致とみなすと落ちる
    @Test("アプリ名もバンドルIDも一致しなければ当たらない。バンドルIDが分からないもの同士は一致とみなさない")
    func doesNotMatchOtherApps() {
        #expect(!isExcludedApp(name: "Microsoft Excel", bundleId: "com.microsoft.Excel", excludedApps: excludedApps))
        #expect(!isExcludedApp(name: "名前の無いアプリ", bundleId: nil, excludedApps: excludedApps))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-3、apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-4
    /// 否定確認: 部分一致ではなく先頭一致(hasPrefix)で判定すると落ちる
    @Test("題名の先頭・途中・末尾のどこにことばがあっても当たる",
          arguments: ["給与明細_2026年9月.pdf", "2026年9月_給与明細.pdf", "2026年9月分 給与"])
    func matchesWordAnywhereInTitle(title: String) {
        #expect(titleContainsExcludedWord(title, excludedTitleWords: ["給与", "人事"]))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-4
    @Test("題名にどのことばも含まれなければ当たらない")
    func doesNotMatchWithoutWord() {
        #expect(!titleContainsExcludedWord("見積_2026.xlsx", excludedTitleWords: ["給与", "人事"]))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないアプリ・ことばの一覧-2
    /// 否定確認: 空のことばを除かずに判定すると落ちる(空文字はどの題名にも含まれるとみなされうる)
    @Test("ことばの一覧が空なら、どの題名も当たらない。空のことばが混ざっていても全部に当たることはない")
    func emptyWordsMatchNothing() {
        #expect(!titleContainsExcludedWord("見積_2026.xlsx", excludedTitleWords: []))
        #expect(!titleContainsExcludedWord("見積_2026.xlsx", excludedTitleWords: [""]))
    }
}
