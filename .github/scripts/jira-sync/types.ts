export type JiraTransition = {
  id: string;
  name: string;
  to: {
    id: string;
    name: string;
  };
};

export type JiraApiResult<T> = { ok: true; data: T } | { ok: false; status?: number; error: string };
