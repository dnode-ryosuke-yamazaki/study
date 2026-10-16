import AppKit
import RecorderCore

// 記録係の入口。launchd がログイン時に起動し、落ちたら起動し直す。
// AppKit を初期化してから回す(前面のアプリの切り替えの通知・モニターの一覧を受け取るため)。
// 画面には何も出さない(Dock にも並ばない)
let application = NSApplication.shared
application.setActivationPolicy(.prohibited)

let ticker = Ticker(loop: RecorderLoop(environment: LiveEnvironment()))
ticker.start()
application.run()
