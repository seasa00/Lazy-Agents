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
from app.domain.agents import AgentConfigSnapshot
from app.domain.recovery import ExecutionCheckpoint, RecoveryState


@dataclass(frozen=True, slots=True)
class InvocationRecord:
    id: str
    agent_id: str
    config_digest: str
    phase: str
    generation: int
    protocol_version: int = 1


@dataclass(frozen=True, slots=True)
class ToolContinuation:
    """Serializable Developer tool-loop boundary; never stores LangChain objects."""
    id: str
    run_id: str
    task_id: str
    attempt_id: str
    invocation_id: str
    agent_id: str
    generation: int
    tool_request_id: str
    operation_id: str
    tool_name: str
    arguments_json: str
    permission_id: str
    state: str
    context_json: str
    prior_results_json: str
    provider_request_id: str
    provider_calls: int
    tool_calls: int
    retry_attempts: int
    result_json: str | None
    created_at: str
    updated_at: str



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
    tool_continuations: tuple[ToolContinuation, ...] = ()
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
    agent_snapshots: tuple[AgentConfigSnapshot, ...] = ()
    invocation_records: tuple[InvocationRecord, ...] = ()
    checkpoint: ExecutionCheckpoint | None = None
    recovery_epoch: int = 0
    recovery: RecoveryState | None = None
    workspace_tools: bool = False

    def to_dict(self):
        def encode(value):
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, bytes):
                return value.decode('utf-8')  # Workspace file contracts admit UTF-8 only.
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, ToolContinuation):
                # Never expose retained model context or tool output through run snapshots.
                return {name: getattr(value, name) for name in (
                    'id', 'run_id', 'task_id', 'attempt_id', 'invocation_id', 'agent_id',
                    'generation', 'tool_request_id', 'operation_id', 'tool_name',
                    'permission_id', 'state', 'provider_request_id', 'provider_calls',
                    'tool_calls', 'retry_attempts', 'created_at', 'updated_at')}
            if is_dataclass(value):
                return {f.name: encode(getattr(value, f.name)) for f in fields(value)}
            if isinstance(value, tuple):
                return [encode(v) for v in value]
            return value
        return encode(self)
