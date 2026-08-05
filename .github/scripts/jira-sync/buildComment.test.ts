import { describe, expect, it } from "vitest";
import { buildMergeEventComment, buildPrEventComment } from "./buildComment.js";

// 仕様: /Users/ryosyamazaki/repo/study/specs/jira-automation/requirements.md#pr作成更新時の自動更新-2
describe("PR作成・更新イベント用のコメント本文組み立て", () => {
  it("イベント種別・PRタイトル・URL・変更内容概要・変更ファイル件数が含まれる", () => {
    const comment = buildPrEventComment({
      eventType: "opened",
      prTitle: "ログイン機能を追加",
      prUrl: "https://github.com/example/study/pull/42",
      summary: "ログインフォームとAPIを実装",
      changedFilesCount: 5,
    });

    expect(comment).toContain("opened");
    expect(comment).toContain("ログイン機能を追加");
    expect(comment).toContain("https://github.com/example/study/pull/42");
    expect(comment).toContain("ログインフォームとAPIを実装");
    expect(comment).toContain("5");
  });
});

// 仕様: /Users/ryosyamazaki/repo/study/specs/jira-automation/requirements.md#prマージ時の自動更新仕様承認pr-2、requirements.md#prマージ時の自動更新実装pr-2
describe("PRマージイベント用のコメント本文組み立て", () => {
  it("PRタイトル・URL・変更内容概要が含まれる", () => {
    const comment = buildMergeEventComment({
      prTitle: "ログイン機能を追加",
      prUrl: "https://github.com/example/study/pull/42",
      summary: "ログインフォームとAPIを実装",
    });

    expect(comment).toContain("ログイン機能を追加");
    expect(comment).toContain("https://github.com/example/study/pull/42");
    expect(comment).toContain("ログインフォームとAPIを実装");
  });
});
