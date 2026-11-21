"""M7.3 committed graph trace, Inspector projection and replay contracts."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from fastapi.testclient import TestClient

from app.api.events import event_stream
from app.api.service import ControlService
from app.main import create_app
from app.agents.contracts import Requirement
from app.dev.workflow import ScriptedWorkflowProvider
from app.domain.agents import AgentKind, default_agent_definitions
from app.domain.commands import CommandProfile
from app.domain.projects import ProjectState, RunStatus
from app.orchestration.graph_observability import redact_text
from app.orchestration.orchestrators import LangGraphOrchestrator, LegacyOrchestrator
from app.persistence.memory import InMemoryStateStore
from app.permissions.policy import WorkspacePolicy
from app.tools.gateway import WorkspaceToolGateway
from tests.test_m71_parity import AdaptedProvider


class M73Tests(unittest.TestCase):
    def fixture(self, *, graph=True, provider=None, definitions=None):
        store = InMemoryStateStore()
        store.create_project(ProjectState('trace', 'Trace', 'Produce synthetic evidence',
            requirements=(Requirement('req', 'Document an artifact', ('Synthetic output is documented',)),)))
        run = store.create_run('trace', run_id='run')
        provider = provider or ScriptedWorkflowProvider()
        cls = LangGraphOrchestrator if graph else LegacyOrchestrator
        runner = cls(store, 'trace', run.id, provider, definitions=definitions)
        runner.initialize()
        return runner, provider

    def service(self, runner):
        service = ControlService(runner.store, lambda *_: runner)
        service.runners[(runner.project_id, runner.run_id)] = runner
        return service

    def test_node_lifecycle_correlation_and_domain_order(self):
        runner, provider = self.fixture()
        runner.run_until_stopped()
        runner.approve()
        runner.run_until_stopped()
        events = runner.store.events('trace')
        starts = [e for e in events if e.type == 'graph.node_started']
        ends = [e for e in events if e.type == 'graph.node_completed']
        self.assertEqual(len(starts), len(ends))
        self.assertEqual(len(starts), 6)
        self.assertEqual([e.payload['node_name'] for e in starts],
            ['manager_plan', 'manager_assignment', 'developer', 'reviewer',
             'accept_submission', 'manager_assignment'])
        self.assertTrue(all(e.project_id == 'trace' and e.run_id == 'run' and
            e.payload['invocation_id'] == e.correlation_id for e in starts + ends))
        self.assertTrue(all(e.sequence > 0 and e.event_id for e in events))
        self.assertEqual(len({e.event_id for e in events}), len(events))
        for start, end in zip(starts, ends):
            self.assertLess(start.sequence, end.sequence)
            self.assertEqual(start.payload['invocation_id'], end.payload['invocation_id'])
            committed = [e for e in events if start.sequence < e.sequence < end.sequence
                         and e.type in end.payload['committed_event_types']]
            self.assertTrue(committed)
        self.assertLess(next(e.sequence for e in events if e.type == 'review.completed'),
                        next(e.sequence for e in events if e.type == 'task.accepted'))
        self.assertEqual(len(runner.run.workflow.call_records), len(provider.requests))

    def test_full_fail_revision_pass_trace_with_two_approved_tests(self):
        with TemporaryDirectory(prefix='m73-trace-') as temp:
            root = Path(temp)
            (root / 'greeting.txt').write_text('hello\n')
            (root / 'test.py').write_text("from pathlib import Path\nassert Path('greeting.txt').read_text() == 'hello world revised\\n'\nprint('PASS')\n")
            store = InMemoryStateStore()
            store.create_project(ProjectState('workspace', 'Trace', 'Update greeting', workspace_root=str(root),
                requirements=(Requirement('greeting', 'Expand greeting', ('Greeting contains hello world',)),)))
            run = store.create_run('workspace', run_id='run')
            profile = CommandProfile('tests', str(Path(sys.executable).resolve()), ('-I', '-B', 'test.py'), True)
            gateway = WorkspaceToolGateway(WorkspacePolicy(root), command_profiles=(profile,))
            provider = AdaptedProvider(('FAIL', 'PASS'), command=True)
            runner = LangGraphOrchestrator(store, 'workspace', run.id, provider, gateway=gateway)
            runner.initialize()
            runner.run_until_stopped()
            runner.approve()
            decisions = 0
            while runner.run.active and decisions < 3:
                runner.run_until_stopped()
                pending = runner.run.workflow.pending_permissions
                if not pending:
                    break
                runner.controls.resolve_command(pending[0], approved=True, reason='M7.3 fixture approval')
                decisions += 1
            runner.run_until_stopped()
            self.assertEqual(runner.run.status, RunStatus.COMPLETED)
            self.assertEqual(decisions, 2)
            wf = runner.run.workflow
            self.assertEqual([c.outcome for c in wf.command_results], ['failed', 'succeeded'])
            self.assertEqual([r.result.verdict.value for r in wf.reviews], ['FAIL', 'PASS'])
            self.assertEqual([r.submission_id for r in wf.reviews], [s.id for s in wf.submissions])
            self.assertEqual(len(wf.revisions), 1)
            self.assertEqual(len(wf.call_records), len(provider.requests))
            inspection = self.service(runner).inspection('workspace', 'run', include_agent_debug=True)
            dev = inspection['agent_debug']['developer']
            reviewer = inspection['agent_debug']['reviewer']
            manager = inspection['agent_debug']['manager']
            trace_text = [row['text'] for row in dev['trace']]
            self.assertIn('Workflow started', trace_text)
            self.assertTrue(any('Tool request: read' in x for x in trace_text))
            self.assertTrue(any('Tool request: edit' in x for x in trace_text))
            self.assertIn('Waiting for command approval', trace_text)
            self.assertIn('Permission approved', trace_text)
            self.assertIn('Developer continuation resumed', trace_text)
            self.assertIn('Command/test result: failed', trace_text)
            self.assertIn('Command/test result: succeeded', trace_text)
            self.assertEqual([x['decision'] for x in reviewer['decisions']],
                ['Reviewer FAIL', 'Reviewer PASS'])
            self.assertEqual([x['refs'][0] for x in reviewer['decisions']], [s.id for s in wf.submissions])
            self.assertTrue(any('revision committed' in x['text'] for x in manager['trace']))
            self.assertEqual(dev['usage']['llmCalls'], inspection['usage']['per_agent']['developer']['provider_calls'])
            self.assertEqual(len({x['id'] for x in dev['trace']}), len(dev['trace']))
            self.assertTrue(all(x['refs']['run_id'] == 'run' and x['refs']['sequence'] > 0 for x in dev['trace']))

    def test_permission_denial_trace_has_no_command_result(self):
        with TemporaryDirectory(prefix='m73-deny-') as temp:
            root = Path(temp)
            (root / 'greeting.txt').write_text('hello\n')
            (root / 'test.py').write_text("print('PASS')\n")
            store = InMemoryStateStore()
            store.create_project(ProjectState('workspace', 'Trace', 'Update greeting', workspace_root=str(root),
                requirements=(Requirement('greeting', 'Expand greeting', ('Greeting contains hello world',)),)))
            run = store.create_run('workspace', run_id='run')
            profile = CommandProfile('tests', str(Path(sys.executable).resolve()), ('-I', '-B', 'test.py'), True)
            provider = AdaptedProvider(command=True)
            runner = LangGraphOrchestrator(store, 'workspace', run.id, provider,
                gateway=WorkspaceToolGateway(WorkspacePolicy(root), command_profiles=(profile,)))
            runner.initialize()
            runner.run_until_stopped()
            runner.approve()
            runner.run_until_stopped()
            self.assertEqual(runner.run.status, RunStatus.WAITING_FOR_USER)
            approval = runner.run.workflow.pending_permissions[0]
            runner.controls.resolve_command(approval, approved=False, reason='M7.3 fixture denial')
            runner.run_until_stopped()
            inspection = self.service(runner).inspection('workspace', 'run', include_agent_debug=True)
            trace = [row['text'] for row in inspection['agent_debug']['developer']['trace']]
            self.assertIn('Waiting for command approval', trace)
            self.assertIn('Permission denied', trace)
            self.assertFalse(any('Command execution started' in row for row in trace))
            self.assertFalse(runner.run.workflow.command_results)

    def test_replay_keeps_event_and_trace_identity(self):
        runner, _ = self.fixture()
        runner.run_until_stopped()
        runner.approve()
        runner.run_until_stopped()
        service = self.service(runner)
        all_events = runner.store.events('trace')
        cursor = all_events[len(all_events) // 2].sequence
        expected = [e for e in all_events if e.sequence > cursor]
        async def collect():
            async def connected(): return False
            stream = event_stream(service, 'trace', cursor, connected, poll=0.001)
            frames = [await anext(stream) for _ in expected]
            await stream.aclose()
            return [json.loads(frame.split('data: ', 1)[1].split('\n', 1)[0]) for frame in frames]
        replay = asyncio.run(collect())
        self.assertEqual([x['event_id'] for x in replay], [e.event_id for e in expected])
        self.assertEqual([x['sequence'] for x in replay], [e.sequence for e in expected])
        first = service.inspection('trace', 'run', include_agent_debug=True)['agent_debug']['developer']['trace']
        second = service.inspection('trace', 'run', include_agent_debug=True)['agent_debug']['developer']['trace']
        self.assertEqual(first, second)
        self.assertEqual(len({row['id'] for row in first}), len(first))

    def test_inspection_http_exposes_committed_graph_projection(self):
        runner, _ = self.fixture()
        runner.run_until_stopped()
        runner.approve()
        runner.run_until_stopped()
        with TestClient(create_app(store=runner.store, runner_factory=lambda *_: runner),
                        base_url='http://localhost') as client:
            response = client.get('/projects/trace/runs/run/inspection?agent_debug=true')
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(set(data['agent_debug']), {'manager', 'developer', 'reviewer'})
            self.assertEqual(data['agent_debug']['reviewer']['decisions'][0]['decision'], 'Reviewer PASS')
            self.assertEqual(data['agent_debug']['developer']['source'], 'backend')

    def test_legacy_inspection_and_redacted_prompt(self):
        definitions = default_agent_definitions()
        definitions[AgentKind.MANAGER] = replace(definitions[AgentKind.MANAGER],
            system_instructions='Use Bearer abcdefghijklmnop and password=hunter2-secret safely')
        runner, _ = self.fixture(graph=False, definitions=definitions)
        runner.run_until_stopped()
        inspection = self.service(runner).inspection('trace', 'run', include_agent_debug=True)
        self.assertTrue(inspection['agent_debug']['manager']['trace'])
        self.assertFalse(any(e.type.startswith('graph.') for e in runner.store.events('trace')))
        encoded = json.dumps(inspection)
        self.assertNotIn('abcdefghijklmnop', encoded)
        self.assertNotIn('hunter2-secret', encoded)
        self.assertIn('[REDACTED]', inspection['agent_debug']['manager']['prompt']['instructions'])
        self.assertEqual(redact_text('sk-proj-FAKEFAKEFAKE1234567890'), '[REDACTED]')

    def test_malformed_reviewer_has_failed_node_not_acceptance(self):
        class Malformed(ScriptedWorkflowProvider):
            def complete(self, request):
                response = super().complete(request)
                if request.context['workflow']['phase'] == 'review':
                    return replace(response, output={**response.output, 'verdict': 'MAYBE'})
                return response
        runner, _ = self.fixture(provider=Malformed())
        runner.run_until_stopped()
        runner.approve()
        runner.run_until_stopped()
        events = runner.store.events('trace')
        self.assertEqual(runner.run.status, RunStatus.WAITING_FOR_USER)
        self.assertTrue(any(e.type == 'graph.node_failed' and e.payload['node_name'] == 'reviewer' for e in events))
        self.assertFalse(any(e.type in {'task.accepted', 'run.completed'} for e in events))
        self.assertFalse(runner.run.workflow.reviews)
