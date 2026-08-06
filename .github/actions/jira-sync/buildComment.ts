export type PrEventType = "opened" | "synchronize";

export type PrEventCommentInput = {
  eventType: PrEventType;
  prTitle: string;
  prUrl: string;
  summary: string;
  changedFilesCount: number;
};

export type MergeEventCommentInput = {
  prTitle: string;
  prUrl: string;
  summary: string;
};

export function buildPrEventComment(input: PrEventCommentInput): string {
  return [
    `イベント種別: ${input.eventType}`,
    `PRタイトル: ${input.prTitle}`,
    `URL: ${input.prUrl}`,
    `変更内容概要: ${input.summary}`,
    `変更ファイル数: ${input.changedFilesCount}件`,
  ].join("\n");
}

export function buildMergeEventComment(input: MergeEventCommentInput): string {
  return [`PRタイトル: ${input.prTitle}`, `URL: ${input.prUrl}`, `変更内容概要: ${input.summary}`].join("\n");
}
