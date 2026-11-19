"""Durable execution boundaries and conservative operator reconciliation values."""
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from app.domain.artifacts import FileChange, CapturedSubmission
from app.domain.commands import CommandRequest, CommandResult
from app.usage.records import LLMCallRecord


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class OutcomeCertainty(StrEnum):
    CONFIRMED_SUCCESS = 'confirmed_success'
    CONFIRMED_FAILURE = 'confirmed_failure'
    INTERRUPTED = 'interrupted'
    UNCERTAIN = 'uncertain'


class OperationStage(StrEnum):
    PREPARED = 'prepared'
    EXECUTING = 'executing'
    SETTLED = 'settled'


@dataclass(frozen=True, slots=True)
class ExecutionCheckpoint:
    project_id: str
    run_id: str
    phase: str
    generation: int
    recovery_epoch: int
    requirement_version: int
    task_id: str | None = None
    attempt_id: str | None = None
    invocation_id: str | None = None
    operation_id: str | None = None
    boundary: str = 'safe'
    safe_phase: str = 'plan'
    last_safe_boundary: str = 'workflow.initialized'
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class ExecutionOperation:
    id: str
    kind: str  # provider, file, command
    checkpoint: ExecutionCheckpoint
    stage: OperationStage = OperationStage.PREPARED
    certainty: OutcomeCertainty = OutcomeCertainty.INTERRUPTED
    operation: str = ''
    path: str = ''
    before_hash: str | None = None
    after_hash: str | None = None
    change: FileChange | None = None
    request: CommandRequest | None = None
    approval_id: str | None = None
    pid: int | None = None  # Diagnostic only; never authority to signal a process.
    call_record: LLMCallRecord | None = None
    proposal: object = None
    result: CommandResult | CapturedSubmission | None = None
    started_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def evolve(self, **changes):
        now = utc_now()
        cp = replace(self.checkpoint, boundary=self.kind + '.' + changes.get('stage', self.stage).value, updated_at=now)
        return replace(self, checkpoint=cp, updated_at=now, **changes)


@dataclass(frozen=True, slots=True)
class RecoveryIssue:
    id: str
    kind: str
    certainty: OutcomeCertainty
    reason: str
    resolved: bool = False
    resolution: str = ''


@dataclass(frozen=True, slots=True)
class RecoveryState:
    epoch: int
    original_status: str
    resume_phase: str
    issues: tuple[RecoveryIssue, ...] = ()
    requires_resume: bool = True
    inspected: bool = True
    started_at: str = field(default_factory=utc_now)
    original_blocked_reason: str | None = None
    original_resume_phase: str | None = None

    @property
    def unresolved(self):
        return tuple(i for i in self.issues if not i.resolved)


def checkpoint(project, run, boundary):
    wf = run.workflow
    old = wf.checkpoint
    attempt = next((a for a in reversed(wf.attempts) if a.task_id == run.current_task_id), None)
    safe = old.safe_phase if old and wf.pending else run.phase
    return ExecutionCheckpoint(project.id, run.id, run.phase, run.execution_generation,
        wf.recovery_epoch, project.requirement_version, run.current_task_id,
        attempt.id if attempt else None, wf.pending if wf.pending and wf.pending.startswith('op_') else None,
        wf.pending, 'reserved' if wf.pending else 'safe', safe,
        old.last_safe_boundary if old and wf.pending else boundary,
        old.created_at if old else utc_now())


def retain_calls(wf, records):
    """Preserve immutable original calls; later receipts live on operation records."""
    by_id = {c.call_id: c for c in wf.call_records}
    added = []
    for record in records:
        existing = by_id.get(record.call_id)
        if existing is None:
            added.append(record)
            by_id[record.call_id] = record
        elif existing != record and existing.status != 'interrupted':
            raise ValueError('conflicting immutable provider call receipt')
    return replace(wf, call_records=(*wf.call_records, *added))
