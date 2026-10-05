"""Immutable submission evidence, including optional captured workspace files."""
from dataclasses import dataclass
from hashlib import sha256
from app.agents.contracts import DeveloperSubmission
from app.domain.artifacts import CapturedSubmission


@dataclass(frozen=True, slots=True)
class TaskAttempt:
    id: str
    task_id: str
    run_id: str
    number: int
    generation: int
    requirement_version: int

    def __post_init__(self):
        if not all((self.id, self.task_id, self.run_id)) or min(self.number, self.generation, self.requirement_version) < 1:
            raise ValueError('invalid task attempt')


@dataclass(frozen=True, slots=True)
class SubmissionManifest:
    id: str
    task_id: str
    attempt_id: str
    version: int
    generation: int
    requirement_version: int
    output: DeveloperSubmission
    evidence: tuple[str, ...]
    digest: str
    files: CapturedSubmission | None = None

    def __post_init__(self):
        if (not self.attempt_id or not self.id or self.id != self.output.submission_id
                or self.task_id != self.output.task_id or self.version != self.output.output_version
                or min(self.version, self.generation, self.requirement_version) < 1
                or not self.evidence or not self.output.tests or not self.output.changed_files
                or self.digest != sha256('\n'.join(self.evidence).encode()).hexdigest()):
            raise ValueError('invalid immutable submission manifest')
        if self.files is not None and (self.files.id != self.id or self.files.attempt_id != self.attempt_id
                or self.files.generation != self.generation or self.files.serialize() not in self.evidence):
            raise ValueError('file evidence does not match immutable manifest')

    @classmethod
    def capture(cls, output, attempt, evidence, files=None):
        if (output.submission_id != attempt.id + ':submission' or output.task_id != attempt.task_id
                or output.output_version != attempt.number or not output.ready_for_review):
            raise ValueError('submission identity/version does not match current attempt')
        if not output.tests or not evidence or not output.changed_files:
            raise ValueError('missing submission evidence')
        return cls(output.submission_id, output.task_id, attempt.id, attempt.number,
                   attempt.generation, attempt.requirement_version, output, tuple(evidence),
                   sha256('\n'.join(evidence).encode()).hexdigest(), files)
