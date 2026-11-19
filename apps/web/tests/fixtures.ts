import type { DomainEvent, Permission, Run, Snapshot } from '@/lib/api/types';
export const task = {
  id: 't0-0',
  title: 'Greeting task',
  description: 'Produce a greeting.',
  acceptance_criteria: ['Greeting works'],
  assignee: 'developer' as const,
  dependencies: [],
  status: 'todo' as const,
  disposition: 'active' as const,
  revision: 1,
  version: 1,
  blocked_reason: null,
};
export const run: Run = {
  id: 'r1',
  status: 'running',
  phase: 'assign',
  current_task_id: null,
  task_ids: ['t0-0'],
  version: 2,
  plan_approved: true,
  plan: {
    summary: 'Greeting plan',
    tasks: [task],
    requirements: [],
    assumptions: ['Bounded task'],
    decisions: [],
  },
  workflow: {
    pending: null,
    pending_permissions: [],
    blocked_reason: null,
    agent_snapshots: [
      {
        agent_id: 'manager',
        kind: 'manager',
        name: 'Manager',
        role: 'Orchestrator',
      },
      {
        agent_id: 'developer',
        kind: 'developer',
        name: 'Developer',
        role: 'Software Developer',
      },
      {
        agent_id: 'reviewer',
        kind: 'reviewer',
        name: 'Reviewer',
        role: 'Quality Reviewer',
      },
    ],
    reviews: [],
    revisions: [],
    final_result: null,
    recovery: null,
  },
};
export const snapshot: Snapshot = {
  schema_version: 1,
  event_cursor: 10,
  project: {
    id: 'p1',
    name: 'Project one',
    goal: 'A bounded greeting',
    requirements: [
      {
        id: 'r1',
        description: 'Greeting',
        acceptance_criteria: ['Greeting works'],
        priority: 'normal',
      },
    ],
    workspace_root: '',
    tasks: [task],
    runs: [run],
    active_run_id: 'r1',
    version: 3,
  },
};
export const event = (
  sequence: number,
  type = 'task.assigned',
): DomainEvent => ({
  schema_version: 1,
  project_id: 'p1',
  run_id: 'r1',
  task_id: 't0-0',
  sequence,
  type,
  payload: { phase: 'develop' },
});
export const permission: Permission = {
  id: 'a1',
  status: 'pending',
  reason: '',
  scope_digest: 'scope-hash',
  request: {
    actor: 'developer',
    profile: 'test',
    executable: '/usr/bin/python3',
    args: ['-I', 'test.py'],
    cwd: '.',
    environment: [],
    workspace_version: 'version-hash',
    timeout_seconds: 10,
    max_output_bytes: 8192,
    attempt_id: 'attempt-1',
  },
};
export function copy<T>(value: T): T {
  return structuredClone(value);
}
