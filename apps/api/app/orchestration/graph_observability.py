"""LangGraph runtime facts in the existing durable event envelope.

Domain reducers remain the only writers of workflow success. These events carry
identities and outcomes, never model context, tool arguments, or reasoning.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import os
import re

from app.domain.agents import AgentKind, default_agent_definitions
from app.domain.artifacts import ToolCallRecord
from app.domain.commands import CommandAuditRecord
from app.domain.events import DomainEvent


class GraphObservabilityAdapter:
    def __init__(self, node_name: str):
        self.node_name = node_name

    @staticmethod
    def _refs(run, task_id=None, invocation_id=None):
        wf = run.workflow
        task_id = task_id or run.current_task_id
        attempt = next((a for a in reversed(wf.attempts) if a.task_id == task_id), None)
        submission = next((s for s in reversed(wf.submissions) if s.task_id == task_id), None)
        review = next((r for r in reversed(wf.reviews)
                       if submission and r.submission_id == submission.id), None)
        invocation = next((i for i in reversed(wf.invocation_records)
                           if i.id == invocation_id), None)
        return {'task_id': task_id, 'attempt_id': attempt.id if attempt else None,
                'submission_id': submission.id if submission else None,
                'review_id': review.result.review_id if review else None,
                'invocation_id': invocation_id,
                'agent_id': invocation.agent_id if invocation else None,
                'execution_generation': run.execution_generation}

    def started(self, project, run, invocation_id):
        refs = self._refs(run, invocation_id=invocation_id)
        return DomainEvent(project.id, 'graph.node_started',
            {'node_name': self.node_name, 'phase': run.phase,
             'operation_id': invocation_id, **refs}, run_id=run.id,
            task_id=refs['task_id'], correlation_id=invocation_id)

    def finished(self, project, before, after, invocation_id, committed_events):
        """Called inside the same reducer after domain validation has succeeded."""
        run = after.run(before.id)
        refs = self._refs(run, before.current_task_id or run.current_task_id, invocation_id)
        event_types = {e.type for e in committed_events}
        if 'developer.waiting_for_approval' in event_types or 'run.paused' in event_types:
            event_type, outcome = 'graph.node_interrupted', 'waiting'
        elif 'run.blocked' in event_types or 'operation.stale_ignored' in event_types:
            event_type, outcome = 'graph.node_failed', 'blocked_or_stale'
        else:
            event_type, outcome = 'graph.node_completed', 'committed'
        return DomainEvent(project.id, event_type,
            {'node_name': self.node_name, 'phase': before.phase,
             'operation_id': invocation_id, 'outcome': outcome,
             'committed_event_types': sorted(event_types), **refs},
            run_id=run.id, task_id=refs['task_id'], correlation_id=invocation_id,
            causation_id=committed_events[-1].event_id if committed_events else None)

    def invocation_finished(self, project, before, node_event):
        suffix = node_event.type.removeprefix('graph.node_')
        event_type = {'completed': 'graph.invocation_completed',
                      'interrupted': 'graph.invocation_interrupted',
                      'failed': 'graph.invocation_failed'}[suffix]
        return DomainEvent(project.id, event_type,
            dict(node_event.payload), run_id=before.id, task_id=node_event.task_id,
            correlation_id=node_event.correlation_id, causation_id=node_event.causation_id)


# This projection deliberately selects safe fields. It never serializes a model
# request, continuation context, arbitrary operation proposal, or raw reasoning.
_SECRET_PATTERNS = (
    re.compile(r'\b(?:sk|rk|pk)-[A-Za-z0-9_-]{8,}\b'),
    re.compile(r'\bgh[pousr]_[A-Za-z0-9_]{16,}\b'),
    re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    re.compile(r'\bBearer\s+[A-Za-z0-9._~+/=-]{8,}', re.I),
    re.compile(r'(?i)(?:(?:api[_-]?key|secret|token|password|credential|authorization)\s*[:=]\s*)([^\s,;}]+)'),
    re.compile(r'://[^\s:@/]+:[^@\s/]+@'),
)


def redact_text(value):
    text = str(value or '')
    for key, secret in os.environ.items():
        if secret and any(word in key.lower() for word in ('secret', 'password', 'api_key', 'token', 'credential')):
            text = text.replace(secret, '[REDACTED]')
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub('[REDACTED]', text)
    return text


def _agent_for_event(event, invocations, tool_records, operations):
    payload = event.payload
    if payload.get('agent_id'):
        return payload['agent_id']
    if payload.get('invocation_id') in invocations:
        return invocations[payload['invocation_id']].agent_id
    if payload.get('operation_id') in invocations:
        return invocations[payload['operation_id']].agent_id
    if event.type == 'usage.recorded':
        return invocations.get(payload.get('invocation_id'), None).agent_id if payload.get('invocation_id') in invocations else None
    if event.type == 'tool.audit':
        record = tool_records.get(payload.get('record_id'))
        return 'developer' if record and (isinstance(record, CommandAuditRecord) or record.actor == 'developer') else None
    if event.type == 'execution.operation_recorded':
        op = operations.get(payload.get('operation_id'))
        return invocations.get(op.checkpoint.invocation_id, None).agent_id if op and op.checkpoint.invocation_id in invocations else None
    if event.type in {'review.completed'}:
        return 'reviewer'
    if event.type in {'submission.admitted', 'developer.waiting_for_approval', 'developer.continuation_resumed',
                      'developer.tool_continuation_completed', 'command.launch', 'command.completed',
                      'command.permission_decided', 'command.permission_requested'}:
        return 'developer'
    if event.type in {'plan.proposed', 'task.assigned', 'task.accepted', 'revision.requested', 'run.completed'}:
        return 'manager'
    return None


def _trace_fact(event, record=None):
    """Return type, text, severity for a committed event, or None if it is noise."""
    kind, payload = event.type, event.payload
    if kind == 'run.started':
        return 'task', 'Workflow started', 'info'
    if kind == 'graph.node_started':
        return 'task', f"{payload['node_name']} node started", 'info'
    if kind == 'graph.node_completed':
        return 'task', f"{payload['node_name']} node completed", 'ok'
    if kind == 'graph.node_interrupted':
        return 'event', f"{payload['node_name']} node interrupted", 'warn'
    if kind == 'graph.node_failed':
        return 'error', f"{payload['node_name']} node failed or stale", 'error'
    if kind == 'graph.invocation_completed':
        return 'llm', 'Agent invocation completed', 'ok'
    if kind == 'graph.invocation_interrupted':
        return 'llm', 'Agent invocation interrupted', 'warn'
    if kind == 'graph.invocation_failed':
        return 'error', 'Agent invocation failed', 'error'
    if kind == 'operation.started':
        return 'llm', 'Agent invocation started', 'info'
    if kind == 'execution.operation_recorded' and payload.get('kind') == 'provider':
        if payload.get('stage') == 'executing':
            return 'llm', 'LLM call started', 'info'
        if payload.get('stage') == 'settled':
            return 'llm', 'LLM call result recorded', 'ok' if payload.get('certainty') == 'confirmed_success' else 'error'
    if kind == 'usage.recorded' and (payload.get('attempt', 1) > 1 or payload.get('purpose') == 'repair'):
        return 'retry', 'Provider retry or structured repair recorded', 'warn'
    if kind == 'tool.audit' and isinstance(record, ToolCallRecord):
        if record.id.endswith(':intent'):
            return 'tool', f'Tool request: {record.operation}', 'info'
        return 'tool', f'Tool result: {record.operation} — {record.outcome}', 'ok' if record.outcome == 'succeeded' else 'error'
    if kind == 'tool.audit' and isinstance(record, CommandAuditRecord) and record.action == 'request':
        return 'tool', 'Command/test tool requested', 'info' if record.outcome == 'pending' else 'error'
    if kind == 'developer.tool_call_started':
        return 'tool', 'Developer tool call started', 'info'
    if kind == 'developer.tool_result_saved':
        return 'tool', 'Developer tool result saved', 'ok'
    if kind == 'developer.waiting_for_approval':
        return 'event', 'Waiting for command approval', 'warn'
    if kind == 'developer.continuation_resumed':
        return 'event', 'Developer continuation resumed', 'info'
    if kind == 'command.permission_decided':
        return 'decision', 'Permission approved' if payload.get('approved') else 'Permission denied', 'ok' if payload.get('approved') else 'warn'
    if kind == 'command.launch':
        return 'tool', 'Command execution started' if payload.get('outcome') == 'started' else 'Command execution rejected', 'info' if payload.get('outcome') == 'started' else 'error'
    if kind == 'command.completed':
        return 'test', f"Command/test result: {payload.get('outcome', 'unknown')}", 'ok' if payload.get('outcome') == 'succeeded' else 'error'
    if kind == 'command.permission_requested':
        return 'tool', 'Command/test permission requested', 'info'
    if kind == 'submission.admitted':
        return 'handoff', 'Submission committed → Reviewer', 'ok'
    if kind == 'review.completed':
        return 'handoff', 'Review committed → Manager', 'ok'
    if kind == 'task.assigned':
        return 'handoff', 'Manager → Developer assignment committed', 'ok'
    if kind == 'revision.requested':
        return 'handoff', 'Manager → Developer revision committed', 'warn'
    if kind == 'task.accepted':
        return 'decision', 'Task accepted', 'ok'
    if kind == 'run.completed':
        return 'task', 'Workflow completed', 'ok'
    if kind in {'run.paused', 'run.resumed', 'run.canceled', 'run.blocked'}:
        return 'event' if kind != 'run.blocked' else 'error', kind.replace('.', ' ').capitalize(), 'warn' if kind != 'run.blocked' else 'error'
    if kind in {'developer.tool_continuation_uncertain', 'operation.stale_ignored'}:
        return 'error', kind.replace('.', ' ').capitalize(), 'error'
    return None


def _duration_ms(operation):
    try:
        start = datetime.fromisoformat(operation.started_at)
        end = datetime.fromisoformat(operation.updated_at)
        return max(0, round((end - start).total_seconds() * 1000))
    except (TypeError, ValueError):
        return None


def project_agent_debug(project, run, events, tool_history, operations, usage):
    """Project durable records to the existing Inspector's AgentDebugSnapshot shape."""
    wf = run.workflow
    definitions = default_agent_definitions()
    snapshots = {s.kind.value: s for s in wf.agent_snapshots} if wf else {}
    invocations = {i.id: i for i in wf.invocation_records} if wf else {}
    tool_records = {t.id: t for t in tool_history}
    operations = {o.id: o for o in operations}
    run_events = tuple(e for e in events if e.run_id == run.id)
    reviews_by_id = {r.result.review_id: r for r in wf.reviews} if wf else {}
    graph_starts = [e for e in run_events if e.type == 'graph.node_started']
    relevant = {kind.value: [] for kind in AgentKind}
    for event in run_events:
        owner = _agent_for_event(event, invocations, tool_records, operations)
        record = tool_records.get(event.payload.get('record_id')) if event.type == 'tool.audit' else None
        fact = _trace_fact(event, record)
        if not fact:
            continue
        if event.type == 'review.completed' and event.payload.get('review_id') in reviews_by_id:
            verdict = reviews_by_id[event.payload['review_id']].result.verdict.value
            fact = ('handoff', f'Reviewer {verdict} committed → Manager',
                    'ok' if verdict == 'PASS' else 'warn')
        if owner is None and event.type == 'run.blocked':
            owner = 'developer' if run.phase == 'develop' else 'reviewer' if run.phase == 'review' else 'manager'
        owners = {owner} if owner in relevant else set()
        if event.type == 'task.assigned':
            owners.update(('manager', 'developer'))
        elif event.type == 'submission.admitted':
            owners.update(('developer', 'reviewer'))
        elif event.type == 'review.completed':
            owners.update(('reviewer', 'manager'))
        elif event.type == 'revision.requested':
            owners.update(('manager', 'developer'))
        elif event.type in {'run.started', 'run.completed', 'run.canceled', 'run.paused', 'run.resumed'}:
            owners.update(relevant)
        payload = event.payload
        refs = {'project_id': project.id, 'run_id': run.id,
                'task_id': event.task_id or payload.get('task_id'),
                'attempt_id': payload.get('attempt_id'), 'agent_id': owner,
                'invocation_id': payload.get('invocation_id'),
                'execution_generation': payload.get('execution_generation', payload.get('generation')),
                'node_name': payload.get('node_name'),
                'operation_id': payload.get('operation_id'),
                'tool_request_id': payload.get('tool_request_id'),
                'permission_id': payload.get('approval_id'),
                'submission_id': payload.get('submission_id'),
                'review_id': payload.get('review_id'),
                'evidence_ref': payload.get('command_id'), 'sequence': event.sequence}
        if refs['review_id'] in reviews_by_id:
            review = reviews_by_id[refs['review_id']]
            refs['submission_id'] = review.submission_id
            refs['task_id'] = review.task_id
        if event.type == 'revision.requested' and refs['submission_id']:
            review = next((r for r in reversed(wf.reviews)
                           if r.submission_id == refs['submission_id']), None)
            if review:
                refs['review_id'] = review.result.review_id
        if event.type == 'tool.audit' and record:
            refs.update(attempt_id=record.attempt_id,
                tool_request_id=(record.id if record.id.endswith(':intent') else record.id + ':intent')
                    if isinstance(record, ToolCallRecord) else record.id,
                operation_id=record.id.removesuffix(':intent') if isinstance(record, ToolCallRecord) else None,
                permission_id=getattr(record, 'approval_id', None),
                evidence_ref=getattr(record, 'submission_id', None))
            graph_start = next((item for item in reversed(graph_starts)
                if item.sequence <= event.sequence and item.payload.get('attempt_id') == record.attempt_id), None)
            if graph_start:
                refs['invocation_id'] = graph_start.payload.get('invocation_id')
                refs['node_name'] = graph_start.payload.get('node_name')
                refs['execution_generation'] = graph_start.payload.get('execution_generation')
        for kind in owners:
            relevant[kind].append({'id': event.event_id, 'at': event.occurred_at,
                'type': fact[0], 'text': redact_text(fact[1]), 'severity': fact[2],
                'refs': refs})

    result = {}
    for kind in AgentKind:
        key = kind.value
        snap = snapshots.get(key) or definitions[kind].snapshot()
        trace = relevant[key]
        task_id = run.current_task_id
        active_kind = ('developer' if run.phase == 'develop' else 'reviewer' if run.phase == 'review'
                       else 'manager' if run.phase in {'plan', 'assign', 'decide', 'final'} else None)
        active = key == active_kind and run.active
        if not active:
            task_id = next((row['refs']['task_id'] for row in reversed(trace) if row['refs']['task_id']), None)
        task = next((t for t in project.tasks if t.id == task_id), None)
        attempts = tuple(a for a in wf.attempts if a.task_id == task_id) if wf else ()
        submissions = tuple(s for s in wf.submissions if s.task_id == task_id) if wf else ()
        reviews = tuple(r for r in wf.reviews if r.task_id == task_id) if wf else ()
        latest_graph = next((e for e in reversed(run_events) if e.type == 'graph.node_started'
                             and e.payload.get('agent_id') == snap.agent_id), None)
        if active and wf and wf.pending:
            status = {'manager': 'thinking', 'developer': 'working', 'reviewer': 'reviewing'}[key]
            action = f"{latest_graph.payload['node_name']} node" if latest_graph else f'{run.phase} invocation'
        elif active and wf and wf.pending_permissions and key == 'developer':
            status, action = 'blocked', 'Waiting for command approval'
        elif active and run.status.value in {'paused', 'waiting_for_user'}:
            status, action = 'blocked', 'Paused or waiting for user'
        else:
            status, action = 'idle', None
        calls = tuple(c for c in wf.call_records if invocations.get(c.invocation_id)
                      and invocations[c.invocation_id].agent_id == snap.agent_id) if wf else ()
        agent_usage = usage.get('per_agent', {}).get(snap.agent_id, {})
        provider_ops = [o for o in operations.values() if o.kind == 'provider' and
                        o.call_record and o.call_record.call_id in {c.call_id for c in calls}]
        last_call_latency = _duration_ms(provider_ops[-1]) if provider_ops else None
        tool_rows = []
        for record in tool_history:
            if isinstance(record, ToolCallRecord) and record.actor == key and not record.id.endswith(':intent'):
                op = operations.get(record.id)
                tool_rows.append({'id': record.id, 'tool': record.operation.upper(),
                    'input': redact_text(record.path), 'at': next((e.occurred_at for e in run_events
                        if e.type == 'tool.audit' and e.payload.get('record_id') == record.id), ''),
                    'durationMs': _duration_ms(op) if op else None,
                    'result': record.outcome, 'ok': record.outcome == 'succeeded',
                    'operationId': record.id, 'approvalStatus': None,
                    'evidenceRef': record.submission_id})
        if key == 'developer' and wf:
            for command in wf.command_results:
                tool_rows.append({'id': command.id, 'tool': 'COMMAND',
                    'input': redact_text(command.request.profile), 'at': command.started_at,
                    'durationMs': round(command.duration_seconds * 1000),
                    'result': command.outcome, 'ok': command.succeeded,
                    'operationId': next((o.id for o in operations.values() if o.kind == 'command' and
                        o.approval_id == command.approval_id), None),
                    'approvalStatus': 'consumed', 'evidenceRef': command.id + ':logs'})
        decisions, outputs, evidence = [], [], []
        if key == 'manager' and run.plan:
            outputs.append({'id': 'plan:' + run.id, 'kind': 'plan', 'title': 'Plan',
                            'body': redact_text(run.plan.summary)})
        if wf:
            if key == 'manager':
                for item in wf.revisions:
                    decisions.append({'id': 'revision:' + item.review_id, 'at': next((e.occurred_at for e in run_events
                        if e.type == 'revision.requested' and e.payload.get('review_id') == item.review_id), '',),
                        'decision': 'Revision requested', 'outcome': 'accepted',
                        'refs': [item.submission_id, item.review_id]})
                for submission_id in wf.accepted:
                    decisions.append({'id': 'accept:' + submission_id, 'at': '',
                        'decision': 'Submission accepted', 'outcome': 'accepted', 'refs': [submission_id]})
                if wf.final_result:
                    outputs.append({'id': 'final:' + run.id, 'kind': 'summary', 'title': 'Final result',
                        'body': redact_text(wf.final_result.summary)})
            if key == 'developer':
                for sub in wf.submissions:
                    outputs.append({'id': sub.id, 'kind': 'submission', 'title': f'Submission {sub.version}',
                        'body': redact_text(sub.output.summary)})
                    evidence.append({'id': sub.id, 'kind': 'submission', 'title': f'Submission {sub.version}',
                        'ref': sub.id, 'detail': f'Task {sub.task_id}'})
                    if sub.files:
                        for file in sub.files.files:
                            evidence.append({'id': sub.id + ':' + file.path, 'kind': 'file',
                                'title': redact_text(file.path), 'ref': sub.id + ':' + file.path})
                        for test in sub.files.tests:
                            evidence.append({'id': test.result.id, 'kind': 'test',
                                'title': 'Test command', 'ref': test.result.id + ':logs',
                                'severity': 'ok' if test.passed else 'error'})
            if key == 'reviewer':
                for review in wf.reviews:
                    decisions.append({'id': review.result.review_id, 'at': next((e.occurred_at for e in run_events
                        if e.type == 'review.completed' and e.payload.get('review_id') == review.result.review_id), ''),
                        'decision': 'Reviewer ' + review.result.verdict.value,
                        'outcome': 'accepted' if review.result.verdict.value == 'PASS' else 'rejected',
                        'refs': [review.submission_id, review.result.review_id]})
                    outputs.append({'id': review.result.review_id, 'kind': 'verdict',
                        'title': review.result.verdict.value, 'body': redact_text(review.result.summary)})
                    evidence.append({'id': review.result.review_id, 'kind': 'review',
                        'title': 'Review ' + review.result.verdict.value,
                        'ref': review.result.review_id, 'detail': 'Submission ' + review.submission_id})
        reads = Counter(r.path for r in tool_history if isinstance(r, ToolCallRecord)
                        and r.actor == key and r.operation == 'read' and not r.id.endswith(':intent'))
        signals = [{'id': 'repeated-read:' + redact_text(path), 'severity': 'info',
                    'observation': f'{redact_text(path)} was read {count} times',
                    'potential': 'Review whether repeated reads were necessary.'}
                   for path, count in reads.items() if count > 1]
        if key == 'developer' and len(reviews) > 1:
            signals.append({'id': 'revision-rounds', 'severity': 'warn',
                'observation': f'{len(reviews)} review rounds for this task',
                'potential': 'Review the retained findings before another revision.'})
        context_refs = [{'label': 'Project goal', 'source': 'persisted project'},
                        {'label': 'Project requirements', 'source': 'persisted requirements'}]
        if task:
            context_refs.append({'label': redact_text(task.title), 'source': 'persisted task'})
        if key == 'reviewer' and submissions:
            context_refs.append({'label': 'Submission ' + submissions[-1].id,
                                 'source': 'immutable submission'})
        if key == 'manager' and reviews:
            context_refs.append({'label': 'Review ' + reviews[-1].result.review_id,
                                 'source': 'persisted review'})
        result[key] = {'agentId': key, 'source': 'backend', 'name': redact_text(snap.name), 'role': redact_text(snap.role),
            'status': status, 'mode': 'live' if run.active else 'historical',
            'currentTask': task_id, 'currentAction': action, 'model': snap.model,
            'startedAt': trace[0]['at'] if trace else None,
            'attempt': f'Attempt {attempts[-1].number} · review round {len(reviews)}' if attempts else None,
            'lastEvent': trace[-1]['text'] if trace else None,
            'lastCallLatencyMs': last_call_latency,
            'prompt': {'instructions': redact_text(snap.system_instructions),
                       'taskPrompt': redact_text(task.description) if task else '',
                       'requirements': redact_text('\n'.join(r.description for r in project.requirements)),
                       'context': context_refs, 'structuredInputs': {'runId': run.id,
                           'taskId': task_id, 'attemptId': attempts[-1].id if attempts else None},
                       'modelConfig': {'model': snap.model, 'tools': list(snap.tools)}},
            'decisions': decisions, 'trace': trace, 'tools': tool_rows, 'outputs': outputs,
            'evidence': evidence,
            'usage': {'inputTokens': agent_usage.get('input_tokens'),
                      'outputTokens': agent_usage.get('output_tokens'),
                      'totalTokens': agent_usage.get('total_tokens'),
                      'estimatedCost': float(agent_usage['estimated_cost']) if agent_usage.get('estimated_cost') is not None else None,
                      'llmCalls': agent_usage.get('provider_calls', 0),
                      'retries': agent_usage.get('retries', 0),
                      'totalLatencyMs': sum(_duration_ms(o) or 0 for o in provider_ops),
                      'latency': {'llmMs': sum(_duration_ms(o) or 0 for o in provider_ops),
                                  'toolsMs': sum(_duration_ms(operations[r.id]) or 0 for r in tool_history
                                      if isinstance(r, ToolCallRecord) and r.id in operations and r.actor == key),
                                  'testsMs': sum(round(c.duration_seconds * 1000) for c in wf.command_results)
                                      if key == 'developer' else 0}},
            'runContext': {'runTotalTokens': usage.get('total_tokens'),
                           'reviewRounds': len(wf.reviews) if wf else 0},
            'optimizationSignals': signals}
    return result


def project_office_poses(run):
    poses = {kind.value: 'idle' for kind in AgentKind}
    if not run.workflow or not run.active:
        return poses
    if run.workflow.pending_permissions:
        poses['developer'] = 'blocked'
    elif run.status.value == 'waiting_for_user':
        poses['developer' if run.phase == 'develop' else 'reviewer' if run.phase == 'review' else 'manager'] = 'blocked'
    elif run.workflow.pending:
        key = 'developer' if run.phase == 'develop' else 'reviewer' if run.phase == 'review' else 'manager'
        poses[key] = {'developer': 'working', 'reviewer': 'reviewing', 'manager': 'thinking'}[key]
    return poses
