import Foundation

/// 記録の行を `records/<日本時間の日付>.jsonl` に書き足す。フォルダは700、ファイルは600で作る
public struct DailyFileWriter {
    public let recordsDirectory: URL

    public init(recordsDirectory: URL) {
        self.recordsDirectory = recordsDirectory
    }

    public func append(_ line: RecordLine) throws {
        let fileManager = FileManager.default
        if !fileManager.fileExists(atPath: recordsDirectory.path) {
            try fileManager.createDirectory(at: recordsDirectory, withIntermediateDirectories: true,
                                            attributes: [.posixPermissions: 0o700])
        }
        let file = recordsDirectory.appendingPathComponent(JapanTime.dateString(line.time) + ".jsonl")
        // 無ければ600で作り、あれば末尾に書き足す。一時ファイルを経由しない
        let descriptor = open(file.path, O_RDWR | O_CREAT | O_APPEND, 0o600)
        guard descriptor >= 0 else {
            throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO)
        }
        let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
        // 前回の最終行が書きかけ(改行で終わらない)なら改行を補い、この行を独立した1行にする。書きかけの行は消さない
        let prefix = endsWithoutNewline(descriptor) ? "\n" : ""
        try handle.write(contentsOf: Data((prefix + line.jsonLine() + "\n").utf8))
        try handle.close()
    }

    private func endsWithoutNewline(_ descriptor: Int32) -> Bool {
        var status = stat()
        guard fstat(descriptor, &status) == 0, status.st_size > 0 else { return false }
        var last: UInt8 = 0
        guard pread(descriptor, &last, 1, status.st_size - 1) == 1 else { return false }
        return last != UInt8(ascii: "\n")
    }
}
