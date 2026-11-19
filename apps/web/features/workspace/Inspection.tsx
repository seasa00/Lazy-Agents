'use client';
import { useEffect, useState } from 'react';
import { getInspection } from '@/lib/api/client';
import type {
  AgentKind,
  Inspection,
  Run,
  Project,
  DomainEvent,
} from '@/lib/api/types';
import { UsagePanel } from '../usage/UsagePanel';
import { AgentDetail } from '../agents/AgentDetail';
import { TaskHistory } from './TaskHistory';
import { ToolActivity } from './ToolActivity';
import { SettingsPanel } from '../settings/SettingsPanel';
import { RecoveryPanel } from './RecoveryPanel';
import type { OfficeNavigation } from '../office/OfficeScene';
import { useProject } from '@/lib/state/context';
export function InspectionPanel({
  project,
  run: currentRun,
  selected,
  events,
  cursor,
  navigation,
  onCurrentInspection,
}: {
  project: Project;
  run?: Run;
  selected: string | null;
  events: DomainEvent[];
  cursor: number;
  navigation?: OfficeNavigation;
  onCurrentInspection?: (value: Inspection) => void;
}) {
  const [inspectedId, setInspectedId] = useState('');
  const run = project.runs.find((r) => r.id === inspectedId) || currentRun;
  const historical = run?.id !== currentRun?.id;
  const [tab, setTab] = useState('Agents');
  const [agent, setAgent] = useState<AgentKind>('developer');
  const [received, setReceived] = useState<{
    runId: string;
    value: Inspection;
  } | null>(null);
  const data = received && received.runId === run?.id ? received.value : null;
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const { select, refresh, command, state, permissions } = useProject();
  useEffect(() => {
    let live = true;

    if (run)
      void getInspection(project.id, run.id)
        .then((value) => {
          if (live) {
            setReceived({ runId: run.id, value });
            if (!historical) onCurrentInspection?.(value);
            setError(null);
          }
        })
        .catch((e) => {
          if (live) setError(e.message);
        });
    return () => {
      live = false;
    };
  }, [
    project.id,
    project.version,
    run?.id,
    cursor,
    retry,
    historical,
    onCurrentInspection,
  ]);
  // This is navigation only; backend attempts and verdicts remain authoritative.
  useEffect(() => {
    if (selected) setTab('Task history');
  }, [selected]);
  useEffect(() => {
    if (!navigation) return;
    setInspectedId('');
    setTab(navigation.view);
    if (navigation.agent) setAgent(navigation.agent);
  }, [navigation]);
  const busy = Object.values(state.pending).some(
    (p) => p.status === 'sending' || p.status === 'uncertain',
  );
  const tabs = [
    'Agents',
    'Task history',
    'Tool activity',
    'Usage',
    'Settings',
    'Recovery',
  ];
  return (
    <section
      id="inspection"
      tabIndex={-1}
      className="panel inspection"
      aria-label="Project inspection"
    >
      <h2>Inspect project</h2>
      {project.runs.length > 1 && (
        <label>
          Inspection run
          <select
            value={inspectedId}
            onChange={(e) => {
              setInspectedId(e.target.value);
              select(null);
            }}
          >
            <option value="">Current / latest run</option>
            {project.runs
              .filter((r) => r.id !== currentRun?.id)
              .map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id} · {r.status}
                </option>
              ))}
          </select>
        </label>
      )}
      {historical && (
        <p className="muted">
          Inspecting retained run {run?.id}. Workflow controls above operate the
          current run.
        </p>
      )}
      <nav className="actions" aria-label="Inspection views">
        {tabs.map((t) => (
          <button key={t} aria-pressed={tab === t} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </nav>
      {error && (
        <p className="error" role="alert">
          Inspection unavailable: {error}{' '}
          <button onClick={() => setRetry((v) => v + 1)}>
            Retry inspection
          </button>
        </p>
      )}
      {tab === 'Agents' && (
        <>
          <div className="actions">
            {(['manager', 'developer', 'reviewer'] as const).map((kind) => (
              <button
                key={kind}
                aria-pressed={agent === kind}
                onClick={() => setAgent(kind)}
              >
                Inspect {kind[0].toUpperCase() + kind.slice(1)}
              </button>
            ))}
          </div>
          <AgentDetail
            kind={agent}
            run={run}
            events={data?.recent_events || events}
            usage={data?.usage}
            capabilities={data?.capabilities?.[agent]}
            onTask={select}
          />
        </>
      )}
      {tab === 'Task history' && (
        <TaskHistory
          project={project}
          run={run}
          taskId={selected}
          onTask={select}
          onAgent={(kind) => {
            setAgent(kind);
            setTab('Agents');
          }}
          operations={data?.operations || []}
          onTools={() => setTab('Tool activity')}
          onUsage={() => setTab('Usage')}
        />
      )}
      {tab === 'Tool activity' && (
        <ToolActivity run={run} inspection={data} onTask={select} />
      )}
      {tab === 'Usage' &&
        (data ? (
          <UsagePanel run={data.usage} project={data.project_usage} />
        ) : (
          <p>Loading durable usage…</p>
        ))}
      {tab === 'Settings' && (
        <>
          <SettingsPanel project={project} refresh={refresh} />
          <h4>Effective run limits (backend-configured)</h4>
          <dl>
            {Object.entries(data?.limits || {}).map(([key, value]) => (
              <div key={key}>
                <dt>{key.replaceAll('_', ' ')}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </>
      )}
      {tab === 'Recovery' && historical && (
        <p>Select Current / latest run to operate recovery controls.</p>
      )}
      {tab === 'Recovery' && (
        <RecoveryPanel
          inspection={data?.recovery}
          recovery={run?.workflow?.recovery}
          busy={busy || historical}
          command={command}
        />
      )}
    </section>
  );
}
