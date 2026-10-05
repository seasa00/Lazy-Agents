"""Narrow state-store contract for M2.1 and later durable implementations."""

from __future__ import annotations

from typing import Callable, Mapping, Protocol

from app.agents.contracts import ManagerPlan
from app.domain.events import DomainEvent
from app.domain.projects import ProjectState, RunState, RunStatus
from app.domain.tasks import Task, TaskStatus


class StoreError(RuntimeError):
    """Base error for state-store operations."""


class NotFoundError(StoreError):
    """Requested project, run, or task does not exist."""


class ActiveRunError(StoreError):
    """A project already has a non-terminal run."""


class VersionConflictError(StoreError):
    """A caller supplied an entity version that is no longer current."""


class PlanApprovalError(StoreError):
    """A plan cannot be approved in the current run state."""


class ExecutionNotApprovedError(StoreError):
    """Execution was requested before the Manager plan was approved."""


class NoReadyTaskError(StoreError):
    """The approved run has no task that is currently ready."""


class StateStore(Protocol):
    """Minimal command/query boundary; implementations commit state and events together."""

    def create_project(self, project: ProjectState) -> ProjectState: ...

    def atomic_update(self, project_id: str, change: Callable, *, expected_version: int | None = None) -> ProjectState: ...

    def get_project(self, project_id: str) -> ProjectState: ...

    def create_run(self, project_id: str, *, config_snapshot: Mapping[str, str] | None = None, run_id: str | None = None) -> RunState: ...

    def propose_plan(self, project_id: str, run_id: str, plan: ManagerPlan) -> RunState: ...

    def approve_plan(self, project_id: str, run_id: str) -> RunState: ...

    def start_next_task(self, project_id: str, run_id: str) -> Task: ...

    def transition_task(self, project_id: str, run_id: str, task_id: str, target: TaskStatus) -> Task: ...

    def transition_run(self, project_id: str, run_id: str, target: RunStatus) -> RunState: ...

    def cancel_task(self, project_id: str, run_id: str, task_id: str) -> Task: ...

    def events(self, project_id: str, *, after_sequence: int = 0) -> tuple[DomainEvent, ...]: ...
