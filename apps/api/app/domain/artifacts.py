"""Value-only immutable file evidence, held outside agent-writable content."""
from dataclasses import dataclass
from hashlib import sha256
import json
from app.domain.commands import TestEvidence


def content_hash(content: bytes) -> str:
    return sha256(content).hexdigest()


@dataclass(frozen=True, slots=True)
class FileChange:
    path: str
    before: bytes | None
    content: bytes
    diff: str

    @property
    def before_hash(self):
        return None if self.before is None else content_hash(self.before)

    @property
    def content_hash(self):
        return content_hash(self.content)

    def to_dict(self):
        return {'path': self.path, 'change_type': 'added' if self.before is None else 'modified',
                'before_hash': self.before_hash, 'content_hash': self.content_hash,
                'content': self.content.decode('utf-8'), 'diff': self.diff}


@dataclass(frozen=True, slots=True)
class CapturedSubmission:
    id: str
    attempt_id: str
    generation: int
    files: tuple[FileChange, ...]
    workspace_version: str | None = None
    tests: tuple[TestEvidence, ...] = ()

    def serialize(self):
        data = {'submission_id': self.id, 'attempt_id': self.attempt_id,
                'generation': self.generation, 'files': [f.to_dict() for f in self.files]}
        if self.workspace_version is not None:
            data.update(workspace_version=self.workspace_version, tests=[t.to_dict() for t in self.tests])
        return json.dumps(data, sort_keys=True, ensure_ascii=True)

    @property
    def digest(self):
        return content_hash(self.serialize().encode())


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    id: str
    actor: str
    operation: str
    attempt_id: str
    generation: int
    path: str
    submission_id: str | None
    outcome: str
    before_hash: str | None = None
    after_hash: str | None = None
