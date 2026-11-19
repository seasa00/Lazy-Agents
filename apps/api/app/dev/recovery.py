"""M4.2 operator CLI and disposable crash fixtures; no live provider or automatic resume."""
import argparse
from dataclasses import asdict, is_dataclass, replace
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from app.dev.workflow import make_runner, approve_generated, ScriptedWorkflowProvider
from app.dev.workspace import make_workspace_runner, WorkspaceFixtureProvider, request
from app.domain.recovery import OperationStage
from app.persistence.sqlite import SQLiteStateStore
from app.orchestration.recovery import RecoveryCoordinator
from app.orchestration.runner import WorkflowRunner
from app.tools.gateway import WorkspaceToolGateway
from app.permissions.policy import WorkspacePolicy

CRASH_EXIT = 73


def encode(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


class ResumedSyntheticProvider(ScriptedWorkflowProvider):
    def complete(self, req):
        response = super().complete(req)
        if req.context['workflow']['phase'] == 'review':
            response = replace(response, output={**response.output, 'review_id': req.invocation_id + ':review'})
        return response


class ResumedWorkspaceProvider(WorkspaceFixtureProvider):
    def complete(self, req):
        response = super().complete(req)
        if req.context['workflow']['phase'] == 'review':
            response = replace(response, output={**response.output, 'review_id': req.invocation_id + ':review'})
        return response


def crash_fixture(base, scenario):
    base.mkdir(parents=True, exist_ok=False)
    with SQLiteStateStore(base / 'state.db') as store:
        if scenario in {'A','B','C'}:
            workspace = base / 'workspace'
            workspace.mkdir()
            (workspace / 'greeting.txt').write_text('hello\n')
            runner = make_workspace_runner(workspace, store=store)
        else:
            runner = make_runner(ScriptedWorkflowProvider(('FAIL','PASS')) if scenario == 'D' else None, store=store)
            approve_generated(runner)
            runner.step()
        marker = {'scenario': scenario, 'project_id': runner.project_id, 'run_id': runner.run_id}
        (base / 'fixture.json').write_text(json.dumps(marker))
        if scenario in {'A','B'}:
            old = runner.file_tool(request(runner,'read',path='greeting.txt'))
            sink = runner.workspace_gateway.operation_sink
            def interrupted(op):
                if op.operation == 'write' and ((scenario == 'A' and op.stage is OperationStage.EXECUTING)
                                                or (scenario == 'B' and op.stage is OperationStage.SETTLED)):
                    os._exit(CRASH_EXIT)
                return sink(op)
            runner.workspace_gateway.operation_sink = interrupted
            runner.file_tool(request(runner,'write',path='greeting.txt',expected_hash=old.content_hash,content='hello world\n'))
        elif scenario == 'C':
            old = runner.file_tool(request(runner,'read',path='greeting.txt'))
            runner.file_tool(request(runner,'write',path='greeting.txt',expected_hash=old.content_hash,content='hello world\n'))
            runner.provider.hook = lambda _: os._exit(CRASH_EXIT)
            runner.step()
        elif scenario == 'D':
            # One committed FAIL and revision, then interrupt Reviewer on attempt 2.
            while len(runner.run.workflow.submissions) < 2:
                runner.step()
            assert len(runner.run.workflow.reviews) == 1 and runner.run.phase == 'review'
            runner.provider.hook = lambda _: os._exit(CRASH_EXIT)
            runner.step()
        else:
            runner.controls.instruct('Retain this queued fixture instruction')
            runner.controls.pause()
            os._exit(CRASH_EXIT)
    raise AssertionError('fixture did not hit its interruption boundary')


def fixture_runner(store, marker):
    run = store.get_project(marker['project_id']).run(marker['run_id'])
    root = store.get_project(marker['project_id']).workspace_root
    gw = WorkspaceToolGateway(WorkspacePolicy(root)) if root else None
    provider = ResumedWorkspaceProvider() if root else ResumedSyntheticProvider()
    return WorkflowRunner(store, marker['project_id'], run.id, provider, gateway=gw)


def summary(store, p, r):
    info = RecoveryCoordinator(store).inspect(p,r)
    metadata = store.get_run_metadata(p,r)
    wf = metadata.workflow
    info['counters'] = {k:getattr(wf,k) for k in ('invocations','llm_calls','iterations','tasks_created','replans')}
    info['limits'] = wf.limits
    info['usage'] = store.usage(p,r)
    try:
        run = store.get_project(p).run(r)
        info.update(attempts=[a.id for a in run.workflow.attempts],
                    submissions=[s.id for s in run.workflow.submissions],
                    reviews=[(v.result.review_id,v.submission_id,v.number) for v in run.workflow.reviews])
    except Exception as exc:
        from app.persistence.models import ArtifactIntegrityError
        if not isinstance(exc, ArtifactIntegrityError):
            raise
        info['artifact_error'] = str(exc)
    return info


def command(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    fixture=sub.add_parser('fixture-crash',help='create a NEW disposable fixture and exit abruptly with code 73')
    fixture.add_argument('scenario',choices=list('ABCDE'))
    fixture.add_argument('directory',type=Path)
    demo=sub.add_parser('demo',help='run all five scenarios in separate child processes')
    demo.add_argument('--directory',type=Path)
    for name in ('list','inspect','resolve','resume'):
        cmd=sub.add_parser(name)
        cmd.add_argument('database',type=Path)
        if name != 'list':
            cmd.add_argument('--project',required=True)
            cmd.add_argument('--run',required=True)
        if name == 'resolve':
            cmd.add_argument('--operation',required=True)
            cmd.add_argument('--action',required=True,choices=('verify-file','verify-capture','verify-artifacts','abandon-provider','accept-result','acknowledge-command','acknowledge-file','abandon-read'))
            cmd.add_argument('--reason',required=True)
            cmd.add_argument('--quiescent',action='store_true')
        if name in ('resolve','resume'):
            cmd.add_argument('--epoch',type=int)
        if name == 'resume':
            cmd.add_argument('--execute-fixture',action='store_true',help='explicitly execute only this CLI disposable fixture')
    args=parser.parse_args(argv)
    if args.command == 'fixture-crash':
        crash_fixture(args.directory.resolve(),args.scenario)
    if args.command == 'demo':
        if args.directory:
            args.directory.mkdir(parents=True,exist_ok=False)
            return demonstration(args.directory.resolve())
        with TemporaryDirectory(prefix='m42-process-demo-') as tmp:
            return demonstration(Path(tmp))
    if not args.database.is_file():
        parser.error('database must already exist')
    with SQLiteStateStore(args.database) as store:
        recovery=RecoveryCoordinator(store)
        recovery.startup()
        if args.command == 'list':
            return {'interrupted_runs':recovery.list_interrupted()}
        p,r=args.project,args.run
        if args.command == 'resolve':
            runner=None
            if args.action == 'accept-result':
                marker_path=args.database.parent/'fixture.json'
                if not marker_path.is_file():
                    parser.error('saved proposal admission in this dev CLI requires a controlled fixture; use the coordinator with your bound runner otherwise')
                marker=json.loads(marker_path.read_text())
                if (p,r)!=(marker['project_id'],marker['run_id']):
                    parser.error('fixture identity mismatch')
                runner=fixture_runner(store,marker)
            recovery.resolve(p,r,args.operation,action=args.action,reason=args.reason,quiescent=args.quiescent,
                             expected_epoch=args.epoch,runner=runner)
        elif args.command == 'resume':
            recovery.resume(p,r,expected_epoch=args.epoch)
            if args.execute_fixture:
                marker_path=args.database.parent/'fixture.json'
                if not marker_path.is_file():
                    parser.error('fixture execution requires this CLI fixture marker')
                marker=json.loads(marker_path.read_text())
                if (p,r)!=(marker['project_id'],marker['run_id']):
                    parser.error('fixture identity mismatch')
                runner=fixture_runner(store,marker)
                if marker['scenario']=='A':
                    # This new mutation is explicitly authorized by --execute-fixture,
                    # not replayed by startup, inspection, reconciliation or resume.
                    old=runner.file_tool(request(runner,'read',path='greeting.txt'))
                    runner.file_tool(request(runner,'write',path='greeting.txt',expected_hash=old.content_hash,content='hello world\n'))
                runner.run_until_stopped()
        return summary(store,p,r)


def invoke(*args, expected=0):
    result=subprocess.run([sys.executable,'-m','app.dev.recovery',*map(str,args)],capture_output=True,text=True)
    if result.returncode != expected:
        raise AssertionError(f'fixture command exit {result.returncode}: {result.stderr}')
    return json.loads(result.stdout) if result.stdout else None


def demonstration(base):
    results=[]
    for scenario in 'ABCDE':
        folder=base/scenario
        invoke('fixture-crash',scenario,folder,expected=CRASH_EXIT)
        marker=json.loads((folder/'fixture.json').read_text())
        db=folder/'state.db'
        identifiers=('--project',marker['project_id'],'--run',marker['run_id'])
        interrupted=invoke('inspect',db,*identifiers)
        repeated=invoke('inspect',db,*identifiers)
        assert interrupted==repeated, 'inspection must be idempotent across processes'
        if scenario in {'A','B'}:
            assert (folder/'workspace'/'greeting.txt').read_text()==('hello\n' if scenario=='A' else 'hello world\n')
        issues=interrupted['recovery']['issues']
        for issue in issues:
            if not issue['resolved']:
                action='verify-file' if issue['kind']=='file' else 'abandon-provider'
                invoke('resolve',db,*identifiers,'--operation',issue['id'],'--action',action,
                       '--reason','Controlled disposable fixture inspection; retain unknown billing')
        if scenario=='D':
            assert len(interrupted['reviews'])==1 and len(interrupted['submissions'])==2
        if scenario=='E':
            assert interrupted['status']=='paused'
        finished=invoke('resume',db,*identifiers,'--execute-fixture')
        assert finished['status']=='completed', finished
        if scenario in {'C','D'}:
            assert finished['usage']['total_tokens'] is None
        if scenario=='D':
            assert len(finished['reviews'])==2 and len(finished['submissions'])==2
            assert finished['reviews'][0]==interrupted['reviews'][0]
        results.append({'scenario':scenario,'interrupted_status':interrupted['status'],
            'classification':[(i['kind'],i['certainty']) for i in issues],
            'automatic_execution':False,'explicit_resume_status':finished['status'],
            'provider_calls':finished['usage']['provider_calls'], 'total_tokens':finished['usage']['total_tokens'],
            'attempts':len(finished['attempts']),'reviews':len(finished['reviews'])})
    return {'scenarios':results,'directory':str(base),'all_passed':True}


if __name__=='__main__':
    print(json.dumps(command(),default=encode,indent=2))
