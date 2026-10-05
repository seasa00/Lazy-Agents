"""POSIX bounded argv execution. Approved commands are trusted local code, not a sandbox."""
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import time
from uuid import uuid4
from app.domain.commands import CommandResult
from app.domain.commands import CommandRequest


def workspace_version(files, limits):
    """Hash all workspace entries, including protected files (hashes only).

    Bounded, no-follow, fail-closed traversal. Metadata notices changes restored to
    identical bytes. No claim of an atomic snapshot against external processes.
    """
    entries, total = [], 0
    def walk(fd, prefix):
        nonlocal total
        if prefix.count('/') > 64:
            raise ValueError('workspace directory depth limit exceeded')
        with os.scandir(fd) as scan:
            names = []
            for entry in scan:
                names.append(entry.name)
                if len(names) + len(entries) > limits.max_workspace_entries:
                    raise ValueError('workspace entry limit exceeded')
        for name in sorted(names):
            path = prefix + name
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISDIR(info.st_mode):
                entries.append((path + '/', mode, info.st_mtime_ns))
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    walk(child, path + '/')
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                try:
                    before = os.fstat(child)
                    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                        raise ValueError('unsupported workspace entry')
                    digest = sha256()
                    while True:
                        data = os.read(child, min(65536, limits.max_workspace_bytes - total + 1))
                        if not data:
                            break
                        total += len(data)
                        if total > limits.max_workspace_bytes:
                            raise ValueError('workspace byte limit exceeded')
                        digest.update(data)
                    after = os.fstat(child)
                    if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                            after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                        raise ValueError('workspace changed during fingerprint')
                    entries.append((path, digest.hexdigest(), mode, after.st_mtime_ns, after.st_ctime_ns))
                finally:
                    os.close(child)
            else:
                raise ValueError('workspace contains symlink, hardlink or special file')
            if len(entries) > limits.max_workspace_entries:
                raise ValueError('workspace entry limit exceeded')
    with files.directory(()) as fd:
        walk(fd, '')
    return sha256(json.dumps(entries, ensure_ascii=True).encode()).hexdigest()


def executable_digest(path):
    target = Path(path)
    if not target.is_absolute() or target.resolve(strict=True) != target or not target.is_file() or not os.access(target, os.X_OK):
        raise ValueError('executable must be a canonical executable file from a configured profile')
    if target.name.casefold() in {'sh', 'bash', 'zsh', 'dash', 'fish', 'csh', 'tcsh', 'ksh', 'cmd.exe', 'powershell', 'pwsh'}:
        raise ValueError('shell profiles are not supported')
    digest = sha256()
    with target.open('rb') as stream:
        total = 0
        while data := stream.read(65536):
            total += len(data)
            if total > 134217728:
                raise ValueError('executable size limit exceeded')
            digest.update(data)
    return digest.hexdigest()


def command_environment(request):
    # No inherited credentials, PYTHONPATH, startup hooks, loader flags, HOME or proxy settings.
    environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'TZ': 'UTC',
                   'PYTHONDONTWRITEBYTECODE': '1'}
    seen = set()
    for key, value in request.environment:
        if key not in {'LANG', 'LC_ALL', 'TZ', 'PYTHONHASHSEED'} or key in seen or '\x00' in value or len(value) > 256:
            raise ValueError('environment override denied')
        environment[key] = value
        seen.add(key)
    return environment


@dataclass
class RunningCommand:
    process: subprocess.Popen
    request: CommandRequest
    approval_id: str
    is_test: bool
    started_at: str
    started: float


def launch(request, approval_id, is_test, root, environment):
    started_at = datetime.now(timezone.utc).isoformat()
    process = subprocess.Popen([request.executable, *request.args], cwd=root / request.cwd,
        env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        shell=False, start_new_session=True, close_fds=True)
    return RunningCommand(process, request, approval_id, is_test, started_at, time.monotonic())


def _kill_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
        return True
    except ProcessLookupError:
        return True
    except OSError:
        return False


def collect(running, stop_reason, version_after):
    """Continuously drain both pipes while bounding retained bytes and elapsed time.

    Always kill the original process group, even if its leader exited normally;
    inherited pipes cannot keep the collector alive indefinitely. Detached children
    that escape the group are outside this trusted-code containment contract.
    """
    process, request = running.process, running.request
    output = {'stdout': bytearray(), 'stderr': bytearray()}
    truncated = {'stdout': False, 'stderr': False}
    outcome, cleanup, code = None, True, None
    selector = selectors.DefaultSelector()
    killed_at = None
    try:
        for name, pipe in (('stdout', process.stdout), ('stderr', process.stderr)):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, name)
        while True:
            now = time.monotonic()
            reason = stop_reason()
            if outcome is None and reason:
                outcome = reason
            if outcome is None and now - running.started >= request.timeout_seconds:
                outcome = 'timed_out'
            code = process.poll()
            if killed_at is None and (outcome is not None or code is not None):
                if outcome is None and code is not None:
                    try:
                        os.killpg(process.pid, 0)
                    except ProcessLookupError:
                        pass
                    else:
                        # A successful leader with unfinished descendants is not
                        # a completed successful command.
                        outcome = 'terminated'
                cleanup = _kill_group(process)
                killed_at = now
            if killed_at is not None and now - killed_at > 1:
                # An escaped descendant may hold a pipe open. Do not hang or call it success.
                if selector.get_map() or process.poll() is None:
                    cleanup = False
                break
            for key, _ in selector.select(0.02):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                name = key.data
                room = request.max_output_bytes - len(output[name])
                output[name].extend(data[:room])
                if len(data) > room:
                    truncated[name] = True
            if killed_at is not None and process.poll() is not None and not selector.get_map():
                break
        code = process.wait(timeout=1)
        if outcome is None:
            outcome = 'succeeded' if code == 0 else 'failed'
    except Exception:
        outcome = 'error'
    finally:
        cleanup = _kill_group(process) and cleanup
        try:
            code = process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            cleanup = False
        selector.close()
        process.stdout.close()
        process.stderr.close()
    try:
        after = version_after()
    except (ValueError, OSError):
        after = None
    if not cleanup:
        outcome = 'cleanup_failed'
    # Replace invalid UTF-8, bounding even the expanded replacement characters.
    decoded = {}
    for name, data in output.items():
        encoded = data.decode('utf-8', errors='replace').encode('utf-8')
        truncated[name] = truncated[name] or len(encoded) > request.max_output_bytes
        decoded[name] = encoded[:request.max_output_bytes].decode('utf-8', errors='ignore')
    return CommandResult('command_' + uuid4().hex, running.approval_id, request, running.is_test,
        outcome, code, decoded['stdout'], decoded['stderr'], truncated['stdout'], truncated['stderr'],
        running.started_at, time.monotonic() - running.started, request.workspace_version, after,
        process.pid, cleanup)
