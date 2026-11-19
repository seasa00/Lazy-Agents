import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { AgentDetail } from '@/features/agents/AgentDetail';
import { TaskHistory } from '@/features/workspace/TaskHistory';
import { ArtifactViewer, Diff } from '@/features/artifacts/ArtifactViewer';
import { UsagePanel } from '@/features/usage/UsagePanel';
import { SettingsPanel } from '@/features/settings/SettingsPanel';
import { RecoveryPanel } from '@/features/workspace/RecoveryPanel';
import { ToolActivity } from '@/features/workspace/ToolActivity';
import { APIError } from '@/lib/api/client';
import type {
  Settings,
  Usage,
  Submission,
  Inspection,
  RecoveryInspection,
} from '@/lib/api/types';
import { copy, run, snapshot, permission } from './fixtures';
const mocks = vi.hoisted(() => ({
  artifact: vi.fn(),
  settings: vi.fn(),
  save: vi.fn(),
}));
vi.mock('@/lib/api/client', async (original) => ({
  ...(await original<object>()),
  getArtifact: mocks.artifact,
  getSettings: mocks.settings,
  saveSettings: mocks.save,
}));
const totals = {
  provider_calls: 4,
  retries: 1,
  total_tokens: 60,
  input_tokens: 40,
  output_tokens: 20,
  cached_input_tokens: 5,
  estimated_cost: '0.004',
  usage_complete: true,
  cost_complete: true,
  known_tokens: 60,
  known_estimated_cost: '0.004',
};
const usage: Usage = {
  ...totals,
  reviews: 2,
  per_agent: { manager: totals, developer: totals, reviewer: totals },
};
const settings: Settings = {
  project_version: 3,
  applies_to: 'next_run',
  agents: run.workflow!.agent_snapshots.map((a) => ({
    ...a,
    model: 'google/gemini-test',
    system_instructions: 'Bounded instructions',
    tools: ['read'],
    permissions: ['workspace-read'],
    config_version: 1,
  })),
  editable_fields: ['name', 'role', 'model', 'system_instructions'],
  provider_configured: true,
  note: 'Future runs only',
};
const submission = (number: number): Submission => ({
  id: `s${number}`,
  task_id: 't0-0',
  attempt_id: `a${number}`,
  version: number,
  generation: 1,
  digest: 'hash' + number,
  output: {
    summary: 'Change ' + number,
    changed_files: [
      { path: 'greeting.txt', change_type: 'modified', summary: 'Greeting' },
    ],
    tests: [{ name: 'unit', status: 'not_run', summary: 'No tests executed' }],
    notes: [],
  },
  files: {
    files: [
      {
        path: 'greeting.txt',
        content: 'hello',
        diff: '-old\n+hello',
        before: 'old',
      },
    ],
    workspace_version: 'workspace',
    tests: [],
  },
});
function historyRun() {
  const r = copy(run);
  const wf = r.workflow!;
  wf.attempts = [1, 2].map((n) => ({
    id: `a${n}`,
    task_id: 't0-0',
    number: n,
    generation: 1,
  }));
  wf.submissions = [submission(1), submission(2)];
  wf.reviews = [1, 2].map((n) => ({
    task_id: 't0-0',
    submission_id: `s${n}`,
    submission_version: n,
    number: n,
    result: {
      review_id: `review${n}`,
      verdict: n === 1 ? 'FAIL' : 'PASS',
      summary: 'Review ' + n,
      assessments: [
        {
          criterion_id: 'c1',
          passed: n === 2,
          evidence: 'Evidence ' + n,
          notes: '',
        },
      ],
      findings:
        n === 1
          ? [
              {
                id: 'f1',
                severity: 'major',
                summary: 'Fix greeting',
                evidence: 'Wrong greeting',
                criterion_id: 'c1',
              },
            ]
          : [],
      checks_not_performed: ['Integration tests'],
    },
  }));
  wf.revisions = [
    {
      task_id: 't0-0',
      submission_id: 's1',
      review_id: 'review1',
      required_fixes: ['Use hello world'],
      remaining_review_rounds: 2,
    },
  ];
  wf.invocation_records = [
    {
      id: 'i1',
      agent_id: 'developer',
      phase: 'develop',
      generation: 1,
      config_digest: 'frozen',
    },
    {
      id: 'i2',
      agent_id: 'reviewer',
      phase: 'review',
      generation: 1,
      config_digest: 'review-frozen',
    },
  ];
  wf.call_records = [
    {
      call_id: 'call1',
      invocation_id: 'i1',
      model: 'anthropic/recorded',
      purpose: 'develop',
      attempt: 1,
      status: 'succeeded',
      usage: { input_tokens: 10, output_tokens: 5, cached_input_tokens: 0 },
      estimated_cost: null,
    },
  ];
  wf.agent_snapshots = wf.agent_snapshots.map((a) => ({
    ...a,
    model: 'anthropic/recorded',
    tools: ['read'],
    permissions: ['workspace-read'],
  }));
  return r;
}
const nav = {
  onTask: vi.fn(),
  onAgent: vi.fn(),
  onTools: vi.fn(),
  onUsage: vi.fn(),
};
const recovery: RecoveryInspection = {
  phase: 'review',
  checkpoint: {
    task_id: 't0-0',
    attempt_id: 'a1',
    phase: 'review',
    generation: 1,
    invocation_id: 'i2',
  },
  operations: [],
  recovery: {
    epoch: 2,
    requires_resume: true,
    issues: [
      {
        id: 'op1',
        kind: 'command',
        certainty: 'uncertain',
        reason: 'Completion cannot be proven',
        resolved: false,
      },
    ],
  },
  available_actions: {
    op1: [
      {
        action: 'acknowledge-command',
        label: 'Acknowledge uncertain command',
        requires_quiescent: true,
      },
    ],
  },
};
beforeEach(() => {
  vi.clearAllMocks();
  mocks.settings.mockResolvedValue(copy(settings));
  mocks.save.mockResolvedValue({ status: 'applied' });
  mocks.artifact.mockResolvedValue({
    artifact_id: 's1:greeting.txt',
    submission_id: 's1',
    task_id: 't0-0',
    attempt_id: 'a1',
    version: 1,
    path: 'greeting.txt',
    content_hash: 'safe-hash',
    before_hash: 'before',
    diff: '-old\n+hello',
    content: 'hello',
    created_at: null,
  });
});
describe('agent inspection', () => {
  it('shows captured model role state and configured capability', () => {
    const r = historyRun();
    r.phase = 'develop';
    r.current_task_id = 't0-0';
    r.workflow!.pending = 'i1';
    render(
      <AgentDetail
        kind="developer"
        run={r}
        usage={usage}
        events={[]}
        onTask={nav.onTask}
      />,
    );
    expect(screen.getByText('Software Developer')).toBeVisible();
    expect(screen.getByText('running · Invocation pending')).toBeVisible();
    expect(screen.getByText('workspace-read')).toBeVisible();
    expect(screen.getAllByText(/anthropic\/recorded/).length).toBeGreaterThan(
      0,
    );
    fireEvent.click(screen.getByRole('button', { name: 't0-0' }));
    expect(nav.onTask).toHaveBeenCalledWith('t0-0');
  });
  it('renders invocation and structured handoff without raw private fields', () => {
    const r = historyRun();
    Object.assign(r.workflow!.call_records![0], {
      private_reasoning: 'PRIVATE_SENTINEL',
      authorization: 'SECRET_SENTINEL',
    });
    render(
      <AgentDetail
        kind="developer"
        run={r}
        usage={usage}
        events={[]}
        onTask={nav.onTask}
      />,
    );
    expect(screen.getByText(/develop · i1/)).toBeVisible();
    expect(screen.getByText(/Change 1/)).toBeVisible();
    expect(document.body).not.toHaveTextContent('PRIVATE_SENTINEL');
    expect(document.body).not.toHaveTextContent('SECRET_SENTINEL');
  });
});
it('shows effective backend denial separately from configured capability', () => {
  render(
    <AgentDetail
      kind="reviewer"
      run={historyRun()}
      usage={usage}
      events={[]}
      onTask={nav.onTask}
      capabilities={{
        files: { write: { allowed: false, reason: 'Captured evidence only' } },
        command_request: {
          allowed: false,
          reason: 'Role policy denies commands',
        },
      }}
    />,
  );
  expect(
    screen.getByText('write: Denied — Captured evidence only'),
  ).toBeVisible();
  expect(
    screen.getByText('Command request: Denied — Role policy denies commands'),
  ).toBeVisible();
  expect(
    screen.queryByRole('button', { name: /Grant/ }),
  ).not.toBeInTheDocument();
});
describe('attempt submission review history', () => {
  it('binds FAIL PASS and findings to exact submissions and versions', () => {
    render(
      <TaskHistory
        project={snapshot.project}
        run={historyRun()}
        taskId="t0-0"
        operations={[]}
        {...nav}
      />,
    );
    expect(screen.getByText('Reviewer FAIL · round 1')).toBeVisible();
    expect(screen.getByText('Reviewer PASS · round 2')).toBeVisible();
    expect(screen.getByText('Exact submission: s1 · v1')).toBeVisible();
    expect(screen.getByText('Exact submission: s2 · v2')).toBeVisible();
    expect(screen.getAllByText('Integration tests')).toHaveLength(2);
    expect(screen.getByText('Use hello world')).toBeVisible();
  });
  it('excludes a review bound to the wrong submission version', () => {
    const r = historyRun();
    r.workflow!.reviews[0].submission_version = 99;
    render(
      <TaskHistory
        project={snapshot.project}
        run={r}
        taskId="t0-0"
        operations={[]}
        {...nav}
      />,
    );
    expect(
      screen.queryByText('Reviewer FAIL · round 1'),
    ).not.toBeInTheDocument();
  });
  it('shows technical error separately without creating a FAIL', () => {
    const r = historyRun();
    r.workflow!.reviews = [];
    r.workflow!.call_records![0].error_type = 'ProviderTimeout';
    render(
      <TaskHistory
        project={snapshot.project}
        run={r}
        taskId="t0-0"
        operations={[
          {
            checkpoint: { task_id: 't0-0', invocation_id: 'i1' },
          } as Inspection['operations'][number],
        ]}
        {...nav}
      />,
    );
    expect(screen.getByText(/TECHNICAL ERROR/)).toBeVisible();
    expect(screen.queryByText(/Reviewer FAIL/)).not.toBeInTheDocument();
  });
  it('navigates to protected historical artifact with stale indication', async () => {
    render(
      <TaskHistory
        project={snapshot.project}
        run={historyRun()}
        taskId="t0-0"
        operations={[]}
        {...nav}
      />,
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'Open diff / file greeting.txt · attempt 1',
      }),
    );
    expect(await screen.findByText('safe-hash')).toBeVisible();
    expect(screen.getByText(/Stale evidence/)).toBeVisible();
    expect(mocks.artifact).toHaveBeenCalledWith(
      'p1',
      'r1',
      's1',
      'greeting.txt',
    );
  });
});
describe('immutable artifacts', () => {
  it('renders added and removed diff lines', () => {
    render(<Diff content={'--- a/file\n+++ b/file\n-old\n+new'} />);
    expect(screen.getByText('+new')).toHaveClass('added');
    expect(screen.getByText('-old')).toHaveClass('removed');
  });
  it.each([
    [404, 'record not found'],
    [400, 'policy rejected'],
    [403, 'Permission denied'],
    [409, 'artifact integrity failure'],
  ])(
    'reports artifact HTTP %s without content fallback',
    async (status, message) => {
      mocks.artifact.mockRejectedValue(new APIError(message, status));
      render(
        <ArtifactViewer
          projectId="p1"
          runId="r1"
          submissionId="s1"
          path="greeting.txt"
          close={vi.fn()}
        />,
      );
      expect(await screen.findByRole('alert')).toHaveTextContent(message);
      expect(screen.queryByText('Captured text')).not.toBeInTheDocument();
    },
  );
});
describe('durable usage', () => {
  it('shows total breakdown per agent and retries separate from reviews', () => {
    render(<UsagePanel run={usage} project={usage} />);
    expect(screen.getByText('Developer usage')).toBeVisible();
    expect(screen.getAllByText('$0.004 estimated USD').length).toBe(5);
    expect(screen.getAllByText('Technical retries').length).toBe(5);
    expect(screen.getAllByText('Review rounds: 2').length).toBe(2);
  });
  it('never turns unknown usage and cost into zero', () => {
    const u = {
      ...usage,
      estimated_cost: null,
      total_tokens: null,
      per_agent: {},
    };
    render(<UsagePanel run={u} project={u} />);
    expect(
      screen.getAllByText('Unavailable / Incomplete').length,
    ).toBeGreaterThan(1);
    expect(screen.queryByText(/\$0/)).not.toBeInTheDocument();
  });
  it('repeated replay refreshes replace totals without increments', () => {
    const view = render(<UsagePanel run={usage} project={usage} />);
    view.rerender(<UsagePanel run={copy(usage)} project={copy(usage)} />);
    expect(screen.getAllByText('$0.004 estimated USD').length).toBe(5);
    expect(screen.queryByText('$0.008 estimated USD')).not.toBeInTheDocument();
  });
});
describe('future configuration', () => {
  it('supports provider slugs and only supported future-run fields', async () => {
    const refresh = vi.fn(async () => {});
    render(<SettingsPanel project={snapshot.project} refresh={refresh} />);
    fireEvent.change(await screen.findByLabelText('Model slug'), {
      target: { value: 'anthropic/new-model' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'Save future configuration' }),
    );
    await waitFor(() => expect(mocks.save).toHaveBeenCalled());
    expect(mocks.save.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        expected_version: 3,
        kind: 'developer',
        model: 'anthropic/new-model',
      }),
    );
    expect(await screen.findByText(/Saved for future runs/)).toBeVisible();
    expect(screen.queryByLabelText(/API key/i)).not.toBeInTheDocument();
  });
  it.each([
    [409, 'Stale project version'],
    [400, 'Backend policy rejected'],
  ])(
    'shows settings rejection %s and refreshes without auto retry',
    async (status, message) => {
      mocks.save.mockRejectedValue(new APIError(message, status));
      const refresh = vi.fn(async () => {});
      render(<SettingsPanel project={snapshot.project} refresh={refresh} />);
      await screen.findByLabelText('Model slug');
      fireEvent.click(
        screen.getByRole('button', { name: 'Save future configuration' }),
      );
      expect(await screen.findByRole('alert')).toHaveTextContent(message);
      await waitFor(() => expect(refresh).toHaveBeenCalled());
      expect(mocks.save).toHaveBeenCalledTimes(1);
    },
  );
  it('uncertain save retries the exact body and key', async () => {
    mocks.save.mockRejectedValueOnce(
      new APIError('Unknown outcome', 502, true),
    );
    render(
      <SettingsPanel
        project={snapshot.project}
        refresh={vi.fn(async () => {})}
      />,
    );
    await screen.findByLabelText('Model slug');
    fireEvent.click(
      screen.getByRole('button', { name: 'Save future configuration' }),
    );
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Retry same settings command',
      }),
    );
    await waitFor(() => expect(mocks.save).toHaveBeenCalledTimes(2));
    expect(mocks.save.mock.calls[1]).toEqual(mocks.save.mock.calls[0]);
  });
  it('ignores secret values even if extra fields are injected', async () => {
    mocks.settings.mockResolvedValue({
      ...settings,
      OPENROUTER_API_KEY: 'SECRET_SENTINEL',
      agents: settings.agents.map((a) => ({
        ...a,
        private_reasoning: 'PRIVATE_SENTINEL',
      })),
    });
    render(
      <SettingsPanel
        project={snapshot.project}
        refresh={vi.fn(async () => {})}
      />,
    );
    await screen.findByLabelText('Model slug');
    expect(document.body).not.toHaveTextContent('SECRET_SENTINEL');
    expect(document.body).not.toHaveTextContent('PRIVATE_SENTINEL');
    expect(
      screen.getByText('Provider credentials: Configured (backend only)'),
    ).toBeVisible();
  });
});
describe('recovery decisions', () => {
  it('shows uncertain intervention and performs no automatic resume', () => {
    const command = vi.fn();
    render(
      <RecoveryPanel inspection={recovery} command={command} busy={false} />,
    );
    expect(screen.getByText('command · UNCERTAIN')).toBeVisible();
    expect(
      screen.getByRole('button', { name: 'Resume when safe' }),
    ).toBeDisabled();
    expect(command).not.toHaveBeenCalled();
  });
  it('requires reason and quiescence for backend-advertised acknowledgment', () => {
    const command = vi.fn(async () => {});
    render(
      <RecoveryPanel inspection={recovery} command={command} busy={false} />,
    );
    fireEvent.change(screen.getByLabelText('Recovery reason op1'), {
      target: { value: 'Confirmed process stopped' },
    });
    expect(
      screen.getByRole('button', { name: 'Acknowledge uncertain command' }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(
      screen.getByRole('button', { name: 'Acknowledge uncertain command' }),
    );
    expect(command).toHaveBeenCalledWith('recovery', {
      operation_id: 'op1',
      action: 'acknowledge-command',
      reason: 'Confirmed process stopped',
      expected_epoch: 2,
      quiescent: true,
    });
  });
  it('resolved issue still requires explicit resume and retains uncertainty', () => {
    const info = copy(recovery);
    info.recovery!.issues[0].resolved = true;
    const command = vi.fn(async () => {});
    render(<RecoveryPanel inspection={info} command={command} busy={false} />);
    expect(command).not.toHaveBeenCalled();
    expect(
      screen.getByText(/Uncertain outcomes remain uncertain/),
    ).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Resume when safe' }));
    expect(command).toHaveBeenCalledWith('resume', { expected_epoch: 2 });
  });
  it('does not offer unadvertised policy overrides', () => {
    const info = copy(recovery);
    info.available_actions = {};
    render(<RecoveryPanel inspection={info} command={vi.fn()} busy={false} />);
    expect(
      screen.queryByRole('button', { name: 'Acknowledge uncertain command' }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/No browser-supported resolution/)).toBeVisible();
  });
});
describe('tool receipts', () => {
  it('shows backend timeout cleanup logs and trusted local limits', () => {
    const r = copy(run);
    r.workflow!.command_results = [
      {
        id: 'cmd1',
        approval_id: 'approved1',
        request: permission.request,
        outcome: 'timed_out',
        is_test: true,
        exit_code: null,
        stdout: 'bounded output',
        stderr: 'timeout',
        started_at: '2026-10-05',
        duration_seconds: 10,
        stdout_truncated: true,
        stderr_truncated: false,
        cleanup_complete: true,
      },
    ];
    render(<ToolActivity run={r} inspection={null} onTask={nav.onTask} />);
    expect(screen.getByText(/Trusted local execution/)).toBeVisible();
    expect(screen.getAllByText(/timed_out/).length).toBe(2);
    expect(screen.getByText('bounded output')).toBeInTheDocument();
    expect(screen.getByText(/stdout/)).toHaveTextContent('truncated');
  });
});
