'use client';
import { useRef, useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { APIError, createProject } from '@/lib/api/client';
import type { CreateProject as Body } from '@/lib/api/types';
interface Row {
  description: string;
  criteria: string;
}
export function CreateProject() {
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>([{ description: '', criteria: '' }]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const retry = useRef<{ body: Body; key: string } | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    const body: Body = {
      name: String(form.get('name')).trim(),
      goal: String(form.get('goal')).trim(),
      requirements: rows.map((row, i) => ({
        id: `req-${i + 1}`,
        description: row.description.trim(),
        acceptance_criteria: row.criteria
          .split('\n')
          .map((x) => x.trim())
          .filter(Boolean),
        priority: 'normal',
      })),
    };
    if (
      !body.name ||
      !body.goal ||
      body.requirements.some(
        (r) => !r.description || !r.acceptance_criteria.length,
      )
    ) {
      setError(
        'Enter a name, goal, and at least one acceptance criterion for every requirement.',
      );
      return;
    }
    const job = retry.current || { body, key: crypto.randomUUID() };
    setBusy(true);
    setError(null);
    try {
      const ack = await createProject(job.body, job.key);
      retry.current = null;
      router.push(`/projects/${encodeURIComponent(ack.project_id)}`);
    } catch (error) {
      if (error instanceof APIError && error.uncertain) retry.current = job;
      else retry.current = null;
      setError(
        error instanceof Error ? error.message : 'Project creation failed.',
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="narrow">
      <Link href="/">← Projects</Link>
      <h1>Create project</h1>
      <p>
        Define the goal and the criteria the Manager and Reviewer should use.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <form onSubmit={submit}>
        <fieldset disabled={busy || Boolean(retry.current)}>
          <label>
            Project name
            <input name="name" required maxLength={200} />
          </label>
          <label>
            Goal
            <textarea name="goal" required maxLength={16000} rows={4} />
          </label>
          <label>
            Workspace
            <select aria-label="Workspace" disabled>
              <option>Configured by backend</option>
            </select>
          </label>
          <p className="muted">
            This API configures workspaces on the backend. Browser selection is
            unavailable. The default backend uses synthetic evidence; a
            workspace fixture uses a disposable folder.
          </p>
          <h2>Requirements</h2>
          {rows.map((row, index) => (
            <section className="requirement" key={index}>
              <h3>Requirement {index + 1}</h3>
              <label>
                Description
                <input
                  aria-label={`Requirement ${index + 1} description`}
                  required
                  maxLength={4000}
                  value={row.description}
                  onChange={(e) =>
                    setRows(
                      rows.map((r, i) =>
                        i === index ? { ...r, description: e.target.value } : r,
                      ),
                    )
                  }
                />
              </label>
              <label>
                Acceptance criteria <span className="muted">one per line</span>
                <textarea
                  aria-label={`Requirement ${index + 1} acceptance criteria`}
                  required
                  rows={3}
                  value={row.criteria}
                  onChange={(e) =>
                    setRows(
                      rows.map((r, i) =>
                        i === index ? { ...r, criteria: e.target.value } : r,
                      ),
                    )
                  }
                />
              </label>
              {rows.length > 1 && (
                <button
                  type="button"
                  onClick={() => setRows(rows.filter((_, i) => i !== index))}
                >
                  Remove requirement {index + 1}
                </button>
              )}
            </section>
          ))}
          <button
            type="button"
            disabled={rows.length >= 100}
            onClick={() =>
              setRows([...rows, { description: '', criteria: '' }])
            }
          >
            Add requirement
          </button>
        </fieldset>
        <button className="primary" disabled={busy} type="submit">
          {busy
            ? 'Creating project…'
            : retry.current
              ? 'Retry same creation command'
              : 'Create project'}
        </button>
        {retry.current && (
          <p role="status">
            Creation outcome is unknown. Retry uses the same idempotency key and
            original fields.
          </p>
        )}
      </form>
    </main>
  );
}
