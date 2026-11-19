"""M4.1 controlled fixture creation and inspection across separate processes.

Creation requires a new disposable directory; inspection never resumes execution.
"""
import argparse
from decimal import Decimal
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
from app.agents.runtime import AgentRuntime
from app.dev.commands import command_request, approve_fixture
from app.dev.workspace import make_workspace_runner, request
from app.domain.commands import CommandProfile
from app.persistence.sqlite import SQLiteStateStore
from app.usage.pricing import PricingTable, PriceSnapshot

SECRET_SENTINEL = 'm41-fake-api-credential-DO-NOT-PERSIST'
ENV_SENTINEL = 'm41-protected-env-content-DO-NOT-PERSIST'


def inspect(store):
    project = store.get_project('workspace-demo')
    run = project.runs[0]
    wf = run.workflow
    events = store.events(project.id)
    usage = store.usage(project.id)
    calls = wf.call_records
    assert usage['provider_calls'] == len(calls)
    assert usage['total_tokens'] == sum(c.usage.total_tokens for c in calls)
    assert usage['estimated_cost'] == sum((c.estimated_cost.amount for c in calls), Decimal(0))
    for agent, totals in usage['per_agent'].items():
        invocation_ids = {i.id for i in wf.invocation_records if i.agent_id == agent}
        selected = [c for c in calls if c.invocation_id in invocation_ids]
        assert totals['total_tokens'] == sum(c.usage.total_tokens for c in selected)
        assert totals['estimated_cost'] == sum((c.estimated_cost.amount for c in selected), Decimal(0))
    dump = '\n'.join(store.connection.iterdump())
    for marker in (SECRET_SENTINEL, ENV_SENTINEL, 'hello world\\n'):
        assert marker not in dump
    assert store.connection.execute('PRAGMA foreign_key_check').fetchall() == []
    assert store.connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert run.status.value == 'completed' and wf.command_results[0].succeeded
    assert wf.submissions[0].files.files[0].content == b'hello world\n'
    assert wf.submissions[0].files.tests[0].passed
    tables = ('projects','agents','runs','tasks','dependencies','attempts','submissions','reviews',
              'decisions','artifact_metadata','artifacts','invocations','llm_calls','command_results',
              'tool_records','interventions','events')
    return {'status': run.status.value, 'project': project.id,
            'tasks': [t.id for t in project.tasks], 'attempts': [a.id for a in wf.attempts],
            'reviews': [r.result.review_id for r in wf.reviews],
            'submission_digest': wf.submissions[0].digest,
            'artifact_hash': wf.submissions[0].files.files[0].content_hash,
            'event_ids': [e.event_id for e in events], 'last_sequence': events[-1].sequence,
            'call_records': [c.to_dict() for c in calls], 'usage': usage,
            'tool_records': [asdict(store.codec.loads(data)) for data, in store.connection.execute('SELECT data FROM tool_records ORDER BY rowid')],
            'artifact_metadata': store.connection.execute('SELECT path,content_hash,before_hash FROM artifact_metadata').fetchall(),
            'table_counts': {t: store.connection.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in tables},
            'integrity_check': 'ok', 'secret_scan': 'passed', 'workspace_files_outside_sqlite': True}


def create(base):
    base.mkdir(parents=True, exist_ok=False)
    workspace = base / 'workspace'
    workspace.mkdir()
    (workspace / 'greeting.txt').write_text('hello\n')
    (workspace / '.env').write_text('PRIVATE_FIXTURE=' + ENV_SENTINEL)
    (workspace / 'test_greeting.py').write_text(
        "from pathlib import Path\nassert Path('greeting.txt').read_text() == 'hello world\\n'\nprint('1 test passed')\n")
    profile = CommandProfile('fixture-test', str(Path(sys.executable).resolve()), ('-I','-B','test_greeting.py'), True)
    price = PriceSnapshot('deterministic-mock-v1', 'USD', Decimal('1'), Decimal('0.5'), Decimal('2'), 'M4.1 fixture', '1')
    runtime = AgentRuntime(pricing=PricingTable({price.model: price}))
    previous = os.environ.get('OPENROUTER_API_KEY')
    os.environ['OPENROUTER_API_KEY'] = SECRET_SENTINEL
    try:
        with SQLiteStateStore(base / 'state.db') as store:
            runner = make_workspace_runner(workspace, command_profiles=(profile,), store=store, runtime=runtime)
            before = runner.file_tool(request(runner, 'read', path='greeting.txt'))
            runner.file_tool(request(runner, 'edit', path='greeting.txt', expected_hash=before.content_hash, old_text='hello', new_text='hello world'))
            req = command_request(runner, profile)
            runner.command_tool(req, approve_fixture(runner, req))
            runner.run_until_stopped()
            result = inspect(store)
            (base / 'expected.json').write_text(json.dumps(result, default=str, sort_keys=True))
            return result
    finally:
        if previous is None:
            os.environ.pop('OPENROUTER_API_KEY', None)
        else:
            os.environ['OPENROUTER_API_KEY'] = previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('create','inspect'))
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    base = args.directory.resolve()
    if args.action == 'create':
        result = create(base)
    else:
        if not (base / 'state.db').is_file():
            parser.error('verification database does not exist')
        with SQLiteStateStore(base / 'state.db') as store:
            result = inspect(store)
        assert json.loads(json.dumps(result, default=str)) == json.loads((base / 'expected.json').read_text())
        result['reopened_history_matches'] = True
    print(json.dumps(result, default=str, indent=2))


if __name__ == '__main__':
    main()
