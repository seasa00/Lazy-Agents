'use client';
import Link from 'next/link';
import { useState } from 'react';
import type { Inspection } from '@/lib/api/types';
import {
  OfficeScene,
  useOfficeTheme,
  type OfficeNavigation,
} from '../office/OfficeScene';
import { apiBase, projectPath } from '@/lib/api/types';
import { ProjectProvider, useProject } from '@/lib/state/context';
import { TaskBoard } from './TaskBoard';
import { ActivityFeed } from './ActivityFeed';
import { RunControls } from './RunControls';
import { Permissions } from './Permissions';
import { InspectionPanel } from './Inspection';
import OfficeExperience from '../office-pixel/OfficeExperience';
export function WorkspaceView() {
  const { state, permissions, command, refresh, retry, select } = useProject();
  const [theme, setTheme] = useOfficeTheme();
  const [navigation, setNavigation] = useState<OfficeNavigation>();
  const [inspection, setInspection] = useState<Inspection>();
  const navigate = (view: string, agent?: OfficeNavigation['agent']) => {
    setNavigation((old) => ({ view, agent, nonce: (old?.nonce || 0) + 1 }));
    document.getElementById('inspection')?.focus();
    document.getElementById('inspection')?.scrollIntoView({ block: 'start' });
  };
  const openTask = (id: string) => {
    select(id);
    navigate('Task history');
  };
  const project = state.snapshot?.project;
  const run =
    project?.runs.find((r) => r.id === project.active_run_id) ||
    project?.runs.at(-1);
  const pending = Object.values(state.pending);
  const uncertain = pending.some((p) => p.status === 'uncertain');
  const final = run?.workflow?.final_result;
  const recovery = run?.workflow?.recovery;
  return (
    <main className="office-workspace" data-office-theme={theme}>
      <Link href="/">← Projects</Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">PROJECT WORKSPACE</p>
          <h1>{project?.name || 'Opening project…'}</h1>
        </div>
        <div aria-live="polite">
          <span
            className={`connection ${state.connection}`}
            data-testid="connection"
          >
            {state.connection === 'connected'
              ? 'Live events connected'
              : state.connection === 'resetting'
                ? 'Snapshot reset required — reloading'
                : state.connection === 'disconnected'
                  ? 'SSE disconnected — reconnecting'
                  : 'Connecting to backend'}
          </span>
          <p className="muted">Event cursor: {state.cursor}</p>
        </div>
      </div>
      {state.streamError && (
        <p role="status" className="warning">
          {state.streamError}
        </p>
      )}
      {state.error && (
        <div role="alert" className="error">
          {state.error}{' '}
          <button onClick={() => void refresh().catch(() => {})}>
            Refresh authoritative state
          </button>
        </div>
      )}
      {uncertain && (
        <div role="alert" className="warning">
          Command outcome is unknown. Retrying uses the original command and
          idempotency key.{' '}
          <button onClick={() => void retry()}>Retry same command</button>
        </div>
      )}
      {!project ? (
        <p role="status">Waiting for an authoritative backend snapshot.</p>
      ) : (
        <>
          <nav className="office-nav" aria-label="Workspace navigation">
            <Link
              className="office-brand"
              href="/"
              aria-label="Lazy Agents projects"
            >
              <span className="brand-office" aria-hidden="true">
                ▥
              </span>
              <span>
                <strong>Lazy Agents</strong>
                <small>Your AI team, always on.</small>
              </span>
            </Link>
            <a href="#office-pixel-workspace">
              <span aria-hidden="true">⌂</span> Office
            </a>
            <a href="#tasks">
              <span aria-hidden="true">▤</span> Tasks{' '}
              <span className="nav-count">{project.tasks.length}</span>
            </a>
            <a href="#activity">
              <span aria-hidden="true">≡</span> Activity
            </a>
            {['Agents', 'Usage', 'Settings', 'Recovery'].map((view) => (
              <button
                key={view}
                aria-label={`Open ${view} view`}
                onClick={() => navigate(view)}
              >
                <span aria-hidden="true">
                  {
                    { Agents: '♙', Usage: '▥', Settings: '⚙', Recovery: '⟳' }[
                      view
                    ]
                  }
                </span>{' '}
                {view}
              </button>
            ))}
            <button onClick={() => navigate('Task history')}>
              <span aria-hidden="true">▧</span> Evidence & reviews
            </button>
          </nav>
          <section
            id="office-pixel-workspace"
            className="office-pixel-workspace"
            aria-label="Office Pixel"
          >
            <div className="office-pixel-workspace-frame">
              <OfficeExperience projectId={project.id} runId={run?.id} cursor={state.cursor} connection={state.connection} runState={run ? `${run.status}:${run.phase}:${run.current_task_id}` : undefined} />
            </div>
          </section>
          <details className="legacy-office">
            <summary>Previous Office view</summary>
            <OfficeScene
              project={project}
              run={run}
              events={state.liveEvents || []}
              connection={state.connection}
              theme={theme}
              onTheme={setTheme}
              onAgent={(kind) => navigate('Agents', kind)}
              onTask={openTask}
              onUsage={() => navigate('Usage')}
              usage={inspection?.project_usage}
              onEvent={(event) => {
                const item = document.getElementById(`event-${event.sequence}`);
                item?.focus();
                item?.scrollIntoView({ block: 'center' });
              }}
            />
          </details>
          <div className="run-overview">
            <RunControls run={run} pending={pending} command={command} />
            <section className="panel current-run">
              <h2>Current run</h2>
              <p>{project.goal}</p>
              {run && <p className="muted current-run-id">{run.id}</p>}
              <p>
                Run status:{' '}
                <strong data-testid="run-status">
                  {run?.status.replaceAll('_', ' ') || 'No run'}
                </strong>
                {run && <span className="muted"> · Phase: {run.phase}</span>}
              </p>
              {run && (
                <div className="run-progress">
                  <progress
                    aria-label="Tasks complete"
                    value={
                      project.tasks.filter(
                        (t) =>
                          run.task_ids.includes(t.id) && t.status === 'done',
                      ).length
                    }
                    max={Math.max(run.task_ids.length, 1)}
                  />
                  <span>
                    {
                      project.tasks.filter(
                        (t) =>
                          run.task_ids.includes(t.id) && t.status === 'done',
                      ).length
                    }
                    /{run.task_ids.length} tasks
                  </span>
                </div>
              )}
              <details>
                <summary>Project requirements</summary>
                <p>
                  Workspace:{' '}
                  <code>
                    {project.workspace_root ||
                      'Backend synthetic evidence (no disk workspace)'}
                  </code>
                </p>
                <ul>
                  {project.requirements.map((r) => (
                    <li key={r.id}>
                      <strong>{r.description}</strong>
                      <ul>
                        {r.acceptance_criteria.map((c) => (
                          <li key={c}>{c}</li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              </details>
            </section>
          </div>
          {run?.workflow?.blocked_reason && (
            <section role="alert" className="warning">
              <h2>Run blocked / input required</h2>
              <p>{run.workflow.blocked_reason}</p>
              <p>
                {recovery?.requires_resume
                  ? 'Inspect the Recovery view below for supported reconciliation actions.'
                  : 'This API exposes the blocker. Arbitrary input and blocker resolution are not exposed yet.'}
              </p>
            </section>
          )}
          {recovery?.requires_resume && (
            <section role="alert" className="warning">
              <h2>Recovery required</h2>
              <p>
                Execution is gated after restart. Explicit resume is available
                after all issues are resolved.
              </p>
              <ul>
                {recovery.issues
                  .filter((i) => !i.resolved)
                  .map((issue, index) => (
                    <li key={issue.id || index}>{issue.reason}</li>
                  ))}
              </ul>
              <p>
                Inspect the Recovery view below to reconcile retained evidence,
                resolve supported issues and resume explicitly.
              </p>
            </section>
          )}

          {run?.plan && (
            <section className="panel manager-plan">
              <details
                open={
                  run.status === 'awaiting_approval' ||
                  run.status === 'planning'
                }
              >
                <summary>
                  <h2>Manager plan</h2>
                </summary>
                <p>{run.plan.summary}</p>
                <h3>Tasks and dependencies</h3>
                <ul>
                  {run.plan.tasks.map((task) => (
                    <li key={task.id}>
                      <strong>
                        {task.id}: {task.title}
                      </strong>
                      <p>{task.description}</p>
                      <p>
                        Dependencies: {task.dependencies.join(', ') || 'None'} ·
                        Assignee: {task.assignee}
                      </p>
                      <ul>
                        {task.acceptance_criteria.map((c) => (
                          <li key={c}>{c}</li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
                {run.plan.assumptions.length > 0 && (
                  <>
                    <h3>Assumptions</h3>
                    <ul>
                      {run.plan.assumptions.map((a) => (
                        <li key={a}>{a}</li>
                      ))}
                    </ul>
                  </>
                )}
              </details>
            </section>
          )}
          <Permissions
            permissions={permissions}
            pendingIds={run?.workflow?.pending_permissions || []}
            busy={pending.some(
              (p) => p.status === 'sending' || p.status === 'uncertain',
            )}
            command={command}
          />
          <div className="dashboard-grid">
            <TaskBoard
              tasks={project.tasks.filter(
                (t) => !run || run.task_ids.includes(t.id),
              )}
              reviews={run?.workflow?.reviews || []}
              selected={state.selectedTask}
              onSelect={openTask}
            />
            <ActivityFeed events={state.events} />
          </div>
          <InspectionPanel
            project={project}
            run={run}
            selected={state.selectedTask}
            events={state.events}
            cursor={state.cursor}
            navigation={navigation}
            onCurrentInspection={setInspection}
          />
          {run?.status === 'completed' && final && (
            <section className="panel final">
              <h2>Final result</h2>
              <p>{final.summary}</p>
              <h3>Completed tasks</h3>
              <ul>
                {final.completed_task_ids.map((id) => (
                  <li key={id}>{id}</li>
                ))}
              </ul>
              {final.limitations.length > 0 && (
                <>
                  <h3>Known limitations</h3>
                  <ul>
                    {final.limitations.map((l) => (
                      <li key={l}>{l}</li>
                    ))}
                  </ul>
                </>
              )}
              <h3>Evidence references</h3>
              <ul>
                {final.evidence_refs.map((ref) => (
                  <li key={ref}>
                    <code>{ref}</code>
                  </li>
                ))}
              </ul>
              <a
                href={`${apiBase}${projectPath(project.id)}/runs/${encodeURIComponent(run.id)}/evidence`}
                target="_blank"
                rel="noreferrer"
              >
                Open backend evidence JSON
              </a>
            </section>
          )}
        </>
      )}
    </main>
  );
}
export function Workspace({ id }: { id: string }) {
  return (
    <ProjectProvider key={id} id={id}>
      <WorkspaceView />
    </ProjectProvider>
  );
}
