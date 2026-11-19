import type { Usage, UsageTotals } from '@/lib/api/types';
export const cost = (value: string | null | undefined) =>
  value == null ? 'Unavailable / Incomplete' : `$${value} estimated USD`;
const count = (value: number | null | undefined) =>
  value == null ? 'Unavailable / Incomplete' : value.toLocaleString();
export function UsageNumbers({ value }: { value?: UsageTotals }) {
  return (
    <dl className="metrics">
      <dt>Provider calls</dt>
      <dd>{count(value?.provider_calls)}</dd>
      <dt>Input tokens</dt>
      <dd>{count(value?.input_tokens)}</dd>
      <dt>Output tokens</dt>
      <dd>{count(value?.output_tokens)}</dd>
      <dt>Cached input tokens (included in input)</dt>
      <dd>{count(value?.cached_input_tokens)}</dd>
      <dt>Total tokens</dt>
      <dd>{count(value?.total_tokens)}</dd>
      <dt>Estimated cost</dt>
      <dd>{cost(value?.estimated_cost)}</dd>
      <dt>Technical retries</dt>
      <dd>{count(value?.retries)}</dd>
    </dl>
  );
}
export function UsagePanel({ run, project }: { run: Usage; project: Usage }) {
  return (
    <div>
      <h3>Durable usage</h3>
      <p>
        Backend accounting, including failed calls and technical retries.
        Estimates use retained price snapshots; unknown billing is incomplete.
        Review rounds are separate from technical retries.
      </p>
      <h4>Current / latest run</h4>
      <UsageNumbers value={run} />
      <p>Review rounds: {run.reviews}</p>
      <h4>Per agent · current run</h4>
      <div className="agents">
        {['manager', 'developer', 'reviewer'].map((kind) => (
          <article key={kind}>
            <h5>{kind[0].toUpperCase() + kind.slice(1)} usage</h5>
            <UsageNumbers value={run.per_agent[kind]} />
          </article>
        ))}
      </div>
      <details>
        <summary>All runs · project total</summary>
        <UsageNumbers value={project} />
        <p>Review rounds: {project.reviews}</p>
      </details>
      <p className="muted">
        Per-task attribution is unavailable in the current accounting contract.
      </p>
    </div>
  );
}
