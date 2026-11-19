'use client';
import { useEffect, useState } from 'react';
import { APIError, getSettings, saveSettings } from '@/lib/api/client';
import type {
  AgentConfiguration,
  Project,
  Settings,
  SettingsCommand,
} from '@/lib/api/types';
export function SettingsPanel({
  project,
  refresh,
}: {
  project: Project;
  refresh: () => Promise<void>;
}) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [kind, setKind] = useState('developer');
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [draft, setDraft] = useState<AgentConfiguration | null>(null);
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState<{
    body: SettingsCommand;
    key: string;
  } | null>(null);
  useEffect(() => {
    let live = true;
    void getSettings(project.id)
      .then((value) => {
        if (live)
          setSettings((previous) =>
            previous &&
            JSON.stringify(previous.agents) === JSON.stringify(value.agents)
              ? { ...value, agents: previous.agents }
              : value,
          );
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [project.id, project.version]);
  useEffect(() => {
    setDraft(settings?.agents.find((a) => a.kind === kind) || null);
  }, [kind, settings?.agents]);
  async function send(job: { body: SettingsCommand; key: string }) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await saveSettings(project.id, job.body, job.key);
      setRetry(null);
      setMessage(
        'Saved for future runs. Current and completed invocations retain their captured configuration.',
      );
      await refresh();
      setSettings(await getSettings(project.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Settings rejected.');
      if (e instanceof APIError && e.uncertain) setRetry(job);
      else {
        setRetry(null);
        await refresh();
        try {
          setSettings(await getSettings(project.id));
        } catch {}
      }
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <h3>Agent / model settings</h3>
      <p>
        Changes apply to future runs only. Current and completed invocations
        retain immutable configuration. Model selection is manual; any nonempty
        provider model slug is accepted by configuration, subject to the backend
        provider’s support at invocation time.
      </p>
      <p>
        Provider credentials:{' '}
        {settings
          ? settings.provider_configured
            ? 'Configured (backend only)'
            : 'Not configured'
          : 'Loading configuration…'}
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {retry && (
        <p className="warning">
          Save outcome unknown.{' '}
          <button disabled={busy} onClick={() => void send(retry)}>
            Retry same settings command
          </button>
        </p>
      )}
      <label>
        Employee
        <select
          value={kind}
          disabled={busy || !!retry}
          onChange={(e) => setKind(e.target.value)}
        >
          {['manager', 'developer', 'reviewer'].map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </label>
      {draft && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!settings || retry || busy) return;
            void send({
              key: crypto.randomUUID(),
              body: {
                expected_version: settings.project_version,
                kind: draft.kind,
                name: draft.name,
                role: draft.role,
                model: draft.model,
                system_instructions: draft.system_instructions,
              },
            });
          }}
        >
          <fieldset disabled={busy || !!retry}>
            <label>
              Employee name
              <input
                required
                maxLength={200}
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
            </label>
            <label>
              Role
              <input
                required
                maxLength={200}
                value={draft.role}
                onChange={(e) => setDraft({ ...draft, role: e.target.value })}
              />
            </label>
            <label>
              Model slug
              <input
                required
                maxLength={200}
                placeholder="anthropic/… or google/… or openai/…"
                value={draft.model}
                onChange={(e) => setDraft({ ...draft, model: e.target.value })}
              />
            </label>
            <label>
              System instructions
              <textarea
                required
                maxLength={16000}
                value={draft.system_instructions}
                onChange={(e) =>
                  setDraft({ ...draft, system_instructions: e.target.value })
                }
              />
            </label>
            <p>Configuration version {draft.config_version}</p>
            <p>
              Configured tools: {draft.tools.join(', ') || 'None'} · Permission
              capabilities: {draft.permissions.join(', ') || 'None'}
            </p>
            <p>
              Tools, permission policy and execution limits are configured by
              the backend and are read-only here. Saving cannot grant a runtime
              permission.
            </p>
            <button type="submit">Save future configuration</button>
          </fieldset>
        </form>
      )}
    </div>
  );
}
