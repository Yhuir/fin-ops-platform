from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppStatusReadModelDefinition:
    key: str
    scope_type: str
    worker_instance: str
    refresh_event_type: str
    readiness_strategy: str = "app_status_readiness"
    critical: bool = True


APP_STATUS_READ_MODEL_REGISTRY: dict[str, AppStatusReadModelDefinition] = {
    "workbench": AppStatusReadModelDefinition(
        key="workbench",
        scope_type="workbench",
        worker_instance="workbench",
        refresh_event_type="workbench.read_model.refresh",
        readiness_strategy="active_generation",
    ),
    "workbench_relation": AppStatusReadModelDefinition(
        key="workbench_relation",
        scope_type="workbench_relation",
        worker_instance="workbench-relation",
        refresh_event_type="workbench_relation.read_model.refresh",
    ),
    "search": AppStatusReadModelDefinition(
        key="search",
        scope_type="search",
        worker_instance="search",
        refresh_event_type="search.read_model.refresh",
    ),
    "no_oa_bank_batch": AppStatusReadModelDefinition(
        key="no_oa_bank_batch",
        scope_type="no_oa_bank_batch",
        worker_instance="no-oa-bank-batch",
        refresh_event_type="no_oa_bank_batch.read_model.refresh",
        critical=False,
    ),
}


def read_model_by_scope_type() -> dict[str, AppStatusReadModelDefinition]:
    return {definition.scope_type: definition for definition in APP_STATUS_READ_MODEL_REGISTRY.values()}


def read_model_by_refresh_event_type() -> dict[str, AppStatusReadModelDefinition]:
    return {definition.refresh_event_type: definition for definition in APP_STATUS_READ_MODEL_REGISTRY.values()}
