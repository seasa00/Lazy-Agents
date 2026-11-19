import type { Action, Command, Run } from '@/lib/api/types';
import type { PendingCommand } from '@/lib/state/reducer';
export function RunControls({
  run,
  pending,
  command,
}: {
  run: Run | undefined;
  pending: PendingCommand[];
  command: (action: Action, extra?: Partial<Command>) => Promise<void>;
}) {
  const busy = pending.some(
    (c) => c.status === 'sending' || c.status === 'uncertain',
  );
  const pausePending =
    pending.some((c) => c.action === 'pause') ||
    run?.status === 'pause_requested';
  const recovery = run?.workflow?.recovery;
  const unresolved = recovery?.issues.some((i) => !i.resolved);
  const terminal =
    run && ['completed', 'failed', 'canceled'].includes(run.status);
  return (
    <section className="panel controls">
      <h2>Run controls</h2>
      <div className="actions">
        {(!run || terminal) && (
          <button
            className="primary"
            disabled={busy}
            onClick={() => void command('plan')}
          >
            Request Manager planning
          </button>
        )}
        {run?.status === 'awaiting_approval' && (
          <button
            className="primary"
            disabled={busy}
            onClick={() => void command('approve')}
          >
            Approve plan
          </button>
        )}
        {run?.status === 'running' && (
          <>
            <button
              disabled={
                busy ||
                Boolean(run.workflow?.pending) ||
                Boolean(run.workflow?.pending_permissions.length) ||
                Boolean(recovery?.requires_resume)
              }
              onClick={() => void command('start')}
            >
              Start / Continue execution
            </button>
            <button
              disabled={busy || pausePending}
              onClick={() => void command('pause')}
            >
              Pause
            </button>
          </>
        )}
        {(run?.status === 'paused' || recovery?.requires_resume) &&
          !terminal && (
            <button
              className="primary"
              disabled={busy || Boolean(unresolved)}
              onClick={() =>
                void command(
                  'resume',
                  recovery ? { expected_epoch: recovery.epoch } : {},
                )
              }
            >
              Resume
            </button>
          )}
        {run && !terminal && (
          <button
            className="danger"
            disabled={busy}
            onClick={() => void command('cancel')}
          >
            Cancel / Stop run
          </button>
        )}
      </div>
      {pausePending && run?.status !== 'paused' && (
        <p role="status" className="warning">
          Pause requested — waiting for the backend safe boundary.
        </p>
      )}
      {pending
        .filter((p) => p.action !== 'pause')
        .map((p) => (
          <p role="status" key={p.key}>
            {p.action}:{' '}
            {p.status === 'uncertain'
              ? 'Outcome unknown'
              : p.status === 'sending'
                ? 'Sending command'
                : 'Command pending'}
          </p>
        ))}
      <p className="muted">
        Instruction submission and plan editing are unavailable in the current
        HTTP API.
      </p>
      {run?.status === 'running' && !run.workflow?.pending && (
        <p className="muted">
          After plan approval or a permission decision, use Start / Continue
          execution.
        </p>
      )}
    </section>
  );
}
