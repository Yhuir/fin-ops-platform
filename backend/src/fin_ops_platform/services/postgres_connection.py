from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
import re
from threading import Lock
from time import monotonic
from typing import Any, Iterator
from urllib.parse import ParseResult, urlparse, urlunparse

from fin_ops_platform.services.api_performance_metrics import record_database_connection_acquire, record_database_query


class PostgresConfigurationError(RuntimeError):
    """Raised when PostgreSQL mode is requested without a usable configuration."""


@dataclass(frozen=True)
class PostgresSettings:
    database_url: str
    connect_timeout_seconds: int = 5
    statement_timeout_ms: int = 10_000
    pool_min_size: int = 1
    pool_max_size: int = 10
    pool_enabled: bool = True

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
            pool_min_size=_positive_int_from_env("FIN_OPS_POSTGRES_POOL_MIN_SIZE", 1),
            pool_max_size=_positive_int_from_env("FIN_OPS_POSTGRES_POOL_MAX_SIZE", 10),
            pool_enabled=(os.environ.get("FIN_OPS_POSTGRES_POOL_ENABLED") or "1").strip().lower()
            not in {"0", "false", "no", "off"},
        )

    @classmethod
    def from_read_env(cls) -> PostgresSettings | None:
        database_url = (os.environ.get("FIN_OPS_POSTGRES_READ_DATABASE_URL") or "").strip()
        if not database_url:
            return None
        default_connect_timeout_seconds = _positive_int_from_env("FIN_OPS_POSTGRES_CONNECT_TIMEOUT_SECONDS", 5)
        default_statement_timeout_ms = _positive_int_from_env("FIN_OPS_POSTGRES_STATEMENT_TIMEOUT_MS", 10_000)
        default_pool_min_size = _positive_int_from_env("FIN_OPS_POSTGRES_POOL_MIN_SIZE", 1)
        default_pool_max_size = _positive_int_from_env("FIN_OPS_POSTGRES_POOL_MAX_SIZE", 10)
        return cls(
            database_url=database_url,
            connect_timeout_seconds=_positive_int_from_env(
                "FIN_OPS_POSTGRES_READ_CONNECT_TIMEOUT_SECONDS",
                default_connect_timeout_seconds,
            ),
            statement_timeout_ms=_positive_int_from_env(
                "FIN_OPS_POSTGRES_READ_STATEMENT_TIMEOUT_MS",
                default_statement_timeout_ms,
            ),
            pool_min_size=_positive_int_from_env("FIN_OPS_POSTGRES_READ_POOL_MIN_SIZE", default_pool_min_size),
            pool_max_size=_positive_int_from_env("FIN_OPS_POSTGRES_READ_POOL_MAX_SIZE", default_pool_max_size),
            pool_enabled=(os.environ.get("FIN_OPS_POSTGRES_READ_POOL_ENABLED") or os.environ.get("FIN_OPS_POSTGRES_POOL_ENABLED") or "1")
            .strip()
            .lower()
            not in {"0", "false", "no", "off"},
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
        self._statement_timeout_ms_override: int | None = None
        self._pool: Any | None = None
        self._pool_lock = Lock()

    def set_statement_timeout_ms(self, value: int | None) -> None:
        if value is not None and value <= 0:
            raise ValueError("statement timeout must be positive when provided.")
        self._statement_timeout_ms_override = value

    def warm_up(self) -> None:
        if not self.settings.pool_enabled:
            with self.connection():
                return
        pool = self._connection_pool()
        wait = getattr(pool, "wait", None)
        if callable(wait):
            wait(timeout=self.settings.connect_timeout_seconds)
            return
        with self.connection():
            return

    @contextmanager
    def connection(self) -> Iterator[Any]:
        started_at = monotonic()
        with self._pooled_or_direct_connection() as connection:
            record_database_connection_acquire((monotonic() - started_at) * 1000)
            self._prepare_connection(connection)
            yield connection

    def _connection_pool(self) -> Any:
        with self._pool_lock:
            if self._pool is None:
                try:
                    from psycopg.rows import dict_row
                    from psycopg_pool import ConnectionPool
                except ImportError as exc:  # pragma: no cover - exercised when dependency is missing in deployment.
                    raise PostgresConfigurationError("PostgreSQL pooling requires psycopg_pool.") from exc
                self._pool = ConnectionPool(
                    conninfo=self.settings.database_url,
                    min_size=self.settings.pool_min_size,
                    max_size=max(self.settings.pool_max_size, self.settings.pool_min_size),
                    kwargs={
                        "connect_timeout": self.settings.connect_timeout_seconds,
                        "row_factory": dict_row,
                    },
                    open=True,
                )
            return self._pool

    @contextmanager
    def _direct_connection(self) -> Iterator[Any]:
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
            yield connection

    @contextmanager
    def _pooled_or_direct_connection(self) -> Iterator[Any]:
        if not self.settings.pool_enabled:
            with self._direct_connection() as connection:
                yield connection
            return
        try:
            pool = self._connection_pool()
        except PostgresConfigurationError:
            with self._direct_connection() as connection:
                yield connection
            return
        with pool.connection() as connection:
            yield connection

    def _prepare_connection(self, connection: Any) -> None:
        connection.autocommit = True
        with connection.cursor() as cursor:
            timeout_ms = self._statement_timeout_ms_override or self.settings.statement_timeout_ms
            cursor.execute("select set_config('statement_timeout', %s, false)", (str(timeout_ms),))
        connection.autocommit = False

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                started_at = monotonic()
                try:
                    cursor.execute(sql, params)
                    row = cursor.fetchone()
                finally:
                    record_database_query((monotonic() - started_at) * 1000)
                return dict(row) if row is not None else None

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                started_at = monotonic()
                try:
                    cursor.execute(sql, params)
                    rows = cursor.fetchall()
                finally:
                    record_database_query((monotonic() - started_at) * 1000)
                return [dict(row) for row in rows]

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                started_at = monotonic()
                try:
                    cursor.execute(sql, params)
                finally:
                    record_database_query((monotonic() - started_at) * 1000)
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
            started_at = monotonic()
            try:
                cursor.execute(sql, params)
                row = cursor.fetchone()
            finally:
                record_database_query((monotonic() - started_at) * 1000)
            return dict(row) if row is not None else None

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._connection.cursor() as cursor:
            started_at = monotonic()
            try:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
            finally:
                record_database_query((monotonic() - started_at) * 1000)
            return [dict(row) for row in rows]

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self._connection.cursor() as cursor:
            started_at = monotonic()
            try:
                cursor.execute(sql, params)
            finally:
                record_database_query((monotonic() - started_at) * 1000)
            return int(cursor.rowcount or 0)

    def execute_many(self, sql: str, params_seq: list[tuple[Any, ...]]) -> int:
        with self._connection.cursor() as cursor:
            started_at = monotonic()
            try:
                cursor.executemany(sql, params_seq)
            finally:
                record_database_query((monotonic() - started_at) * 1000)
            return int(cursor.rowcount or 0)

    def execute_many_values(self, sql: str, params_seq: list[tuple[Any, ...]], *, chunk_size: int = 1000) -> int:
        rows = list(params_seq or [])
        if not rows:
            return 0
        parsed = _split_insert_values_sql(sql)
        if parsed is None:
            return self.execute_many(sql, rows)
        params_per_row = len(rows[0])
        if params_per_row <= 0 or any(len(row) != params_per_row for row in rows):
            return self.execute_many(sql, rows)
        prefix, row_sql, suffix = parsed
        max_rows_by_params = max(1, 60_000 // params_per_row)
        effective_chunk_size = max(1, min(chunk_size, max_rows_by_params))
        affected = 0
        with self._connection.cursor() as cursor:
            for start in range(0, len(rows), effective_chunk_size):
                chunk = rows[start : start + effective_chunk_size]
                chunk_sql = f"{prefix}{', '.join([row_sql] * len(chunk))}{suffix}"
                chunk_params = tuple(value for row in chunk for value in row)
                started_at = monotonic()
                try:
                    cursor.execute(chunk_sql, chunk_params)
                finally:
                    record_database_query((monotonic() - started_at) * 1000)
                affected += int(cursor.rowcount or 0)
        return affected


def _split_insert_values_sql(sql: str) -> tuple[str, str, str] | None:
    raw_sql = str(sql or "")
    match = re.search(r"\bvalues\b", raw_sql, flags=re.IGNORECASE)
    if match is None:
        return None
    open_index = match.end()
    while open_index < len(raw_sql) and raw_sql[open_index].isspace():
        open_index += 1
    if open_index >= len(raw_sql) or raw_sql[open_index] != "(":
        return None
    close_index = _matching_parenthesis_index(raw_sql, open_index)
    if close_index is None:
        return None
    prefix = raw_sql[:open_index]
    row_sql = raw_sql[open_index : close_index + 1]
    suffix = raw_sql[close_index + 1 :]
    return prefix, row_sql, suffix


def _matching_parenthesis_index(sql: str, open_index: int) -> int | None:
    depth = 0
    quote: str | None = None
    index = open_index
    while index < len(sql):
        char = sql[index]
        if quote is not None:
            if char == quote:
                if quote == "'" and index + 1 < len(sql) and sql[index + 1] == "'":
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None
