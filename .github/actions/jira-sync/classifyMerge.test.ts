import { describe, expect, it } from "vitest";
import { classifyMerge } from "./classifyMerge.js";

const STUDY_SPEC_ONLY_PATTERN = "^(specs/|apps/[^/]+/specs/)";

// 仕様: /Users/ryosyamazaki/repo/study/specs/jira-automation/requirements.md#prマージ時の自動更新仕様承認pr-1、requirements.md#prマージ時の自動更新実装pr-1、requirements.md#他リポジトリからの利用-2
describe("マージされたPRの変更ファイルによる仕様承認PR/実装PRの判定", () => {
  it("変更ファイルがすべてspecs/配下の場合は仕様承認PRのマージ(spec-only)と判定する", () => {
    const changedFiles = ["specs/jira-automation/requirements.md", "specs/jira-automation/design.md"];
    expect(classifyMerge(changedFiles, STUDY_SPEC_ONLY_PATTERN)).toBe("spec-only");
  });

  it("変更ファイルがすべてapps/*/specs/配下の場合は仕様承認PRのマージ(spec-only)と判定する", () => {
    const changedFiles = ["apps/notes-api/specs/note-deletion/requirements.md"];
    expect(classifyMerge(changedFiles, STUDY_SPEC_ONLY_PATTERN)).toBe("spec-only");
  });

  it("変更ファイルに仕様関連ディレクトリ以外のパスが1件でも含まれる場合は実装PRのマージ(implementation)と判定する", () => {
    const changedFiles = [
      "specs/jira-automation/requirements.md",
      "apps/notes-api/application/lambda/handler.py",
    ];
    expect(classifyMerge(changedFiles, STUDY_SPEC_ONLY_PATTERN)).toBe("implementation");
  });

  it("呼び出し元から渡された判定条件が異なる場合、その条件に従って判定する(判定条件を決め打ちにしない)", () => {
    const changedFiles = [".claude/docs/jira-automation/spec/requirements/requirements.md"];
    expect(classifyMerge(changedFiles, "^\\.claude/docs/[^/]+/(spec|tasks)/")).toBe("spec-only");
    expect(classifyMerge(changedFiles, STUDY_SPEC_ONLY_PATTERN)).toBe("implementation");
  });
});
