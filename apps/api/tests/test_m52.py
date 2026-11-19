"""M5.2 read projections and future-run configuration, without workflow changes."""
from dataclasses import replace
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import create_app
from app.api.schemas import AgentSettings
from app.api.service import ControlService, public
from app.domain.agents import AgentKind
from app.domain.recovery import ExecutionOperation, checkpoint, OperationStage
from app.dev.workflow import make_runner, approve_generated, ScriptedWorkflowProvider
from app.dev.workspace import make_workspace_runner, request
from app.orchestration.runner import WorkflowRunner
from app.persistence.sqlite import SQLiteStateStore


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'state.db'
        self.store = SQLiteStateStore(self.path)
        self.addCleanup(self.store.close)
        self.runner = make_runner(ScriptedWorkflowProvider(('FAIL', 'PASS')), store=self.store)
        approve_generated(self.runner)
        self.runner.run_until_stopped()
        self.service = ControlService(self.store, lambda s,p,r: WorkflowRunner(s,p,r,ScriptedWorkflowProvider()))
        self.pid, self.rid = self.runner.project_id, self.runner.run_id

    def settings_body(self, **changes):
        data = dict(expected_version=self.store.get_project(self.pid).version, kind='developer', name='Dev',
            role='Implementer', model='anthropic/test-model', system_instructions='Bounded implementation')
        return AgentSettings(**(data | changes))

    def test_recent_committed_events_are_bounded_ordered_and_run_scoped(self):
        events = self.service.inspection(self.pid, self.rid)['recent_events']
        self.assertTrue(events)
        self.assertLessEqual(len(events), 50)
        self.assertEqual([e['sequence'] for e in events], sorted(e['sequence'] for e in events))
        self.assertTrue(all(e['run_id'] == self.rid for e in events))
        self.assertEqual(len({e['sequence'] for e in events}), len(events))
        self.store.create_run(self.pid)
        self.assertEqual(self.service.inspection(self.pid, self.rid)['recent_events'], events)

    def test_usage_breakdown_and_replay_reads(self):
        before = self.service.inspection(self.pid, self.rid)['usage']
        self.assertEqual(before['input_tokens'], before['provider_calls'] * 10)
        self.assertEqual(before['output_tokens'], before['provider_calls'] * 5)
        self.assertEqual(before['cached_input_tokens'], 0)
        self.assertIsNone(before['estimated_cost'])
        self.assertEqual(before['reviews'], 2)
        self.assertEqual(set(before['per_agent']), {'manager','developer','reviewer'})
        for _ in range(3):
            self.assertEqual(self.service.inspection(self.pid, self.rid)['usage'], before)

    def test_attempts_exact_review_references_remain(self):
        wf = self.service.snapshot(self.pid).project['runs'][0]['workflow']
        self.assertEqual(len(wf['attempts']), 2)
        for review in wf['reviews']:
            submission = next(s for s in wf['submissions'] if s['id'] == review['submission_id'])
            self.assertEqual(submission['version'], review['submission_version'])
            self.assertTrue(review['result']['checks_not_performed'])
        self.assertEqual([r['result']['verdict'] for r in wf['reviews']], ['FAIL', 'PASS'])

    def test_settings_idempotent_and_durable(self):
        body = self.settings_body()
        first = self.service.configure(self.pid, body, 'settings-key')
        self.assertEqual(first, self.service.configure(self.pid, body, 'settings-key'))
        self.assertEqual(self.service.settings(self.pid)['agents'][1]['config_version'], 2)
        with SQLiteStateStore(self.path) as reopened:
            self.assertEqual(reopened.get_project(self.pid).agent_definitions[1].model, body.model)

    def test_settings_stale_version_rejected(self):
        from app.persistence.store import VersionConflictError
        body = self.settings_body()
        self.service.configure(self.pid, body, 'first')
        with self.assertRaises(VersionConflictError):
            self.service.configure(self.pid, body, 'second')

    def test_future_run_config_history_immutable(self):
        old = self.runner.run.workflow.agent_snapshots
        self.service.configure(self.pid, self.settings_body(), 'future')
        rid = self.store.create_run(self.pid).id
        runner = self.service.runner(self.pid, rid)
        runner.initialize()
        self.assertEqual(runner.definitions[AgentKind.DEVELOPER].model, 'anthropic/test-model')
        self.assertEqual(self.store.get_project(self.pid).run(self.rid).workflow.agent_snapshots, old)
        # Reconstructed historical runner must use captured settings, not new project configuration.
        historical = self.service.runner(self.pid, self.rid)
        self.assertEqual(historical.definitions[AgentKind.DEVELOPER].snapshot(), old[1])

    def test_settings_reject_capability_and_secret_fields(self):
        with TestClient(create_app(store=self.store), base_url='http://localhost') as client:
            data = self.settings_body().model_dump() | {'permissions':['all'], 'api_key':'forbidden'}
            response = client.post(f'/projects/{self.pid}/settings', json=data, headers={'Idempotency-Key':'bad'})
            self.assertEqual(response.status_code,422)
            self.assertNotIn('forbidden', response.text)

    def test_browser_projection_no_environment_headers_or_key(self):
        with patch.dict(os.environ, {'OPENROUTER_API_KEY':'secret-sentinel'}):
            data = public({'environment':{'HOME':'hidden'}, 'effective_environment':[['TOKEN','secret']],
                'Authorization':'Bearer sentinel', 'text':'Authorization: Bearer sentinel\nsecret-sentinel'})
            encoded = json.dumps(data)
            for value in ('hidden','secret-sentinel','Bearer sentinel','environment'):
                self.assertNotIn(value, encoded)
            self.assertTrue(self.service.settings(self.pid)['provider_configured'])
            for view in (self.service.settings(self.pid), self.service.inspection(self.pid,self.rid), self.service.snapshot(self.pid).model_dump()):
                self.assertNotIn('secret-sentinel', json.dumps(view))

    def test_inspection_http_missing_run(self):
        with TestClient(create_app(store=self.store), base_url='http://localhost') as client:
            self.assertEqual(client.get(f'/projects/{self.pid}/runs/missing/inspection').status_code,404)
            self.assertEqual(client.get(f'/projects/{self.pid}/runs/{self.rid}/inspection').status_code,200)

    def test_recovery_supported_actions_and_explicit_resolution(self):
        rid = self.store.create_run(self.pid).id
        runner = self.service.runner(self.pid, rid)
        runner.initialize()
        cp = checkpoint(self.store.get_project(self.pid), runner.run, 'fixture')
        op = ExecutionOperation('uncertain-command','command',replace(cp, operation_id='uncertain-command'),
            operation='execute')
        self.store.record_operation(op)
        op = op.evolve(stage=OperationStage.EXECUTING)
        self.store.record_operation(op)
        recovery = self.service.recovery.reconcile(self.pid, rid)
        info = self.service.recovery.inspect(self.pid, rid)
        self.assertEqual(info['available_actions']['uncertain-command'][0]['action'], 'acknowledge-command')
        self.assertTrue(info['available_actions']['uncertain-command'][0]['requires_quiescent'])
        self.service.recovery.resolve(self.pid, rid, op.id, action='acknowledge-command', reason='Confirmed quiescent',
            quiescent=True, expected_epoch=recovery.epoch)
        self.assertEqual(runner.run.status.value,'paused')
        self.assertTrue(runner.run.workflow.recovery.requires_resume)
        self.assertEqual(runner.run.workflow.recovery.issues[0].certainty.value,'uncertain')


class ArtifactProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name); (root/'greeting.txt').write_text('hello\n')
        self.runner = make_workspace_runner(root)
        old = self.runner.file_tool(request(self.runner,'read',path='greeting.txt'))
        self.runner.file_tool(request(self.runner,'write',path='greeting.txt',expected_hash=old.content_hash,content='hello world\n'))
        self.runner.run_until_stopped()
        self.service = ControlService(self.runner.store, lambda *_: self.runner)
        self.submission = self.runner.run.workflow.submissions[0].id

    def artifact(self, path):
        return self.service.artifact(self.runner.project_id,self.runner.run_id,self.submission,path)

    def test_immutable_diff_and_association(self):
        result = self.artifact('greeting.txt')
        self.assertIn('+hello world', result['diff'])
        self.assertIn('-hello', result['diff'])
        self.assertEqual(result['submission_id'], self.submission)
        self.assertEqual(len(result['content_hash']), 64)

    def test_missing_artifact_rejected(self):
        with self.assertRaises(KeyError): self.artifact('absent.txt')

    def test_protected_paths_rejected(self):
        for path in ('.env','../greeting.txt','/etc/passwd','.git/config'):
            with self.subTest(path=path), self.assertRaises(ValueError): self.artifact(path)
