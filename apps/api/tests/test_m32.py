"""Approved command lifecycle using harmless code in disposable workspaces only."""
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import time
import unittest
from unittest.mock import patch
from app.dev.workspace import make_workspace_runner, request as file_request
from app.domain.agents import AgentKind
from app.domain.commands import CommandRequest, CommandProfile, CommandLimits
from app.domain.projects import RunStatus
from app.tools.gateway import FileToolRequest


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix='m32-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'greeting.txt').write_text('hello\n')
        self.executable = str(Path(sys.executable).resolve())

    def runner(self, script="print('pass')", *, args=(), is_test=True, limits=None):
        (self.root / 'test.py').write_text(script)
        profile = CommandProfile('tests', self.executable, ('-I', '-B', 'test.py', *args), is_test)
        return make_workspace_runner(self.root, command_profiles=(profile,), command_limits=limits)

    def req(self, runner, **kw):
        attempt = runner.run.workflow.attempts[-1]
        profile = runner.workspace_gateway._profiles['tests']
        return CommandRequest(kw.pop('actor', AgentKind.DEVELOPER), attempt.id, attempt.generation,
            profile.name, profile.executable, profile.args, runner.workspace_gateway.workspace_version(), **kw)

    def approve(self, runner, req):
        approval = runner.request_command(req)
        runner.controls.resolve_command(approval.id, approved=True, reason='Approve exact disposable fixture command')
        return approval.id

    def run_command(self, runner, **kw):
        req = self.req(runner, **kw)
        return runner.command_tool(req, self.approve(runner, req))

    def edit(self, runner, content='hello world\n'):
        old = runner.file_tool(file_request(runner, 'read', path='greeting.txt'))
        runner.file_tool(file_request(runner, 'write', path='greeting.txt', expected_hash=old.content_hash, content=content))

    def wait_active(self, runner):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if runner.workspace_gateway.command_active:
                return
            time.sleep(0.005)
        self.fail('command did not launch')

    def background(self, runner, req, approval):
        results, errors = [], []
        def call():
            try:
                results.append(runner.command_tool(req, approval))
            except Exception as exc:
                errors.append(exc)
        thread = Thread(target=call)
        thread.start()
        self.wait_active(runner)
        def cleanup():
            if thread.is_alive():
                runner.controls.cancel()
            thread.join(4)
        self.addCleanup(cleanup)
        return thread, results, errors

    def test_unapproved_command_denied(self):
        runner = self.runner("open('executed', 'w').write('bad')")
        with self.assertRaises(ValueError):
            runner.command_tool(self.req(runner), 'unapproved')
        self.assertFalse((self.root / 'executed').exists())
        self.assertEqual(runner.workspace_gateway.command_records[-1].outcome, 'denied')

    def test_pending_approval_does_not_launch_or_advance_workflow(self):
        runner = self.runner()
        req = self.req(runner)
        approval = runner.request_command(req)
        self.assertFalse(runner.step())
        self.assertIn(approval.id, runner.run.workflow.pending_permissions)
        with self.assertRaises(ValueError):
            runner.command_tool(req, approval.id)

    def test_explicit_denial_recorded_and_no_execution(self):
        runner = self.runner("open('executed', 'w').write('bad')")
        req = self.req(runner)
        approval = runner.request_command(req)
        runner.controls.resolve_command(approval.id, approved=False, reason='Fixture denial')
        with self.assertRaises(ValueError):
            runner.command_tool(req, approval.id)
        self.assertFalse((self.root / 'executed').exists())
        self.assertTrue(any(r.action == 'decision' and r.outcome == 'denied' for r in runner.workspace_gateway.command_records))

    def test_exact_approval_scope_mismatch(self):
        runner = self.runner()
        (self.root / 'subdir').mkdir()
        req = self.req(runner)
        approval = self.approve(runner, req)
        for changes in ({'timeout_seconds': 9}, {'max_output_bytes': 123}, {'cwd': 'subdir'},
                        {'environment': (('TZ', 'Asia/Bangkok'),)}, {'args': ('-c', 'print(1)')},
                        {'profile': 'other'}, {'generation': 2}, {'attempt_id': 'other'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                runner.command_tool(replace(req, **changes), approval)
        self.assertTrue(runner.command_tool(req, approval).succeeded)

    def test_approval_is_single_use(self):
        runner = self.runner()
        req = self.req(runner)
        approval = self.approve(runner, req)
        runner.command_tool(req, approval)
        with self.assertRaises(ValueError):
            runner.command_tool(req, approval)

    def test_no_shell_expansion_or_injection(self):
        args = ('$(touch injected)', '; touch injected', '`touch injected`', '*', '$HOME', '~', '| cat', 'a b')
        runner = self.runner('import sys, json; print(json.dumps(sys.argv[1:]))', args=args)
        result = self.run_command(runner)
        self.assertTrue(result.succeeded)
        self.assertEqual(tuple(json.loads(result.stdout)), args)
        self.assertFalse((self.root / 'injected').exists())

    def test_shell_profile_denied(self):
        executable = str(Path('/bin/sh').resolve())
        profile = CommandProfile('shell', executable, ('-c', 'true'))
        runner = make_workspace_runner(self.root, command_profiles=(profile,))
        attempt = runner.run.workflow.attempts[-1]
        req = CommandRequest(AgentKind.DEVELOPER, attempt.id, attempt.generation, profile.name,
                             executable, profile.args, runner.workspace_gateway.workspace_version())
        with self.assertRaises(ValueError):
            runner.request_command(req)

    def test_working_directory_escape_denied(self):
        runner = self.runner()
        for cwd in ('..', '/tmp', 'a/../../outside', './', 'a//b'):
            with self.subTest(cwd=cwd), self.assertRaises(ValueError):
                runner.request_command(self.req(runner, cwd=cwd))

    def test_working_directory_symlink_denied(self):
        runner = self.runner()
        req = self.req(runner, cwd='link')
        (self.root / 'link').symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            runner.request_command(req)

    def test_nested_scoped_working_directory(self):
        runner = self.runner('import os; print(os.getcwd())')
        (self.root / 'subdir').mkdir()
        (self.root / 'subdir' / 'test.py').write_text('import os; print(os.getcwd())')
        result = self.run_command(runner, cwd='subdir')
        self.assertTrue(result.succeeded)
        self.assertEqual(result.stdout.strip(), str(self.root / 'subdir'))

    def test_restricted_environment_does_not_inherit_credentials(self):
        runner = self.runner('import os, json; print(json.dumps(dict(os.environ)))')
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'secret', 'AWS_SECRET_ACCESS_KEY': 'secret',
                                    'PYTHONPATH': '/bad', 'BASH_ENV': '/bad', 'LD_PRELOAD': '/bad'}):
            result = self.run_command(runner)
        env = json.loads(result.stdout)
        for key in ('OPENROUTER_API_KEY', 'AWS_SECRET_ACCESS_KEY', 'PYTHONPATH', 'BASH_ENV', 'LD_PRELOAD', 'HOME'):
            self.assertNotIn(key, env)
        self.assertEqual(env['PATH'], '/usr/bin:/bin')

    def test_environment_overrides_restricted(self):
        runner = self.runner()
        for env in ((('PATH', '/bad'),), (('PYTHONPATH', '/bad'),), (('LANG', 'C'), ('LANG', 'C')), (('TZ', '\x00'),)):
            with self.assertRaises(ValueError):
                runner.request_command(self.req(runner, environment=env))

    def test_timeout_never_success(self):
        runner = self.runner('import time; time.sleep(30)')
        result = self.run_command(runner, timeout_seconds=0.1)
        self.assertEqual(result.outcome, 'timed_out')
        self.assertFalse(result.succeeded)
        self.assertIsNotNone(result.exit_code)
        self.assertTrue(result.cleanup_complete)
        with self.assertRaises(ProcessLookupError):
            os.kill(result.pid, 0)

    def test_bounded_stdout_and_stderr_are_drained(self):
        runner = self.runner("import os\nfor _ in range(100):\n os.write(1, b'x' * 8192)\n os.write(2, b'y' * 8192)\n")
        result = self.run_command(runner, max_output_bytes=256)
        self.assertTrue(result.succeeded)
        self.assertEqual(result.stdout, 'x' * 256)
        self.assertEqual(result.stderr, 'y' * 256)
        self.assertTrue(result.stdout_truncated and result.stderr_truncated)

    def test_output_flood_cannot_evade_timeout(self):
        runner = self.runner("import os\nwhile True: os.write(1, b'x' * 65536)")
        result = self.run_command(runner, timeout_seconds=0.1, max_output_bytes=64)
        self.assertEqual(result.outcome, 'timed_out')
        self.assertLessEqual(len(result.stdout.encode()), 64)

    def test_cancellation_cleanup_and_usage_record(self):
        runner = self.runner('import time; time.sleep(30)')
        req = self.req(runner)
        thread, results, errors = self.background(runner, req, self.approve(runner, req))
        runner.controls.cancel()
        thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        result = results[0]
        self.assertEqual(result.outcome, 'canceled')
        self.assertFalse(result.succeeded)
        self.assertTrue(result.cleanup_complete)
        self.assertEqual(runner.run.workflow.command_results, (result,))
        self.assertIsNone(runner.run.workflow.pending)
        with self.assertRaises(ProcessLookupError):
            os.kill(result.pid, 0)

    def test_descendant_process_cleanup(self):
        runner = self.runner("import subprocess, sys, time\np = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\nprint(p.pid, flush=True)\ntime.sleep(30)\n")
        result = self.run_command(runner, timeout_seconds=0.3)
        child = int(result.stdout.strip())
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                break
            time.sleep(0.01)
        else:
            self.fail('descendant still exists after group cleanup')
        self.assertEqual(result.outcome, 'timed_out')

    def test_leader_exit_with_running_child_is_not_success(self):
        runner = self.runner("import subprocess, sys\np = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\nprint(p.pid, flush=True)")
        result = self.run_command(runner)
        self.assertEqual(result.outcome, 'terminated')
        self.assertFalse(result.succeeded)
        self.assertLess(result.duration_seconds, 3)

    def test_pause_before_launch(self):
        runner = self.runner("open('executed', 'w').write('bad')")
        req = self.req(runner)
        approval = self.approve(runner, req)
        runner.controls.pause()
        with self.assertRaises(ValueError):
            runner.command_tool(req, approval)
        self.assertFalse((self.root / 'executed').exists())

    def test_pause_during_command_stops_and_can_resume(self):
        runner = self.runner('import time; time.sleep(30)')
        req = self.req(runner)
        thread, results, errors = self.background(runner, req, self.approve(runner, req))
        runner.controls.pause()
        thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        self.assertEqual(results[0].outcome, 'paused')
        self.assertEqual(runner.run.status, RunStatus.PAUSED)
        runner.controls.resume()
        self.assertEqual(runner.run.status, RunStatus.RUNNING)

    def test_one_command_at_a_time_and_no_file_mutation(self):
        runner = self.runner('import time; time.sleep(30)')
        req = self.req(runner)
        approval = self.approve(runner, req)
        another = self.approve(runner, req)
        thread, results, errors = self.background(runner, req, approval)
        with self.assertRaises(ValueError):
            runner.command_tool(req, another)
        with self.assertRaises(ValueError):
            self.edit(runner)
        self.assertFalse(runner.step())
        runner.controls.cancel()
        thread.join(4)
        self.assertFalse(errors)

    def test_failed_test_captures_exit_status_and_stderr(self):
        runner = self.runner("import sys; print('assertion failed', file=sys.stderr); sys.exit(7)")
        result = self.run_command(runner)
        self.assertEqual(result.outcome, 'failed')
        self.assertEqual(result.exit_code, 7)
        self.assertEqual(result.stderr, 'assertion failed\n')
        self.assertFalse(result.succeeded)
        test = runner.workspace_gateway.test_evidence(result.request.attempt_id, result.request.generation)[0]
        self.assertFalse(test.stale)
        self.assertFalse(test.passed)

    def test_test_evidence_stale_after_gateway_mutation(self):
        runner = self.runner()
        result = self.run_command(runner)
        self.edit(runner)
        test = runner.workspace_gateway.test_evidence(result.request.attempt_id, result.request.generation)[0]
        self.assertTrue(test.stale)
        self.assertFalse(test.passed)

    def test_external_and_unchanged_file_changes_make_evidence_stale(self):
        runner = self.runner()
        result = self.run_command(runner)
        (self.root / 'test.py').write_text("print('changed tests')")
        test = runner.workspace_gateway.test_evidence(result.request.attempt_id, result.request.generation)[0]
        self.assertTrue(test.stale)

    def test_test_that_changes_workspace_is_stale(self):
        runner = self.runner("open('generated', 'w').write('changed')")
        result = self.run_command(runner)
        self.assertTrue(result.succeeded)
        self.assertNotEqual(result.workspace_before, result.workspace_after)
        self.assertTrue(runner.workspace_gateway.test_evidence(result.request.attempt_id, result.request.generation)[0].stale)

    def test_stale_approval_after_file_change_denied(self):
        runner = self.runner()
        req = self.req(runner)
        approval = self.approve(runner, req)
        self.edit(runner)
        with self.assertRaises(ValueError):
            runner.command_tool(req, approval)
        with self.assertRaises(ValueError):
            runner.command_tool(self.req(runner), approval)

    def test_reviewer_and_manager_cannot_execute_or_request(self):
        runner = self.runner()
        req = self.req(runner)
        approval = self.approve(runner, req)
        for role in (AgentKind.REVIEWER, AgentKind.MANAGER):
            with self.subTest(role=role):
                other = replace(req, actor=role)
                with self.assertRaises(ValueError):
                    runner.request_command(other)
                with self.assertRaises(ValueError):
                    runner.command_tool(other, approval)

    def test_command_limits_persist_after_pause_resume(self):
        runner = self.runner(limits=CommandLimits(max_commands=1))
        self.run_command(runner)
        runner.controls.pause()
        runner.controls.resume()
        req = self.req(runner)
        approval = self.approve(runner, req)
        with self.assertRaises(ValueError):
            runner.command_tool(req, approval)

    def test_request_and_execution_bounds(self):
        runner = self.runner(limits=CommandLimits(max_requests=2))
        for kwargs in ({'timeout_seconds': 31}, {'max_output_bytes': 65537}, {}):
            with self.assertRaises(ValueError):
                runner.request_command(self.req(runner, **kwargs))

    def test_fingerprint_bounded_and_no_symlink_following(self):
        runner = self.runner(limits=CommandLimits(max_workspace_bytes=128))
        (self.root / 'large').write_bytes(b'x' * 129)
        with self.assertRaises(ValueError):
            runner.workspace_gateway.workspace_version()

    def test_mutable_or_unbounded_requests_rejected(self):
        runner = self.runner()
        req = self.req(runner)
        for fields in ({'args': ['bad']}, {'environment': [('TZ', 'UTC')]}, {'timeout_seconds': float('inf')},
                       {'timeout_seconds': float('nan')}, {'max_output_bytes': -1}, {'args': ('x' * 16385,)}):
            with self.assertRaises(ValueError):
                replace(req, **fields)

    def test_fresh_test_and_submission_review_use_captured_evidence(self):
        runner = self.runner("from pathlib import Path\nassert Path('greeting.txt').read_text() == 'hello world\\n'\nprint('greeting PASS')")
        self.edit(runner)
        result = self.run_command(runner)
        runner.step()
        sub = runner.run.workflow.submissions[0]
        self.assertEqual(sub.files.tests[0].result, result)
        self.assertTrue(sub.files.tests[0].passed)
        digest = sub.digest
        (self.root / 'greeting.txt').write_text('later live version')
        runner.run_until_stopped()
        self.assertEqual(runner.run.status, RunStatus.COMPLETED)
        self.assertEqual(runner.run.workflow.submissions[0].digest, digest)
        review = next(q for q in runner.provider.requests if q.context['workflow']['phase'] == 'review')
        captured = json.loads(review.context['workflow']['evidence'][0])
        self.assertTrue(captured['tests'][0]['passed'])
        self.assertEqual(captured['tests'][0]['command']['stdout'], 'greeting PASS\n')

    def test_stale_test_cannot_establish_reviewer_pass(self):
        runner = self.runner()
        self.run_command(runner)
        self.edit(runner)
        runner.step()
        self.assertTrue(runner.run.workflow.submissions[0].files.tests[0].stale)
        runner.step()
        self.assertEqual(runner.run.status, RunStatus.WAITING_FOR_USER)
        self.assertIn('stale captured tests', runner.run.workflow.blocked_reason)

    def test_failed_test_cannot_establish_reviewer_pass(self):
        runner = self.runner('raise SystemExit(1)')
        self.edit(runner)
        self.run_command(runner)
        runner.step()
        runner.step()
        self.assertEqual(runner.run.status, RunStatus.WAITING_FOR_USER)

    def test_retest_supersedes_stale_result_for_same_profile(self):
        runner = self.runner()
        self.run_command(runner)
        self.edit(runner)
        self.run_command(runner)
        runner.run_until_stopped()
        self.assertEqual(runner.run.status, RunStatus.COMPLETED)
        tests = runner.run.workflow.submissions[0].files.tests
        self.assertTrue(tests[0].stale)
        self.assertTrue(tests[1].passed)

    def test_general_command_is_not_test_evidence(self):
        runner = self.runner(is_test=False)
        result = self.run_command(runner)
        self.assertFalse(result.is_test)
        self.assertFalse(runner.workspace_gateway.test_evidence(result.request.attempt_id, result.request.generation))

    def test_launch_error_consumes_approval_and_records_failure(self):
        runner = self.runner()
        req = self.req(runner)
        approval = self.approve(runner, req)
        with patch('app.tools.commands.subprocess.Popen', side_effect=OSError('fixture launch failure')):
            result = runner.command_tool(req, approval)
        self.assertEqual(result.outcome, 'error')
        self.assertIsNone(result.exit_code)
        self.assertFalse(result.succeeded)
        self.assertIsNone(runner.run.workflow.pending)

    def test_workspace_and_command_history_are_json_serializable(self):
        runner = self.runner()
        self.edit(runner)
        self.run_command(runner)
        runner.run_until_stopped()
        state = json.loads(json.dumps(runner.run.to_dict()))
        self.assertEqual(state['workflow']['command_results'][0]['outcome'], 'succeeded')
        self.assertTrue(state['workflow']['submissions'][0]['files']['tests'])

    def test_protected_file_change_invalidates_tests_without_exposing_secret(self):
        runner = self.runner()
        (self.root / '.env').write_text('SECRET=before')
        result = self.run_command(runner)
        (self.root / '.env').write_text('SECRET=after')
        tests = runner.workspace_gateway.test_evidence(result.request.attempt_id, result.request.generation)
        self.assertTrue(tests[0].stale)
        self.assertNotIn('SECRET=', json.dumps(tests[0].to_dict()))

    def test_restored_bytes_still_invalidate_prior_version(self):
        runner = self.runner()
        result = self.run_command(runner)
        self.edit(runner)
        self.edit(runner, content='hello\n')
        self.assertTrue(runner.workspace_gateway.test_evidence(result.request.attempt_id, result.request.generation)[0].stale)

    def test_executable_change_invalidates_approval(self):
        runner = self.runner()
        req = self.req(runner)
        approval = self.approve(runner, req)
        with patch('app.tools.gateway.executable_digest', return_value='different executable hash'):
            with self.assertRaises(ValueError):
                runner.command_tool(req, approval)

    def test_profile_reclassification_requires_new_approval(self):
        runner = self.runner(is_test=False)
        req = self.req(runner)
        approval = self.approve(runner, req)
        runner.workspace_gateway._profiles['tests'] = replace(runner.workspace_gateway._profiles['tests'], is_test=True)
        with self.assertRaises(ValueError):
            runner.command_tool(req, approval)

    def test_scope_change_invalidates_pending_and_approved_commands(self):
        runner = self.runner()
        req = self.req(runner)
        approval = self.approve(runner, req)
        pending = runner.request_command(req)
        runner.controls.change_scope()
        self.assertFalse(runner.run.workflow.pending_permissions)
        self.assertTrue(all(a.status == 'invalidated' for a in runner.workspace_gateway.approvals))
        runner.controls.resume()
        with self.assertRaises(ValueError):
            runner.command_tool(req, approval)

    def test_scope_change_during_command_cancels_and_retains_result(self):
        runner = self.runner('import time; time.sleep(30)')
        req = self.req(runner)
        thread, results, errors = self.background(runner, req, self.approve(runner, req))
        runner.controls.change_scope()
        thread.join(4)
        self.assertFalse(errors)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results[0].outcome, 'canceled')
        self.assertEqual(runner.run.status, RunStatus.PAUSED)

    def test_invalid_utf8_output_remains_byte_bounded(self):
        runner = self.runner("import os; os.write(1, b'\\xff' * 20)")
        result = self.run_command(runner, max_output_bytes=10)
        self.assertTrue(result.succeeded)
        self.assertLessEqual(len(result.stdout.encode()), 10)
        self.assertTrue(result.stdout_truncated)

    def test_final_prelaunch_guard_denies_without_consuming_approval(self):
        runner = self.runner()
        req = self.req(runner)
        approval = self.approve(runner, req)
        original = runner.workspace_gateway.before_mutation
        checks = 0
        def guard(request):
            nonlocal checks
            checks += 1
            if checks == 2:
                raise ValueError('stopped at launch boundary')
            original(request)
        runner.workspace_gateway.before_mutation = guard
        with patch('app.tools.commands.subprocess.Popen') as popen:
            with self.assertRaisesRegex(ValueError, 'launch boundary'):
                runner.command_tool(req, approval)
            popen.assert_not_called()
        self.assertEqual(runner.workspace_gateway.approvals[0].status, 'approved')

    def test_manual_verification_fixture(self):
        from app.dev.commands import demonstration
        result = demonstration()
        self.assertEqual(result['workflow_status'], 'completed')
        self.assertEqual(result['slow_command_outcome'], 'canceled')
        self.assertTrue(result['process_reaped'])
        self.assertTrue(result['live_test_evidence_stale_after_edit'])

    def test_incomplete_cleanup_blocks_new_commands_and_resume(self):
        # The fixture leader exits normally; simulate a failed cleanup confirmation
        # without leaving an actual subprocess alive.
        runner = self.runner()
        with patch('app.tools.commands._kill_group', return_value=False):
            result = self.run_command(runner)
        self.assertEqual(result.outcome, 'cleanup_failed')
        self.assertFalse(result.succeeded)
        self.assertEqual(runner.run.status, RunStatus.WAITING_FOR_USER)
        self.assertIsNotNone(runner.run.workflow.pending)
        self.assertTrue(runner.workspace_gateway.command_active)
        with self.assertRaises(ValueError):
            runner.controls.resolve()
        with self.assertRaises(ValueError):
            runner.request_command(self.req(runner))
        with self.assertRaises(ProcessLookupError):
            os.kill(result.pid, 0)


if __name__ == '__main__':
    unittest.main()
