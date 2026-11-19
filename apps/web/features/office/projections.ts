import type { AgentKind, DomainEvent, Run } from '@/lib/api/types';
export const roles: AgentKind[] = ['manager', 'developer', 'reviewer'];
export const roleName = (kind: AgentKind) =>
  kind[0].toUpperCase() + kind.slice(1);
export type OfficeStatus =
  | 'Idle'
  | 'Thinking'
  | 'Working'
  | 'Waiting'
  | 'Reviewing'
  | 'Blocked'
  | 'Done'
  | 'Error';
export const statusIcon: Record<OfficeStatus, string> = {
  Idle: '○',
  Thinking: '···',
  Working: '⌨',
  Waiting: 'Ⅱ',
  Reviewing: '☑',
  Blocked: '!',
  Done: '✓',
  Error: '×',
};
export type HandoffKind =
  'assignment' | 'submission' | 'review' | 'revision' | 'accepted';
export type ReviewVerdict = 'PASS' | 'FAIL';
export type OfficeHandoff = {
  from: AgentKind;
  to: AgentKind;
  label: string;
  kind: HandoffKind;
  verdict?: ReviewVerdict;
  event: DomainEvent;
};
export function agentState(kind: AgentKind, run?: Run) {
  const active: AgentKind | null =
    run?.phase === 'develop'
      ? 'developer'
      : run?.phase === 'review'
        ? 'reviewer'
        : ['plan', 'assign', 'decide', 'final'].includes(run?.phase || '')
          ? 'manager'
          : null;
  const taskId = active === kind ? run?.current_task_id || null : null;
  const result = (status: OfficeStatus, reason: string) => ({
    status,
    reason,
    taskId,
  });
  if (!run) return result('Idle', 'No run started');
  if (run.status === 'completed') return result('Done', 'Run completed');
  if (run.status === 'failed')
    return result(
      'Error',
      run.workflow?.blocked_reason || 'Run failed; inspect retained evidence',
    );
  if (run.status === 'canceled') return result('Waiting', 'Run canceled');
  if (run.workflow?.recovery?.requires_resume)
    return result(
      'Blocked',
      'Recovery requires inspection and explicit resume',
    );
  if (run.status === 'paused')
    return result('Waiting', 'Run paused at a safe boundary');
  if (run.workflow?.pending_permissions.length)
    return result(
      kind === 'developer' ? 'Blocked' : 'Waiting',
      'Waiting for a backend permission decision',
    );
  if (run.status === 'waiting_for_user' || run.workflow?.blocked_reason)
    return result(
      kind === active ? 'Blocked' : 'Waiting',
      run.workflow?.blocked_reason || 'Run needs user input',
    );
  if (run.status === 'awaiting_approval')
    return result('Waiting', 'Plan awaits approval');
  if (kind === active && run.workflow?.pending)
    return result(
      kind === 'manager'
        ? 'Thinking'
        : kind === 'developer'
          ? 'Working'
          : 'Reviewing',
      run.status === 'pause_requested'
        ? 'Pause requested; current operation is still pending'
        : `Backend operation pending · ${run.phase}`,
    );
  return result('Idle', 'No pending operation for this employee');
}
export function handoff(event: DomainEvent, run?: Run) {
  let from: AgentKind,
    to: AgentKind,
    label: string,
    kind: HandoffKind,
    verdict: ReviewVerdict | undefined = undefined;
  switch (event.type) {
    case 'task.assigned':
      from = 'manager';
      to = 'developer';
      label = 'Task assigned';
      kind = 'assignment';
      break;
    case 'submission.admitted':
      from = 'developer';
      to = 'reviewer';
      label = 'Submission for review';
      kind = 'submission';
      break;
    case 'review.completed': {
      from = 'reviewer';
      to = 'manager';
      kind = 'review';
      const review = run?.workflow?.reviews.find(
        (r) => r.result.review_id === event.payload.review_id,
      );
      verdict = review?.result.verdict;
      label = verdict ? `${verdict} review returned` : 'Review returned';
      break;
    }
    case 'revision.requested':
      from = 'manager';
      to = 'developer';
      label = 'Revision instructions';
      kind = 'revision';
      verdict = 'FAIL';
      break;
    case 'task.accepted':
      from = 'manager';
      to = 'developer';
      label = 'Task accepted';
      kind = 'accepted';
      verdict = 'PASS';
      break;
    default:
      return null;
  }
  return { from, to, label, kind, verdict, event } satisfies OfficeHandoff;
}
export function canMove(run?: Run) {
  return Boolean(
    run &&
    ['planning', 'running', 'pause_requested'].includes(run.status) &&
    !run.workflow?.recovery?.requires_resume &&
    !run.workflow?.pending_permissions.length &&
    !run.workflow?.blocked_reason,
  );
}
