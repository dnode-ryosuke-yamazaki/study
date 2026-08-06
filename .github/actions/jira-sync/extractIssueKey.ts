const ISSUE_KEY_PATTERN = /[A-Z][A-Z0-9]*-\d+/;

export function extractIssueKey(branchName: string): string | null {
  const match = branchName.match(ISSUE_KEY_PATTERN);
  return match ? match[0] : null;
}
