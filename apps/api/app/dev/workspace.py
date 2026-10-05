"""M3.1 real-file verification, exclusively in a disposable TemporaryDirectory."""
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from app.agents.contracts import Requirement
from app.dev.workflow import ScriptedWorkflowProvider, approve_generated
from app.domain.agents import AgentKind
from app.domain.projects import ProjectState
from app.orchestration.runner import WorkflowRunner
from app.persistence.memory import InMemoryStateStore
from app.permissions.policy import WorkspacePolicy
from app.tools.gateway import FileToolRequest, WorkspaceToolGateway


class WorkspaceFixtureProvider(ScriptedWorkflowProvider):
    """Deterministic role outputs. Real edits use the trusted runner entrypoint."""
    def complete(self, request):
        response = super().complete(request)
        out = response.output
        phase = request.context['workflow']['phase']
        if phase == 'plan':
            out['summary'] = 'Update a disposable greeting file'
            out['assumptions'] = ['No commands executed']
            out['tasks'][0].update(description='Change greeting.txt to hello world.',
                                   acceptance_criteria=['Greeting contains hello world'])
        elif phase == 'develop':
            out.update(summary='Updated greeting file',
                changed_files=[{'path': 'greeting.txt', 'change_type': 'modified', 'summary': 'Expanded greeting'}],
                tests=[{'name': 'execution', 'status': 'not_run', 'summary': 'No commands executed'}],
                notes=['File inspection only'])
        elif phase == 'review':
            evidence = json.loads(request.context['workflow']['evidence'][0])
            if evidence['files'][0]['content'] != 'hello world\n':
                raise ValueError('Reviewer did not receive the exact captured version')
            out.update(summary='Captured greeting verified', checks_not_performed=['Command execution'])
            for assessment in out['assessments']:
                assessment['notes'] = 'Inspected immutable captured bytes'
        elif phase == 'final':
            out.update(summary='Captured greeting accepted', limitations=['No commands executed'])
        return replace(response, output=out)


def make_workspace_runner(root, provider=None, *, command_profiles=(), command_limits=None, **policy_options):
    store = InMemoryStateStore()
    store.create_project(ProjectState('workspace-demo', 'M3.1', 'Update a greeting in a disposable workspace',
        requirements=(Requirement('greeting', 'Expand greeting', ('Greeting contains hello world',)),)))
    run = store.create_run('workspace-demo', run_id='workspace-run')
    gateway = WorkspaceToolGateway(WorkspacePolicy(root, **policy_options), command_profiles=command_profiles,
                                   **({} if command_limits is None else {'command_limits': command_limits}))
    runner = WorkflowRunner(store, 'workspace-demo', run.id, provider or WorkspaceFixtureProvider(), gateway=gateway)
    runner.initialize()
    approve_generated(runner)
    runner.step()
    return runner


def request(runner, operation, actor=AgentKind.DEVELOPER, **kwargs):
    attempt = runner.run.workflow.attempts[-1]
    return FileToolRequest(operation, actor, attempt.id, attempt.generation, **kwargs)


def demonstration():
    with TemporaryDirectory(prefix='m31-') as disposable:
        base = Path(disposable)
        root = base / 'workspace'
        root.mkdir()
        live = root / 'greeting.txt'
        live.write_text('hello\n')
        outside = base / 'outside.txt'
        outside.write_text('untouched')
        runner = make_workspace_runner(root)
        original = runner.file_tool(request(runner, 'read', path='greeting.txt'))
        denied = []
        for name, req in [
            ('outside_root', request(runner, 'write', path=str(outside), content='bad', expected_hash=None)),
            ('reviewer_mutation', request(runner, 'write', AgentKind.REVIEWER, path='greeting.txt', expected_hash=original.content_hash)),
            ('manager_mutation', request(runner, 'write', AgentKind.MANAGER, path='greeting.txt', expected_hash=original.content_hash)),
        ]:
            try:
                runner.file_tool(req)
            except ValueError:
                denied.append(name)
        assert len(denied) == 3 and outside.read_text() == 'untouched' and live.read_text() == 'hello\n'
        runner.file_tool(request(runner, 'edit', path='greeting.txt', expected_hash=original.content_hash,
                                 old_text='hello', new_text='hello world'))
        edited = runner.file_tool(request(runner, 'read', path='greeting.txt'))
        live.write_text('external competing edit\n')
        try:
            runner.file_tool(request(runner, 'write', path='greeting.txt', expected_hash=edited.content_hash, content='bad'))
        except ValueError:
            denied.append('hash_conflict')
        assert live.read_text() == 'external competing edit\n' and len(denied) == 4
        external = runner.file_tool(request(runner, 'read', path='greeting.txt'))
        runner.file_tool(request(runner, 'write', path='greeting.txt', expected_hash=external.content_hash,
                                 content='hello world\n'))
        runner.step()  # Developer proposal and immutable file capture.
        sub = runner.run.workflow.submissions[0]
        digest = sub.digest
        live.write_text('later external version\n')
        reviewed = runner.file_tool(request(runner, 'read', AgentKind.REVIEWER,
            path='greeting.txt', submission_id=sub.id))
        assert reviewed.content == 'hello world\n' and sub.files.files[0].content == b'hello world\n'
        runner.run_until_stopped()
        assert runner.run.workflow.submissions[0].digest == digest
        return {'status': runner.run.status.value, 'denied': denied, 'submission_id': sub.id,
                'submission_digest': digest, 'captured_content': reviewed.content,
                'live_content': live.read_text(), 'diff': sub.files.files[0].diff,
                'tool_operations': len(runner.workspace_gateway.records), 'disposable_workspace': True}


if __name__ == '__main__':
    print(json.dumps(demonstration(), indent=2))
