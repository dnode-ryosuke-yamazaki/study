import type { JiraTransition } from "./types.js";

export function resolveTransition(
  transitions: JiraTransition[],
  targetStatusName: string,
): JiraTransition | null {
  return transitions.find((transition) => transition.to.name === targetStatusName) ?? null;
}
