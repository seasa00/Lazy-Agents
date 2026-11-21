"""Interchangeable workflow coordinators over the same durable domain runner."""
from __future__ import annotations

from typing import Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from app.domain.projects import RunStatus
from app.orchestration.graph_observability import GraphObservabilityAdapter
from app.orchestration.runner import WorkflowRunner


class Orchestrator(Protocol):
    @property
    def run(self): ...

    def initialize(self, limits=...): ...
    def approve(self): ...
    def step(self) -> bool: ...
    def run_until_stopped(self): ...


class LegacyOrchestrator(WorkflowRunner):
    """The original coordinator and the default execution path."""


class WorkflowGraphState(TypedDict):
    run_id: str
    phase: str
    task_id: str | None
    attempt_id: str | None
    submission_id: str | None
    review_id: str | None
    execution_generation: int
    status: str
    progressed: bool


class LangGraphOrchestrator(WorkflowRunner):
    """Routes committed domain phases with LangGraph; SQLite remains authoritative.

    Each node executes one existing runner operation. No checkpointer is used:
    a fresh graph invocation reads the committed phase and continuation from the
    domain store, including after a process restart.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.graph = self._build_graph()

    def _snapshot(self, progressed=True):
        run = self.run
        wf = run.workflow
        task_id = run.current_task_id
        attempt_id = next((a.id for a in reversed(wf.attempts) if a.task_id == task_id), None) if wf else None
        submission_id = next((s.id for s in reversed(wf.submissions) if s.task_id == task_id), None) if wf else None
        review_id = next((r.result.review_id for r in reversed(wf.reviews)
                          if r.submission_id == submission_id), None) if wf else None
        return WorkflowGraphState(run_id=run.id, phase=run.phase, task_id=task_id,
            attempt_id=attempt_id, submission_id=submission_id, review_id=review_id,
            execution_generation=run.execution_generation, status=run.status.value,
            progressed=progressed)

    def _route(self, state: WorkflowGraphState):
        run = self.run
        wf = run.workflow
        if (not state['progressed'] or run.id != state['run_id']
                or (run.phase, run.execution_generation, run.current_task_id) !=
                   (state['phase'], state['execution_generation'], state['task_id'])
                or wf is None or wf.pending or wf.pending_permissions
                or run.status not in {RunStatus.DRAFT, RunStatus.PLANNING, RunStatus.RUNNING}):
            return 'stop'
        if run.phase == 'plan':
            return 'manager_plan'
        if run.phase in {'assign', 'execution'}:
            return 'manager_assignment'
        if run.phase == 'develop':
            return 'developer'
        if run.phase == 'review':
            return 'reviewer'
        if run.phase == 'decide':
            if state['submission_id'] is None or state['review_id'] is None:
                return 'stop'
            review = next((r for r in reversed(wf.reviews)
                           if r.submission_id == state['submission_id'] and
                           r.result.review_id == state['review_id']), None)
            if review is None:
                return 'stop'
            return 'accept_submission' if review.result.verdict.value == 'PASS' else 'manager_revision'
        if run.phase == 'final':
            return 'finalize'
        return 'stop'

    def _operation(self, state: WorkflowGraphState):
        identity = (state['phase'], state['execution_generation'], state['task_id'], state['attempt_id'])
        observer = GraphObservabilityAdapter(self._route(state))
        progressed = super().step(expected_identity=identity, observer=observer)
        return self._snapshot(progressed)

    def _build_graph(self):
        graph = StateGraph(WorkflowGraphState)
        nodes = ('manager_plan', 'manager_assignment', 'developer', 'reviewer',
                 'accept_submission', 'manager_revision', 'finalize')
        for name in nodes:
            graph.add_node(name, self._operation)
        paths = {name: name for name in nodes}
        paths['stop'] = END
        graph.add_conditional_edges(START, self._route, paths)
        for name in nodes:
            graph.add_conditional_edges(name, self._route, paths)
        return graph.compile()

    def step(self):
        state = self._snapshot()
        if self._route(state) == 'stop':
            return False
        return self._operation(state)['progressed']

    def run_until_stopped(self):
        wf = self.run.workflow
        if wf is None:
            raise ValueError('initialize workflow first')
        # The domain iteration cap is authoritative; this only bounds the
        # in-memory graph invocation and is never persisted as workflow state.
        self.graph.invoke(self._snapshot(), config={'recursion_limit':
            max(25, 2 * wf.limits.max_iterations + 5)})
        return self.run


def make_orchestrator(kind, *args, **kwargs) -> Orchestrator:
    """Explicit opt-in for isolated comparisons; legacy remains the default."""
    if kind == 'legacy':
        return LegacyOrchestrator(*args, **kwargs)
    if kind == 'langgraph':
        return LangGraphOrchestrator(*args, **kwargs)
    raise ValueError('orchestrator must be legacy or langgraph')
