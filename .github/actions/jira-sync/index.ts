import { readFile } from "node:fs/promises";
import { buildMergeEventComment, buildPrEventComment, type PrEventType } from "./buildComment.js";
import { classifyMerge } from "./classifyMerge.js";
import { extractIssueKey } from "./extractIssueKey.js";
import * as defaultJiraClient from "./jiraClient.js";
import type { JiraConfig } from "./jiraClient.js";
import { resolveTransition } from "./resolveTransition.js";
import type { JiraApiResult, JiraTransition } from "./types.js";

export type PullRequestEvent = {
  action: "opened" | "synchronize" | "closed" | string;
  number: number;
  pull_request: {
    head: { ref: string };
    title: string;
    html_url: string;
    body: string | null;
    changed_files: number;
    merged: boolean;
  };
};

export type RunEnv = {
  JIRA_BASE_URL?: string;
  JIRA_EMAIL?: string;
  JIRA_API_TOKEN?: string;
  CHANGED_FILES?: string;
  SPEC_ONLY_PATH_PATTERN?: string;
  GITHUB_REPOSITORY?: string;
};

type JiraClientDeps = {
  addComment: (config: JiraConfig, issueKey: string, commentBody: string) => Promise<JiraApiResult<void>>;
  getTransitions: (config: JiraConfig, issueKey: string) => Promise<JiraApiResult<JiraTransition[]>>;
  transitionIssue: (config: JiraConfig, issueKey: string, transitionId: string) => Promise<JiraApiResult<void>>;
};

export type RunDeps = {
  extractIssueKey?: typeof extractIssueKey;
  classifyMerge?: typeof classifyMerge;
  resolveTransition?: typeof resolveTransition;
  jiraClient?: JiraClientDeps;
};

const REVIEW_STATUS_NAME = "レビュー中";
const IN_PROGRESS_STATUS_NAME = "進行中";
const DONE_STATUS_NAME = "完了";

async function applyTransition(
  issueKey: string,
  targetStatusName: string,
  config: JiraConfig,
  jiraClient: JiraClientDeps,
  resolveTransitionFn: typeof resolveTransition,
): Promise<void> {
  const transitionsResult = await jiraClient.getTransitions(config, issueKey);
  if (!transitionsResult.ok) {
    console.warn(`[WARN] issue=${issueKey} failed to fetch transitions: ${transitionsResult.error}`);
    return;
  }

  const transition = resolveTransitionFn(transitionsResult.data, targetStatusName);
  if (!transition) {
    console.log(`[INFO] issue=${issueKey} transition to "${targetStatusName}" is not available, skipping`);
    return;
  }

  const transitionResult = await jiraClient.transitionIssue(config, issueKey, transition.id);
  if (transitionResult.ok) {
    console.log(`[INFO] issue=${issueKey} transitioned to "${targetStatusName}"`);
  } else {
    console.warn(`[WARN] issue=${issueKey} failed to transition to "${targetStatusName}": ${transitionResult.error}`);
  }
}

async function postComment(issueKey: string, comment: string, config: JiraConfig, jiraClient: JiraClientDeps): Promise<void> {
  const commentResult = await jiraClient.addComment(config, issueKey, comment);
  if (commentResult.ok) {
    console.log(`[INFO] issue=${issueKey} comment added`);
  } else {
    console.warn(`[WARN] issue=${issueKey} failed to add comment: ${commentResult.error}`);
  }
}

async function handlePrEvent(
  event: PullRequestEvent,
  issueKey: string,
  config: JiraConfig,
  jiraClient: JiraClientDeps,
  resolveTransitionFn: typeof resolveTransition,
): Promise<void> {
  await applyTransition(issueKey, REVIEW_STATUS_NAME, config, jiraClient, resolveTransitionFn);

  const comment = buildPrEventComment({
    eventType: event.action as PrEventType,
    prTitle: event.pull_request.title,
    prUrl: event.pull_request.html_url,
    summary: event.pull_request.body ?? "",
    changedFilesCount: event.pull_request.changed_files,
  });
  await postComment(issueKey, comment, config, jiraClient);
}

async function handleMergeEvent(
  event: PullRequestEvent,
  issueKey: string,
  config: JiraConfig,
  changedFiles: string[],
  specOnlyPathPattern: string,
  jiraClient: JiraClientDeps,
  classifyMergeFn: typeof classifyMerge,
  resolveTransitionFn: typeof resolveTransition,
): Promise<void> {
  const classification = classifyMergeFn(changedFiles, specOnlyPathPattern);
  const targetStatusName = classification === "spec-only" ? IN_PROGRESS_STATUS_NAME : DONE_STATUS_NAME;

  await applyTransition(issueKey, targetStatusName, config, jiraClient, resolveTransitionFn);

  const comment = buildMergeEventComment({
    prTitle: event.pull_request.title,
    prUrl: event.pull_request.html_url,
    summary: event.pull_request.body ?? "",
  });
  await postComment(issueKey, comment, config, jiraClient);
}

export async function run(event: PullRequestEvent, env: RunEnv, deps: RunDeps = {}): Promise<void> {
  const extractIssueKeyFn = deps.extractIssueKey ?? extractIssueKey;
  const classifyMergeFn = deps.classifyMerge ?? classifyMerge;
  const resolveTransitionFn = deps.resolveTransition ?? resolveTransition;
  const jiraClient = deps.jiraClient ?? defaultJiraClient;

  const issueKey = extractIssueKeyFn(event.pull_request.head.ref);
  console.log(`[INFO] PR #${event.number} event=${event.action} issueKey=${issueKey ?? "(not found)"}`);
  console.log(`[INFO] repository=${env.GITHUB_REPOSITORY ?? "(unknown)"} specOnlyPathPattern=${env.SPEC_ONLY_PATH_PATTERN ?? "(not set)"}`);

  if (!issueKey) {
    return;
  }

  if (!env.JIRA_BASE_URL || !env.JIRA_EMAIL || !env.JIRA_API_TOKEN) {
    console.log(`[INFO] issue=${issueKey} JIRA credentials are not available, skipping`);
    return;
  }

  const config: JiraConfig = {
    baseUrl: env.JIRA_BASE_URL,
    email: env.JIRA_EMAIL,
    apiToken: env.JIRA_API_TOKEN,
  };

  if (event.action === "opened" || event.action === "synchronize") {
    await handlePrEvent(event, issueKey, config, jiraClient, resolveTransitionFn);
    return;
  }

  if (event.action === "closed" && event.pull_request.merged) {
    const changedFiles = (env.CHANGED_FILES ?? "")
      .split("\n")
      .map((path) => path.trim())
      .filter((path) => path.length > 0);
    await handleMergeEvent(
      event,
      issueKey,
      config,
      changedFiles,
      env.SPEC_ONLY_PATH_PATTERN ?? "",
      jiraClient,
      classifyMergeFn,
      resolveTransitionFn,
    );
    return;
  }

  console.log(`[INFO] issue=${issueKey} event=${event.action} merged=${event.pull_request.merged} is not applicable, skipping`);
}

async function main(): Promise<void> {
  try {
    const eventPath = process.env.GITHUB_EVENT_PATH;
    if (!eventPath) {
      console.warn("[WARN] GITHUB_EVENT_PATH is not set, skipping");
      return;
    }
    const raw = await readFile(eventPath, "utf-8");
    const event = JSON.parse(raw) as PullRequestEvent;
    await run(event, process.env as RunEnv);
  } catch (error) {
    console.warn(`[WARN] jira-sync failed unexpectedly: ${error instanceof Error ? error.message : String(error)}`);
  }
}

const isMainModule = process.argv[1] !== undefined && import.meta.url === `file://${process.argv[1]}`;
if (isMainModule) {
  void main();
}
