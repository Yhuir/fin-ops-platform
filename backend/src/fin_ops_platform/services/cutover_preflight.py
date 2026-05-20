from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import os
import re
from typing import Any, Protocol
from urllib.parse import ParseResult, urlparse, urlunparse

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings


DEFAULT_DATABASE_URL_ENV = "FIN_OPS_POSTGRES_DATABASE_URL"
SCHEMA_MIGRATIONS_TABLE = "public.schema_migrations"
CORE_COUNT_TABLES = (
    ("import_batches", "app.import_batches"),
    ("import_batch_rows", "app.import_batch_rows"),
    ("import_files", "app.import_files"),
    ("invoices", "app.invoices"),
    ("bank_transactions", "app.bank_transactions"),
    ("search_index_rows", "read_model.search_index_rows"),
)
FORBIDDEN_ACTIONS = ("cutover", "enable_dual_write", "restart_service", "production_write")
SECRET_KEY_PARTS = ("password", "passwd", "secret", "token", "credential", "database_url", "uri", "url")


class CutoverPreflightConfigurationError(RuntimeError):
    """Raised when cutover preflight cannot run with the provided read-only config."""


class ReadOnlyPostgresConnection(Protocol):
    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None: ...

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class CutoverPreflightConfig:
    database_url: str
    database_url_env: str = DEFAULT_DATABASE_URL_ENV
    app_storage_backend: str = "local_pickle"
    require_backup_confirmation: bool = False
    backup_confirmed: bool = False
    no_production_writes: bool = True

    @classmethod
    def from_env(
        cls,
        *,
        database_url_env: str = DEFAULT_DATABASE_URL_ENV,
        require_backup_confirmation: bool = False,
        no_production_writes: bool = True,
    ) -> CutoverPreflightConfig:
        database_url = (os.environ.get(database_url_env) or "").strip()
        if not database_url:
            raise CutoverPreflightConfigurationError(f"{database_url_env} is required for read-only cutover preflight.")
        if not no_production_writes:
            raise CutoverPreflightConfigurationError("Cutover preflight requires --no-production-writes.")
        return cls(
            database_url=database_url,
            database_url_env=database_url_env,
            app_storage_backend=(os.environ.get("FIN_OPS_APP_STORAGE_BACKEND") or "local_pickle").strip() or "local_pickle",
            require_backup_confirmation=require_backup_confirmation,
            backup_confirmed=_truthy(os.environ.get("FIN_OPS_CUTOVER_BACKUP_CONFIRMED")),
            no_production_writes=no_production_writes,
        )

    @property
    def redacted_database_url(self) -> str:
        return redact_uri(self.database_url)


class CutoverPreflightChecker:
    def __init__(self, *, config: CutoverPreflightConfig, connection: ReadOnlyPostgresConnection | None = None) -> None:
        self._config = config
        self._connection = connection or PostgresConnection(
            PostgresSettings(
                database_url=config.database_url,
                connect_timeout_seconds=_positive_int_from_env("FIN_OPS_POSTGRES_CONNECT_TIMEOUT_SECONDS", 5),
                statement_timeout_ms=_positive_int_from_env("FIN_OPS_POSTGRES_STATEMENT_TIMEOUT_MS", 10_000),
            )
        )

    def run(self) -> dict[str, Any]:
        postgres = self._postgres_summary()
        backup = self._backup_checklist()
        rollback = self._rollback_checklist()
        guards = self._guard_status()
        status = "pass" if backup["status"] != "blocked" and guards["no_production_writes"] == "enforced" else "blocked"
        return redact_secret_values(
            {
                "status": status,
                "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                "app_storage": self._app_storage_summary(),
                "postgres": postgres,
                "readiness": {
                    "status": status,
                    "storage_backend": self._config.app_storage_backend,
                    "postgres_connectivity": postgres["connectivity"],
                    "schema_version": postgres["schema_version"],
                },
                "backup_checklist": backup,
                "rollback_checklist": rollback,
                "guards": guards,
            }
        )

    def _app_storage_summary(self) -> dict[str, Any]:
        return {
            "backend": self._config.app_storage_backend,
            "database_url_env": self._config.database_url_env,
            "database_url": self._config.redacted_database_url,
        }

    def _postgres_summary(self) -> dict[str, Any]:
        health = self._connection.fetch_one(
            """
            select
              current_database() as database,
              current_user as "user",
              coalesce(max(version), '0000') as schema_version,
              to_regclass('public.schema_migrations') is not null as schema_migrations_exists
            from public.schema_migrations
            """,
        )
        if not health:
            raise CutoverPreflightConfigurationError("PostgreSQL read-only health query returned no rows.")
        locations = self._connection.fetch_all(
            """
            select table_schema, table_name
            from information_schema.tables
            where table_schema = %s and table_name = %s
            order by table_schema, table_name
            """,
            ("public", "schema_migrations"),
        )
        counts = self._fetch_core_counts()
        location = _schema_table_location(locations)
        return {
            "connectivity": "ready",
            "database": health.get("database"),
            "user": health.get("user"),
            "schema_version": str(health.get("schema_version") or "0000"),
            "schema_migrations_table": location,
            "schema_migrations_exists": bool(health.get("schema_migrations_exists")) and location == SCHEMA_MIGRATIONS_TABLE,
            "core_counts": counts,
            "database_url_env": self._config.database_url_env,
            "database_url": self._config.redacted_database_url,
        }

    def _fetch_core_counts(self) -> dict[str, int]:
        select_parts = [f"select '{label}' as table_name, count(*)::bigint as row_count from {table}" for label, table in CORE_COUNT_TABLES]
        rows = self._connection.fetch_all("\nunion all\n".join(select_parts))
        return {str(row["table_name"]): int(row["row_count"]) for row in rows}

    def _backup_checklist(self) -> dict[str, Any]:
        items = [
            {"item": "postgres_readonly_backup_verified", "status": "placeholder"},
            {"item": "app_mongo_backup_verified", "status": "placeholder"},
            {"item": "oa_mongo_not_touched", "status": "enforced"},
        ]
        if self._config.require_backup_confirmation and not self._config.backup_confirmed:
            return {"status": "blocked", "requires_confirmation": True, "items": items}
        return {
            "status": "confirmed" if self._config.backup_confirmed else "pending",
            "requires_confirmation": self._config.require_backup_confirmation,
            "items": items,
        }

    def _rollback_checklist(self) -> dict[str, Any]:
        return {
            "status": "placeholder",
            "items": [
                {"item": "keep_current_app_storage_backend", "status": "placeholder"},
                {"item": "disable_shadow_or_dual_flags", "status": "placeholder"},
                {"item": "restore_from_verified_backup_if_directed", "status": "placeholder"},
            ],
        }

    def _guard_status(self) -> dict[str, Any]:
        return {
            "no_production_writes": "enforced" if self._config.no_production_writes else "blocked",
            "forbidden_actions": {action: "refused" for action in FORBIDDEN_ACTIONS},
            "read_only": True,
        }


def build_checker_from_env(
    *,
    database_url_env: str = DEFAULT_DATABASE_URL_ENV,
    require_backup_confirmation: bool = False,
    no_production_writes: bool = True,
) -> CutoverPreflightChecker:
    config = CutoverPreflightConfig.from_env(
        database_url_env=database_url_env,
        require_backup_confirmation=require_backup_confirmation,
        no_production_writes=no_production_writes,
    )
    return CutoverPreflightChecker(config=config)


def redact_secret_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_by_key(key, item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_secret_values(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secret_values(item) for item in value)
    if isinstance(value, str):
        return redact_uri(value)
    return value


def redact_uri(value: str) -> str:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return value
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port is not None else ""
    username = parsed.username or ""
    credentials = f"{username}:***@" if username else ""
    return urlunparse(
        ParseResult(
            scheme=parsed.scheme,
            netloc=f"{credentials}{host}{port}",
            path=parsed.path,
            params="",
            query="",
            fragment="",
        )
    )


def redact_secret_text(value: str) -> str:
    return re.sub(r"[a-z][a-z0-9+.-]*://[^\s'\"<>]+", lambda match: redact_uri(match.group(0)), value)


def _redact_by_key(key: str, value: Any) -> Any:
    lowered = key.lower()
    if lowered.endswith("_env"):
        return redact_secret_values(value)
    if any(part in lowered for part in SECRET_KEY_PARTS):
        if isinstance(value, str):
            redacted_uri = redact_uri(value)
            if "***" in value:
                return value
            return redacted_uri if redacted_uri != value else "<redacted>"
        return "<redacted>"
    return redact_secret_values(value)


def _schema_table_location(rows: list[dict[str, Any]]) -> str | None:
    for row in rows:
        if row.get("table_schema") == "public" and row.get("table_name") == "schema_migrations":
            return SCHEMA_MIGRATIONS_TABLE
    return None


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "y", "on", "confirmed"}


def _positive_int_from_env(name: str, default: int) -> int:
    raw_value = (os.environ.get(name) or "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise CutoverPreflightConfigurationError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise CutoverPreflightConfigurationError(f"{name} must be positive.") from None
    return value
