"""HTTP boundary, durable command admission, and committed cursor transport."""
import asyncio
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import create_app
from app.api.events import event_stream
from app.api.service import ControlService, public
from app.domain.events import DomainEvent
from app.domain.projects import ProjectState
from app.dev.workflow import ScriptedWorkflowProvider, make_runner, approve_generated
from app.orchestration.runner import WorkflowRunner
from app.persistence.sqlite import SQLiteStateStore
from app.persistence.store import VersionConflictError


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'state.db'
        self.store = SQLiteStateStore(self.path)
        self.addCleanup(self.store.close)
        self.provider = ScriptedWorkflowProvider()
        self.client = TestClient(create_app(store=self.store, runner_factory=lambda s,p,r: WorkflowRunner(s,p,r,self.provider)),
                                 base_url='http://localhost')
        self.client.__enter__()
        self.addCleanup(lambda: self.client.__exit__(None,None,None))
        self.pid = self.client.post('/projects', json={'name':'Fixture','goal':'Synthetic greeting','requirements':[{'id':'r1','description':'Greeting','acceptance_criteria':['Synthetic output is documented']}]} ,
                                    headers={'Idempotency-Key':'create'}).json()['project_id']

    def snapshot(self):
        return self.client.get(f'/projects/{self.pid}/snapshot').json()

    def command(self, action, *, rid=None, key=None, version=None, **fields):
        path = f'/projects/{self.pid}/plan' if action == 'plan' else f'/projects/{self.pid}/runs/{rid}/{action}'
        return self.client.post(path, json={'expected_version':version or self.snapshot()['project']['version'], **fields},
                                headers={'Idempotency-Key':key or action})

    def wait_status(self, status):
        for _ in range(300):
            snapshot = self.snapshot()
            if snapshot['project']['runs'][-1]['status'] == status:
                return snapshot
            time.sleep(.01)
        self.fail(f'never reached {status}: {snapshot}')

    def plan(self):
        response = self.command('plan')
        self.assertEqual(response.json()['status'],'pending')
        rid = response.json()['run_id']
        self.wait_status('awaiting_approval')
        return rid

    def test_api_workflow_end_to_end(self):
        rid = self.plan()
        self.assertEqual(self.command('approve',rid=rid).json()['status'],'applied')
        self.assertEqual(self.command('start',rid=rid).json()['status'],'pending')
        self.wait_status('completed')
        for kind in ('tasks','reviews','evidence','usage','permissions','recovery'):
            self.assertEqual(self.client.get(f'/projects/{self.pid}/runs/{rid}/{kind}').status_code,200)
        usage = self.client.get(f'/projects/{self.pid}/runs/{rid}/usage').json()
        self.assertTrue(usage)
        self.assertEqual(len(self.provider.requests),6)

    def test_duplicate_create(self):
        response = self.client.post('/projects',json={'name':'Fixture','goal':'Synthetic greeting','requirements':[{'id':'r1','description':'Greeting','acceptance_criteria':['Synthetic output is documented']}]} ,headers={'Idempotency-Key':'create'})
        self.assertEqual(response.json()['project_id'],self.pid)
        self.assertEqual(len(self.client.get('/projects').json()),1)

    def test_duplicate_plan_ignores_now_stale_version(self):
        first = self.command('plan',version=1,key='p')
        self.wait_status('awaiting_approval')
        second = self.command('plan',version=1,key='p')
        self.assertEqual(first.json(),second.json())
        self.assertEqual(len(self.provider.requests),1)
        self.assertEqual(len(self.snapshot()['project']['runs']),1)

    def test_key_conflicting_payload(self):
        self.command('plan',version=1,key='p')
        self.assertEqual(self.command('plan',version=2,key='p').status_code,409)

    def test_stale_version(self):
        rid = self.plan()
        before = len(self.store.events(self.pid))
        self.assertEqual(self.command('approve',rid=rid,version=1).status_code,409)
        self.assertEqual(len(self.store.events(self.pid)),before)

    def test_pause_resume(self):
        rid = self.plan()
        self.command('approve',rid=rid)
        self.assertEqual(self.command('pause',rid=rid).json()['status'],'applied')
        self.wait_status('paused')
        self.command('resume',rid=rid)
        self.wait_status('completed')

    def test_cancel_duplicate(self):
        rid = self.plan()
        version = self.snapshot()['project']['version']
        first = self.command('cancel',rid=rid,version=version)
        self.assertEqual(first.json(),self.command('cancel',rid=rid,version=version).json())
        self.wait_status('canceled')
        self.assertEqual(sum(e.type == 'run.canceled' for e in self.store.events(self.pid)),1)

    def test_one_active_run(self):
        self.plan()
        self.assertEqual(self.command('plan',key='second').json()['status'],'rejected')

    def test_snapshot_cursor(self):
        self.plan()
        snapshot = self.snapshot()
        project, cursor = self.store.snapshot(self.pid)
        self.assertEqual(snapshot['event_cursor'],cursor)
        self.assertEqual(snapshot['project']['version'],project.version)
        self.assertEqual(cursor,self.store.events(self.pid)[-1].sequence)

    def test_cursor_rejection(self):
        for value in ('bad','-1','999999'):
            self.assertEqual(self.client.get(f'/projects/{self.pid}/events',headers={'Last-Event-ID':value}).status_code,409)

    def test_strict_validation(self):
        self.assertEqual(self.client.post('/projects',json={'name':'x','goal':'y','api_key':'secret'},
                                         headers={'Idempotency-Key':'other'}).status_code,422)
        self.assertEqual(self.client.post(f'/projects/{self.pid}/plan',json={'expected_version':1}).status_code,422)

    def test_host_and_origin(self):
        self.assertEqual(self.client.get('/projects',headers={'Host':'evil.example'}).status_code,400)
        self.assertEqual(self.client.get('/projects',headers={'Origin':'http://evil.example'}).status_code,403)
        self.assertEqual(self.client.post('/projects',json={'name':'x','goal':'y'},
            headers={'Idempotency-Key':'evil','Sec-Fetch-Site':'cross-site'}).status_code,403)

    def test_missing(self):
        self.assertEqual(self.client.get('/projects/missing').status_code,404)

    def test_credentials_not_serialized(self):
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'sentinel-secret'}):
            self.store.create_project(ProjectState('secret','Secret','sentinel-secret'))
            for path in ('/projects','/projects/secret/snapshot'):
                self.assertNotIn('sentinel-secret',self.client.get(path).text)
            self.assertNotIn('sentinel-secret',json.dumps(public({'api_key':'sentinel-secret','nested':'sentinel-secret'})))

    def test_execution_without_browser_and_responsive_during_io(self):
        rid = self.plan()
        entered, release = Event(), Event()
        def hook(request):
            if request.context['workflow']['phase'] == 'develop':
                entered.set()
                release.wait(5)
        self.provider.hook = hook
        self.command('approve',rid=rid)
        self.command('start',rid=rid)
        self.assertTrue(entered.wait(2))
        try:
            self.assertEqual(self.client.get('/projects').status_code,200)
            response = self.command('pause',rid=rid)
            self.assertEqual(response.json()['status'],'pending')
        finally:
            release.set()
        self.wait_status('paused')
        self.command('resume',rid=rid)
        self.wait_status('completed')

    def test_rejected_permission(self):
        rid = self.plan()
        self.assertEqual(self.command('permission',rid=rid,approval_id='missing',approved=True,reason='inspect').json()['status'],'rejected')

    def test_artifact_paths_rejected(self):
        rid = self.plan()
        root = Path(self.temp.name)/'workspace'
        root.mkdir()
        from dataclasses import replace
        self.store.atomic_update(self.pid,lambda p:(replace(p,workspace_root=str(root)),(DomainEvent(self.pid,'fixture.root',{}),)))
        for path in ('../outside','/etc/passwd','.env','.git/config','x/../y','credentials.json'):
            self.assertEqual(self.client.get(f'/projects/{self.pid}/runs/{rid}/artifacts/missing',params={'path':path}).status_code,400)


class DurableAPIRecoveryTests(unittest.TestCase):
    def test_journal_survives_restart_and_uncertain_never_reexecutes(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.db'
            s=SQLiteStateStore(path)
            calls=[]
            result=s.admit_command('create','k','f',None,lambda:(calls.append(1) or {'status':'applied'}))
            s._command_put('create','uncertain','f',None)
            s.close()
            s=SQLiteStateStore(path)
            try:
                self.assertEqual(result,s.admit_command('create','k','f',None,lambda:calls.append(2)))
                with self.assertRaises(VersionConflictError):
                    s.admit_command('create','uncertain','f',None,lambda:calls.append(3))
                self.assertEqual(calls,[1])
            finally:s.close()

    def test_recovery_inspection_resume(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.db'
            s=SQLiteStateStore(path)
            runner=make_runner(store=s)
            approve_generated(runner)
            runner.step()
            s.close()
            s=SQLiteStateStore(path)
            try:
                with TestClient(create_app(store=s),base_url='http://localhost') as c:
                    base='/projects/demo/runs/run-demo'
                    recovery=c.get(base+'/recovery').json()
                    self.assertTrue(recovery['recovery']['requires_resume'])
                    version=c.get('/projects/demo/snapshot').json()['project']['version']
                    response=c.post(base+'/resume',json={'expected_version':version,'expected_epoch':recovery['recovery']['epoch']},
                                    headers={'Idempotency-Key':'resume'})
                    self.assertEqual(response.json()['status'],'pending')
                    for _ in range(200):
                        if c.get('/projects/demo/snapshot').json()['project']['runs'][0]['status']=='completed':break
                        time.sleep(.01)
                    else:self.fail('recovery did not finish')
            finally:s.close()


class SSETests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.persistence.memory import InMemoryStateStore
        self.store=InMemoryStateStore()
        self.store.create_project(ProjectState('p','P','G'))
        self.service=ControlService(self.store,None)
        self.disconnected=False

    async def disconnect(self):return self.disconnected

    def stream(self,cursor=0,**kwargs):
        return event_stream(self.service,'p',cursor,self.disconnect,poll=.001,**kwargs)

    def change(self,name):
        from dataclasses import replace
        self.store.atomic_update('p',lambda p:(replace(p,name=name),(DomainEvent('p','changed',{}),)))

    async def test_ordered_replay_reconnect(self):
        self.change('one');self.change('two')
        stream=self.stream()
        frames=[await anext(stream) for _ in range(3)]
        self.assertEqual([int(f.splitlines()[0][4:]) for f in frames],[1,2,3])
        await stream.aclose()
        self.change('three')
        stream=self.stream(3)
        self.assertTrue((await anext(stream)).startswith('id: 4'))
        await stream.aclose()

    async def test_events_during_replay(self):
        self.change('one')
        stream=self.stream()
        await anext(stream)
        self.change('two')
        frames=[await anext(stream),await anext(stream)]
        self.assertTrue(frames[-1].startswith('id: 3'))
        await stream.aclose()

    async def test_snapshot_stream_race(self):
        _,cursor=self.store.snapshot('p')
        self.change('after snapshot')
        stream=self.stream(cursor)
        self.assertTrue((await anext(stream)).startswith('id: 2'))
        await stream.aclose()

    async def test_slow_client_does_not_hold_store(self):
        stream=self.stream()
        await anext(stream)
        for i in range(110):self.change(str(i))
        self.assertEqual(self.store.snapshot('p')[1],111)
        self.assertTrue((await anext(stream)).startswith('id: 2'))
        await stream.aclose()

    async def test_disconnect(self):
        self.disconnected=True
        with self.assertRaises(StopAsyncIteration):await anext(self.stream())
        self.change('still writable')
        self.assertEqual(self.store.snapshot('p')[1],2)

    async def test_keepalive(self):
        stream=self.stream(1,keepalive=.001)
        self.assertEqual(await anext(stream),': keepalive\n\n')
        await stream.aclose()


class WorkspaceAPITests(unittest.TestCase):
    def setUp(self):
        from app.dev.workspace import make_workspace_runner
        from app.domain.commands import CommandProfile
        import sys
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'workspace';self.root.mkdir()
        (self.root/'greeting.txt').write_text('hello\n')
        self.store=SQLiteStateStore(Path(self.temp.name)/'state.db')
        self.addCleanup(self.store.close)
        self.profile=CommandProfile('test',str(Path(sys.executable).resolve()),('-I','-B','-c','print("ok")'),True)
        self.runner=make_workspace_runner(self.root,store=self.store,command_profiles=(self.profile,),protected=('private.txt',))
        self.client=TestClient(create_app(store=self.store,runner_factory=lambda s,p,r:self.runner),base_url='http://localhost')
        self.client.__enter__();self.addCleanup(lambda:self.client.__exit__(None,None,None))
        self.base='/projects/workspace-demo/runs/workspace-run'

    def test_permission_decision_idempotent(self):
        from app.domain.commands import CommandRequest
        from app.domain.agents import AgentKind
        attempt=self.runner.run.workflow.attempts[-1]
        req=CommandRequest(AgentKind.DEVELOPER,attempt.id,attempt.generation,self.profile.name,
            self.profile.executable,self.profile.args,self.runner.workspace_gateway.workspace_version())
        approval=self.runner.request_command(req)
        body={'expected_version':self.store.get_project('workspace-demo').version,'approval_id':approval.id,
              'approved':True,'reason':'Inspected exact disposable command'}
        response=self.client.post(self.base+'/permission',json=body,headers={'Idempotency-Key':'permission'})
        self.assertEqual(response.json()['status'],'applied')
        duplicate=self.client.post(self.base+'/permission',json=body,headers={'Idempotency-Key':'permission'})
        self.assertEqual(response.json(),duplicate.json())
        self.assertEqual(len(self.client.get(self.base+'/permissions').json()),1)
        self.assertTrue(self.runner.command_tool(req,approval.id).succeeded)

    def test_artifact_read_immutable_and_custom_protected(self):
        from app.dev.workspace import request
        old=self.runner.file_tool(request(self.runner,'read',path='greeting.txt'))
        self.runner.file_tool(request(self.runner,'write',path='greeting.txt',expected_hash=old.content_hash,content='hello world\n'))
        self.runner.step()
        submission=self.runner.run.workflow.submissions[0]
        (self.root/'greeting.txt').write_text('later external edit')
        response=self.client.get(self.base+'/artifacts/'+submission.id,params={'path':'greeting.txt'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['content'],'hello world\n')
        self.assertEqual(self.client.get(self.base+'/artifacts/'+submission.id,params={'path':'private.txt'}).status_code,400)
        self.assertEqual(self.client.get(self.base+'/artifacts/'+submission.id,params={'path':'missing'}).status_code,404)


class AdditionalAdmissionTests(unittest.TestCase):
    def test_concurrent_duplicate_commands(self):
        from concurrent.futures import ThreadPoolExecutor
        from app.persistence.memory import InMemoryStateStore
        store=InMemoryStateStore();effects=[]
        def call():return store.admit_command('create','key','same',None,lambda:(effects.append(1) or {'status':'applied'}))
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(lambda _:call(),range(20)))
        self.assertEqual(effects,[1]);self.assertTrue(all(r==results[0] for r in results))

    def test_recovery_resolution_and_epoch_rejection_through_api(self):
        class Crash(BaseException):pass
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.db';store=SQLiteStateStore(path)
            runner=make_runner(store=store);approve_generated(runner);runner.step()
            runner.provider.hook=lambda request:(_ for _ in ()).throw(Crash())
            with self.assertRaises(Crash):runner.step()
            store.close();store=SQLiteStateStore(path)
            try:
                with TestClient(create_app(store=store),base_url='http://localhost') as c:
                    base='/projects/demo/runs/run-demo'
                    info=c.get(base+'/recovery').json()
                    op=next(o for o in info['operations'] if o['stage']=='executing')
                    epoch=info['recovery']['epoch']
                    def send(name, key, **extra):
                        version=c.get('/projects/demo/snapshot').json()['project']['version']
                        return c.post(base+'/'+name,json={'expected_version':version,**extra},headers={'Idempotency-Key':key})
                    self.assertEqual(send('resume','stale',expected_epoch=epoch+1).json()['status'],'rejected')
                    response=send('recovery','resolve',operation_id=op['id'],action='abandon-provider',
                                  reason='Accept unknown billing and abandon interrupted proposal',expected_epoch=epoch)
                    self.assertEqual(response.json()['status'],'applied')
                    self.assertEqual(send('resume','resume',expected_epoch=epoch).json()['status'],'pending')
            finally:store.close()


class DurableSSETests(unittest.IsolatedAsyncioTestCase):
    async def test_sqlite_committed_sequence_and_no_rollback_event(self):
        from dataclasses import replace
        from app.persistence.store import StoreError
        with TemporaryDirectory() as tmp:
            store=SQLiteStateStore(Path(tmp)/'state.db')
            try:
                store.create_project(ProjectState('p','P','G'))
                with self.assertRaises(StoreError):
                    store.atomic_update('p',lambda p:(p,(DomainEvent('p','uncommitted',{}),)))
                store.atomic_update('p',lambda p:(replace(p,name='changed'),(DomainEvent('p','committed',{}),)))
                service=ControlService(store,None)
                async def connected():return False
                stream=event_stream(service,'p',0,connected)
                frames=[await anext(stream),await anext(stream)]
                await stream.aclose()
                self.assertEqual([int(f.splitlines()[0][4:]) for f in frames],[1,2])
                self.assertNotIn('uncommitted',''.join(frames))
                data=json.loads(frames[1].split('data: ')[1].strip())
                self.assertEqual(data['sequence'],2)
            finally:store.close()
