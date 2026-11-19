"""Exact Decimal aggregation of call records, preserving unknown totals."""
from decimal import Decimal
from app.usage.records import UsageCompleteness


def aggregate(records, *, reviews=0):
    records = tuple(records)
    def totals(calls):
        calls = tuple(calls)
        usage_complete = all(c.usage is not None and c.usage_completeness is UsageCompleteness.COMPLETE for c in calls)
        cost_complete = usage_complete and all(c.estimated_cost is not None for c in calls)
        known_tokens = sum(c.usage.total_tokens for c in calls if c.usage is not None)
        known_cost = sum((c.estimated_cost.amount for c in calls if c.estimated_cost is not None), Decimal(0))
        return {'provider_calls': len(calls), 'retries': sum(c.attempt > 1 for c in calls),
                'total_tokens': known_tokens if usage_complete else None,
                'known_tokens': known_tokens, 'usage_complete': usage_complete,
                **{key: sum(getattr(c.usage, key) for c in calls if c.usage is not None) if usage_complete else None
                   for key in ('input_tokens', 'output_tokens', 'cached_input_tokens')},
                'estimated_cost': known_cost if cost_complete else None,
                'known_estimated_cost': known_cost, 'cost_complete': cost_complete}
    return {**totals(c for _, c in records), 'reviews': reviews,
            'per_agent': {agent: totals(c for a, c in records if a == agent) for agent in sorted({a for a, _ in records})}}


def effective_records(records, operations, runs):
    """One billable record per local call ID; late durable receipts enrich unknown history."""
    records = tuple(records)
    by_id = {c.call_id: (agent, c) for agent, c in records}
    agents = {i.id: i.agent_id for run in runs if run.workflow for i in run.workflow.invocation_records}
    # Metadata-only runs lack invocation collections; baseline rows still carry agent attribution.
    for op in operations:
        call = op.call_record
        if call is None or op.stage.value == 'prepared' or call.status == 'not_submitted':
            continue
        old = by_id.get(call.call_id)
        if old is None or old[1].usage is None:
            agent = old[0] if old else agents.get(call.invocation_id, op.operation)
            by_id[call.call_id] = (agent, call)
    return tuple(by_id.values())
