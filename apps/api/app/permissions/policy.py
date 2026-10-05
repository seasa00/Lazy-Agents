"""Fail-closed workspace and role policy. No OS sandbox is implied."""
from dataclasses import dataclass
from pathlib import Path
from app.domain.agents import AgentKind


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class WorkspacePolicy:
    root: Path
    protected: tuple[str, ...] = ()
    max_file_bytes: int = 65536
    max_result_bytes: int = 262144
    max_entries: int = 1000

    def __post_init__(self):
        root = Path(self.root).absolute()
        if not root.is_dir() or root.is_symlink() or root == Path(root.anchor):
            raise ValueError('workspace must be an existing non-symlink directory, not filesystem root')
        # OS aliases above a supplied workspace (e.g. macOS /var) are resolved once.
        object.__setattr__(self, 'root', root.resolve(strict=True))
        object.__setattr__(self, 'protected', tuple(self.protected))
        if min(self.max_file_bytes, self.max_result_bytes, self.max_entries) < 1:
            raise ValueError('workspace bounds must be positive')
        for path in self.protected:
            self.parts(path)

    @staticmethod
    def parts(path, *, listing=False):
        if listing and path == '.':
            return ()
        if (not isinstance(path, str) or not path or '\\' in path or '\x00' in path
                or ':' in path or path.startswith('/')
                or any(p in {'', '.', '..'} for p in path.split('/'))):
            raise ValueError('path must be canonical workspace-relative; traversal denied')
        return tuple(path.split('/'))

    def check_path(self, path, *, listing=False):
        parts = self.parts(path, listing=listing)
        reserved = {'.git', '.agents', '.codex', '.aws', '.ssh', '.gnupg',
                    '.runtime', '.artifacts', '__pycache__'}
        lowered = tuple(p.casefold() for p in parts)
        if any(p in reserved or p.startswith('.env') or p.endswith(('.pem', '.key'))
               or p in {'credentials', 'credentials.json', 'secrets.json'} for p in lowered):
            raise ValueError('protected path denied')
        for entry in self.protected:
            prefix = tuple(p.casefold() for p in self.parts(entry))
            if lowered[:len(prefix)] == prefix:
                raise ValueError('protected path denied')
        return parts

    def decide(self, actor, operation, submission_id=None):
        if actor is AgentKind.DEVELOPER and operation in {'list', 'read', 'write', 'edit', 'capture_submission'}:
            return PermissionDecision(True, 'Developer workspace access')
        if actor in {AgentKind.REVIEWER, AgentKind.MANAGER} and operation in {'list', 'read'} and submission_id:
            return PermissionDecision(True, 'captured submission read only')
        return PermissionDecision(False, 'role or operation denied; Reviewer and Manager require captured evidence')

    def decide_command(self, actor):
        if actor is AgentKind.DEVELOPER:
            return PermissionDecision(True, 'Developer may request an exact command approval')
        return PermissionDecision(False, 'command execution is denied for Reviewer and Manager')
