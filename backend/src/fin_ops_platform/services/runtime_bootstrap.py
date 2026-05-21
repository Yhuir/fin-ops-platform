from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fin_ops_platform.services.object_storage import ObjectStorageSettings
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository
from fin_ops_platform.services.runtime_redis import RuntimeRedisHelper, RuntimeRedisSettings


@dataclass(frozen=True)
class LegacySnapshotDependency:
    snapshot_key: str
    owner: str
    module: str
    exit_condition: str


LEGACY_SNAPSHOT_ALLOWLIST: tuple[LegacySnapshotDependency, ...] = (
)

LEGACY_FULL_SNAPSHOT_REASON_PREFIXES = (
    "legacy_",
    "migration_",
    "shadow_",
    "test",
    "unit_test",
)


class LegacySnapshotBootstrap:
    def __init__(self, state_store: Any | None, allowlist: tuple[LegacySnapshotDependency, ...] = LEGACY_SNAPSHOT_ALLOWLIST) -> None:
        self._state_store = state_store
        self.allowlist = allowlist

    def load_full_snapshot(self, *, reason: str) -> dict[str, object]:
        normalized_reason = str(reason or "").strip()
        if not normalized_reason.startswith(LEGACY_FULL_SNAPSHOT_REASON_PREFIXES):
            raise RuntimeError(
                "Full snapshot bootstrap is restricted to explicit legacy, migration, shadow, or test scenarios."
            )
        if self._state_store is None:
            return {}
        bootstrap_loader = getattr(self._state_store, "load_bootstrap_snapshot", None)
        payload = bootstrap_loader() if callable(bootstrap_loader) else self._state_store.load()
        if not isinstance(payload, dict):
            raise RuntimeError(f"Legacy full snapshot load for {reason} returned {type(payload).__name__}, expected dict.")
        return payload

    def summary(self) -> dict[str, object]:
        return {
            "allowlist_count": len(self.allowlist),
            "allowlist": [
                {
                    "snapshot_key": entry.snapshot_key,
                    "owner": entry.owner,
                    "module": entry.module,
                    "exit_condition": entry.exit_condition,
                }
                for entry in self.allowlist
            ],
        }


@dataclass(frozen=True)
class RuntimeRepositoryContext:
    state_store: Any | None
    queue_repository: RuntimeQueueRepository | None
    redis_helper: RuntimeRedisHelper
    object_storage_settings: ObjectStorageSettings

    @classmethod
    def from_state_store(cls, state_store: Any | None) -> RuntimeRepositoryContext:
        connection = getattr(state_store, "_connection", None)
        return cls(
            state_store=state_store,
            queue_repository=RuntimeQueueRepository(connection) if connection is not None else None,
            redis_helper=RuntimeRedisHelper.from_settings(RuntimeRedisSettings.from_env()),
            object_storage_settings=ObjectStorageSettings.from_env(),
        )

    def summary(self) -> dict[str, object]:
        return {
            "state_store_backend": getattr(self.state_store, "storage_backend", None),
            "queue_repository": self.queue_repository is not None,
            "redis_enabled": self.redis_helper.enabled,
            "object_storage_backend": self.object_storage_settings.backend,
            "object_storage_enabled": self.object_storage_settings.enabled,
        }
