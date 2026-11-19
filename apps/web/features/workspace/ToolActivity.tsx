import type { Inspection, Run, Permission } from '@/lib/api/types';
export function ToolActivity({
  run,
  inspection,
  onTask,
  permissions = [],
  taskId,
}: {
  permissions?: Permission[];
  taskId?: string | null;
  run?: Run;
  inspection: Inspection | null;
  onTask: (id: string) => void;
}) {
  const attempts =
    run?.workflow?.attempts
      ?.filter((a) => a.task_id === taskId)
      .map((a) => a.id) || [];
  const matches = (attempt: string) => !taskId || attempts.includes(attempt);
  const results = (run?.workflow?.command_results || []).filter((r) =>
    matches(r.request.attempt_id),
  );
  return (
    <div>
      <h3>Tool / command activity</h3>
      <p className="warning">
        Trusted local execution: approved commands can access anything the local
        OS account can access. Filesystem checks are application safeguards, not
        an OS sandbox. Denied backend policy cannot be overridden here.
      </p>
      {taskId && (
        <p>Task filter: {taskId}. Open the task history to change selection.</p>
      )}
      <h4>Exact runtime permission grants</h4>
      {permissions
        .filter((p) => matches(p.request.attempt_id))
        .map((p) => (
          <details key={p.id}>
            <summary>
              {p.request.actor} · {p.request.profile} · {p.status}
            </summary>
            <p>
              Decision: {p.reason || 'Pending human decision'} · Approval {p.id}
            </p>
            <p>
              Scope {p.request.cwd} · Workspace {p.request.workspace_version} ·
              Digest {p.scope_digest}
            </p>
            <p>
              <code>{[p.request.executable, ...p.request.args].join(' ')}</code>
            </p>
            <p>
              Configured capability and this one-operation grant are separate.
              Consumed permission cannot be reused.
            </p>
          </details>
        ))}
      <h4>Runtime requests and decisions</h4>
      {inspection?.tools
        .filter((t) => matches(t.attempt_id))
        .map((t) => (
          <p key={t.id}>
            <code>{t.id}</code> · {t.actor} · {t.operation || t.action} ·{' '}
            {t.outcome} · {t.path || t.reason} · Attempt {t.attempt_id}
          </p>
        ))}
      <h4>Retained execution boundaries</h4>
      {inspection?.operations
        .filter(
          (o) =>
            o.kind !== 'provider' &&
            (!taskId || o.checkpoint.task_id === taskId),
        )
        .map((o) => (
          <details key={o.id}>
            <summary>
              {o.kind}: {o.operation} · {o.certainty.toUpperCase()} · {o.stage}
            </summary>
            <p>
              {o.id} · {o.path}
            </p>
            <p>
              Start: {o.started_at} · Last receipt: {o.updated_at}
            </p>
            <p>
              Approval: {o.approval_id || 'No command approval'} · Scope:{' '}
              {o.request?.cwd || o.path || 'Unavailable'}
            </p>
            {o.checkpoint.task_id && (
              <button onClick={() => onTask(o.checkpoint.task_id!)}>
                Open task {o.checkpoint.task_id}
              </button>
            )}
          </details>
        ))}
      <h4>Command / test logs</h4>
      {results.length === 0 && <p>No completed command receipts.</p>}
      {results.map((r) => (
        <details key={r.id}>
          <summary>
            Command evidence {r.id} · {r.outcome} ·{' '}
            {r.is_test ? 'test' : 'not a test'}
          </summary>
          <p>
            Agent: {r.request.actor} · Attempt {r.request.attempt_id} · Approval{' '}
            {r.approval_id}
          </p>
          <p>
            <code>{[r.request.executable, ...r.request.args].join(' ')}</code>
          </p>
          <p>
            Scope {r.request.cwd} · Workspace {r.request.workspace_version}
          </p>
          <p>
            Start {r.started_at} · Duration {r.duration_seconds}s · Exit{' '}
            {r.exit_code ?? 'Unavailable'} · Cleanup{' '}
            {r.cleanup_complete ? 'complete' : 'INCOMPLETE'}
          </p>
          <p>
            End (derived from start and recorded duration):{' '}
            {Number.isFinite(Date.parse(r.started_at))
              ? new Date(
                  Date.parse(r.started_at) + r.duration_seconds * 1000,
                ).toISOString()
              : 'Unavailable'}
          </p>
          <p>Timeout / cancellation status: {r.outcome}</p>
          <h5>stdout {r.stdout_truncated && '(truncated)'}</h5>
          <pre>{r.stdout || '(empty)'}</pre>
          <h5>stderr {r.stderr_truncated && '(truncated)'}</h5>
          <pre>{r.stderr || '(empty)'}</pre>
          <p>Historical receipt; not proof of current workspace state.</p>
        </details>
      ))}
    </div>
  );
}
