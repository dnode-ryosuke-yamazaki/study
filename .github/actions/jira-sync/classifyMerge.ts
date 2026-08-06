export type MergeClassification = "spec-only" | "implementation";

export function classifyMerge(changedFiles: string[], specOnlyPathPattern: string): MergeClassification {
  const pattern = new RegExp(specOnlyPathPattern);
  const isSpecOnly = changedFiles.every((path) => pattern.test(path));
  return isSpecOnly ? "spec-only" : "implementation";
}
