"""Authoritative task state for the M2.1 in-memory workflow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.agents.contracts import TaskSpec
from app.domain.agents import AgentKind


class TaskStatus(StrEnum):
    """Lifecycle state of a task; cancellation is a separate disposition."""

    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    BLOCKED = "blocked"


class TaskDisposition(StrEnum):
    ACTIVE = "active"
    CANCELED = "canceled"


@dataclass(frozen=True, slots=True)
class Task:
    """A versioned task with explicit prerequisite IDs."""

    id: str
    title: str
    description: str
    acceptance_criteria: tuple[str, ...]
    assignee: AgentKind
    dependencies: tuple[str, ...] = ()
    status: TaskStatus = TaskStatus.BACKLOG
    disposition: TaskDisposition = TaskDisposition.ACTIVE
    blocked_reason: str | None = None
    resume_phase: TaskStatus | None = None
    revision: int = 1
    version: int = 1

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.title.strip() or not self.description.strip():
            raise ValueError("task id, title, and description are required")
        if not isinstance(self.assignee, AgentKind):
            raise ValueError("task assignee must be an AgentKind")
        if not self.acceptance_criteria or any(not item.strip() for item in self.acceptance_criteria):
            raise ValueError("task acceptance criteria must not be empty")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("task dependencies must not contain duplicates")
        if self.id in self.dependencies:
            raise ValueError("task cannot depend on itself")
        if self.revision < 1 or self.version < 1:
            raise ValueError("task revision and version must be positive")
        if self.status is not TaskStatus.BLOCKED and self.blocked_reason is not None:
            raise ValueError("blocked_reason is only valid for blocked tasks")

    @classmethod
    def from_spec(cls, spec: TaskSpec) -> "Task":
        return cls(
            id=spec.id,
            title=spec.title,
            description=spec.description,
            acceptance_criteria=spec.acceptance_criteria,
            assignee=spec.assignee,
            dependencies=spec.dependencies,
        )

    @property
    def is_canceled(self) -> bool:
        return self.disposition is TaskDisposition.CANCELED

    @property
    def is_completed(self) -> bool:
        """Canceled work is deliberately not completed work."""

        return self.disposition is TaskDisposition.ACTIVE and self.status is TaskStatus.DONE

    @property
    def state(self) -> TaskStatus:
        """Compatibility name for callers that call lifecycle state ``state``."""

        return self.status

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "acceptance_criteria": list(self.acceptance_criteria),
            "assignee": self.assignee.value,
            "dependencies": list(self.dependencies),
            "status": self.status.value,
            "disposition": self.disposition.value,
            "blocked_reason": self.blocked_reason,
            "resume_phase": None if self.resume_phase is None else self.resume_phase.value,
            "revision": self.revision,
            "version": self.version,
        }


# Convenient aliases for callers that use "state" for the record or its
# lifecycle enum; the explicit names above remain canonical.
TaskState = Task
TaskLifecycleState = TaskStatus
