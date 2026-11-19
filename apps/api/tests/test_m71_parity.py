"""Domain-level comparison of the trusted legacy and adapted Developer paths."""
from dataclasses import replace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from app.dev.workspace import WorkspaceFixtureProvider, make_workspace_runner, request
from app.dev.workflow import ScriptedWorkflowProvider
from app.api.service import ControlService
from app.domain.commands import CommandProfile
from app.domain.projects import RunStatus
from app.providers.base import ProviderCapabilities, ProviderResponse, ProviderToolCall, UsageSnapshot


class LegacyProvider(WorkspaceFixtureProvider):
    def complete(self, req):
        if req.context['workflow']['phase'] == 'review':
            return ScriptedWorkflowProvider.complete(self, req)
        return super().complete(req)


class AdaptedProvider(LegacyProvider):
    capabilities = ProviderCapabilities(structured_outputs=True, tools=True, usage=True)

    def __init__(self, verdicts=('PASS',), *, command=False):
        super().__init__(verdicts)
        self.command = command

    def complete(self, req):
        if req.context['workflow']['phase'] != 'develop':
            return super().complete(req)
        self.requests.append(req)
        results = req.context.get('tool_results', [])
        if not results:
            return ProviderResponse({}, req.model, f'file-read-{len(self.requests)}',
                (ProviderToolCall('read_file', {'path': 'greeting.txt'}),), UsageSnapshot(10, 5))
        last = results[-1]['result']
        if last.get('operation') == 'read':
            content = last['content']
            old = 'hello world' if content == 'hello world\n' else 'hello'
            new = 'hello world revised' if old == 'hello world' else 'hello world'
            return ProviderResponse({}, req.model, f'file-edit-{len(self.requests)}',
                (ProviderToolCall('edit_file', {'path': 'greeting.txt', 'old_text': old,
                    'new_text': new, 'expected_hash': last['content_hash']}),),
                UsageSnapshot(10, 5))
        if self.command and last.get('operation') == 'edit':
            return ProviderResponse({}, req.model, f'test-request-{len(self.requests)}',
                (ProviderToolCall('run_approved_command', {'profile': 'tests'}),), UsageSnapshot(10, 5))
        # WorkspaceFixtureProvider's role output is the same structured result
        # used by the legacy fixture. Remove the manual request append above.
        self.requests.pop()
        return super().complete(req)


class M71ParityTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix='m71-parity-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def pair(self, *, command=False, verdicts=('PASS',), deny=False, malformed=False,
             cancel=False):
        self.pair_number = getattr(self, 'pair_number', 0) + 1
        outcomes = []
        for adapted in (False, True):
            root = self.base / f'pair-{self.pair_number}' / ('adapted' if adapted else 'legacy')
            root.parent.mkdir(exist_ok=True)
            root.mkdir()
            (root / 'greeting.txt').write_text('hello\n')
            (root / 'test.py').write_text("from pathlib import Path\nassert Path('greeting.txt').read_text().startswith('hello world')\nprint('PASS')\n")
            profile = CommandProfile('tests', str(Path(sys.executable).resolve()), ('-I', '-B', 'test.py'), True)
            base_class = AdaptedProvider if adapted else LegacyProvider
            if malformed:
                class Malformed(base_class):
                    def complete(self, req):
                        response = super().complete(req)
                        if req.context['workflow']['phase'] == 'develop' and not response.tool_calls:
                            return replace(response, output={})
                        return response
                provider_type = Malformed
            else:
                provider_type = base_class
            provider = provider_type(verdicts, command=command) if adapted else provider_type(verdicts)
            runner = make_workspace_runner(root, provider=provider, command_profiles=(profile,))
            while runner.run.active and runner.run.status in {RunStatus.RUNNING, RunStatus.WAITING_FOR_USER}:
                if runner.run.status is RunStatus.WAITING_FOR_USER:
                    pending = runner.run.workflow.pending_permissions
                    if not pending:
                        break
                    if cancel:
                        runner.controls.cancel()
                        break
                    runner.controls.resolve_command(pending[0], approved=not deny, reason='Deterministic comparison')
                    continue
                if runner.run.phase == 'develop' and not adapted:
                    read = runner.file_tool(request(runner, 'read', path='greeting.txt'))
                    old = 'hello world' if read.content == 'hello world\n' else 'hello'
                    new = 'hello world revised' if old == 'hello world' else 'hello world'
                    runner.file_tool(request(runner, 'edit', path='greeting.txt',
                        expected_hash=read.content_hash, old_text=old, new_text=new))
                    if command:
                        req = runner.workspace_gateway.command_request('tests',
                            attempt_id=runner.run.workflow.attempts[-1].id,
                            generation=runner.run.execution_generation)
                        approval = runner.request_command(req)
                        if cancel:
                            runner.controls.cancel()
                            break
                        runner.controls.resolve_command(approval.id, approved=not deny,
                            reason='Deterministic comparison')
                        if not deny:
                            runner.command_tool(req, approval.id)
                runner.step()
            outcomes.append((runner, provider, root))
        return outcomes

    @staticmethod
    def domain(runner):
        run = runner.run
        wf = run.workflow
        project = runner.store.get_project(runner.project_id)
        return {'status': run.status.value, 'task': project.task(run.task_ids[0]).status.value,
            'submission_versions': [s.version for s in wf.submissions],
            'captured': [s.files.files[0].content for s in wf.submissions],
            'review_verdicts': [r.result.verdict.value for r in wf.reviews],
            'review_links': [r.submission_id == s.id for r, s in zip(wf.reviews, wf.submissions)],
            'revisions': len(wf.revisions), 'attempts': len(wf.attempts),
            'command_outcomes': [c.outcome for c in wf.command_results],
            'permission_outcomes': [a.status for a in runner.store.approvals(runner.project_id, runner.run_id)],
            'tokens': sum(c.usage.total_tokens for c in wf.call_records if c.usage),
            'call_records': len(wf.call_records)}

    def test_a_file_only_success_and_f_revision_parity(self):
        for verdicts, rounds in ((('PASS',), 1), (('FAIL', 'PASS'), 2)):
            with self.subTest(verdicts=verdicts):
                pair = self.pair(verdicts=verdicts, command=rounds == 2)
                legacy, adapted = (self.domain(item[0]) for item in pair)
                for key in ('status', 'task', 'submission_versions', 'captured',
                            'review_verdicts', 'review_links', 'revisions', 'attempts'):
                    self.assertEqual(legacy[key], adapted[key], key)
                self.assertEqual(legacy['status'], 'completed')
                self.assertEqual(len(legacy['submission_versions']), rounds)
                self.assertEqual(len(pair[1][0].run.workflow.submissions), rounds)
                self.assertEqual(len(pair[1][0].run.workflow.command_results),
                                 2 if rounds == 2 else 0)
                self.assertEqual([a.number for a in pair[1][0].run.workflow.attempts],
                                 list(range(1, rounds + 1)))
                self.assertEqual(len({s.id for s in pair[1][0].run.workflow.submissions}), rounds)
                self.assertEqual([r.submission_id for r in pair[1][0].run.workflow.reviews],
                    [s.id for s in pair[1][0].run.workflow.submissions])
                self.assertEqual(len(pair[1][0].run.workflow.call_records), len(pair[1][1].requests))

    def test_b_approved_command_and_c_denial_parity(self):
        for deny in (False, True):
            with self.subTest(deny=deny):
                pair = self.pair(command=True, deny=deny)
                legacy, adapted = (self.domain(item[0]) for item in pair)
                for key in ('status', 'task', 'submission_versions', 'captured',
                            'review_verdicts', 'command_outcomes', 'permission_outcomes'):
                    self.assertEqual(legacy[key], adapted[key], key)
                self.assertEqual(adapted['permission_outcomes'], ['denied' if deny else 'consumed'])
                self.assertEqual(len(pair[1][0].run.workflow.command_results), 0 if deny else 1)
                self.assertEqual(len(pair[1][0].run.workflow.call_records), len(pair[1][1].requests))
                for runner, _, _ in pair:
                    audits = runner.store.tool_history(runner.project_id, runner.run_id)
                    self.assertEqual([a.action for a in audits if hasattr(a, 'action')][:2],
                                     ['request', 'decision'])
                    if not deny:
                        command_result = runner.run.workflow.command_results[0]
                        self.assertEqual((command_result.stdout, command_result.stderr), ('PASS\n', ''))
                        evidence = json.loads(runner.run.workflow.submissions[0].evidence[0])
                        self.assertTrue(evidence['tests'][0]['passed'])
                        self.assertFalse(evidence['tests'][0]['stale'])
                        self.assertEqual(evidence['tests'][0]['workspace_version'],
                                         command_result.workspace_before)

    def test_d_malformed_output_and_e_cancellation_parity(self):
        pair = self.pair(malformed=True)
        for runner, provider, _ in pair:
            self.assertEqual(runner.run.status, RunStatus.WAITING_FOR_USER)
            self.assertFalse(runner.run.workflow.submissions)
            self.assertIn('technical failure', runner.run.workflow.blocked_reason)
            self.assertEqual(len(runner.run.workflow.call_records), len(provider.requests))
            self.assertLessEqual(len([q for q in provider.requests
                if q.context['workflow']['phase'] == 'develop']), 8)
        pair = self.pair(command=True, cancel=True)
        for runner, provider, _ in pair:
            self.assertEqual(runner.run.status, RunStatus.CANCELED)
            self.assertFalse(runner.run.workflow.command_results)
            self.assertFalse(runner.run.workflow.submissions)
            self.assertEqual(len(runner.run.workflow.call_records), len(provider.requests))

    def test_inspector_trace_and_replay_contract(self):
        runner, provider, _ = self.pair(command=True)[1]
        service = ControlService(runner.store, lambda *_: runner)
        service.runners[(runner.project_id, runner.run_id)] = runner
        inspection = service.inspection(runner.project_id, runner.run_id)
        events = runner.store.events(runner.project_id)
        relevant = [e for e in events if e.run_id == runner.run_id]
        names = [e.type for e in relevant]
        ordered = ['task.assigned', 'developer.waiting_for_approval',
            'command.permission_decided', 'command.launch', 'command.completed',
            'submission.admitted', 'review.completed', 'task.accepted']
        self.assertEqual([names.index(name) for name in ordered],
            sorted(names.index(name) for name in ordered))
        self.assertEqual(len({e.sequence for e in events}), len(events))
        cursor = relevant[0].sequence
        replay = runner.store.event_page(runner.project_id, cursor, 100)
        self.assertTrue(all(e.sequence > cursor for e in replay))
        self.assertEqual(len({e.sequence for e in replay}), len(replay))
        self.assertTrue(any(t.operation == 'read' for t in runner.store.tool_history(runner.project_id, runner.run_id)
                            if hasattr(t, 'operation')))
        self.assertTrue(any(t.action == 'request' for t in runner.store.tool_history(runner.project_id, runner.run_id)
                            if hasattr(t, 'action')))
        self.assertEqual(inspection['usage']['provider_calls'], len(runner.run.workflow.call_records))
        self.assertEqual(len(runner.run.workflow.call_records), len(provider.requests))
        self.assertEqual(len(runner.run.workflow.submissions), 1)

        revision_runner, revision_provider, _ = self.pair(command=True,
            verdicts=('FAIL', 'PASS'))[1]
        revision_events = [e.type for e in revision_runner.store.events(revision_runner.project_id)
                           if e.run_id == revision_runner.run_id]
        self.assertEqual([revision_events.count(name) for name in
            ('submission.admitted', 'review.completed', 'revision.requested', 'task.accepted')],
            [2, 2, 1, 1])
        first_review = revision_events.index('review.completed')
        revision = revision_events.index('revision.requested')
        second_submission = revision_events.index('submission.admitted', first_review)
        second_review = revision_events.index('review.completed', second_submission)
        self.assertLess(first_review, revision)
        self.assertLess(revision, second_submission)
        self.assertLess(second_submission, second_review)
        self.assertEqual([r.submission_id for r in revision_runner.run.workflow.reviews],
            [s.id for s in revision_runner.run.workflow.submissions])
        self.assertEqual(len(revision_runner.run.workflow.call_records), len(revision_provider.requests))


if __name__ == '__main__':
    unittest.main()
