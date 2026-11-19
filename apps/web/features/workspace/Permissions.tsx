'use client';
import { useState } from 'react';
import type { Action, Command, Permission } from '@/lib/api/types';
export function Permissions({
  permissions,
  pendingIds,
  busy,
  command,
}: {
  permissions: Permission[];
  pendingIds: string[];
  busy: boolean;
  command: (action: Action, extra?: Partial<Command>) => Promise<void>;
}) {
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const requests = permissions.filter(
    (p) => p.status === 'pending' && pendingIds.includes(p.id),
  );
  const denied = permissions.filter((p) => p.status === 'denied');
  if (!requests.length && !denied.length) return null;
  return (
    <section className="panel permissions">
      <h2>Permissions</h2>
      {requests.map((p) => (
        <article key={p.id} className="permission">
          <h3>Permission required: {p.request.profile}</h3>
          <p>
            Requested by {p.request.actor} for attempt{' '}
            <code>{p.request.attempt_id}</code>
          </p>
          <dl>
            <dt>Command</dt>
            <dd>
              <code>{[p.request.executable, ...p.request.args].join(' ')}</code>
            </dd>
            <dt>Scope / working directory</dt>
            <dd>{p.request.cwd}</dd>
            <dt>Workspace version</dt>
            <dd>
              <code>{p.request.workspace_version}</code>
            </dd>
            <dt>Scope digest</dt>
            <dd>
              <code>{p.scope_digest}</code>
            </dd>
            <dt>Limits</dt>
            <dd>
              {p.request.timeout_seconds}s · {p.request.max_output_bytes} output
              bytes
            </dd>
          </dl>
          <label>
            Decision reason
            <input
              aria-label={`Decision reason ${p.id}`}
              required
              maxLength={1000}
              value={reasons[p.id] || ''}
              onChange={(e) =>
                setReasons({ ...reasons, [p.id]: e.target.value })
              }
            />
          </label>
          <div className="actions">
            <button
              disabled={busy || !reasons[p.id]?.trim()}
              onClick={() =>
                void command('permission', {
                  approval_id: p.id,
                  approved: true,
                  reason: reasons[p.id].trim(),
                })
              }
            >
              Approve permission
            </button>
            <button
              disabled={busy || !reasons[p.id]?.trim()}
              onClick={() =>
                void command('permission', {
                  approval_id: p.id,
                  approved: false,
                  reason: reasons[p.id].trim(),
                })
              }
            >
              Deny permission
            </button>
          </div>
        </article>
      ))}
      {denied.map((p) => (
        <p key={p.id} role="status" className="warning">
          Permission denied: {p.request.profile}. {p.reason}
        </p>
      ))}
    </section>
  );
}
