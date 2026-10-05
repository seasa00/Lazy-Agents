"""Human commands applied atomically at workflow boundaries."""
from dataclasses import replace
from app.agents.contracts import Requirement
from app.domain.events import DomainEvent
from app.domain.projects import RunStatus
from app.domain.tasks import TaskStatus, TaskDisposition


def commit_run(project, run, event_type, *, tasks=None, payload=None):
    run = replace(run, version=project.run(run.id).version + 1)
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
            if approval_id not in r.workflow.pending_permissions:
                raise ValueError('permission intervention is not pending on this run')
            decision = self.command_gateway.resolve_command(approval_id, approved=approved, reason=reason)
            wf = replace(r.workflow, pending_permissions=tuple(x for x in r.workflow.pending_permissions if x != approval_id))
            return commit_run(p, replace(r, workflow=wf), 'command.permission_decided',
                              payload={'approval_id': approval_id, 'approved': approved, 'reason': decision.reason})
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

    def resume(self):
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
            r = replace(r, status=RunStatus.CANCELED, execution_generation=r.execution_generation + 1,
                        workflow=replace(r.workflow, pending_permissions=()))
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
            if r.status not in {RunStatus.RUNNING, RunStatus.PAUSED, RunStatus.PAUSE_REQUESTED, RunStatus.WAITING_FOR_USER}:
                raise ValueError('scope change requires an approved workflow')
            if self.command_gateway:
                self.command_gateway.invalidate_commands('execution scope changed')
            wf = replace(r.workflow, accepted=(), blocked_reason=None, resume_phase=None, pending_permissions=())
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
