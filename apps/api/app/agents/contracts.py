"""Typed agent inputs and outputs with strict, JSON-compatible validation.

M1.1 deliberately uses standard-library dataclasses instead of introducing a
validation framework. The ``from_dict`` methods reject missing and unknown
fields so a provider cannot silently change the contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, TypeVar

from app.domain.agents import AgentKind


class ContractValidationError(ValueError):
    """Raised when structured agent input or output violates its contract."""


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{label} must be an object")
    return value


def _keys(data: Mapping[str, Any], expected: set[str], label: str) -> None:
    missing = sorted(expected - data.keys())
    extra = sorted(data.keys() - expected)
    messages: list[str] = []
    if missing:
        messages.append(f"missing fields: {', '.join(missing)}")
    if extra:
        messages.append(f"unknown fields: {', '.join(extra)}")
    if messages:
        raise ContractValidationError(f"invalid {label}: {'; '.join(messages)}")


def _str(value: object, field: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ContractValidationError(f"{field} must be a non-empty string")
    return value


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ContractValidationError(f"{field} must be a boolean")
    return value


def _str_tuple(value: object, field: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ContractValidationError(f"{field} must be a list of strings")
    result = tuple(_str(item, field) for item in value)
    if not allow_empty and not result:
        raise ContractValidationError(f"{field} must not be empty")
    if len(set(result)) != len(result):
        raise ContractValidationError(f"{field} must not contain duplicates")
    return result


def _object_tuple(value: object, field: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        raise ContractValidationError(f"{field} must be a list of objects")
    return tuple(_mapping(item, field) for item in value)


T = TypeVar("T")


def _parse_tuple(value: object, field: str, parser: Any) -> tuple[Any, ...]:
    return tuple(parser(item) for item in _object_tuple(value, field))


class DecisionAction(StrEnum):
    ASSIGN_TASK = "assign_task"
    REQUEST_REVISION = "request_revision"
    ACCEPT_SUBMISSION = "accept_submission"
    BLOCK = "block"
    COMPLETE = "complete"
    REQUEST_USER_INPUT = "request_user_input"


class ReviewVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class FindingSeverity(StrEnum):
    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"
    NOTE = "note"


@dataclass(frozen=True, slots=True)
class Requirement:
    id: str
    description: str
    acceptance_criteria: tuple[str, ...]
    priority: str = "normal"

    @classmethod
    def from_dict(cls, value: object) -> "Requirement":
        data = _mapping(value, "requirement")
        _keys(data, {"id", "description", "acceptance_criteria", "priority"}, "requirement")
        return cls(
            id=_str(data["id"], "requirement id"),
            description=_str(data["description"], "requirement description"),
            acceptance_criteria=_str_tuple(data["acceptance_criteria"], "acceptance_criteria", allow_empty=False),
            priority=_str(data["priority"], "priority"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "acceptance_criteria": list(self.acceptance_criteria),
            "priority": self.priority,
        }


@dataclass(frozen=True, slots=True)
class TaskSummary:
    id: str
    title: str
    status: str
    assignee: AgentKind
    dependencies: tuple[str, ...]
    review_attempts: int

    @classmethod
    def from_dict(cls, value: object) -> "TaskSummary":
        data = _mapping(value, "task summary")
        _keys(data, {"id", "title", "status", "assignee", "dependencies", "review_attempts"}, "task summary")
        try:
            assignee = AgentKind(str(data["assignee"]).lower())
        except ValueError as exc:
            raise ContractValidationError(f"unknown task assignee {data['assignee']!r}") from exc
        attempts = data["review_attempts"]
        if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 0:
            raise ContractValidationError("review_attempts must be a non-negative integer")
        return cls(
            id=_str(data["id"], "task id"),
            title=_str(data["title"], "task title"),
            status=_str(data["status"], "task status"),
            assignee=assignee,
            dependencies=_str_tuple(data["dependencies"], "dependencies"),
            review_attempts=attempts,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "assignee": self.assignee.value,
            "dependencies": list(self.dependencies),
            "review_attempts": self.review_attempts,
        }


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    id: str
    summary: str
    rationale: str

    @classmethod
    def from_dict(cls, value: object) -> "DecisionRecord":
        data = _mapping(value, "decision")
        _keys(data, {"id", "summary", "rationale"}, "decision")
        return cls(_str(data["id"], "decision id"), _str(data["summary"], "decision summary"), _str(data["rationale"], "decision rationale"))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "summary": self.summary, "rationale": self.rationale}


@dataclass(frozen=True, slots=True)
class ReviewReference:
    review_id: str
    submission_id: str
    verdict: ReviewVerdict
    summary: str
    findings: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: object) -> "ReviewReference":
        data = _mapping(value, "review reference")
        _keys(data, {"review_id", "submission_id", "verdict", "summary", "findings"}, "review reference")
        try:
            verdict = ReviewVerdict(str(data["verdict"]).upper())
        except ValueError as exc:
            raise ContractValidationError(f"invalid review verdict {data['verdict']!r}") from exc
        return cls(
            review_id=_str(data["review_id"], "review id"),
            submission_id=_str(data["submission_id"], "submission id"),
            verdict=verdict,
            summary=_str(data["summary"], "review summary"),
            findings=_str_tuple(data["findings"], "findings"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "submission_id": self.submission_id,
            "verdict": self.verdict.value,
            "summary": self.summary,
            "findings": list(self.findings),
        }


@dataclass(frozen=True, slots=True)
class TaskBrief:
    id: str
    title: str
    description: str
    acceptance_criteria: tuple[str, ...]
    assignee: AgentKind
    dependencies: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: object) -> "TaskBrief":
        data = _mapping(value, "task brief")
        _keys(data, {"id", "title", "description", "acceptance_criteria", "assignee", "dependencies"}, "task brief")
        try:
            assignee = AgentKind(str(data["assignee"]).lower())
        except ValueError as exc:
            raise ContractValidationError(f"unknown task assignee {data['assignee']!r}") from exc
        return cls(
            id=_str(data["id"], "task id"),
            title=_str(data["title"], "task title"),
            description=_str(data["description"], "task description"),
            acceptance_criteria=_str_tuple(data["acceptance_criteria"], "acceptance_criteria", allow_empty=False),
            assignee=assignee,
            dependencies=_str_tuple(data["dependencies"], "dependencies"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "acceptance_criteria": list(self.acceptance_criteria),
            "assignee": self.assignee.value,
            "dependencies": list(self.dependencies),
        }


@dataclass(frozen=True, slots=True)
class ManagerContext:
    goal: str
    requirements: tuple[Requirement, ...]
    task_summaries: tuple[TaskSummary, ...]
    decisions: tuple[DecisionRecord, ...]
    relevant_review: ReviewReference | None = None

    @property
    def kind(self) -> AgentKind:
        return AgentKind.MANAGER

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "goal": self.goal,
            "requirements": [item.to_dict() for item in self.requirements],
            "task_summaries": [item.to_dict() for item in self.task_summaries],
            "decisions": [item.to_dict() for item in self.decisions],
        }
        if self.relevant_review is not None:
            payload["relevant_review"] = self.relevant_review.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class DeveloperContext:
    goal: str
    requirements: tuple[Requirement, ...]
    current_task: TaskBrief
    dependencies: tuple[TaskSummary, ...]
    relevant_review: ReviewReference | None
    available_files: tuple[str, ...]

    @property
    def kind(self) -> AgentKind:
        return AgentKind.DEVELOPER

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "goal": self.goal,
            "requirements": [item.to_dict() for item in self.requirements],
            "current_task": self.current_task.to_dict(),
            "dependencies": [item.to_dict() for item in self.dependencies],
            "available_files": list(self.available_files),
        }
        if self.relevant_review is not None:
            payload["relevant_review"] = self.relevant_review.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class FileReference:
    path: str
    description: str

    @classmethod
    def from_dict(cls, value: object) -> "FileReference":
        data = _mapping(value, "file reference")
        _keys(data, {"path", "description"}, "file reference")
        return cls(_str(data["path"], "file path"), _str(data["description"], "file description"))

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "description": self.description}


@dataclass(frozen=True, slots=True)
class SubmissionReference:
    id: str
    version: int
    summary: str
    changed_files: tuple[FileReference, ...]
    test_evidence: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: object) -> "SubmissionReference":
        data = _mapping(value, "submission reference")
        _keys(data, {"id", "version", "summary", "changed_files", "test_evidence"}, "submission reference")
        version = data["version"]
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ContractValidationError("submission version must be a positive integer")
        return cls(
            id=_str(data["id"], "submission id"),
            version=version,
            summary=_str(data["summary"], "submission summary"),
            changed_files=_parse_tuple(data["changed_files"], "changed_files", FileReference.from_dict),
            test_evidence=_str_tuple(data["test_evidence"], "test_evidence"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "summary": self.summary,
            "changed_files": [item.to_dict() for item in self.changed_files],
            "test_evidence": list(self.test_evidence),
        }


@dataclass(frozen=True, slots=True)
class ReviewerContext:
    goal: str
    requirements: tuple[Requirement, ...]
    current_task: TaskBrief
    submission: SubmissionReference
    available_files: tuple[str, ...]

    @property
    def kind(self) -> AgentKind:
        return AgentKind.REVIEWER

    def to_payload(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "requirements": [item.to_dict() for item in self.requirements],
            "current_task": self.current_task.to_dict(),
            "submission": self.submission.to_dict(),
            "available_files": list(self.available_files),
        }


RoleContext = ManagerContext | DeveloperContext | ReviewerContext


@dataclass(frozen=True, slots=True)
class TaskSpec:
    id: str
    title: str
    description: str
    acceptance_criteria: tuple[str, ...]
    assignee: AgentKind
    dependencies: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: object) -> "TaskSpec":
        brief = TaskBrief.from_dict(value)
        return cls(brief.id, brief.title, brief.description, brief.acceptance_criteria, brief.assignee, brief.dependencies)

    def to_dict(self) -> dict[str, Any]:
        return TaskBrief(self.id, self.title, self.description, self.acceptance_criteria, self.assignee, self.dependencies).to_dict()


@dataclass(frozen=True, slots=True)
class ManagerPlan:
    summary: str
    requirements: tuple[Requirement, ...]
    tasks: tuple[TaskSpec, ...]
    assumptions: tuple[str, ...]
    decisions: tuple[DecisionRecord, ...]

    @classmethod
    def from_dict(cls, value: object) -> "ManagerPlan":
        data = _mapping(value, "manager plan")
        _keys(data, {"summary", "requirements", "tasks", "assumptions", "decisions"}, "manager plan")
        plan = cls(
            summary=_str(data["summary"], "plan summary"),
            requirements=_parse_tuple(data["requirements"], "requirements", Requirement.from_dict),
            tasks=_parse_tuple(data["tasks"], "tasks", TaskSpec.from_dict),
            assumptions=_str_tuple(data["assumptions"], "assumptions"),
            decisions=_parse_tuple(data["decisions"], "decisions", DecisionRecord.from_dict),
        )
        if not plan.requirements or not plan.tasks:
            raise ContractValidationError("manager plan must contain requirements and tasks")
        ids = [task.id for task in plan.tasks]
        if len(set(ids)) != len(ids):
            raise ContractValidationError("manager plan task ids must be unique")
        return plan

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "requirements": [item.to_dict() for item in self.requirements],
            "tasks": [item.to_dict() for item in self.tasks],
            "assumptions": list(self.assumptions),
            "decisions": [item.to_dict() for item in self.decisions],
        }


@dataclass(frozen=True, slots=True)
class ManagerDecision:
    action: DecisionAction
    task_id: str | None
    reason: str
    revision_instructions: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: object) -> "ManagerDecision":
        data = _mapping(value, "manager decision")
        _keys(data, {"action", "task_id", "reason", "revision_instructions"}, "manager decision")
        try:
            action = DecisionAction(str(data["action"]).lower())
        except ValueError as exc:
            raise ContractValidationError(f"unknown manager action {data['action']!r}") from exc
        task_id = data["task_id"]
        if task_id is not None:
            task_id = _str(task_id, "task_id")
        return cls(action, task_id, _str(data["reason"], "decision reason"), _str_tuple(data["revision_instructions"], "revision_instructions"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "task_id": self.task_id,
            "reason": self.reason,
            "revision_instructions": list(self.revision_instructions),
        }


@dataclass(frozen=True, slots=True)
class FinalResult:
    status: str
    summary: str
    completed_task_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    limitations: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: object) -> "FinalResult":
        data = _mapping(value, "final result")
        _keys(data, {"status", "summary", "completed_task_ids", "evidence_refs", "limitations"}, "final result")
        return cls(
            status=_str(data["status"], "final status"),
            summary=_str(data["summary"], "final summary"),
            completed_task_ids=_str_tuple(data["completed_task_ids"], "completed_task_ids"),
            evidence_refs=_str_tuple(data["evidence_refs"], "evidence_refs"),
            limitations=_str_tuple(data["limitations"], "limitations"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "completed_task_ids": list(self.completed_task_ids),
            "evidence_refs": list(self.evidence_refs),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class FileChange:
    path: str
    change_type: str
    summary: str

    @classmethod
    def from_dict(cls, value: object) -> "FileChange":
        data = _mapping(value, "file change")
        _keys(data, {"path", "change_type", "summary"}, "file change")
        return cls(_str(data["path"], "changed file path"), _str(data["change_type"], "change type"), _str(data["summary"], "file change summary"))

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "change_type": self.change_type, "summary": self.summary}


@dataclass(frozen=True, slots=True)
class TestResult:
    name: str
    status: str
    summary: str

    @classmethod
    def from_dict(cls, value: object) -> "TestResult":
        data = _mapping(value, "test result")
        _keys(data, {"name", "status", "summary"}, "test result")
        return cls(_str(data["name"], "test name"), _str(data["status"], "test status"), _str(data["summary"], "test summary"))

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "summary": self.summary}


@dataclass(frozen=True, slots=True)
class DeveloperSubmission:
    submission_id: str
    task_id: str
    output_version: int
    summary: str
    changed_files: tuple[FileChange, ...]
    tests: tuple[TestResult, ...]
    ready_for_review: bool
    notes: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: object) -> "DeveloperSubmission":
        data = _mapping(value, "developer submission")
        _keys(data, {"submission_id", "task_id", "output_version", "summary", "changed_files", "tests", "ready_for_review", "notes"}, "developer submission")
        version = data["output_version"]
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ContractValidationError("output_version must be a positive integer")
        return cls(
            submission_id=_str(data["submission_id"], "submission id"),
            task_id=_str(data["task_id"], "task id"),
            output_version=version,
            summary=_str(data["summary"], "submission summary"),
            changed_files=_parse_tuple(data["changed_files"], "changed_files", FileChange.from_dict),
            tests=_parse_tuple(data["tests"], "tests", TestResult.from_dict),
            ready_for_review=_bool(data["ready_for_review"], "ready_for_review"),
            notes=_str_tuple(data["notes"], "notes"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "submission_id": self.submission_id,
            "task_id": self.task_id,
            "output_version": self.output_version,
            "summary": self.summary,
            "changed_files": [item.to_dict() for item in self.changed_files],
            "tests": [item.to_dict() for item in self.tests],
            "ready_for_review": self.ready_for_review,
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class CriterionAssessment:
    criterion_id: str
    passed: bool
    evidence: str
    notes: str

    @classmethod
    def from_dict(cls, value: object) -> "CriterionAssessment":
        data = _mapping(value, "criterion assessment")
        _keys(data, {"criterion_id", "passed", "evidence", "notes"}, "criterion assessment")
        return cls(_str(data["criterion_id"], "criterion id"), _bool(data["passed"], "criterion passed"), _str(data["evidence"], "criterion evidence"), _str(data["notes"], "criterion notes", empty=True))

    def to_dict(self) -> dict[str, Any]:
        return {"criterion_id": self.criterion_id, "passed": self.passed, "evidence": self.evidence, "notes": self.notes}


@dataclass(frozen=True, slots=True)
class ReviewFinding:
    id: str
    severity: FindingSeverity
    summary: str
    evidence: str
    criterion_id: str | None

    @classmethod
    def from_dict(cls, value: object) -> "ReviewFinding":
        data = _mapping(value, "review finding")
        _keys(data, {"id", "severity", "summary", "evidence", "criterion_id"}, "review finding")
        try:
            severity = FindingSeverity(str(data["severity"]).lower())
        except ValueError as exc:
            raise ContractValidationError(f"unknown finding severity {data['severity']!r}") from exc
        criterion_id = data["criterion_id"]
        if criterion_id is not None:
            criterion_id = _str(criterion_id, "criterion id")
        return cls(_str(data["id"], "finding id"), severity, _str(data["summary"], "finding summary"), _str(data["evidence"], "finding evidence"), criterion_id)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "severity": self.severity.value, "summary": self.summary, "evidence": self.evidence, "criterion_id": self.criterion_id}


@dataclass(frozen=True, slots=True)
class ReviewResult:
    review_id: str
    submission_id: str
    verdict: ReviewVerdict
    summary: str
    assessments: tuple[CriterionAssessment, ...]
    findings: tuple[ReviewFinding, ...]
    checks_not_performed: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: object) -> "ReviewResult":
        data = _mapping(value, "review result")
        _keys(data, {"review_id", "submission_id", "verdict", "summary", "assessments", "findings", "checks_not_performed"}, "review result")
        try:
            verdict = ReviewVerdict(str(data["verdict"]).upper())
        except ValueError as exc:
            raise ContractValidationError(f"invalid review verdict {data['verdict']!r}") from exc
        result = cls(
            review_id=_str(data["review_id"], "review id"),
            submission_id=_str(data["submission_id"], "submission id"),
            verdict=verdict,
            summary=_str(data["summary"], "review summary"),
            assessments=_parse_tuple(data["assessments"], "assessments", CriterionAssessment.from_dict),
            findings=_parse_tuple(data["findings"], "findings", ReviewFinding.from_dict),
            checks_not_performed=_str_tuple(data["checks_not_performed"], "checks_not_performed"),
        )
        if result.verdict is ReviewVerdict.PASS and any(not item.passed for item in result.assessments):
            raise ContractValidationError("PASS review cannot contain a failed criterion")
        if result.verdict is ReviewVerdict.FAIL and not result.findings:
            raise ContractValidationError("FAIL review must contain at least one finding")
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "submission_id": self.submission_id,
            "verdict": self.verdict.value,
            "summary": self.summary,
            "assessments": [item.to_dict() for item in self.assessments],
            "findings": [item.to_dict() for item in self.findings],
            "checks_not_performed": list(self.checks_not_performed),
        }


AgentOutput = ManagerPlan | ManagerDecision | FinalResult | DeveloperSubmission | ReviewResult


def parse_agent_output(kind: AgentKind, value: object) -> AgentOutput:
    """Validate the output expected from an agent kind.

    M1.1 uses one output per invocation: Manager returns a plan, Developer a
    submission, and Reviewer a review. Manager decision/final-result schemas
    are also available as structured contracts for later workflow calls.
    """

    if kind is AgentKind.MANAGER:
        return ManagerPlan.from_dict(value)
    if kind is AgentKind.DEVELOPER:
        return DeveloperSubmission.from_dict(value)
    if kind is AgentKind.REVIEWER:
        return ReviewResult.from_dict(value)
    raise ContractValidationError(f"unsupported agent kind {kind!r}")
