"""Explicit M5.1 browser fixture; real durable events and harmless local tools.

Never used by app.main's default backend. All roots/DBs are disposable unless the
operator supplies AI_OFFICE_FIXTURE_HOME. Existing workflow rules are unchanged.
"""
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sys
import time
from app.main import create_app
from app.dev.workspace import request
from app.dev.workflow import ScriptedWorkflowProvider
from app.domain.agents import AgentKind
from app.domain.commands import CommandProfile, CommandRequest
from app.domain.projects import RunStatus
from app.orchestration.runner import WorkflowRunner
from app.permissions.policy import WorkspacePolicy
from app.tools.gateway import WorkspaceToolGateway
from app.persistence.sqlite import SQLiteStateStore

_fixture = TemporaryDirectory(prefix='m51-browser-')
_home = Path(os.environ.get('AI_OFFICE_FIXTURE_HOME', _fixture.name)).resolve()
_home.mkdir(parents=True, exist_ok=True)


class BrowserProvider(ScriptedWorkflowProvider):
    """FAIL then PASS with genuine per-attempt captured greeting changes."""
    def complete(self, req):
        response = super().complete(req)
        output = response.output
        phase = req.context['workflow']['phase']
        if phase == 'plan':
            output['summary'] = 'Update a disposable greeting file'
            output['assumptions'] = ['A harmless non-test command requires explicit permission']
            output['tasks'][0].update(description='Change greeting.txt to hello world.',
                acceptance_criteria=['Greeting contains hello world'])
        elif phase == 'develop':
            output.update(summary='Updated disposable greeting',
                changed_files=[{'path': 'greeting.txt', 'change_type': 'modified', 'summary': 'Expanded greeting'}],
                tests=[{'name': 'automated-tests', 'status': 'not_run', 'summary': 'No test command configured'}],
                notes=['Actual captured files; harmless command is not test evidence'])
        elif phase == 'review':
            evidence = json.loads(req.context['workflow']['evidence'][0])
            if not evidence['files'][0]['content'].startswith('hello world\n'):
                raise ValueError('Fixture greeting content does not satisfy the supplied criteria')
            output['checks_not_performed'] = ['Production code and automated tests']
        elif phase == 'final':
            output['limitations'] = ['Disposable browser fixture only; no production code or live provider',
                'The approved harmless command is not automated test evidence']
        return replace(response, output=output)


class BrowserRunner(WorkflowRunner):
    """Trusted fixture steps call existing tools; decisions still require HTTP humans."""
    def step(self):
        run = self.run
        if run.status is RunStatus.RUNNING and run.phase == 'develop' and not run.workflow.pending:
            approvals = self.store.approvals(self.project_id, self.run_id)
            if not approvals:
                attempt = run.workflow.attempts[-1]
                profile = self.workspace_gateway._profiles['fixture-check']
                req = CommandRequest(AgentKind.DEVELOPER, attempt.id, attempt.generation,
                    profile.name, profile.executable, profile.args, self.workspace_gateway.workspace_version())
                self.request_command(req)
                return False
            approval = approvals[0]
            if approval.status == 'pending':
                return False
            if approval.status == 'denied':
                self.controls.block('Fixture check permission denied. Cancel this run or inspect the decision.')
                return False
            if approval.status == 'approved':
                result = self.command_tool(approval.request, approval.id)
                if not result.succeeded:
                    return False
            # Every revision attempt records its own real change/capture boundary.
            old = self.file_tool(request(self, 'read', path='greeting.txt'))
            self.file_tool(request(self, 'write', path='greeting.txt', expected_hash=old.content_hash,
                content='hello world\n' + (f'revision {run.workflow.attempts[-1].number}\n' if run.workflow.attempts[-1].number > 1 else '')))
        return super().step()


def runner_factory(store, project_id, run_id):
    root = _home / 'workspaces' / project_id
    root.mkdir(parents=True, exist_ok=True)
    if not (root / 'greeting.txt').exists():
        (root / 'greeting.txt').write_text('hello\n')
    # Non-test profile demonstrates exact approval without claiming test evidence.
    profile = CommandProfile('fixture-check', str(Path(sys.executable).resolve()),
        ('-I', '-B', '-c', 'print("approved disposable fixture check")'))
    def hook(req):
        phase = req.context['workflow']['phase']
        # Explicit visual verification only: a genuinely pending fixture provider
        # call stays observable long enough for headed screenshots.
        context = json.dumps(req.context)
        visual = os.environ.get('AI_OFFICE_M6_VISUAL') == '1' and 'M6 visual verification' in context
        reviewer_capture = visual and 'M6 reviewer capture' in context
        delay = 8 if reviewer_capture and phase == 'review' else 4 if phase == 'develop' else 2 if visual else .4
        time.sleep(delay)
    provider = BrowserProvider(verdicts=('FAIL', 'PASS'), hook=hook)
    return BrowserRunner(store, project_id, run_id, provider,
        gateway=WorkspaceToolGateway(WorkspacePolicy(root), command_profiles=(profile,)))


_store = SQLiteStateStore(_home / 'state.db')
app = create_app(store=_store, runner_factory=runner_factory)
if os.environ.get('AI_OFFICE_M52_FIXTURE') == '1':
    # M5.2 inspection state is opt-in so its intentionally interrupted active run
    # cannot occupy the single-run slot in unrelated browser workflows.
    from app.dev.inspection import seed

    @app.post('/__fixture__/m52/seed')
    def seed_m52_fixture():
        existing = set(_store.list_run_refs())
        seed(_store, runner_factory)
        added = set(_store.list_run_refs()) - existing
        # Match a real reopen: only these newly seeded runs enter startup recovery.
        _store._startup_pending.update(added)
        app.state.service.recovery.startup()
        return {'projects': [project.id for project in _store.list_projects()]}
