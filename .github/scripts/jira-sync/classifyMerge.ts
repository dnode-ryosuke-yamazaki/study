export type MergeClassification = "spec-only" | "implementation";

const SPEC_PATH_PATTERN = /^(specs\/|apps\/[^/]+\/specs\/)/;

export function classifyMerge(changedFiles: string[]): MergeClassification {
  const isSpecOnly = changedFiles.every((path) => SPEC_PATH_PATTERN.test(path));
  return isSpecOnly ? "spec-only" : "implementation";
}
