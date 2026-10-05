"""Run-owned workflow records retained across pauses, revisions and replans."""
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from enum import Enum
from app.agents.contracts import FinalResult
from app.domain.submissions import TaskAttempt, SubmissionManifest
from app.domain.reviews import ReviewRound, RevisionBrief
from app.orchestration.limits import ExecutionLimits
from app.usage.records import LLMCallRecord
from app.domain.commands import CommandResult


@dataclass(frozen=True, slots=True)
class WorkflowState:
    limits: ExecutionLimits = ExecutionLimits()
    invocations: int = 0
    llm_calls: int = 0
    iterations: int = 0
    tasks_created: int = 0
    replans: int = 0
    pending: str | None = None
    pending_permissions: tuple[str, ...] = ()
    command_results: tuple[CommandResult, ...] = ()
    pending_instructions: tuple[str, ...] = ()
    instructions: tuple[str, ...] = ()
    blocked_reason: str | None = None
    exhausted_limit: bool = False
    resume_phase: str | None = None
    attempts: tuple[TaskAttempt, ...] = ()
    submissions: tuple[SubmissionManifest, ...] = ()
    reviews: tuple[ReviewRound, ...] = ()
    revisions: tuple[RevisionBrief, ...] = ()
    accepted: tuple[str, ...] = ()
    call_records: tuple[LLMCallRecord, ...] = ()
    final_result: FinalResult | None = None

    def to_dict(self):
        def encode(value):
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, bytes):
                return value.decode('utf-8')  # Workspace file contracts admit UTF-8 only.
            if isinstance(value, Enum):
                return value.value
            if is_dataclass(value):
                return {f.name: encode(getattr(value, f.name)) for f in fields(value)}
            if isinstance(value, tuple):
                return [encode(v) for v in value]
            return value
        return encode(self)
