"""Append-only domain event envelopes for committed in-memory state changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping
from uuid import uuid4


class ActorKind(StrEnum):
    SYSTEM = "system"
    USER = "user"
    MANAGER = "manager"


@dataclass(frozen=True, slots=True)
class EventActor:
    kind: ActorKind
    id: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ActorKind) or not self.id.strip():
            raise ValueError("event actor requires a valid kind and id")

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind.value, "id": self.id}


@dataclass(frozen=True, slots=True)
class DomainEvent:
    project_id: str
    type: str
    payload: Mapping[str, Any]
    sequence: int = 0
    event_id: str = field(default_factory=lambda: f"evt_{uuid4().hex}")
    run_id: str | None = None
    task_id: str | None = None
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    actor: EventActor = field(default_factory=lambda: EventActor(ActorKind.SYSTEM, "system"))
    schema_version: int = 1
    correlation_id: str | None = None
    causation_id: str | None = None

    def __post_init__(self) -> None:
        if not self.project_id.strip() or not self.type.strip() or self.sequence < 0 or self.schema_version < 1:
            raise ValueError("event requires project, type, and valid versions")
        if not isinstance(self.payload, Mapping):
            raise ValueError("event payload must be a mapping")

    def with_sequence(self, sequence: int) -> "DomainEvent":
        if sequence < 1:
            raise ValueError("event sequence must be positive")
        return DomainEvent(
            project_id=self.project_id,
            type=self.type,
            payload=dict(self.payload),
            sequence=sequence,
            event_id=self.event_id,
            run_id=self.run_id,
            task_id=self.task_id,
            occurred_at=self.occurred_at,
            actor=self.actor,
            schema_version=self.schema_version,
            correlation_id=self.correlation_id,
            causation_id=self.causation_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "sequence": self.sequence,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "type": self.type,
            "occurred_at": self.occurred_at,
            "actor": self.actor.to_dict(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "payload": dict(self.payload),
        }
