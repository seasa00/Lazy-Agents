"""Application-owned command admission and execution supervision, independent of HTTP."""
from dataclasses import asdict, is_dataclass, replace
from hashlib import sha256
import json
import os
from decimal import Decimal
from app.domain.agents import AgentKind, AgentDefinition, default_agent_definitions
from app.domain.events import DomainEvent
from queue import Queue
from threading import Thread
from uuid import uuid4

from app.domain.projects import ProjectState, RunStatus
from app.agents.contracts import Requirement
from app.orchestration.recovery import RecoveryCoordinator
from app.permissions.policy import WorkspacePolicy
from app.api.schemas import ProjectSnapshot
from app.orchestration.graph_observability import redact_text


def public(value):
    """Never expose credential configuration or backend exception details."""
    if hasattr(value, 'to_dict'):
        value = value.to_dict()
    elif is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        return {str(k): public(v) for k, v in value.items()
                if not any(word in str(k).lower() for word in ('secret', 'password', 'api_key', 'credential', 'authorization', 'environment', 'private_reasoning', 'chain_of_thought'))}
    if isinstance(value, (tuple, list)):
        return [public(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        value = value.decode('utf-8')
    if isinstance(value, str):
        value = redact_text(value)
    return value


class ControlService:
    def __init__(self, store, runner_factory):
        self.store, self.runner_factory = store, runner_factory
        self.recovery = RecoveryCoordinator(store)
        self.runners = {}
        self.queue = Queue()
        self.worker = None
        self.failures = set()

    def startup(self):
        self.recovery.startup()
        self.worker = Thread(target=self._work, name='workflow-executor', daemon=True)
        self.worker.start()

    def shutdown(self):
        # Stop admission externally first, then request a safe boundary for active IO.
        for runner in tuple(self.runners.values()):
            try:
                if runner.run.status is RunStatus.RUNNING:
                    runner.controls.pause()
            except ValueError:
                pass
        self.queue.put(None)
        if self.worker:
            self.worker.join()  # store remains open until all owned execution settles

    def _work(self):
        while (identity := self.queue.get()) is not None:
            try:
                self.runner(*identity).run_until_stopped()
            except Exception:
                self.failures.add(identity)
                try:
                    self.runner(*identity).controls.block('backend execution failed; inspect recovery')
                except Exception:
                    pass

    def runner(self, project_id, run_id):
        identity = (project_id, run_id)
        if identity not in self.runners:
            runner = self.runner_factory(self.store, project_id, run_id)
            project = self.store.get_project(project_id)
            run = project.run(run_id)
            if run.workflow and run.workflow.agent_snapshots:
                # Restart uses immutable run configuration, never newer project settings.
                definitions = {}
                for snapshot in run.workflow.agent_snapshots:
                    data = snapshot.to_dict()
                    data['id'] = data.pop('agent_id')
                    data.pop('config_digest')
                    data['status'] = 'idle'
                    definitions[snapshot.kind] = AgentDefinition.from_dict(data)
                runner.definitions = definitions
            elif project.agent_definitions:
                runner.definitions = {a.kind: a for a in project.agent_definitions}
            self.runners[identity] = runner
        return self.runners[identity]

    def snapshot(self, project_id):
        project, cursor = self.store.snapshot(project_id)
        return ProjectSnapshot(project=public(project), event_cursor=cursor)

    def create(self, body, key):
        fingerprint = sha256(body.model_dump_json().encode()).hexdigest()
        def apply():
            p = self.store.create_project(ProjectState('project_' + uuid4().hex, body.name, body.goal,
                requirements=tuple(Requirement.from_dict(r.model_dump()) for r in body.requirements)))
            return self._ack(key, p.id)
        return self.store.admit_command('create', key, fingerprint, None, apply)

    def _ack(self, key, project_id, run_id=None, pending=False):
        snapshot = self.snapshot(project_id)
        return dict(command_id=key, status='pending' if pending else 'applied', project_id=project_id,
                    run_id=run_id, project_version=snapshot.project['version'], event_cursor=snapshot.event_cursor)

    def command(self, project_id, run_id, name, body, key):
        fingerprint = sha256(json.dumps([run_id, name, body.model_dump()], sort_keys=True).encode()).hexdigest()
        def apply():
            rid = run_id
            if name == 'plan':
                rid = self.store.create_run(project_id).id
                runner = self.runner(project_id, rid)
                runner.initialize()
                self.queue.put((project_id, rid))
            else:
                runner = self.runner(project_id, rid)
                if name == 'approve':
                    runner.approve()
                elif name == 'start':
                    if runner.run.status is not RunStatus.RUNNING or not runner.run.approved:
                        raise ValueError('start requires approved running workflow')
                    self.queue.put((project_id, rid))
                elif name in {'pause', 'cancel'}:
                    getattr(runner.controls, name)()
                elif name == 'resume':
                    runner.controls.resume(expected_epoch=body.expected_epoch)
                    self.queue.put((project_id, rid))
                elif name == 'permission':
                    if body.approval_id is None or body.approved is None or not body.reason.strip():
                        raise ValueError('permission decision fields required')
                    runner.controls.resolve_command(body.approval_id, approved=body.approved, reason=body.reason)
                    if any(c.permission_id == body.approval_id and c.state in {
                            'APPROVED_PENDING_EXECUTION', 'TOOL_COMPLETED'}
                           for c in runner.run.workflow.tool_continuations):
                        self.queue.put((project_id, rid))
                elif name == 'recovery':
                    self.recovery.resolve(project_id, rid, body.operation_id, action=body.action,
                        reason=body.reason, runner=runner, quiescent=body.quiescent, expected_epoch=body.expected_epoch)
                else:
                    raise ValueError('unknown command')
            return self._ack(key, project_id, rid, pending=name in {'plan', 'start', 'resume'} or
                             runner.run.status is RunStatus.PAUSE_REQUESTED)
        return self.store.admit_command(project_id, key, fingerprint, body.expected_version, apply)

    def read(self, project_id, run_id, kind):
        if kind == 'recovery':
            return public(self.recovery.inspect(project_id, run_id))
        if kind == 'usage':
            return public(self.store.usage(project_id, run_id))
        if kind == 'permissions':
            self.store.get_run_metadata(project_id, run_id)
            return public(self.store.approvals(project_id, run_id))
        p = self.store.get_project(project_id)
        r = p.run(run_id)
        if kind == 'tasks':
            return public(tuple(t for t in p.tasks if t.id in r.task_ids))
        if kind == 'reviews':
            return public(r.workflow.reviews if r.workflow else ())
        if kind == 'evidence':
            return public(r.workflow.submissions if r.workflow else ())
        raise ValueError('unknown query')

    def settings(self, project_id):
        project = self.store.get_project(project_id)
        definitions = project.agent_definitions or tuple(default_agent_definitions().values())
        return public({'project_version': project.version, 'applies_to': 'next_run',
            'agents': definitions, 'editable_fields': ['name', 'role', 'model', 'system_instructions'],
            'provider_configured': bool(os.environ.get('OPENROUTER_API_KEY')),
            'note': 'Future runs only. Active and completed invocations retain immutable configuration. Tools, permissions and limits are backend-configured.'})

    def configure(self, project_id, body, key):
        fingerprint = sha256(body.model_dump_json().encode()).hexdigest()
        def apply():
            def change(project):
                definitions = project.agent_definitions or tuple(default_agent_definitions().values())
                updated = tuple(replace(a, name=body.name, role=body.role, model=body.model,
                    system_instructions=body.system_instructions, config_version=a.config_version + 1)
                    if a.kind is AgentKind(body.kind) else a for a in definitions)
                return replace(project, agent_definitions=updated), [DomainEvent(project_id,
                    'agent.configuration_updated', {'kind': body.kind, 'applies_to': 'next_run'})]
            self.store.atomic_update(project_id, change, expected_version=body.expected_version)
            return self._ack(key, project_id)
        return self.store.admit_command(project_id, key, fingerprint, body.expected_version, apply)

    def inspection(self, project_id, run_id, include_agent_debug=False):
        from app.orchestration.graph_observability import project_agent_debug, project_office_poses
        project = self.store.get_project(project_id)
        run = project.run(run_id)
        runner = self.runners.get((project_id, run_id))
        gateway = runner.workspace_gateway if runner else None
        capabilities = None if gateway is None else {
            kind.value: {'files': {operation: gateway.policy.decide(kind, operation, 'captured-submission' if kind is not AgentKind.DEVELOPER else None)
                for operation in ('list', 'read', 'write', 'edit', 'capture_submission')},
                'command_request': gateway.policy.decide_command(kind)} for kind in AgentKind}
        usage = self.store.usage(project_id, run_id)
        tools = self.store.tool_history(project_id, run_id)
        operations = self.store.operations(project_id, run_id, metadata_only=True)
        detail = {'recent_events': self.store.recent_run_events(project_id, run_id),
            'capabilities': capabilities, 'usage': self.store.usage(project_id, run_id),
            'project_usage': self.store.usage(project_id),
            'tools': tools,
            'operations': operations,
            'recovery': self.recovery.inspect(project_id, run_id),
            'settings': self.settings(project_id),
            'limits': run.workflow.limits if run.workflow else None}
        if include_agent_debug:
            detail['agent_debug'] = project_agent_debug(project, run,
                self.store.events(project_id), tools, operations, usage)
            detail['office_poses'] = project_office_poses(run)
        return public(detail)

    def artifact(self, project_id, run_id, submission_id, path):
        p = self.store.get_project(project_id)
        r = p.run(run_id)
        # No arbitrary sidecar or live workspace path; immutable captured files only.
        if not p.workspace_root:
            raise ValueError('no workspace artifacts')
        runner = self.runner(project_id, run_id)
        policy = runner.workspace_gateway.policy if runner.workspace_gateway else WorkspacePolicy(p.workspace_root)
        policy.check_path(path)
        for submission in r.workflow.submissions:
            if submission.id == submission_id and submission.files:
                for file in submission.files.files:
                    if file.path == path:
                        return public({'artifact_id': submission.id + ':' + path, 'submission_id': submission.id,
                            'task_id': submission.task_id, 'attempt_id': submission.attempt_id,
                            'version': submission.version, 'path': path, 'content_hash': file.content_hash,
                            'before_hash': file.before_hash, 'diff': file.diff,
                            'created_at': None, 'content': file.content.decode('utf-8')})
        raise KeyError('artifact not found')
