from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from typing import TextIO
from urllib.parse import parse_qsl, quote, unquote, urlsplit, urlunsplit


MIGRATION_FILENAME_RE = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
ACCEPTED_CHECKSUM_DRIFTS_PATH = Path(__file__).resolve().parent / "accepted_checksum_drifts.json"
SCHEMA_MIGRATIONS_TABLE = "public.schema_migrations"


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    name: str
    path: Path
    checksum_sha256: str


@dataclass(frozen=True, slots=True)
class AppliedMigration:
    version: str
    name: str
    checksum_sha256: str


@dataclass(frozen=True, slots=True)
class AcceptedChecksumDrift:
    version: str
    name: str
    applied_checksum_sha256: str
    current_checksum_sha256: str
    accepted_at: str
    reason: str


def redact_database_url(database_url: str) -> str:
    parts = urlsplit(database_url)
    if not parts.scheme or not parts.netloc:
        return "<redacted-database-url>"
    username = unquote(parts.username or "")
    hostname = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    credentials = ""
    if username:
        credentials = f"{quote(username)}:***@"
    return urlunsplit((parts.scheme, f"{credentials}{hostname}{port}", parts.path, "", ""))


def checksum_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_migrations(migrations_dir: Path = MIGRATIONS_DIR) -> list[Migration]:
    migrations: list[Migration] = []
    seen_versions: set[str] = set()
    for path in sorted(migrations_dir.glob("*.sql")):
        match = MIGRATION_FILENAME_RE.match(path.name)
        if match is None:
            raise MigrationError(f"Invalid migration filename: {path.name}")
        version = match.group("version")
        if version in seen_versions:
            raise MigrationError(f"Duplicate migration version: {version}")
        seen_versions.add(version)
        migrations.append(
            Migration(
                version=version,
                name=match.group("name"),
                path=path,
                checksum_sha256=checksum_file(path),
            )
        )
    if not migrations:
        raise MigrationError(f"No migrations found in {migrations_dir}")
    return migrations


def database_url_from_env_or_arg(database_url: str | None) -> str:
    resolved = (
        database_url
        or os.getenv("DATABASE_URL")
        or os.getenv("FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL")
        or os.getenv("FIN_OPS_POSTGRES_DATABASE_URL")
    )
    if not resolved:
        raise MigrationError(
            "PostgreSQL connection is required. Set DATABASE_URL, "
            "FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL, FIN_OPS_POSTGRES_DATABASE_URL, "
            "or pass --database-url."
        )
    return resolved


def load_accepted_checksum_drifts(path: Path = ACCEPTED_CHECKSUM_DRIFTS_PATH) -> dict[str, AcceptedChecksumDrift]:
    if not path.exists():
        return {}
    try:
        raw_entries = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MigrationError(f"Invalid accepted checksum drift registry: {path}") from exc
    if not isinstance(raw_entries, list):
        raise MigrationError(f"Accepted checksum drift registry must be a list: {path}")
    entries: dict[str, AcceptedChecksumDrift] = {}
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise MigrationError(f"Accepted checksum drift entry must be an object: {path}")
        entry = AcceptedChecksumDrift(
            version=str(raw.get("version") or ""),
            name=str(raw.get("name") or ""),
            applied_checksum_sha256=str(raw.get("applied_checksum_sha256") or ""),
            current_checksum_sha256=str(raw.get("current_checksum_sha256") or ""),
            accepted_at=str(raw.get("accepted_at") or ""),
            reason=str(raw.get("reason") or ""),
        )
        if not MIGRATION_FILENAME_RE.match(f"{entry.version}_{entry.name}.sql"):
            raise MigrationError(f"Invalid accepted checksum drift entry: {entry.version} {entry.name}")
        for value in (entry.applied_checksum_sha256, entry.current_checksum_sha256):
            if not re.fullmatch(r"[0-9a-f]{64}", value):
                raise MigrationError(f"Invalid checksum in accepted drift entry: {entry.version}")
        if not entry.accepted_at or not entry.reason:
            raise MigrationError(f"Accepted checksum drift entry requires accepted_at and reason: {entry.version}")
        if entry.version in entries:
            raise MigrationError(f"Duplicate accepted checksum drift entry: {entry.version}")
        entries[entry.version] = entry
    return entries


def is_accepted_checksum_drift(migration: Migration, applied: AppliedMigration, accepted: dict[str, AcceptedChecksumDrift]) -> bool:
    entry = accepted.get(migration.version)
    return (
        entry is not None
        and entry.name == migration.name
        and entry.applied_checksum_sha256 == applied.checksum_sha256
        and entry.current_checksum_sha256 == migration.checksum_sha256
    )


def _psql_path() -> str:
    path = shutil.which("psql")
    if path is None:
        raise MigrationError("psql is not available on PATH.")
    return path


def _psql_env(database_url: str) -> dict[str, str]:
    parts = urlsplit(database_url)
    if parts.scheme not in {"postgres", "postgresql"}:
        raise MigrationError("DATABASE_URL must use postgres:// or postgresql://.")
    if not parts.hostname or not parts.path.strip("/"):
        raise MigrationError("DATABASE_URL must include host and database name.")
    env = os.environ.copy()
    env["PGHOST"] = unquote(parts.hostname)
    env["PGDATABASE"] = unquote(parts.path.lstrip("/"))
    if parts.port:
        env["PGPORT"] = str(parts.port)
    if parts.username:
        env["PGUSER"] = unquote(parts.username)
    if parts.password:
        env["PGPASSWORD"] = unquote(parts.password)
    for key, value in parse_qsl(parts.query, keep_blank_values=False):
        if key.lower() == "sslmode":
            env["PGSSLMODE"] = value
    return env


def run_psql(database_url: str, *, sql: str) -> str:
    command = [
        _psql_path(),
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "-At",
        "-q",
    ]
    result = subprocess.run(
        command,
        input=sql,
        text=True,
        capture_output=True,
        check=False,
        env=_psql_env(database_url),
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "psql failed").strip()
        raise MigrationError(message)
    return result.stdout.strip()


def assert_safe_target(database_url: str) -> None:
    rows = run_psql(
        database_url,
        sql="""
select current_database() || E'\t' || current_user || E'\t' ||
       coalesce(current_setting('server_version', true), '');
""",
    )
    database_name, _, _ = rows.split("\t", 2)
    if database_name == "fin_ops":
        return
    allow_test_db = os.getenv("FIN_OPS_ALLOW_POSTGRES_TEST_DB") == "1"
    if allow_test_db and "test" in database_name:
        return
    raise MigrationError(
        "Refusing to apply migrations outside database fin_ops. "
        "Set FIN_OPS_ALLOW_POSTGRES_TEST_DB=1 only for disposable test databases."
    )


def fetch_applied_migrations(database_url: str) -> dict[str, AppliedMigration]:
    exists_sql = "select case when to_regclass('public.schema_migrations') is null then '' else 'exists' end;"
    if run_psql(database_url, sql=exists_sql) != "exists":
        return {}
    rows_sql = """
select version || E'\t' || name || E'\t' || checksum_sha256
from public.schema_migrations
order by version;
"""
    rows = run_psql(database_url, sql=rows_sql)
    applied: dict[str, AppliedMigration] = {}
    for row in rows.splitlines():
        if not row:
            continue
        version, name, checksum_sha256 = row.split("\t", 2)
        applied[version] = AppliedMigration(version, name, checksum_sha256)
    return applied


def format_plan(migrations: Sequence[Migration], applied: dict[str, AppliedMigration] | None = None) -> list[str]:
    lines: list[str] = []
    applied = applied or {}
    accepted = load_accepted_checksum_drifts()
    for migration in migrations:
        state = "pending"
        if migration.version in applied:
            applied_migration = applied[migration.version]
            if applied_migration.checksum_sha256 == migration.checksum_sha256:
                state = "applied"
            elif is_accepted_checksum_drift(migration, applied_migration, accepted):
                state = "accepted-checksum-drift"
            else:
                state = "checksum-mismatch"
        lines.append(f"{migration.version} {state} {migration.name} {migration.checksum_sha256}")
    return lines


def build_apply_sql(migration: Migration, execution_ms: int) -> str:
    body = migration.path.read_text(encoding="utf-8")
    escaped_name = migration.name.replace("'", "''")
    escaped_checksum = migration.checksum_sha256.replace("'", "''")
    return f"""
begin;
select pg_advisory_xact_lock(hashtext('fin_ops_platform_postgres_migrate'));
{body}
insert into public.schema_migrations(version, name, checksum_sha256, applied_at, execution_ms)
values ('{migration.version}', '{escaped_name}', '{escaped_checksum}', now(), {execution_ms});
commit;
"""


def ensure_metadata_table(database_url: str) -> None:
    exists_sql = "select case when to_regclass('public.schema_migrations') is null then '' else 'exists' end;"
    if run_psql(database_url, sql=exists_sql) == "exists":
        return
    run_psql(
        database_url,
        sql="""
create table if not exists public.schema_migrations (
    version text primary key,
    name text not null,
    checksum_sha256 text not null,
    applied_at timestamptz not null default now(),
    execution_ms integer not null,
    metadata jsonb not null default '{}'::jsonb
);
""",
    )


def apply_migrations(database_url: str, migrations: Sequence[Migration], stdout: TextIO) -> None:
    assert_safe_target(database_url)
    ensure_metadata_table(database_url)
    applied = fetch_applied_migrations(database_url)
    accepted = load_accepted_checksum_drifts()
    for migration in migrations:
        existing = applied.get(migration.version)
        if existing is not None:
            if existing.checksum_sha256 != migration.checksum_sha256:
                if is_accepted_checksum_drift(migration, existing, accepted):
                    print(f"{migration.version} skipped-accepted-checksum-drift {migration.name}", file=stdout)
                    continue
                raise MigrationError(
                    "Applied migration checksum mismatch: "
                    f"{migration.version} {migration.name} "
                    f"applied={existing.checksum_sha256} current={migration.checksum_sha256}"
                )
            print(f"{migration.version} skipped {migration.name}", file=stdout)
            continue
        start = time.perf_counter()
        run_psql(database_url, sql=build_apply_sql(migration, execution_ms=0))
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        run_psql(
            database_url,
            sql=(
                "update public.schema_migrations "
                f"set execution_ms = {elapsed_ms} "
                f"where version = '{migration.version}';"
            ),
        )
        print(f"{migration.version} applied {migration.name} {elapsed_ms}ms", file=stdout)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="fin-ops-platform PostgreSQL schema migration tool")
    parser.add_argument("command", choices=("plan", "status", "apply"))
    parser.add_argument("--database-url", help="PostgreSQL connection URI. Prefer DATABASE_URL in shell history.")
    parser.add_argument("--migrations-dir", type=Path, default=MIGRATIONS_DIR)
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO = sys.stdout, stderr: TextIO = sys.stderr) -> int:
    args = build_parser().parse_args(argv)
    try:
        migrations = discover_migrations(args.migrations_dir)
        if args.command == "plan":
            applied = None
            if args.database_url or os.getenv("DATABASE_URL"):
                applied = fetch_applied_migrations(database_url_from_env_or_arg(args.database_url))
            print("\n".join(format_plan(migrations, applied)), file=stdout)
            return 0

        database_url = database_url_from_env_or_arg(args.database_url)
        if args.command == "status":
            applied = fetch_applied_migrations(database_url)
            print("\n".join(format_plan(migrations, applied)), file=stdout)
            return 0

        apply_migrations(database_url, migrations, stdout)
        return 0
    except MigrationError as exc:
        print(f"ERROR: {exc}", file=stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
