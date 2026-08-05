import { describe, expect, it } from "vitest";
import { classifyMerge } from "./classifyMerge.js";

// 仕様: /Users/ryosyamazaki/repo/study/specs/jira-automation/requirements.md#prマージ時の自動更新仕様承認pr-1、requirements.md#prマージ時の自動更新実装pr-1
describe("マージされたPRの変更ファイルによる仕様承認PR/実装PRの判定", () => {
  it("変更ファイルがすべてspecs/配下の場合は仕様承認PRのマージ(spec-only)と判定する", () => {
    const changedFiles = ["specs/jira-automation/requirements.md", "specs/jira-automation/design.md"];
    expect(classifyMerge(changedFiles)).toBe("spec-only");
  });

  it("変更ファイルがすべてapps/*/specs/配下の場合は仕様承認PRのマージ(spec-only)と判定する", () => {
    const changedFiles = ["apps/notes-api/specs/note-deletion/requirements.md"];
    expect(classifyMerge(changedFiles)).toBe("spec-only");
  });

  it("変更ファイルに仕様関連ディレクトリ以外のパスが1件でも含まれる場合は実装PRのマージ(implementation)と判定する", () => {
    const changedFiles = [
      "specs/jira-automation/requirements.md",
      "apps/notes-api/application/lambda/handler.py",
    ];
    expect(classifyMerge(changedFiles)).toBe("implementation");
  });
});
