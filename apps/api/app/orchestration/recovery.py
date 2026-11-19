"""Startup inspection and explicit recovery controls. Never performs external work.

A start fence proves only that execution was permitted, not that it occurred.
Unknown operations require operator decisions; no PID is ever signaled here.
"""
from dataclasses import replace
from datetime import datetime, timezone
import json
from app.domain.events import DomainEvent
from app.domain.projects import RunStatus, TERMINAL_RUN_STATUSES
from app.domain.recovery import (RecoveryState, RecoveryIssue, OperationStage,
    OutcomeCertainty, retain_calls)
from app.persistence.models import ArtifactIntegrityError


class RecoveryError(ValueError):
    pass


class RecoveryCoordinator:
    def __init__(self, store):
        self.store = store

    def ensure_startup(self, project_id, run_id):
        if self.store.needs_recovery(project_id, run_id):
            self.reconcile(project_id, run_id)

    def startup(self):
        for project_id, run_id in self.store.list_run_refs():
            self.ensure_startup(project_id, run_id)
        return self.list_interrupted()

    def list_interrupted(self):
        return tuple((p, r) for p, r in self.store.list_run_refs()
                     if (run := self.store.get_run_metadata(p, r)).workflow
                     and run.workflow.recovery and run.workflow.recovery.requires_resume)

    def inspect(self, project_id, run_id):
        self.ensure_startup(project_id, run_id)
        run = self.store.get_run_metadata(project_id, run_id)
        return {'project_id': project_id, 'run_id': run_id, 'status': run.status.value,
                'phase': run.phase, 'generation': run.execution_generation,
                'checkpoint': run.workflow.checkpoint if run.workflow else None,
                'recovery': run.workflow.recovery if run.workflow else None,
                'operations': self.store.operations(project_id, run_id, metadata_only=True),
                'available_actions': self.available_actions(project_id, run)}

    def available_actions(self, project_id, run):
        """Advertise existing reconciliation actions. Resolve still validates all gates."""
        recovery = run.workflow.recovery if run.workflow else None
        if not recovery or not recovery.requires_resume:
            return {}
        try:
            ops = self.store.operations(project_id, run.id)
        except ArtifactIntegrityError:
            ops = ()
        actions = {}
        for issue in recovery.unresolved:
            op = next((o for o in ops if o.id == issue.id), None)
            choices = []
            def add(action, label, quiescent=False):
                choices.append({'action': action, 'label': label, 'requires_quiescent': quiescent})
            if issue.kind == 'artifact':
                add('verify-artifacts', 'Verify restored immutable artifacts')
            elif issue.kind == 'provider':
                add('abandon-provider', 'Abandon proposal; billing remains uncertain')
                if op and op.proposal is not None and op.certainty is OutcomeCertainty.CONFIRMED_SUCCESS:
                    add('accept-result', 'Admit retained validated result')
            elif issue.kind == 'command':
                add('acknowledge-command', 'Acknowledge uncertain command after confirming quiescence', True)
            elif issue.kind == 'file':
                if op and op.change and op.operation in {'write', 'edit'}:
                    add('verify-file', 'Compare live file with retained before/after hashes')
                elif op and op.operation == 'capture_submission' and op.result:
                    add('verify-capture', 'Verify retained submission capture')
                elif op and op.operation in {'read', 'list'}:
                    add('abandon-read', 'Abandon interrupted read')
                elif op is None or op.change is None:
                    add('acknowledge-file', 'Acknowledge uncertain file operation after quiescence', True)
            actions[issue.id] = choices
        return actions

    def reconcile(self, project_id, run_id):
        run = self.store.get_run_metadata(project_id, run_id)
        wf = run.workflow
        if wf is None:
            self.store.acknowledge_startup(project_id, run_id)
            return None
        ops = self.store.operations(project_id, run_id, metadata_only=True)
        approvals = self.store.approvals(project_id, run_id)
        history = self.store.tool_history(project_id, run_id)
        def matched_approval_seed(invocation_id):
            seed = next((c for c in wf.tool_continuations if c.invocation_id == invocation_id
                         and c.state == 'REQUESTING_APPROVAL'), None)
            if seed is None:
                return None
            try:
                profile = json.loads(seed.arguments_json).get('profile')
            except (TypeError, ValueError):
                return None
            approval = next((a for a in approvals if a.request.attempt_id == seed.attempt_id
                             and a.request.generation == seed.generation
                             and a.request.profile == profile), None)
            if approval is None or not any(getattr(record, 'action', None) == 'request'
                    and getattr(record, 'approval_id', None) == approval.id for record in history):
                return None
            return seed, approval
        old = wf.recovery if wf.recovery and wf.recovery.requires_resume else None
        issues = []
        def issue(identity, kind, certainty, reason, resolved=False):
            prior = next((i for i in wf.recovery.issues if i.id == identity), None) if wf.recovery and kind != 'artifact' else None
            issues.append(prior if prior and prior.resolved else RecoveryIssue(identity, kind, certainty, reason, resolved))
        full_project = None
        try:
            full_project = self.store.get_project(project_id)
            self.store.operations(project_id, run_id)
        except ArtifactIntegrityError as exc:
            issue('artifact-integrity', 'artifact', OutcomeCertainty.UNCERTAIN, str(exc))
        for op in ops:
            # The provider call may still be marked EXECUTING because approval
            # interrupted it before its response receipt was committed. A
            # persisted seed plus the exact audited intervention is a safe
            # continuation boundary; retain the call as interrupted/unknown,
            # but do not demand provider replay or discard the approval.
            if op.kind == 'provider' and matched_approval_seed(op.checkpoint.invocation_id):
                continue
            if op.stage is OperationStage.PREPARED:
                issue(op.id, op.kind, OutcomeCertainty.INTERRUPTED, 'prepared; execution start fence was never committed', True)
            elif op.stage is OperationStage.EXECUTING or op.certainty is OutcomeCertainty.UNCERTAIN:
                issue(op.id, op.kind, OutcomeCertainty.UNCERTAIN, 'execution permitted; completion cannot be proven')
            elif (op.kind == 'provider' and wf.pending == op.checkpoint.invocation_id
                  and op.id == [o.id for o in ops if o.kind == 'provider' and o.checkpoint.invocation_id == wf.pending][-1]):
                # A durable validated proposal needs explicit admission, or explicit abandonment.
                if matched_approval_seed(wf.pending) is None:
                    issue(op.id, 'provider', op.certainty,
                          'provider receipt committed; workflow result not yet admitted')
        known_ids = {o.id for o in ops}
        history = self.store.tool_history(project_id, run_id)
        for record in history:
            if getattr(record, 'operation', None) and record.id.endswith(':intent'):
                identity = record.id[:-7]
                if identity not in known_ids and not any(r.id == identity for r in history):
                    modern = record.protocol_version >= 2
                    issue('legacy:' + identity, 'file', OutcomeCertainty.INTERRUPTED if modern else OutcomeCertainty.UNCERTAIN,
                          'execution fence absent' if modern else 'legacy intent has no execution fence or outcome', modern)
            elif getattr(record, 'action', None) == 'intent' and not any(o.approval_id == record.approval_id for o in ops):
                if not any(getattr(r, 'action', None) == 'result' and r.approval_id == record.approval_id for r in history):
                    modern = record.protocol_version >= 2
                    issue('legacy:' + record.id, 'command', OutcomeCertainty.INTERRUPTED if modern else OutcomeCertainty.UNCERTAIN,
                          'execution fence absent' if modern else 'legacy command intent has no proven result', modern)
        if wf.pending and wf.pending.startswith('op_') and not any(o.checkpoint.invocation_id == wf.pending for o in ops):
            reserved = [e for e in self.store.events(project_id) if e.run_id == run_id
                        and e.type == 'provider.call_reserved' and e.payload.get('operation_id') == wf.pending]
            invocation = next((i for i in full_project.run(run_id).workflow.invocation_records if i.id == wf.pending), None) if full_project else None
            modern = invocation is not None and invocation.protocol_version >= 2
            if modern:
                issue(wf.pending, 'provider', OutcomeCertainty.INTERRUPTED, 'provider submission fence absent', True)
            elif reserved and full_project:
                from app.domain.recovery import checkpoint, ExecutionOperation
                from app.usage.records import LLMCallRecord, UsageProvenance, UsageCompleteness
                full_run = full_project.run(run_id)
                invocation = next((i for i in full_run.workflow.invocation_records if i.id == wf.pending), None)
                snapshot = next((s for s in full_run.workflow.agent_snapshots if invocation and s.agent_id == invocation.agent_id
                                 and s.config_digest == invocation.config_digest), None)
                for number, event in enumerate(reserved, 1):
                    identity = wf.pending + ':call:' + str(number)
                    cp = replace(checkpoint(full_project, full_run, 'legacy.reservation'), operation_id=identity,
                                 invocation_id=wf.pending, boundary='legacy.reservation',
                                 generation=invocation.generation if invocation else run.execution_generation)
                    call = LLMCallRecord(identity, wf.pending, number, 'initial' if number == 1 else 'retry',
                        'unknown', snapshot.model if snapshot else 'unknown', 'submitted', None, None,
                        UsageProvenance.UNKNOWN, UsageCompleteness.UNKNOWN, None, None)
                    imported = ExecutionOperation(identity, 'provider', cp, operation=invocation.agent_id if invocation else 'unknown',
                        call_record=call, started_at=event.occurred_at)
                    self.store.record_operation(imported)
                    self.store.record_operation(imported.evolve(stage=OperationStage.EXECUTING))
                    issue(identity, 'provider', OutcomeCertainty.UNCERTAIN, 'legacy reservation may have been submitted; usage unknown')
            else:
                issue(wf.pending, 'provider', OutcomeCertainty.UNCERTAIN if reserved else OutcomeCertainty.INTERRUPTED,
                      'legacy provider reservation may have been submitted' if reserved else 'invocation reserved; no provider submission fence', not reserved)
        if run.status in TERMINAL_RUN_STATUSES and not wf.pending and not any(not i.resolved for i in issues):
            self.store.acknowledge_startup(project_id, run_id)
            return old
        epoch = old.epoch if old else wf.recovery_epoch + 1
        original = old.original_status if old else run.status.value
        phase = old.resume_phase if old else ('assign' if run.phase == 'execution' else run.phase)
        recovery = replace(old, issues=tuple(issues)) if old else RecoveryState(epoch, original, phase, tuple(issues),
            original_blocked_reason=wf.blocked_reason, original_resume_phase=wf.resume_phase)
        if old == recovery:
            self.store.acknowledge_startup(project_id, run_id)
            return recovery
        has_pending_approval = any(a.status == 'pending'
            and a.request.generation == run.execution_generation for a in approvals)
        status = run.status if run.status in TERMINAL_RUN_STATUSES else (
            RunStatus.WAITING_FOR_USER if recovery.unresolved or has_pending_approval else RunStatus.PAUSED)
        def change(r):
            current = r.workflow
            cp = replace(current.checkpoint, recovery_epoch=epoch, boundary='recovery.blocked' if recovery.unresolved else 'recovery.ready') if current.checkpoint else None
            wf_after = replace(current, recovery_epoch=epoch, recovery=recovery, checkpoint=cp,
                workspace_tools=current.workspace_tools or bool(full_project and full_project.workspace_root and history),
                resume_phase=phase, blocked_reason='restart reconciliation required' if recovery.unresolved else current.blocked_reason)
            after = replace(r, status=status, workflow=wf_after)
            return after, (DomainEvent(project_id, 'recovery.inspected', {'epoch': epoch, 'unresolved': [i.id for i in recovery.unresolved]}, run_id=run_id),)
        self.store.update_recovery(project_id, run_id, change)
        self.store.acknowledge_startup(project_id, run_id)
        # Merge durable receipts after marking the gate, never before fencing old results.
        if not any(i.kind == 'artifact' for i in recovery.unresolved):
            self._retain_history(project_id, run_id)
        return recovery

    def _retain_history(self, project_id, run_id):
        ops = self.store.operations(project_id, run_id)
        project = self.store.get_project(project_id)
        run = project.run(run_id)
        wf = run.workflow
        calls = [replace(o.call_record, status='interrupted') if o.stage is OperationStage.EXECUTING else o.call_record
                 for o in ops if o.call_record and o.call_record.status != 'not_submitted' and o.stage is not OperationStage.PREPARED]
        updated = retain_calls(wf, calls)
        results = tuple(o.result for o in ops if o.kind == 'command' and o.stage is OperationStage.SETTLED and o.result is not None)
        approvals = self.store.approvals(project_id, run_id)
        by_id = {a.id: a for a in approvals}
        pending = tuple(i for i in wf.pending_permissions if i not in by_id or (
            by_id[i].status == 'pending' and by_id[i].request.generation == run.execution_generation))
        pending = (*pending, *(a.id for a in approvals if a.status == 'pending'
            and a.request.generation == run.execution_generation and a.id not in pending))
        history = self.store.tool_history(project_id, run_id)
        continuations = []
        for continuation in updated.tool_continuations:
            if continuation.state != 'REQUESTING_APPROVAL':
                continuations.append(continuation)
                continue
            approval = next((a for a in approvals if a.request.attempt_id == continuation.attempt_id
                and a.request.generation == continuation.generation
                and a.request.profile == json.loads(continuation.arguments_json).get('profile')), None)
            if approval is None:
                continuations.append(replace(continuation, state='FAILED',
                    updated_at=datetime.now(timezone.utc).isoformat()))
                continue
            request_record = next((v for v in history if getattr(v, 'action', None) == 'request'
                                   and getattr(v, 'approval_id', None) == approval.id), None)
            state = {'pending': 'WAITING_FOR_APPROVAL', 'approved': 'APPROVED_PENDING_EXECUTION',
                     'consumed': 'APPROVED_PENDING_EXECUTION', 'denied': 'TOOL_COMPLETED'}
            result_json = continuation.result_json
            if approval.status == 'denied':
                result_json = json.dumps({'outcome': 'denied', 'approval_id': approval.id,
                    'reason': approval.reason}, sort_keys=True, separators=(',', ':'))
            continuations.append(replace(continuation, permission_id=approval.id,
                tool_request_id=request_record.id if request_record else continuation.tool_request_id,
                state=state.get(approval.status, 'FAILED'), result_json=result_json,
                updated_at=datetime.now(timezone.utc).isoformat()))
            if approval.status == 'pending' and approval.id not in pending:
                pending = (*pending, approval.id)
        updated = replace(updated, pending_permissions=tuple(pending),
                          tool_continuations=tuple(continuations))
        existing = {r.id for r in wf.command_results}
        updated = replace(updated, command_results=(*updated.command_results, *(r for r in results if r.id not in existing)))
        if updated == wf:
            return
        from app.orchestration.controls import commit_run
        def apply(p):
            r = p.run(run_id)
            current = retain_calls(r.workflow, calls)
            ids = {v.id for v in current.command_results}
            current = replace(current, pending_permissions=tuple(pending),
                              tool_continuations=updated.tool_continuations,
                              command_results=(*current.command_results, *(v for v in results if v.id not in ids)))
            return commit_run(p, replace(r, workflow=current), 'recovery.history_retained')
        self.store.atomic_update(project_id, apply, expected_version=project.version)

    def resolve(self, project_id, run_id, operation_id, *, action, reason, runner=None, quiescent=False, expected_epoch=None):
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 4000:
            raise RecoveryError('bounded operator evidence/reason is required')
        self.ensure_startup(project_id, run_id)
        run = self.store.get_run_metadata(project_id, run_id)
        recovery = run.workflow.recovery
        if not recovery or not recovery.requires_resume:
            raise RecoveryError('run has no active recovery gate')
        if expected_epoch is not None and expected_epoch != recovery.epoch:
            raise RecoveryError('stale recovery epoch')
        item = next((i for i in recovery.issues if i.id == operation_id), None)
        if item is None:
            raise RecoveryError('operation is not in the reconciliation report')
        if item.resolved:
            return recovery  # Repeated resolution is idempotent.
        ops = self.store.operations(project_id, run_id, metadata_only=item.kind == 'artifact')
        op = next((o for o in ops if o.id == operation_id), None)
        certainty = item.certainty
        if action == 'verify-artifacts' and item.kind == 'artifact':
            self.store.get_project(project_id)
            self.store.operations(project_id, run_id)
            certainty = OutcomeCertainty.CONFIRMED_SUCCESS
        elif action == 'verify-file' and op and op.kind == 'file' and op.change:
            if op.operation not in {'write', 'edit'}:
                raise RecoveryError('file verification requires a retained mutation description')
            from app.permissions.policy import WorkspacePolicy
            from app.tools.files import WorkspaceFiles
            from app.domain.artifacts import content_hash
            root = self.store.get_project(project_id).workspace_root
            if not root:
                raise RecoveryError('workspace root is not retained')
            data = WorkspaceFiles(WorkspacePolicy(root)).read(op.path)
            digest = content_hash(data) if data is not None else None
            if digest == op.after_hash:
                certainty = OutcomeCertainty.CONFIRMED_SUCCESS
            elif digest == op.before_hash:
                certainty = OutcomeCertainty.CONFIRMED_FAILURE
            else:
                raise RecoveryError('live file matches neither retained before nor intended after hash')
            self.store.record_operation(op.evolve(stage=OperationStage.SETTLED, certainty=certainty))
        elif action == 'verify-capture' and op and op.kind == 'file' and op.operation == 'capture_submission' and op.result:
            project = self.store.get_project(project_id)
            if op.checkpoint.generation != run.execution_generation or op.checkpoint.requirement_version != project.requirement_version:
                raise RecoveryError('captured submission belongs to a stale execution generation')
            certainty = OutcomeCertainty.CONFIRMED_SUCCESS
            self.store.record_operation(op.evolve(stage=OperationStage.SETTLED, certainty=certainty))
        elif action == 'abandon-provider' and item.kind == 'provider':
            # Provider-native tools are disabled. This abandons the application
            # proposal, preserving unknown billing; it makes no claim of non-processing.
            if op and op.stage is not OperationStage.SETTLED:
                self.store.record_operation(op.evolve(stage=OperationStage.SETTLED, certainty=OutcomeCertainty.UNCERTAIN,
                    call_record=replace(op.call_record, status='interrupted') if op.call_record else None))
        elif action == 'accept-result' and op and op.kind == 'provider' and op.proposal is not None:
            if op.certainty is not OutcomeCertainty.CONFIRMED_SUCCESS or runner is None:
                raise RecoveryError('validated successful receipt and a bound runner are required')
            if any(i.id != item.id and not i.resolved and i.kind in {'file', 'command', 'artifact'} for i in recovery.issues):
                raise RecoveryError('dangerous side effects/artifacts must be resolved before result admission')
            self._admit(project_id, run_id, op, runner)
        elif action == 'acknowledge-command' and item.kind == 'command' and quiescent:
            # Explicit operator attestation, never stale-PID inference or an invented exit code.
            if op and op.stage is not OperationStage.SETTLED:
                self.store.record_operation(op.evolve(stage=OperationStage.SETTLED, certainty=OutcomeCertainty.UNCERTAIN))
        elif action == 'acknowledge-file' and item.kind == 'file' and quiescent and (op is None or op.change is None):
            if op and op.stage is not OperationStage.SETTLED:
                self.store.record_operation(op.evolve(stage=OperationStage.SETTLED, certainty=OutcomeCertainty.UNCERTAIN))
        elif action == 'abandon-read' and op and op.kind == 'file' and op.operation in {'read', 'list'}:
            self.store.record_operation(op.evolve(stage=OperationStage.SETTLED, certainty=OutcomeCertainty.INTERRUPTED))
        else:
            raise RecoveryError('resolution does not establish a supported safe boundary')
        def change(r):
            rec = r.workflow.recovery
            if rec.epoch != recovery.epoch:
                raise RecoveryError('stale recovery epoch')
            issues = tuple(replace(i, resolved=True, certainty=certainty, resolution=action + ': ' + reason) if i.id == operation_id else i for i in rec.issues)
            rec = replace(rec, issues=issues, requires_resume=r.status not in TERMINAL_RUN_STATUSES)
            status = r.status if r.status in TERMINAL_RUN_STATUSES else (RunStatus.WAITING_FOR_USER if rec.unresolved else RunStatus.PAUSED)
            return replace(r, status=status, workflow=replace(r.workflow, recovery=rec,
                pending=None if r.status in TERMINAL_RUN_STATUSES and not rec.unresolved else r.workflow.pending)), (
                DomainEvent(project_id, 'recovery.resolved', {'operation_id': operation_id, 'action': action,
                    'certainty': certainty.value, 'reason': reason, 'epoch': rec.epoch}, run_id=run_id),)
        after = self.store.update_recovery(project_id, run_id, change)
        self._retain_history(project_id, run_id)
        return after.workflow.recovery

    def _admit(self, project_id, run_id, op, runner):
        if runner.store is not self.store or (runner.project_id, runner.run_id) != (project_id, run_id):
            raise RecoveryError('runner identity mismatch')
        from app.orchestration.controls import commit_run
        if runner.workspace_gateway:
            runner.workspace_gateway.restore(self.store.operations(project_id, run_id),
                self.store.approvals(project_id, run_id), runner.run, self.store.tool_history(project_id, run_id))
        def apply(p):
            r = p.run(run_id)
            cp = op.checkpoint
            if (cp.generation != r.execution_generation or cp.requirement_version != p.requirement_version
                    or cp.phase != r.workflow.recovery.resume_phase):
                raise RecoveryError('proposal generation, requirement version or phase is stale')
            invocation = next((i for i in r.workflow.invocation_records if i.id == cp.invocation_id), None)
            snapshot = next((a for a in r.workflow.agent_snapshots if invocation and a.agent_id == invocation.agent_id
                             and a.config_digest == invocation.config_digest), None)
            if snapshot is None or dict(r.config_snapshot).get(snapshot.kind.value) != snapshot.config_digest:
                raise RecoveryError('proposal configuration snapshot is stale')
            if runner.definitions[snapshot.kind].snapshot().config_digest != snapshot.config_digest:
                raise RecoveryError('configured runner does not match the saved proposal')
            original_pending = r.workflow.pending
            if original_pending != cp.invocation_id:
                raise RecoveryError('proposal does not belong to the interrupted invocation')
            ready = replace(r, status=RunStatus.RUNNING if r.approved else RunStatus.PLANNING,
                            workflow=replace(r.workflow, pending=None))
            runner._admitting_recovery = True
            try:
                after, events = runner._apply(p, ready, op.proposal)
            finally:
                runner._admitting_recovery = False
            updated = after.run(run_id)
            rec = replace(updated.workflow.recovery, resume_phase=updated.phase)
            updated = replace(updated, status=updated.status if updated.status in TERMINAL_RUN_STATUSES else RunStatus.PAUSED,
                              workflow=replace(updated.workflow, recovery=rec))
            after, gate = commit_run(after, updated, 'recovery.result_admitted', payload={'operation_id': op.id})
            return after, (*events, *gate)
        self.store.atomic_update(project_id, apply)

    def resume(self, project_id, run_id, *, expected_epoch=None):
        self.ensure_startup(project_id, run_id)
        current = self.store.get_run_metadata(project_id, run_id)
        rec = current.workflow.recovery
        if not rec or not rec.requires_resume or rec.unresolved:
            raise RecoveryError('resume requires inspected, fully resolved recovery')
        if expected_epoch is not None and rec.epoch != expected_epoch:
            raise RecoveryError('stale recovery epoch')
        current_wf = current.workflow
        continuations_by_operation = {c.operation_id: c for c in current_wf.tool_continuations
            if c.state == 'APPROVED_PENDING_EXECUTION'}
        approved_ids = {a.id for a in self.store.approvals(project_id, run_id)
                        if a.status in {'approved', 'consumed'}}
        for op in self.store.operations(project_id, run_id):
            if op.stage is OperationStage.PREPARED:
                continuation = continuations_by_operation.get(op.id)
                if (op.kind == 'command' and continuation is not None
                        and continuation.permission_id in approved_ids
                        and continuation.generation == current.execution_generation):
                    # PREPARED proves the command start fence was not crossed. Retain
                    # this exact approved operation identity for a safe single retry.
                    continue
                self.store.record_operation(op.evolve(stage=OperationStage.SETTLED, certainty=OutcomeCertainty.CONFIRMED_FAILURE,
                    call_record=replace(op.call_record, status='not_submitted') if op.call_record else None))
        self._retain_history(project_id, run_id)
        durable_operations = self.store.operations(project_id, run_id)
        from app.orchestration.controls import commit_run
        def apply(p):
            r = p.run(run_id)
            wf, rec = r.workflow, r.workflow.recovery
            if not rec or not rec.requires_resume or not rec.inspected or rec.unresolved:
                raise RecoveryError('resume requires inspected, fully resolved recovery')
            if expected_epoch is not None and rec.epoch != expected_epoch:
                raise RecoveryError('stale recovery epoch')
            if r.status in TERMINAL_RUN_STATUSES:
                raise RecoveryError('terminal runs cannot resume')
            if wf.exhausted_limit:
                raise RecoveryError('exhausted limits cannot be reset by recovery')
            if wf.checkpoint and (wf.checkpoint.generation != r.execution_generation
                    or wf.checkpoint.requirement_version != p.requirement_version or rec.epoch != wf.recovery_epoch):
                raise RecoveryError('checkpoint generation or requirement version is stale')
            # Artifact checks occurred in get_project. Phase prerequisites remain the
            # same validated submissions/attempts and accepted history.
            phase = rec.resume_phase
            if phase == 'develop':
                attempt = next((a for a in reversed(wf.attempts) if a.task_id == r.current_task_id), None)
                if not attempt or attempt.generation != r.execution_generation or attempt.requirement_version != p.requirement_version:
                    raise RecoveryError('developer resume phase has no valid current attempt')
            if phase in {'review', 'decide'}:
                submission = next((s for s in reversed(wf.submissions) if s.task_id == r.current_task_id), None)
                if not submission or submission.generation != r.execution_generation or submission.requirement_version != p.requirement_version:
                    raise RecoveryError('resume phase has no current submission')
                if phase == 'decide' and not any(v.submission_id == submission.id for v in wf.reviews):
                    raise RecoveryError('decision phase has no linked review')
            status = RunStatus(rec.original_status)
            if status in {RunStatus.RUNNING, RunStatus.PAUSED, RunStatus.PAUSE_REQUESTED}:
                status = RunStatus.RUNNING
            calls_by_invocation = {}
            for call in wf.call_records:
                calls_by_invocation[call.invocation_id] = max(
                    calls_by_invocation.get(call.invocation_id, 0), call.attempt)
            continued = []
            for c in wf.tool_continuations:
                if c.state != 'RUNNING':
                    continued.append(c)
                    continue
                unreturned_tools = [o for o in durable_operations if o.kind == 'file'
                    and o.checkpoint.invocation_id == c.invocation_id and o.updated_at > c.updated_at]
                state = 'FAILED' if unreturned_tools else 'TOOL_COMPLETED'
                continued.append(replace(c, state=state,
                    provider_calls=max(c.provider_calls, calls_by_invocation.get(c.invocation_id, 0))))
                if unreturned_tools:
                    status = RunStatus.WAITING_FOR_USER
            continuations = tuple(continued)
            wf = replace(wf, pending=None, tool_continuations=continuations,
                         recovery=replace(rec, requires_resume=False),
                         blocked_reason=('continued tool outcome requires intervention' if status is RunStatus.WAITING_FOR_USER
                                         and any(c.state == 'FAILED' for c in continuations) else
                                         rec.original_blocked_reason if status is RunStatus.WAITING_FOR_USER else None),
                         resume_phase='develop' if any(c.state == 'FAILED' for c in continuations)
                                      else rec.original_resume_phase)
            return commit_run(p, replace(r, status=status, phase=phase, workflow=wf), 'recovery.resumed', payload={'epoch': rec.epoch})
        return self.store.atomic_update(project_id, apply).run(run_id)
