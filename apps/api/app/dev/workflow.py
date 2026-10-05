"""M2.2 deterministic scenarios and opt-in bounded OpenRouter workflow."""
import argparse
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from threading import Event, Thread
from app.agents.contracts import Requirement
from app.agents.runtime import AgentRuntime
from app.domain.agents import default_agent_definitions
from app.domain.projects import ProjectState, RunStatus
from app.orchestration.runner import WorkflowRunner
from app.orchestration.limits import ExecutionLimits
from app.persistence.memory import InMemoryStateStore
from app.providers.base import ProviderCapabilities, ProviderResponse, UsageSnapshot
from app.providers.openrouter import OpenRouterProviderConfig, OpenRouterResponsesProvider
from app.usage.pricing import PricingTable


class ScriptedWorkflowProvider:
    name = 'controlled-workflow-fixture'
    capabilities = ProviderCapabilities(structured_outputs=True, usage=True)

    def __init__(self, verdicts=('PASS',), *, tasks=1, hook=None):
        self.verdicts, self.task_count, self.hook = verdicts, tasks, hook
        self.requests = []
        self.review_count = 0

    def complete(self, request):
        self.requests.append(request)
        if self.hook:
            self.hook(request)
        c, w = request.context, request.context['workflow']
        phase = w['phase']
        if phase == 'plan':
            prefix = f't{len(w["existing_task_ids"])}-'
            output = {'summary': 'Controlled demonstration', 'requirements': c['requirements'],
                'tasks': [{'id': prefix + str(i), 'title': f'Task {i}', 'description': 'Produce synthetic evidence.',
                    'assignee': 'developer', 'acceptance_criteria': ['Synthetic output is documented'],
                    'dependencies': [] if i == 0 else [prefix + str(i - 1)]} for i in range(self.task_count)],
                'assumptions': ['In-memory evidence only'], 'decisions': []}
        elif phase in {'assign', 'decide'}:
            if phase == 'assign':
                action, task_id = 'assign_task', w['ready_task_ids'][0]
            else:
                action = 'accept_submission' if w['review']['verdict'] == 'PASS' else 'request_revision'
                task_id = w['task_id']
            output = {'action': action, 'task_id': task_id, 'reason': 'Follow validated evidence',
                      'revision_instructions': ['Address the reported synthetic defect'] if action == 'request_revision' else []}
        elif phase == 'develop':
            output = {'submission_id': w['submission_id'], 'task_id': c['current_task']['id'],
                'output_version': w['output_version'], 'summary': 'Synthetic implementation',
                'changed_files': [{'path': 'memory-artifact', 'change_type': 'modified', 'summary': 'Synthetic output is documented'}],
                'tests': [{'name': 'synthetic-check', 'status': 'passed', 'summary': 'In-memory fixture validation'}],
                'ready_for_review': True, 'notes': ['No real files or commands']}
        elif phase == 'review':
            verdict = self.verdicts[min(self.review_count, len(self.verdicts) - 1)]
            self.review_count += 1
            output = {'review_id': f'review-{len(self.requests)}', 'submission_id': c['submission']['id'],
                'verdict': verdict, 'summary': 'Controlled review',
                'assessments': [{'criterion_id': k, 'passed': verdict == 'PASS', 'evidence': w['evidence'][0],
                                 'notes': 'Synthetic only'} for k in w['criteria']],
                'findings': [] if verdict == 'PASS' else [{'id': 'f1', 'severity': 'major',
                    'summary': 'Controlled defect', 'evidence': 'Fixture-selected defect', 'criterion_id': 'c1'}],
                'checks_not_performed': ['Real filesystem and shell execution']}
        else:
            output = {'status': 'completed', 'summary': 'All synthetic submissions accepted',
                'completed_task_ids': w['completed_task_ids'], 'evidence_refs': w['evidence_refs'],
                'limitations': ['Controlled in-memory evidence only']}
        return ProviderResponse(output, request.model, f'fixture-{len(self.requests)}', usage=UsageSnapshot(10, 5))


def make_runner(provider=None, *, limits=ExecutionLimits(), runtime=None, definitions=None):
    store = InMemoryStateStore()
    requirement = Requirement('req-1', 'Produce a synthetic in-memory artifact describing a greeting.',
                              ('Synthetic output is documented',))
    store.create_project(ProjectState('demo', 'M2.2', 'Produce one bounded synthetic greeting artifact; no real files or commands.',
                                      requirements=(requirement,)))
    run = store.create_run('demo', run_id='run-demo')
    runner = WorkflowRunner(store, 'demo', run.id, provider or ScriptedWorkflowProvider(), runtime=runtime, definitions=definitions)
    runner.initialize(limits)
    return runner


def approve_generated(runner):
    runner.run_until_stopped()
    if runner.run.status is not RunStatus.AWAITING_APPROVAL:
        raise ValueError(runner.run.workflow.blocked_reason or 'plan was not generated')
    runner.approve()


def scenario(name):
    verdicts = {'A': ('PASS',), 'B': ('FAIL', 'PASS'), 'C': ('FAIL',)}.get(name, ('PASS',))
    entered, release = Event(), Event()
    def slow(request):
        if request.context['workflow']['phase'] == 'develop':
            entered.set()
            if not release.wait(10):
                raise ValueError('controlled operation timed out')
    provider = ScriptedWorkflowProvider(verdicts, hook=slow if name in {'D', 'E'} else None)
    runner = make_runner(provider)
    approve_generated(runner)
    detail = ''
    if name in {'D', 'E'}:
        runner.step()  # assignment
        thread = Thread(target=runner.step)
        thread.start()
        if not entered.wait(5):
            release.set()
            thread.join(5)
            raise AssertionError('controlled operation did not start')
        if name == 'D':
            runner.controls.pause()
        else:
            runner.controls.cancel()
        release.set()
        thread.join(5)
        if thread.is_alive():
            raise AssertionError('controlled operation did not stop')
        count = len(provider.requests)
        runner.step()
        assert len(provider.requests) == count
        if name == 'D':
            assert runner.run.status is RunStatus.PAUSED
            runner.controls.resume()
            runner.run_until_stopped()
            assert runner.run.status is RunStatus.COMPLETED
            detail = 'paused at boundary; no next call; resumed and completed'
        else:
            assert runner.run.status is RunStatus.CANCELED and not runner.run.workflow.submissions
            assert any(e.type == 'operation.stale_ignored' for e in runner.store.events('demo'))
            detail = 'late result ignored; usage retained'
    else:
        runner.run_until_stopped()
        assert runner.run.status is (RunStatus.WAITING_FOR_USER if name == 'C' else RunStatus.COMPLETED)
        assert len(runner.run.workflow.reviews) == {'A': 1, 'B': 2, 'C': 3}[name]
    return {'scenario': name, 'status': runner.run.status.value,
            'review_rounds': len(runner.run.workflow.submissions),
            'calls': runner.run.workflow.llm_calls, 'detail': detail or runner.run.workflow.blocked_reason}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', choices=['A', 'B', 'C', 'D', 'E', 'all', 'live'])
    parser.add_argument('--model', default='openai/gpt-4o-mini')
    args = parser.parse_args(argv)
    if args.scenario != 'live':
        for name in 'ABCDE' if args.scenario == 'all' else args.scenario:
            print(json.dumps(scenario(name)))
        return 0
    try:
        config = OpenRouterProviderConfig(timeout_seconds=30)
        provider = OpenRouterResponsesProvider(config)
        definitions = {k: replace(d, model=args.model) for k, d in default_agent_definitions().items()}
        pricing = PricingTable.from_json(Path(__file__).resolve().parents[4] / 'config/model-pricing/openrouter.json')
        runner = make_runner(provider, definitions=definitions, runtime=AgentRuntime(pricing=pricing),
            limits=ExecutionLimits(max_tasks=1, max_invocations=16, max_llm_calls=24, max_iterations=24))
        approve_generated(runner)
        runner.run_until_stopped()
        wf = runner.run.workflow
        print(json.dumps({'status': runner.run.status.value, 'blocked_reason': wf.blocked_reason,
            'model': args.model, 'calls': [c.to_dict() for c in wf.call_records],
            'review_rounds': len(wf.submissions),
            'estimated_usd': (str(sum((c.estimated_cost.amount for c in wf.call_records), Decimal(0)))
                              if wf.call_records and all(c.estimated_cost is not None for c in wf.call_records) else None)}))
        return 0 if runner.run.status is RunStatus.COMPLETED else 2
    except ValueError as exc:
        print(json.dumps({'status': 'not_verified', 'reason': str(exc)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
