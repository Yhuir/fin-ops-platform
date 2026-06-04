from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppStatusDependencyDefinition:
    key: str
    label: str
    critical: bool = True


APP_STATUS_DEPENDENCY_REGISTRY: dict[str, AppStatusDependencyDefinition] = {
    "oa_identity": AppStatusDependencyDefinition("oa_identity", "OA身份"),
    "oa_sync": AppStatusDependencyDefinition("oa_sync", "OA同步"),
    "background_jobs": AppStatusDependencyDefinition("background_jobs", "后台任务"),
    "state_store": AppStatusDependencyDefinition("state_store", "状态存储"),
    "postgres": AppStatusDependencyDefinition("postgres", "PostgreSQL"),
    "redis": AppStatusDependencyDefinition("redis", "Redis", critical=False),
    "object_storage": AppStatusDependencyDefinition("object_storage", "对象存储", critical=False),
    "rabbitmq": AppStatusDependencyDefinition("rabbitmq", "RabbitMQ", critical=False),
    "oa_mongo": AppStatusDependencyDefinition("oa_mongo", "OA MongoDB"),
}
