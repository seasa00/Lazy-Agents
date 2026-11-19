import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { OfficeScene, useOfficeTheme } from '@/features/office/OfficeScene';
import { agentState, handoff, roles } from '@/features/office/projections';
import { initialState, reducer } from '@/lib/state/reducer';
import type { AgentKind, DomainEvent, Run } from '@/lib/api/types';
import { copy, event, run, snapshot } from './fixtures';
vi.mock('@/features/office3d/OfficeCanvas', () => ({
  OfficeCanvas: () => <div data-testid="office-canvas" />,
}));
const committed = (n: number, type = 'task.assigned') => ({
  ...event(n, type),
  event_id: `evt-${n}`,
});
function active(phase = 'develop') {
  const r = copy(run);
  r.phase = phase;
  r.current_task_id = 't0-0';
  r.workflow!.pending = 'op-1';
  return r;
}
const props = () => ({
  project: snapshot.project,
  run: active(),
  events: [] as DomainEvent[],
  connection: 'connected' as const,
  theme: 'day' as const,
  onTheme: vi.fn(),
  onAgent: vi.fn(),
  onTask: vi.fn(),
  onEvent: vi.fn(),
  onUsage: vi.fn(),
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
describe('authoritative office status', () => {
  it.each(roles)('%s is idle without a run or pending operation', (kind) => {
    expect(agentState(kind).status).toBe('Idle');
    expect(agentState(kind, run).status).toBe('Idle');
  });
  it.each([
    ['manager', 'plan', 'Thinking'],
    ['manager', 'decide', 'Thinking'],
    ['developer', 'develop', 'Working'],
    ['reviewer', 'review', 'Reviewing'],
  ] as const)(
    '%s in %s derives %s from pending operation',
    (kind, phase, status) => {
      expect(agentState(kind, active(phase)).status).toBe(status);
    },
  );
  it.each(roles)('%s waits for plan approval and paused execution', (kind) => {
    for (const status of ['paused', 'awaiting_approval', 'canceled'] as const)
      expect(agentState(kind, { ...active(), status }).status).toBe('Waiting');
    expect(agentState(kind, { ...run, status: 'completed' }).status).toBe(
      'Done',
    );
    expect(agentState(kind, { ...run, status: 'failed' }).status).toBe('Error');
  });
  it('permission, recovery and input blockers suppress working', () => {
    const r = active();
    r.workflow!.pending_permissions = ['permission'];
    expect(agentState('developer', r).status).toBe('Blocked');
    expect(agentState('reviewer', r).status).toBe('Waiting');
    r.workflow!.pending_permissions = [];
    r.status = 'waiting_for_user';
    r.workflow!.blocked_reason = 'Need input';
    expect(agentState('developer', r)).toMatchObject({
      status: 'Blocked',
      reason: 'Need input',
    });
    r.workflow!.recovery = { requires_resume: true, epoch: 1, issues: [] };
    expect(agentState('manager', r).status).toBe('Blocked');
  });
  it('pause requested remains active until the authoritative safe boundary', () => {
    const p = props();
    p.run.status = 'pause_requested';
    const v = render(<OfficeScene {...p} />);
    expect(screen.getByTestId('desk-developer')).toHaveAttribute(
      'data-active',
      'true',
    );
    expect(screen.getByTestId('desk-developer')).toHaveTextContent(
      'Pause requested',
    );
    v.rerender(<OfficeScene {...p} run={{ ...p.run, status: 'paused' }} />);
    expect(screen.getByTestId('desk-developer')).toHaveAttribute(
      'data-active',
      'false',
    );
  });
  it.each([
    ['manager', 'plan'],
    ['developer', 'develop'],
    ['reviewer', 'review'],
  ] as const)('only active %s receives ongoing motion', (kind, phase) => {
    render(<OfficeScene {...props()} run={active(phase)} />);
    for (const role of roles)
      expect(screen.getByTestId(`desk-${role}`)).toHaveAttribute(
        'data-active',
        String(kind === role),
      );
  });
  it('idle Developer, waiting Reviewer and blocked Developer have no work motion', () => {
    const p = props();
    p.run.workflow!.pending_permissions = ['approval'];
    render(<OfficeScene {...p} />);
    for (const kind of roles)
      expect(screen.getByTestId(`desk-${kind}`)).toHaveAttribute(
        'data-active',
        'false',
      );
  });
  it('disconnect preserves last-known status without pretending execution stopped', () => {
    render(<OfficeScene {...props()} connection="disconnected" />);
    expect(screen.getByTestId('desk-developer')).toHaveTextContent('Working');
    expect(screen.getByTestId('desk-developer')).toHaveAttribute(
      'data-active',
      'false',
    );
    expect(
      screen.getByText(/disconnected browsers do not stop agents/),
    ).toBeVisible();
  });
});
describe('committed handoffs and replay safety', () => {
  it.each([
    ['task.assigned', 'manager', 'developer'],
    ['submission.admitted', 'developer', 'reviewer'],
    ['revision.requested', 'manager', 'developer'],
    ['review.completed', 'reviewer', 'manager'],
    ['task.accepted', 'manager', 'developer'],
  ])('%s maps %s to %s', (type, from, to) => {
    expect(handoff(committed(11, type))).toMatchObject({ from, to });
  });
  it.each(['FAIL', 'PASS'] as const)(
    'resolves %s from the matching review identity',
    (verdict) => {
      const r = active('decide');
      r.workflow!.reviews = [
        {
          task_id: 't0-0',
          submission_id: 's1',
          number: 1,
          result: { review_id: 'review-1', verdict, summary: 'Checked' },
        },
      ];
      const e = committed(11, 'review.completed');
      e.payload.review_id = 'review-1';
      expect(handoff(e, r)).toMatchObject({
        label: `${verdict} review returned`,
        kind: 'review',
        verdict,
      });
      e.payload.review_id = 'other';
      expect(handoff(e, r)?.label).toBe('Review returned');
    },
  );
  it('ignores unrelated activity', () => {
    expect(handoff(committed(11, 'tool.audit'))).toBeNull();
  });
  it('fresh events animate once and open the same activity entry', () => {
    vi.useFakeTimers();
    const p = props();
    const v = render(<OfficeScene {...p} />);
    const e = committed(11);
    v.rerender(<OfficeScene {...p} events={[e]} />);
    const packet = screen.getByRole('button', { name: /Manager to Developer/ });
    expect(packet).toHaveAttribute('data-handoff-kind', 'assignment');
    expect(screen.getByTestId('desk-manager')).toHaveAttribute(
      'data-interaction',
      'assigning',
    );
    expect(screen.getByTestId('desk-developer')).toHaveAttribute(
      'data-interaction',
      'receiving',
    );
    fireEvent.click(packet);
    expect(p.onEvent).toHaveBeenCalledWith(e);
    expect(screen.getByTestId('desk-developer')).toHaveTextContent(
      'Task received',
    );
    act(() => vi.advanceTimersByTime(1900));
    v.rerender(<OfficeScene {...p} events={[e, e]} />);
    expect(
      screen.queryByRole('button', { name: /Manager to Developer/ }),
    ).not.toBeInTheDocument();
  });
  it('shows compact outcome packets and resolves accepted work from task state', () => {
    vi.useFakeTimers();
    const p = props();
    const completed = copy(snapshot.project.tasks[0]);
    completed.status = 'done';
    const accepted = committed(12, 'task.accepted');
    const view = render(<OfficeScene {...p} />);
    view.rerender(
      <OfficeScene
        {...p}
        project={{ ...p.project, tasks: [completed] }}
        events={[accepted]}
      />,
    );
    const packet = screen.getByRole('button', { name: /Task accepted/ });
    expect(packet).toHaveAttribute('data-handoff-kind', 'accepted');
    expect(packet).toHaveAttribute('data-verdict', 'PASS');
    expect(screen.getByTestId('desk-developer')).toHaveTextContent(
      'Task complete',
    );
    expect(screen.getByTestId('desk-developer')).toHaveAttribute(
      'data-interaction',
      'receiving',
    );
    expect(
      screen.getByRole('button', { name: /Open completed task t0-0/ }),
    ).toHaveTextContent('✓ t0-0 · Greeting task');
  });
  it('maps committed assignment, submission, review, revision, and acceptance events to desk cues', () => {
    vi.useFakeTimers();
    const p = props();
    const view = render(<OfficeScene {...p} />);
    let events: DomainEvent[] = [];
    const publish = (
      next: DomainEvent,
      nextRun: Run = p.run,
      nextProject = p.project,
    ) => {
      events = [...events, next];
      view.rerender(
        <OfficeScene
          {...p}
          project={nextProject}
          run={nextRun}
          events={events}
        />,
      );
    };

    publish(committed(11, 'task.assigned'));
    expect(screen.getByTestId('desk-manager')).toHaveAttribute(
      'data-interaction',
      'assigning',
    );
    expect(screen.getByTestId('desk-manager')).toHaveTextContent(
      'Assigning task',
    );
    expect(screen.getByTestId('desk-developer')).toHaveAttribute(
      'data-interaction',
      'receiving',
    );

    publish(committed(12, 'submission.admitted'));
    expect(screen.getByTestId('desk-developer')).toHaveAttribute(
      'data-interaction',
      'submitting',
    );
    expect(screen.getByTestId('desk-reviewer')).toHaveAttribute(
      'data-interaction',
      'receiving',
    );
    expect(screen.getByTestId('desk-developer')).toHaveTextContent(
      'Submitting work',
    );

    const failed = active('decide');
    failed.workflow!.reviews = [
      {
        task_id: 't0-0',
        submission_id: 's1',
        number: 1,
        result: {
          review_id: 'review-fail',
          verdict: 'FAIL',
          summary: 'Revise',
        },
      },
    ];
    const failEvent = committed(13, 'review.completed');
    failEvent.payload.review_id = 'review-fail';
    publish(failEvent, failed);
    expect(screen.getByTestId('desk-reviewer')).toHaveAttribute(
      'data-interaction',
      'review-fail',
    );
    expect(screen.getByTestId('desk-manager')).toHaveTextContent(
      'FAIL review returned',
    );
    expect(
      screen.getByRole('button', { name: /FAIL review returned/ }),
    ).toHaveAttribute('data-verdict', 'FAIL');

    publish(committed(14, 'revision.requested'), failed);
    expect(screen.getByTestId('desk-manager')).toHaveAttribute(
      'data-interaction',
      'revising',
    );
    expect(screen.getByTestId('desk-developer')).toHaveTextContent(
      'Revision received',
    );

    const passed = copy(failed);
    passed.workflow!.reviews.push({
      task_id: 't0-0',
      submission_id: 's2',
      number: 2,
      result: { review_id: 'review-pass', verdict: 'PASS', summary: 'Ready' },
    });
    const passEvent = committed(15, 'review.completed');
    passEvent.payload.review_id = 'review-pass';
    publish(passEvent, passed);
    expect(screen.getByTestId('desk-reviewer')).toHaveAttribute(
      'data-interaction',
      'review-pass',
    );
    expect(screen.getByTestId('desk-manager')).toHaveTextContent(
      'PASS review returned',
    );

    const completed = copy(passed);
    completed.status = 'completed';
    completed.phase = 'completed';
    completed.current_task_id = null;
    const doneProject = copy(p.project);
    doneProject.tasks[0].status = 'done';
    publish(committed(16, 'task.accepted'), completed, doneProject);
    expect(screen.getByTestId('desk-developer')).toHaveTextContent(
      'Task complete',
    );
    expect(screen.getByTestId('desk-developer')).toHaveAttribute(
      'data-interaction',
      'receiving',
    );
    expect(
      screen.getByRole('button', { name: /Open completed task t0-0/ }),
    ).toHaveTextContent('✓ t0-0 · Greeting task');
  });
  it('mount/refresh never animates existing events', () => {
    render(<OfficeScene {...props()} events={[committed(11)]} />);
    expect(
      screen.queryByRole('button', { name: /Manager to Developer/ }),
    ).not.toBeInTheDocument();
  });
  it('pausing clears travel and does not replay it on resume', () => {
    const p = props();
    const v = render(<OfficeScene {...p} />);
    const events = [committed(11)];
    v.rerender(<OfficeScene {...p} events={events} />);
    v.rerender(
      <OfficeScene
        {...p}
        events={events}
        run={{ ...p.run, status: 'paused' }}
      />,
    );
    expect(
      screen.queryByRole('button', { name: /Manager to Developer/ }),
    ).not.toBeInTheDocument();
    v.rerender(<OfficeScene {...p} events={events} />);
    expect(
      screen.queryByRole('button', { name: /Manager to Developer/ }),
    ).not.toBeInTheDocument();
  });
  it('only explicit live committed identities enter the visual window; reset clears it', () => {
    let s = reducer(initialState, { type: 'snapshot', snapshot });
    s = reducer(s, { type: 'event', event: committed(11) });
    expect(s.liveEvents).toHaveLength(0);
    s = reducer(s, { type: 'event', event: committed(12), live: true });
    expect(s.liveEvents).toHaveLength(1);
    s = reducer(s, { type: 'event', event: committed(12), live: true });
    expect(s.liveEvents).toHaveLength(1);
    s = reducer(s, { type: 'event', event: event(13), live: true });
    expect(s.liveEvents).toHaveLength(1);
    s = reducer(s, { type: 'snapshot', snapshot, reset: true });
    expect(s.liveEvents).toHaveLength(0);
  });
  it('reconnect clears old visuals and permits only fresh post-boundary events', () => {
    let s = reducer(initialState, { type: 'snapshot', snapshot });
    s = reducer(s, { type: 'event', event: committed(11), live: true });
    s = reducer(s, { type: 'connection', connection: 'disconnected' });
    expect(s.liveEvents).toHaveLength(0);
    s = reducer(s, { type: 'event', event: committed(12), live: false });
    expect(s.liveEvents).toHaveLength(0);
    s = reducer(s, { type: 'event', event: committed(13), live: true });
    expect(s.liveEvents.map((e) => e.sequence)).toEqual([13]);
  });
});
describe('office interactions and theme', () => {
  it.each(roles)('opens existing %s details through navigation', (kind) => {
    const p = props();
    render(<OfficeScene {...p} />);
    fireEvent.click(
      screen.getByRole('button', {
        name: `Open ${kind[0].toUpperCase() + kind.slice(1)} details`,
      }),
    );
    expect(p.onAgent).toHaveBeenCalledWith(kind);
  });
  it('opens the current task and detailed usage; unknown cost is never zero', () => {
    const p = props();
    render(<OfficeScene {...p} />);
    fireEvent.click(
      screen.getByRole('button', { name: 'Open task t0-0 from Developer' }),
    );
    expect(p.onTask).toHaveBeenCalledWith('t0-0');
    fireEvent.click(
      screen.getByRole('button', { name: 'Open detailed resource usage' }),
    );
    expect(p.onUsage).toHaveBeenCalledOnce();
    expect(
      screen.getByRole('button', { name: 'Open detailed resource usage' }),
    ).toHaveTextContent('Unavailable');
    expect(screen.queryByText('$0')).not.toBeInTheDocument();
  });
  it('day/night manual selection persists across remount without touching backend data', () => {
    const values = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => values.get(k),
      setItem: (k: string, v: string) => values.set(k, v),
    });
    function Themed() {
      const [theme, onTheme] = useOfficeTheme();
      return <OfficeScene {...props()} theme={theme} onTheme={onTheme} />;
    }
    const v = render(<Themed />);
    expect(screen.getByRole('button', { name: '☀ Day' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    fireEvent.click(screen.getByRole('button', { name: '☾ Night' }));
    expect(values.get('ai-office-theme')).toBe('night');
    v.unmount();
    render(<Themed />);
    expect(screen.getByRole('button', { name: '☾ Night' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByTestId('desk-developer')).toHaveTextContent('Working');
    fireEvent.click(screen.getByRole('button', { name: '☀ Day' }));
    expect(values.get('ai-office-theme')).toBe('day');
  });
});
