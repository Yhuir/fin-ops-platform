from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fin_ops_platform.services.object_storage import ObjectStorageSettings
from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository, RuntimeQueueSettings
from fin_ops_platform.services.runtime_redis import RuntimeRedisHelper, RuntimeRedisSettings


@dataclass(frozen=True)
class RuntimeRepositoryContext:
    state_store: Any | None
    operations_audit_repository: PostgresOperationsAuditRepository | None
    queue_repository: RuntimeQueueRepository | None
    queue_settings: RuntimeQueueSettings
    redis_helper: RuntimeRedisHelper
    object_storage_settings: ObjectStorageSettings

    @classmethod
    def from_state_store(cls, state_store: Any | None) -> RuntimeRepositoryContext:
        connection = getattr(state_store, "_connection", None)
        return cls(
            state_store=state_store,
            operations_audit_repository=PostgresOperationsAuditRepository(connection) if connection is not None else None,
            queue_repository=RuntimeQueueRepository(connection) if connection is not None else None,
            queue_settings=RuntimeQueueSettings.from_env(),
            redis_helper=RuntimeRedisHelper.from_settings(RuntimeRedisSettings.from_env()),
            object_storage_settings=ObjectStorageSettings.from_env(),
        )

    def summary(self) -> dict[str, object]:
        redis_summary = self.redis_helper.health_summary()
        return {
            "state_store_backend": getattr(self.state_store, "storage_backend", None),
            "queue_repository": self.queue_repository is not None,
            **self.queue_settings.summary(),
            "redis_enabled": self.redis_helper.enabled,
            **redis_summary,
            "object_storage_backend": self.object_storage_settings.backend,
            "object_storage_enabled": self.object_storage_settings.enabled,
        }
