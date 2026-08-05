import type { JiraApiResult, JiraTransition } from "./types.js";

export type JiraConfig = {
  baseUrl: string;
  email: string;
  apiToken: string;
};

const MAX_ATTEMPTS = 3;
const RETRY_DELAY_MS = 50;

function buildHeaders(config: JiraConfig): Record<string, string> {
  const token = Buffer.from(`${config.email}:${config.apiToken}`).toString("base64");
  return {
    Authorization: `Basic ${token}`,
    "Content-Type": "application/json",
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function requestWithRetry(url: string, init: RequestInit): Promise<JiraApiResult<unknown>> {
  let lastError = "unknown error";
  let lastStatus: number | undefined;

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
      const response = await fetch(url, init);
      if (response.ok) {
        const data = await response.json().catch(() => undefined);
        return { ok: true, data };
      }

      lastStatus = response.status;
      lastError = `JIRA API request failed: ${response.status} ${url}`;
      const isRetryableStatus = response.status >= 500;
      if (!isRetryableStatus || attempt === MAX_ATTEMPTS) {
        return { ok: false, status: response.status, error: lastError };
      }
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
      if (attempt === MAX_ATTEMPTS) {
        return { ok: false, error: lastError };
      }
    }

    await sleep(RETRY_DELAY_MS);
  }

  return { ok: false, status: lastStatus, error: lastError };
}

export async function addComment(
  config: JiraConfig,
  issueKey: string,
  commentBody: string,
): Promise<JiraApiResult<void>> {
  const result = await requestWithRetry(`${config.baseUrl}/rest/api/2/issue/${issueKey}/comment`, {
    method: "POST",
    headers: buildHeaders(config),
    body: JSON.stringify({ body: commentBody }),
  });
  return result.ok ? { ok: true, data: undefined } : result;
}

export async function getTransitions(
  config: JiraConfig,
  issueKey: string,
): Promise<JiraApiResult<JiraTransition[]>> {
  const result = await requestWithRetry(`${config.baseUrl}/rest/api/2/issue/${issueKey}/transitions`, {
    method: "GET",
    headers: buildHeaders(config),
  });
  if (!result.ok) {
    return result;
  }
  const data = result.data as { transitions: JiraTransition[] };
  return { ok: true, data: data.transitions };
}

export async function transitionIssue(
  config: JiraConfig,
  issueKey: string,
  transitionId: string,
): Promise<JiraApiResult<void>> {
  const result = await requestWithRetry(`${config.baseUrl}/rest/api/2/issue/${issueKey}/transitions`, {
    method: "POST",
    headers: buildHeaders(config),
    body: JSON.stringify({ transition: { id: transitionId } }),
  });
  return result.ok ? { ok: true, data: undefined } : result;
}
