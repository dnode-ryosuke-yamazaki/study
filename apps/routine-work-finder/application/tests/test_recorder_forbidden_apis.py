"""記録係のソースが、記録しないと決めたものを取る関数を使っていないことを確かめる構造検証。

画面の撮影・Apple Events・キー入力の取得・カメラ・部品の中の文字の読み取りと、相手のアプリへの書き込みは、
処理そのものを持たない。記録係のソース(recorder/Sources/)からコメントを除いて走査し、名前が出てこないことを見る。
"""

import os
import re
import unittest
from pathlib import Path

SOURCES_DIR = Path(os.environ.get("RWF_RECORDER_SOURCES", Path(__file__).resolve().parent.parent / "recorder" / "Sources"))

SCREEN_CAPTURE = ["CGWindowListCreateImage", "CGDisplayCreateImage", "CGDisplayStream", "ScreenCaptureKit", "SCStream", "SCScreenshotManager"]
APPLE_EVENTS = ["NSAppleScript", "NSAppleEventDescriptor", "AESendMessage", "OSAScript", "SBApplication", "NSUserAppleScriptTask"]
KEY_INPUT = ["tapCreate", "CGEventTapCreate", "addGlobalMonitorForEvents", "addLocalMonitorForEvents", "IOHIDManager"]
CAMERA = ["AVCaptureDevice", "AVCaptureSession", "AVCaptureVideoDataOutput"]
INNER_TEXT = [
    "kAXSelectedTextAttribute",
    "kAXSelectedTextRangeAttribute",
    "kAXStringForRangeParameterizedAttribute",
    "kAXVisibleCharacterRangeAttribute",
    "kAXNumberOfCharactersAttribute",
    "AXUIElementCopyParameterizedAttributeValue",
    "AXUIElementCopyMultipleAttributeValues",
]
WRITE_TO_APPS = ["AXUIElementSetAttributeValue", "AXUIElementPerformAction", "AXManualAccessibility", "AXEnhancedUserInterface"]

ALLOWED_AX_ATTRIBUTES = {
    "kAXFocusedWindowAttribute",
    "kAXTitleAttribute",
    "kAXFocusedUIElementAttribute",
    "kAXRoleAttribute",
    "kAXSubroleAttribute",
    "kAXChildrenAttribute",
    "kAXTabsAttribute",
    "kAXValueAttribute",
}


def strip_comments(source: str) -> str:
    """// と /* */ のコメントを除く(文字列の中の // は考えない。記録係のソースは URL などを持たない)"""
    without_block = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(line.split("//", 1)[0] for line in without_block.splitlines())


def recorder_code() -> str:
    files = sorted(SOURCES_DIR.rglob("*.swift"))
    if not files:
        raise AssertionError(f"記録係のソースが見つからない: {SOURCES_DIR}")
    return "\n".join(strip_comments(path.read_text(encoding="utf-8")) for path in files)


class ForbiddenApiTests(unittest.TestCase):
    """記録係が、記録しないと決めたものを取る処理を持たないこと"""

    def assert_absent(self, names):
        code = recorder_code()
        found = [name for name in names if re.search(rf"\b{re.escape(name)}\b", code)]
        self.assertEqual(found, [], f"使ってはいけない名前が記録係のソースにある: {found}")

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないもの-1
    def test_画面の撮影とApple_Eventsの関数を使っていない(self):
        """否定確認: 記録係のソースに CGWindowListCreateImage の呼び出しを1行足すと落ちる"""
        self.assert_absent(SCREEN_CAPTURE + APPLE_EVENTS)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないもの-2
    def test_キー入力を受け取る関数を使っていない(self):
        """否定確認: NSEvent.addGlobalMonitorForEvents の呼び出しを1行足すと落ちる"""
        self.assert_absent(KEY_INPUT)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないもの-3
    def test_カメラを使う型を使っていない(self):
        """否定確認: AVCaptureDevice を使う行を1行足すと落ちる"""
        self.assert_absent(CAMERA)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないもの-4
    def test_部品の中の文字を返す属性を読まない(self):
        """否定確認: kAXSelectedTextAttribute を読む行を1行足すと落ちる"""
        self.assert_absent(INNER_TEXT)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#ウィンドウの題名の記録-3
    def test_相手のアプリに書き込まない(self):
        """否定確認: AXUIElementSetAttributeValue の呼び出しを1行足すと落ちる"""
        self.assert_absent(WRITE_TO_APPS)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないもの-4
    def test_読む属性は許可した8つだけ(self):
        """否定確認: kAXDescriptionAttribute を読む行を1行足すと落ちる"""
        used = set(re.findall(r"\bkAX\w+Attribute\b", recorder_code()))
        self.assertTrue(used, "記録係がアクセシビリティの属性を1つも読んでいない")
        self.assertEqual(used - ALLOWED_AX_ATTRIBUTES, set())

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないもの-4
    def test_値の属性はタブの選択状態を見る1か所だけで読む(self):
        """否定確認: kAXValueAttribute を読む行をもう1行足すと落ちる"""
        self.assertEqual(len(re.findall(r"\bkAXValueAttribute\b", recorder_code())), 1)

    # 仕様: apps/routine-work-finder/specs/activity-recording/requirements.md#記録しないもの-4
    def test_属性の名前を文字列で直接書いて許可リストをすり抜けない(self):
        """否定確認: "AXSelectedText" を属性名として渡す行を1行足すと落ちる"""
        literals = re.findall(r'"(AX[A-Za-z]+)"', recorder_code())
        role_names = {"AXTabGroup"}
        self.assertEqual(sorted(set(literals) - role_names), [])


if __name__ == "__main__":
    unittest.main()
