"""SQLite persistence and shared M2/M3 contract parity on disposable databases."""
from contextlib import ExitStack, closing
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import test_m21
import test_m22
import test_m31
import test_m32
import test_finalization
from app.persistence.sqlite import SQLiteStateStore
from app.persistence.memory import InMemoryStateStore
from app.persistence.store import StoreError
from app.persistence.models import ArtifactIntegrityError
from app.persistence.migrate import migrate, MIGRATIONS
from app.domain.projects import ProjectState
from app.domain.events import DomainEvent
from app.dev.workflow import make_runner, approve_generated, ScriptedWorkflowProvider
from app.usage.aggregation import aggregate
from app.usage.records import LLMCallRecord, UsageCompleteness, UsageProvenance
from app.usage.pricing import CostEstimate
from app.providers.base import UsageSnapshot


class SQLiteParity:
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(TemporaryDirectory(prefix='m41-parity-')))
        self.store_count = 0
        def factory():
            self.store_count += 1
            return self.stack.enter_context(SQLiteStateStore(root / f'{self.store_count}.db'))
        for module in (test_m21, __import__('app.dev.workflow', fromlist=['']), __import__('app.dev.workspace', fromlist=[''])):
            self.stack.enter_context(patch.object(module, 'InMemoryStateStore', factory))
        super().setUp()


class SQLiteStoreContracts(SQLiteParity, test_m21.StateStoreTests):
    pass


class SQLiteWorkflowContracts(SQLiteParity, test_m22.WorkflowTests):
    pass


class SQLiteWorkspaceContracts(SQLiteParity, test_m31.WorkspaceTests):
    pass


class SQLiteCommandContracts(SQLiteParity, test_m32.CommandTests):
    pass


class SQLiteFinalizationContracts(SQLiteParity, test_finalization.FinalizationTests):
    pass


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix='m41-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'state.db'
        self.store = SQLiteStateStore(self.path)
        self.addCleanup(lambda: self.store.close())

    def workflow(self):
        with patch('app.dev.workflow.InMemoryStateStore', return_value=self.store):
            runner = make_runner(ScriptedWorkflowProvider(tasks=2))
        approve_generated(runner)
        runner.run_until_stopped()
        return runner

    def test_complete_history_reopens(self):
        runner = self.workflow()
        before = self.store.get_project('demo')
        events = self.store.events('demo')
        usage = self.store.usage('demo')
        self.store.close()
        self.store = SQLiteStateStore(self.path)
        self.assertEqual(before, self.store.get_project('demo'))
        self.assertEqual(events, self.store.events('demo'))
        self.assertEqual(usage, self.store.usage('demo'))
        for table in ('projects', 'runs', 'tasks', 'dependencies', 'attempts', 'submissions', 'reviews', 'agents', 'invocations', 'llm_calls', 'events'):
            self.assertGreater(self.store.connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0], 0, table)
        self.assertEqual(self.store.get_project('demo').runs[0].status.value, 'completed')

    def test_state_and_events_rollback_on_event_insert_failure(self):
        self.store.create_project(ProjectState('p', 'P', 'G'))
        before = self.store.get_project('p')
        events = self.store.events('p')
        self.store.connection.execute("CREATE TRIGGER fail_event BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(StoreError):
            self.store.create_run('p')
        self.assertEqual(before, self.store.get_project('p'))
        self.assertEqual(events, self.store.events('p'))

    def test_invalid_state_rolls_back_events_and_all_rows(self):
        self.store.create_project(ProjectState('p', 'P', 'G'))
        before = self.store.events('p')
        with self.assertRaises(StoreError):
            self.store.atomic_update('p', lambda p: (replace(p, name='changed'), [DomainEvent('p','bad',{},run_id='missing')]))
        self.assertEqual(self.store.get_project('p').name, 'P')
        self.assertEqual(before, self.store.events('p'))

    def test_both_stores_reject_event_only_and_state_only(self):
        for store in (self.store, InMemoryStateStore()):
            store.create_project(ProjectState('p', 'P', 'G'))
            with self.assertRaises(StoreError):
                store.atomic_update('p', lambda p: (replace(p, name='new'), ()))
            with self.assertRaises(StoreError):
                store.atomic_update('p', lambda p: (p, (DomainEvent('p','bad',{}),)))

    def test_sequence_continues_and_history_is_append_only(self):
        self.store.create_project(ProjectState('p', 'P', 'G'))
        self.store.close()
        self.store = SQLiteStateStore(self.path)
        self.store.create_run('p')
        self.assertEqual([e.sequence for e in self.store.events('p')], [1,2])
        for sql in ('DELETE FROM events', "UPDATE events SET type='changed'"):
            with self.assertRaises(sqlite3.IntegrityError):
                self.store.connection.execute(sql)
        self.assertEqual(len(self.store.events('p', after_sequence=1)), 1)

    def test_foreign_keys_and_duplicate_identifiers(self):
        self.store.create_project(ProjectState('p', 'P', 'G'))
        with self.assertRaises(StoreError):
            self.store.create_project(ProjectState('p', 'P', 'G'))
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute("INSERT INTO tasks VALUES ('missing','t','{}')")
        self.store.create_run('p', run_id='r')
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute("INSERT INTO runs VALUES ('p','other',1,'{}')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute("INSERT INTO dependencies VALUES ('p','missing','other')")

    def test_fresh_current_and_upgrade_migrations(self):
        self.assertEqual(self.store.connection.execute('SELECT max(version) FROM schema_migrations').fetchone()[0], 4)
        old = Path(self.temp.name) / 'old'
        old.mkdir()
        (old / '001_initial.sql').write_bytes((MIGRATIONS / '001_initial.sql').read_bytes())
        connection = sqlite3.connect(Path(self.temp.name) / 'upgrade.db', isolation_level=None)
        self.addCleanup(connection.close)
        migrate(connection, old)
        connection.execute("INSERT INTO projects VALUES ('sentinel',1,'{}')")
        migrate(connection)
        migrate(connection)
        self.assertEqual(connection.execute('SELECT count(*) FROM schema_migrations').fetchone()[0], 4)
        self.assertEqual(connection.execute('SELECT id FROM projects').fetchone()[0], 'sentinel')

    def test_invalid_migration_state(self):
        self.store.connection.execute("UPDATE schema_migrations SET checksum='bad' WHERE version=1")
        with self.assertRaisesRegex(StoreError, 'checksum'):
            migrate(self.store.connection)
        self.store.connection.execute('DELETE FROM schema_migrations WHERE version=1')
        with self.assertRaisesRegex(StoreError, 'state'):
            migrate(self.store.connection)

    def test_missing_and_corrupt_artifact_detected(self):
        self.workflow()
        import json
        raw, = self.store.connection.execute('SELECT data FROM submissions LIMIT 1').fetchone()
        digest = json.loads(raw)['fields']['evidence']['$artifact']
        path = self.store.codec.root / digest
        saved = path.read_bytes()
        path.unlink()
        with self.assertRaises(ArtifactIntegrityError):
            self.store.get_project('demo')
        path.write_bytes(b'corrupt')
        with self.assertRaises(ArtifactIntegrityError):
            self.store.get_project('demo')
        path.write_bytes(saved)
        self.assertEqual(self.store.get_project('demo').runs[0].status.value, 'completed')

    def test_duplicate_call_and_changed_history_rejected(self):
        self.workflow()
        before = self.store.get_project('demo')
        run = before.runs[0]
        wf = replace(run.workflow, call_records=(*run.workflow.call_records, run.workflow.call_records[0]))
        with self.assertRaisesRegex(StoreError, 'duplicate'):
            self.store.atomic_update('demo', lambda p: (replace(p, runs=(replace(run, workflow=wf),)), [DomainEvent('demo','bad',{})]))
        self.assertEqual(before, self.store.get_project('demo'))

    def test_no_transaction_during_reducer_or_external_io(self):
        self.store.create_project(ProjectState('p', 'P', 'G'))
        def change(p):
            self.assertFalse(self.store.connection.in_transaction)
            return replace(p, name='changed'), [DomainEvent('p','changed',{})]
        original = self.store.codec.external
        def external(value):
            self.assertFalse(self.store.connection.in_transaction)
            return original(value)
        self.store.atomic_update('p', change)
        with patch.object(self.store.codec, 'external', external):
            self.workflow()

    def test_credentials_not_configuration(self):
        self.store.create_project(ProjectState('p', 'P', 'G'))
        with self.assertRaisesRegex(StoreError, 'credentials'):
            self.store.create_run('p', config_snapshot={'OPENROUTER_API_KEY':'sentinel-secret'})
        self.assertNotIn('sentinel-secret', '\n'.join(self.store.connection.iterdump()))


class AggregationTests(unittest.TestCase):
    def call(self, identity='call', **kwargs):
        values = dict(call_id=identity, invocation_id='inv', attempt=1, purpose='initial', provider_name='mock', model='m', status='success', provider_request_id=None,
            usage=UsageSnapshot(10,5,2), usage_provenance=UsageProvenance.PROVIDER_REPORTED, usage_completeness=UsageCompleteness.COMPLETE,
            price_snapshot=None, estimated_cost=CostEstimate(Decimal('0.00000001')))
        values.update(kwargs)
        return LLMCallRecord(**values)

    def test_decimal_per_agent_and_retries(self):
        result = aggregate([('dev',self.call()), ('dev',self.call('two',attempt=2)), ('review',self.call('three'))], reviews=1)
        self.assertEqual(result['estimated_cost'], Decimal('0.00000003'))
        self.assertEqual(result['per_agent']['dev']['estimated_cost'], Decimal('0.00000002'))
        self.assertEqual((result['total_tokens'],result['provider_calls'],result['retries'],result['reviews']), (45,3,1,1))

    def test_unknown_and_partial_are_not_zero(self):
        for call in (self.call(estimated_cost=None), self.call(usage=None, usage_completeness=UsageCompleteness.UNKNOWN,estimated_cost=None),
                     self.call(usage_completeness=UsageCompleteness.PARTIAL)):
            result = aggregate([('dev',call)])
            self.assertIsNone(result['estimated_cost'])
            if call.usage_completeness is not UsageCompleteness.COMPLETE:
                self.assertIsNone(result['total_tokens'])

class DurableBoundaryTests(unittest.TestCase):
    setUp = PersistenceTests.setUp
    workflow = PersistenceTests.workflow

    def workspace(self):
        from app.dev.workspace import make_workspace_runner
        from app.domain.commands import CommandProfile
        import sys
        root = Path(self.temp.name) / 'workspace'
        root.mkdir()
        (root / 'greeting.txt').write_text('hello\n')
        (root / '.env').write_text('PROTECTED=m41-protected-marker')
        (root / 'test.py').write_text("print('ok')\n")
        profile = CommandProfile('test', str(Path(sys.executable).resolve()), ('-I','-B','test.py'), True)
        return make_workspace_runner(root, store=self.store, command_profiles=(profile,)), profile

    def test_tool_intent_visible_on_separate_connection_before_write(self):
        from app.dev.workspace import request
        runner, _ = self.workspace()
        original = runner.workspace_gateway._files.write
        observed = []
        def write(*args, **kwargs):
            self.assertFalse(self.store.connection.in_transaction)
            with closing(sqlite3.connect(self.path)) as reader:
                records = [self.store.codec.loads(row[0]) for row in reader.execute('SELECT data FROM tool_records')]
            observed.extend(r for r in records if r.operation == 'write' and r.outcome == 'pending')
            return original(*args, **kwargs)
        with patch.object(runner.workspace_gateway._files, 'write', write):
            runner.file_tool(request(runner, 'write', path='new.txt', content='new', expected_hash=None))
        self.assertEqual(len(observed), 1)
        rows = [self.store.codec.loads(row[0]) for row in self.store.connection.execute('SELECT data FROM tool_records')]
        self.assertTrue(any(r.id + ':intent' == observed[0].id and r.outcome == 'succeeded' for r in rows))

    def test_failed_intent_commit_prevents_file_execution(self):
        from app.dev.workspace import request
        runner, _ = self.workspace()
        self.store.connection.execute("CREATE TRIGGER fail_tool BEFORE INSERT ON tool_records BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            runner.file_tool(request(runner, 'write', path='must-not-exist', content='no', expected_hash=None))
        self.assertFalse((runner.workspace_gateway.policy.root / 'must-not-exist').exists())

    def test_command_intent_committed_before_launch(self):
        from app.dev.commands import command_request, approve_fixture
        import app.tools.gateway as module
        runner, profile = self.workspace()
        req = command_request(runner, profile)
        approval = approve_fixture(runner, req)
        original = module.launch
        def launch(*args, **kwargs):
            self.assertFalse(self.store.connection.in_transaction)
            with closing(sqlite3.connect(self.path)) as reader:
                records = [self.store.codec.loads(row[0]) for row in reader.execute('SELECT data FROM tool_records')]
            self.assertTrue(any(r.action == 'intent' and r.approval_id == approval for r in records))
            return original(*args, **kwargs)
        with patch.object(module, 'launch', launch):
            result = runner.command_tool(req, approval)
        self.assertTrue(result.succeeded)
        self.assertEqual(self.store.connection.execute('SELECT count(*) FROM interventions').fetchone()[0], 1)

    def test_real_artifact_metadata_audits_and_interventions_reopen(self):
        from app.dev.persistence import create, inspect
        root = Path(self.temp.name) / 'manual-fixture'
        before = create(root)
        with SQLiteStateStore(root / 'state.db') as reopened:
            after = inspect(reopened)
            self.assertEqual(before, after)
            self.assertEqual(after['usage']['estimated_cost'], Decimal('0.00012000'))
            self.assertEqual(after['table_counts']['artifact_metadata'], 1)
            self.assertEqual(after['table_counts']['tool_records'], 11)
            self.assertEqual(after['table_counts']['interventions'], 1)

    def test_decisions_dependencies_and_task_transition_survive(self):
        self.store.create_project(ProjectState('p', 'P', 'G'))
        self.store.create_run('p', run_id='r')
        self.store.propose_plan('p', 'r', test_m21.two_task_plan())
        self.store.approve_plan('p','r')
        task = self.store.start_next_task('p','r')
        self.store.close()
        self.store = SQLiteStateStore(self.path)
        project = self.store.get_project('p')
        self.assertEqual(project.decisions[0].id, 'decision-1')
        self.assertEqual(project.task(task.id).status.value, 'in_progress')
        self.assertEqual(project.task('task-b').dependencies, ('task-a',))
        self.assertEqual(self.store.events('p')[-1].type, 'task.started')

    def test_event_failure_rolls_back_tool_record(self):
        from app.domain.artifacts import ToolCallRecord
        self.store.create_project(ProjectState('p','P','G'))
        self.store.create_run('p',run_id='r')
        self.store.connection.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.record_tool('p','r',ToolCallRecord('t','developer','read','a',1,'x',None,'pending'))
        self.assertEqual(self.store.connection.execute('SELECT count(*) FROM tool_records').fetchone()[0], 0)

    def test_unknown_usage_and_retries_persist_in_aggregates(self):
        from app.providers.base import ProviderTimeoutError
        class RetryProvider(ScriptedWorkflowProvider):
            failed = False
            def complete(self, request):
                if not self.failed:
                    self.failed = True
                    raise ProviderTimeoutError('fixture timeout')
                return super().complete(request)
        with patch('app.dev.workflow.InMemoryStateStore',return_value=self.store):
            runner = make_runner(RetryProvider())
        approve_generated(runner)
        runner.run_until_stopped()
        self.store.close()
        self.store = SQLiteStateStore(self.path)
        totals = self.store.usage('demo')
        self.assertEqual((totals['provider_calls'],totals['retries']), (7,1))
        self.assertIsNone(totals['total_tokens'])
        self.assertIsNone(totals['estimated_cost'])
        self.assertEqual(totals['known_tokens'], 90)

    def test_conflicting_immutable_call_and_duplicate_event_roll_back(self):
        self.workflow()
        before = self.store.get_project('demo')
        run = before.runs[0]
        records = run.workflow.call_records
        changed = replace(records[0], status='changed')
        wf = replace(run.workflow, call_records=(changed,*records[1:]))
        with self.assertRaisesRegex(StoreError,'immutable'):
            self.store.atomic_update('demo',lambda p:(replace(p,runs=(replace(run,workflow=wf),)),[DomainEvent('demo','bad',{})]))
        with self.assertRaises(StoreError):
            self.store.atomic_update('demo',lambda p:(replace(p,name='bad'),[self.store.events('demo')[0]]))
        self.assertEqual(before,self.store.get_project('demo'))

    def test_migration_failure_is_atomic_and_future_version_rejected(self):
        directory = Path(self.temp.name) / 'migrations'
        directory.mkdir()
        for path in MIGRATIONS.glob('*.sql'):
            (directory / path.name).write_bytes(path.read_bytes())
        (directory / '005_broken.sql').write_text('CREATE TABLE must_rollback (id TEXT);\nINVALID SQL;\n')
        with self.assertRaises(sqlite3.OperationalError):
            migrate(self.store.connection,directory)
        self.assertIsNone(self.store.connection.execute("SELECT name FROM sqlite_master WHERE name='must_rollback'").fetchone())
        self.store.connection.execute("INSERT INTO schema_migrations VALUES (5,'future')")
        with self.assertRaisesRegex(StoreError,'newer'):
            migrate(self.store.connection)

    def test_duplicate_attempt_number_and_invalid_submission_relation(self):
        self.workflow()
        connection = self.store.connection
        row = connection.execute('SELECT project_id,run_id,task_id,number,data FROM attempts LIMIT 1').fetchone()
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute('INSERT INTO attempts(project_id,run_id,id,task_id,number,data) VALUES (?,?,?,?,?,?)',
                (row[0],row[1],'duplicate-number',row[2],row[3],row[4]))
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO submissions VALUES ('demo','run-demo','bad','missing','{}')")

    def test_partial_call_is_preserved_and_aggregate_stays_unknown(self):
        self.workflow()
        run = self.store.get_project('demo').runs[0]
        partial = replace(run.workflow.call_records[0], call_id='partial', usage_completeness=UsageCompleteness.PARTIAL)
        wf = replace(run.workflow, call_records=(*run.workflow.call_records, partial))
        self.store.atomic_update('demo', lambda p: (replace(p,runs=(replace(run,workflow=wf),)),[DomainEvent('demo','usage.recorded',partial.to_dict())]))
        self.store.close()
        self.store = SQLiteStateStore(self.path)
        self.assertEqual(self.store.get_project('demo').runs[0].workflow.call_records[-1],partial)
        self.assertIsNone(self.store.usage('demo')['total_tokens'])
        self.assertIsNone(self.store.usage('demo')['estimated_cost'])

    def test_tool_record_duplicates_are_idempotent_but_conflicts_fail(self):
        from app.domain.artifacts import ToolCallRecord
        self.store.create_project(ProjectState('p','P','G'))
        self.store.create_run('p',run_id='r')
        record = ToolCallRecord('t','developer','read','a',1,'x',None,'pending')
        self.store.record_tool('p','r',record)
        self.store.record_tool('p','r',record)
        self.assertEqual(len(self.store.events('p')),3)
        with self.assertRaises(StoreError):
            self.store.record_tool('p','r',replace(record,outcome='changed'))
        self.assertEqual(len(self.store.events('p')),3)
