"""Capture verified gateway changes as immutable values, never live path references."""
from difflib import unified_diff
from app.domain.artifacts import CapturedSubmission, FileChange
from app.tools.files import FileConflict


def capture(files, submission_id, attempt_id, generation, changes, paths, max_bytes):
    if not changes or len(paths) != len(set(paths)) or set(paths) != set(changes):
        raise ValueError('submission paths must match all gateway changes for this attempt')
    result = []
    for path, (before, after) in sorted(changes.items()):
        if files.read(path) != after:
            raise FileConflict('external edit before submission capture')
        lines = unified_diff(
            ([] if before is None else before.decode('utf-8').splitlines(keepends=True)),
            after.decode('utf-8').splitlines(keepends=True),
            fromfile='/dev/null' if before is None else 'a/' + path, tofile='b/' + path)
        diff = ''.join(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n' for line in lines)
        result.append(FileChange(path, before, after, diff))
    snapshot = CapturedSubmission(submission_id, attempt_id, generation, tuple(result))
    if len(snapshot.serialize().encode()) > max_bytes:
        raise ValueError('submission size limit exceeded')
    return snapshot
