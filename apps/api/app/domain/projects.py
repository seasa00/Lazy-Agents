"""Versioned project and run state used by the M2.1 orchestration boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from app.agents.contracts import DecisionRecord, ManagerPlan, Requirement
from app.domain.tasks import Task
from app.domain.workflow import WorkflowState


class RunStatus(StrEnum):
    DRAFT = "draft"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    WAITING_FOR_USER = "waiting_for_user"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


TERMINAL_RUN_STATUSES = frozenset({RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED})
ACTIVE_RUN_STATUSES = frozenset(set(RunStatus) - TERMINAL_RUN_STATUSES)


def _snapshot_items(value: Mapping[str, str] | tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    items = tuple(value.items()) if isinstance(value, Mapping) else tuple(value)
    if any(not isinstance(key, str) or not key.strip() or not isinstance(item, str) or not item.strip() for key, item in items):
        raise ValueError("configuration snapshot must map non-empty strings to non-empty strings")
    if len({key for key, _ in items}) != len(items):
        raise ValueError("configuration snapshot keys must be unique")
    return tuple(sorted(items))


@dataclass(frozen=True, slots=True)
class RunState:
    id: str
    project_id: str
    status: RunStatus = RunStatus.DRAFT
    phase: str = "planning"
    current_task_id: str | None = None
    task_ids: tuple[str, ...] = ()
    plan: ManagerPlan | None = None
    config_snapshot: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    execution_generation: int = 1
    version: int = 1
    workflow: WorkflowState | None = None
    plan_approved: bool = False

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.project_id.strip():
            raise ValueError("run id and project id are required")
        if not isinstance(self.status, RunStatus):
            raise ValueError("run status must be a RunStatus")
        if not self.phase.strip():
            raise ValueError("run phase is required")
        if len(set(self.task_ids)) != len(self.task_ids):
            raise ValueError("run task ids must be unique")
        if self.execution_generation < 1 or self.version < 1:
            raise ValueError("run generation and version must be positive")
        _snapshot_items(self.config_snapshot)

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_RUN_STATUSES

    @property
    def approved(self) -> bool:
        return self.plan_approved and self.plan is not None

    @property
    def state(self) -> RunStatus:
        return self.status

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "status": self.status.value,
            "phase": self.phase,
            "current_task_id": self.current_task_id,
            "task_ids": list(self.task_ids),
            "plan": None if self.plan is None else self.plan.to_dict(),
            "config_snapshot": {key: value for key, value in self.config_snapshot},
            "execution_generation": self.execution_generation,
            "version": self.version,
            "workflow": None if self.workflow is None else self.workflow.to_dict(),
            "plan_approved": self.plan_approved,
        }


@dataclass(frozen=True, slots=True)
class ProjectState:
    id: str
    name: str
    goal: str
    workspace_root: str = ""
    requirements: tuple[Requirement, ...] = ()
    requirement_version: int = 1
    decisions: tuple[DecisionRecord, ...] = ()
    tasks: tuple[Task, ...] = ()
    runs: tuple[RunState, ...] = ()
    active_run_id: str | None = None
    version: int = 1

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.name.strip() or not self.goal.strip():
            raise ValueError("project id, name, and goal are required")
        if self.requirement_version < 1 or self.version < 1:
            raise ValueError("project versions must be positive")
        for label, records in (("requirement", self.requirements), ("decision", self.decisions), ("task", self.tasks), ("run", self.runs)):
            ids = [item.id for item in records]
            if len(set(ids)) != len(ids):
                raise ValueError(f"{label} ids must be unique")
        run_ids = {run.id for run in self.runs}
        if self.active_run_id is not None and self.active_run_id not in run_ids:
            raise ValueError("active_run_id must reference a run")
        active = [run.id for run in self.runs if run.active]
        if len(active) > 1:
            raise ValueError("a project may have only one active run")
        if self.active_run_id != (active[0] if active else None):
            raise ValueError("active_run_id is inconsistent with run statuses")

    @property
    def active_run(self) -> RunState | None:
        return next((run for run in self.runs if run.active), None)

    def task(self, task_id: str) -> Task:
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise KeyError(task_id)

    def run(self, run_id: str) -> RunState:
        for run in self.runs:
            if run.id == run_id:
                return run
        raise KeyError(run_id)

    @property
    def completed_task_ids(self) -> tuple[str, ...]:
        return tuple(task.id for task in self.tasks if task.is_completed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "goal": self.goal,
            "workspace_root": self.workspace_root,
            "requirements": [item.to_dict() for item in self.requirements],
            "requirement_version": self.requirement_version,
            "decisions": [item.to_dict() for item in self.decisions],
            "tasks": [item.to_dict() for item in self.tasks],
            "runs": [item.to_dict() for item in self.runs],
            "active_run_id": self.active_run_id,
            "version": self.version,
        }


# Domain-friendly names while preserving the M1 structured contracts.
Decision = DecisionRecord
