"""Immutable command scope, approval interventions, results and test evidence."""
from dataclasses import dataclass, asdict
from hashlib import sha256
import json
import math
from app.domain.agents import AgentKind


@dataclass(frozen=True, slots=True)
class CommandLimits:
    max_commands: int = 20
    max_requests: int = 60
    max_timeout_seconds: float = 30
    max_output_bytes: int = 65536  # Per stream; excess bytes are drained and discarded.
    max_workspace_bytes: int = 2097152
    max_workspace_entries: int = 2000

    def __post_init__(self):
        if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v <= 0
               for v in asdict(self).values()):
            raise ValueError('command limits must be finite positive numbers')
        if any(not isinstance(v, int) for k, v in asdict(self).items() if k != 'max_timeout_seconds'):
            raise ValueError('command count and byte limits must be integers')


@dataclass(frozen=True, slots=True)
class CommandProfile:
    name: str
    executable: str
    args: tuple[str, ...]
    is_test: bool = False

    def __post_init__(self):
        if (not isinstance(self.name, str) or not self.name or not isinstance(self.executable, str)
                or not isinstance(self.is_test, bool) or not isinstance(self.args, tuple)
                or not all(isinstance(a, str) and '\x00' not in a for a in self.args)):
            raise ValueError('profile requires a name and immutable argument vector')


@dataclass(frozen=True, slots=True)
class CommandRequest:
    actor: AgentKind
    attempt_id: str
    generation: int
    profile: str
    executable: str
    args: tuple[str, ...]
    workspace_version: str
    cwd: str = '.'
    environment: tuple[tuple[str, str], ...] = ()
    timeout_seconds: float = 10
    max_output_bytes: int = 8192

    def __post_init__(self):
        if (not isinstance(self.args, tuple) or not all(isinstance(a, str) and '\x00' not in a for a in self.args)
                or not isinstance(self.environment, tuple)
                or any(not isinstance(e, tuple) or len(e) != 2 or not all(isinstance(v, str) for v in e)
                       for e in self.environment)):
            raise ValueError('command arguments and environment must be immutable string tuples')
        if (not isinstance(self.actor, AgentKind) or not isinstance(self.attempt_id, str) or not self.attempt_id
                or not isinstance(self.generation, int) or isinstance(self.generation, bool) or self.generation < 1
                or not isinstance(self.executable, str) or not self.executable.startswith('/')
                or '\x00' in self.executable or not isinstance(self.profile, str) or not self.profile
                or not isinstance(self.cwd, str) or not isinstance(self.workspace_version, str)
                or len(self.workspace_version) != 64 or any(c not in '0123456789abcdef' for c in self.workspace_version)):
            raise ValueError('invalid command identity, executable or workspace version')
        if (not isinstance(self.timeout_seconds, (int, float)) or isinstance(self.timeout_seconds, bool)
                or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0
                or not isinstance(self.max_output_bytes, int) or isinstance(self.max_output_bytes, bool)
                or self.max_output_bytes < 1):
            raise ValueError('invalid command bounds')
        if sum(len(a) for a in self.args) + sum(len(k) + len(v) for k, v in self.environment) > 16384:
            raise ValueError('command request size limit exceeded')


@dataclass(frozen=True, slots=True)
class CommandApproval:
    id: str
    request: CommandRequest
    scope_digest: str
    status: str = 'pending'  # pending -> approved/denied -> consumed
    reason: str = ''


@dataclass(frozen=True, slots=True)
class CommandAuditRecord:
    id: str
    action: str
    actor: str
    attempt_id: str
    generation: int
    approval_id: str | None
    outcome: str
    reason: str


@dataclass(frozen=True, slots=True)
class CommandResult:
    id: str
    approval_id: str
    request: CommandRequest
    is_test: bool
    outcome: str  # succeeded, failed, timed_out, canceled, paused, terminated, error, cleanup_failed
    exit_code: int | None
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    started_at: str
    duration_seconds: float
    workspace_before: str
    workspace_after: str | None
    pid: int | None
    cleanup_complete: bool

    @property
    def succeeded(self):
        return self.outcome == 'succeeded' and self.exit_code == 0 and self.cleanup_complete

    def to_dict(self):
        data = asdict(self)
        data['request']['actor'] = self.request.actor.value
        data['log_ref'] = self.id + ':logs'
        return data


@dataclass(frozen=True, slots=True)
class TestEvidence:
    result: CommandResult
    workspace_version: str
    stale: bool

    @property
    def passed(self):
        return not self.stale and self.result.succeeded

    def to_dict(self):
        return {'command': self.result.to_dict(), 'workspace_version': self.workspace_version,
                'stale': self.stale, 'passed': self.passed}


def scope_digest(request, root, executable_hash, environment, profile):
    data = asdict(request)
    data['actor'] = request.actor.value
    data.update(root=str(root), executable_hash=executable_hash, effective_environment=environment,
                configured_profile=asdict(profile))
    return sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
