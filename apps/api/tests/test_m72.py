"""M7.2 isolated legacy/graph comparison over the same domain services."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import sys
import unittest

from app.agents.contracts import Requirement
from app.dev.workflow import ScriptedWorkflowProvider
from app.domain.commands import CommandProfile
from app.domain.projects import ProjectState, RunStatus
from app.orchestration.orchestrators import LangGraphOrchestrator, LegacyOrchestrator, make_orchestrator
from app.persistence.memory import InMemoryStateStore
from app.persistence.sqlite import SQLiteStateStore
from app.permissions.policy import WorkspacePolicy
from app.tools.gateway import WorkspaceToolGateway
from tests.test_m71_parity import AdaptedProvider


class M72Tests(unittest.TestCase):
    def synthetic(self, kind, verdicts=('PASS',), *, tasks=1, hook=None, provider_type=ScriptedWorkflowProvider):
        store = InMemoryStateStore()
        store.create_project(ProjectState('comparison', 'Comparison', 'Produce synthetic evidence',
            requirements=(Requirement('req', 'Document a synthetic artifact', ('Synthetic output is documented',)),)))
        run = store.create_run('comparison', run_id='run')
        provider = provider_type(verdicts, tasks=tasks, hook=hook)
        runner = make_orchestrator(kind, store, 'comparison', run.id, provider)
        runner.initialize()
        return runner, provider

    def workspace(self, kind, root, *, deny=False, restart=False):
        store = InMemoryStateStore()
        store.create_project(ProjectState('workspace', 'Comparison', 'Update greeting', workspace_root=str(root),
            requirements=(Requirement('greeting', 'Expand greeting', ('Greeting contains hello world',)),)))
        run = store.create_run('workspace', run_id='run')
        profile = CommandProfile('tests', str(Path(sys.executable).resolve()), ('-I', '-B', 'test.py'), True)
        gateway = WorkspaceToolGateway(WorkspacePolicy(root), command_profiles=(profile,))
        provider = AdaptedProvider(command=True)
        runner = make_orchestrator(kind, store, 'workspace', run.id, provider, gateway=gateway)
        runner.initialize()
        runner.run_until_stopped()
        runner.approve()
        runner.run_until_stopped()
        self.assertEqual(runner.run.status, RunStatus.WAITING_FOR_USER)
        self.assertEqual(len(runner.run.workflow.pending_permissions), 1)
        if restart:
            gateway = WorkspaceToolGateway(WorkspacePolicy(root), command_profiles=(profile,))
            runner = make_orchestrator(kind, store, 'workspace', run.id, provider, gateway=gateway)
            self.assertEqual(runner.run.status, RunStatus.WAITING_FOR_USER)
        approval = runner.run.workflow.pending_permissions[0]
        runner.controls.resolve_command(approval, approved=not deny, reason='M7.2 fixture')
        runner.run_until_stopped()
        return runner, provider

    @staticmethod
    def outcome(runner):
        run = runner.run
        wf = run.workflow
        events = tuple(e.type for e in runner.store.events(runner.project_id) if e.run_id == run.id)
        return (run.status.value, run.phase,
            tuple(runner.store.get_project(runner.project_id).task(t).status.value for t in run.task_ids),
            tuple(s.version for s in wf.submissions),
            tuple(x.result.verdict.value for x in wf.reviews),
            tuple(r.submission_id == s.id for r, s in zip(wf.reviews, wf.submissions)),
            len(wf.revisions), len(wf.attempts), len(wf.accepted),
            len(wf.call_records), wf.llm_calls,
            sum(c.usage.total_tokens for c in wf.call_records if c.usage),
            sum((c.estimated_cost.amount for c in wf.call_records if c.estimated_cost), Decimal(0)),
            tuple(c.purpose for c in wf.call_records),
            events)

    def test_graph_construction_and_explicit_default(self):
        legacy, _ = self.synthetic('legacy')
        graph, _ = self.synthetic('langgraph')
        self.assertIsInstance(legacy, LegacyOrchestrator)
        self.assertIsInstance(graph, LangGraphOrchestrator)
        self.assertEqual(set(graph.graph.get_graph().nodes) - {'__start__', '__end__'},
            {'manager_plan', 'manager_assignment', 'developer', 'reviewer',
             'accept_submission', 'manager_revision', 'finalize'})
        with self.assertRaisesRegex(ValueError, 'orchestrator must'):
            make_orchestrator('other', graph.store, graph.project_id, graph.run_id, graph.provider)

    def test_a_b_c_h_domain_and_accounting_parity(self):
        for verdicts, tasks in ((('PASS',), 1), (('FAIL', 'PASS'), 1), (('FAIL',), 1), (('PASS',), 3)):
            with self.subTest(verdicts=verdicts, tasks=tasks):
                pair = [self.synthetic(kind, verdicts, tasks=tasks) for kind in ('legacy', 'langgraph')]
                for runner, _ in pair:
                    runner.run_until_stopped()
                    runner.approve()
                    runner.run_until_stopped()
                self.assertEqual(self.outcome(pair[0][0]), self.outcome(pair[1][0]))
                for runner, provider in pair:
                    wf = runner.run.workflow
                    self.assertEqual(len(wf.call_records), len(provider.requests))
                    self.assertEqual([r.submission_id for r in wf.reviews], [s.id for s in wf.submissions])
                    if tasks == 3:
                        self.assertEqual(tuple(a.task_id for a in wf.attempts), runner.run.task_ids)
                    if verdicts == ('FAIL',):
                        self.assertEqual(len(wf.reviews), 3)
                        self.assertEqual(runner.run.status, RunStatus.WAITING_FOR_USER)
                    else:
                        self.assertEqual(runner.run.status, RunStatus.COMPLETED)
                        self.assertEqual(set(wf.final_result.evidence_refs), set(wf.accepted))

    def test_d_e_approval_and_denial_resume_once(self):
        for deny in (False, True):
            with self.subTest(deny=deny), TemporaryDirectory(prefix='m72-workspace-') as parent:
                outcomes = []
                for kind in ('legacy', 'langgraph'):
                    root = Path(parent) / kind
                    root.mkdir()
                    (root / 'greeting.txt').write_text('hello\n')
                    (root / 'test.py').write_text("from pathlib import Path\nassert Path('greeting.txt').read_text().startswith('hello world')\nprint('PASS')\n")
                    runner, provider = self.workspace(kind, root, deny=deny)
                    self.assertEqual(len(runner.run.workflow.call_records), len(provider.requests))
                    self.assertEqual(len(runner.run.workflow.command_results), 0 if deny else 1)
                    self.assertEqual(len([o for o in runner.store.operations(runner.project_id, runner.run_id)
                        if o.kind == 'command' and o.stage.value == 'settled']), 0 if deny else 1)
                    before = len(provider.requests)
                    runner.run_until_stopped()
                    self.assertEqual(len(provider.requests), before)
                    outcomes.append((self.outcome(runner),
                        tuple(a.status for a in runner.store.approvals(runner.project_id, runner.run_id)),
                        (root / 'greeting.txt').read_text()))
                self.assertEqual(outcomes[0], outcomes[1])

    def test_approval_boundary_survives_new_graph_instance(self):
        with TemporaryDirectory(prefix='m72-resume-') as parent:
            root = Path(parent)
            (root / 'greeting.txt').write_text('hello\n')
            (root / 'test.py').write_text("from pathlib import Path\nassert Path('greeting.txt').read_text().startswith('hello world')\nprint('PASS')\n")
            runner, provider = self.workspace('langgraph', root, restart=True)
            self.assertEqual(runner.run.status, RunStatus.COMPLETED)
            self.assertEqual(len(runner.run.workflow.command_results), 1)
            self.assertEqual(len(runner.run.workflow.call_records), len(provider.requests))

    def test_f_pause_resume_and_committed_submission_restart(self):
        runner, provider = self.synthetic('langgraph')
        runner.run_until_stopped()
        runner.approve()
        runner.step()  # assignment
        runner.controls.pause()
        before = len(provider.requests)
        runner.run_until_stopped()
        self.assertEqual(len(provider.requests), before)
        runner.controls.resume()
        runner.step()  # durable submission
        self.assertEqual(len(runner.run.workflow.submissions), 1)
        fresh = LangGraphOrchestrator(runner.store, runner.project_id, runner.run_id, provider)
        fresh.run_until_stopped()
        self.assertEqual(fresh.run.status, RunStatus.COMPLETED)
        self.assertEqual(len(fresh.run.workflow.submissions), 1)
        self.assertEqual(len(fresh.run.workflow.reviews), 1)

    def test_sqlite_committed_node_boundary(self):
        with TemporaryDirectory(prefix='m72-sqlite-') as parent:
            path = Path(parent) / 'state.db'
            provider = ScriptedWorkflowProvider()
            with SQLiteStateStore(path) as store:
                store.create_project(ProjectState('comparison', 'Comparison', 'Produce synthetic evidence',
                    requirements=(Requirement('req', 'Document a synthetic artifact',
                        ('Synthetic output is documented',)),)))
                run = store.create_run('comparison', run_id='run')
                graph = LangGraphOrchestrator(store, 'comparison', run.id, provider)
                graph.initialize()
                graph.run_until_stopped()
                graph.approve()
                graph.step()
                graph.step()
                self.assertEqual(len(graph.run.workflow.submissions), 1)
            with SQLiteStateStore(path) as store:
                graph = LangGraphOrchestrator(store, 'comparison', 'run', provider)
                self.assertEqual(graph.run.status, RunStatus.PAUSED)
                graph.controls.resume()
                graph.run_until_stopped()
                self.assertEqual(graph.run.status, RunStatus.COMPLETED)
                self.assertEqual(len(graph.run.workflow.submissions), 1)
                self.assertEqual(len(graph.run.workflow.reviews), 1)

    def test_g_canceled_late_result_and_stale_graph_snapshot(self):
        entered, release = Event(), Event()
        def hook(request):
            if request.context['workflow']['phase'] == 'develop':
                entered.set()
                release.wait(5)
        runner, _ = self.synthetic('langgraph', hook=hook)
        runner.run_until_stopped()
        runner.approve()
        runner.step()
        stale = runner._snapshot()
        thread = Thread(target=runner.step)
        thread.start()
        self.assertTrue(entered.wait(3))
        runner.controls.cancel()
        release.set()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(runner._operation(stale)['progressed'])
        self.assertEqual(runner.run.status, RunStatus.CANCELED)
        self.assertFalse(runner.run.workflow.submissions)
        self.assertFalse(runner.run.workflow.accepted)

    def test_malformed_result_blocks_without_review_or_duplicate_transition(self):
        class Malformed(ScriptedWorkflowProvider):
            def complete(self, request):
                response = super().complete(request)
                if request.context['workflow']['phase'] == 'review':
                    return replace(response, output={**response.output, 'verdict': 'MAYBE'})
                return response
        runner, provider = self.synthetic('langgraph', provider_type=Malformed)
        runner.run_until_stopped()
        runner.approve()
        runner.run_until_stopped()
        self.assertEqual(runner.run.status, RunStatus.WAITING_FOR_USER)
        self.assertEqual(len(runner.run.workflow.submissions), 1)
        self.assertFalse(runner.run.workflow.reviews)
        self.assertEqual(len(runner.run.workflow.call_records), len(provider.requests))
        before = self.outcome(runner)
        runner.run_until_stopped()
        self.assertEqual(self.outcome(runner), before)
