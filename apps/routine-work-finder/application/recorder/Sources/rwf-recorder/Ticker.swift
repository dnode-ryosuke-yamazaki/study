import Foundation
import RecorderCore

/// メインのランループで5秒ごとに1回分の記録を回す。起動した直後に1回目を回す
final class Ticker {
    static let interval: TimeInterval = 5

    private let loop: RecorderLoop
    private var timer: Timer?

    init(loop: RecorderLoop) {
        self.loop = loop
    }

    func start() {
        loop.tick()
        let timer = Timer(timeInterval: Self.interval, repeats: true) { [loop] _ in
            loop.tick()
        }
        timer.tolerance = 0.5
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer
    }
}
