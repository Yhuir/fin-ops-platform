from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from typing import Any, Iterator
from urllib.parse import ParseResult, urlparse, urlunparse


class PostgresConfigurationError(RuntimeError):
    """Raised when PostgreSQL mode is requested without a usable configuration."""


@dataclass(frozen=True)
class PostgresSettings:
    database_url: str
    connect_timeout_seconds: int = 5
    statement_timeout_ms: int = 10_000

    @classmethod
    def from_env(cls) -> PostgresSettings:
        database_url = (os.environ.get("FIN_OPS_POSTGRES_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
        if not database_url:
            raise PostgresConfigurationError(
                "FIN_OPS_APP_STORAGE_BACKEND=postgres requires FIN_OPS_POSTGRES_DATABASE_URL or DATABASE_URL."
            )
        return cls(
            database_url=database_url,
            connect_timeout_seconds=_positive_int_from_env("FIN_OPS_POSTGRES_CONNECT_TIMEOUT_SECONDS", 5),
            statement_timeout_ms=_positive_int_from_env("FIN_OPS_POSTGRES_STATEMENT_TIMEOUT_MS", 10_000),
        )

    @property
    def redacted_database_url(self) -> str:
        return redact_database_url(self.database_url)


def _positive_int_from_env(name: str, default: int) -> int:
    raw_value = (os.environ.get(name) or "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise PostgresConfigurationError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise PostgresConfigurationError(f"{name} must be positive.")
    return value


def redact_database_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    if not parsed.scheme or not parsed.netloc:
        return "<invalid-postgres-url>"
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port is not None else ""
    username = parsed.username or ""
    credentials = f"{username}:***@" if username else ""
    redacted = ParseResult(
        scheme=parsed.scheme,
        netloc=f"{credentials}{host}{port}",
        path=parsed.path,
        params="",
        query="",
        fragment="",
    )
    return urlunparse(redacted)


class PostgresConnection:
    def __init__(self, settings: PostgresSettings) -> None:
        self.settings = settings

    @contextmanager
    def connection(self) -> Iterator[Any]:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - exercised when dependency is missing in deployment.
            raise PostgresConfigurationError("PostgreSQL mode requires the psycopg package.") from exc

        with psycopg.connect(
            self.settings.database_url,
            connect_timeout=self.settings.connect_timeout_seconds,
            row_factory=dict_row,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select set_config('statement_timeout', %s, true)", (str(self.settings.statement_timeout_ms),))
            yield connection

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                row = cursor.fetchone()
                return dict(row) if row is not None else None

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return int(cursor.rowcount or 0)

    @contextmanager
    def transaction(self) -> Iterator[PostgresTransaction]:
        with self.connection() as connection:
            with connection.transaction():
                yield PostgresTransaction(connection)

    def health_summary(self) -> dict[str, object]:
        row = self.fetch_one(
            """
            select
              current_database() as database,
              current_user as user,
              coalesce(max(version), '0000') as schema_version
            from public.schema_migrations
            """,
        )
        schema_version = row.get("schema_version") if row else None
        if isinstance(schema_version, bytes):
            schema_version = schema_version.decode()
        try:
            parsed_schema_version = int(str(schema_version))
        except (TypeError, ValueError):
            parsed_schema_version = 0
        return {
            "postgres_status": "ready",
            "postgres_database": row.get("database") if row else None,
            "postgres_user": row.get("user") if row else None,
            "postgres_schema_version": parsed_schema_version,
        }


class PostgresTransaction:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return dict(row) if row is not None else None

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return int(cursor.rowcount or 0)

    def execute_many(self, sql: str, params_seq: list[tuple[Any, ...]]) -> int:
        with self._connection.cursor() as cursor:
            cursor.executemany(sql, params_seq)
            return int(cursor.rowcount or 0)
