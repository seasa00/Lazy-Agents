"""Disposable real HTTP/SSE M4.3 verification, no provider network calls."""
import json
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from threading import Event, Thread
import time
import httpx
import uvicorn
from app.main import create_app
from app.dev.workflow import ScriptedWorkflowProvider
from app.orchestration.runner import WorkflowRunner
from app.persistence.sqlite import SQLiteStateStore


def main():
    with TemporaryDirectory(prefix='m43-http-') as tmp:
        store = SQLiteStateStore(Path(tmp)/'state.db')
        entered, release = Event(), Event()
        def hook(request):
            if request.context['workflow']['phase'] == 'develop':
                entered.set()
                release.wait(5)
        provider = ScriptedWorkflowProvider(hook=hook)
        app = create_app(store=store, runner_factory=lambda s,p,r: WorkflowRunner(s,p,r,provider))
        sock = socket.socket()
        sock.bind(('127.0.0.1',0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning'))
        thread = Thread(target=server.run, kwargs={'sockets':[sock]}, daemon=True)
        thread.start()
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=5) as client:
                for _ in range(200):
                    if server.started:break
                    time.sleep(.01)
                body={'name':'HTTP fixture','goal':'Synthetic greeting','requirements':[
                    {'id':'r1','description':'Greeting','acceptance_criteria':['Synthetic output is documented']}]}
                ack=client.post('/projects',json=body,headers={'Idempotency-Key':'create'}).json()
                pid=ack['project_id']; base=f'/projects/{pid}'
                assert client.post('/projects',json=body,headers={'Idempotency-Key':'create'}).json()==ack
                def snapshot():return client.get(base+'/snapshot').json()
                def command(action,rid=None):
                    path=base+'/plan' if action=='plan' else base+f'/runs/{rid}/{action}'
                    response=client.post(path,json={'expected_version':snapshot()['project']['version']},
                                         headers={'Idempotency-Key':action})
                    response.raise_for_status()
                    assert response.json()['status']!='rejected',response.text
                    return response.json()
                def wait_status(status):
                    for _ in range(300):
                        snap=snapshot()
                        if snap['project']['runs'][-1]['status']==status:return snap
                        time.sleep(.01)
                    raise AssertionError(f'missing {status}')
                rid=command('plan')['run_id'];wait_status('awaiting_approval')
                command('approve',rid)
                snap=snapshot(); cursor=snap['event_cursor']
                # Open a real socket stream and then disconnect during provider work.
                with client.stream('GET',base+'/events',params={'after':0}) as response:
                    assert response.status_code==200
                    assert response.headers['content-type'].startswith('text/event-stream')
                    first=next(line for line in response.iter_lines() if line.startswith('id: '))
                    first_id=int(first[4:])
                    command('start',rid)
                    assert entered.wait(2)
                    assert client.get(base+'/snapshot').status_code==200
                    command('pause',rid)
                release.set();wait_status('paused')
                command('resume',rid)
                final=wait_status('completed')
                # Last-Event-ID takes precedence even over an unavailable query cursor.
                ids=[]
                with client.stream('GET',base+'/events',params={'after':999999},
                                   headers={'Last-Event-ID':str(cursor)}) as response:
                    assert response.status_code==200
                    for line in response.iter_lines():
                        if line.startswith('id: '):
                            ids.append(int(line[4:]))
                            if ids[-1]==final['event_cursor']:break
                expected=[e.sequence for e in store.events(pid,after_sequence=cursor)]
                assert ids==expected,(ids,expected)
                assert len(provider.requests)==6
                print(json.dumps({'result':'PASS','workflow':'completed','provider_calls':6,
                    'first_event':first_id,'snapshot_cursor':cursor,'replayed_events':len(ids),
                    'final_cursor':final['event_cursor'],'disconnect_did_not_stop_execution':True,
                    'responsive_during_provider_io':True,'last_event_id_precedence':True}))
        finally:
            release.set()
            server.should_exit=True
            thread.join(10)
            assert not thread.is_alive(),'server shutdown did not settle'
            sock.close()
            store.close()


if __name__=='__main__':main()
