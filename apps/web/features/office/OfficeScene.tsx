'use client';
import { useEffect, useRef, useState } from 'react';
import type {
  AgentKind,
  DomainEvent,
  Project,
  Run,
  Usage,
} from '@/lib/api/types';
import type { Connection } from '@/lib/state/reducer';
import { OfficeCanvas } from '../office3d/OfficeCanvas';
import type { CharacterCue } from './PixelCharacter';
import {
  agentState,
  canMove,
  handoff,
  roles,
  roleName,
  statusIcon,
  type OfficeHandoff,
} from './projections';
export type OfficeNavigation = {
  view: string;
  agent?: AgentKind;
  nonce: number;
};
export function useOfficeTheme() {
  const [theme, setTheme] = useState<'day' | 'night'>('day');
  useEffect(() => {
    try {
      if (localStorage.getItem('ai-office-theme') === 'night')
        setTheme('night');
    } catch {
      /* Storage may be disabled. */
    }
  }, []);
  return [
    theme,
    (value: 'day' | 'night') => {
      setTheme(value);
      try {
        localStorage.setItem('ai-office-theme', value);
      } catch {
        /* The toggle still works for this visit. */
      }
    },
  ] as const;
}
function cueFor(kind: AgentKind, route: OfficeHandoff): CharacterCue {
  if (route.to === kind) return 'receiving';
  switch (route.kind) {
    case 'assignment':
      return 'assigning';
    case 'submission':
      return 'submitting';
    case 'review':
      return route.verdict === 'PASS' ? 'review-pass' : 'review-fail';
    case 'revision':
      return 'revising';
    case 'accepted':
      return 'approving';
  }
}
function handoffMark(route: OfficeHandoff) {
  if (route.verdict === 'PASS') return '✓';
  if (route.verdict === 'FAIL') return '!';
  if (route.kind === 'revision') return '↻';
  return undefined;
}
function receiptLabel(route: OfficeHandoff) {
  switch (route.kind) {
    case 'assignment':
      return 'Task received';
    case 'submission':
      return 'Submission received';
    case 'review':
      return route.verdict
        ? `${route.verdict} review returned`
        : 'Review returned';
    case 'revision':
      return 'Revision received';
    case 'accepted':
      return 'Task complete';
  }
}
function sendingLabel(route: OfficeHandoff) {
  switch (route.kind) {
    case 'assignment':
      return 'Assigning task';
    case 'submission':
      return 'Submitting work';
    case 'review':
      return route.verdict === 'PASS'
        ? 'Review passed'
        : route.verdict === 'FAIL'
          ? 'Changes requested'
          : 'Review complete';
    case 'revision':
      return 'Sending revision';
    case 'accepted':
      return 'Approving task';
  }
}
export function OfficeScene({
  project,
  run,
  events,
  connection,
  theme,
  onTheme,
  onAgent,
  onTask,
  onEvent,
  usage,
  onUsage,
}: {
  project: Project;
  run?: Run;
  events: DomainEvent[];
  connection: Connection;
  theme: 'day' | 'night';
  onTheme: (theme: 'day' | 'night') => void;
  onAgent: (kind: AgentKind) => void;
  onTask: (id: string) => void;
  onEvent: (event: DomainEvent) => void;
  usage?: Usage;
  onUsage: () => void;
}) {
  // Already present events are historical when this presentation mounts.
  const seen = useRef(new Set(events.map((e) => e.event_id)));
  const [packets, setPackets] = useState<DomainEvent[]>([]);
  const animate = canMove(run) && connection === 'connected';
  const acknowledge =
    connection === 'connected' &&
    Boolean(
      run &&
      !['paused', 'canceled', 'failed'].includes(run.status) &&
      !run.workflow?.recovery?.requires_resume,
    );
  useEffect(() => {
    const fresh = events.filter(
      (e) => e.event_id && !seen.current.has(e.event_id),
    );
    for (const e of fresh) seen.current.add(e.event_id);
    // The controller's live window is bounded; sequence ordering is its durable
    // deduplication guard. Retain only recent visual IDs here.
    if (seen.current.size > 512)
      seen.current = new Set(events.map((e) => e.event_id));
    if (!acknowledge) {
      setPackets([]);
      return;
    }
    const incoming = fresh.filter((e) => e.run_id === run?.id && handoff(e));
    if (incoming.length) setPackets((old) => [...old, ...incoming].slice(-4));
  }, [events, acknowledge, run?.id]);
  useEffect(() => {
    if (!packets.length) return;
    // Expiry is only a visual acknowledgement. It cannot invoke a command or
    // mutate a task; this phase shows committed receipts as static HTML cues.
    const timer = window.setTimeout(() => setPackets([]), 1800);
    return () => window.clearTimeout(timer);
  }, [packets]);
  const tasks = project.tasks.filter(
    (t) => !run || run.task_ids.includes(t.id),
  );
  return (
    <section
      className="office"
      id="office"
      aria-label="AI Office room"
      data-connection={connection}
    >
      <div className="office-heading">
        <div>
          <p className="eyebrow">THREE MINDS · ONE WORKSPACE</p>
          <h2>
            The office{' '}
            <span className="office-season">
              {theme === 'day'
                ? 'A little daylight. A clear plan.'
                : 'Quiet hours. Bright ideas.'}
            </span>
          </h2>
        </div>
        <div className="theme-toggle" role="group" aria-label="Office lighting">
          <button aria-pressed={theme === 'day'} onClick={() => onTheme('day')}>
            ☀ Day
          </button>
          <button
            aria-pressed={theme === 'night'}
            onClick={() => onTheme('night')}
          >
            ☾ Night
          </button>
        </div>
      </div>
      <div className="office-stage" data-motion={animate ? 'live' : 'still'}>
        <OfficeCanvas theme={theme} />
      </div>
      <div className="office-agent-grid" role="group" aria-label="Office team">
        {roles.map((kind) => {
          const employee = run?.workflow?.agent_snapshots.find(
            (a) => a.kind === kind,
          );
          const state = agentState(kind, run);
          const active =
            animate &&
            ['Thinking', 'Working', 'Reviewing'].includes(state.status);
          const relatedPackets = packets.flatMap((event) => {
            const route = handoff(event, run);
            return route && (route.from === kind || route.to === kind)
              ? [{ event, route }]
              : [];
          });
          const latestInteraction = relatedPackets.at(-1);
          const interaction = latestInteraction
            ? cueFor(kind, latestInteraction.route)
            : null;
          const receipt =
            latestInteraction?.route.to === kind ? latestInteraction : null;
          const accepted =
            kind === 'developer'
              ? [...relatedPackets]
                  .reverse()
                  .find((item) => item.route.kind === 'accepted')
              : undefined;
          const displayedTaskId =
            state.taskId || accepted?.event.task_id || null;
          const task = tasks.find((t) => t.id === displayedTaskId);
          const resolved = task?.status === 'done';
          const lastReview =
            kind === 'reviewer' ? run?.workflow?.reviews.at(-1) : null;
          return (
            <article
              className={`agent-desk desk-${kind}`}
              data-testid={`desk-${kind}`}
              data-status={state.status}
              data-active={active}
              data-interaction={interaction || state.status.toLowerCase()}
              data-received={Boolean(receipt)}
              data-sending={Boolean(latestInteraction?.route.from === kind)}
              key={kind}
            >
              <button
                className="employee-button"
                aria-label={`Open ${roleName(kind)} details`}
                aria-describedby={`office-${kind}-reason`}
                onClick={() => onAgent(kind)}
                title={state.reason}
              >
                <span className="desk-nameplate">
                  <span className="employee-name">
                    {employee?.name || roleName(kind)}
                  </span>
                  {employee?.name && employee.name !== roleName(kind) && (
                    <span className="employee-role">
                      {employee.role || roleName(kind)}
                    </span>
                  )}
                  <span
                    className={`office-status status-${state.status.toLowerCase()}`}
                  >
                    <span aria-hidden="true">{statusIcon[state.status]}</span>{' '}
                    {state.status}
                  </span>
                  {latestInteraction && (
                    <span
                      className="desk-ack"
                      key={latestInteraction.event.event_id}
                      data-kind={latestInteraction.route.kind}
                      data-verdict={
                        latestInteraction.route.verdict || undefined
                      }
                      aria-live="polite"
                    >
                      <span aria-hidden="true">
                        {handoffMark(latestInteraction.route) || '▤'}
                      </span>{' '}
                      {receipt
                        ? receiptLabel(receipt.route)
                        : sendingLabel(latestInteraction.route)}
                    </span>
                  )}
                </span>
              </button>
              <p
                id={`office-${kind}-reason`}
                className="desk-reason"
                title={state.reason}
              >
                {state.reason}
              </p>
              {displayedTaskId ? (
                <button
                  className={`desk-task${resolved ? ' desk-task-done' : ''}`}
                  title={task?.title || displayedTaskId}
                  onClick={() => onTask(displayedTaskId)}
                  aria-label={`${resolved ? 'Open completed task' : 'Open task'} ${displayedTaskId} from ${roleName(kind)}`}
                >
                  {resolved ? '✓ ' : '▤ '}
                  {displayedTaskId} · {task?.title || 'Current task'}
                </button>
              ) : (
                <span className="desk-no-task">No current task</span>
              )}
              {lastReview && (
                <button
                  className="desk-review"
                  onClick={() => onTask(lastReview.task_id)}
                >
                  Last review: {lastReview.result.verdict} ↗
                </button>
              )}
            </article>
          );
        })}
      </div>
      <div className="handoff-layer" aria-label="Recent committed handoffs">
        {packets.map((event) => {
          const route = handoff(event, run)!;
          return (
            <button
              className="task-packet"
              key={event.event_id}
              data-handoff-id={event.event_id}
              data-handoff-type={event.type}
              data-handoff-kind={route.kind}
              data-verdict={route.verdict || undefined}
              onClick={() => onEvent(event)}
              aria-label={`${roleName(route.from)} to ${roleName(route.to)}: ${route.label}, event ${event.sequence}`}
            >
              <span
                className="task-document-art"
                data-mark={handoffMark(route)}
                aria-hidden="true"
              />
              <small className="packet-label">{route.label}</small>
            </button>
          );
        })}
      </div>
      <div className="office-footer">
        <p>
          <span className="office-live-dot" aria-hidden="true" />
          {connection === 'connected'
            ? 'Live office · work follows backend state'
            : 'Last known state · disconnected browsers do not stop agents'}
          <br />
          <small>Click an employee or task to inspect their work.</small>
        </p>
        <button
          className="resource-monitor"
          onClick={onUsage}
          aria-label="Open detailed resource usage"
        >
          <span>
            <strong>
              {usage?.total_tokens == null
                ? 'Unavailable'
                : usage.total_tokens.toLocaleString()}
              {usage && !usage.usage_complete ? ' · Incomplete' : ''}
            </strong>{' '}
            tokens
          </span>
          <span>
            <strong>
              {usage?.estimated_cost == null
                ? 'Unavailable'
                : `$${usage.estimated_cost}`}
              {usage && !usage.cost_complete ? ' · Incomplete' : ''}
            </strong>{' '}
            estimated cost
          </span>
          <span>
            <strong>{usage?.provider_calls ?? 'Unavailable'}</strong> calls
          </span>
          <span>
            <strong>
              {tasks.filter((t) => t.status === 'done').length}/{tasks.length}
            </strong>{' '}
            tasks complete ↗
          </span>
        </button>
      </div>
    </section>
  );
}
