import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import type { Action, Command } from '@/lib/api/types';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CreateProject } from '@/features/projects/CreateProject';
import { WorkspaceView } from '@/features/workspace/Workspace';
import { ProjectList } from '@/features/projects/ProjectList';
import { Permissions } from '@/features/workspace/Permissions';
import { copy, event, permission, snapshot } from './fixtures';
import { initialState, type State } from '@/lib/state/reducer';
const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  create: vi.fn(),
  projects: vi.fn(),
  useProject: vi.fn(),
}));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock('@/lib/api/client', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  createProject: mocks.create,
  getProjects: mocks.projects,
}));
vi.mock('@/lib/state/context', () => ({
  useProject: mocks.useProject,
  ProjectProvider: ({ children }: { children: React.ReactNode }) => children,
}));
let state: State;
let command: Mock<(action: Action, extra?: Partial<Command>) => Promise<void>>;
function view() {
  mocks.useProject.mockReturnValue({
    state,
    permissions: [permission],
    command,
    refresh: vi.fn(),
    retry: vi.fn(),
    select: vi.fn(),
  });
  return render(<WorkspaceView />);
}
beforeEach(() => {
  vi.clearAllMocks();
  state = {
    ...copy(initialState),
    snapshot: copy(snapshot),
    cursor: 10,
    connection: 'connected',
  };
  command = vi.fn(async () => {});
  mocks.projects.mockResolvedValue([snapshot.project]);
});
describe('browser workflow UI', () => {
  it('lists and opens persisted projects', async () => {
    render(<ProjectList />);
    expect(
      await screen.findByRole('link', { name: /Project one/ }),
    ).toHaveAttribute('href', '/projects/p1');
  });
  it('creates with goal and structured requirements through FastAPI', async () => {
    mocks.create.mockResolvedValue({
      project_id: 'created',
      status: 'applied',
    });
    render(<CreateProject />);
    fireEvent.change(screen.getByLabelText('Project name'), {
      target: { value: 'Greeting' },
    });
    fireEvent.change(screen.getByLabelText('Goal'), {
      target: { value: 'Say hello' },
    });
    fireEvent.change(screen.getByLabelText('Requirement 1 description'), {
      target: { value: 'Greeting' },
    });
    fireEvent.change(
      screen.getByLabelText('Requirement 1 acceptance criteria'),
      { target: { value: 'Contains hello\nContains world' } },
    );
    fireEvent.click(screen.getByRole('button', { name: 'Create project' }));
    await waitFor(() =>
      expect(mocks.push).toHaveBeenCalledWith('/projects/created'),
    );
    expect(
      mocks.create.mock.calls[0][0].requirements[0].acceptance_criteria,
    ).toEqual(['Contains hello', 'Contains world']);
    expect(mocks.create.mock.calls[0][0]).not.toHaveProperty('workspace_root');
  });
  it('requests Manager planning', () => {
    state.snapshot!.project.runs = [];
    view();
    fireEvent.click(
      screen.getByRole('button', { name: 'Request Manager planning' }),
    );
    expect(command).toHaveBeenCalledWith('plan');
  });
  it('displays structured plan and calls approval', () => {
    state.snapshot!.project.runs[0].status = 'awaiting_approval';
    view();
    expect(screen.getByText('Greeting plan')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Approve plan' }));
    expect(command).toHaveBeenCalledWith('approve');
  });
  it('calls start without changing task state locally', () => {
    view();
    fireEvent.click(
      screen.getByRole('button', { name: 'Start / Continue execution' }),
    );
    expect(command).toHaveBeenCalledWith('start');
    expect(screen.getByTestId('task-t0-0')).toHaveTextContent('TODO');
  });
  it('renders task changes and review counts from snapshots', () => {
    state.snapshot!.project.tasks[0].status = 'review';
    state.snapshot!.project.runs[0].workflow!.reviews = [
      {
        task_id: 't0-0',
        submission_id: 's',
        number: 1,
        result: { review_id: 'rev', verdict: 'FAIL', summary: 'Defect' },
      },
    ];
    view();
    expect(screen.getByTestId('task-t0-0')).toHaveTextContent('REVIEW');
    expect(screen.getByTestId('task-t0-0')).toHaveTextContent('Reviews: 1');
  });
  it('shows Pause requested separately from authoritative running status', () => {
    state.pending = {
      k: { key: 'k', action: 'pause', status: 'pending', baseline: 3 },
    };
    view();
    expect(screen.getByText(/Pause requested — waiting/)).toBeInTheDocument();
    expect(screen.getByTestId('run-status')).toHaveTextContent('running');
  });
  it('renders actual Paused confirmation and Resume', () => {
    state.snapshot!.project.runs[0].status = 'paused';
    view();
    expect(screen.getByTestId('run-status')).toHaveTextContent('paused');
    fireEvent.click(screen.getByRole('button', { name: 'Resume' }));
    expect(command).toHaveBeenCalledWith('resume', {});
  });
  it('calls cancel and leaves state unchanged until snapshot', () => {
    view();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel / Stop run' }));
    expect(command).toHaveBeenCalledWith('cancel');
    expect(screen.getByTestId('run-status')).toHaveTextContent('running');
  });
  it('renders final summary, tasks, limitations and evidence link', () => {
    const run = state.snapshot!.project.runs[0];
    run.status = 'completed';
    run.workflow!.final_result = {
      summary: 'Greeting accepted',
      completed_task_ids: ['t0-0'],
      evidence_refs: ['s1'],
      limitations: ['Synthetic fixture'],
    };
    view();
    expect(
      screen.getByRole('heading', { name: 'Final result' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Greeting accepted')).toBeInTheDocument();
    expect(screen.getByText('Synthetic fixture')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Open backend evidence JSON' }),
    ).toHaveAttribute('href', '/api/backend/projects/p1/runs/r1/evidence');
  });
  it('shows disconnect and stale version errors', () => {
    state.connection = 'disconnected';
    state.error =
      'Stale project version. State refreshed; review it before retrying.';
    view();
    expect(screen.getByTestId('connection')).toHaveTextContent(
      'SSE disconnected',
    );
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Stale project version',
    );
  });
  it('exposes blocked input and recovery requirements without resolving locally', () => {
    const run = state.snapshot!.project.runs[0];
    run.status = 'waiting_for_user';
    run.workflow!.blocked_reason = 'Clarify requested scope';
    run.workflow!.recovery = {
      requires_resume: true,
      epoch: 2,
      issues: [{ id: 'i', reason: 'Unknown provider result', resolved: false }],
    };
    view();
    expect(screen.getByText('Clarify requested scope')).toBeInTheDocument();
    expect(screen.getByText('Unknown provider result')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Resume' })).toBeDisabled();
  });
  it('renders only committed activity and deduplicated IDs', () => {
    state.events = [event(11, 'revision.requested')];
    view();
    expect(screen.getByText('Revision requested')).toBeInTheDocument();
    expect(document.querySelectorAll('[data-event-id="11"]')).toHaveLength(1);
  });
  it('shows explicit unsupported workspace and plan editing limits', () => {
    render(<CreateProject />);
    expect(screen.getByLabelText('Workspace')).toBeDisabled();
    expect(
      screen.getByText(/Browser selection is unavailable/),
    ).toBeInTheDocument();
  });
});
describe('permission decisions', () => {
  it('displays exact action, command, scope and limits', () => {
    render(
      <Permissions
        permissions={[permission]}
        pendingIds={['a1']}
        busy={false}
        command={command}
      />,
    );
    expect(screen.getByText('Permission required: test')).toBeInTheDocument();
    expect(screen.getByText('/usr/bin/python3 -I test.py')).toBeInTheDocument();
    expect(screen.getByText('scope-hash')).toBeInTheDocument();
  });
  it('requires a reason and submits approval to the existing API', () => {
    render(
      <Permissions
        permissions={[permission]}
        pendingIds={['a1']}
        busy={false}
        command={command}
      />,
    );
    expect(
      screen.getByRole('button', { name: 'Approve permission' }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Decision reason a1'), {
      target: { value: 'Inspected' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Approve permission' }));
    expect(command).toHaveBeenCalledWith('permission', {
      approval_id: 'a1',
      approved: true,
      reason: 'Inspected',
    });
    expect(screen.getByText('Permission required: test')).toBeInTheDocument();
  });
  it('submits denial without granting itself access', () => {
    render(
      <Permissions
        permissions={[permission]}
        pendingIds={['a1']}
        busy={false}
        command={command}
      />,
    );
    fireEvent.change(screen.getByLabelText('Decision reason a1'), {
      target: { value: 'Unsafe scope' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Deny permission' }));
    expect(command).toHaveBeenCalledWith('permission', {
      approval_id: 'a1',
      approved: false,
      reason: 'Unsafe scope',
    });
  });
  it('displays a rejected decision and leaves the request pending', () => {
    state.snapshot!.project.runs[0].workflow!.pending_permissions = ['a1'];
    state.error = 'Command or request rejected. approval scope changed';
    view();
    expect(screen.getByRole('alert')).toHaveTextContent(
      'approval scope changed',
    );
    expect(
      screen.getByRole('button', { name: 'Approve permission' }),
    ).toBeInTheDocument();
  });
  it('displays persisted permission denied status', () => {
    render(
      <Permissions
        permissions={[{ ...permission, status: 'denied', reason: 'Unsafe' }]}
        pendingIds={[]}
        busy={false}
        command={command}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent(
      'Permission denied: test. Unsafe',
    );
    expect(
      screen.queryByRole('button', { name: 'Approve permission' }),
    ).not.toBeInTheDocument();
  });
});
