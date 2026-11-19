"""Single-process SQLite store. Relational current state; append-only event history.

Reducers and artifact IO run under the application lock, BEFORE BEGIN IMMEDIATE.
Opening is read-only with respect to workflows; runner/operator startup applies the recovery gate.
"""
from dataclasses import replace
from pathlib import Path
from threading import RLock
import json
import sqlite3
from app.domain.events import DomainEvent
from app.persistence.operations import StateOperations
from app.persistence.models import Codec
from app.persistence.migrate import migrate
from app.persistence.store import StoreError, NotFoundError, VersionConflictError

# Run-owned immutable collections are separate authoritative rows, not event projections.
COLLECTIONS = {'agent_snapshots': ('agents', lambda x: x.agent_id + ':' + x.config_digest),
               'invocation_records': ('invocations', lambda x: x.id),
               'attempts': ('attempts', lambda x: x.id),
               'submissions': ('submissions', lambda x: x.id),
               'reviews': ('reviews', lambda x: x.result.review_id),
               'call_records': ('llm_calls', lambda x: x.call_id),
               'command_results': ('command_results', lambda x: x.id)}


class SQLiteStateStore(StateOperations):
    def __init__(self, path, *, artifact_root=None):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.codec = Codec(artifact_root or self.path.with_suffix(self.path.suffix + '.artifacts'))
        self.connection = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self.connection.execute('PRAGMA foreign_keys=ON')
        self.connection.execute('PRAGMA busy_timeout=5000')
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.execute('PRAGMA synchronous=FULL')
        try:
            migrate(self.connection)
            self._startup_pending = set(self.list_run_refs())
        except Exception:
            self.connection.close()
            raise

    def event_cursor(self, project_id):
        with self._lock:
            self._value('projects', 'id=?', (project_id,))
            return self.connection.execute('SELECT COALESCE(MAX(sequence),0) FROM events WHERE project_id=?',
                                           (project_id,)).fetchone()[0]

    def valid_cursor(self, project_id, cursor):
        with self._lock:
            return cursor == 0 or self.connection.execute(
                'SELECT 1 FROM events WHERE project_id=? AND sequence=?', (project_id, cursor)).fetchone() is not None

    def event_page(self, project_id, cursor, limit=100):
        with self._lock:
            self._value('projects', 'id=?', (project_id,))
            return tuple(self.codec.loads(row[1]).with_sequence(row[0]) for row in self.connection.execute(
                'SELECT sequence,data FROM events WHERE project_id=? AND sequence>? ORDER BY sequence LIMIT ?',
                (project_id, cursor, limit)))

    def _command_get(self, scope, key):
        import json
        row = self.connection.execute(
            'SELECT fingerprint,receipt FROM api_commands WHERE scope=? AND key=?', (scope, key)).fetchone()
        return None if row is None else (row[0], None if row[1] is None else json.loads(row[1]))

    def _command_put(self, scope, key, fingerprint, receipt):
        import json
        self.connection.execute(
            'INSERT INTO api_commands VALUES (?,?,?,?) ON CONFLICT(scope,key) DO UPDATE SET receipt=excluded.receipt',
            (scope, key, fingerprint, None if receipt is None else json.dumps(receipt)))

    def close(self):
        with self._lock:
            self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @property
    def _projects(self):
        return {row[0]: self._project(row[0]) for row in self.connection.execute('SELECT id FROM projects')}

    def _value(self, table, where, params):
        row = self.connection.execute(f'SELECT data FROM {table} WHERE {where}', params).fetchone()
        if row is None:
            raise NotFoundError(f'{table} record not found')
        return self.codec.loads(row[0])

    def _project(self, project_id):
        body = self._value('projects', 'id=?', (project_id,))
        project = body['state']
        tasks = tuple(self._value('tasks', 'project_id=? AND id=?', (project_id, i)) for i in body['tasks'])
        decisions = tuple(self._value('decisions', 'project_id=? AND id=?', (project_id, i)) for i in body['decisions'])
        runs = []
        for identity in body['runs']:
            data = self._value('runs', 'project_id=? AND id=?', (project_id, identity))
            run = data['state']
            if run.workflow:
                collections = {field: tuple(self._value(table, 'project_id=? AND run_id=? AND id=?',
                    (project_id, identity, i)) for i in data[field]) for field, (table, _) in COLLECTIONS.items()}
                run = replace(run, workflow=replace(run.workflow, **collections))
            runs.append(run)
        return replace(project, tasks=tasks, decisions=decisions, runs=tuple(runs), active_run_id=next((r.id for r in runs if r.active), None))

    def _prepare(self, project):
        rows = []
        def add(table, keys, value, **columns):
            data = self.codec.dumps(value)
            if table in {'agents', 'invocations', 'attempts', 'submissions', 'reviews', 'llm_calls', 'command_results', 'decisions'}:
                where = ' AND '.join(k + '=?' for k in keys)
                existing = self.connection.execute(f'SELECT data FROM {table} WHERE {where}', tuple(keys.values())).fetchone()
                # Defaults added to value contracts may change their JSON encoding.
                # Keep the original immutable bytes when the domain value is equal.
                # Artifact decoding happens here, before the SQL transaction.
                if existing and self.codec.loads(existing[0]) == value:
                    data = existing[0]
            rows.append((table, {**keys, **columns, 'data': data}))
        pid = project.id
        # Strip children without constructing an invalid ProjectState with an active run.
        skeleton = replace(project, tasks=(), runs=(), decisions=(), active_run_id=None)
        add('projects', {'id': pid}, {'state': skeleton, 'tasks': tuple(t.id for t in project.tasks),
            'runs': tuple(r.id for r in project.runs), 'decisions': tuple(d.id for d in project.decisions)}, version=project.version)
        for task in project.tasks:
            add('tasks', {'project_id': pid, 'id': task.id}, task)
        for decision in project.decisions:
            add('decisions', {'project_id': pid, 'id': decision.id}, decision)
        for run in project.runs:
            if run.project_id != pid:
                raise StoreError('run project mismatch')
            if any(key.lower() in {'secret', 'api_key', 'password', 'credentials', 'authorization', 'access_token', 'refresh_token'}
                   or key.lower().endswith(('_api_key', '_password', '_secret')) for key, _ in run.config_snapshot):
                raise StoreError('credentials are not configuration snapshots')
            wf = run.workflow
            body = {'state': replace(run, workflow=replace(wf, **{f: () for f in COLLECTIONS}) if wf else None)}
            if wf:
                body.update({f: tuple(key(v) for v in getattr(wf, f)) for f, (_, key) in COLLECTIONS.items()})
                if any(len(ids) != len(set(ids)) for f, ids in body.items() if f != 'state'):
                    raise StoreError('duplicate record identifier')
            add('runs', {'project_id': pid, 'id': run.id}, body, active=int(run.active))
            if not wf:
                continue
            agents = {i.id: i.agent_id for i in wf.invocation_records}
            for field, (table, key) in COLLECTIONS.items():
                for value in getattr(wf, field):
                    columns = {}
                    if table == 'invocations':
                        columns['snapshot_id'] = value.agent_id + ':' + value.config_digest
                    elif table == 'attempts':
                        if value.run_id != run.id:
                            raise StoreError('attempt run mismatch')
                        columns.update(task_id=value.task_id, number=value.number)
                    elif table == 'submissions':
                        attempt = next((a for a in wf.attempts if a.id == value.attempt_id), None)
                        if attempt is None or attempt.task_id != value.task_id:
                            raise StoreError('submission attempt mismatch')
                        columns['attempt_id'] = value.attempt_id
                    elif table == 'reviews':
                        submission = next((s for s in wf.submissions if s.id == value.submission_id), None)
                        if submission is None or submission.task_id != value.task_id:
                            raise StoreError('review submission mismatch')
                        columns.update(submission_id=value.submission_id, task_id=value.task_id, number=value.number)
                    elif table == 'llm_calls':
                        if value.invocation_id not in agents:
                            raise StoreError('call invocation missing')
                        columns.update(invocation_id=value.invocation_id, agent_id=agents[value.invocation_id],
                            provider=value.provider_name, model=value.model, provider_request_id=value.provider_request_id,
                            attempt=value.attempt, purpose=value.purpose, status=value.status,
                            input_tokens=value.usage.input_tokens if value.usage else None,
                            cached_tokens=value.usage.cached_input_tokens if value.usage else None,
                            uncached_tokens=value.usage.uncached_input_tokens if value.usage else None,
                            output_tokens=value.usage.output_tokens if value.usage else None,
                            total_tokens=value.usage.total_tokens if value.usage else None,
                            usage_provenance=value.usage_provenance.value, usage_completeness=value.usage_completeness.value,
                            price_snapshot=json.dumps(value.price_snapshot.to_dict()) if value.price_snapshot else None,
                            estimated_cost=str(value.estimated_cost.amount) if value.estimated_cost else None,
                            error_type=value.error_type, error_message=value.error_message)
                    add(table, {'project_id': pid, 'run_id': run.id, 'id': key(value)}, value, **columns)
        return rows

    def _put(self, table, row, *, immutable=False):
        keys = [k for k in ('project_id', 'run_id', 'id') if k in row]
        where = ' AND '.join(k + '=?' for k in keys)
        existing = self.connection.execute(f'SELECT data FROM {table} WHERE {where}', tuple(row[k] for k in keys)).fetchone()
        if existing:
            if immutable:
                if existing[0] != row['data']:
                    raise StoreError('immutable record changed: ' + table)
                return
            columns = [k for k in row if k not in keys]
            self.connection.execute(f'UPDATE {table} SET ' + ','.join(k + '=?' for k in columns) + ' WHERE ' + where,
                tuple(row[k] for k in columns + keys))
        else:
            self.connection.execute(f'INSERT INTO {table} (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', tuple(row.values()))

    def _event(self, event, data):
        self.connection.execute('INSERT INTO events(event_id,project_id,run_id,task_id,type,actor,schema_version,payload,timestamp,data) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (event.event_id, event.project_id, event.run_id, event.task_id, event.type,
             json.dumps(event.actor.to_dict()), event.schema_version, json.dumps(dict(event.payload)), event.occurred_at, data))

    def _artifacts(self, data):
        def visit(value):
            if isinstance(value, dict):
                if '$artifact' in value:
                    self.connection.execute('INSERT OR IGNORE INTO artifacts VALUES (?,?,?)',
                        (value['$artifact'], value['$artifact'], value['size']))
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(json.loads(data))

    def _persist(self, before, after, events):
        # All serialization, validation and sidecar IO precedes the SQL transaction.
        rows = self._prepare(after)
        encoded_events = [(e, self.codec.dumps(e)) for e in events]
        try:
            self.connection.execute('BEGIN IMMEDIATE')
            current = self.connection.execute('SELECT version FROM projects WHERE id=?', (after.id,)).fetchone()
            if before is None and current:
                raise StoreError('project already exists')
            if before is not None and (current is None or current[0] != before.version):
                raise VersionConflictError('project version changed')
            # Parent rows before FK children; relations before attempts.
            for table, row in rows:
                if table in {'projects', 'tasks', 'decisions', 'runs'}:
                    self._put(table, row, immutable=table == 'decisions')
            self.connection.execute('DELETE FROM dependencies WHERE project_id=?', (after.id,))
            for task in after.tasks:
                for dep in task.dependencies:
                    self.connection.execute('INSERT INTO dependencies VALUES (?,?,?)', (after.id, task.id, dep))
            for run in after.runs:
                for task_id in run.task_ids:
                    self.connection.execute('INSERT OR IGNORE INTO run_tasks VALUES (?,?,?)', (after.id, run.id, task_id))
            for table, row in rows:
                if table not in {'projects', 'tasks', 'decisions', 'runs'}:
                    self._put(table, row, immutable=True)
                self._artifacts(row['data'])
            for run in after.runs:
                if run.workflow:
                    for sub in run.workflow.submissions:
                        if sub.files:
                            for file in sub.files.files:
                                self.connection.execute('INSERT OR IGNORE INTO artifact_metadata VALUES (?,?,?,?,?,?)',
                                    (after.id, run.id, sub.id, file.path, file.content_hash, file.before_hash))
            for event, data in encoded_events:
                self._event(event, data)
            self.connection.commit()
        except sqlite3.IntegrityError as exc:
            self.connection.rollback()
            raise StoreError('SQLite constraint violation: ' + str(exc)) from exc
        except Exception:
            self.connection.rollback()
            raise

    def create_project(self, project):
        with self._lock:
            self._persist(None, project, [DomainEvent(project.id, 'project.created', {'project_version': project.version})])
            return project

    def _commit(self, before, after, events):
        self._validate_commit(before, after, events)
        self._persist(before, after, events)

    def events(self, project_id, *, after_sequence=0):
        if after_sequence < 0:
            raise ValueError('after_sequence must be non-negative')
        with self._lock:
            if not self.connection.execute('SELECT 1 FROM projects WHERE id=?', (project_id,)).fetchone():
                raise NotFoundError('project not found')
            return tuple(self.codec.loads(data).with_sequence(sequence) for sequence, data in
                self.connection.execute('SELECT sequence,data FROM events WHERE project_id=? AND sequence>? ORDER BY sequence', (project_id, after_sequence)))

    def record_tool(self, project_id, run_id, record, *, approval=None):
        with self._lock:
            data = self.codec.dumps(record)
            approval_data = self.codec.dumps(approval) if approval else None
            event = DomainEvent(project_id, 'tool.audit', {'record_id': record.id, 'outcome': record.outcome}, run_id=run_id)
            encoded_event = self.codec.dumps(event)
            try:
                self.connection.execute('BEGIN IMMEDIATE')
                existing = self.connection.execute('SELECT data FROM tool_records WHERE project_id=? AND run_id=? AND id=?',
                    (project_id, run_id, record.id)).fetchone()
                if existing:
                    if existing[0] != data:
                        raise StoreError('conflicting tool record')
                    self.connection.rollback()
                    return
                self._put('tool_records', dict(project_id=project_id, run_id=run_id, id=record.id, data=data), immutable=True)
                if approval:
                    self._put('interventions', dict(project_id=project_id, run_id=run_id, id=approval.id, data=approval_data))
                self._event(event, encoded_event)
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise


    def list_run_refs(self):
        with self._lock:
            return tuple(self.connection.execute('SELECT project_id,id FROM runs ORDER BY rowid'))

    @property
    def _operations(self):
        return {(p, r, i): self._read_operation(data, metadata_only=True) for p, r, i, data in
                self.connection.execute('SELECT project_id,run_id,id,data FROM execution_operations')}

    def get_run_metadata(self, project_id, run_id):
        with self._lock:
            return self._value('runs', 'project_id=? AND id=?', (project_id, run_id))['state']

    def update_recovery(self, project_id, run_id, change):
        # Metadata-only path permits recording an integrity block without loading
        # damaged external evidence or rewriting any immutable child row.
        with self._lock:
            body = self._value('runs', 'project_id=? AND id=?', (project_id, run_id))
            before = body['state']
            after, events = change(before)
            if after.id != before.id or after.project_id != before.project_id or not events:
                raise StoreError('invalid recovery mutation')
            after = replace(after, version=before.version + 1)
            body['state'] = after
            project_body = self._value('projects', 'id=?', (project_id,))
            project_body['state'] = replace(project_body['state'], version=project_body['state'].version + 1)
            run_data, project_data = self.codec.dumps(body), self.codec.dumps(project_body)
            encoded_events = [(e, self.codec.dumps(e)) for e in events]
            try:
                self.connection.execute('BEGIN IMMEDIATE')
                self.connection.execute('UPDATE runs SET active=?,data=? WHERE project_id=? AND id=?',
                    (int(after.active), run_data, project_id, run_id))
                self.connection.execute('UPDATE projects SET version=?,data=? WHERE id=?',
                    (project_body['state'].version, project_data, project_id))
                for event, data in encoded_events:
                    self._event(event, data)
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise
            return after

    def _read_operation(self, data, *, metadata_only=False):
        if metadata_only:
            raw = json.loads(data)
            for key in ('change', 'proposal', 'result'):
                raw['fields'][key] = None
            return self.codec.decode(raw)
        return self.codec.loads(data)

    def operations(self, project_id, run_id, *, metadata_only=False):
        with self._lock:
            return tuple(self._read_operation(data, metadata_only=metadata_only) for data, in self.connection.execute(
                'SELECT data FROM execution_operations WHERE project_id=? AND run_id=? ORDER BY rowid', (project_id, run_id)))

    def approvals(self, project_id, run_id):
        with self._lock:
            return tuple(self.codec.loads(data) for data, in self.connection.execute(
                'SELECT data FROM interventions WHERE project_id=? AND run_id=? ORDER BY rowid', (project_id, run_id)))

    def recent_run_events(self, project_id, run_id, limit=50):
        with self._lock:
            self.get_run_metadata(project_id, run_id)
            rows = self.connection.execute('SELECT sequence,data FROM events WHERE project_id=? AND run_id=? ORDER BY sequence DESC LIMIT ?',
                (project_id, run_id, max(1, min(limit, 100)))).fetchall()
            return tuple(self.codec.loads(data).with_sequence(sequence) for sequence, data in reversed(rows))

    def tool_history(self, project_id, run_id):
        with self._lock:
            return tuple(self.codec.loads(data) for data, in self.connection.execute(
                'SELECT data FROM tool_records WHERE project_id=? AND run_id=? ORDER BY rowid', (project_id, run_id)))

    def record_operation(self, operation):
        with self._lock:
            cp = operation.checkpoint
            existing = self.connection.execute('SELECT data FROM execution_operations WHERE project_id=? AND run_id=? AND id=?',
                (cp.project_id, cp.run_id, operation.id)).fetchone()
            before = self.codec.loads(existing[0]) if existing else None
            if before == operation:
                return
            self._validate_operation(before, operation)
            data = self.codec.dumps(operation)
            event = DomainEvent(cp.project_id, 'execution.operation_recorded', self._operation_payload(operation), run_id=cp.run_id)
            encoded_event = self.codec.dumps(event)
            try:
                self.connection.execute('BEGIN IMMEDIATE')
                self._put('execution_operations', dict(project_id=cp.project_id, run_id=cp.run_id, id=operation.id,
                    kind=operation.kind, stage=operation.stage.value, certainty=operation.certainty.value, data=data))
                self._artifacts(data)
                self._event(event, encoded_event)
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

    def usage(self, project_id, run_id=None):
        from app.usage.aggregation import aggregate
        with self._lock:
            if not self.connection.execute('SELECT 1 FROM projects WHERE id=?', (project_id,)).fetchone():
                raise NotFoundError('project not found')
            if run_id is not None and not self.connection.execute('SELECT 1 FROM runs WHERE project_id=? AND id=?', (project_id, run_id)).fetchone():
                raise NotFoundError('run not found')
            where, params = 'project_id=?', (project_id,)
            if run_id is not None:
                where += ' AND run_id=?'
                params += (run_id,)
            records = [(agent, self.codec.loads(data)) for agent, data in self.connection.execute(
                'SELECT agent_id,data FROM llm_calls WHERE ' + where + ' ORDER BY rowid', params)]
            reviews = self.connection.execute('SELECT count(*) FROM reviews WHERE ' + where, params).fetchone()[0]
            from app.usage.aggregation import effective_records
            ops = [op for (p, r, _), op in self._operations.items() if p == project_id and (run_id is None or r == run_id)]
            runs = [self.get_run_metadata(project_id, r) for p, r in self.list_run_refs() if p == project_id]
            return aggregate(effective_records(records, ops, runs), reviews=reviews)
