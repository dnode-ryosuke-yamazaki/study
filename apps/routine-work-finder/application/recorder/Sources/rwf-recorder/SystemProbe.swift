import AppKit
import CoreAudio
import CoreGraphics
import Foundation
import IOKit.pwr_mgt
import RecorderCore

/// 前面のアプリ
struct FrontApp {
    let name: String?
    let bundleId: String?
    let processIdentifier: pid_t
}

/// 5秒ごとの行に入れる周りの状態を macOS の関数で尋ねる。別のコマンドは起動しない。
/// 取れなかった項目は nil を返す(行には null で書く)。取り方は appendix.md「周りの状態の取り方」
enum SystemProbe {
    static func frontApp() -> FrontApp? {
        guard let app = NSWorkspace.shared.frontmostApplication else { return nil }
        return FrontApp(name: app.localizedName, bundleId: app.bundleIdentifier, processIdentifier: app.processIdentifier)
    }

    static func surroundings(for app: FrontApp?) -> Surroundings {
        Surroundings(
            app: app?.name,
            bundleId: app?.bundleId,
            monitor: monitorNumber(),
            idleSec: secondsSinceLastInput(),
            locked: screenLocked(),
            mic: microphoneInUse(),
            displaySleepPrevented: displaySleepPrevented()
        )
    }

    /// マウスカーソルのあるモニターの番号(1から数える)
    static func monitorNumber() -> Int? {
        let location = NSEvent.mouseLocation
        guard let index = NSScreen.screens.firstIndex(where: { NSMouseInRect(location, $0.frame, false) }) else { return nil }
        return index + 1
    }

    /// 最後のキーボードかマウスの入力からの秒数
    static func secondsSinceLastInput() -> Double? {
        guard let anyInput = CGEventType(rawValue: UInt32.max) else { return nil }
        let seconds = CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: anyInput)
        return seconds.isFinite && seconds >= 0 ? seconds : nil
    }

    /// 画面ロック中か。セッションの情報が取れなければ nil、ロックの項目が無ければロックしていない
    static func screenLocked() -> Bool? {
        guard let session = CGSessionCopyCurrentDictionary() as? [String: Any] else { return nil }
        return (session["CGSSessionScreenIsLocked"] as? Bool) ?? false
    }

    /// 既定のマイク(入力デバイス)がどこかのアプリで使われているか
    static func microphoneInUse() -> Bool? {
        var deviceId = AudioObjectID(kAudioObjectUnknown)
        var size = UInt32(MemoryLayout<AudioObjectID>.size)
        var defaultInput = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &defaultInput, 0, nil, &size, &deviceId) == noErr,
              deviceId != kAudioObjectUnknown
        else { return nil }

        var running: UInt32 = 0
        size = UInt32(MemoryLayout<UInt32>.size)
        var isRunning = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyDeviceIsRunningSomewhere,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        guard AudioObjectGetPropertyData(deviceId, &isRunning, 0, nil, &size, &running) == noErr else { return nil }
        return running != 0
    }

    /// 画面のスリープを止めているアプリがあるか(PreventUserIdleDisplaySleep の数が1以上)
    static func displaySleepPrevented() -> Bool? {
        var status: Unmanaged<CFDictionary>?
        guard IOPMCopyAssertionsStatus(&status) == kIOReturnSuccess,
              let dictionary = status?.takeRetainedValue() as? [String: Any]
        else { return nil }
        guard let count = dictionary[kIOPMAssertionTypePreventUserIdleDisplaySleep] as? Int else { return false }
        return count >= 1
    }
}
