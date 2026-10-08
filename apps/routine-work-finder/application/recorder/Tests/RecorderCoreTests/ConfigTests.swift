import Foundation
import Testing
@testable import RecorderCore

/// 記録係が設定ファイルを読む処理。形の違う設定を「読めない」として記録しない側に倒し、
/// 設定ファイルが無いことは「終わりの日時が無い」として区別する。
@Suite("記録係が設定ファイルを読む")
struct ConfigTests {
    let validJSON = """
    {"version":1,"endsAt":"2026-10-31T18:00:00+09:00","stoppedAt":null,
     "excludedApps":[{"name":"パスワード","bundleId":"com.apple.Passwords"},{"name":"家計簿","bundleId":null}],
     "excludedTitleWords":["給与"]}
    """

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    @Test("形の合った設定は、終わりの日時と記録しないアプリ・ことばを読み取れる")
    func readsValidConfig() {
        let result = parseConfig(Data(validJSON.utf8))
        guard case .loaded(let config) = result else {
            Issue.record("読めなかった: \(result)")
            return
        }
        #expect(config.endsAt == jst("2026-10-31T18:00:00"))
        #expect(config.stoppedAt == nil)
        #expect(config.excludedApps == [
            ExcludedApp(name: "パスワード", bundleId: "com.apple.Passwords"),
            ExcludedApp(name: "家計簿", bundleId: nil),
        ])
        #expect(config.excludedTitleWords == ["給与"])
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    /// 否定確認: stoppedAt を必須にすると落ちる
    @Test("止めた日時の項目が欠けていても読め、止めていないとみなす")
    func missingStoppedAtIsNull() {
        let json = #"{"version":1,"endsAt":null,"excludedApps":[],"excludedTitleWords":[]}"#
        #expect(parseConfig(Data(json.utf8)) == .loaded(RecorderConfig(
            version: 1, endsAt: nil, stoppedAt: nil, excludedApps: [], excludedTitleWords: [])))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    @Test("必須の項目が欠けていたら、欠けた項目名を理由にして読めないとする",
          arguments: ["version", "endsAt", "excludedApps", "excludedTitleWords"])
    func missingRequiredFieldIsUnreadable(field: String) throws {
        var object = try JSONSerialization.jsonObject(with: Data(validJSON.utf8)) as! [String: Any]
        object.removeValue(forKey: field)
        let data = try JSONSerialization.data(withJSONObject: object)
        #expect(parseConfig(data) == .unreadable("missingField:\(field)"))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    @Test("項目の型が違ったら、その項目名を理由にして読めないとする")
    func wrongTypeIsUnreadable() {
        let json = #"{"version":1,"endsAt":20261031,"excludedApps":[],"excludedTitleWords":[]}"#
        #expect(parseConfig(Data(json.utf8)) == .unreadable("invalidType:endsAt"))
        let badDate = #"{"version":1,"endsAt":"10月31日","excludedApps":[],"excludedTitleWords":[]}"#
        #expect(parseConfig(Data(badDate.utf8)) == .unreadable("invalidType:endsAt"))
        let badApp = #"{"version":1,"endsAt":null,"excludedApps":["パスワード"],"excludedTitleWords":[]}"#
        #expect(parseConfig(Data(badApp.utf8)) == .unreadable("invalidType:excludedApps"))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    @Test("JSON として壊れていたら読めないとする")
    func brokenJSONIsUnreadable() {
        #expect(parseConfig(Data(#"{"version":1,"endsAt":"#.utf8)) == .unreadable("invalidJson"))
        #expect(parseConfig(Data("[]".utf8)) == .unreadable("invalidJson"))
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    /// 否定確認: ファイルが無いときに unreadable を返すと落ちる
    @Test("設定ファイルが無いときは、読めないではなく「無い」として返す")
    func missingFileIsMissing() {
        let directory = temporaryDirectory()
        #expect(loadConfig(at: directory.appendingPathComponent("config.json")) == .missing)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-4
    @Test("設定ファイルがあれば中身を読み取る")
    func loadsExistingFile() throws {
        let url = temporaryDirectory().appendingPathComponent("config.json")
        try Data(validJSON.utf8).write(to: url)
        guard case .loaded = loadConfig(at: url) else {
            Issue.record("読めなかった")
            return
        }
    }
}
