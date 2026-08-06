import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { run, type PullRequestEvent, type RunEnv } from "./index.js";
import type { JiraTransition } from "./types.js";

const validEnv: RunEnv = {
  JIRA_BASE_URL: "https://example.atlassian.net",
  JIRA_EMAIL: "bot@example.com",
  JIRA_API_TOKEN: "dummy-token",
};

function buildEvent(overrides: Partial<PullRequestEvent> = {}): PullRequestEvent {
  return {
    action: "opened",
    number: 42,
    pull_request: {
      head: { ref: "feature/NMBM-1-add-login" },
      title: "ログイン機能を追加",
      html_url: "https://github.com/example/study/pull/42",
      body: "概要",
      changed_files: 3,
      merged: false,
    },
    ...overrides,
  };
}

function buildJiraClientMock() {
  return {
    addComment: vi.fn().mockResolvedValue({ ok: true, data: undefined }),
    getTransitions: vi.fn().mockResolvedValue({ ok: true, data: [] as JiraTransition[] }),
    transitionIssue: vi.fn().mockResolvedValue({ ok: true, data: undefined }),
  };
}

beforeEach(() => {
  vi.spyOn(console, "log").mockImplementation(() => undefined);
  vi.spyOn(console, "warn").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
});

// 仕様: /Users/ryosyamazaki/repo/study/specs/jira-automation/requirements.md#pr作成更新時の自動更新-4
describe("ブランチ名からJIRAチケットキーを抽出できない場合の早期終了", () => {
  it("キー抽出に失敗した場合、classifyMerge・jiraClientを呼ばずに終了する", async () => {
    const jiraClient = buildJiraClientMock();
    const classifyMerge = vi.fn();

    await run(buildEvent(), validEnv, {
      extractIssueKey: vi.fn().mockReturnValue(null),
      classifyMerge,
      jiraClient,
    });

    expect(classifyMerge).not.toHaveBeenCalled();
    expect(jiraClient.getTransitions).not.toHaveBeenCalled();
    expect(jiraClient.addComment).not.toHaveBeenCalled();
  });
});

// 仕様: /Users/ryosyamazaki/repo/study/specs/jira-automation/design.md#エラーハンドリング
describe("JIRA APIトークンが渡っていない場合のスキップ(フォークPR対応)", () => {
  it("シークレットが渡っていない場合、処理をスキップして正常終了する", async () => {
    const jiraClient = buildJiraClientMock();

    await expect(
      run(buildEvent(), { ...validEnv, JIRA_API_TOKEN: undefined }, { jiraClient }),
    ).resolves.toBeUndefined();

    expect(jiraClient.getTransitions).not.toHaveBeenCalled();
    expect(jiraClient.addComment).not.toHaveBeenCalled();
  });
});

// 仕様: /Users/ryosyamazaki/repo/study/specs/jira-automation/design.md#pr作成更新時のjira更新
describe("PR作成/更新イベントでのコメント追記とステータス遷移試行", () => {
  it("有効な遷移に「レビュー中」が含まれる場合、遷移を実行してからコメントを追記する", async () => {
    const reviewTransition: JiraTransition = { id: "21", name: "レビューを依頼する", to: { id: "4", name: "レビュー中" } };
    const jiraClient = buildJiraClientMock();
    jiraClient.getTransitions.mockResolvedValue({ ok: true, data: [reviewTransition] });

    await run(buildEvent({ action: "synchronize" }), validEnv, { jiraClient });

    expect(jiraClient.transitionIssue).toHaveBeenCalledWith(
      expect.objectContaining({ baseUrl: validEnv.JIRA_BASE_URL }),
      "NMBM-1",
      "21",
    );
    expect(jiraClient.addComment).toHaveBeenCalledWith(
      expect.anything(),
      "NMBM-1",
      expect.stringContaining("synchronize"),
    );
  });
});

// 仕様: /Users/ryosyamazaki/repo/study/specs/jira-automation/design.md#prマージ時のjira更新
describe("PRマージイベントでのステータス遷移先の切り替え", () => {
  it("仕様承認PRのマージ(spec-only)の場合は「進行中」への遷移を試みる", async () => {
    const jiraClient = buildJiraClientMock();
    const resolveTransition = vi.fn().mockReturnValue(null);

    await run(
      buildEvent({ action: "closed", pull_request: { ...buildEvent().pull_request, merged: true } }),
      { ...validEnv, CHANGED_FILES: "specs/jira-automation/requirements.md" },
      { classifyMerge: vi.fn().mockReturnValue("spec-only"), resolveTransition, jiraClient },
    );

    expect(resolveTransition).toHaveBeenCalledWith(expect.anything(), "進行中");
  });

  it("実装PRのマージ(implementation)の場合は「完了」への遷移を試みる", async () => {
    const jiraClient = buildJiraClientMock();
    const resolveTransition = vi.fn().mockReturnValue(null);

    await run(
      buildEvent({ action: "closed", pull_request: { ...buildEvent().pull_request, merged: true } }),
      { ...validEnv, CHANGED_FILES: "apps/notes-api/application/lambda/handler.py" },
      { classifyMerge: vi.fn().mockReturnValue("implementation"), resolveTransition, jiraClient },
    );

    expect(resolveTransition).toHaveBeenCalledWith(expect.anything(), "完了");
  });
});

// 仕様: /Users/ryosyamazaki/repo/study/specs/jira-automation/requirements.md#他リポジトリからの利用-2
describe("仕様のみ判定条件(SPEC_ONLY_PATH_PATTERN)の呼び出し元からの受け渡し", () => {
  it("環境変数SPEC_ONLY_PATH_PATTERNで渡された条件を、変更ファイル一覧とともにclassifyMergeへ渡す", async () => {
    const jiraClient = buildJiraClientMock();
    const classifyMerge = vi.fn().mockReturnValue("spec-only");

    await run(
      buildEvent({ action: "closed", pull_request: { ...buildEvent().pull_request, merged: true } }),
      {
        ...validEnv,
        CHANGED_FILES: ".claude/docs/jira-automation/spec/requirements/requirements.md",
        SPEC_ONLY_PATH_PATTERN: "^\\.claude/docs/[^/]+/(spec|tasks)/",
      },
      { classifyMerge, jiraClient },
    );

    expect(classifyMerge).toHaveBeenCalledWith(
      [".claude/docs/jira-automation/spec/requirements/requirements.md"],
      "^\\.claude/docs/[^/]+/(spec|tasks)/",
    );
  });
});

// 仕様: /Users/ryosyamazaki/repo/study/specs/jira-automation/design.md#エラーハンドリング
describe("JIRA API呼び出しの失敗時にも異常終了しないこと", () => {
  it("コメント追記・遷移取得が失敗を返しても、run()はrejectしない", async () => {
    const jiraClient = {
      addComment: vi.fn().mockResolvedValue({ ok: false, status: 503, error: "boom" }),
      getTransitions: vi.fn().mockResolvedValue({ ok: false, status: 503, error: "boom" }),
      transitionIssue: vi.fn().mockResolvedValue({ ok: false, status: 503, error: "boom" }),
    };

    await expect(run(buildEvent(), validEnv, { jiraClient })).resolves.toBeUndefined();
  });
});

// 仕様: /Users/ryosyamazaki/repo/study/specs/jira-automation/design.md#ログ
describe("処理状況のログ出力", () => {
  it("処理開始時にPR番号・イベント種別・抽出したチケットキーをINFOログに出力する", async () => {
    const jiraClient = buildJiraClientMock();

    await run(buildEvent(), validEnv, { jiraClient });

    expect(console.log).toHaveBeenCalledWith(expect.stringContaining("PR #42"));
    expect(console.log).toHaveBeenCalledWith(expect.stringContaining("opened"));
    expect(console.log).toHaveBeenCalledWith(expect.stringContaining("NMBM-1"));
  });

  it("コメント投稿・ステータス遷移が失敗した場合はWARNログに出力する", async () => {
    const jiraClient = {
      addComment: vi.fn().mockResolvedValue({ ok: false, status: 500, error: "boom" }),
      getTransitions: vi.fn().mockResolvedValue({ ok: false, status: 500, error: "boom" }),
      transitionIssue: vi.fn().mockResolvedValue({ ok: false, status: 500, error: "boom" }),
    };

    await run(buildEvent(), validEnv, { jiraClient });

    expect(console.warn).toHaveBeenCalledWith(expect.stringContaining("failed to fetch transitions"));
    expect(console.warn).toHaveBeenCalledWith(expect.stringContaining("failed to add comment"));
  });
});
