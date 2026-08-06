import { afterEach, describe, expect, it, vi } from "vitest";
import { addComment, getTransitions, transitionIssue } from "./jiraClient.js";

const config = {
  baseUrl: "https://example.atlassian.net",
  email: "bot@example.com",
  apiToken: "dummy-token",
};

function stubFetchOnce(response: { status: number; json?: unknown }) {
  return vi.fn().mockResolvedValueOnce({
    ok: response.status >= 200 && response.status < 300,
    status: response.status,
    json: async () => response.json ?? {},
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// 仕様: /Users/ryosyamazaki/repo/study/specs/jira-automation/design.md#関連するファイル抜粋
describe("JIRAチケットへのコメント追加", () => {
  it("正しいエンドポイント・認証ヘッダー・ボディでリクエストする", async () => {
    const fetchMock = stubFetchOnce({ status: 201 });
    vi.stubGlobal("fetch", fetchMock);

    await addComment(config, "NMBM-123", "テストコメント");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://example.atlassian.net/rest/api/2/issue/NMBM-123/comment");
    expect(init.method).toBe("POST");
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe(`Basic ${Buffer.from("bot@example.com:dummy-token").toString("base64")}`);
    expect(headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual({ body: "テストコメント" });
  });
});

describe("対象チケットの有効な遷移一覧の取得", () => {
  it("対象チケットの遷移一覧を取得できる", async () => {
    const transitions = [{ id: "21", name: "レビューを依頼する", to: { id: "4", name: "レビュー中" } }];
    const fetchMock = stubFetchOnce({ status: 200, json: { transitions } });
    vi.stubGlobal("fetch", fetchMock);

    const result = await getTransitions(config, "NMBM-123");

    expect(result).toEqual({ ok: true, data: transitions });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://example.atlassian.net/rest/api/2/issue/NMBM-123/transitions");
    expect(init.method).toBe("GET");
  });
});

describe("指定した遷移idでのステータス遷移実行", () => {
  it("指定した遷移idでリクエストする", async () => {
    const fetchMock = stubFetchOnce({ status: 204 });
    vi.stubGlobal("fetch", fetchMock);

    await transitionIssue(config, "NMBM-123", "21");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://example.atlassian.net/rest/api/2/issue/NMBM-123/transitions");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ transition: { id: "21" } });
  });
});

// 仕様: /Users/ryosyamazaki/repo/study/specs/jira-automation/design.md#エラーハンドリング
describe("一時的な5xxエラーへのリトライ", () => {
  it("1〜2回リトライした後、最終的に失敗してもエラーをthrowせず失敗を表す結果を返す", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await addComment(config, "NMBM-123", "テストコメント");

    expect(result).toEqual({ ok: false, status: 503, error: expect.any(String) });
    expect(fetchMock.mock.calls.length).toBeGreaterThan(1);
    expect(fetchMock.mock.calls.length).toBeLessThanOrEqual(3);
  });
});
