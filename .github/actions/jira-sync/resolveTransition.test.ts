import { describe, expect, it } from "vitest";
import { resolveTransition } from "./resolveTransition.js";
import type { JiraTransition } from "./types.js";

// 仕様: /Users/ryosyamazaki/repo/study/specs/jira-automation/requirements.md#ビジネスルール制約-2
describe("有効な遷移一覧から指定した遷移先ステータス名の遷移を解決する", () => {
  const transitions: JiraTransition[] = [
    { id: "11", name: "開始する", to: { id: "3", name: "進行中" } },
    { id: "21", name: "レビューを依頼する", to: { id: "4", name: "レビュー中" } },
  ];

  it("遷移一覧に指定した遷移先ステータス名が含まれる場合、その遷移を返す", () => {
    expect(resolveTransition(transitions, "レビュー中")).toEqual(transitions[1]);
  });

  it("遷移一覧に指定した遷移先ステータス名が含まれない場合、nullを返す", () => {
    expect(resolveTransition(transitions, "完了")).toBeNull();
  });
});
