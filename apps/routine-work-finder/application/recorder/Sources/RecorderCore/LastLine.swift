import Foundation

/// 記録のファイルの最後の行の時刻と、それが停止の行かどうか。記録係が覚えておき、停止の行を書くかを決める
public struct LastLine: Equatable, Sendable {
    public let time: Date?
    public let isStop: Bool

    public init(time: Date?, isStop: Bool) {
        self.time = time
        self.isStop = isStop
    }

    /// 記録のファイルが無い・読める行が無いときは、停止の行とみなす
    public static let assumedStop = LastLine(time: nil, isStop: true)
}

/// 記録のファイルの中身から、最後に読める行を取り出す。書きかけ(JSON として読めない)の行は飛ばす。
/// 行は LF だけで分ける(題名の中の U+2028 などで行を割らない)
public func parseLastLine(_ contents: String) -> LastLine {
    for line in contents.split(separator: "\n").reversed() {
        guard let object = (try? JSONSerialization.jsonObject(with: Data(line.utf8))) as? [String: Any],
              let timestamp = object["t"] as? String,
              let time = JapanTime.parseTimestamp(timestamp),
              let kind = object["kind"] as? String
        else {
            continue
        }
        return LastLine(time: time, isStop: kind == "stop")
    }
    return .assumedStop
}

/// 記録のファイル名(日本時間の日付)。削除・読み取りの対象はこの形のファイルだけ
public let recordFileNamePattern = #"^\d{4}-\d{2}-\d{2}\.jsonl$"#

/// いちばん新しい日付の記録のファイルの、最後に読める行を読む。起動した最初の回の初期値に使う
public func readLastLine(recordsDirectory: URL) -> LastLine {
    let names = (try? FileManager.default.contentsOfDirectory(atPath: recordsDirectory.path)) ?? []
    guard let newest = names.filter({ $0.range(of: recordFileNamePattern, options: .regularExpression) != nil }).max(),
          let data = try? Data(contentsOf: recordsDirectory.appendingPathComponent(newest))
    else {
        return .assumedStop
    }
    // 日本語の途中で途切れた最終行があっても前の行を読めるよう、文字に直せないバイトは置き換えて読む(その行は JSON として読めず飛ばされる)
    return parseLastLine(String(decoding: data, as: UTF8.self))
}
