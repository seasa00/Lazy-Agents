"""Configurable employee definitions for the three-agent M1.1 runtime.

The workflow position is represented by :class:`AgentKind`.  ``DEVELOPER``
is the canonical name for the blueprint's initial Worker role; the separate
``role`` field is where a future specialization can be configured.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping


class AgentDefinitionError(ValueError):
    """Raised when a configurable employee definition is invalid."""


class AgentKind(StrEnum):
    MANAGER = "manager"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"

    @classmethod
    def parse(cls, value: object) -> "AgentKind":
        if not isinstance(value, str):
            raise AgentDefinitionError("agent kind must be a string")
        try:
            return cls(value.lower())
        except ValueError as exc:
            allowed = ", ".join(kind.value for kind in cls)
            raise AgentDefinitionError(f"unknown agent kind {value!r}; expected one of {allowed}") from exc


class AgentStatus(StrEnum):
    IDLE = "idle"
    THINKING = "thinking"
    WORKING = "working"
    WAITING = "waiting"
    REVIEWING = "reviewing"
    BLOCKED = "blocked"
    DONE = "done"
    ERROR = "error"


_CONTEXT_SECTIONS = {
    "goal",
    "requirements",
    "current_task",
    "task_summaries",
    "dependencies",
    "decisions",
    "relevant_review",
    "submission",
    "available_files",
}


def _required_keys(data: Mapping[str, Any], expected: set[str], label: str) -> None:
    if not isinstance(data, Mapping):
        raise AgentDefinitionError(f"{label} must be an object")
    missing = sorted(expected - data.keys())
    extra = sorted(data.keys() - expected)
    errors: list[str] = []
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")
    if extra:
        errors.append(f"unknown fields: {', '.join(extra)}")
    if errors:
        raise AgentDefinitionError(f"invalid {label}: {'; '.join(errors)}")


def _string(value: object, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise AgentDefinitionError(f"{field} must be a non-empty string")
    return value


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise AgentDefinitionError(f"{field} must be a list of strings")
    result: list[str] = []
    for item in value:
        result.append(_string(item, field))
    if len(set(result)) != len(result):
        raise AgentDefinitionError(f"{field} must not contain duplicates")
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ContextPolicy:
    """Allowlist and size policy used when constructing an agent context."""

    allowed_sections: tuple[str, ...]
    required_sections: tuple[str, ...]
    max_chars: int = 24_000

    def __post_init__(self) -> None:
        if not self.allowed_sections:
            raise AgentDefinitionError("context policy must allow at least one section")
        unknown = set(self.allowed_sections) - _CONTEXT_SECTIONS
        if unknown:
            raise AgentDefinitionError(f"unknown context sections: {', '.join(sorted(unknown))}")
        if len(set(self.allowed_sections)) != len(self.allowed_sections):
            raise AgentDefinitionError("allowed context sections must not contain duplicates")
        if len(set(self.required_sections)) != len(self.required_sections):
            raise AgentDefinitionError("required context sections must not contain duplicates")
        if not set(self.required_sections).issubset(self.allowed_sections):
            raise AgentDefinitionError("required context sections must be allowed")
        if self.max_chars < 256:
            raise AgentDefinitionError("context policy max_chars must be at least 256")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ContextPolicy":
        _required_keys(data, {"allowed_sections", "required_sections", "max_chars"}, "context policy")
        max_chars = data["max_chars"]
        if not isinstance(max_chars, int) or isinstance(max_chars, bool):
            raise AgentDefinitionError("context policy max_chars must be an integer")
        return cls(
            allowed_sections=_string_tuple(data["allowed_sections"], "allowed_sections"),
            required_sections=_string_tuple(data["required_sections"], "required_sections"),
            max_chars=max_chars,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_sections": list(self.allowed_sections),
            "required_sections": list(self.required_sections),
            "max_chars": self.max_chars,
        }


@dataclass(frozen=True, slots=True)
class AgentConfigSnapshot:
    """Immutable configuration captured at invocation start."""

    agent_id: str
    kind: AgentKind
    name: str
    role: str
    responsibilities: tuple[str, ...]
    system_instructions: str
    model: str
    tools: tuple[str, ...]
    permissions: tuple[str, ...]
    context_policy: ContextPolicy
    config_version: int
    config_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "kind": self.kind.value,
            "name": self.name,
            "role": self.role,
            "responsibilities": list(self.responsibilities),
            "system_instructions": self.system_instructions,
            "model": self.model,
            "tools": list(self.tools),
            "permissions": list(self.permissions),
            "context_policy": self.context_policy.to_dict(),
            "config_version": self.config_version,
            "config_digest": self.config_digest,
        }


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """Configuration for one employee identity.

    This object is immutable so an invocation can safely retain its snapshot
    while a caller prepares a replacement definition for a later invocation.
    """

    id: str
    kind: AgentKind
    name: str
    role: str
    responsibilities: tuple[str, ...]
    system_instructions: str
    model: str
    tools: tuple[str, ...]
    permissions: tuple[str, ...]
    context_policy: ContextPolicy
    config_version: int = 1
    status: AgentStatus = AgentStatus.IDLE

    def __post_init__(self) -> None:
        _string(self.id, "agent id")
        _string(self.name, "agent name")
        _string(self.role, "agent role")
        _string(self.system_instructions, "system instructions")
        _string(self.model, "agent model")
        if not isinstance(self.kind, AgentKind):
            raise AgentDefinitionError("agent kind must be an AgentKind")
        if not isinstance(self.status, AgentStatus):
            raise AgentDefinitionError("agent status must be an AgentStatus")
        if not self.responsibilities:
            raise AgentDefinitionError("agent must have at least one responsibility")
        if any(not isinstance(item, str) or not item.strip() for item in self.responsibilities):
            raise AgentDefinitionError("agent responsibilities must be non-empty strings")
        if len(set(self.responsibilities)) != len(self.responsibilities):
            raise AgentDefinitionError("agent responsibilities must not contain duplicates")
        if not isinstance(self.config_version, int) or isinstance(self.config_version, bool) or self.config_version < 1:
            raise AgentDefinitionError("config version must be a positive integer")
        if len(set(self.tools)) != len(self.tools):
            raise AgentDefinitionError("agent tools must not contain duplicates")
        if len(set(self.permissions)) != len(self.permissions):
            raise AgentDefinitionError("agent permissions must not contain duplicates")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentDefinition":
        _required_keys(
            data,
            {
                "id",
                "kind",
                "name",
                "role",
                "responsibilities",
                "system_instructions",
                "model",
                "tools",
                "permissions",
                "context_policy",
                "config_version",
                "status",
            },
            "agent definition",
        )
        config_version = data["config_version"]
        if not isinstance(config_version, int) or isinstance(config_version, bool):
            raise AgentDefinitionError("config_version must be an integer")
        status = data["status"]
        if not isinstance(status, str):
            raise AgentDefinitionError("status must be a string")
        try:
            parsed_status = AgentStatus(status.lower())
        except ValueError as exc:
            raise AgentDefinitionError(f"unknown agent status {status!r}") from exc
        return cls(
            id=_string(data["id"], "agent id"),
            kind=AgentKind.parse(data["kind"]),
            name=_string(data["name"], "agent name"),
            role=_string(data["role"], "agent role"),
            responsibilities=_string_tuple(data["responsibilities"], "responsibilities"),
            system_instructions=_string(data["system_instructions"], "system instructions"),
            model=_string(data["model"], "model"),
            tools=_string_tuple(data["tools"], "tools"),
            permissions=_string_tuple(data["permissions"], "permissions"),
            context_policy=ContextPolicy.from_dict(data["context_policy"]),
            config_version=config_version,
            status=parsed_status,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "name": self.name,
            "role": self.role,
            "responsibilities": list(self.responsibilities),
            "system_instructions": self.system_instructions,
            "model": self.model,
            "tools": list(self.tools),
            "permissions": list(self.permissions),
            "context_policy": self.context_policy.to_dict(),
            "config_version": self.config_version,
            "status": self.status.value,
        }

    def snapshot(self) -> AgentConfigSnapshot:
        payload = self.to_dict()
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        return AgentConfigSnapshot(
            agent_id=self.id,
            kind=self.kind,
            name=self.name,
            role=self.role,
            responsibilities=self.responsibilities,
            system_instructions=self.system_instructions,
            model=self.model,
            tools=self.tools,
            permissions=self.permissions,
            context_policy=self.context_policy,
            config_version=self.config_version,
            config_digest=digest,
        )


def default_agent_definitions() -> dict[AgentKind, AgentDefinition]:
    """Return the three default agents with no tools or permissions."""

    common = {
        "model": "deterministic-mock-v1",
        "tools": (),
        "permissions": (),
        "config_version": 1,
        "status": AgentStatus.IDLE,
    }
    definitions = (
        AgentDefinition(
            id="manager",
            kind=AgentKind.MANAGER,
            name="Manager",
            role="Orchestrator",
            responsibilities=("Understand the goal", "Propose structured tasks", "Summarize the result"),
            system_instructions="Orchestrate work through structured plans and decisions; do not perform specialist work.",
            context_policy=ContextPolicy(
                allowed_sections=("goal", "requirements", "task_summaries", "decisions", "relevant_review"),
                required_sections=("goal", "requirements"),
            ),
            **common,
        ),
        AgentDefinition(
            id="developer",
            kind=AgentKind.DEVELOPER,
            name="Developer",
            role="Software Developer",
            responsibilities=("Implement the assigned task", "Report changes", "Submit work for review"),
            system_instructions="Implement only the assigned task and report structured work; tools are unavailable until the later tools milestone.",
            context_policy=ContextPolicy(
                allowed_sections=("goal", "requirements", "current_task", "dependencies", "relevant_review", "available_files"),
                required_sections=("current_task",),
            ),
            **common,
        ),
        AgentDefinition(
            id="reviewer",
            kind=AgentKind.REVIEWER,
            name="Reviewer",
            role="Quality Reviewer",
            responsibilities=("Check acceptance criteria", "Identify issues", "Return PASS or FAIL"),
            system_instructions="Review the submitted version against its criteria; never modify the submitted output.",
            context_policy=ContextPolicy(
                allowed_sections=("goal", "requirements", "current_task", "submission", "available_files"),
                required_sections=("current_task", "submission"),
            ),
            **common,
        ),
    )
    return {definition.kind: definition for definition in definitions}


def load_agent_definitions(path: str | Path) -> dict[AgentKind, AgentDefinition]:
    """Load and validate exactly one definition for each canonical agent kind."""

    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AgentDefinitionError(f"could not read agent configuration {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AgentDefinitionError(f"agent configuration is not valid JSON: {exc}") from exc
    if not isinstance(raw, list):
        raise AgentDefinitionError("agent configuration must be a JSON list")
    definitions = [AgentDefinition.from_dict(item) for item in raw if isinstance(item, Mapping)]
    if len(definitions) != len(raw):
        raise AgentDefinitionError("each agent configuration entry must be an object")
    by_kind: dict[AgentKind, AgentDefinition] = {}
    for definition in definitions:
        if definition.kind in by_kind:
            raise AgentDefinitionError(f"duplicate definition for {definition.kind.value}")
        by_kind[definition.kind] = definition
    expected = set(AgentKind)
    if set(by_kind) != expected:
        missing = ", ".join(sorted(kind.value for kind in expected - set(by_kind)))
        raise AgentDefinitionError(f"configuration must define exactly Manager, Developer, Reviewer; missing: {missing}")
    ids = [definition.id for definition in definitions]
    if len(set(ids)) != len(ids):
        raise AgentDefinitionError("agent definition ids must be unique")
    return by_kind
