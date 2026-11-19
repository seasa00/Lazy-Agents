"""Small ordered, checksummed, transactional project-local migrations."""
from hashlib import sha256
from pathlib import Path
import sqlite3
from app.persistence.store import StoreError

MIGRATIONS = Path(__file__).with_name('migrations')


def migrate(connection, directory=MIGRATIONS):
    files = sorted(Path(directory).glob('[0-9][0-9][0-9]_*.sql'))
    versions = [int(p.name.split('_')[0]) for p in files]
    if versions != list(range(1, len(files) + 1)):
        raise StoreError('invalid migration sequence')
    try:
        connection.execute('BEGIN IMMEDIATE')
        connection.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, checksum TEXT NOT NULL)')
        applied = connection.execute('SELECT version,checksum FROM schema_migrations ORDER BY version').fetchall()
        if [r[0] for r in applied] != list(range(1, len(applied) + 1)) or len(applied) > len(files):
            raise StoreError('invalid or newer migration state')
        for version, path in zip(versions, files):
            script = path.read_text()
            digest = sha256(script.encode()).hexdigest()
            if version <= len(applied):
                if applied[version - 1][1] != digest:
                    raise StoreError('migration checksum mismatch')
                continue
            statement = ''
            for line in script.splitlines(keepends=True):
                statement += line
                if sqlite3.complete_statement(statement):
                    connection.execute(statement)
                    statement = ''
            if statement.strip():
                raise StoreError('incomplete migration SQL')
            connection.execute('INSERT INTO schema_migrations VALUES (?,?)', (version, digest))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
