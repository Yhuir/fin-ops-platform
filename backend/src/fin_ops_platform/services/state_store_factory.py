from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

POSTGRES_STORAGE_BACKEND = "postgres"
APP_STORAGE_BACKEND_ENV = "FIN_OPS_APP_STORAGE_BACKEND"
PRODUCTION_RUNTIME_GUARD_ENV = "FIN_OPS_PRODUCTION_RUNTIME_GUARD"


def build_state_store(data_dir: Path | None) -> Any | None:
    if data_dir is None:
        return None

    backend = _storage_backend_from_env(APP_STORAGE_BACKEND_ENV)
    if backend != POSTGRES_STORAGE_BACKEND:
        configured_backend = backend or "<unset>"
        guard_prefix = f"{PRODUCTION_RUNTIME_GUARD_ENV}=1 " if _production_runtime_guard_enabled() else ""
        raise ValueError(
            f"{guard_prefix}requires {APP_STORAGE_BACKEND_ENV}=postgres, "
            f"got {_redact_config_value(configured_backend)!r}."
        )
    return _build_postgres_store(data_dir)


def _build_postgres_store(data_dir: Path) -> Any:
    from fin_ops_platform.services.object_storage import ObjectStorageSettings, S3ObjectStorageRepository
    from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
    from fin_ops_platform.services.postgres_state_store import PostgresStateStore

    object_storage_settings = ObjectStorageSettings.from_env()
    object_storage_repository = S3ObjectStorageRepository(object_storage_settings) if object_storage_settings.enabled else None
    connection = PostgresConnection(PostgresSettings.from_env())
    _warm_up_postgres_connection(connection)
    read_settings = PostgresSettings.from_read_env()
    sql_read_connection = PostgresConnection(read_settings) if read_settings is not None else None
    if sql_read_connection is not None:
        _warm_up_postgres_connection(sql_read_connection)
    kwargs: dict[str, Any] = {
        "data_dir": data_dir,
        "connection": connection,
    }
    if sql_read_connection is not None:
        kwargs["sql_read_connection"] = sql_read_connection
    if object_storage_repository is not None:
        kwargs["object_storage_repository"] = object_storage_repository
    return PostgresStateStore(**kwargs)


def _warm_up_postgres_connection(connection: Any) -> None:
    warm_up = getattr(connection, "warm_up", None)
    if callable(warm_up):
        warm_up()


def _storage_backend_from_env(env_name: str) -> str:
    return (os.environ.get(env_name) or "").strip().lower()


def _production_runtime_guard_enabled() -> bool:
    return (os.environ.get(PRODUCTION_RUNTIME_GUARD_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


def _redact_config_value(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return "<redacted-uri>"
    lowered = value.lower()
    if any(marker in lowered for marker in ("password=", "token=", "secret=", "authorization=", "cookie=")):
        return "<redacted-secret>"
    return value
