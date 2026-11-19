"""Role-enforced files and exact-approved commands; no unrestricted shell or deletion tool."""
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4
import json
from app.domain.agents import AgentKind
from app.domain.artifacts import CapturedSubmission, ToolCallRecord, FileChange, content_hash
from app.domain.recovery import ExecutionCheckpoint, ExecutionOperation, OperationStage, OutcomeCertainty
from app.tools.files import WorkspaceFiles, FileConflict
from app.tools.submissions import capture
from app.domain.commands import (CommandLimits, CommandApproval, CommandAuditRecord, CommandRequest,
                                 CommandResult, TestEvidence, scope_digest)
from app.tools.commands import (workspace_version, executable_digest, command_environment,
                                launch, collect)


@dataclass(frozen=True, slots=True)
class FileToolRequest:
    operation: str
    actor: AgentKind
    attempt_id: str
    generation: int
    path: str = '.'
    content: str = ''
    expected_hash: str | None = ''  # None explicitly means create; empty means omitted.
    old_text: str = ''
    new_text: str = ''
    submission_id: str | None = None
    paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FileToolResult:
    content: str | None = None
    content_hash: str | None = None
    entries: tuple[str, ...] = ()
    submission: CapturedSubmission | None = None


class WorkspaceToolGateway:
    def __init__(self, policy, *, before_mutation=None, command_profiles=(), command_limits=CommandLimits()):
        self.audit_sink = lambda record, approval=None: None
        self.operation_sink = lambda operation: operation
        self._command_operation = None
        self._operations = {}
        self.policy = policy
        self._files = WorkspaceFiles(policy)
        self.before_mutation = before_mutation or self._deny_unbound
        self._records = []
        self._changes = {}
        self._submissions = {}
        self._sealed = set()
        self.command_limits = command_limits
        self._profiles = {p.name: p for p in command_profiles}
        if len(self._profiles) != len(command_profiles):
            raise ValueError('duplicate command profile')
        self._command_lock = RLock()
        self._approvals = {}
        self._command_records = []
        self._command_results = []
        self._active_command = None
        self._command_requests = 0
        self._command_launches = 0

    def _persist_operation(self, operation):
        saved = self.operation_sink(operation) or operation
        self._operations[saved.id] = saved
        return saved

    def _prepared(self, identity, kind, scope_request, **kwargs):
        cp = ExecutionCheckpoint('', '', 'develop', scope_request.generation, 0, 1,
            attempt_id=scope_request.attempt_id, operation_id=identity, boundary=kind + '.prepared', safe_phase='develop')
        return self._persist_operation(ExecutionOperation(identity, kind, cp, **kwargs))

    def restore(self, operations, approvals, run, history=()):
        """Restore application-owned evidence/counters; never launch or signal a process."""
        self._approvals = {a.id: a for a in approvals}
        self._operations = {op.id: op for op in operations}
        self._records = [r for r in history if isinstance(r, ToolCallRecord) and not r.id.endswith(':intent')]
        self._command_records = [r for r in history if isinstance(r, CommandAuditRecord)]
        self._command_requests = sum(getattr(r, 'action', '') == 'request' for r in history)
        self._command_launches = sum(getattr(r, 'action', '') == 'intent' for r in history)
        wf = run.workflow
        if wf is None:
            return
        results = {r.id: r for r in wf.command_results}
        for op in operations:
            if op.kind == 'command' and isinstance(op.result, CommandResult):
                results.setdefault(op.result.id, op.result)
            if op.kind != 'file' or op.checkpoint.generation != run.execution_generation:
                continue
            if op.certainty is OutcomeCertainty.CONFIRMED_SUCCESS and op.change:
                scope = (op.checkpoint.attempt_id, op.checkpoint.generation)
                changes = self._changes.setdefault(scope, {})
                baseline = changes.get(op.path, (op.change.before, None))[0]
                if baseline == op.change.content:
                    changes.pop(op.path, None)
                else:
                    changes[op.path] = (baseline, op.change.content)
            if isinstance(op.result, CapturedSubmission) and op.certainty is OutcomeCertainty.CONFIRMED_SUCCESS:
                self._submissions[op.result.id] = op.result
                self._sealed.add((op.result.attempt_id, op.result.generation))
        for sub in wf.submissions:
            if sub.files:
                self._submissions[sub.id] = sub.files
                self._sealed.add((sub.attempt_id, sub.generation))
        self._command_results = list(results.values())

    @property
    def approvals(self):
        return tuple(self._approvals.values())

    @property
    def command_records(self):
        return tuple(self._command_records)

    @property
    def command_results(self):
        return tuple(self._command_results)

    @property
    def command_active(self):
        return self._active_command is not None

    def workspace_version(self):
        return workspace_version(self._files, self.command_limits)

    def command_request(self, profile_name, *, attempt_id, generation, actor=AgentKind.DEVELOPER):
        """Build a request from a configured immutable profile, never model argv."""
        profile = self._profiles.get(profile_name)
        if profile is None:
            raise ValueError('unknown approved command profile')
        if actor is not AgentKind.DEVELOPER or not self.policy.decide_command(actor).allowed:
            raise ValueError('command request denied')
        return CommandRequest(actor, attempt_id, generation, profile.name, profile.executable,
            profile.args, self.workspace_version(), timeout_seconds=min(10, self.command_limits.max_timeout_seconds),
            max_output_bytes=min(8192, self.command_limits.max_output_bytes))

    def _command_scope(self, request, *, check_execution=True):
        decision = self.policy.decide_command(request.actor)
        if not decision.allowed:
            raise ValueError(decision.reason)
        if check_execution:
            self.before_mutation(request)
        if (request.attempt_id, request.generation) in self._sealed:
            raise ValueError('submitted attempt is immutable')
        profile = self._profiles.get(request.profile)
        if profile is None or (profile.executable, profile.args) != (request.executable, request.args):
            raise ValueError('command does not match a configured profile')
        if request.timeout_seconds > self.command_limits.max_timeout_seconds or request.max_output_bytes > self.command_limits.max_output_bytes:
            raise ValueError('command limits exceeded')
        parts = self.policy.check_path(request.cwd, listing=True)
        with self._files.directory(parts):
            pass
        environment = command_environment(request)
        if self.workspace_version() != request.workspace_version:
            raise ValueError('command approval workspace version is stale')
        digest = scope_digest(request, self.policy.root, executable_digest(request.executable), environment, profile)
        return digest, environment, profile

    def _command_record(self, action, request, approval_id, outcome, reason=''):
        record = CommandAuditRecord('tool_' + uuid4().hex, action,
            'human' if action == 'decision' else 'system' if action == 'invalidate' else request.actor.value, request.attempt_id,
            request.generation, approval_id, outcome, reason, 2)
        self.audit_sink(record, self._approvals.get(approval_id))
        self._command_records.append(record)

    def request_command(self, request):
        """Record a pending intervention; this never authorizes execution."""
        with self._command_lock:
            try:
                self._command_requests += 1
                if self._command_requests > self.command_limits.max_requests:
                    raise ValueError('command request limit exceeded')
                if self.command_active:
                    raise ValueError('one command at a time')
                digest, _, _ = self._command_scope(request)
                approval = CommandApproval('approval_' + uuid4().hex, request, digest)
                self._approvals[approval.id] = approval
                self._command_record('request', request, approval.id, 'pending')
                return approval
            except (ValueError, OSError) as exc:
                self._command_record('request', request, None, 'denied', str(exc) if isinstance(exc, ValueError) else 'filesystem error')
                raise ValueError(str(exc) if isinstance(exc, ValueError) else 'command scope inaccessible') from exc

    def resolve_command(self, approval_id, *, approved, reason):
        """Trusted human-control API, never an agent tool."""
        with self._command_lock:
            approval = self._approvals.get(approval_id)
            if approval is None or approval.status != 'pending':
                raise ValueError('permission intervention is not pending')
            if not isinstance(approved, bool) or not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
                raise ValueError('explicit boolean decision and bounded reason required')
            if approved:
                try:
                    digest, _, _ = self._command_scope(approval.request, check_execution=False)
                    if digest != approval.scope_digest:
                        raise ValueError('approval scope changed')
                except (ValueError, OSError) as exc:
                    self._command_record('decision', approval.request, approval_id, 'rejected', 'approval scope is no longer valid')
                    raise ValueError('approval scope is no longer valid') from exc
            approval = replace(approval, status='approved' if approved else 'denied', reason=reason)
            self._approvals[approval_id] = approval
            self._command_record('decision', approval.request, approval_id, approval.status, reason)
            return approval

    def invalidate_commands(self, reason):
        with self._command_lock:
            for identity, approval in tuple(self._approvals.items()):
                if approval.status in {'pending', 'approved'}:
                    self._approvals[identity] = replace(approval, status='invalidated', reason=reason)
                    self._command_record('invalidate', approval.request, identity, 'invalidated', reason)

    def start_command(self, request, approval_id, *, operation_id=None):
        """Check+consume approval and launch while the runner holds the control lock."""
        with self._command_lock:
            try:
                operation_id = operation_id or 'command_exec_' + uuid4().hex
                existing = self._operations.get(operation_id)
                if existing and (existing.kind != 'command' or existing.request != request
                                 or existing.approval_id != approval_id):
                    raise ValueError('command operation identity mismatch')
                if existing and existing.stage is not OperationStage.PREPARED:
                    raise ValueError('command operation already crossed its execution boundary')
                if self.command_active:
                    raise ValueError('one command at a time')
                if not existing and self._command_launches >= self.command_limits.max_commands:
                    raise ValueError('command launch limit exceeded')
                digest, environment, profile = self._command_scope(request)
                approval = self._approvals.get(approval_id)
                reusable_prestart = bool(existing and existing.stage is OperationStage.PREPARED
                                         and approval is not None and approval.status == 'consumed')
                if (approval is None or (approval.status != 'approved' and not reusable_prestart) or approval.request != request
                        or approval.scope_digest != digest):
                    raise ValueError('missing, denied, consumed or mismatched exact command approval')
                self.before_mutation(request)  # Final pause/cancel check before Popen.
                operation = existing or self._prepared(operation_id, 'command', request,
                    request=request, approval_id=approval_id, operation=request.profile)
                if approval.status == 'approved':
                    self._approvals[approval_id] = replace(approval, status='consumed')
                    self._command_launches += 1
                    self._command_record('intent', request, approval_id, 'pending')
                operation = self._persist_operation(operation.evolve(stage=OperationStage.EXECUTING))
                self._command_operation = operation
                try:
                    running = launch(request, approval_id, profile.is_test, self.policy.root, environment)
                except OSError:
                    running = CommandResult('command_' + uuid4().hex, approval_id, request, profile.is_test,
                        'error', None, '', '', False, False, datetime.now(timezone.utc).isoformat(), 0,
                        request.workspace_version, None, None, True)
                if not isinstance(running, CommandResult):
                    operation = self._persist_operation(operation.evolve(pid=running.process.pid))
                    self._command_operation = operation
                self._active_command = running
                self._command_record('launch', request, approval_id, 'started' if not isinstance(running, CommandResult) else 'error')
                return running
            except (ValueError, OSError) as exc:
                self._command_record('launch', request, approval_id, 'denied', str(exc) if isinstance(exc, ValueError) else 'filesystem error')
                raise ValueError(str(exc) if isinstance(exc, ValueError) else 'command scope inaccessible') from exc

    def collect_command(self, running, stop_reason):
        # Deliberately outside the gateway/store locks: controls must remain responsive.
        return running if isinstance(running, CommandResult) else collect(running, stop_reason, self.workspace_version)

    def finish_command(self, running, result):
        with self._command_lock:
            if self._active_command is not running:
                raise ValueError('command ownership mismatch')
            certainty = (OutcomeCertainty.CONFIRMED_SUCCESS if result.succeeded else
                         OutcomeCertainty.CONFIRMED_FAILURE if result.cleanup_complete else OutcomeCertainty.UNCERTAIN)
            if self._command_operation:
                self._persist_operation(self._command_operation.evolve(stage=OperationStage.SETTLED,
                    certainty=certainty, result=result))
            self._command_results.append(result)
            if result.cleanup_complete:
                self._active_command = None
            self._command_record('result', result.request, result.approval_id, result.outcome)

    def test_evidence(self, attempt_id, generation, *, version=None):
        if version is None:
            try:
                version = self.workspace_version()
            except (ValueError, OSError):
                version = 'unavailable'
        return tuple(TestEvidence(r, version, r.workspace_before != version or r.workspace_after != version)
                     for r in self._command_results
                     if r.is_test and r.request.attempt_id == attempt_id and r.request.generation == generation)

    @staticmethod
    def _deny_unbound(request):
        raise ValueError('workspace mutation requires a bound execution-control guard')

    @property
    def records(self):
        return tuple(self._records)

    def _check_result(self, result):
        data = (result.submission.serialize() if result.submission else
                json.dumps({'content': result.content, 'content_hash': result.content_hash,
                            'entries': result.entries}))
        if len(data.encode()) > self.policy.max_result_bytes:
            raise ValueError('tool result size limit exceeded')

    def execute(self, request):
        with self._command_lock:
            return self._execute_file(request)

    def _execute_file(self, request):
        operation_id = 'file_' + uuid4().hex
        self.audit_sink(ToolCallRecord(operation_id + ':intent', request.actor.value,
            request.operation, request.attempt_id, request.generation, request.path,
            request.submission_id, 'pending', protocol_version=2))
        execution = None
        outcome, before, after = 'denied', None, None
        try:
            decision = self.policy.decide(request.actor, request.operation, request.submission_id)
            if not decision.allowed:
                raise ValueError(decision.reason)
            if not request.attempt_id or request.generation < 1:
                raise ValueError('attempt and generation required')
            scope = (request.attempt_id, request.generation)
            op = request.operation
            execution = self._prepared(operation_id, 'file', request, operation=op, path=request.path)
            if op in {'write', 'edit', 'capture_submission'}:
                if self.command_active:
                    raise ValueError('workspace mutation denied while command is active')
                if scope in self._sealed:
                    raise ValueError('submitted attempt is immutable')
                self.before_mutation(request)
            if op == 'capture_submission':
                if request.submission_id != request.attempt_id + ':submission' or request.submission_id in self._submissions:
                    raise ValueError('invalid or duplicate submission identity')
                has_tests = any(r.is_test and r.request.attempt_id == request.attempt_id
                                and r.request.generation == request.generation for r in self._command_results)
                version = self.workspace_version() if has_tests else None
                snapshot = capture(self._files, request.submission_id, request.attempt_id,
                                   request.generation, self._changes.get(scope, {}), request.paths,
                                   self.policy.max_result_bytes)
                if has_tests:
                    if self.workspace_version() != version:
                        raise FileConflict('workspace changed during submission capture')
                    snapshot = replace(snapshot, workspace_version=version,
                        tests=self.test_evidence(request.attempt_id, request.generation, version=version))
                self._check_result(FileToolResult(submission=snapshot))
                self.before_mutation(request)
                execution = self._persist_operation(execution.evolve(stage=OperationStage.EXECUTING, result=snapshot))
                self._submissions[snapshot.id] = snapshot
                self._sealed.add(scope)
                result = FileToolResult(submission=snapshot)
            elif request.submission_id:
                if op not in {'read', 'list'}:
                    raise ValueError('captured submissions are read only')
                snapshot = self._submissions.get(request.submission_id)
                if snapshot is None or (snapshot.attempt_id, snapshot.generation) != scope:
                    raise ValueError('unknown submission or mismatched scope')
                if op == 'list':
                    if request.path != '.':
                        raise ValueError('submission list uses root path')
                    result = FileToolResult(entries=tuple(f.path for f in snapshot.files))
                else:
                    self.policy.check_path(request.path)
                    file = next((f for f in snapshot.files if f.path == request.path), None)
                    if file is None:
                        raise ValueError('path not captured in submission')
                    result = FileToolResult(file.content.decode('utf-8'), file.content_hash)
            elif op == 'list':
                result = FileToolResult(entries=self._files.list(request.path))
            elif op == 'read':
                data = self._files.read(request.path)
                if data is None:
                    raise ValueError('file does not exist')
                result = FileToolResult(data.decode('utf-8'), content_hash(data))
            else:
                if request.expected_hash is not None and (not isinstance(request.expected_hash, str)
                        or len(request.expected_hash) != 64
                        or any(c not in '0123456789abcdef' for c in request.expected_hash)):
                    raise ValueError('explicit expected hash required; None only for creation')
                data = request.content
                if op == 'edit':
                    current = self._files.read(request.path)
                    if current is None or content_hash(current) != request.expected_hash:
                        raise FileConflict('expected hash conflict')
                    text = current.decode('utf-8')
                    if not request.old_text or text.count(request.old_text) != 1:
                        raise ValueError('edit must match exactly one nonempty occurrence')
                    data = text.replace(request.old_text, request.new_text, 1)
                if not isinstance(data, str):
                    raise ValueError('file content must be UTF-8 text')
                encoded = data.encode('utf-8')
                self._check_result(FileToolResult(content_hash=content_hash(encoded)))
                prior = self._files.read(request.path)
                if (None if prior is None else content_hash(prior)) != request.expected_hash:
                    raise FileConflict('expected hash conflict')
                change = FileChange(request.path, prior, encoded, '')
                execution = self._persist_operation(execution.evolve(change=change, before_hash=change.before_hash,
                    after_hash=change.content_hash))
                execution = self._persist_operation(execution.evolve(stage=OperationStage.EXECUTING))
                previous = self._files.write(request.path, encoded, request.expected_hash,
                                            lambda: self.before_mutation(request))
                changes = self._changes.setdefault(scope, {})
                baseline = changes.get(request.path, (previous, None))[0]
                if baseline == encoded:
                    changes.pop(request.path, None)
                else:
                    changes[request.path] = (baseline, encoded)
                before = None if previous is None else content_hash(previous)
                after = content_hash(encoded)
                result = FileToolResult(content_hash=after)
            self._check_result(result)
            outcome = 'succeeded'
            return result
        except FileConflict:
            outcome = 'conflict'
            raise
        except (OSError, UnicodeError) as exc:
            # Do not expose OS paths or content in ordinary audit/error output.
            outcome = 'error'
            raise ValueError('unsupported or inaccessible workspace path/content') from exc
        finally:
            if execution:
                certainty = (OutcomeCertainty.CONFIRMED_SUCCESS if outcome == 'succeeded' else
                    OutcomeCertainty.UNCERTAIN if execution.stage is OperationStage.EXECUTING and outcome == 'error' else
                    OutcomeCertainty.CONFIRMED_FAILURE)
                execution = self._persist_operation(execution.evolve(stage=OperationStage.SETTLED, certainty=certainty))
            record = ToolCallRecord(operation_id, request.actor.value,
                request.operation, request.attempt_id, request.generation, request.path,
                request.submission_id, outcome, before, after, 2)
            self.audit_sink(record)
            self._records.append(record)
