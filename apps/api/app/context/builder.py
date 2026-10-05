"""Role-scoped context construction for M1.1.

The builder receives structured project state and emits the smallest typed
context required by one employee. It never accepts or forwards a conversation
transcript.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4

from app.agents.contracts import (
    DeveloperContext,
    DecisionRecord,
    ManagerContext,
    Requirement,
    ReviewerContext,
    ReviewReference,
    RoleContext,
    SubmissionReference,
    TaskBrief,
    TaskSummary,
)
from app.domain.agents import AgentDefinition, AgentKind


class ContextBuildError(ValueError):
    """Raised when a role cannot receive a complete bounded context."""


@dataclass(frozen=True, slots=True)
class ProjectContext:
    """Structured project facts available to the context builder."""

    goal: str
    requirements: tuple[Requirement, ...]
    task_summaries: tuple[TaskSummary, ...] = ()
    decisions: tuple[DecisionRecord, ...] = ()
    current_task: TaskBrief | None = None
    dependencies: tuple[TaskSummary, ...] = ()
    relevant_review: ReviewReference | None = None
    submission: SubmissionReference | None = None
    available_files: tuple[str, ...] = ()
    source_versions: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class ContextManifest:
    """Evidence describing exactly what was supplied to an invocation."""

    manifest_id: str
    agent_kind: AgentKind
    configuration_version: int
    configuration_digest: str
    selected_sections: tuple[str, ...]
    source_versions: tuple[tuple[str, str], ...]
    context_digest: str
    serialized_chars: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "agent_kind": self.agent_kind.value,
            "configuration_version": self.configuration_version,
            "configuration_digest": self.configuration_digest,
            "selected_sections": list(self.selected_sections),
            "source_versions": {key: value for key, value in self.source_versions},
            "context_digest": self.context_digest,
            "serialized_chars": self.serialized_chars,
        }


@dataclass(frozen=True, slots=True)
class BuiltContext:
    context: RoleContext
    payload: dict[str, Any]
    manifest: ContextManifest


def _require_goal(goal: str) -> str:
    if not isinstance(goal, str) or not goal.strip():
        raise ContextBuildError("project goal is required")
    return goal


def _require_section(project: ProjectContext, section: str) -> None:
    value = getattr(project, section)
    if value is None or value == "" or value == () or value == []:
        raise ContextBuildError(f"required context section {section!r} is missing")


def _section_payload(project: ProjectContext, section: str) -> Any:
    if section == "goal":
        return project.goal
    if section == "requirements":
        return [item.to_dict() for item in project.requirements]
    if section == "current_task":
        return None if project.current_task is None else project.current_task.to_dict()
    if section == "task_summaries":
        return [item.to_dict() for item in project.task_summaries]
    if section == "dependencies":
        return [item.to_dict() for item in project.dependencies]
    if section == "decisions":
        return [item.to_dict() for item in project.decisions]
    if section == "relevant_review":
        return None if project.relevant_review is None else project.relevant_review.to_dict()
    if section == "submission":
        return None if project.submission is None else project.submission.to_dict()
    if section == "available_files":
        return list(project.available_files)
    raise ContextBuildError(f"unsupported context section {section!r}")


def _role_context(kind: AgentKind, project: ProjectContext) -> RoleContext:
    if kind is AgentKind.MANAGER:
        return ManagerContext(
            goal=_require_goal(project.goal),
            requirements=project.requirements,
            task_summaries=project.task_summaries,
            decisions=project.decisions,
            relevant_review=project.relevant_review,
        )
    if kind is AgentKind.DEVELOPER:
        if project.current_task is None:
            raise ContextBuildError("Developer context requires current_task")
        return DeveloperContext(
            goal=_require_goal(project.goal),
            requirements=project.requirements,
            current_task=project.current_task,
            dependencies=project.dependencies,
            relevant_review=project.relevant_review,
            available_files=project.available_files,
        )
    if kind is AgentKind.REVIEWER:
        if project.current_task is None:
            raise ContextBuildError("Reviewer context requires current_task")
        if project.submission is None:
            raise ContextBuildError("Reviewer context requires submission")
        return ReviewerContext(
            goal=_require_goal(project.goal),
            requirements=project.requirements,
            current_task=project.current_task,
            submission=project.submission,
            available_files=project.available_files,
        )
    raise ContextBuildError(f"unsupported agent kind {kind!r}")


def build_context(
    agent: AgentDefinition,
    project: ProjectContext,
    *,
    source_versions: Mapping[str, str] | None = None,
) -> BuiltContext:
    """Build, bound, and manifest a context for one agent definition."""

    _require_goal(project.goal)
    policy = agent.context_policy
    for section in policy.required_sections:
        _require_section(project, section)

    # Build the typed context first; this adds role-specific semantic checks.
    typed_context = _role_context(agent.kind, project)
    payload = typed_context.to_payload()
    selected = tuple(section for section in policy.allowed_sections if section in payload)
    # A policy must describe exactly what the typed context can expose. This
    # catches accidental additions to a role's context instead of forwarding
    # them silently.
    unexpected = set(payload) - set(policy.allowed_sections)
    if unexpected:
        raise ContextBuildError(
            f"{agent.kind.value} context contains sections outside its policy: {', '.join(sorted(unexpected))}"
        )
    for section in policy.required_sections:
        if section not in payload:
            raise ContextBuildError(f"required context section {section!r} was not emitted")

    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    size = len(serialized)
    if size > policy.max_chars:
        raise ContextBuildError(
            f"{agent.kind.value} context is {size} characters, above max_chars={policy.max_chars}; context was not truncated"
        )
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    versions = source_versions or project.source_versions or {}
    if any(not isinstance(key, str) or not isinstance(value, str) or not key or not value for key, value in versions.items()):
        raise ContextBuildError("source_versions must map non-empty strings to non-empty strings")
    manifest = ContextManifest(
        manifest_id=f"ctx_{uuid4().hex}",
        agent_kind=agent.kind,
        configuration_version=agent.config_version,
        configuration_digest=agent.snapshot().config_digest,
        selected_sections=selected,
        source_versions=tuple(sorted(versions.items())),
        context_digest=digest,
        serialized_chars=size,
    )
    return BuiltContext(context=typed_context, payload=payload, manifest=manifest)


def project_context_from_payload(data: Mapping[str, Any]) -> ProjectContext:
    """Parse a fixture payload into structured project context.

    This helper is used by the development harness; it is strict so fixtures
    cannot accidentally become an untyped conversation channel.
    """

    expected = {
        "goal",
        "requirements",
        "task_summaries",
        "decisions",
        "current_task",
        "dependencies",
        "relevant_review",
        "submission",
        "available_files",
        "source_versions",
    }
    missing = sorted(expected - data.keys())
    extra = sorted(data.keys() - expected)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing fields: {', '.join(missing)}")
        if extra:
            details.append(f"unknown fields: {', '.join(extra)}")
        raise ContextBuildError(f"invalid project context fixture: {'; '.join(details)}")
    source_versions = data["source_versions"]
    if not isinstance(source_versions, Mapping):
        raise ContextBuildError("source_versions must be an object")
    available_files = data["available_files"]
    if not isinstance(available_files, (list, tuple)) or any(
        not isinstance(item, str) or not item.strip() for item in available_files
    ):
        raise ContextBuildError("available_files must be a list of non-empty strings")
    raw_requirements = data["requirements"]
    raw_task_summaries = data["task_summaries"]
    raw_decisions = data["decisions"]
    raw_dependencies = data["dependencies"]
    for value, label in (
        (raw_requirements, "requirements"),
        (raw_task_summaries, "task_summaries"),
        (raw_decisions, "decisions"),
        (raw_dependencies, "dependencies"),
    ):
        if not isinstance(value, (list, tuple)):
            raise ContextBuildError(f"{label} must be a list")
    return ProjectContext(
        goal=_require_goal(data["goal"]),
        requirements=tuple(Requirement.from_dict(item) for item in raw_requirements),
        task_summaries=tuple(TaskSummary.from_dict(item) for item in raw_task_summaries),
        decisions=tuple(DecisionRecord.from_dict(item) for item in raw_decisions),
        current_task=None if data["current_task"] is None else TaskBrief.from_dict(data["current_task"]),
        dependencies=tuple(TaskSummary.from_dict(item) for item in raw_dependencies),
        relevant_review=None if data["relevant_review"] is None else ReviewReference.from_dict(data["relevant_review"]),
        submission=None if data["submission"] is None else SubmissionReference.from_dict(data["submission"]),
        available_files=tuple(available_files),
        source_versions=dict(source_versions),
    )
