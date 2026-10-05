"""M3.2 disposable real-process demo. Approvals apply only to explicit harmless fixtures."""
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import time
from app.dev.workspace import make_workspace_runner, request as file_request
from app.domain.agents import AgentKind
from app.domain.commands import CommandProfile, CommandRequest


def command_request(runner, profile):
    attempt = runner.run.workflow.attempts[-1]
    return CommandRequest(AgentKind.DEVELOPER, attempt.id, attempt.generation, profile.name,
        profile.executable, profile.args, runner.workspace_gateway.workspace_version(),
        timeout_seconds=5, max_output_bytes=2048)


def approve_fixture(runner, req):
    approval = runner.request_command(req)
    runner.controls.resolve_command(approval.id, approved=True,
        reason='Explicit approval of this exact harmless disposable verification fixture')
    return approval.id


def demonstration():
    with TemporaryDirectory(prefix='m32-demo-') as disposable:
        root = Path(disposable).resolve()
        project = root / 'project'
        project.mkdir()
        (project / 'greeting.txt').write_text('hello\n')
        (project / 'test_greeting.py').write_text(
            "from pathlib import Path\nassert Path('greeting.txt').read_text() == 'hello world\\n'\nprint('1 test passed')\n")
        executable = str(Path(sys.executable).resolve())
        profile = CommandProfile('greeting-tests', executable, ('-I', '-B', 'test_greeting.py'), True)
        runner = make_workspace_runner(project, command_profiles=(profile,))
        before = runner.file_tool(file_request(runner, 'read', path='greeting.txt'))
        runner.file_tool(file_request(runner, 'edit', path='greeting.txt', expected_hash=before.content_hash,
                                     old_text='hello', new_text='hello world'))
        req = command_request(runner, profile)
        result = runner.command_tool(req, approve_fixture(runner, req))
        assert result.succeeded and result.workspace_before == result.workspace_after
        runner.run_until_stopped()
        sub = runner.run.workflow.submissions[0]
        assert runner.run.status.value == 'completed' and sub.files.tests[0].passed
        review = next(q for q in runner.provider.requests if q.context['workflow']['phase'] == 'review')
        evidence = json.loads(review.context['workflow']['evidence'][0])
        assert evidence['tests'][0]['command']['id'] == result.id and evidence['tests'][0]['passed']

        # A second disposable run exercises denial and cancellation without reopening a sealed attempt.
        controls_project = root / 'controls'
        controls_project.mkdir()
        (controls_project / 'greeting.txt').write_text('hello\n')
        (controls_project / 'denied.py').write_text("open('must-not-exist', 'w').write('executed')\n")
        (controls_project / 'slow.py').write_text('import time\ntime.sleep(30)\n')
        denied_profile = CommandProfile('denied', executable, ('-I', '-B', 'denied.py'))
        slow_profile = CommandProfile('slow', executable, ('-I', '-B', 'slow.py'))
        controlled = make_workspace_runner(controls_project, command_profiles=(denied_profile, slow_profile))
        denied_req = command_request(controlled, denied_profile)
        permission = controlled.request_command(denied_req)
        controlled.controls.resolve_command(permission.id, approved=False, reason='Demonstrate explicit denial')
        denied = False
        try:
            controlled.command_tool(denied_req, permission.id)
        except ValueError:
            denied = True
        assert denied and not (controls_project / 'must-not-exist').exists()
        slow_req = command_request(controlled, slow_profile)
        approval = approve_fixture(controlled, slow_req)
        results, errors = [], []
        def run_slow():
            try:
                results.append(controlled.command_tool(slow_req, approval))
            except Exception as exc:
                errors.append(str(exc))
        thread = Thread(target=run_slow)
        thread.start()
        try:
            deadline = time.monotonic() + 3
            while not controlled.workspace_gateway.command_active and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            controlled.controls.cancel()
        finally:
            thread.join(8)
        assert not thread.is_alive() and not errors and results
        canceled = results[0]
        assert canceled.outcome == 'canceled' and not canceled.succeeded and canceled.cleanup_complete
        try:
            os.kill(canceled.pid, 0)
        except ProcessLookupError:
            reaped = True
        else:
            reaped = False
        assert reaped

        (project / 'greeting.txt').write_text('later external version\n')
        current = runner.workspace_gateway.test_evidence(req.attempt_id, req.generation)[0]
        assert current.stale and not current.passed
        assert runner.run.workflow.submissions[0].digest == sub.digest and sub.files.tests[0].passed
        return {'workflow_status': runner.run.status.value, 'test_outcome': result.outcome,
                'exit_code': result.exit_code, 'stdout': result.stdout,
                'reviewer_received_submission_and_tests': True, 'denied_without_execution': denied,
                'slow_command_outcome': canceled.outcome, 'process_reaped': reaped,
                'live_test_evidence_stale_after_edit': current.stale,
                'captured_submission_unchanged': True, 'disposable_workspaces': True}


if __name__ == '__main__':
    print(json.dumps(demonstration(), indent=2))
