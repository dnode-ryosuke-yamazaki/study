import { describe, expect, it } from "vitest";

// 仕様: apps/digest-platform/specs/batch-runner/tasks.md の「2.」(要件の項目を持たない土台の確認)
describe("バッチ部品のテストを回す土台", () => {
  it("手元のターミナルで npm test を実行するとテストが1件見つかって通る", () => {
    expect(true).toBe(true);
  });
});
