import Foundation
import Testing
@testable import RecorderCore

/// 操作スクリプト(Python)が書いた設定ファイルを、記録係が読めることの契約。
/// fixture は操作スクリプトのテスト(tests/test_config_store.py)が書き出したもので、両者の形がずれると落ちる
@Suite("操作スクリプトが書いた設定ファイルを記録係が読む")
struct ConfigContractTests {
    static let fixtureURL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().appendingPathComponent("Fixtures/config.json")

    func fixtureObject() throws -> [String: Any] {
        try #require(JSONSerialization.jsonObject(with: Data(contentsOf: Self.fixtureURL)) as? [String: Any])
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-1
    @Test("操作スクリプトが書いた設定ファイルから、終わりの日時と記録しないアプリを読める")
    func readsFixture() throws {
        let result = parseConfig(try Data(contentsOf: Self.fixtureURL))
        guard case .loaded(let config) = result else {
            Issue.record("読めなかった: \(result)")
            return
        }
        #expect(config.endsAt == jst("2026-10-31T18:00:00"))
        #expect(config.excludedApps.map(\.bundleId) == ["com.apple.Passwords", "com.apple.keychainaccess", "com.apple.systempreferences"])
        #expect(config.excludedTitleWords.isEmpty)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-1
    @Test("止めた日時の項目が欠けた設定ファイルも読める")
    func readsWithoutStoppedAt() throws {
        var object = try fixtureObject()
        object.removeValue(forKey: "stoppedAt")
        guard case .loaded(let config) = parseConfig(try JSONSerialization.data(withJSONObject: object)) else {
            Issue.record("読めなかった")
            return
        }
        #expect(config.stoppedAt == nil)
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-1
    @Test("必須の項目の欠け・型違い・壊れた JSON は、記録しない側に倒れる(操作スクリプトと同じ理由を返す)")
    func failureFormsAreUnreadable() throws {
        var missing = try fixtureObject()
        missing.removeValue(forKey: "excludedTitleWords")
        var wrongType = try fixtureObject()
        wrongType["endsAt"] = 20261031
        let broken = Data(String(decoding: try Data(contentsOf: Self.fixtureURL), as: UTF8.self).dropLast(10).utf8)

        let cases: [(Data, String)] = [
            (try JSONSerialization.data(withJSONObject: missing), "missingField:excludedTitleWords"),
            (try JSONSerialization.data(withJSONObject: wrongType), "invalidType:endsAt"),
            (broken, "invalidJson"),
        ]
        for (data, reason) in cases {
            let result = parseConfig(data)
            #expect(result == .unreadable(reason))
            let decision = decideTick(config: result, now: jst("2026-10-07T09:00:00"), lastLine: .assumedStop, recordedPreviousTick: false)
            #expect(!decision.recording)
            #expect(decision.configError == reason)
        }
    }

    // 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録の始め方・止め方-1
    /// 否定確認: version の真偽値を数として受け入れると落ちる(操作スクリプトは読めないと判定する)
    @Test("version が真偽値のときは、操作スクリプトと同じく型違いとして読めないとする")
    func boolVersionIsUnreadable() throws {
        var object = try fixtureObject()
        object["version"] = true
        #expect(parseConfig(try JSONSerialization.data(withJSONObject: object)) == .unreadable("invalidType:version"))
    }
}
