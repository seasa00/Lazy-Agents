"""Human commands applied atomically at workflow boundaries."""
from dataclasses import replace
from datetime import datetime, timezone
import json
from app.agents.contracts import Requirement
from app.domain.events import DomainEvent
from app.domain.projects import RunStatus
from app.domain.tasks import TaskStatus, TaskDisposition
from app.domain.recovery import checkpoint


def commit_run(project, run, event_type, *, tasks=None, payload=None):
    run = replace(run, version=project.run(run.id).version + 1)
    if run.workflow is not None:
        run = replace(run, workflow=replace(run.workflow, checkpoint=checkpoint(project, run, event_type)))
    runs = tuple(run if r.id == run.id else r for r in project.runs)
    after = replace(project, runs=runs, tasks=project.tasks if tasks is None else tuple(tasks),
                    active_run_id=next((r.id for r in runs if r.active), None))
    event = DomainEvent(project.id, event_type, {'run_version': run.version, **(payload or {})},
                        run_id=run.id, task_id=run.current_task_id)
    return after, (event,)


def block_state(project, run, reason, *, keep_pending=False, exhausted_limit=False):
    wf = replace(run.workflow, blocked_reason=reason, resume_phase=run.phase,
                 exhausted_limit=run.workflow.exhausted_limit or exhausted_limit,
                 pending=run.workflow.pending if keep_pending else None)
    tasks = tuple(replace(t, status=TaskStatus.BLOCKED, blocked_reason=reason,
                          resume_phase=t.status, version=t.version + 1)
                  if t.id == run.current_task_id else t for t in project.tasks)
    return commit_run(project, replace(run, workflow=wf, status=RunStatus.WAITING_FOR_USER),
                      'run.blocked', tasks=tasks, payload={'reason': reason})


class WorkflowControls:
    def __init__(self, store, project_id, run_id, *, command_gateway=None):
        self.store, self.project_id, self.run_id = store, project_id, run_id
        self.command_gateway = command_gateway

    def resolve_command(self, approval_id, *, approved, reason):
        """Explicit human decision on one exact pending permission intervention."""
        if self.command_gateway is None:
            raise ValueError('no command gateway configured')
        def apply(p, r):
            continuation = next((c for c in r.workflow.tool_continuations
                                 if c.permission_id == approval_id), None)
            approval = next((a for a in self.command_gateway.approvals if a.id == approval_id), None)
            if approval_id not in r.workflow.pending_permissions:
                if continuation and approved and continuation.state in {'APPROVED_PENDING_EXECUTION', 'TOOL_COMPLETED', 'COMPLETED'}:
                    return commit_run(p, r, 'command.permission_duplicate',
                        payload={'approval_id': approval_id, 'approved': True,
                                 'continuation_id': continuation.id})
                if continuation and not approved and continuation.state in {'TOOL_COMPLETED', 'COMPLETED', 'STALE', 'CANCELED'}:
                    return commit_run(p, r, 'command.permission_duplicate',
                        payload={'approval_id': approval_id, 'approved': False,
                                 'continuation_id': continuation.id})
                if continuation and continuation.state == 'WAITING_FOR_APPROVAL' and approval and (
                        (approved and approval.status == 'approved') or
                        (not approved and approval.status == 'denied')):
                    # Recover the small durable boundary between recording the
                    # intervention decision and committing workflow continuation.
                    pass
                else:
                    raise ValueError('permission intervention is not pending on this run')
            invocation = next((i for i in r.workflow.invocation_records
                               if continuation and i.id == continuation.invocation_id), None)
            expected_profile = (json.loads(continuation.arguments_json).get('profile') if continuation else None)
            if continuation and (continuation.generation != r.execution_generation
                                 or continuation.task_id != r.current_task_id
                                 or invocation is None or invocation.agent_id != continuation.agent_id
                                 or approval is None or approval.request.attempt_id != continuation.attempt_id
                                 or approval.request.generation != continuation.generation
                                 or approval.request.profile != expected_profile):
                decision = (self.command_gateway.resolve_command(approval_id, approved=False,
                    reason='stale developer continuation') if approval and approval.status == 'pending'
                    else approval)
                updated = replace(continuation, state='STALE', updated_at=datetime.now(timezone.utc).isoformat())
                values = tuple(updated if c.id == updated.id else c for c in r.workflow.tool_continuations)
                wf = replace(r.workflow, pending_permissions=tuple(x for x in r.workflow.pending_permissions if x != approval_id),
                             tool_continuations=values)
                return commit_run(p, replace(r, workflow=wf), 'developer.continuation_stale',
                    payload={'continuation_id': updated.id, 'approval_id': approval_id,
                             'decision': decision.status})
            if approval is None:
                raise ValueError('permission intervention is unavailable')
            if approval.status == 'pending':
                decision = self.command_gateway.resolve_command(approval_id, approved=approved, reason=reason)
            elif (approved and approval.status == 'approved') or (not approved and approval.status == 'denied'):
                decision = approval
            else:
                raise ValueError('permission decision conflicts with the recorded intervention')
            wf = replace(r.workflow, pending_permissions=tuple(x for x in r.workflow.pending_permissions if x != approval_id))
            status = r.status
            if continuation:
                now = datetime.now(timezone.utc).isoformat()
                if approved:
                    updated = replace(continuation, state='APPROVED_PENDING_EXECUTION', updated_at=now)
                else:
                    result = {'outcome': 'denied', 'approval_id': approval_id, 'reason': decision.reason}
                    updated = replace(continuation, state='TOOL_COMPLETED',
                        result_json=json.dumps(result, sort_keys=True, separators=(',', ':')),
                        updated_at=now)
                wf = replace(wf, tool_continuations=tuple(updated if c.id == updated.id else c
                                                          for c in wf.tool_continuations))
                if status is RunStatus.WAITING_FOR_USER:
                    status = RunStatus.RUNNING
                    wf = replace(wf, blocked_reason=None, resume_phase=None)
            return commit_run(p, replace(r, workflow=wf, status=status), 'command.permission_decided',
                              payload={'approval_id': approval_id, 'approved': approved,
                                       'reason': decision.reason,
                                       'continuation_id': continuation.id if continuation else None})
        return self._change(apply)

    def _change(self, fn):
        def change(p):
            r = p.run(self.run_id)
            if r.workflow is None or not r.active:
                raise ValueError('control requires an active workflow')
            return fn(p, r)
        return self.store.atomic_update(self.project_id, change)

    def pause(self):
        def apply(p, r):
            if r.status is not RunStatus.RUNNING:
                raise ValueError('pause requires running state')
            status = RunStatus.PAUSE_REQUESTED if r.workflow.pending else RunStatus.PAUSED
            return commit_run(p, replace(r, status=status), 'run.' + status.value)
        return self._change(apply)

    def resume(self, *, expected_epoch=None):
        from app.orchestration.recovery import RecoveryCoordinator
        recovery = RecoveryCoordinator(self.store)
        recovery.ensure_startup(self.project_id, self.run_id)
        r = self.store.get_run_metadata(self.project_id, self.run_id)
        if r.workflow and r.workflow.recovery and r.workflow.recovery.requires_resume:
            recovery.resume(self.project_id, self.run_id, expected_epoch=expected_epoch)
            def activate(p):
                current = p.run(self.run_id)
                resumable = any(c.state in {'APPROVED_PENDING_EXECUTION', 'TOOL_COMPLETED'}
                                for c in current.workflow.tool_continuations)
                if resumable and current.status is RunStatus.WAITING_FOR_USER:
                    return commit_run(p, replace(current, status=RunStatus.RUNNING,
                        workflow=replace(current.workflow, blocked_reason=None, resume_phase=None)),
                        'developer.continuation_resumed')
                return commit_run(p, current, 'run.resume_reconciled')
            return self.store.atomic_update(self.project_id, activate).run(self.run_id)
        def apply(p, r):
            if r.status is not RunStatus.PAUSED or r.workflow.pending:
                raise ValueError('resume requires paused state; blocked work needs resolution')
            return commit_run(p, replace(r, status=RunStatus.RUNNING), 'run.resumed')
        return self._change(apply)

    def cancel(self):
        def apply(p, r):
            if self.command_gateway:
                self.command_gateway.invalidate_commands('run canceled')
            tasks = tuple(replace(t, disposition=TaskDisposition.CANCELED, version=t.version + 1)
                          if t.id in r.task_ids and not t.is_completed else t for t in p.tasks)
            now = datetime.now(timezone.utc).isoformat()
            continuations = tuple(replace(c, state='CANCELED', updated_at=now)
                if c.state not in {'COMPLETED', 'CANCELED', 'STALE', 'FAILED'} else c
                for c in r.workflow.tool_continuations)
            r = replace(r, status=RunStatus.CANCELED, execution_generation=r.execution_generation + 1,
                        workflow=replace(r.workflow, pending_permissions=(), tool_continuations=continuations))
            return commit_run(p, r, 'run.canceled', tasks=tasks)
        return self._change(apply)

    def instruct(self, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError('instruction must contain 1..4000 characters')
        def apply(p, r):
            if len(r.workflow.instructions) + len(r.workflow.pending_instructions) >= 20:
                raise ValueError('instruction limit reached')
            wf = replace(r.workflow, pending_instructions=(*r.workflow.pending_instructions, text))
            return commit_run(p, replace(r, workflow=wf), 'instruction.queued')
        return self._change(apply)

    def block(self, reason):
        if not reason.strip():
            raise ValueError('block reason is required')
        return self._change(lambda p, r: block_state(p, r, reason, keep_pending=True))

    def resolve(self):
        """Resume the same phase; never erase history or replenish budgets."""
        def apply(p, r):
            if r.status is not RunStatus.WAITING_FOR_USER or r.workflow.pending:
                raise ValueError('resolution requires blocked work')
            wf = r.workflow
            if self.store.needs_recovery(self.project_id, self.run_id) or (wf.recovery and wf.recovery.requires_resume):
                raise ValueError('restart requires recovery resolution and explicit resume')
            if wf.exhausted_limit:
                raise ValueError('exhausted limits cannot be reset by resolution')
            tasks = tuple(replace(t, status=t.resume_phase or TaskStatus.TODO, blocked_reason=None,
                                  resume_phase=None, version=t.version + 1)
                          if t.id == r.current_task_id else t for t in p.tasks)
            return commit_run(p, replace(r, status=RunStatus.RUNNING,
                workflow=replace(wf, blocked_reason=None, resume_phase=None)), 'run.resolved', tasks=tasks)
        return self._change(apply)

    def change_scope(self, requirements=None, config_snapshot=None):
        """Conservatively invalidate all tasks: M1 plans have no requirement/task map."""
        parsed = None if requirements is None else tuple(Requirement.from_dict(x.to_dict()) for x in requirements)
        if parsed is not None and (not parsed or len({x.id for x in parsed}) != len(parsed)):
            raise ValueError('requirements must be nonempty with unique ids')
        def apply(p, r):
            if self.store.needs_recovery(self.project_id, self.run_id) or (r.workflow.recovery and r.workflow.recovery.requires_resume):
                raise ValueError('scope change requires resolving the recovery gate first')
            if r.status not in {RunStatus.RUNNING, RunStatus.PAUSED, RunStatus.PAUSE_REQUESTED, RunStatus.WAITING_FOR_USER}:
                raise ValueError('scope change requires an approved workflow')
            if self.command_gateway:
                self.command_gateway.invalidate_commands('execution scope changed')
            now = datetime.now(timezone.utc).isoformat()
            continuations = tuple(replace(c, state='STALE', updated_at=now)
                if c.state in {'WAITING_FOR_APPROVAL', 'APPROVED_PENDING_EXECUTION', 'TOOL_COMPLETED'} else c
                for c in r.workflow.tool_continuations)
            wf = replace(r.workflow, accepted=(), blocked_reason=None, resume_phase=None, pending_permissions=(),
                         tool_continuations=continuations)
            tasks = tuple(replace(t, status=TaskStatus.BACKLOG if t.dependencies else TaskStatus.TODO,
                                  blocked_reason=None, resume_phase=None, revision=t.revision + 1, version=t.version + 1)
                          if t.id in r.task_ids and not t.is_canceled else t for t in p.tasks)
            if parsed is not None:
                p = replace(p, requirements=parsed, requirement_version=p.requirement_version + 1)
            snapshot = r.config_snapshot if config_snapshot is None else tuple(sorted(config_snapshot.items()))
            return commit_run(p, replace(r, status=RunStatus.PAUSED, phase='assign', current_task_id=None,
                execution_generation=r.execution_generation + 1, workflow=wf, config_snapshot=snapshot),
                'scope.changed', tasks=tasks, payload={'requirement_version': p.requirement_version})
        return self._change(apply)
