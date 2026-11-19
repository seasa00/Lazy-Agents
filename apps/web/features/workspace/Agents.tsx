import type { AgentKind, Run } from '@/lib/api/types';
const kinds: AgentKind[] = ['manager', 'developer', 'reviewer'];
export function Agents({ run }: { run: Run | undefined }) {
  const active =
    run?.phase === 'develop'
      ? 'developer'
      : run?.phase === 'review'
        ? 'reviewer'
        : 'manager';
  return (
    <section>
      <h2>Agents</h2>
      <div className="agents">
        {kinds.map((kind) => {
          const agent = run?.workflow?.agent_snapshots.find(
            (a) => a.kind === kind,
          );
          const status = !run
            ? 'Not started'
            : run.status === 'paused'
              ? 'Paused'
              : run.status === 'pause_requested'
                ? 'Pause requested'
                : run.workflow?.pending_permissions.length &&
                    kind === 'developer'
                  ? 'Awaiting permission'
                  : run.status === 'awaiting_approval' && kind === 'manager'
                    ? 'Awaiting plan approval'
                    : run.status === 'waiting_for_user'
                      ? 'Blocked'
                      : ['completed', 'failed', 'canceled'].includes(run.status)
                        ? run.status
                        : run.workflow?.pending && kind === active
                          ? 'Working'
                          : 'Idle';
          return (
            <article className="panel" key={kind}>
              <h3>{agent?.name || kind[0].toUpperCase() + kind.slice(1)}</h3>
              <p>
                {agent?.role ||
                  {
                    manager: 'Orchestrator',
                    developer: 'Software Developer',
                    reviewer: 'Quality Reviewer',
                  }[kind]}
              </p>
              <span className="badge">{status}</span>
              <p className="muted">
                Current task:{' '}
                {kind === active ? run?.current_task_id || 'None' : 'None'}
              </p>
            </article>
          );
        })}
      </div>
    </section>
  );
}
