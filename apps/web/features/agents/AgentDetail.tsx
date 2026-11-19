import type {
  AgentKind,
  Run,
  Usage,
  DomainEvent,
  Inspection,
} from '@/lib/api/types';
import { UsageNumbers } from '../usage/UsagePanel';
export function AgentDetail({
  kind,
  run,
  usage,
  events,
  onTask,
  capabilities,
}: {
  capabilities?: NonNullable<Inspection['capabilities']>[AgentKind];
  kind: AgentKind;
  run?: Run;
  usage?: Usage;
  events: DomainEvent[];
  onTask: (id: string) => void;
}) {
  const agent = run?.workflow?.agent_snapshots
    .filter((a) => a.kind === kind)
    .at(-1);
  const invocations =
    run?.workflow?.invocation_records?.filter(
      (i) => i.agent_id === (agent?.agent_id || kind),
    ) || [];
  const calls =
    run?.workflow?.call_records?.filter((c) =>
      invocations.some((i) => i.id === c.invocation_id),
    ) || [];
  const activeKind =
    run?.phase === 'develop'
      ? 'developer'
      : run?.phase === 'review'
        ? 'reviewer'
        : 'manager';
  const activity = events.filter(
    (e) =>
      e.run_id === run?.id &&
      (e.payload.actor === kind ||
        e.payload.agent_id === kind ||
        invocations.some((i) => i.id === e.payload.operation_id) ||
        e.payload.phase ===
          { manager: 'plan', developer: 'develop', reviewer: 'review' }[kind]),
  );
  return (
    <article aria-label={`${kind} details`}>
      <h3>{agent?.name || kind} details</h3>
      <dl>
        <dt>Agent kind</dt>
        <dd>{kind}</dd>
        <dt>Role</dt>
        <dd>{agent?.role || 'Unavailable'}</dd>
        <dt>Model · captured run configuration</dt>
        <dd>{agent?.model || 'Unavailable'}</dd>
        <dt>Current status</dt>
        <dd>
          {run
            ? `${run.status.replaceAll('_', ' ')} · ${kind === activeKind && run.workflow?.pending ? 'Invocation pending' : 'No pending invocation'}`
            : 'Not started'}
        </dd>
        <dt>Current task</dt>
        <dd>
          {kind === activeKind && run?.current_task_id ? (
            <button onClick={() => onTask(run.current_task_id!)}>
              {run.current_task_id}
            </button>
          ) : (
            'None known'
          )}
        </dd>
        <dt>Configured tools</dt>
        <dd>{agent?.tools?.join(', ') || 'None configured'}</dd>
        <dt>Configured permission capabilities</dt>
        <dd>{agent?.permissions?.join(', ') || 'None configured'}</dd>
      </dl>
      <p>
        Configured capability does not grant a runtime operation. Exact requests
        and backend decisions appear under Tool activity and Permissions.
        Trusted fixture tool execution is backend-owned.
      </p>
      <h4>Effective backend workspace permissions</h4>
      {capabilities ? (
        <ul>
          {Object.entries(capabilities.files).map(([operation, decision]) => (
            <li key={operation}>
              {operation}:{' '}
              {decision.allowed ? 'Allowed by role policy' : 'Denied'} —{' '}
              {decision.reason}
            </li>
          ))}
          <li>
            Command request:{' '}
            {capabilities.command_request.allowed
              ? 'Allowed to request exact approval'
              : 'Denied'}{' '}
            — {capabilities.command_request.reason}
          </li>
        </ul>
      ) : (
        <p>
          Unavailable: no bound workspace gateway in this backend session.
          Configured capabilities above do not imply a runtime grant.
        </p>
      )}
      <UsageNumbers value={usage?.per_agent[agent?.agent_id || kind]} />
      <h4>Recent invocations</h4>
      {invocations.length === 0 && <p>No invocations recorded.</p>}
      {invocations
        .slice(-20)
        .reverse()
        .map((i) => (
          <details key={i.id}>
            <summary>
              {i.phase} · {i.id}
            </summary>
            <p>
              Configuration digest: <code>{i.config_digest}</code> · Generation{' '}
              {i.generation}
            </p>
            {calls
              .filter((c) => c.invocation_id === i.id)
              .map((c) => (
                <p key={c.call_id}>
                  {c.model} · {c.status} · Technical attempt {c.attempt}
                  {c.error_type && (
                    <strong> · TECHNICAL ERROR: {c.error_type}</strong>
                  )}{' '}
                  · Input {c.usage?.input_tokens ?? 'Unavailable'} / Output{' '}
                  {c.usage?.output_tokens ?? 'Unavailable'}
                </p>
              ))}
          </details>
        ))}
      <h4>Structured messages / handoffs</h4>
      {kind === 'manager' && run?.plan && <p>Plan: {run.plan.summary}</p>}
      {kind === 'developer' &&
        run?.workflow?.submissions?.map((s) => (
          <p key={s.id}>
            <button onClick={() => onTask(s.task_id)}>
              {s.task_id} · submission v{s.version}
            </button>{' '}
            {s.output.summary}
          </p>
        ))}
      {kind === 'reviewer' &&
        run?.workflow?.reviews.map((r) => (
          <p key={r.result.review_id}>
            <button onClick={() => onTask(r.task_id)}>
              {r.task_id} · {r.submission_id}
            </button>{' '}
            {r.result.verdict}: {r.result.summary}
          </p>
        ))}
      <h4>Recent committed activity</h4>
      <ul>
        {activity.slice(-12).map((e) => (
          <li key={e.sequence}>
            {e.type} · {e.occurred_at || `Event ${e.sequence}`}
          </li>
        ))}
      </ul>
      <p className="muted">
        Only structured summaries and retained receipts are shown. No private
        reasoning is requested.
      </p>
    </article>
  );
}
