import { describe, expect, it } from "vitest";
import { extractIssueKey } from "./extractIssueKey.js";

// 仕様: /Users/ryosyamazaki/repo/study/specs/jira-automation/requirements.md#前提-チケットキーとブランチの紐付け-1
describe("ブランチ名からのJIRAチケットキー抽出", () => {
  it("JIRAキーをプレフィックスに含むブランチ名からキーを抽出できる", () => {
    expect(extractIssueKey("feature/NMBM-123-add-login")).toBe("NMBM-123");
  });

  it("JIRAキーを含まないブランチ名の場合はnullを返す", () => {
    expect(extractIssueKey("feature/add-login")).toBeNull();
  });

  it("プロジェクトキーが2種類以上含まれるブランチ名では先頭に一致した1件のみを抽出する", () => {
    expect(extractIssueKey("feature/ABC-1-DEF-2-xxx")).toBe("ABC-1");
  });
});
