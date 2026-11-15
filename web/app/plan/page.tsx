import type { Metadata } from "next";
import { Suspense } from "react";
import { connection } from "next/server";
import { AREAS, PHASES, loadPlan, type Area, type TaskState } from "./tasks";
import styles from "./plan.module.css";

// Live task plan for the team. Not linked from any other page.
export const metadata: Metadata = {
  title: "Plan · Argos",
  robots: { index: false, follow: false },
};

const AREA_NAMES: Record<Area, string> = {
  web: "Web",
  station: "Station",
  joint: "Joint",
};

const STATE_CLASS: Record<TaskState, string> = {
  done: styles.done,
  "in progress": styles.inProgress,
  ready: styles.ready,
  blocked: styles.blocked,
};

async function Swimlane() {
  // Read GitHub on every request, so a closed or assigned issue shows on reload.
  await connection();
  const plan = await loadPlan();

  if (!plan.ok) {
    return <p>Could not read the task issues: {plan.reason}</p>;
  }

  return (
    <div className={styles.scroll}>
      <div className={styles.grid}>
        <div />
        {PHASES.map((phase) => (
          <div key={phase} className={styles.heading}>
            Phase {phase}
          </div>
        ))}
        {AREAS.map((area) => (
          <div key={area} className={styles.row}>
            <div className={styles.heading}>{AREA_NAMES[area]}</div>
            {PHASES.map((phase) => (
              <div key={phase} className={styles.cell}>
                {plan.tasks
                  .filter((t) => t.area === area && t.phase === phase)
                  .map((task) => (
                    <a
                      key={task.number}
                      href={task.url}
                      className={`${styles.card} ${STATE_CLASS[task.state]}`}
                    >
                      <span className={styles.id}>{task.id}</span>
                      <span>{task.name}</span>
                      <span className={styles.meta}>
                        <span className={styles.state}>{task.state}</span>
                        {task.assignees.length > 0 && (
                          <span>@{task.assignees.join(", @")}</span>
                        )}
                      </span>
                    </a>
                  ))}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function PlanPage() {
  return (
    <main className={styles.main}>
      <h1>Plan</h1>
      <p className={styles.legend}>
        Done = issue closed · in progress = assigned · ready = all dependencies
        closed · blocked = otherwise. Read live from GitHub issues.
      </p>
      <Suspense fallback={<p>Reading the task issues…</p>}>
        <Swimlane />
      </Suspense>
    </main>
  );
}
