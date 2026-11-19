"""Versioned, allowlisted JSON values; file evidence lives in a content-addressed sidecar."""
from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path
import os
import tempfile
from app.persistence.store import StoreError

MODULES = ('app.agents.contracts', 'app.domain.agents', 'app.domain.projects',
           'app.domain.tasks', 'app.domain.workflow', 'app.domain.submissions',
           'app.domain.reviews', 'app.domain.artifacts', 'app.domain.commands',
           'app.domain.events', 'app.domain.recovery', 'app.orchestration.limits', 'app.providers.base',
           'app.usage.records', 'app.usage.pricing')


class ArtifactIntegrityError(StoreError):
    pass


class Codec:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.types = {}
        for name in MODULES:
            for value in vars(import_module(name)).values():
                if isinstance(value, type) and (is_dataclass(value) or issubclass(value, Enum)):
                    self.types[value.__module__ + '.' + value.__name__] = value

    def external(self, value):
        data = self.dumps(value).encode()
        digest = sha256(data).hexdigest()
        path = self.root / digest
        if path.exists():
            if path.read_bytes() != data:
                raise ArtifactIntegrityError('artifact hash mismatch: ' + digest)
        else:
            fd, temp = tempfile.mkstemp(dir=self.root)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp, path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        return {'$artifact': digest, 'size': len(data)}

    def encode(self, value):
        if isinstance(value, Enum):
            return {'$enum': type(value).__module__ + '.' + type(value).__name__, 'value': value.value}
        if isinstance(value, Decimal):
            return {'$decimal': str(value)}
        if isinstance(value, bytes):
            return {'$bytes': value.hex()}
        if is_dataclass(value):
            # Evidence may contain captured file bytes and logs. Never inline it in SQL.
            external_fields = {'ExecutionOperation': {'change', 'proposal', 'result'}, 'SubmissionManifest': {'evidence', 'files'},
                               'CommandResult': {'stdout', 'stderr'},
                               'FileChange': {'before', 'content', 'diff'}}.get(type(value).__name__, set())
            return {'$type': type(value).__module__ + '.' + type(value).__name__,
                    'fields': {f.name: (self.external(getattr(value, f.name)) if f.name in external_fields
                                      else self.encode(getattr(value, f.name))) for f in fields(value)}}
        if isinstance(value, tuple):
            return {'$tuple': [self.encode(v) for v in value]}
        if isinstance(value, list):
            return [self.encode(v) for v in value]
        if isinstance(value, dict):
            return {'$map': [[k, self.encode(v)] for k, v in value.items()]}
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise StoreError('unsupported persisted value: ' + type(value).__name__)

    def decode(self, value):
        if isinstance(value, list):
            return [self.decode(v) for v in value]
        if not isinstance(value, dict):
            return value
        if '$artifact' in value:
            digest = value['$artifact']
            if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ArtifactIntegrityError('invalid artifact reference')
            try:
                data = (self.root / digest).read_bytes()
            except OSError as exc:
                raise ArtifactIntegrityError('missing artifact: ' + digest) from exc
            if sha256(data).hexdigest() != digest or len(data) != value['size']:
                raise ArtifactIntegrityError('artifact hash mismatch: ' + digest)
            return self.loads(data)
        if '$type' in value:
            return self.types[value['$type']](**{k: self.decode(v) for k, v in value['fields'].items()})
        if '$enum' in value:
            return self.types[value['$enum']](value['value'])
        if '$decimal' in value:
            return Decimal(value['$decimal'])
        if '$bytes' in value:
            return bytes.fromhex(value['$bytes'])
        if '$tuple' in value:
            return tuple(self.decode(v) for v in value['$tuple'])
        if '$map' in value:
            return {k: self.decode(v) for k, v in value['$map']}
        raise StoreError('invalid persisted JSON value')

    def dumps(self, value):
        return json.dumps(self.encode(value), sort_keys=True, separators=(',', ':'))

    def loads(self, value):
        return self.decode(json.loads(value))
