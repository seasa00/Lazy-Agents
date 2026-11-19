from dataclasses import replace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from app.dev.workspace import WorkspaceFixtureProvider, make_workspace_runner
from app.domain.commands import CommandProfile
from app.domain.projects import RunStatus
from app.persistence.sqlite import SQLiteStateStore
from app.permissions.policy import WorkspacePolicy
from app.providers.base import ProviderCapabilities, ProviderResponse, ProviderToolCall, UsageSnapshot
from app.orchestration.runner import WorkflowRunner
from app.tools.gateway import WorkspaceToolGateway
from app.orchestration.recovery import RecoveryCoordinator


class CommandLoopProvider(WorkspaceFixtureProvider):
    name = 'm71-command-fixture'
    capabilities = ProviderCapabilities(structured_outputs=True, tools=True, usage=True)

    def complete(self, request):
        if request.context['workflow']['phase'] != 'develop':
            return super().complete(request)
        wf = request.context['workflow']
        results = request.context.get('tool_results', [])
        if not results:
            call = ProviderToolCall('read_file', {'path': 'greeting.txt'})
            return ProviderResponse({}, request.model, 'read-request', (call,), UsageSnapshot(11, 2))
        result = results[-1]['result']
        if result.get('operation') == 'read':
            call = ProviderToolCall('edit_file', {'path': 'greeting.txt', 'old_text': 'hello',
                'new_text': 'hello world', 'expected_hash': result['content_hash']})
            return ProviderResponse({}, request.model, 'edit-request', (call,), UsageSnapshot(13, 3))
        if result.get('operation') == 'edit':
            call = ProviderToolCall('run_approved_command', {'profile': 'tests'})
            return ProviderResponse({}, request.model, 'command-request', (call,), UsageSnapshot(17, 4))
        output = {'submission_id': wf['submission_id'], 'task_id': request.context['current_task']['id'],
            'output_version': wf['output_version'], 'summary': 'Edited and tested greeting',
            'changed_files': [{'path': 'greeting.txt', 'change_type': 'modified', 'summary': 'Greeting updated'}],
            'tests': [{'name': 'approved-test', 'status': 'passed', 'summary': 'Approved test profile completed'}],
            'ready_for_review': True, 'notes': []}
        return ProviderResponse(output, request.model, 'developer-result', usage=UsageSnapshot(19, 5))


class DurableDeveloperCommandContinuationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix='m71-command-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'workspace'
        self.root.mkdir()
        (self.root / 'greeting.txt').write_text('hello\n')
        (self.root / 'test.py').write_text("from pathlib import Path\nassert Path('greeting.txt').read_text() == 'hello world\\n'\nprint('PASS')\n")
        self.profile = CommandProfile('tests', str(Path(sys.executable).resolve()), ('-I', '-B', 'test.py'), True)
        self.provider = CommandLoopProvider()
        self.runner = make_workspace_runner(self.root, provider=self.provider, command_profiles=(self.profile,))

    def wait_for_approval(self):
        self.assertEqual(self.runner.run.phase, 'develop')
        self.runner.step()
        run = self.runner.run
        self.assertEqual(run.status, RunStatus.WAITING_FOR_USER)
        self.assertEqual(len(run.workflow.tool_continuations), 1)
        continuation = run.workflow.tool_continuations[-1]
        self.assertEqual(continuation.state, 'WAITING_FOR_APPROVAL')
        return continuation

    def test_approval_executes_test_once_and_resumes_developer(self):
        continuation = self.wait_for_approval()
        self.assertFalse(self.runner.workspace_gateway.command_results)
        self.assertFalse((self.root / 'executed').exists())
        self.assertEqual(self.runner.run.workflow.pending_permissions, (continuation.permission_id,))
        self.assertTrue(self.root.joinpath('greeting.txt').read_text() == 'hello world\n')
        public_continuation = self.runner.run.to_dict()['workflow']['tool_continuations'][-1]
        self.assertNotIn('context_json', public_continuation)
        self.assertNotIn('arguments_json', public_continuation)
        self.assertNotIn('result_json', public_continuation)
        self.runner.controls.resolve_command(continuation.permission_id, approved=True, reason='Approve exact test profile')
        self.runner.run_until_stopped()
        run = self.runner.run
        self.assertEqual(run.status, RunStatus.COMPLETED)
        self.assertEqual(len(run.workflow.command_results), 1)
        command = run.workflow.command_results[0]
        self.assertTrue(command.succeeded)
        self.assertEqual(command.stdout, 'PASS\n')
        continuation = run.workflow.tool_continuations[-1]
        self.assertEqual(continuation.state, 'COMPLETED')
        receipt = json.loads(continuation.result_json)
        self.assertTrue(receipt['test_evidence'][0]['passed'])
        self.assertEqual(receipt['test_evidence'][0]['command']['workspace_before'], command.workspace_before)
        self.assertEqual(len([c for c in run.workflow.call_records if c.invocation_id == continuation.invocation_id]), 4)

    def test_denial_returns_structured_tool_result_without_execution(self):
        continuation = self.wait_for_approval()
        self.runner.controls.resolve_command(continuation.permission_id, approved=False, reason='Do not run this test')
        self.runner.run_until_stopped()
        self.assertEqual(self.runner.run.status, RunStatus.COMPLETED)
        self.assertEqual(self.runner.run.workflow.command_results, ())
        self.assertEqual(len(self.runner.workspace_gateway.command_records), 2)  # request and decision only
        self.assertFalse((self.root / 'executed').exists())
        self.assertEqual(self.runner.run.workflow.tool_continuations[-1].state, 'COMPLETED')
        self.assertEqual(json.loads(self.runner.run.workflow.tool_continuations[-1].result_json)['outcome'], 'denied')

    def test_duplicate_approval_and_resume_do_not_repeat_command(self):
        continuation = self.wait_for_approval()
        self.runner.controls.resolve_command(continuation.permission_id, approved=True, reason='Approve exact test profile')
        self.runner.controls.resolve_command(continuation.permission_id, approved=True, reason='Duplicate approval retry')
        self.runner.step()  # command operation
        command_id = self.runner.run.workflow.command_results[0].id
        self.runner.step()  # Developer resumes and finishes.
        self.assertEqual(self.runner.run.workflow.command_results[0].id, command_id)
        self.assertEqual(len(self.runner.run.workflow.command_results), 1)

    def test_pause_after_approval_defers_execution_until_resume(self):
        continuation = self.wait_for_approval()
        self.runner.controls.resolve_command(continuation.permission_id, approved=True, reason='Approve exact test profile')
        self.runner.controls.pause()
        self.assertFalse(self.runner.step())
        self.assertEqual(self.runner.run.status, RunStatus.PAUSED)
        self.assertEqual(self.runner.run.workflow.tool_continuations[-1].state, 'APPROVED_PENDING_EXECUTION')
        self.assertEqual(self.runner.run.workflow.command_results, ())
        self.runner.controls.resume()
        self.runner.run_until_stopped()
        self.assertEqual(self.runner.run.status, RunStatus.COMPLETED)
        self.assertEqual(len(self.runner.run.workflow.command_results), 1)

    def test_cancel_while_waiting_makes_late_approval_inert(self):
        continuation = self.wait_for_approval()
        self.runner.controls.cancel()
        with self.assertRaises(ValueError):
            self.runner.controls.resolve_command(continuation.permission_id, approved=True, reason='Late approval')
        self.assertEqual(self.runner.run.status, RunStatus.CANCELED)
        self.assertEqual(self.runner.run.workflow.command_results, ())

    def test_stale_generation_invalidates_waiting_command(self):
        continuation = self.wait_for_approval()
        self.runner.controls.change_scope()
        with self.assertRaises(ValueError):
            self.runner.controls.resolve_command(continuation.permission_id, approved=True, reason='Stale approval')
        self.assertEqual(self.runner.run.execution_generation, continuation.generation + 1)
        self.assertEqual(self.runner.run.workflow.tool_continuations[-1].state, 'STALE')
        self.assertEqual(self.runner.run.workflow.command_results, ())

    def test_sqlite_restart_preserves_waiting_continuation(self):
        db = self.root.parent / 'state.db'
        store = SQLiteStateStore(db)
        self.addCleanup(lambda: store.close() if store.connection else None)
        # Recreate the workflow in SQLite so the continuation crosses a real codec/reopen boundary.
        from app.dev.workspace import make_workspace_runner
        sqlite_runner = make_workspace_runner(self.root, provider=self.provider, store=store,
                                               command_profiles=(self.profile,))
        sqlite_runner.step()
        sqlite_runner.step()
        cont = sqlite_runner.run.workflow.tool_continuations[-1]
        store.close()
        store = SQLiteStateStore(db)
        recovery_provider = CommandLoopProvider()
        gateway = WorkspaceToolGateway(WorkspacePolicy(self.root), command_profiles=(self.profile,))
        reopened = WorkflowRunner(store, sqlite_runner.project_id, sqlite_runner.run_id,
                                  recovery_provider, gateway=gateway)
        self.assertEqual(reopened.run.workflow.tool_continuations[-1].id, cont.id)
        self.assertEqual(reopened.run.workflow.tool_continuations[-1].state, 'WAITING_FOR_APPROVAL')
        reopened.controls.resolve_command(cont.permission_id, approved=True, reason='Approve after restart')
        # Startup recovery requires an explicit resume before work is admitted.
        reopened.controls.resume()
        reopened.run_until_stopped()
        self.assertEqual(reopened.run.status, RunStatus.COMPLETED)
        self.assertEqual(len(reopened.run.workflow.command_results), 1)

    def test_restart_after_approval_before_command_start_resumes_once(self):
        db = self.root.parent / 'approved-before-start.db'
        store = SQLiteStateStore(db)
        from app.dev.workspace import make_workspace_runner
        old = make_workspace_runner(self.root, provider=self.provider, store=store,
                                    command_profiles=(self.profile,))
        old.step()
        continuation = old.run.workflow.tool_continuations[-1]
        old.controls.resolve_command(continuation.permission_id, approved=True, reason='Approve exact test profile')
        store.close()
        store = SQLiteStateStore(db)
        gateway = WorkspaceToolGateway(WorkspacePolicy(self.root), command_profiles=(self.profile,))
        reopened = WorkflowRunner(store, old.project_id, old.run_id, CommandLoopProvider(), gateway=gateway)
        self.assertEqual(reopened.run.workflow.tool_continuations[-1].state, 'APPROVED_PENDING_EXECUTION')
        reopened.controls.resume()
        reopened.run_until_stopped()
        self.assertEqual(reopened.run.status, RunStatus.COMPLETED)
        self.assertEqual(len(reopened.run.workflow.command_results), 1)

    def test_restart_between_permission_persist_and_continuation_commit(self):
        class Crash(BaseException):
            pass
        db = self.root.parent / 'approval-commit-gap.db'
        store = SQLiteStateStore(db)
        from app.dev.workspace import make_workspace_runner
        old = make_workspace_runner(self.root, provider=self.provider, store=store,
                                    command_profiles=(self.profile,))
        original_request = old.workspace_gateway.request_command
        def crash_after_permission_persist(request):
            original_request(request)  # audit + intervention commit independently
            raise Crash()
        old.workspace_gateway.request_command = crash_after_permission_persist
        with self.assertRaises(Crash):
            old.step()
        self.assertEqual(len(old.run.workflow.tool_continuations), 1)
        self.assertEqual(old.run.workflow.tool_continuations[-1].state, 'REQUESTING_APPROVAL')
        store.close()
        store = SQLiteStateStore(db)
        reopened = WorkflowRunner(store, old.project_id, old.run_id, CommandLoopProvider(),
            gateway=WorkspaceToolGateway(WorkspacePolicy(self.root), command_profiles=(self.profile,)))
        continuation = reopened.run.workflow.tool_continuations[-1]
        self.assertEqual(continuation.state, 'WAITING_FOR_APPROVAL')
        self.assertEqual(continuation.provider_request_id, 'command-request')
        self.assertEqual(reopened.run.workflow.pending_permissions, (continuation.permission_id,))
        self.assertEqual(reopened.run.status, RunStatus.WAITING_FOR_USER)
        self.assertEqual(reopened.run.workflow.command_results, ())
        reopened.controls.resolve_command(continuation.permission_id, approved=True,
                                          reason='Approve exact test profile after recovery')
        reopened.controls.resume()
        reopened.run_until_stopped()
        self.assertEqual(reopened.run.status, RunStatus.COMPLETED)
        self.assertEqual(len(reopened.run.workflow.command_results), 1)

    def test_uncertain_command_start_is_reconciled_and_never_replayed(self):
        class Crash(BaseException):
            pass
        db = self.root.parent / 'uncertain-command.db'
        store = SQLiteStateStore(db)
        from app.dev.workspace import make_workspace_runner
        old = make_workspace_runner(self.root, provider=self.provider, store=store,
                                    command_profiles=(self.profile,))
        old.step()
        continuation = old.run.workflow.tool_continuations[-1]
        old.controls.resolve_command(continuation.permission_id, approved=True, reason='Approve exact test profile')
        from unittest.mock import patch
        with patch('app.tools.gateway.launch', side_effect=Crash()):
            with self.assertRaises(Crash):
                old.step()
        store.close()
        store = SQLiteStateStore(db)
        gateway = WorkspaceToolGateway(WorkspacePolicy(self.root), command_profiles=(self.profile,))
        reopened = WorkflowRunner(store, old.project_id, old.run_id, CommandLoopProvider(), gateway=gateway)
        issue = reopened.run.workflow.recovery.unresolved[0]
        self.assertEqual(issue.kind, 'command')
        coordinator = RecoveryCoordinator(store)
        coordinator.resolve(reopened.project_id, reopened.run_id, issue.id,
            action='acknowledge-command', reason='Inspect fixture process state', runner=reopened, quiescent=True)
        reopened.controls.resume()
        with patch('app.tools.gateway.launch', side_effect=AssertionError('uncertain command replayed')):
            reopened.step()
        self.assertEqual(reopened.run.workflow.command_results, ())
        self.assertEqual(reopened.run.workflow.tool_continuations[-1].state, 'FAILED')

    def test_crash_after_approval_consumption_before_start_fence_resumes_same_operation(self):
        class Crash(BaseException):
            pass
        db = self.root.parent / 'prepared-command.db'
        store = SQLiteStateStore(db)
        from app.dev.workspace import make_workspace_runner
        old = make_workspace_runner(self.root, provider=self.provider, store=store,
                                    command_profiles=(self.profile,))
        old.step()
        continuation = old.run.workflow.tool_continuations[-1]
        old.controls.resolve_command(continuation.permission_id, approved=True, reason='Approve exact test profile')
        original = old.workspace_gateway.audit_sink
        def crash_after_approval_consumption(record, approval=None):
            saved = original(record, approval)
            if getattr(record, 'action', '') == 'intent':
                raise Crash()
            return saved
        old.workspace_gateway.audit_sink = crash_after_approval_consumption
        with self.assertRaises(Crash):
            old.step()
        self.assertEqual(next(o for o in store.operations(old.project_id, old.run_id)
                              if o.id == continuation.operation_id).stage.value, 'prepared')
        store.close()
        store = SQLiteStateStore(db)
        reopened = WorkflowRunner(store, old.project_id, old.run_id, CommandLoopProvider(),
            gateway=WorkspaceToolGateway(WorkspacePolicy(self.root), command_profiles=(self.profile,)))
        self.assertFalse(reopened.run.workflow.recovery.unresolved)
        reopened.controls.resume()
        reopened.run_until_stopped()
        self.assertEqual(reopened.run.status, RunStatus.COMPLETED)
        self.assertEqual(len(reopened.run.workflow.command_results), 1)
        operation = next(o for o in store.operations(old.project_id, old.run_id)
                         if o.id == continuation.operation_id)
        self.assertEqual(operation.stage.value, 'settled')


if __name__ == '__main__':
    unittest.main()
