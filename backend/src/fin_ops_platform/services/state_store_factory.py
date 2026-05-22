from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fin_ops_platform.services.state_store import ApplicationStateStore


POSTGRES_STORAGE_BACKEND = "postgres"
APP_STORAGE_BACKEND_ENV = "FIN_OPS_APP_STORAGE_BACKEND"
PRIMARY_STORAGE_BACKEND_ENV = "FIN_OPS_PRIMARY_STORAGE_BACKEND"
SHADOW_STORAGE_BACKEND_ENV = "FIN_OPS_SHADOW_STORAGE_BACKEND"
MIRROR_STORAGE_BACKEND_ENV = "FIN_OPS_MIRROR_STORAGE_BACKEND"
CUTOVER_PREFLIGHT_ONLY_ENV = "FIN_OPS_CUTOVER_PREFLIGHT_ONLY"
SHADOW_COMPARE_ENABLED_ENV = "FIN_OPS_SHADOW_COMPARE_ENABLED"
SHADOW_COMPARE_SAMPLE_RATE_ENV = "FIN_OPS_SHADOW_COMPARE_SAMPLE_RATE"
DUAL_WRITE_STRICT_ENV = "FIN_OPS_DUAL_WRITE_STRICT"

LOCAL_STORAGE_BACKENDS = {"local", "local_pickle"}
APPLICATION_STATE_STORE_BACKENDS = {*LOCAL_STORAGE_BACKENDS, "mongo", "mongo_pickle", "auto"}
PREFLIGHT_STORE_BACKENDS = {"local_pickle", POSTGRES_STORAGE_BACKEND}


@dataclass(frozen=True)
class ShadowPreflightStateStore:
    primary_store: Any
    shadow_store: Any

    @property
    def storage_backend(self) -> str:
        return "shadow"

    @property
    def storage_mode(self) -> str:
        return "shadow"

    @property
    def data_dir(self) -> Path:
        return self.primary_store.data_dir

    @property
    def mongo_database_name(self) -> str | None:
        return getattr(self.primary_store, "mongo_database_name", None)

    def health_summary(self) -> dict[str, object]:
        summary = _store_health_summary(self.primary_store)
        summary["preflight_mode"] = "shadow"
        summary["primary_backend"] = getattr(self.primary_store, "storage_backend", None)
        summary["shadow_backend"] = getattr(self.shadow_store, "storage_backend", None)
        return summary

    def __getattr__(self, name: str) -> Any:
        return getattr(self.primary_store, name)


@dataclass(frozen=True)
class DualPreflightStateStore:
    primary_store: Any
    mirror_store: Any

    @property
    def storage_backend(self) -> str:
        return "dual"

    @property
    def storage_mode(self) -> str:
        return "dual"

    @property
    def data_dir(self) -> Path:
        return self.primary_store.data_dir

    @property
    def mongo_database_name(self) -> str | None:
        return getattr(self.primary_store, "mongo_database_name", None)

    def health_summary(self) -> dict[str, object]:
        summary = _store_health_summary(self.primary_store)
        summary["preflight_mode"] = "dual"
        summary["primary_backend"] = getattr(self.primary_store, "storage_backend", None)
        summary["mirror_backend"] = getattr(self.mirror_store, "storage_backend", None)
        return summary

    def __getattr__(self, name: str) -> Any:
        return getattr(self.primary_store, name)


def build_state_store(data_dir: Path | None) -> Any | None:
    if data_dir is None:
        return None

    backend = _storage_backend_from_env(APP_STORAGE_BACKEND_ENV)
    if not backend or backend in APPLICATION_STATE_STORE_BACKENDS:
        return ApplicationStateStore(data_dir)

    if backend == POSTGRES_STORAGE_BACKEND:
        return _build_postgres_store(data_dir)

    if backend == "shadow":
        return _build_shadow_store(data_dir)

    if backend == "dual":
        return _build_dual_store(data_dir)

    raise ValueError(
        f"Unsupported {APP_STORAGE_BACKEND_ENV}={_redact_config_value(backend)!r}. "
        "Supported values are local_pickle, mongo, auto, postgres, shadow, and dual."
    )


def _build_shadow_store(data_dir: Path) -> Any:
    primary_backend = _required_preflight_backend(PRIMARY_STORAGE_BACKEND_ENV)
    shadow_backend = _required_preflight_backend(SHADOW_STORAGE_BACKEND_ENV)
    primary_store = _build_preflight_backend_store(data_dir, PRIMARY_STORAGE_BACKEND_ENV, primary_backend)
    shadow_store = _build_preflight_backend_store(data_dir, SHADOW_STORAGE_BACKEND_ENV, shadow_backend)
    return _make_shadow_wrapper(primary_store=primary_store, shadow_store=shadow_store)


def _build_dual_store(data_dir: Path) -> Any:
    primary_backend = _required_preflight_backend(PRIMARY_STORAGE_BACKEND_ENV)
    mirror_backend = _required_preflight_backend(MIRROR_STORAGE_BACKEND_ENV)
    if (os.environ.get(CUTOVER_PREFLIGHT_ONLY_ENV) or "").strip() != "1":
        raise ValueError(f"FIN_OPS_APP_STORAGE_BACKEND=dual requires {CUTOVER_PREFLIGHT_ONLY_ENV}=1.")
    primary_store = _build_preflight_backend_store(data_dir, PRIMARY_STORAGE_BACKEND_ENV, primary_backend)
    mirror_store = _build_preflight_backend_store(data_dir, MIRROR_STORAGE_BACKEND_ENV, mirror_backend)
    return _make_dual_wrapper(primary_store=primary_store, mirror_store=mirror_store)


def _build_preflight_backend_store(data_dir: Path, env_name: str, backend: str) -> Any:
    if backend == "local_pickle":
        return ApplicationStateStore(data_dir)
    if backend == POSTGRES_STORAGE_BACKEND:
        return _build_postgres_store(data_dir)
    raise ValueError(
        f"Unsupported {env_name}={_redact_config_value(backend)!r}. "
        "Supported preflight backend values are local_pickle and postgres."
    )


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


def _required_preflight_backend(env_name: str) -> str:
    backend = _storage_backend_from_env(env_name)
    if not backend:
        raise ValueError(f"FIN_OPS_APP_STORAGE_BACKEND preflight mode requires explicit {env_name}.")
    if backend in PREFLIGHT_STORE_BACKENDS:
        return backend
    raise ValueError(
        f"Unsupported {env_name}={_redact_config_value(backend)!r}. "
        "Supported preflight backend values are local_pickle and postgres."
    )


def _storage_backend_from_env(env_name: str) -> str:
    return (os.environ.get(env_name) or "").strip().lower()


def _redact_config_value(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return "<redacted-uri>"
    lowered = value.lower()
    if any(marker in lowered for marker in ("password=", "token=", "secret=", "authorization=", "cookie=")):
        return "<redacted-secret>"
    return value


def _store_health_summary(store: Any) -> dict[str, object]:
    if hasattr(store, "health_summary"):
        return dict(store.health_summary())
    return {}


def _make_shadow_wrapper(*, primary_store: Any, shadow_store: Any) -> Any:
    wrapper_class = _shadow_wrapper_class()
    if wrapper_class is ShadowPreflightStateStore:
        return wrapper_class(primary_store=primary_store, shadow_store=shadow_store)
    return wrapper_class(
        primary=primary_store,
        shadow=shadow_store,
        compare_enabled=_env_flag_enabled(SHADOW_COMPARE_ENABLED_ENV, default=False),
        compare_sample_rate=_env_float_between(SHADOW_COMPARE_SAMPLE_RATE_ENV, default=1.0, minimum=0.0, maximum=1.0),
    )


def _make_dual_wrapper(*, primary_store: Any, mirror_store: Any) -> Any:
    wrapper_class = _dual_wrapper_class()
    if wrapper_class is DualPreflightStateStore:
        return wrapper_class(primary_store=primary_store, mirror_store=mirror_store)
    return wrapper_class(
        primary=primary_store,
        mirror=mirror_store,
        strict=_env_flag_enabled(DUAL_WRITE_STRICT_ENV, default=False),
    )


def _env_flag_enabled(env_name: str, *, default: bool) -> bool:
    raw_value = (os.environ.get(env_name) or "").strip()
    if not raw_value:
        return default
    normalized = raw_value.lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Unsupported {env_name}={_redact_config_value(raw_value)!r}; expected boolean flag.")


def _env_float_between(env_name: str, *, default: float, minimum: float, maximum: float) -> float:
    raw_value = (os.environ.get(env_name) or "").strip()
    if not raw_value:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"Unsupported {env_name}={_redact_config_value(raw_value)!r}; expected decimal value.") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"Unsupported {env_name}={value!r}; expected {minimum} <= value <= {maximum}.")
    return value


def _shadow_wrapper_class() -> type[Any]:
    try:
        from fin_ops_platform.services.shadow_state_store import ShadowStateStore
    except ImportError:
        return ShadowPreflightStateStore
    return ShadowStateStore


def _dual_wrapper_class() -> type[Any]:
    try:
        from fin_ops_platform.services.dual_state_store import DualStateStore
    except ImportError:
        return DualPreflightStateStore
    return DualStateStore
