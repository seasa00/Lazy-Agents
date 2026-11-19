'use client';
import { useState } from 'react';
import type {
  Action,
  Command,
  Recovery,
  RecoveryInspection,
} from '@/lib/api/types';
export function RecoveryPanel({
  inspection,
  recovery,
  command,
  busy,
}: {
  inspection?: RecoveryInspection;
  recovery?: Recovery | null;
  command: (action: Action, body?: Partial<Command>) => Promise<void>;
  busy: boolean;
}) {
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [quiet, setQuiet] = useState<Record<string, boolean>>({});
  const gate = inspection?.recovery || recovery;
  return (
    <div>
      <h3>Recovery inspection</h3>
      {!gate?.requires_resume ? (
        <p>
          No active recovery gate. Retained execution evidence remains available
          under Tool activity.
        </p>
      ) : (
        <>
          <p className="warning">
            Run interrupted · phase{' '}
            {inspection?.checkpoint?.phase ||
              inspection?.phase ||
              'Unavailable'}{' '}
            · resume phase{' '}
            {('resume_phase' in gate && String(gate.resume_phase)) ||
              'Unavailable'}
            . Execution will not resume automatically.
          </p>
          {gate.issues.map((issue) => {
            const op = inspection?.operations.find((o) => o.id === issue.id);
            return (
              <article className="attempt" key={issue.id}>
                <h4>
                  {issue.kind || 'Operation'} ·{' '}
                  {(issue.certainty || 'Unavailable').toUpperCase()}
                </h4>
                <p>
                  Operation: <code>{issue.id}</code> ·{' '}
                  {op?.operation || 'Unavailable'} · Task{' '}
                  {op?.checkpoint.task_id || 'None known'}
                </p>
                <p>{issue.reason}</p>
                {issue.resolved ? (
                  <p className="badge">
                    Resolved: {issue.resolution || 'Acknowledged'}. Uncertain
                    outcomes remain uncertain.
                  </p>
                ) : (
                  <>
                    <details>
                      <summary>Inspect retained evidence</summary>
                      <p>
                        Stage {op?.stage || 'Unavailable'} · Certainty{' '}
                        {op?.certainty || issue.certainty || 'Unavailable'} ·
                        Path {op?.path || 'Unavailable'}
                      </p>
                      <p>
                        Start {op?.started_at || 'Unavailable'} · Receipt{' '}
                        {op?.updated_at || 'Unavailable'}
                      </p>
                      <p>
                        {op?.call_record
                          ? `${op.call_record.model} · ${op.call_record.status} · ${op.call_record.usage ? 'Usage retained' : 'Usage / billing unavailable'}`
                          : 'No provider receipt'}
                      </p>
                    </details>
                    <label>
                      Recovery reason
                      <input
                        aria-label={`Recovery reason ${issue.id}`}
                        value={reasons[issue.id] || ''}
                        maxLength={4000}
                        onChange={(e) =>
                          setReasons({ ...reasons, [issue.id]: e.target.value })
                        }
                      />
                    </label>
                    {inspection?.available_actions[issue.id]?.some(
                      (a) => a.requires_quiescent,
                    ) && (
                      <label>
                        <input
                          type="checkbox"
                          checked={quiet[issue.id] || false}
                          onChange={(e) =>
                            setQuiet({ ...quiet, [issue.id]: e.target.checked })
                          }
                        />
                        I have independently confirmed the affected local
                        operation is quiescent.
                      </label>
                    )}
                    <div className="actions">
                      {inspection?.available_actions[issue.id]?.map((a) => (
                        <button
                          key={a.action}
                          disabled={
                            busy ||
                            !reasons[issue.id]?.trim() ||
                            (a.requires_quiescent && !quiet[issue.id])
                          }
                          onClick={() =>
                            void command('recovery', {
                              operation_id: issue.id,
                              action: a.action,
                              reason: reasons[issue.id].trim(),
                              expected_epoch: gate.epoch,
                              quiescent: quiet[issue.id] || false,
                            })
                          }
                        >
                          {a.label}
                        </button>
                      ))}
                    </div>
                    {inspection &&
                      !inspection.available_actions[issue.id]?.length && (
                        <p>
                          No browser-supported resolution for this issue;
                          inspect backend recovery tooling.
                        </p>
                      )}
                  </>
                )}
              </article>
            );
          })}
          <button
            disabled={busy || gate.issues.some((i) => !i.resolved)}
            onClick={() =>
              void command('resume', { expected_epoch: gate.epoch })
            }
          >
            Resume when safe
          </button>
          <p>
            Resolve acknowledges a safe recovery boundary; it does not prove
            that an uncertain command never ran or was not billed.
          </p>
        </>
      )}
    </div>
  );
}
