"""Small, dependency-free SQLite migration runner.

Migration files are immutable and named NNN_description.sql. The runner records the
SHA-256 digest of each applied migration. A changed migration that has already been
applied is treated as a fatal configuration error rather than silently accepted.
"""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path
    sha256: str
    sql: str


def _load_migrations(directory: str | Path) -> list[Migration]:
    root = Path(directory)
    if not root.is_dir():
        raise MigrationError(f"Migration directory does not exist: {root}")

    migrations: list[Migration] = []
    for path in sorted(root.glob("[0-9][0-9][0-9]_*.sql")):
        prefix = path.name.split("_", 1)[0]
        try:
            version = int(prefix)
        except ValueError as exc:
            raise MigrationError(f"Invalid migration filename: {path.name}") from exc
        sql = path.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                version=version,
                name=path.name,
                path=path,
                sha256=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
                sql=sql,
            )
        )

    if not migrations:
        raise MigrationError(f"No migrations found in: {root}")
    versions = [m.version for m in migrations]
    if len(versions) != len(set(versions)):
        raise MigrationError("Duplicate migration versions detected")
    return migrations


def _ensure_history(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            sha256 TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        )
        """
    )
    conn.commit()


def apply_migrations(conn: sqlite3.Connection, directory: str | Path) -> list[str]:
    """Apply pending migrations and return the filenames that were applied."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    _ensure_history(conn)
    applied_rows = conn.execute(
        "SELECT version, name, sha256 FROM schema_migrations ORDER BY version"
    ).fetchall()
    applied = {int(row[0]): (str(row[1]), str(row[2])) for row in applied_rows}

    completed: list[str] = []
    for migration in _load_migrations(directory):
        previous = applied.get(migration.version)
        if previous:
            previous_name, previous_hash = previous
            if previous_name != migration.name or previous_hash != migration.sha256:
                raise MigrationError(
                    f"Applied migration {migration.version} was modified: "
                    f"database=({previous_name}, {previous_hash}) "
                    f"filesystem=({migration.name}, {migration.sha256})"
                )
            continue

        try:
            conn.execute("BEGIN IMMEDIATE")
            # executescript commits implicitly in sqlite3, so execute statements safely.
            statements = [s.strip() for s in migration.sql.split(";") if s.strip()]
            for statement in statements:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations(version, name, sha256) VALUES(?,?,?)",
                (migration.version, migration.name, migration.sha256),
            )
            conn.commit()
            completed.append(migration.name)
        except Exception as exc:
            conn.rollback()
            raise MigrationError(f"Failed migration {migration.name}: {exc}") from exc
    return completed


def migrate_database(db_path: str | Path, directory: str | Path) -> list[str]:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        return apply_migrations(conn, directory)
