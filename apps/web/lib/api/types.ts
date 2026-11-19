import type { components } from './openapi';
export type CreateProject = components['schemas']['CreateProject'];
export type Command = components['schemas']['Command'];
export type Acknowledgement = components['schemas']['CommandAcknowledgement'];
export type Requirement = components['schemas']['RequirementInput'];
// OpenAPI deliberately leaves the authoritative domain document as a dict.
// These read projections mirror domain/*.to_dict; they never implement transitions.
export type TaskStatus =
  'backlog' | 'todo' | 'in_progress' | 'review' | 'done' | 'blocked';
export type RunStatus =
  | 'draft'
  | 'planning'
  | 'awaiting_approval'
  | 'running'
  | 'pause_requested'
  | 'paused'
  | 'waiting_for_user'
  | 'completed'
  | 'failed'
  | 'canceled';
export type AgentKind = 'manager' | 'developer' | 'reviewer';
export interface Task {
  id: string;
  title: string;
  description: string;
  acceptance_criteria: string[];
  assignee: AgentKind;
  dependencies: string[];
  status: TaskStatus;
  disposition: 'active' | 'canceled';
  revision: number;
  version: number;
  blocked_reason: string | null;
}
export interface Agent {
  agent_id: string;
  kind: AgentKind;
  name: string;
  role: string;
  model?: string;
  tools?: string[];
  permissions?: string[];
  config_digest?: string;
}
export interface Review {
  task_id: string;
  submission_id: string;
  number: number;
  submission_version?: number;
  result: {
    review_id: string;
    verdict: 'PASS' | 'FAIL';
    summary: string;
    assessments?: Array<{
      criterion_id: string;
      passed: boolean;
      evidence: string;
      notes: string;
    }>;
    findings?: Array<{
      id: string;
      severity: string;
      summary: string;
      evidence: string;
      criterion_id: string | null;
    }>;
    checks_not_performed?: string[];
  };
}
export interface FinalResult {
  summary: string;
  completed_task_ids: string[];
  evidence_refs: string[];
  limitations: string[];
}
export interface Recovery {
  requires_resume: boolean;
  epoch: number;
  issues: Array<{
    id: string;
    reason: string;
    resolved: boolean;
    kind?: string;
    certainty?: string;
    resolution?: string;
  }>;
}
export interface Workflow {
  pending: string | null;
  pending_permissions: string[];
  blocked_reason: string | null;
  agent_snapshots: Agent[];
  reviews: Review[];
  revisions: Revision[];
  attempts?: Attempt[];
  submissions?: Submission[];
  invocation_records?: Invocation[];
  call_records?: CallRecord[];
  command_results?: CommandResult[];
  final_result: FinalResult | null;
  recovery: Recovery | null;
}
export interface Plan {
  summary: string;
  tasks: Array<
    Omit<
      Task,
      'status' | 'disposition' | 'revision' | 'version' | 'blocked_reason'
    >
  >;
  requirements: Requirement[];
  assumptions: string[];
  decisions: Array<{ id: string; summary?: string; description?: string }>;
}
export interface Run {
  id: string;
  status: RunStatus;
  phase: string;
  current_task_id: string | null;
  task_ids: string[];
  plan: Plan | null;
  plan_approved: boolean;
  workflow: Workflow | null;
  version: number;
}
export interface Project {
  id: string;
  name: string;
  goal: string;
  requirements: Requirement[];
  workspace_root: string;
  tasks: Task[];
  runs: Run[];
  active_run_id: string | null;
  version: number;
}
export interface Snapshot {
  schema_version: 1;
  project: Project;
  event_cursor: number;
}
export interface DomainEvent {
  event_id?: string; // Committed backend identity; missing identities never animate.
  schema_version: number;
  project_id: string;
  run_id: string | null;
  task_id: string | null;
  sequence: number;
  type: string;
  occurred_at?: string;
  payload: Record<string, unknown>;
}
export interface Permission {
  id: string;
  status: 'pending' | 'approved' | 'denied' | 'consumed';
  reason: string;
  scope_digest: string;
  request: {
    actor: string;
    profile: string;
    executable: string;
    args: string[];
    cwd: string;
    environment?: Array<[string, string]>;
    workspace_version: string;
    timeout_seconds: number;
    max_output_bytes: number;
    attempt_id: string;
  };
}
export type Action =
  | 'plan'
  | 'approve'
  | 'start'
  | 'pause'
  | 'resume'
  | 'cancel'
  | 'permission'
  | 'recovery';
export const apiBase = '/api/backend';
export const projectPath = (id: string) =>
  `/projects/${encodeURIComponent(id)}`;

export interface AgentConfiguration extends Agent {
  id?: string;
  model: string;
  system_instructions: string;
  tools: string[];
  permissions: string[];
  config_version: number;
  config_digest?: string;
}
export interface Settings {
  project_version: number;
  applies_to: 'next_run';
  agents: AgentConfiguration[];
  editable_fields: string[];
  provider_configured: boolean;
  note: string;
}
export type SettingsCommand = components['schemas']['AgentSettings'];
export interface UsageTotals {
  provider_calls: number;
  retries: number;
  total_tokens: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cached_input_tokens: number | null;
  estimated_cost: string | null;
  usage_complete: boolean;
  cost_complete: boolean;
  known_tokens: number;
  known_estimated_cost: string;
}
export interface Usage extends UsageTotals {
  reviews: number;
  per_agent: Record<string, UsageTotals>;
}
export interface CallRecord {
  call_id: string;
  invocation_id: string;
  model: string;
  purpose: string;
  attempt: number;
  status: string;
  error_type?: string | null;
  usage: {
    input_tokens: number;
    output_tokens: number;
    cached_input_tokens: number;
  } | null;
  estimated_cost: { amount: string } | null;
}
export interface Invocation {
  id: string;
  agent_id: string;
  phase: string;
  generation: number;
  config_digest: string;
}
export interface Attempt {
  id: string;
  task_id: string;
  number: number;
  generation: number;
}
export interface FileEvidence {
  path: string;
  content: string;
  diff: string;
  before: string | null;
}
export interface CommandResult {
  id: string;
  approval_id: string;
  request: Permission['request'];
  outcome: string;
  is_test: boolean;
  exit_code: number | null;
  stdout: string;
  stderr: string;
  started_at: string;
  duration_seconds: number;
  stdout_truncated: boolean;
  stderr_truncated: boolean;
  cleanup_complete: boolean;
}
export interface Submission {
  id: string;
  task_id: string;
  attempt_id: string;
  version: number;
  digest: string;
  generation: number;
  output: {
    summary: string;
    changed_files: Array<{
      path: string;
      change_type: string;
      summary: string;
    }>;
    tests: Array<{ name: string; status: string; summary: string }>;
    notes: string[];
  };
  files: {
    files: FileEvidence[];
    tests: Array<{
      result: CommandResult;
      stale: boolean;
      workspace_version: string;
    }>;
    workspace_version: string;
  } | null;
}
export interface Revision {
  task_id: string;
  submission_id: string;
  review_id: string;
  required_fixes: string[];
  remaining_review_rounds: number;
}
export interface Operation {
  id: string;
  kind: string;
  operation: string;
  stage: string;
  certainty: string;
  path: string;
  started_at: string;
  updated_at: string;
  approval_id: string | null;
  checkpoint: {
    task_id: string | null;
    attempt_id: string | null;
    phase: string;
    generation: number;
    invocation_id: string | null;
  };
  request: Permission['request'] | null;
  call_record: CallRecord | null;
}
export interface RecoveryInspection {
  phase: string;
  checkpoint: Operation['checkpoint'] | null;
  recovery: Recovery | null;
  operations: Operation[];
  available_actions: Record<
    string,
    Array<{ action: string; label: string; requires_quiescent: boolean }>
  >;
}
export interface Inspection {
  recent_events?: DomainEvent[];
  capabilities?: Record<
    AgentKind,
    {
      files: Record<string, { allowed: boolean; reason: string }>;
      command_request: { allowed: boolean; reason: string };
    }
  > | null;
  usage: Usage;
  project_usage: Usage;
  settings: Settings;
  tools: Array<{
    id: string;
    actor: string;
    operation?: string;
    action?: string;
    attempt_id: string;
    outcome: string;
    path?: string;
    reason?: string;
  }>;
  operations: Operation[];
  recovery: RecoveryInspection;
  limits: Record<string, number> | null;
}
export interface Artifact {
  artifact_id: string;
  submission_id: string;
  task_id: string;
  attempt_id: string;
  version: number;
  path: string;
  content_hash: string;
  before_hash: string | null;
  diff: string;
  content: string;
  created_at: string | null;
}
