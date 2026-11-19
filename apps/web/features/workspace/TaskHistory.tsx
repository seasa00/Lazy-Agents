'use client';
import { useState } from 'react';
import type { AgentKind, Project, Run, Operation } from '@/lib/api/types';
import { ArtifactViewer } from '../artifacts/ArtifactViewer';
export function TaskHistory({
  project,
  run,
  taskId,
  onTask,
  onAgent,
  onTools,
  onUsage,
  operations,
}: {
  operations: Operation[];
  project: Project;
  run?: Run;
  taskId: string | null;
  onTask: (id: string) => void;
  onAgent: (kind: AgentKind) => void;
  onTools: () => void;
  onUsage: () => void;
}) {
  const [file, setFile] = useState<{
    submission: string;
    path: string;
    stale: boolean;
  } | null>(null);
  const task = project.tasks.find(
    (t) => t.id === taskId && (!run || run.task_ids.includes(t.id)),
  );
  const wf = run?.workflow;
  const attempts = wf?.attempts?.filter((a) => a.task_id === taskId) || [];
  return (
    <div>
      <h3>Task / attempt / review history</h3>
      <div className="actions">
        {project.tasks
          .filter((t) => !run || run.task_ids.includes(t.id))
          .map((t) => (
            <button
              key={t.id}
              aria-pressed={taskId === t.id}
              onClick={() => {
                setFile(null);
                onTask(t.id);
              }}
            >
              {t.id}: {t.title}
            </button>
          ))}
      </div>
      {!task ? (
        <p>Select a task to inspect its evidence.</p>
      ) : (
        <>
          <h4>
            {task.title} · {task.status.toUpperCase()}
          </h4>
          {task.blocked_reason && (
            <p className="warning">BLOCKED: {task.blocked_reason}</p>
          )}
          <div className="actions">
            <button onClick={() => onAgent(task.assignee)}>
              Inspect assigned {task.assignee}
            </button>
            <button onClick={onTools}>Task tool activity</button>
            <button onClick={onUsage}>Task usage availability</button>
          </div>
          {attempts.length === 0 && <p>No attempt recorded yet.</p>}
          {attempts.map((a) => {
            const submissions =
              wf?.submissions?.filter((s) => s.attempt_id === a.id) || [];
            const latest = Math.max(
              ...attempts.map((attempt) => attempt.number),
            );
            return (
              <article key={a.id} className="attempt">
                <h4>
                  Attempt {a.number} · {a.id}
                </h4>
                <p>Generation {a.generation}</p>
                {submissions.length === 0 && (
                  <p>
                    No immutable submission retained. Inspect tool/provider
                    receipts for interrupted or technical failures.
                  </p>
                )}
                {submissions.map((s) => (
                  <details key={s.id} open>
                    <summary>
                      Submission v{s.version} · {s.id}
                    </summary>
                    <p>{s.output.summary}</p>
                    <p>
                      Evidence digest: <code>{s.digest}</code>
                    </p>
                    <h5>Changed files</h5>
                    <ul>
                      {s.output.changed_files.map((f) => (
                        <li key={f.path}>
                          {f.path} · {f.change_type}: {f.summary}
                        </li>
                      ))}
                    </ul>
                    <div className="actions">
                      {s.files?.files.map((f) => (
                        <button
                          key={f.path}
                          onClick={() =>
                            setFile({
                              submission: s.id,
                              path: f.path,
                              stale: a.number < latest,
                            })
                          }
                        >
                          Open diff / file {f.path} · attempt {a.number}
                        </button>
                      ))}
                    </div>
                    <h5>Test evidence</h5>
                    <ul>
                      {s.output.tests.map((t, i) => (
                        <li key={i}>
                          {t.name}: {t.status} — {t.summary}
                        </li>
                      ))}
                    </ul>
                    {s.files?.tests.map((t) => (
                      <details key={t.result.id}>
                        <summary>
                          Test / command evidence {t.result.id} ·{' '}
                          {t.stale ? 'STALE' : t.result.outcome}
                        </summary>
                        <p>
                          Exit {t.result.exit_code ?? 'Unavailable'} · Workspace{' '}
                          {t.workspace_version}
                        </p>
                        <pre>{t.result.stdout}</pre>
                        <pre>{t.result.stderr}</pre>
                      </details>
                    ))}
                    <h5>Reviewer assessments</h5>
                    {wf?.reviews
                      .filter(
                        (r) =>
                          r.submission_id === s.id &&
                          (r.submission_version == null ||
                            r.submission_version === s.version),
                      )
                      .map((r) => (
                        <article
                          key={r.result.review_id}
                          className={`review ${r.result.verdict.toLowerCase()}`}
                        >
                          <h5>
                            Reviewer {r.result.verdict} · round {r.number}
                          </h5>
                          <p>
                            Exact submission: {r.submission_id} · v
                            {r.submission_version ?? s.version}
                          </p>
                          <p>{r.result.summary}</p>
                          <ul>
                            {r.result.assessments?.map((c) => (
                              <li key={c.criterion_id}>
                                <strong>
                                  {c.criterion_id} ·{' '}
                                  {c.passed ? 'PASS' : 'FAIL'}
                                </strong>
                                : {c.evidence} {c.notes}
                              </li>
                            ))}
                          </ul>
                          <h6>Findings</h6>
                          <ul>
                            {r.result.findings?.map((f) => (
                              <li key={f.id}>
                                {f.severity}: {f.summary} — {f.evidence}
                              </li>
                            ))}
                          </ul>
                          <h6>Checks not performed</h6>
                          <ul>
                            {r.result.checks_not_performed?.map((c) => (
                              <li key={c}>{c}</li>
                            ))}
                          </ul>
                          <button onClick={() => onAgent('reviewer')}>
                            Inspect Reviewer for this task
                          </button>
                        </article>
                      ))}
                    {wf?.revisions
                      .filter((r) => r.submission_id === s.id)
                      .map((r) => (
                        <div key={r.review_id} className="warning">
                          <h5>Requested fixes → next attempt</h5>
                          <ul>
                            {r.required_fixes.map((f) => (
                              <li key={f}>{f}</li>
                            ))}
                          </ul>
                          <p>
                            Remaining review rounds: {r.remaining_review_rounds}
                          </p>
                        </div>
                      ))}
                  </details>
                ))}
              </article>
            );
          })}
          {wf?.call_records
            ?.filter(
              (c) =>
                c.error_type &&
                operations.some(
                  (o) =>
                    o.checkpoint.task_id === taskId &&
                    o.checkpoint.invocation_id === c.invocation_id,
                ),
            )
            .map((c) => (
              <p key={c.call_id} className="technical">
                TECHNICAL ERROR · {c.call_id}: {c.error_type}. No Reviewer
                verdict is implied.
              </p>
            ))}
        </>
      )}
      {file && run && (
        <ArtifactViewer
          key={`${file.submission}:${file.path}`}
          projectId={project.id}
          runId={run.id}
          submissionId={file.submission}
          path={file.path}
          stale={file.stale}
          close={() => setFile(null)}
        />
      )}
    </div>
  );
}
