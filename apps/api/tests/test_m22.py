"""Workflow tests exercise authority, evidence, lifetime budgets and control races."""
import unittest
from dataclasses import replace
from threading import Event, Thread

from app.agents.contracts import Requirement
from app.agents.runtime import AgentRuntime
from app.dev.workflow import ScriptedWorkflowProvider, make_runner, approve_generated, scenario
from app.domain.agents import AgentKind
from app.domain.projects import ProjectState, RunStatus
from app.domain.tasks import TaskStatus
from app.orchestration.limits import ExecutionLimits
from app.persistence.store import StoreError, ActiveRunError, VersionConflictError
from app.providers.base import ProviderTimeoutError, ProviderConfigurationError
from app.tools.memory import InMemoryToolGateway
from app.tools.contracts import ToolRequest


class AlteredProvider(ScriptedWorkflowProvider):
    def __init__(self, alter, **kwargs):
        super().__init__(**kwargs)
        self.alter = alter

    def complete(self, request):
        response = super().complete(request)
        output = response.output
        self.alter(request, output)
        return replace(response, output=output)


class WorkflowTests(unittest.TestCase):
    def execute(self, provider=None, **kwargs):
        runner = make_runner(provider, **kwargs)
        approve_generated(runner)
        runner.run_until_stopped()
        return runner

    def test_initial_pass_and_final_completion_require_accepted_manifest(self):
        r = self.execute()
        self.assertEqual(r.run.status, RunStatus.COMPLETED)
        wf = r.run.workflow
        self.assertEqual(wf.accepted, (wf.submissions[0].id,))
        self.assertEqual(wf.final_result.completed_task_ids, r.run.task_ids)
        self.assertEqual(len(wf.attempts), 1)
        self.assertEqual(len(wf.call_records), 6)

    def test_multi_task_dependency_execution_and_evidence_context(self):
        provider = ScriptedWorkflowProvider(tasks=3)
        r = self.execute(provider)
        self.assertEqual(r.run.status, RunStatus.COMPLETED)
        self.assertEqual(tuple(a.task_id for a in r.run.workflow.attempts), r.run.task_ids)
        events = r.store.events('demo')
        accepted = [e.sequence for e in events if e.type == 'task.accepted']
        assigned = [e.sequence for e in events if e.type == 'task.assigned']
        self.assertTrue(accepted[0] < assigned[1] < accepted[1] < assigned[2])
        dev = [q for q in provider.requests if q.context['workflow']['phase'] == 'develop']
        self.assertTrue(dev[1].context['workflow']['dependency_evidence'])

    def test_fail_revision_pass(self):
        r = self.execute(ScriptedWorkflowProvider(('FAIL', 'PASS')))
        self.assertEqual(r.run.status, RunStatus.COMPLETED)
        self.assertEqual([s.version for s in r.run.workflow.submissions], [1, 2])
        self.assertEqual(r.run.workflow.revisions[0].remaining_review_rounds, 2)

    def test_two_revisions_then_pass(self):
        r = self.execute(ScriptedWorkflowProvider(('FAIL', 'FAIL', 'PASS')))
        self.assertEqual(r.run.status, RunStatus.COMPLETED)
        self.assertEqual(len(r.run.workflow.reviews), 3)
        self.assertEqual(len(r.run.workflow.revisions), 2)

    def test_repeated_fail_blocks_exactly_at_limit(self):
        r = self.execute(ScriptedWorkflowProvider(('FAIL',)))
        self.assertEqual(r.run.status, RunStatus.WAITING_FOR_USER)
        self.assertEqual(len(r.run.workflow.submissions), 3)
        self.assertEqual(len(r.run.workflow.reviews), 3)
        self.assertEqual(r.store.get_project('demo').task(r.run.current_task_id).status, TaskStatus.BLOCKED)
        with self.assertRaisesRegex(ValueError, 'limits'):
            r.controls.resolve()

    def test_manager_cannot_bypass_fail(self):
        def alter(q, out):
            if q.context['workflow']['phase'] == 'decide':
                out['action'] = 'accept_submission'
        r = self.execute(AlteredProvider(alter, verdicts=('FAIL',)))
        self.assertEqual(r.run.status, RunStatus.WAITING_FOR_USER)
        self.assertFalse(r.run.workflow.accepted)
        self.assertIn('bypass Reviewer FAIL', r.run.workflow.blocked_reason)

    def test_missing_submission_evidence_blocks(self):
        def alter(q, out):
            if q.context['workflow']['phase'] == 'develop':
                out['tests'] = []
        r = self.execute(AlteredProvider(alter))
        self.assertEqual(r.run.status, RunStatus.WAITING_FOR_USER)
        self.assertFalse(r.run.workflow.submissions)
        self.assertIn('missing submission evidence', r.run.workflow.blocked_reason)

    def test_wrong_submission_version_is_rejected(self):
        def alter(q, out):
            if q.context['workflow']['phase'] == 'develop':
                out['output_version'] = 99
        r = self.execute(AlteredProvider(alter))
        self.assertFalse(r.run.workflow.submissions)
        self.assertIn('identity/version', r.run.workflow.blocked_reason)

    def test_malformed_review_is_technical_failure_not_fail(self):
        def alter(q, out):
            if q.context['workflow']['phase'] == 'review':
                out['verdict'] = 'MAYBE'
        r = self.execute(AlteredProvider(alter))
        self.assertEqual(len(r.run.workflow.submissions), 1)
        self.assertFalse(r.run.workflow.reviews)
        self.assertIn('technical failure', r.run.workflow.blocked_reason)
        self.assertEqual(sum(c.purpose == 'repair' for c in r.run.workflow.call_records), 1)

    def test_empty_review_assessments_cannot_pass(self):
        def alter(q, out):
            if q.context['workflow']['phase'] == 'review':
                out['assessments'] = []
        r = self.execute(AlteredProvider(alter))
        self.assertFalse(r.run.workflow.accepted)
        self.assertIn('every current criterion', r.run.workflow.blocked_reason)

    def test_stale_review_submission_rejected(self):
        def alter(q, out):
            if q.context['workflow']['phase'] == 'review':
                out['submission_id'] = 'old-submission'
        r = self.execute(AlteredProvider(alter))
        self.assertFalse(r.run.workflow.reviews)
        self.assertIn('stale submission', r.run.workflow.blocked_reason)

    def test_dependency_bypass_assignment_rejected(self):
        def alter(q, out):
            if q.context['workflow']['phase'] == 'assign':
                out['task_id'] = 't0-1'
        r = self.execute(AlteredProvider(alter, tasks=2))
        self.assertFalse(r.run.workflow.attempts)
        self.assertIn('not approved and ready', r.run.workflow.blocked_reason)

    def test_second_task_never_starts_after_invalid_previous_review(self):
        def alter(q, out):
            if q.context['workflow']['phase'] == 'review':
                out['assessments'] = []
        r = self.execute(AlteredProvider(alter, tasks=2))
        self.assertEqual(len(r.run.workflow.attempts), 1)
        self.assertEqual(len(r.run.workflow.accepted), 0)

    def test_final_result_cannot_omit_evidence(self):
        def alter(q, out):
            if q.context['workflow']['phase'] == 'final':
                out['evidence_refs'] = []
        r = self.execute(AlteredProvider(alter))
        self.assertEqual(r.run.status, RunStatus.WAITING_FOR_USER)
        self.assertIsNone(r.run.workflow.final_result)

    def test_generic_store_mutation_cannot_bypass_workflow(self):
        r = make_runner()
        approve_generated(r)
        task_id = r.run.task_ids[0]
        for command in [lambda: r.store.start_next_task('demo', r.run_id),
                        lambda: r.store.transition_task('demo', r.run_id, task_id, TaskStatus.DONE),
                        lambda: r.store.transition_run('demo', r.run_id, RunStatus.COMPLETED),
                        lambda: r.store.cancel_task('demo', r.run_id, task_id)]:
            with self.assertRaisesRegex(StoreError, 'orchestration'):
                command()

    def test_execution_before_approval_does_not_call_provider(self):
        r = make_runner()
        r.step()
        count = len(r.provider.requests)
        self.assertFalse(r.step())
        self.assertEqual(len(r.provider.requests), count)

    def test_invocation_limit(self):
        r = self.execute(limits=ExecutionLimits(max_invocations=2))
        self.assertEqual(r.run.workflow.invocations, 2)
        self.assertEqual(len(r.provider.requests), 2)
        self.assertIn('invocation limit', r.run.workflow.blocked_reason)

    def test_llm_call_limit(self):
        r = self.execute(limits=ExecutionLimits(max_llm_calls=2))
        self.assertEqual(r.run.workflow.llm_calls, 2)
        self.assertEqual(len(r.provider.requests), 2)
        self.assertIn('LLM call limit', r.run.workflow.blocked_reason)

    def test_iteration_limit(self):
        r = self.execute(limits=ExecutionLimits(max_iterations=2))
        self.assertEqual(r.run.workflow.iterations, 2)
        self.assertIn('iteration limit', r.run.workflow.blocked_reason)

    def test_task_creation_limit(self):
        r = make_runner(ScriptedWorkflowProvider(tasks=2), limits=ExecutionLimits(max_tasks=1))
        r.run_until_stopped()
        self.assertEqual(r.run.status, RunStatus.WAITING_FOR_USER)
        self.assertFalse(r.store.get_project('demo').tasks)
        self.assertIn('task creation limit', r.run.workflow.blocked_reason)

    def test_replanning_limit_and_cumulative_tasks(self):
        r = make_runner(limits=ExecutionLimits(max_replans=1))
        r.run_until_stopped()
        r.request_replan()
        r.run_until_stopped()
        self.assertEqual(r.run.workflow.tasks_created, 2)
        r.request_replan()
        self.assertEqual(r.run.status, RunStatus.WAITING_FOR_USER)
        self.assertEqual(r.run.workflow.replans, 1)
        self.assertEqual(r.run.workflow.invocations, 2)

    def test_replacement_plan_cannot_evade_task_creation_budget(self):
        r = make_runner(limits=ExecutionLimits(max_tasks=1))
        r.run_until_stopped()
        r.request_replan()
        r.run_until_stopped()
        self.assertEqual(r.run.workflow.tasks_created, 1)
        self.assertIn('task creation limit', r.run.workflow.blocked_reason)

    def test_review_rounds_survive_scope_changes(self):
        r = make_runner()
        approve_generated(r)
        for _ in range(4):
            r.step()  # accepted first submission, before final
        old = r.run.workflow
        r.controls.change_scope(requirements=(Requirement('req-1', 'Changed goal', ('Changed criterion',)),))
        self.assertFalse(r.run.workflow.accepted)
        self.assertEqual(r.run.workflow.attempts, old.attempts)
        self.assertEqual(r.run.workflow.submissions, old.submissions)
        self.assertEqual(r.run.workflow.invocations, old.invocations)
        r.controls.resume()
        r.run_until_stopped()
        self.assertEqual(r.run.status, RunStatus.COMPLETED)
        self.assertEqual(len(r.run.workflow.submissions), 2)
        self.assertEqual(r.run.workflow.submissions[-1].requirement_version, r.store.get_project('demo').requirement_version)

    def test_pause_ack_prevents_new_operations_and_resume_keeps_counters(self):
        r = make_runner()
        approve_generated(r)
        r.controls.pause()
        before = r.run.workflow
        self.assertEqual(r.run.status, RunStatus.PAUSED)
        for _ in range(3):
            self.assertFalse(r.step())
        self.assertEqual(r.run.workflow, before)
        r.controls.resume()
        r.run_until_stopped()
        self.assertEqual(r.run.status, RunStatus.COMPLETED)

    def test_pause_during_slow_operation(self):
        self.assertEqual(scenario('D')['status'], 'completed')

    def test_cancel_late_result_does_not_advance_and_usage_is_retained(self):
        result = scenario('E')
        self.assertEqual(result['status'], 'canceled')
        self.assertEqual(result['review_rounds'], 0)
        self.assertEqual(result['calls'], 3)

    def test_instruction_applied_only_at_next_boundary(self):
        r = make_runner()
        approve_generated(r)
        r.controls.instruct('Use a concise synthetic summary')
        self.assertEqual(r.run.workflow.instructions, ())
        r.step()
        self.assertEqual(r.run.workflow.pending_instructions, ())
        self.assertIn('Use a concise synthetic summary', r.provider.requests[-1].context['workflow']['instructions'])

    def test_scope_change_during_provider_call_rejects_old_generation(self):
        r = make_runner()
        approve_generated(r)
        r.step()
        def change(q):
            if q.context['workflow']['phase'] == 'develop':
                r.controls.change_scope(requirements=(Requirement('req-1', 'New scope', ('New criterion',)),))
        r.provider.hook = change
        r.step()
        self.assertEqual(r.run.status, RunStatus.PAUSED)
        self.assertFalse(r.run.workflow.submissions)
        self.assertEqual(len(r.run.workflow.call_records), 3)
        self.assertTrue(any(e.type == 'operation.stale_ignored' for e in r.store.events('demo')))

    def test_configuration_change_invalidates_inflight_generation(self):
        r = make_runner()
        approve_generated(r)
        r.step()
        def change(q):
            if q.context['workflow']['phase'] == 'develop':
                r.controls.change_scope(config_snapshot={'developer': 'different'})
        r.provider.hook = change
        r.step()
        self.assertEqual(r.run.status, RunStatus.PAUSED)
        self.assertFalse(r.run.workflow.submissions)

    def test_technical_retry_does_not_consume_extra_review_round(self):
        class RetryProvider(ScriptedWorkflowProvider):
            failed = False
            def complete(self, request):
                if request.context['workflow']['phase'] == 'review' and not self.failed:
                    self.failed = True
                    raise ProviderTimeoutError('fixture timeout')
                return super().complete(request)
        r = self.execute(RetryProvider(), runtime=AgentRuntime(sleeper=lambda _: None))
        self.assertEqual(r.run.status, RunStatus.COMPLETED)
        self.assertEqual(len(r.run.workflow.submissions), 1)
        self.assertEqual(len(r.run.workflow.reviews), 1)
        self.assertEqual(len(r.run.workflow.call_records), 7)
        self.assertEqual(sum(c.status == 'failed' for c in r.run.workflow.call_records), 1)

    def test_per_invocation_call_budget(self):
        class RetryProvider(ScriptedWorkflowProvider):
            def complete(self, request):
                if request.context['workflow']['phase'] == 'review':
                    raise ProviderTimeoutError('fixture timeout')
                return super().complete(request)
        r = self.execute(RetryProvider(), limits=ExecutionLimits(max_calls_per_invocation=2),
                         runtime=AgentRuntime(sleeper=lambda _: None))
        self.assertEqual(len(r.run.workflow.submissions), 1)
        self.assertEqual(sum(c.status == 'failed' for c in r.run.workflow.call_records), 2)
        self.assertIn('call limit', r.run.workflow.blocked_reason)

    def test_pause_prevents_retry_after_transient_error(self):
        r = make_runner(runtime=AgentRuntime(sleeper=lambda _: None))
        approve_generated(r)
        def pause_and_fail(q):
            r.controls.pause()
            raise ProviderTimeoutError('timeout while pausing')
        r.provider.hook = pause_and_fail
        r.step()
        self.assertEqual(r.run.status, RunStatus.PAUSED)
        self.assertEqual(len(r.run.workflow.call_records), 2)
        self.assertFalse(r.run.workflow.attempts)

    def test_nonretryable_error_keeps_call_attribution(self):
        r = make_runner()
        approve_generated(r)
        def fail(q):
            raise ProviderConfigurationError('fixture failure')
        r.provider.hook = fail
        r.step()
        self.assertEqual(len(r.run.workflow.call_records), 2)
        self.assertEqual(r.run.workflow.call_records[-1].status, 'failed')

    def test_cancel_does_not_reset_budgets_or_allow_reinitialize(self):
        r = make_runner()
        approve_generated(r)
        r.step()
        old = r.run.workflow
        r.controls.cancel()
        self.assertEqual(r.run.workflow.invocations, old.invocations)
        self.assertEqual(r.run.workflow.tasks_created, old.tasks_created)
        with self.assertRaisesRegex(ValueError, 'cannot reset'):
            r.initialize()
        with self.assertRaises(ValueError):
            r.request_replan()
        self.assertFalse(r.step())

    def test_reviewer_cannot_write_controlled_evidence(self):
        with self.assertRaisesRegex(ValueError, 'read-only'):
            InMemoryToolGateway().execute(ToolRequest('capture_submission', AgentKind.REVIEWER, 's1', 1, ('data',)))

    def test_tool_has_no_filesystem_or_command_operation(self):
        for operation in ['write_file', 'run_command', 'read_file']:
            with self.assertRaises(ValueError):
                InMemoryToolGateway().execute(ToolRequest(operation, AgentKind.DEVELOPER, 's1', 1, ('data',)))

    def test_store_version_conflict_and_event_defensive_copy(self):
        r = make_runner()
        p = r.store.get_project('demo')
        with self.assertRaises(VersionConflictError):
            r.store.atomic_update('demo', lambda _: None, expected_version=p.version - 1)
        events = r.store.events('demo')
        events[0].payload['tampered'] = True
        self.assertNotIn('tampered', r.store.events('demo')[0].payload)

    def test_second_project_cannot_start_another_active_run(self):
        r = make_runner()
        r.store.create_project(ProjectState('other', 'Other', 'Other goal'))
        with self.assertRaises(ActiveRunError):
            r.store.create_run('other')

    def test_resolve_technical_failure_preserves_phase_and_round(self):
        r = make_runner()
        approve_generated(r)
        r.step()
        r.step()
        def fail(q):
            raise ProviderConfigurationError('fixture transport unavailable')
        r.provider.hook = fail
        r.step()
        self.assertEqual(r.run.status, RunStatus.WAITING_FOR_USER)
        rounds = len(r.run.workflow.submissions)
        r.provider.hook = None
        r.controls.resolve()
        r.run_until_stopped()
        self.assertEqual(r.run.status, RunStatus.COMPLETED)
        self.assertEqual(len(r.run.workflow.submissions), rounds)

    def test_invalid_limits_rejected(self):
        for kwargs in [{'max_review_rounds': 0}, {'max_llm_calls': True}, {'max_replans': -1}]:
            with self.assertRaises(ValueError):
                ExecutionLimits(**kwargs)

    def test_scope_change_cannot_resume_while_old_operation_is_pending(self):
        r = make_runner()
        approve_generated(r)
        r.step()
        def change(q):
            r.controls.change_scope()
            with self.assertRaises(ValueError):
                r.controls.resume()
        r.provider.hook = change
        r.step()
        self.assertIsNone(r.run.workflow.pending)
        r.provider.hook = None
        r.controls.resume()
        r.run_until_stopped()
        self.assertEqual(r.run.status, RunStatus.COMPLETED)

    def test_block_during_call_discards_result_and_resumes_same_phase(self):
        r = make_runner()
        approve_generated(r)
        r.step()
        r.provider.hook = lambda q: r.controls.block('Human requested inspection')
        r.step()
        self.assertEqual(r.run.status, RunStatus.WAITING_FOR_USER)
        self.assertFalse(r.run.workflow.submissions)
        self.assertEqual(r.run.workflow.resume_phase, 'develop')
        r.provider.hook = None
        r.controls.resolve()
        r.run_until_stopped()
        self.assertEqual(r.run.status, RunStatus.COMPLETED)

    def test_concurrent_step_cannot_dispatch_second_operation(self):
        r = make_runner()
        approve_generated(r)
        r.provider.hook = lambda q: self.assertFalse(r.step())
        r.run_until_stopped()
        self.assertEqual(r.run.status, RunStatus.COMPLETED)
        self.assertEqual(len(r.provider.requests), 6)

    def test_usage_events_reference_run_task_and_call(self):
        r = self.execute()
        events = [e for e in r.store.events('demo') if e.type == 'usage.recorded']
        self.assertEqual(len(events), len(r.run.workflow.call_records))
        self.assertTrue(all(e.run_id == r.run_id and e.correlation_id == e.payload['invocation_id'] for e in events))
        self.assertTrue(any(e.task_id == r.run.task_ids[0] for e in events))

    def test_task_acceptance_event_references_exact_submission(self):
        r = self.execute()
        event = next(e for e in r.store.events('demo') if e.type == 'task.accepted')
        self.assertEqual(event.task_id, r.run.task_ids[0])
        self.assertEqual(event.payload['submission_id'], r.run.workflow.accepted[0])

    def test_new_requirements_are_included_in_review_criteria(self):
        r = make_runner()
        approve_generated(r)
        r.controls.change_scope(requirements=(Requirement('req-1', 'New scope', ('Brand-new criterion',)),))
        r.controls.resume()
        r.run_until_stopped()
        review_request = next(q for q in r.provider.requests if q.context['workflow']['phase'] == 'review')
        self.assertIn('Brand-new criterion', review_request.context['workflow']['criteria'].values())

    def test_cancellation_retains_charge_after_late_provider_error(self):
        r = make_runner()
        approve_generated(r)
        def cancel_and_fail(q):
            r.controls.cancel()
            raise ProviderTimeoutError('late timeout')
        r.provider.hook = cancel_and_fail
        r.runtime = AgentRuntime(sleeper=lambda _: None)
        r.step()
        self.assertEqual(r.run.status, RunStatus.CANCELED)
        self.assertEqual(r.run.workflow.call_records[-1].status, 'failed')
        self.assertEqual(r.run.workflow.llm_calls, 2)

    def test_manifest_snapshot_cannot_be_changed_by_review(self):
        r = make_runner()
        approve_generated(r)
        r.step()
        r.step()
        snapshot = r.run.workflow.submissions[0]
        r.step()
        self.assertEqual(r.run.workflow.submissions[0], snapshot)
        with self.assertRaises(AttributeError):
            snapshot.digest = 'changed'

    def test_run_snapshot_serializes_workflow_history(self):
        import json
        r = self.execute()
        state = json.loads(json.dumps(r.run.to_dict()))
        self.assertEqual(state['workflow']['final_result']['status'], 'completed')
        self.assertEqual(len(state['workflow']['call_records']), 6)


if __name__ == '__main__':
    unittest.main()
