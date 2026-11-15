import "server-only";

// Reads the task issues (#4 onwards in ogutdgn/argos) and works out each
// task's state. Runs only on the server: GITHUB_TOKEN never reaches the browser.

const REPO = "ogutdgn/argos";

export const AREAS = ["web", "station", "joint"] as const;
export const PHASES = [0, 1, 2, 3] as const;

export type Area = (typeof AREAS)[number];
export type TaskState = "done" | "in progress" | "ready" | "blocked";

export type Task = {
  id: string; // e.g. "W0.2"
  name: string;
  number: number;
  url: string;
  area: Area;
  phase: number;
  state: TaskState;
  assignees: string[]; // GitHub logins only
};

export type PlanResult =
  | { ok: true; tasks: Task[] }
  | { ok: false; reason: string };

type GitHubIssue = {
  number: number;
  title: string;
  state: "open" | "closed";
  html_url: string;
  body: string | null;
  labels: { name?: string }[];
  assignees: { login: string }[] | null;
  pull_request?: unknown;
};

// Titles look like "W0.2: Plan page".
const TITLE = /^([WSJ]\d+\.\d+):\s*(.+)$/;
const PHASE_LABEL = /^phase (\d+)$/;

// The body has "**Depends on:** W0.1 (#5), S0.1 (#6) · **Branch:** ..." or
// "**Depends on:** —". Only the issue numbers matter.
function dependencies(body: string | null): number[] {
  const match = body?.match(/\*\*Depends on:\*\*([^\n]*)/);
  if (!match) return [];
  const segment = match[1].split(" · ")[0];
  return [...segment.matchAll(/#(\d+)/g)].map((m) => Number(m[1]));
}

async function fetchIssues(token: string): Promise<GitHubIssue[]> {
  const issues: GitHubIssue[] = [];
  for (let page = 1; ; page++) {
    const res = await fetch(
      `https://api.github.com/repos/${REPO}/issues?state=all&per_page=100&page=${page}`,
      {
        headers: {
          Accept: "application/vnd.github+json",
          Authorization: `Bearer ${token}`,
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "argos-plan-page",
        },
        cache: "no-store",
      },
    );
    if (!res.ok) throw new Error(`GitHub answered ${res.status}`);
    const batch = (await res.json()) as GitHubIssue[];
    issues.push(...batch);
    if (batch.length < 100) return issues;
  }
}

export async function loadPlan(): Promise<PlanResult> {
  const token = process.env.GITHUB_TOKEN;
  if (!token) return { ok: false, reason: "GITHUB_TOKEN is not set" };

  let issues: GitHubIssue[];
  try {
    // The issues endpoint also lists pull requests; drop them.
    issues = (await fetchIssues(token)).filter((i) => !i.pull_request);
  } catch (e) {
    return { ok: false, reason: e instanceof Error ? e.message : "Unknown error" };
  }

  const closed = new Set(
    issues.filter((i) => i.state === "closed").map((i) => i.number),
  );

  const tasks: Task[] = [];
  for (const issue of issues) {
    const title = issue.title.match(TITLE);
    const labels = issue.labels.map((l) => l.name ?? "");
    const area = AREAS.find((a) => labels.includes(a));
    const phaseLabel = labels.map((l) => l.match(PHASE_LABEL)).find(Boolean);
    if (!title || !area || !phaseLabel) continue; // not a task issue

    const assignees = (issue.assignees ?? []).map((a) => a.login);
    // A dependency counts as finished only if its issue is closed; one that
    // cannot be found keeps the task blocked.
    let state: TaskState;
    if (issue.state === "closed") state = "done";
    else if (assignees.length > 0) state = "in progress";
    else if (dependencies(issue.body).every((n) => closed.has(n))) state = "ready";
    else state = "blocked";

    tasks.push({
      id: title[1],
      name: title[2],
      number: issue.number,
      url: issue.html_url,
      area,
      phase: Number(phaseLabel[1]),
      state,
      assignees,
    });
  }

  // Order by task ID within a cell: W1.1, W1.2, ... W1.10.
  tasks.sort((a, b) => a.id.localeCompare(b.id, "en", { numeric: true }));
  return { ok: true, tasks };
}
