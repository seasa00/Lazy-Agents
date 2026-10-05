"""Legal run and task transitions; authoritative state changes use these guards."""

from __future__ import annotations

from app.domain.projects import RunStatus
from app.domain.tasks import TaskDisposition, TaskStatus


class TransitionError(ValueError):
    """Raised when a requested state transition is not legal."""


RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.DRAFT: frozenset({RunStatus.PLANNING, RunStatus.CANCELED}),
    RunStatus.PLANNING: frozenset({RunStatus.AWAITING_APPROVAL, RunStatus.CANCELED}),
    RunStatus.AWAITING_APPROVAL: frozenset({RunStatus.RUNNING, RunStatus.CANCELED}),
    RunStatus.RUNNING: frozenset({RunStatus.PAUSE_REQUESTED, RunStatus.WAITING_FOR_USER, RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED}),
    RunStatus.PAUSE_REQUESTED: frozenset({RunStatus.PAUSED, RunStatus.CANCELED, RunStatus.FAILED}),
    RunStatus.PAUSED: frozenset({RunStatus.RUNNING, RunStatus.CANCELED, RunStatus.FAILED}),
    RunStatus.WAITING_FOR_USER: frozenset({RunStatus.RUNNING, RunStatus.CANCELED, RunStatus.FAILED}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELED: frozenset(),
}


TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.BACKLOG: frozenset({TaskStatus.TODO, TaskStatus.BLOCKED}),
    TaskStatus.TODO: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED}),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.REVIEW, TaskStatus.BLOCKED}),
    TaskStatus.REVIEW: frozenset({TaskStatus.DONE, TaskStatus.TODO, TaskStatus.BLOCKED}),
    TaskStatus.DONE: frozenset({TaskStatus.TODO}),
    TaskStatus.BLOCKED: frozenset({TaskStatus.TODO, TaskStatus.REVIEW}),
}


def assert_run_transition(current: RunStatus, target: RunStatus) -> None:
    if target not in RUN_TRANSITIONS[current]:
        raise TransitionError(f"illegal run transition: {current.value} -> {target.value}")


def assert_task_transition(current: TaskStatus, target: TaskStatus, *, disposition: TaskDisposition = TaskDisposition.ACTIVE) -> None:
    if disposition is TaskDisposition.CANCELED:
        raise TransitionError("canceled tasks cannot transition")
    if target not in TASK_TRANSITIONS[current]:
        raise TransitionError(f"illegal task transition: {current.value} -> {target.value}")
