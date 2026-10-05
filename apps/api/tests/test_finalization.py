"""Finalization must preserve authoritative task and accepted evidence identities."""
import unittest
from dataclasses import replace

from app.dev.workflow import ScriptedWorkflowProvider, make_runner, approve_generated
from app.domain.projects import RunStatus
from app.providers.schemas import schema_for_output


class FinalizationTests(unittest.TestCase):
    def run_fixture(self, tasks=1, verdicts=('PASS',), mutation=None):
        class Provider(ScriptedWorkflowProvider):
            def complete(self, request):
                response = super().complete(request)
                if mutation and request.context['workflow']['phase'] == 'final':
                    mutation(response.output, self.requests)
                return response
        provider = Provider(tasks=tasks, verdicts=verdicts)
        runner = make_runner(provider)
        approve_generated(runner)
        runner.run_until_stopped()
        return runner, provider

    def test_one_and_multiple_tasks_use_authoritative_final_context(self):
        for count in (1, 3):
            with self.subTest(tasks=count):
                runner, provider = self.run_fixture(tasks=count)
                self.assertEqual(runner.run.status, RunStatus.COMPLETED)
                wf = runner.run.workflow
                final = provider.requests[-1]
                self.assertEqual(final.output_schema, 'final_result.v1')
                context = final.context['workflow']
                self.assertEqual(context['completed_task_ids'], list(runner.run.task_ids))
                self.assertEqual(context['evidence_refs'], list(wf.accepted))
                self.assertEqual(wf.final_result.completed_task_ids, runner.run.task_ids)
                self.assertEqual(wf.final_result.evidence_refs, wf.accepted)
                self.assertIn('Copy workflow.completed_task_ids', context['finalization_policy'])
                self.assertEqual(context['accepted_submissions'], [
                    {'task_id': s.task_id, 'submission_id': s.id,
                     'output_version': s.version, 'evidence_digest': s.digest}
                    for s in wf.submissions])

    def test_missing_task_or_evidence_rejected_for_one_and_multiple_tasks(self):
        for count in (1, 3):
            for field in ('completed_task_ids', 'evidence_refs'):
                with self.subTest(tasks=count, field=field):
                    runner, _ = self.run_fixture(tasks=count,
                        mutation=lambda out, requests: out[field].pop())
                    self.assertEqual(runner.run.status, RunStatus.WAITING_FOR_USER)
                    self.assertIsNone(runner.run.workflow.final_result)
                    self.assertIn('final result must reference all accepted tasks and evidence',
                                  runner.run.workflow.blocked_reason)

    def test_six_successful_calls_can_still_fail_final_reference_validation(self):
        # Reproduce the observed failure shape; the original live payload was not retained.
        runner, _ = self.run_fixture(mutation=lambda out, requests:
            out.update(evidence_refs=list(out['completed_task_ids'])))
        wf = runner.run.workflow
        self.assertEqual(len(wf.call_records), 6)
        self.assertTrue(all(c.attempt == 1 and c.error_type is None for c in wf.call_records))
        self.assertEqual(len(wf.reviews), 1)
        self.assertEqual(runner.run.status, RunStatus.WAITING_FOR_USER)
        self.assertIn('final result must reference all accepted tasks and evidence', wf.blocked_reason)

    def test_revision_final_context_contains_only_current_accepted_submission(self):
        runner, provider = self.run_fixture(verdicts=('FAIL', 'PASS'))
        wf = runner.run.workflow
        self.assertEqual(runner.run.status, RunStatus.COMPLETED)
        self.assertEqual(provider.requests[-1].context['workflow']['evidence_refs'], [wf.submissions[-1].id])
        self.assertNotIn(wf.submissions[0].id, wf.final_result.evidence_refs)
        self.assertEqual(wf.final_result.evidence_refs, (wf.submissions[-1].id,))

    def test_stale_submission_and_raw_evidence_are_rejected(self):
        for raw in (False, True):
            with self.subTest(raw_evidence=raw):
                def mutate(out, requests):
                    old_review = next(q for q in requests if q.context['workflow']['phase'] == 'review')
                    out['evidence_refs'] = ([old_review.context['workflow']['evidence'][0]] if raw
                        else [old_review.context['submission']['id']])
                runner, _ = self.run_fixture(verdicts=('FAIL', 'PASS'), mutation=mutate)
                self.assertEqual(runner.run.status, RunStatus.WAITING_FOR_USER)
                self.assertIsNone(runner.run.workflow.final_result)

    def test_stale_acceptance_history_cannot_enter_final_manifest(self):
        runner, _ = self.run_fixture(verdicts=('FAIL', 'PASS'))
        run = runner.run
        corrupt = replace(run, workflow=replace(run.workflow,
            accepted=tuple(s.id for s in run.workflow.submissions)))
        with self.assertRaisesRegex(ValueError, 'noncurrent submissions'):
            runner._final_manifest(runner.store.get_project('demo'), corrupt)

    def test_schema_requires_and_explains_exact_reference_fields(self):
        schema = schema_for_output('final_result.v1')
        for field in ('completed_task_ids', 'evidence_refs'):
            self.assertIn(field, schema['required'])
            self.assertIn('workflow.' + field, schema['properties'][field]['description'])
        self.assertIn('accepted submission IDs', schema['properties']['evidence_refs']['description'])
        self.assertEqual(schema['properties']['status']['enum'], ['completed'])
