"""Private filesystem implementation used only by the permission gateway.

Directory descriptors and O_NOFOLLOW reject symlinks at every workspace component.
Atomic replacement avoids following hardlinks. External processes can still rename
an opened directory or race the final hash check: this is not hostile-process isolation.
"""
from contextlib import contextmanager
import os
import stat
from uuid import uuid4
from app.domain.artifacts import content_hash


class FileConflict(ValueError):
    pass


class WorkspaceFiles:
    def __init__(self, policy):
        self.policy = policy
        info = policy.root.stat()
        self.identity = (info.st_dev, info.st_ino)

    @contextmanager
    def directory(self, parts):
        fd = os.open(self.policy.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) != self.identity:
                raise ValueError('workspace root replaced')
            for part in parts:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            yield fd
        finally:
            os.close(fd)

    def read_at(self, fd, name):
        try:
            child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        except FileNotFoundError:
            return None
        try:
            info = os.fstat(child)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('only regular, singly linked files are supported')
            with os.fdopen(child, 'rb', closefd=False) as stream:
                data = stream.read(self.policy.max_file_bytes + 1)
            if len(data) > self.policy.max_file_bytes:
                raise ValueError('file size limit exceeded')
            data.decode('utf-8')
            return data
        finally:
            os.close(child)

    def read(self, path):
        parts = self.policy.check_path(path)
        with self.directory(parts[:-1]) as fd:
            return self.read_at(fd, parts[-1])

    def list(self, path):
        parts = self.policy.check_path(path, listing=True)
        result = []
        with self.directory(parts) as fd:
            with os.scandir(fd) as entries:
                for count, entry in enumerate(entries, 1):
                    if count > self.policy.max_entries:
                        raise ValueError('directory entry limit exceeded')
                    relative = '/'.join((*parts, entry.name))
                    try:
                        self.policy.check_path(relative)
                    except ValueError:
                        continue
                    if entry.is_symlink():
                        continue
                    info = entry.stat(follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode) or (stat.S_ISREG(info.st_mode) and info.st_nlink == 1):
                        result.append(relative + ('/' if stat.S_ISDIR(info.st_mode) else ''))
        return tuple(sorted(result))

    def write(self, path, data, expected_hash, before_mutation):
        parts = self.policy.check_path(path)
        if len(data) > self.policy.max_file_bytes:
            raise ValueError('file size limit exceeded')
        with self.directory(parts[:-1]) as fd:
            before = self.read_at(fd, parts[-1])
            if (None if before is None else content_hash(before)) != expected_hash:
                raise FileConflict('expected hash conflict')
            before_mutation()
            mode = 0o600 if before is None else stat.S_IMODE(os.stat(parts[-1], dir_fd=fd, follow_symlinks=False).st_mode)
            name = '.workspace-' + uuid4().hex
            tmp = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            try:
                with os.fdopen(tmp, 'wb') as stream:
                    os.fchmod(stream.fileno(), mode)
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                if self.read_at(fd, parts[-1]) != before:
                    raise FileConflict('external edit during write')
                before_mutation()
                os.replace(name, parts[-1], src_dir_fd=fd, dst_dir_fd=fd)
            finally:
                try:
                    os.unlink(name, dir_fd=fd)
                except FileNotFoundError:
                    pass
        return before
