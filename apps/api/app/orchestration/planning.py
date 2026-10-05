"""Manager-plan validation and deterministic dependency readiness."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Mapping

from app.agents.contracts import ContractValidationError, ManagerPlan
from app.domain.tasks import Task


class PlanValidationError(ValueError):
    """Raised when a structured Manager plan is not safe to commit."""


def validate_manager_plan(value: ManagerPlan | Mapping[str, object]) -> ManagerPlan:
    """Parse and validate a Manager proposal without mutating authoritative state."""

    try:
        plan = ManagerPlan.from_dict(value.to_dict() if isinstance(value, ManagerPlan) else value)
    except (ContractValidationError, TypeError, ValueError) as exc:
        raise PlanValidationError(str(exc)) from exc

    requirement_ids = [item.id for item in plan.requirements]
    if len(set(requirement_ids)) != len(requirement_ids):
        raise PlanValidationError("manager plan requirement ids must be unique")
    decision_ids = [item.id for item in plan.decisions]
    if len(set(decision_ids)) != len(decision_ids):
        raise PlanValidationError("manager plan decision ids must be unique")
    task_ids = [task.id for task in plan.tasks]
    if len(set(task_ids)) != len(task_ids):
        raise PlanValidationError("manager plan task ids must be unique")
    task_set = set(task_ids)
    for task in plan.tasks:
        if len(set(task.dependencies)) != len(task.dependencies):
            raise PlanValidationError(f"task {task.id!r} has duplicate dependencies")
        if task.id in task.dependencies:
            raise PlanValidationError(f"task {task.id!r} cannot depend on itself")
        missing = sorted(set(task.dependencies) - task_set)
        if missing:
            raise PlanValidationError(f"task {task.id!r} has missing dependencies: {', '.join(missing)}")
    _assert_acyclic({task.id: task.dependencies for task in plan.tasks})
    return plan


def _assert_acyclic(graph: Mapping[str, Iterable[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, path: tuple[str, ...]) -> None:
        if node in visiting:
            cycle_start = path.index(node) if node in path else 0
            cycle = " -> ".join((*path[cycle_start:], node))
            raise PlanValidationError(f"task dependency cycle detected: {cycle}")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency, (*path, node))
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node, ())


def materialize_tasks(plan: ManagerPlan) -> tuple[Task, ...]:
    """Convert a validated proposal into authoritative task records."""

    validate_manager_plan(plan)
    return tuple(Task.from_spec(spec) for spec in plan.tasks)


def ready_tasks(tasks: Iterable[Task]) -> tuple[Task, ...]:
    """Return deterministic ready tasks; only active, unfinished prerequisites count."""

    by_id = {task.id: task for task in tasks}
    result = []
    for task in by_id.values():
        if task.is_canceled or task.status.value not in {"backlog", "todo"}:
            continue
        if all(dependency in by_id and by_id[dependency].is_completed for dependency in task.dependencies):
            result.append(task)
    return tuple(sorted(result, key=lambda item: item.id))


def dependency_order(tasks: Iterable[Task]) -> tuple[str, ...]:
    """Return a stable topological order for a validated task collection."""

    by_id = {task.id: task for task in tasks}
    _assert_acyclic({task.id: task.dependencies for task in by_id.values()})
    remaining = {task.id: set(task.dependencies) for task in by_id.values()}
    result: list[str] = []
    while remaining:
        available = sorted(task_id for task_id, deps in remaining.items() if not deps)
        if not available:
            raise PlanValidationError("task dependency cycle detected")
        result.extend(available)
        for task_id in available:
            del remaining[task_id]
        for deps in remaining.values():
            deps.difference_update(available)
    return tuple(result)
