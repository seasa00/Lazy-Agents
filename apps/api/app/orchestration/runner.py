"""Sequential bounded workflow. Providers return proposals; reducers commit facts."""
from dataclasses import replace
from uuid import uuid4
from app.agents.contracts import (
    DecisionAction, DeveloperSubmission, FileReference, ManagerPlan, ReviewReference,
    ReviewVerdict, SubmissionReference, TaskBrief, TaskSummary,
)
from app.agents.runtime import AgentRuntime, InvocationError
from app.context.builder import ProjectContext
from app.domain.agents import AgentKind, default_agent_definitions
from app.domain.projects import RunStatus
from app.domain.events import DomainEvent
from app.domain.tasks import Task, TaskStatus
from app.domain.workflow import WorkflowState
from app.domain.submissions import TaskAttempt, SubmissionManifest
from app.domain.reviews import ReviewRound, RevisionBrief
from app.orchestration.controls import commit_run, block_state, WorkflowControls
from app.orchestration.limits import ExecutionLimits, LimitExceeded
from app.orchestration.planning import validate_manager_plan
from app.tools.contracts import ToolRequest
from app.tools.memory import InMemoryToolGateway
from app.tools.gateway import FileToolRequest, WorkspaceToolGateway


class BoundaryStopped(InvocationError):
    pass


class BudgetStopped(BoundaryStopped):
    pass


class _NoOperation(Exception):
    pass


class WorkflowRunner:
    def __init__(self, store, project_id, run_id, provider, *, runtime=None, definitions=None, gateway=None):
        self.store, self.project_id, self.run_id = store, project_id, run_id
        self.provider = provider
        self.runtime = runtime or AgentRuntime()
        self.definitions = definitions or default_agent_definitions()
        self.workspace_gateway = gateway if isinstance(gateway, WorkspaceToolGateway) else None
        self.gateway = InMemoryToolGateway() if self.workspace_gateway else (gateway or InMemoryToolGateway())
        if self.workspace_gateway:
            self.workspace_gateway.before_mutation = self._guard_file_mutation
        self.controls = WorkflowControls(store, project_id, run_id, command_gateway=self.workspace_gateway)

    def request_command(self, request):
        """Developer asks; only controls.resolve_command can supply human approval."""
        gateway = self.workspace_gateway
        if gateway is None:
            raise ValueError('no workspace gateway configured')
        results, errors = [], []
        def apply(p):
            r = p.run(self.run_id)
            if r.workflow.pending:
                gateway._command_record('request', request, None, 'denied', 'operation already pending')
                errors.append(ValueError('operation already pending'))
            else:
                try:
                    approval = gateway.request_command(request)
                    results.append(approval)
                    r = replace(r, workflow=replace(r.workflow,
                        pending_permissions=(*r.workflow.pending_permissions, approval.id)))
                except ValueError as exc:
                    errors.append(exc)
            record = gateway.command_records[-1]
            return commit_run(p, r, 'command.permission_requested', payload={
                'tool_call_id': record.id, 'approval_id': record.approval_id, 'outcome': record.outcome})
        self.store.atomic_update(self.project_id, apply)
        if errors:
            raise errors[0]
        return results[0]

    def command_tool(self, request, approval_id):
        """Launch under the control lock, drain outside it, then retain every result."""
        gateway = self.workspace_gateway
        if gateway is None:
            raise ValueError('no workspace gateway configured')
        token = 'command_op_' + uuid4().hex
        running, errors = [], []
        def reserve(p):
            r = p.run(self.run_id)
            if r.workflow.pending or r.workflow.pending_permissions or len(r.workflow.command_results) >= gateway.command_limits.max_commands:
                gateway._command_record('launch', request, approval_id, 'denied', 'pending operation/permission or command limit')
                errors.append(ValueError('pending operation/permission or command limit'))
            else:
                try:
                    running.append(gateway.start_command(request, approval_id))
                    r = replace(r, workflow=replace(r.workflow, pending=token))
                except ValueError as exc:
                    errors.append(exc)
            record = gateway.command_records[-1]
            return commit_run(p, r, 'command.launch', payload={
                'operation_id': token, 'tool_call_id': record.id, 'approval_id': approval_id, 'outcome': record.outcome})
        self.store.atomic_update(self.project_id, reserve)
        if errors:
            raise errors[0]
        def stop_reason():
            r = self.run
            if r.status is RunStatus.CANCELED or r.execution_generation != request.generation:
                return 'canceled'
            if r.status in {RunStatus.PAUSED, RunStatus.PAUSE_REQUESTED}:
                return 'paused'
            if r.status is not RunStatus.RUNNING or r.workflow.pending != token:
                return 'canceled'
            return None
        result = gateway.collect_command(running[0], stop_reason)
        final = []
        def finish(p):
            r = p.run(self.run_id)
            current = result
            reason = stop_reason()
            if reason and result.succeeded:
                current = replace(result, outcome=reason)
            gateway.finish_command(running[0], current)
            final.append(current)
            wf = replace(r.workflow, pending=None if r.workflow.pending == token and current.cleanup_complete else r.workflow.pending,
                         command_results=(*r.workflow.command_results, current))
            status = RunStatus.PAUSED if r.status is RunStatus.PAUSE_REQUESTED else r.status
            after, events = commit_run(p, replace(r, workflow=wf, status=status), 'command.completed', payload={
                'operation_id': token, 'command_id': current.id, 'approval_id': approval_id,
                'outcome': current.outcome, 'exit_code': current.exit_code})
            if not current.cleanup_complete and after.run(r.id).active:
                after, blocked = block_state(after, after.run(r.id),
                    'command cleanup incomplete; manual intervention required', keep_pending=True)
                events = (*events, *blocked)
            return after, events
        self.store.atomic_update(self.project_id, finish)
        return final[0]

    def _guard_file_mutation(self, request):
        r = self.run
        if (r.status is not RunStatus.RUNNING or not r.approved or r.phase != 'develop'
                or not r.workflow or not r.workflow.attempts
                or r.workflow.attempts[-1].id != request.attempt_id
                or r.execution_generation != request.generation):
            raise ValueError('file mutation stopped: inactive, paused, canceled, or stale attempt')

    def file_tool(self, request):
        """Trusted role-bound entrypoint; serialize file operations with human controls.

        Provider tool calls remain unsupported. The caller supplies application-owned
        role/attempt identity, never identity taken from model-generated arguments.
        """
        if self.workspace_gateway is None:
            raise ValueError('no workspace gateway configured')
        result, failure = [], []
        def apply(p):
            r = p.run(self.run_id)
            try:
                result.append(self.workspace_gateway.execute(request))
            except ValueError as exc:
                failure.append(exc)
            record = self.workspace_gateway.records[-1]
            return commit_run(p, r, 'file.operation', payload={
                'tool_call_id': record.id, 'operation': record.operation, 'actor': record.actor,
                'attempt_id': record.attempt_id, 'outcome': record.outcome})
        self.store.atomic_update(self.project_id, apply)
        if failure:
            raise failure[0]
        return result[0]

    @property
    def run(self):
        return self.store.get_project(self.project_id).run(self.run_id)

    def initialize(self, limits=ExecutionLimits()):
        def apply(p):
            r = p.run(self.run_id)
            if r.workflow is not None:
                raise ValueError('workflow already initialized; counters cannot reset')
            if r.status not in {RunStatus.DRAFT, RunStatus.RUNNING, RunStatus.AWAITING_APPROVAL}:
                raise ValueError('workflow requires draft or approved plan')
            if any(t.status not in {TaskStatus.TODO, TaskStatus.BACKLOG} or t.is_canceled for t in p.tasks if t.id in r.task_ids):
                raise ValueError('cannot adopt partially executed work without evidence')
            if len(r.task_ids) > limits.max_tasks:
                raise ValueError('task creation limit exceeded')
            if any(t.assignee is not AgentKind.DEVELOPER for t in p.tasks if t.id in r.task_ids):
                raise ValueError('implementation tasks must belong to Developer')
            wf = WorkflowState(limits=limits, tasks_created=len(r.task_ids))
            phase = 'plan' if r.status is RunStatus.DRAFT else 'assign'
            snapshot = tuple((k.value, d.snapshot().config_digest) for k, d in self.definitions.items())
            return commit_run(p, replace(r, workflow=wf, phase=phase, config_snapshot=snapshot), 'workflow.initialized')
        self.store.atomic_update(self.project_id, apply)

    def approve(self):
        # M2.1 command retains the workflow records and budgets.
        return self.store.approve_plan(self.project_id, self.run_id)

    def request_replan(self):
        def apply(p):
            r = p.run(self.run_id)
            wf = r.workflow
            if wf is None or r.status is not RunStatus.AWAITING_APPROVAL or wf.pending:
                raise ValueError('replanning is limited to unapproved plans; replacement execution is unsupported')
            if wf.replans >= wf.limits.max_replans:
                return block_state(p, r, 'replanning limit reached', exhausted_limit=True)
            # Retain old tasks and all counters; never erase prior work.
            return commit_run(p, replace(r, status=RunStatus.PLANNING, phase='plan',
                workflow=replace(wf, replans=wf.replans + 1)), 'plan.replanning_requested')
        return self.store.atomic_update(self.project_id, apply)

    def run_until_stopped(self):
        while self.step():
            pass
        return self.run

    def step(self):
        """Reserve one operation atomically, release the store lock during model IO."""
        token = 'op_' + uuid4().hex
        reserved = []
        def reserve(p):
            r = p.run(self.run_id)
            wf = r.workflow
            if wf is None:
                raise ValueError('initialize workflow first')
            if wf.pending or wf.pending_permissions or r.status not in {RunStatus.DRAFT, RunStatus.PLANNING, RunStatus.RUNNING}:
                raise _NoOperation
            if wf.iterations >= wf.limits.max_iterations:
                return block_state(p, r, 'workflow iteration limit reached', exhausted_limit=True)
            phase = 'assign' if r.phase == 'execution' else r.phase
            if phase != 'plan' and not r.approved:
                return block_state(p, r, 'execution requires an approved plan')
            if phase == 'assign':
                required = [p.task(i) for i in r.task_ids]
                if required and all(self._accepted(p, r, t.id) for t in required):
                    phase = 'final'
                elif any(t.is_canceled or t.status in {TaskStatus.IN_PROGRESS, TaskStatus.REVIEW, TaskStatus.BLOCKED} for t in required):
                    return block_state(p, r, 'required task state is invalid for assignment')
                elif not self._ready(p, r):
                    return block_state(p, r, 'no dependency-ready task')
            if wf.invocations >= wf.limits.max_invocations:
                return block_state(p, r, 'invocation limit reached', exhausted_limit=True)
            wf = replace(wf, pending=token, iterations=wf.iterations + 1,
                         invocations=wf.invocations + 1,
                         instructions=(*wf.instructions, *wf.pending_instructions), pending_instructions=())
            r = replace(r, workflow=wf, phase=phase)
            reserved.append((p, r))
            return commit_run(p, r, 'operation.started', payload={'operation_id': token, 'phase': phase})
        try:
            self.store.atomic_update(self.project_id, reserve)
        except _NoOperation:
            return False
        if not reserved:
            return False
        project, run = reserved[0]
        generation = run.execution_generation
        calls = 0
        def before_call():
            nonlocal calls
            def charge(p):
                r = p.run(self.run_id)
                wf = r.workflow
                if r.execution_generation != generation or wf.pending != token or r.status in {
                    RunStatus.CANCELED, RunStatus.PAUSED, RunStatus.PAUSE_REQUESTED, RunStatus.WAITING_FOR_USER}:
                    raise BoundaryStopped('operation stopped at safe boundary')
                if calls >= wf.limits.max_calls_per_invocation or wf.llm_calls >= wf.limits.max_llm_calls:
                    raise BudgetStopped('LLM call limit reached')
                return commit_run(p, replace(r, workflow=replace(wf, llm_calls=wf.llm_calls + 1)),
                                  'provider.call_reserved', payload={'operation_id': token})
            self.store.atomic_update(self.project_id, charge)
            calls += 1
        result = None
        failure = None
        try:
            kind, schema, context, extra = self._request(project, run)
            agent = self.definitions[kind]
            if dict(run.config_snapshot).get(kind.value) != agent.snapshot().config_digest:
                raise ValueError('configuration generation does not match agent snapshot')
            result = self.runtime.invoke(agent, context, self.provider,
                invocation_id=token, output_schema=schema, workflow_context=extra,
                source_versions={'requirements': str(project.requirement_version), 'generation': str(generation),
                                 'run': str(run.version)},
                before_call=before_call, max_attempts=run.workflow.limits.max_provider_attempts,
                max_repairs=run.workflow.limits.max_repairs)
        except (InvocationError, ValueError) as exc:
            failure = exc
        records = result.call_records if result else getattr(failure, 'call_records', ())
        def finish(p):
            r = p.run(self.run_id)
            wf = replace(r.workflow, call_records=(*r.workflow.call_records, *records))
            r = replace(r, workflow=wf)
            if r.execution_generation != generation or wf.pending != token or not r.active or r.status is RunStatus.WAITING_FOR_USER:
                if wf.pending == token:
                    r = replace(r, workflow=replace(wf, pending=None))
                return commit_run(p, r, 'operation.stale_ignored', payload={'operation_id': token, 'calls': len(records)})
            r = replace(r, workflow=replace(wf, pending=None))
            pause = r.status is RunStatus.PAUSE_REQUESTED
            if pause and self.workspace_gateway and r.phase == 'develop':
                # File capture is a mutation too. Retry this phase on resume,
                # retaining usage and edits but never sealing while paused.
                return commit_run(p, replace(r, status=RunStatus.PAUSED), 'run.paused')
            if isinstance(failure, BoundaryStopped) and pause:
                return commit_run(p, replace(r, status=RunStatus.PAUSED), 'run.paused')
            if failure is not None:
                return block_state(p, r, f'technical failure: {failure}', exhausted_limit=isinstance(failure, BudgetStopped))
            if pause:
                r = replace(r, status=RunStatus.RUNNING)
            try:
                after, events = self._apply(p, r, result.output)
            except ValueError as exc:
                return block_state(p, r, f'workflow validation: {exc}', exhausted_limit=isinstance(exc, LimitExceeded))
            if pause and after.run(r.id).status is RunStatus.RUNNING:
                paused = replace(after.run(r.id), status=RunStatus.PAUSED)
                after, pause_events = commit_run(after, paused, 'run.paused')
                events = (*events, *pause_events)
            return after, events
        def finish_with_usage(p):
            after, events = finish(p)
            usage_events = tuple(DomainEvent(p.id, 'usage.recorded', record.to_dict(),
                run_id=run.id, task_id=run.current_task_id, correlation_id=token) for record in records)
            return after, (*events, *usage_events)
        self.store.atomic_update(self.project_id, finish_with_usage)
        return True

    @staticmethod
    def _submission(run, task_id):
        return next((s for s in reversed(run.workflow.submissions) if s.task_id == task_id), None)

    @classmethod
    def _accepted(cls, project, run, task_id):
        task = project.task(task_id)
        sub = cls._submission(run, task_id)
        return bool(task.is_completed and sub and sub.id in run.workflow.accepted and
                    sub.generation == run.execution_generation and sub.requirement_version == project.requirement_version)

    @classmethod
    def _final_manifest(cls, project, run):
        """Resolve only current accepted submissions, in required task order."""
        if not run.task_ids or not all(cls._accepted(project, run, i) for i in run.task_ids):
            raise ValueError('completion requires all current submissions accepted')
        submissions = tuple(cls._submission(run, i) for i in run.task_ids)
        if set(run.workflow.accepted) != {s.id for s in submissions}:
            raise ValueError('accepted manifest contains noncurrent submissions')
        return submissions

    @classmethod
    def _ready(cls, project, run):
        return tuple(t for t in project.tasks if t.id in run.task_ids and not t.is_canceled and
                     t.status in {TaskStatus.BACKLOG, TaskStatus.TODO} and
                     all(cls._accepted(project, run, dep) for dep in t.dependencies))

    def _request(self, p, r):
        wf = r.workflow
        task = p.task(r.current_task_id) if r.current_task_id else None
        sub = self._submission(r, task.id) if task else None
        review = next((x for x in reversed(wf.reviews) if sub and x.submission_id == sub.id), None)
        reference = None if review is None else ReviewReference(review.result.review_id, sub.id,
            review.result.verdict, review.result.summary, tuple(f.summary for f in review.result.findings))
        context = ProjectContext(p.goal, p.requirements,
            task_summaries=tuple(TaskSummary(t.id, t.title, t.status.value, t.assignee, t.dependencies,
                sum(s.task_id == t.id for s in wf.submissions)) for t in p.tasks if t.id in r.task_ids),
            decisions=p.decisions,
            current_task=None if task is None else TaskBrief(task.id, task.title, task.description,
                self._criteria(p, task), task.assignee, task.dependencies),
            relevant_review=reference,
            dependencies=tuple(TaskSummary(p.task(dep).id, p.task(dep).title, p.task(dep).status.value,
                p.task(dep).assignee, p.task(dep).dependencies, sum(s.task_id == dep for s in wf.submissions))
                for dep in (() if task is None else task.dependencies)),
            submission=None if sub is None else SubmissionReference(sub.id, sub.version, sub.output.summary,
                tuple(FileReference(f.path, f.summary) for f in sub.output.changed_files), sub.evidence))
        extra = {'phase': r.phase, 'instructions': list(wf.instructions),
                 'controlled_tools': 'Synthetic in-memory evidence only. No file or command execution.'}
        if self.workspace_gateway:
            extra['controlled_tools'] = 'Workspace files and exact-approved commands through trusted runner gateway. Captured file/test evidence is authoritative; model test claims are unverified.'
        schema = 'manager_decision.v1'
        kind = AgentKind.MANAGER
        if r.phase == 'plan':
            schema = 'manager_plan.v1'
            extra.update({'task_budget_remaining': wf.limits.max_tasks - wf.tasks_created,
                          'plan_policy': 'Copy supplied requirements exactly, including IDs, descriptions, criteria and priority. Propose only Developer tasks within the remaining budget, with new unique IDs. This is a synthetic demonstration, not a real implementation.',
                          'existing_task_ids': [t.id for t in p.tasks]})
            if self.workspace_gateway:
                extra['plan_policy'] = 'Copy supplied requirements exactly. Propose only Developer tasks within the remaining budget, with unique IDs. Files and exact-approved command profiles are available through the trusted runner.'
        elif r.phase == 'assign':
            extra['ready_task_ids'] = [t.id for t in self._ready(p, r)]
            extra['expected_action'] = 'assign_task'
        elif r.phase == 'develop':
            kind, schema = AgentKind.DEVELOPER, 'developer_submission.v1'
            attempt = wf.attempts[-1]
            extra.update({'submission_id': attempt.id + ':submission', 'output_version': attempt.number,
                          'dependency_evidence': {dep: list(self._submission(r, dep).evidence) for dep in task.dependencies},
                          'revision': None if not wf.revisions or wf.revisions[-1].task_id != task.id else {
                              'required_fixes': list(wf.revisions[-1].required_fixes),
                              'remaining_review_rounds': wf.revisions[-1].remaining_review_rounds},
                          'evidence_policy': 'Return synthetic changed_files summaries and at least one test result; clearly label simulated evidence.'})
            if self.workspace_gateway:
                extra['evidence_policy'] = 'Report exactly the files changed through the workspace gateway in this attempt. Only application-captured fresh test evidence verifies executed tests.'
        elif r.phase == 'review':
            kind, schema = AgentKind.REVIEWER, 'review_result.v1'
            extra['review_id'] = sub.id + ':review'
            extra['review_policy'] = 'Use the supplied unique review_id and exact submission ID. Assess every supplied criterion ID against the captured synthetic evidence.'
            extra['criteria'] = {f'c{i}': c for i, c in enumerate(self._criteria(p, task), 1)}
            extra['evidence'] = list(sub.evidence)
            if sub.files:
                extra['review_policy'] = 'Review immutable captured file contents, diffs and test evidence for the exact submission ID. Stale or unsuccessful tests cannot establish a passing result. Without captured tests, test claims are unverified.'
        elif r.phase == 'decide':
            extra.update({'task_id': task.id, 'submission_id': sub.id,
                          'decision_policy': 'For the current task, propose accept_submission only after PASS; propose request_revision with concrete fixes after FAIL, or block/request_user_input. Do not propose complete or assign_task in this phase.',
                          'review': review.result.to_dict(),
                          'remaining_review_rounds': wf.limits.max_review_rounds - sum(s.task_id == task.id for s in wf.submissions)})
        elif r.phase == 'final':
            schema = 'final_result.v1'
            accepted = self._final_manifest(p, r)
            extra.update({'completed_task_ids': [s.task_id for s in accepted],
                          'evidence_refs': [s.id for s in accepted],
                          'accepted_submissions': [{'task_id': s.task_id, 'submission_id': s.id,
                              'output_version': s.version, 'evidence_digest': s.digest} for s in accepted],
                          'required_status': 'completed',
                          'finalization_policy': 'Return status completed. Copy workflow.completed_task_ids and '
                              'workflow.evidence_refs exactly into the corresponding output arrays. Include every '
                              'entry, without additions or substitutions. evidence_refs are accepted submission IDs '
                              'identifying immutable evidence, not task IDs, file paths, evidence text or digests. '
                              'Use only the current accepted_submissions mapping; never an earlier attempt.'})
        else:
            raise ValueError('unknown workflow phase')
        return kind, schema, context, extra

    @staticmethod
    def _criteria(project, task):
        # M1 plans lack task-to-requirement references: conservatively check all.
        return tuple(dict.fromkeys((*task.acceptance_criteria,
            *(criterion for req in project.requirements for criterion in req.acceptance_criteria))))

    def _apply(self, p, r, output):
        wf = r.workflow
        tasks = list(p.tasks)
        def set_task(task):
            tasks[:] = [task if t.id == task.id else t for t in tasks]
        phase = r.phase
        event = 'workflow.advanced'
        if phase == 'plan':
            plan = validate_manager_plan(output.to_dict())
            proposed = {x.id: x for x in plan.requirements}
            if any(proposed.get(x.id) != x for x in p.requirements):
                raise ValueError('Manager plan cannot remove or alter existing requirements')
            if wf.tasks_created + len(plan.tasks) > wf.limits.max_tasks:
                raise LimitExceeded('task creation limit reached')
            if set(t.id for t in plan.tasks) & set(t.id for t in tasks):
                raise ValueError('replacement task identifiers cannot be reused')
            if any(t.assignee is not AgentKind.DEVELOPER for t in plan.tasks):
                raise ValueError('implementation tasks must be assigned to Developer')
            tasks.extend(Task.from_spec(t) for t in plan.tasks)
            p = replace(p, requirements=plan.requirements, decisions=plan.decisions,
                        requirement_version=p.requirement_version + 1)
            r = replace(r, status=RunStatus.AWAITING_APPROVAL, phase='assign', plan=plan, plan_approved=False,
                        task_ids=tuple(t.id for t in plan.tasks),
                        workflow=replace(wf, tasks_created=wf.tasks_created + len(plan.tasks)))
            event = 'plan.proposed'
        elif phase == 'assign':
            if output.action is not DecisionAction.ASSIGN_TASK or output.task_id not in {t.id for t in self._ready(p, r)}:
                raise ValueError('Manager assignment is not approved and ready')
            task = p.task(output.task_id)
            if sum(s.task_id == task.id for s in wf.submissions) >= wf.limits.max_review_rounds:
                raise LimitExceeded('review round limit reached')
            attempt = TaskAttempt(f'{r.id}:{task.id}:attempt:{1 + sum(a.task_id == task.id for a in wf.attempts)}',
                task.id, r.id, 1 + sum(a.task_id == task.id for a in wf.attempts),
                r.execution_generation, p.requirement_version)
            set_task(replace(task, status=TaskStatus.IN_PROGRESS, version=task.version + 1))
            r = replace(r, current_task_id=task.id, phase='develop', workflow=replace(wf, attempts=(*wf.attempts, attempt)))
            event = 'task.assigned'
        elif phase == 'develop':
            task = p.task(r.current_task_id)
            attempt = wf.attempts[-1]
            if attempt.generation != r.execution_generation or attempt.requirement_version != p.requirement_version:
                raise ValueError('stale execution generation')
            if sum(s.task_id == task.id for s in wf.submissions) >= wf.limits.max_review_rounds:
                raise LimitExceeded('review round limit reached')
            evidence = tuple('SIMULATED artifact ' + f.path + ': ' + f.summary for f in output.changed_files) + tuple(
                'SIMULATED test ' + t.name + ': ' + t.status + ': ' + t.summary for t in output.tests)
            if self.workspace_gateway:
                # Validate model identity before sealing any gateway artifacts.
                SubmissionManifest.capture(output, attempt, ('pending file capture',))
                captured = self.workspace_gateway.execute(FileToolRequest('capture_submission',
                    AgentKind.DEVELOPER, attempt.id, r.execution_generation,
                    submission_id=output.submission_id, paths=tuple(f.path for f in output.changed_files))).submission
                actual_types = {f.path: 'added' if f.before is None else 'modified' for f in captured.files}
                output = replace(output, changed_files=tuple(replace(f, change_type=actual_types[f.path])
                                                            for f in output.changed_files))
                evidence = (captured.serialize(), 'Application-captured command results are version-bound; model test reports remain UNVERIFIED.'
                            if captured.tests else 'UNVERIFIED test reports; no test commands executed.')
                sub = SubmissionManifest.capture(output, attempt, evidence, captured)
            else:
                captured = self.gateway.execute(ToolRequest('capture_submission', AgentKind.DEVELOPER,
                    output.submission_id, r.execution_generation, evidence))
                sub = SubmissionManifest.capture(output, attempt, captured.evidence)
            if any(s.id == sub.id for s in wf.submissions):
                raise ValueError('submission identity already exists')
            set_task(replace(task, status=TaskStatus.REVIEW, version=task.version + 1))
            r = replace(r, phase='review', workflow=replace(wf, submissions=(*wf.submissions, sub)))
            event = 'submission.admitted'
        elif phase == 'review':
            task = p.task(r.current_task_id)
            sub = self._submission(r, task.id)
            if sub.generation != r.execution_generation or sub.requirement_version != p.requirement_version:
                raise ValueError('stale submission generation')
            if sub.files and sub.files.tests and output.verdict is ReviewVerdict.PASS:
                latest = {test.result.request.profile: test for test in sub.files.tests}
                if any(not test.passed for test in latest.values()):
                    raise ValueError('Reviewer PASS cannot override failed, terminated or stale captured tests')
            if any(x.result.review_id == output.review_id for x in wf.reviews):
                raise ValueError('review id already exists')
            review = ReviewRound.validate(output, sub, self._criteria(p, task),
                sum(s.task_id == task.id for s in wf.submissions))
            r = replace(r, phase='decide', workflow=replace(wf, reviews=(*wf.reviews, review)))
            event = 'review.completed'
        elif phase == 'decide':
            task = p.task(r.current_task_id)
            sub = self._submission(r, task.id)
            review = next(x for x in reversed(wf.reviews) if x.submission_id == sub.id)
            if output.task_id != task.id:
                raise ValueError('Manager decision references wrong task')
            if output.action in {DecisionAction.BLOCK, DecisionAction.REQUEST_USER_INPUT}:
                return block_state(p, r, output.reason)
            if output.action is DecisionAction.ACCEPT_SUBMISSION:
                if review.result.verdict is not ReviewVerdict.PASS or sub.generation != r.execution_generation:
                    raise ValueError('Manager cannot bypass Reviewer FAIL or stale evidence')
                set_task(replace(task, status=TaskStatus.DONE, version=task.version + 1))
                r = replace(r, phase='assign', current_task_id=None,
                            workflow=replace(wf, accepted=(*wf.accepted, sub.id)))
                projected = replace(p, tasks=tuple(tasks))
                for candidate in self._ready(projected, r):
                    if candidate.status is TaskStatus.BACKLOG:
                        set_task(replace(candidate, status=TaskStatus.TODO, version=candidate.version + 1))
                event = 'task.accepted'
            elif output.action is DecisionAction.REQUEST_REVISION:
                rounds = sum(s.task_id == task.id for s in wf.submissions)
                if rounds >= wf.limits.max_review_rounds:
                    return block_state(p, r, 'review round limit reached', exhausted_limit=True)
                if not output.revision_instructions:
                    raise ValueError('revision requires instructions')
                brief = RevisionBrief(task.id, sub.id, review.result.review_id, output.revision_instructions,
                                      self._criteria(p, task), wf.limits.max_review_rounds - rounds)
                set_task(replace(task, status=TaskStatus.TODO, revision=task.revision + 1, version=task.version + 1))
                r = replace(r, phase='assign', current_task_id=None,
                            workflow=replace(wf, revisions=(*wf.revisions, brief)))
                event = 'revision.requested'
            else:
                raise ValueError('Manager must accept, revise, or block the current submission')
        elif phase == 'final':
            accepted = self._final_manifest(p, r)
            if output.status != 'completed' or set(output.completed_task_ids) != {s.task_id for s in accepted} or set(output.evidence_refs) != {s.id for s in accepted}:
                raise ValueError('final result must reference all accepted tasks and evidence')
            r = replace(r, status=RunStatus.COMPLETED, phase='completed',
                        workflow=replace(wf, final_result=output))
            event = 'run.completed'
        task_id = r.current_task_id or getattr(output, 'task_id', None)
        payload = {'phase': phase, 'generation': r.execution_generation}
        if task_id:
            payload['task_id'] = task_id
            sub = self._submission(r, task_id)
            if sub:
                payload.update(submission_id=sub.id, submission_version=sub.version)
        if phase == 'review':
            payload['review_id'] = output.review_id
        if phase == 'develop' and self.workspace_gateway:
            payload['tool_call_id'] = self.workspace_gateway.records[-1].id
            payload['file_digest'] = sub.files.digest
        after, events = commit_run(p, r, event, tasks=tasks, payload=payload)
        return after, tuple(replace(e, task_id=task_id) for e in events)
