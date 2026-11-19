"""Deterministic interrupted-state recovery; every DB/workspace is disposable."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from unittest.mock import patch
import json
import sqlite3
import unittest

from app.domain.projects import RunStatus
from app.domain.events import DomainEvent
from app.domain.recovery import (ExecutionCheckpoint, ExecutionOperation, OutcomeCertainty, OperationStage)
from app.dev.workflow import make_runner, approve_generated, ScriptedWorkflowProvider
from app.dev.workspace import make_workspace_runner, request
from app.persistence.sqlite import SQLiteStateStore
from app.orchestration.recovery import RecoveryCoordinator, RecoveryError
from app.orchestration.runner import WorkflowRunner
from app.orchestration.limits import ExecutionLimits
from app.tools.gateway import WorkspaceToolGateway
from app.permissions.policy import WorkspacePolicy
from app.persistence.models import ArtifactIntegrityError


class Crash(BaseException):
    pass


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix='m42-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'state.db'
        self.store = SQLiteStateStore(self.path)
        self.addCleanup(lambda: self.store.close())

    def synthetic(self, provider=None, **kwargs):
        runner = make_runner(provider, store=self.store, **kwargs)
        approve_generated(runner)
        runner.step()
        return runner

    def workspace(self, **kwargs):
        root = self.root / 'workspace'
        root.mkdir()
        (root / 'greeting.txt').write_text('hello\n')
        return make_workspace_runner(root, store=self.store, **kwargs)

    def restart(self, old, *, gateway=False):
        self.store.close()
        self.store = SQLiteStateStore(self.path)
        recovery = RecoveryCoordinator(self.store)
        recovery.startup()
        provider = ScriptedWorkflowProvider()
        if gateway:
            from app.dev.workspace import WorkspaceFixtureProvider
            provider = WorkspaceFixtureProvider()
            gw = WorkspaceToolGateway(WorkspacePolicy(self.root / 'workspace'))
        else:
            gw = None
        runner = WorkflowRunner(self.store, old.project_id, old.run_id, provider, gateway=gw)
        self.assertFalse(runner.step())
        self.assertEqual(provider.requests, [])
        return runner, recovery

    def crash_provider(self, runner, *, after=False):
        if after:
            original = runner.store.record_operation
            def save(op):
                original(op)
                if op.kind == 'provider' and op.stage is OperationStage.SETTLED:
                    raise Crash()
            with patch.object(runner.store, 'record_operation', save):
                with self.assertRaises(Crash):
                    runner.step()
        else:
            def fail(_):
                raise Crash()
            runner.provider.hook = fail
            with self.assertRaises(Crash):
                runner.step()
            runner.provider.hook = None

    def crash_file(self, runner, *, mutated):
        before = runner.file_tool(request(runner, 'read', path='greeting.txt'))
        original = runner.workspace_gateway.operation_sink
        def save(op):
            if op.kind == 'file' and op.operation == 'write':
                if (mutated and op.stage is OperationStage.SETTLED) or (not mutated and op.stage is OperationStage.EXECUTING):
                    raise Crash()
            return original(op)
        with patch.object(runner.workspace_gateway, 'operation_sink', save):
            with self.assertRaises(Crash):
                runner.file_tool(request(runner, 'write', path='greeting.txt', expected_hash=before.content_hash, content='hello world\n'))
        return next(o for o in self.store.operations(runner.project_id,runner.run_id) if o.operation == 'write')

    def test_startup_and_runner_constructor_never_execute(self):
        runner = self.synthetic()
        self.store.close()
        self.store = SQLiteStateStore(self.path)
        provider = ScriptedWorkflowProvider()
        reopened = WorkflowRunner(self.store, runner.project_id, runner.run_id, provider)
        self.assertEqual(reopened.run.status, RunStatus.PAUSED)
        self.assertFalse(reopened.step())
        self.assertEqual(provider.requests, [])

    def test_safe_restart_requires_explicit_resume_same_attempt(self):
        runner = self.synthetic()
        attempt = runner.run.workflow.attempts[-1]
        new, recovery = self.restart(runner)
        recovery.resume(new.project_id,new.run_id)
        new.run_until_stopped()
        self.assertEqual(new.run.status, RunStatus.COMPLETED)
        self.assertEqual(new.run.workflow.attempts, (attempt,))

    def test_prepared_file_cannot_have_executed(self):
        runner = self.workspace()
        op = self.crash_file(runner,mutated=False)
        new, recovery = self.restart(runner,gateway=True)
        self.assertEqual((self.root/'workspace'/'greeting.txt').read_text(),'hello\n')
        self.assertFalse(new.run.workflow.recovery.unresolved)
        recovery.resume(new.project_id,new.run_id)
        self.assertEqual(next(o for o in self.store.operations(new.project_id,new.run_id) if o.id == op.id).certainty,
                         OutcomeCertainty.CONFIRMED_FAILURE)
        self.assertEqual((self.root/'workspace'/'greeting.txt').read_text(),'hello\n')

    def test_mutation_without_receipt_blocks_and_hash_proof_resolves(self):
        runner = self.workspace()
        op = self.crash_file(runner,mutated=True)
        new, recovery = self.restart(runner,gateway=True)
        self.assertEqual(new.run.status,RunStatus.WAITING_FOR_USER)
        with self.assertRaises(RecoveryError):
            recovery.resume(new.project_id,new.run_id)
        recovery.resolve(new.project_id,new.run_id,op.id,action='verify-file',reason='Inspect retained hash proof')
        recovery.resume(new.project_id,new.run_id)
        new.run_until_stopped()
        self.assertEqual(new.run.status,RunStatus.COMPLETED)
        self.assertEqual(len(new.run.workflow.attempts),1)
        self.assertEqual((self.root/'workspace'/'greeting.txt').read_text(),'hello world\n')

    def test_divergent_file_cannot_be_resolved_as_success_or_failure(self):
        runner=self.workspace()
        op=self.crash_file(runner,mutated=True)
        (self.root/'workspace'/'greeting.txt').write_text('external edit')
        new,recovery=self.restart(runner,gateway=True)
        with self.assertRaisesRegex(RecoveryError,'neither'):
            recovery.resolve(new.project_id,new.run_id,op.id,action='verify-file',reason='Inspect mismatch')
        self.assertTrue(new.run.workflow.recovery.unresolved)

    def test_confirmed_file_outcome_restores_change_capture_without_replay(self):
        runner=self.workspace()
        before=runner.file_tool(request(runner,'read',path='greeting.txt'))
        runner.file_tool(request(runner,'write',path='greeting.txt',expected_hash=before.content_hash,content='hello world\n'))
        new,recovery=self.restart(runner,gateway=True)
        recovery.resume(new.project_id,new.run_id)
        with patch.object(new.workspace_gateway._files,'write',side_effect=AssertionError('blind replay')):
            new.run_until_stopped()
        self.assertEqual(new.run.status,RunStatus.COMPLETED)

    def test_provider_inflight_unknown_usage_is_retained_without_resend(self):
        runner=self.synthetic()
        self.crash_provider(runner)
        old_calls=runner.run.workflow.llm_calls
        new,recovery=self.restart(runner)
        issue=new.run.workflow.recovery.unresolved[0]
        self.assertEqual(issue.certainty,OutcomeCertainty.UNCERTAIN)
        self.assertIsNone(self.store.usage(new.project_id)['total_tokens'])
        self.assertIsNone(self.store.usage(new.project_id)['estimated_cost'])
        self.assertEqual(new.run.workflow.llm_calls,old_calls)
        recovery.resolve(new.project_id,new.run_id,issue.id,action='abandon-provider',reason='Accept unknown charge; abandon application result')
        recovery.resume(new.project_id,new.run_id)
        new.run_until_stopped()
        self.assertEqual(new.run.status,RunStatus.COMPLETED)
        self.assertIsNone(self.store.usage(new.project_id)['total_tokens'])
        self.assertEqual(len(new.run.workflow.attempts),1)

    def test_durable_provider_success_can_be_admitted_without_new_call(self):
        runner=self.synthetic()
        self.crash_provider(runner,after=True)
        new,recovery=self.restart(runner)
        issue=new.run.workflow.recovery.unresolved[0]
        recovery.resolve(new.project_id,new.run_id,issue.id,action='accept-result',reason='Admit retained validated proposal',runner=new)
        self.assertEqual(new.run.phase,'review')
        self.assertEqual(new.provider.requests,[])
        recovery.resume(new.project_id,new.run_id)
        new.run_until_stopped()
        self.assertEqual(new.run.status,RunStatus.COMPLETED)
        self.assertEqual(len(new.run.workflow.submissions),1)

    def test_reviewer_interruption_keeps_submission_and_rounds(self):
        runner=self.synthetic()
        runner.step()
        sub=runner.run.workflow.submissions[0]
        self.crash_provider(runner)
        new,recovery=self.restart(runner)
        self.assertEqual(new.run.workflow.submissions[0],sub)
        issue=new.run.workflow.recovery.unresolved[0]
        recovery.resolve(new.project_id,new.run_id,issue.id,action='abandon-provider',reason='Unknown reviewer charge; retry same immutable submission')
        recovery.resume(new.project_id,new.run_id)
        new.run_until_stopped()
        self.assertEqual(len(new.run.workflow.submissions),1)
        self.assertEqual(new.run.workflow.reviews[0].submission_id,sub.id)

    def test_pause_limits_generation_instructions_survive(self):
        runner=self.synthetic(limits=ExecutionLimits(max_invocations=15,max_llm_calls=20))
        runner.controls.instruct('Preserve this queued instruction')
        runner.controls.pause()
        wf=runner.run.workflow
        generation=runner.run.execution_generation
        new,recovery=self.restart(runner)
        self.assertEqual(new.run.status,RunStatus.PAUSED)
        self.assertEqual(new.run.workflow.limits,wf.limits)
        for field in ('invocations','llm_calls','tasks_created','replans','iterations','pending_instructions'):
            self.assertEqual(getattr(new.run.workflow,field),getattr(wf,field))
        self.assertEqual(new.run.execution_generation,generation)
        new.controls.resume()
        self.assertEqual(new.run.status,RunStatus.RUNNING)

    def test_completed_task_not_reexecuted_after_restart(self):
        runner=make_runner(ScriptedWorkflowProvider(tasks=2),store=self.store)
        approve_generated(runner)
        while len(runner.run.workflow.accepted)<1:
            runner.step()
        completed=runner.run.workflow.accepted[0]
        new,recovery=self.restart(runner)
        recovery.resume(new.project_id,new.run_id)
        new.run_until_stopped()
        self.assertEqual(new.run.status,RunStatus.COMPLETED)
        self.assertEqual(new.run.workflow.accepted.count(completed),1)
        self.assertEqual(len(new.run.workflow.attempts),2)

    def test_reconciliation_is_idempotent_and_resolution_idempotent(self):
        runner=self.synthetic()
        self.crash_provider(runner)
        new,recovery=self.restart(runner)
        count=len(self.store.events(new.project_id))
        recovery.reconcile(new.project_id,new.run_id)
        self.assertEqual(len(self.store.events(new.project_id)),count)
        issue=new.run.workflow.recovery.unresolved[0]
        recovery.resolve(new.project_id,new.run_id,issue.id,action='abandon-provider',reason='Controlled operator decision')
        count=len(self.store.events(new.project_id))
        recovery.resolve(new.project_id,new.run_id,issue.id,action='abandon-provider',reason='Controlled operator decision')
        self.assertEqual(len(self.store.events(new.project_id)),count)

    def test_stale_recovery_epoch_and_generic_resolve_cannot_bypass_gate(self):
        runner=self.synthetic()
        new,recovery=self.restart(runner)
        with self.assertRaises(RecoveryError):
            recovery.resume(new.project_id,new.run_id,expected_epoch=999)
        self.assertFalse(new.step())
        self.crash_provider_after_resume(new,recovery)
        with self.assertRaises(ValueError):
            new.controls.resolve()

    def crash_provider_after_resume(self, runner, recovery):
        recovery.resume(runner.project_id,runner.run_id)
        self.crash_provider(runner)
        recovery.reconcile(runner.project_id,runner.run_id)

    def test_old_late_result_is_fenced_but_known_usage_retained(self):
        entered,release=Event(),Event()
        def wait(req):
            if req.context['workflow']['phase']=='develop':
                entered.set()
                if not release.wait(5):
                    raise RuntimeError('fixture timeout')
        runner=self.synthetic(ScriptedWorkflowProvider(hook=wait))
        errors=[]
        def execute():
            try: runner.step()
            except BaseException as exc: errors.append(exc)
        thread=Thread(target=execute)
        thread.start()
        self.assertTrue(entered.wait(2))
        try:
            recovery=RecoveryCoordinator(self.store)
            recovery.reconcile(runner.project_id,runner.run_id)
            issue=runner.run.workflow.recovery.unresolved[0]
            recovery.resolve(runner.project_id,runner.run_id,issue.id,action='abandon-provider',reason='Fence old in-flight result')
        finally:
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors,[])
        self.assertFalse(runner.run.workflow.submissions)
        self.assertEqual(runner.run.phase,'develop')
        self.assertEqual(self.store.usage(runner.project_id)['total_tokens'],45)
        self.assertTrue(any(e.type=='operation.stale_ignored' for e in self.store.events(runner.project_id)))

    def test_artifact_corruption_can_be_reported_without_loading_contents(self):
        runner=self.synthetic()
        runner.step()
        raw,=self.store.connection.execute('SELECT data FROM submissions LIMIT 1').fetchone()
        digest=json.loads(raw)['fields']['evidence']['$artifact']
        path=self.store.codec.root/digest
        saved=path.read_bytes()
        path.write_bytes(b'corrupt')
        self.store.close()
        self.store=SQLiteStateStore(self.path)
        recovery=RecoveryCoordinator(self.store)
        recovery.startup()
        info=recovery.inspect(runner.project_id,runner.run_id)
        self.assertEqual(info['status'],'waiting_for_user')
        self.assertTrue(any(i.kind=='artifact' for i in info['recovery'].unresolved))
        with self.assertRaises(RecoveryError):
            recovery.resume(runner.project_id,runner.run_id)
        path.write_bytes(saved)
        recovery.resolve(runner.project_id,runner.run_id,'artifact-integrity',action='verify-artifacts',reason='Restore exact hashed artifact bytes')
        recovery.resume(runner.project_id,runner.run_id)

    def test_checkpoint_and_operation_events_commit_atomically(self):
        runner=self.synthetic()
        cp=runner.run.workflow.checkpoint
        self.assertEqual(cp.phase,'develop')
        self.assertEqual(cp.attempt_id,runner.run.workflow.attempts[-1].id)
        op=ExecutionOperation('fixture','file',replace(cp,operation_id='fixture'))
        self.store.connection.execute("CREATE TRIGGER fail_recovery BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.record_operation(op)
        self.assertFalse(any(o.id=='fixture' for o in self.store.operations(runner.project_id,runner.run_id)))

    def test_terminal_cancel_never_resumes(self):
        runner=self.synthetic()
        runner.controls.cancel()
        self.store.close()
        self.store=SQLiteStateStore(self.path)
        recovery=RecoveryCoordinator(self.store)
        recovery.startup()
        self.assertEqual(self.store.get_project(runner.project_id).runs[0].status,RunStatus.CANCELED)
        with self.assertRaises(RecoveryError):
            recovery.resume(runner.project_id,runner.run_id)

class CommandRecoveryTests(unittest.TestCase):
    setUp=RecoveryTests.setUp
    restart=RecoveryTests.restart

    def command_fixture(self):
        from app.domain.commands import CommandProfile
        from app.dev.commands import command_request, approve_fixture
        import sys
        root=self.root/'workspace'
        root.mkdir()
        (root/'greeting.txt').write_text('hello\n')
        (root/'test.py').write_text("print('controlled completion')\n")
        profile=CommandProfile('test',str(Path(sys.executable).resolve()),('-I','-B','test.py'),True)
        runner=make_workspace_runner(root,store=self.store,command_profiles=(profile,))
        before=runner.file_tool(request(runner,'read',path='greeting.txt'))
        runner.file_tool(request(runner,'write',path='greeting.txt',expected_hash=before.content_hash,content='hello world\n'))
        req=command_request(runner,profile)
        approval=approve_fixture(runner,req)
        return runner,req,approval,profile

    def test_command_prepared_before_launch_is_safe_but_never_replayed(self):
        runner,req,approval,_=self.command_fixture()
        original=runner.workspace_gateway.operation_sink
        def interrupt(op):
            if op.kind=='command' and op.stage is OperationStage.EXECUTING:
                raise Crash()
            return original(op)
        with patch.object(runner.workspace_gateway,'operation_sink',interrupt), patch('app.tools.gateway.launch',side_effect=AssertionError('launch must not happen')):
            with self.assertRaises(Crash): runner.command_tool(req,approval)
        new,recovery=self.restart(runner,gateway=True)
        self.assertFalse(new.run.workflow.recovery.unresolved)
        self.assertEqual(new.workspace_gateway.approvals[0].status,'consumed')
        recovery.resume(new.project_id,new.run_id)
        self.assertEqual(new.workspace_gateway._command_launches,1)

    def test_uncertain_command_never_uses_pid_to_signal(self):
        runner,req,approval,_=self.command_fixture()
        running=[]
        original=runner.workspace_gateway.collect_command
        def interrupt(command,stop):
            running.append(command)
            raise Crash()
        with patch.object(runner.workspace_gateway,'collect_command',interrupt):
            with self.assertRaises(Crash): runner.command_tool(req,approval)
        # Reap only the actual Popen owned by this fixture. Recovery never sees or signals it.
        running[0].process.communicate(timeout=3)
        with patch('os.kill',side_effect=AssertionError('unsafe PID signaling')), patch('os.killpg',side_effect=AssertionError('unsafe group signaling')):
            new,recovery=self.restart(runner,gateway=True)
            issue=next(i for i in new.run.workflow.recovery.unresolved if i.kind=='command')
            self.assertEqual(issue.certainty,OutcomeCertainty.UNCERTAIN)
            with self.assertRaises(RecoveryError): recovery.resume(new.project_id,new.run_id)
            with self.assertRaises(RecoveryError):
                recovery.resolve(new.project_id,new.run_id,issue.id,action='acknowledge-command',reason='Cannot prove process quiescence')
            recovery.resolve(new.project_id,new.run_id,issue.id,action='acknowledge-command',reason='Owned fixture process reaped; inspected workspace',quiescent=True)
            recovery.resume(new.project_id,new.run_id)
        self.assertEqual(new.run.workflow.command_results,())
        self.assertEqual(new.workspace_gateway._command_launches,1)

    def test_confirmed_command_receipt_restores_results_and_test_evidence(self):
        runner,req,approval,_=self.command_fixture()
        original=runner.workspace_gateway.operation_sink
        def interrupt(op):
            saved=original(op)
            if op.kind=='command' and op.stage is OperationStage.SETTLED:
                raise Crash()
            return saved
        with patch.object(runner.workspace_gateway,'operation_sink',interrupt):
            with self.assertRaises(Crash): runner.command_tool(req,approval)
        new,recovery=self.restart(runner,gateway=True)
        self.assertEqual(len(new.run.workflow.command_results),1)
        self.assertTrue(new.run.workflow.command_results[0].succeeded)
        recovery.resume(new.project_id,new.run_id)
        with patch('app.tools.gateway.launch',side_effect=AssertionError('command replay')):
            new.run_until_stopped()
        self.assertEqual(new.run.status,RunStatus.COMPLETED)
        self.assertTrue(new.run.workflow.submissions[0].files.tests[0].passed)

    def test_pending_permission_and_request_limit_restore(self):
        from app.dev.commands import command_request
        runner,req,approval,profile=self.command_fixture()
        pending=runner.request_command(command_request(runner,profile))
        self.store.close()
        self.store=SQLiteStateStore(self.path)
        recovery=RecoveryCoordinator(self.store)
        recovery.startup()
        gw=WorkspaceToolGateway(WorkspacePolicy(self.root/'workspace'),command_profiles=(profile,))
        new=WorkflowRunner(self.store,runner.project_id,runner.run_id,ScriptedWorkflowProvider(),gateway=gw)
        self.assertEqual(new.run.workflow.pending_permissions,(pending.id,))
        self.assertEqual(gw._command_requests,2)
        recovery.resume(new.project_id,new.run_id)
        self.assertFalse(new.step())
        new.controls.resolve_command(pending.id,approved=False,reason='Retained human denial after restart')
        self.assertEqual(new.run.workflow.pending_permissions,())
        self.assertEqual(next(a for a in gw.approvals if a.id==pending.id).status,'denied')


class FurtherRecoveryTests(unittest.TestCase):
    setUp=RecoveryTests.setUp
    synthetic=RecoveryTests.synthetic
    workspace=RecoveryTests.workspace
    restart=RecoveryTests.restart
    crash_provider=RecoveryTests.crash_provider
    crash_file=RecoveryTests.crash_file

    def test_review_history_and_limit_survive_second_round_interruption(self):
        runner=self.synthetic(ScriptedWorkflowProvider(('FAIL','PASS')))
        while len(runner.run.workflow.submissions)<2: runner.step()
        prior=runner.run.workflow.reviews[0]
        self.crash_provider(runner)
        new,recovery=self.restart(runner)
        self.assertEqual(new.run.workflow.reviews,(prior,))
        issue=new.run.workflow.recovery.unresolved[0]
        recovery.resolve(new.project_id,new.run_id,issue.id,action='abandon-provider',reason='Retry only the interrupted second review')
        recovery.resume(new.project_id,new.run_id)
        new.run_until_stopped()
        self.assertEqual(len(new.run.workflow.reviews),2)
        self.assertEqual(new.run.workflow.reviews[0],prior)
        self.assertEqual(new.run.workflow.reviews[1].number,2)
        self.assertEqual(new.run.workflow.limits.max_review_rounds,3)

    def test_missing_operation_artifact_blocks_metadata_inspection_and_resume(self):
        runner=self.workspace()
        op=self.crash_file(runner,mutated=True)
        raw,=self.store.connection.execute('SELECT data FROM execution_operations WHERE id=?',(op.id,)).fetchone()
        digest=json.loads(raw)['fields']['change']['$artifact']
        path=self.store.codec.root/digest
        saved=path.read_bytes()
        path.unlink()
        self.store.close()
        self.store=SQLiteStateStore(self.path)
        recovery=RecoveryCoordinator(self.store)
        recovery.startup()
        info=recovery.inspect(runner.project_id,runner.run_id)
        self.assertTrue(any(i.kind=='artifact' for i in info['recovery'].unresolved))
        path.write_bytes(saved)
        recovery.resolve(runner.project_id,runner.run_id,'artifact-integrity',action='verify-artifacts',reason='Restore exact retained change artifact')
        recovery.resolve(runner.project_id,runner.run_id,op.id,action='verify-file',reason='Verify intended file hash after restoration')
        recovery.resume(runner.project_id,runner.run_id)

    def test_completed_run_artifact_damage_is_visible_without_reopening_execution(self):
        runner=self.synthetic()
        runner.run_until_stopped()
        raw,=self.store.connection.execute('SELECT data FROM submissions LIMIT 1').fetchone()
        digest=json.loads(raw)['fields']['evidence']['$artifact']
        (self.store.codec.root/digest).unlink()
        self.store.close()
        self.store=SQLiteStateStore(self.path)
        recovery=RecoveryCoordinator(self.store)
        recovery.startup()
        info=recovery.inspect(runner.project_id,runner.run_id)
        self.assertEqual(info['status'],'completed')
        self.assertTrue(any(i.kind=='artifact' for i in info['recovery'].unresolved))

    def test_exhausted_limits_cannot_be_reset_with_recovery(self):
        runner=self.synthetic()
        runner.controls.block('budget exhausted')
        self.store.atomic_update(runner.project_id,lambda p:(replace(p,runs=(replace(p.runs[0],workflow=replace(p.runs[0].workflow,exhausted_limit=True)),)),[DomainEvent(p.id,'fixture.limit_exhausted',{})]))
        new,recovery=self.restart(runner)
        with self.assertRaisesRegex(RecoveryError,'exhausted'):
            recovery.resume(new.project_id,new.run_id)
        self.assertTrue(new.run.workflow.exhausted_limit)

    def test_generation_is_preserved_after_scope_change_and_restart(self):
        runner=self.synthetic()
        runner.controls.change_scope()
        generation=runner.run.execution_generation
        new,recovery=self.restart(runner)
        self.assertEqual(new.run.execution_generation,generation)
        recovery.resume(new.project_id,new.run_id)
        self.assertEqual(new.run.execution_generation,generation)

    def test_recovery_gate_blocks_scope_change_bypass(self):
        runner=self.synthetic()
        self.crash_provider(runner)
        new,recovery=self.restart(runner)
        with self.assertRaises(ValueError): new.controls.change_scope()
        with self.assertRaises(ValueError): new.file_tool(None)

    def test_prepared_provider_call_has_no_unknown_charge(self):
        runner=self.synthetic()
        original=self.store.record_operation
        def interrupt(op):
            if op.kind=='provider' and op.stage is OperationStage.EXECUTING:
                raise Crash()
            original(op)
        with patch.object(self.store,'record_operation',interrupt):
            with self.assertRaises(Crash): runner.step()
        new,recovery=self.restart(runner)
        self.assertFalse(new.run.workflow.recovery.unresolved)
        self.assertEqual(self.store.usage(new.project_id)['provider_calls'],2)
        self.assertEqual(self.store.usage(new.project_id)['total_tokens'],30)
        recovery.resume(new.project_id,new.run_id)
        self.assertEqual(new.run.workflow.llm_calls,3) # Conservative reservation consumes the cap.
        self.assertEqual(self.store.usage(new.project_id)['provider_calls'],2)

    def test_fixture_process_crashes_and_all_five_restart_scenarios(self):
        from app.dev.recovery import demonstration
        result=demonstration(self.root/'process-fixtures')
        self.assertTrue(result['all_passed'])
        self.assertEqual(len(result['scenarios']),5)
        self.assertTrue(all(v['explicit_resume_status']=='completed' and not v['automatic_execution'] for v in result['scenarios']))

    def test_file_start_fence_without_mutation_can_be_proven_against_before_hash(self):
        runner=self.workspace()
        original=runner.workspace_gateway._files.write
        with patch.object(runner.workspace_gateway._files,'write',side_effect=Crash()):
            # Abrupt death normally skips finally. Here suppress final outcome persistence too.
            sink=runner.workspace_gateway.operation_sink
            def retain(op):
                if op.stage is OperationStage.SETTLED and op.operation=='write': raise Crash()
                return sink(op)
            with patch.object(runner.workspace_gateway,'operation_sink',retain):
                before=runner.file_tool(request(runner,'read',path='greeting.txt'))
                with self.assertRaises(Crash):
                    runner.file_tool(request(runner,'write',path='greeting.txt',expected_hash=before.content_hash,content='hello world\n'))
        new,recovery=self.restart(runner,gateway=True)
        issue=new.run.workflow.recovery.unresolved[0]
        recovery.resolve(new.project_id,new.run_id,issue.id,action='verify-file',reason='Current file equals retained pre-mutation bytes')
        operation=next(o for o in self.store.operations(new.project_id,new.run_id) if o.id==issue.id)
        self.assertEqual(operation.certainty,OutcomeCertainty.CONFIRMED_FAILURE)
        recovery.resume(new.project_id,new.run_id)
        self.assertEqual((self.root/'workspace'/'greeting.txt').read_text(),'hello\n')

    def test_provider_reservation_before_submission_fence_is_known_unstarted(self):
        runner=self.synthetic()
        original=self.store.record_operation
        def interrupt(op):
            if op.kind=='provider': raise Crash()
            original(op)
        with patch.object(self.store,'record_operation',interrupt):
            with self.assertRaises(Crash): runner.step()
        new,recovery=self.restart(runner)
        self.assertFalse(new.run.workflow.recovery.unresolved)
        self.assertEqual(self.store.usage(new.project_id)['total_tokens'],30)
        recovery.resume(new.project_id,new.run_id)
        new.run_until_stopped()
        self.assertEqual(new.run.status,RunStatus.COMPLETED)

    def test_legacy_provider_reservations_remain_unknown(self):
        runner=self.synthetic()
        original=self.store.record_operation
        def interrupt(op):
            if op.kind=='provider': raise Crash()
            original(op)
        with patch.object(self.store,'record_operation',interrupt):
            with self.assertRaises(Crash): runner.step()
        # Represent the pre-M4.2 invocation protocol without rewriting event history.
        raw,=self.store.connection.execute('SELECT data FROM invocations WHERE id=?',(runner.run.workflow.pending,)).fetchone()
        legacy=json.loads(raw)
        legacy['fields'].pop('protocol_version',None)
        self.store.connection.execute('UPDATE invocations SET data=? WHERE id=?',(json.dumps(legacy),runner.run.workflow.pending))
        new,recovery=self.restart(runner)
        self.assertTrue(new.run.workflow.recovery.unresolved)
        self.assertIsNone(self.store.usage(new.project_id)['total_tokens'])
        issue=new.run.workflow.recovery.unresolved[0]
        recovery.resolve(new.project_id,new.run_id,issue.id,action='abandon-provider',reason='Abandon legacy submitted request with unknown billing')
        recovery.resume(new.project_id,new.run_id)

    def test_legacy_file_intent_requires_explicit_operator_attestation(self):
        from app.domain.artifacts import ToolCallRecord
        runner=self.workspace()
        attempt=runner.run.workflow.attempts[-1]
        self.store.record_tool(runner.project_id,runner.run_id,
            ToolCallRecord('legacy-file:intent','developer','write',attempt.id,attempt.generation,'greeting.txt',None,'pending'))
        new,recovery=self.restart(runner,gateway=True)
        issue=new.run.workflow.recovery.unresolved[0]
        self.assertEqual(issue.certainty,OutcomeCertainty.UNCERTAIN)
        recovery.resolve(new.project_id,new.run_id,issue.id,action='acknowledge-file',reason='Controlled fixture inspected; current workspace accepted',quiescent=True)
        recovery.resume(new.project_id,new.run_id)
        self.assertEqual((self.root/'workspace'/'greeting.txt').read_text(),'hello\n')

    def test_recovered_reviewer_success_admits_linked_round_without_repeat(self):
        runner=self.synthetic()
        runner.step()
        submission=runner.run.workflow.submissions[0]
        self.crash_provider(runner,after=True)
        new,recovery=self.restart(runner)
        issue=new.run.workflow.recovery.unresolved[0]
        recovery.resolve(new.project_id,new.run_id,issue.id,action='accept-result',reason='Admit validated reviewer response',runner=new)
        self.assertEqual(new.run.phase,'decide')
        self.assertEqual(new.run.workflow.reviews[0].submission_id,submission.id)
        self.assertEqual(new.provider.requests,[])
        recovery.resume(new.project_id,new.run_id)
        new.run_until_stopped()
        self.assertEqual(len(new.run.workflow.reviews),1)

    def test_scope_change_late_provider_result_retains_usage_without_admission(self):
        entered,release=Event(),Event()
        def wait(req):
            if req.context['workflow']['phase']=='develop':
                entered.set()
                if not release.wait(4): raise RuntimeError('fixture deadline')
        runner=self.synthetic(ScriptedWorkflowProvider(hook=wait))
        errors=[]
        def execute():
            try: runner.step()
            except BaseException as exc: errors.append(exc)
        thread=Thread(target=execute);thread.start()
        self.assertTrue(entered.wait(2))
        try: runner.controls.change_scope()
        finally: release.set();thread.join(5)
        self.assertFalse(errors)
        self.assertFalse(runner.run.workflow.submissions)
        self.assertEqual(runner.run.status,RunStatus.PAUSED)
        self.assertEqual(self.store.usage(runner.project_id)['total_tokens'],45)

    def test_late_file_outcome_after_cancel_is_audited_without_resurrecting_run(self):
        from app.persistence.store import VersionConflictError
        runner=self.workspace()
        before=runner.file_tool(request(runner,'read',path='greeting.txt'))
        original=runner.workspace_gateway._files.write
        def write(*args,**kwargs):
            result=original(*args,**kwargs)
            runner.controls.cancel()
            return result
        with patch.object(runner.workspace_gateway._files,'write',write):
            with self.assertRaises(VersionConflictError):
                runner.file_tool(request(runner,'write',path='greeting.txt',expected_hash=before.content_hash,content='hello world\n'))
        self.assertEqual(runner.run.status,RunStatus.CANCELED)
        outcomes=[o for o in self.store.operations(runner.project_id,runner.run_id) if o.operation=='write']
        self.assertEqual(outcomes[-1].certainty,OutcomeCertainty.CONFIRMED_SUCCESS)
        self.assertLess(outcomes[-1].checkpoint.generation,runner.run.execution_generation)

    def test_captured_submission_is_reused_after_explicit_result_admission(self):
        runner=self.workspace()
        before=runner.file_tool(request(runner,'read',path='greeting.txt'))
        runner.file_tool(request(runner,'write',path='greeting.txt',expected_hash=before.content_hash,content='hello world\n'))
        original=runner.workspace_gateway.operation_sink
        def interrupt(op):
            if op.operation=='capture_submission' and op.stage is OperationStage.SETTLED:
                raise Crash()
            return original(op)
        with patch.object(runner.workspace_gateway,'operation_sink',interrupt):
            with self.assertRaises(Crash): runner.step()
        new,recovery=self.restart(runner,gateway=True)
        capture_issue=next(i for i in new.run.workflow.recovery.unresolved if i.kind=='file')
        provider_issue=next(i for i in new.run.workflow.recovery.unresolved if i.kind=='provider')
        recovery.resolve(new.project_id,new.run_id,capture_issue.id,action='verify-capture',reason='Verify hashed immutable captured submission')
        with patch.object(new.workspace_gateway,'execute',side_effect=AssertionError('capture replay')):
            recovery.resolve(new.project_id,new.run_id,provider_issue.id,action='accept-result',reason='Use retained capture with saved developer proposal',runner=new)
        self.assertEqual(new.run.phase,'review')
        self.assertEqual(len(new.run.workflow.submissions),1)
        recovery.resume(new.project_id,new.run_id)
        new.run_until_stopped()
        self.assertEqual(new.run.status,RunStatus.COMPLETED)

    def test_canceled_interrupted_provider_can_be_closed_without_erasing_unknown_usage(self):
        runner=self.synthetic()
        self.crash_provider(runner)
        runner.controls.cancel()
        new,recovery=self.restart(runner)
        self.assertEqual(new.run.status,RunStatus.CANCELED)
        issue=new.run.workflow.recovery.unresolved[0]
        recovery.resolve(new.project_id,new.run_id,issue.id,action='abandon-provider',reason='Keep canceled; accept unknown charge')
        self.assertIsNone(new.run.workflow.pending)
        self.assertIsNone(self.store.usage(new.project_id)['total_tokens'])
        self.store.create_run(new.project_id,run_id='new-explicit-run')

    def test_requirement_version_fences_late_result_without_generation_change(self):
        entered,release=Event(),Event()
        def wait(req):
            if req.context['workflow']['phase']=='develop':
                entered.set()
                if not release.wait(4): raise RuntimeError('fixture deadline')
        runner=self.synthetic(ScriptedWorkflowProvider(hook=wait))
        errors=[]
        def execute():
            try: runner.step()
            except BaseException as exc: errors.append(exc)
        thread=Thread(target=execute);thread.start()
        self.assertTrue(entered.wait(2))
        try:
            self.store.atomic_update(runner.project_id,lambda p:(replace(p,requirement_version=p.requirement_version+1),[DomainEvent(p.id,'fixture.requirements_changed',{})]))
        finally: release.set();thread.join(5)
        self.assertFalse(errors)
        self.assertFalse(runner.run.workflow.submissions)
        self.assertEqual(self.store.usage(runner.project_id)['total_tokens'],45)

    def test_recovery_retains_original_blocked_reason_and_resume_phase(self):
        runner=self.synthetic()
        runner.controls.block('original technical blocker')
        new,recovery=self.restart(runner)
        recovery.resume(new.project_id,new.run_id)
        self.assertEqual(new.run.status,RunStatus.WAITING_FOR_USER)
        self.assertEqual(new.run.workflow.blocked_reason,'original technical blocker')
        self.assertEqual(new.run.workflow.resume_phase,'develop')
        self.assertFalse(new.step())

    def test_version_two_upgrade_preserves_immutable_history_bytes(self):
        runner=self.synthetic()
        runner.run_until_stopped()
        con=self.store.connection
        for identity,data in con.execute('SELECT id,data FROM invocations').fetchall():
            value=json.loads(data)
            value['fields'].pop('protocol_version',None)
            con.execute('UPDATE invocations SET data=? WHERE id=?',(json.dumps(value),identity))
        raw,=con.execute('SELECT data FROM runs WHERE id=?',(runner.run_id,)).fetchone()
        body=json.loads(raw)
        wf_fields=dict(body['$map'])['state']['fields']['workflow']['fields']
        for field in ('checkpoint','recovery','recovery_epoch'): wf_fields.pop(field,None)
        con.execute('UPDATE runs SET data=? WHERE id=?',(json.dumps(body),runner.run_id))
        con.execute('DROP TABLE execution_operations')
        con.execute('DROP TABLE api_commands')
        con.execute('DELETE FROM schema_migrations WHERE version>=3')
        saved=con.execute('SELECT id,data FROM invocations ORDER BY id').fetchall()
        events=self.store.events(runner.project_id)
        self.store.close()
        self.store=SQLiteStateStore(self.path)
        self.assertEqual(self.store.connection.execute('SELECT max(version) FROM schema_migrations').fetchone()[0],4)
        self.assertEqual(self.store.events(runner.project_id),events)
        self.store.create_run(runner.project_id,run_id='after-migration')
        self.assertEqual(self.store.connection.execute('SELECT id,data FROM invocations ORDER BY id').fetchall(),saved)


class InMemoryRecoveryTests(unittest.TestCase):
    def test_unknown_provider_and_explicit_resume_use_same_store_boundary(self):
        from app.persistence.memory import InMemoryStateStore
        store=InMemoryStateStore()
        runner=make_runner(store=store)
        approve_generated(runner);runner.step()
        runner.provider.hook=lambda _: (_ for _ in ()).throw(Crash())
        with self.assertRaises(Crash): runner.step()
        runner.provider.hook=None
        recovery=RecoveryCoordinator(store)
        recovery.reconcile(runner.project_id,runner.run_id)
        self.assertFalse(runner.step())
        issue=runner.run.workflow.recovery.unresolved[0]
        recovery.resolve(runner.project_id,runner.run_id,issue.id,action='abandon-provider',reason='Controlled memory fixture abandonment')
        recovery.resume(runner.project_id,runner.run_id)
        runner.run_until_stopped()
        self.assertEqual(runner.run.status,RunStatus.COMPLETED)
        self.assertIsNone(store.usage(runner.project_id)['total_tokens'])

    def test_safe_phase_reconciliation_preserves_attempt_and_counters(self):
        from app.persistence.memory import InMemoryStateStore
        runner=make_runner(store=InMemoryStateStore())
        approve_generated(runner);runner.step()
        original=runner.run.workflow
        recovery=RecoveryCoordinator(runner.store)
        recovery.reconcile(runner.project_id,runner.run_id)
        self.assertFalse(runner.step())
        recovery.resume(runner.project_id,runner.run_id)
        self.assertEqual(runner.run.workflow.invocations,original.invocations)
        self.assertEqual(runner.run.workflow.attempts,original.attempts)
        runner.run_until_stopped()
        self.assertEqual(runner.run.status,RunStatus.COMPLETED)

    def test_recovery_metadata_and_event_failure_roll_back_together(self):
        runner=make_runner()
        approve_generated(runner);runner.step()
        # This test is in the memory-contract class; use a disposable SQLite copy
        # so the separate metadata-only recovery write is exercised under failure.
        with TemporaryDirectory(prefix='m42-metadata-') as tmp:
            with SQLiteStateStore(Path(tmp)/'state.db') as store:
                saved=store.create_project(runner.store.get_project(runner.project_id))
                before=store.get_project(saved.id)
                events=store.events(saved.id)
                store.connection.execute("CREATE TRIGGER fail_gate BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT,'injected'); END")
                with self.assertRaises(sqlite3.IntegrityError):
                    RecoveryCoordinator(store).reconcile(saved.id,runner.run_id)
                self.assertEqual(store.get_project(saved.id),before)
                self.assertEqual(store.events(saved.id),events)

    def test_workspace_runner_cannot_resume_using_synthetic_gateway(self):
        with TemporaryDirectory(prefix='m42-mode-') as tmp:
            path=Path(tmp)
            workspace=path/'workspace';workspace.mkdir()
            (workspace/'greeting.txt').write_text('hello\n')
            with SQLiteStateStore(path/'state.db') as store:
                runner=make_workspace_runner(workspace,store=store)
            with SQLiteStateStore(path/'state.db') as store:
                provider=ScriptedWorkflowProvider()
                with self.assertRaisesRegex(ValueError,'workspace gateway'):
                    WorkflowRunner(store,runner.project_id,runner.run_id,provider)
                self.assertFalse(provider.requests)

    def test_memory_late_file_outcome_after_cancel_cannot_resurrect_run(self):
        from app.persistence.memory import InMemoryStateStore
        from app.persistence.store import VersionConflictError
        with TemporaryDirectory(prefix='m42-memory-file-') as tmp:
            root=Path(tmp)
            (root/'greeting.txt').write_text('hello\n')
            runner=make_workspace_runner(root,store=InMemoryStateStore())
            before=runner.file_tool(request(runner,'read',path='greeting.txt'))
            original=runner.workspace_gateway._files.write
            def write(*args,**kwargs):
                value=original(*args,**kwargs)
                runner.controls.cancel()
                return value
            with patch.object(runner.workspace_gateway._files,'write',write):
                with self.assertRaises(VersionConflictError):
                    runner.file_tool(request(runner,'write',path='greeting.txt',expected_hash=before.content_hash,content='hello world\n'))
            self.assertEqual(runner.run.status,RunStatus.CANCELED)
            self.assertEqual(runner.store.operations(runner.project_id,runner.run_id)[-1].certainty,OutcomeCertainty.CONFIRMED_SUCCESS)


class LateCommandRecoveryTests(unittest.TestCase):
    setUp = RecoveryTests.setUp
    command_fixture = CommandRecoveryTests.command_fixture
    def test_old_command_receipt_cannot_acknowledge_new_provider_pause(self):
        from app.dev.workspace import WorkspaceFixtureProvider
        runner,req,approval,_=self.command_fixture()
        collected,release_command,entered,release_provider=Event(),Event(),Event(),Event()
        errors=[]
        original=runner.workspace_gateway.collect_command
        def collect(command,stop):
            result=original(command,stop)
            collected.set()
            if not release_command.wait(5): raise RuntimeError('command fixture timeout')
            return result
        def command_work():
            try: runner.command_tool(req,approval)
            except BaseException as exc: errors.append(exc)
        with patch.object(runner.workspace_gateway,'collect_command',collect):
            thread=Thread(target=command_work);thread.start()
            self.assertTrue(collected.wait(2))
            provider_thread=None
            try:
                recovery=RecoveryCoordinator(self.store)
                recovery.reconcile(runner.project_id,runner.run_id)
                issue=next(i for i in runner.run.workflow.recovery.unresolved if i.kind=='command')
                recovery.resolve(runner.project_id,runner.run_id,issue.id,action='acknowledge-command',
                                 reason='Owned process collected and reaped; delayed result delivery only',quiescent=True)
                recovery.resume(runner.project_id,runner.run_id)
                def wait(req):
                    entered.set()
                    if not release_provider.wait(5): raise RuntimeError('provider fixture timeout')
                gateway=WorkspaceToolGateway(WorkspacePolicy(self.root/'workspace'))
                new=WorkflowRunner(self.store,runner.project_id,runner.run_id,WorkspaceFixtureProvider(hook=wait),gateway=gateway)
                def provider_work():
                    try: new.step()
                    except BaseException as exc: errors.append(exc)
                provider_thread=Thread(target=provider_work);provider_thread.start()
                self.assertTrue(entered.wait(2))
                pending=new.run.workflow.pending
                new.controls.pause()
                release_command.set();thread.join(3)
                self.assertFalse(thread.is_alive())
                self.assertEqual(new.run.status,RunStatus.PAUSE_REQUESTED)
                self.assertEqual(new.run.workflow.pending,pending)
            finally:
                release_command.set();release_provider.set()
                thread.join(5)
                if provider_thread: provider_thread.join(5)
            self.assertFalse(errors)
            self.assertEqual(new.run.status,RunStatus.PAUSED)


    def test_pending_permission_receipt_before_workflow_commit_is_restored(self):
        runner,req,approval,_=self.command_fixture()
        original=self.store.record_tool
        def interrupt(p,r,record,**kwargs):
            original(p,r,record,**kwargs)
            if getattr(record,'action',None)=='request' and record.outcome=='pending': raise Crash()
        with patch.object(self.store,'record_tool',interrupt):
            with self.assertRaises(Crash): runner.request_command(req)
        self.assertEqual(runner.run.workflow.pending_permissions,())
        self.store.close();self.store=SQLiteStateStore(self.path)
        recovery=RecoveryCoordinator(self.store);recovery.startup()
        gateway=WorkspaceToolGateway(WorkspacePolicy(self.root/'workspace'))
        new=WorkflowRunner(self.store,runner.project_id,runner.run_id,ScriptedWorkflowProvider(),gateway=gateway)
        pending=next(a for a in gateway.approvals if a.status=='pending')
        self.assertEqual(new.run.workflow.pending_permissions,(pending.id,))
        recovery.resume(new.project_id,new.run_id)
        self.assertFalse(new.step())
        new.controls.resolve_command(pending.id,approved=False,reason='Explicit denial of restored pending request')
        self.assertEqual(new.run.workflow.pending_permissions,())

    def test_permission_decision_receipt_before_workflow_commit_is_retained(self):
        runner,req,approval,_=self.command_fixture()
        pending=runner.request_command(req)
        original=self.store.record_tool
        def interrupt(p,r,record,**kwargs):
            original(p,r,record,**kwargs)
            if getattr(record,'action',None)=='decision': raise Crash()
        with patch.object(self.store,'record_tool',interrupt):
            with self.assertRaises(Crash):
                runner.controls.resolve_command(pending.id,approved=False,reason='Durable denial with interrupted workflow commit')
        self.assertEqual(runner.run.workflow.pending_permissions,(pending.id,))
        self.store.close();self.store=SQLiteStateStore(self.path)
        recovery=RecoveryCoordinator(self.store);recovery.startup()
        self.assertEqual(self.store.get_project(runner.project_id).run(runner.run_id).workflow.pending_permissions,())
        self.assertEqual(next(a for a in self.store.approvals(runner.project_id,runner.run_id) if a.id==pending.id).status,'denied')
