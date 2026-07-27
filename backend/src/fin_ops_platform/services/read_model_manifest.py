from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReadModelManifestEntry:
    key: str
    scope_type: str
    refresh_event_type: str
    primary_worker_instance: str
    auxiliary_refresh_worker_instances: tuple[str, ...]
    query_status_contract: str
    projection_strategy: str
    all_scope_semantics: str
    partition_key_contract: str
    scoped_incremental_target: str
    full_rebuild_fallback: str
    freshness_proof_contract: str
    force_refresh_contract: str
    operation_barrier_contract: str
    repository_port_contract: tuple[str, ...]
    query_owner: str
    repository_owner: str
    permission_owner: str
    test_owner: str
    read_dependencies: tuple[str, ...] = ()


READ_MODEL_MANIFEST: dict[str, ReadModelManifestEntry] = {
    "workbench": ReadModelManifestEntry(
        key="workbench",
        scope_type="workbench",
        refresh_event_type="workbench.read_model.refresh",
        primary_worker_instance="workbench",
        auxiliary_refresh_worker_instances=(),
        query_status_contract="equivalent_active_generation",
        projection_strategy="active_generation_scoped_publish",
        all_scope_semantics="active_month_shard_aggregate",
        partition_key_contract="month_scope active generation; all aggregates active month shards",
        scoped_incremental_target="workbench active generation rows, groups, summaries and details for affected month scopes",
        full_rebuild_fallback="gateway force refresh rebuilds requested active month generation or all aggregate from canonical facts",
        freshness_proof_contract=(
            "active generation metadata, expected relation/rule and scoped canonical object source_versions, "
            "active pending claim version, and current-effective dirty/outbox state"
        ),
        force_refresh_contract="gateway_force_refresh_active_generation_scope",
        operation_barrier_contract="app_status_registry_target",
        repository_port_contract=(
            "get_workbench_initial_page",
            "get_workbench_summary",
            "get_workbench_groups_page",
            "get_workbench_group_detail",
            "get_workbench_row_detail",
            "find_workbench_row_scope_key",
            "get_workbench_refresh_status",
            "get_workbench_groups_freshness_status",
            "save_workbench_read_models",
            "load_workbench_read_models",
        ),
        query_owner="WorkbenchQueryFacade",
        repository_owner="PostgresReadModelRepository.workbench",
        permission_owner="workbench_api_session",
        test_owner="tests/test_workbench_sql_runtime.py",
    ),
    "workbench_relation": ReadModelManifestEntry(
        key="workbench_relation",
        scope_type="workbench_relation",
        refresh_event_type="workbench_relation.read_model.refresh",
        primary_worker_instance="workbench-relation",
        auxiliary_refresh_worker_instances=(),
        query_status_contract="self_managed_freshness",
        projection_strategy="scoped_incremental_distribution",
        all_scope_semantics="fan_out_command",
        partition_key_contract="relation month_scope; all is fan-out only",
        scoped_incremental_target="workbench relation distribution rows and groups for affected month scopes",
        full_rebuild_fallback="gateway force refresh fan-out rebuilds relation month shards and marks empty scopes",
        freshness_proof_contract="workbench_relation scope source_versions plus app_status readiness and current-effective dirty/outbox state",
        force_refresh_contract="gateway_force_refresh",
        operation_barrier_contract="app_status_registry_target",
        repository_port_contract=(
            "save_workbench_relation_distribution",
            "mark_workbench_relation_scope_empty",
            "get_workbench_relation_rows_by_ids",
            "list_workbench_relation_rows",
            "get_workbench_relation_groups_by_ids",
            "workbench_relation_source_versions",
            "workbench_relation_scope_summaries",
            "workbench_relation_scope_summary",
        ),
        query_owner="WorkbenchRelationReadFacade",
        repository_owner="WorkbenchRelationReadModelRepositoryPort",
        permission_owner="downstream_page_api_session",
        test_owner="tests/test_workbench_relation_read_facade.py",
    ),
    "search": ReadModelManifestEntry(
        key="search",
        scope_type="search",
        refresh_event_type="search.read_model.refresh",
        primary_worker_instance="search",
        auxiliary_refresh_worker_instances=("search-secondary", "search-tertiary"),
        query_status_contract="self_managed_freshness",
        projection_strategy="partitioned_scoped_index",
        all_scope_semantics="fan_out_command",
        partition_key_contract="search source month_scope; all is fan-out only",
        scoped_incremental_target="search index rows for affected month scopes",
        full_rebuild_fallback="gateway force refresh all enumerates search month shards through the search refresh producer",
        freshness_proof_contract="search index source_versions plus current-effective dirty/outbox state",
        force_refresh_contract="gateway_force_refresh",
        operation_barrier_contract="app_status_registry_target",
        repository_port_contract=(
            "search_index",
            "save_search_index_rows",
        ),
        query_owner="Search read API",
        repository_owner="SearchReadModelRepositoryPort",
        permission_owner="search_api_session",
        test_owner="tests/test_search_sql_runtime.py",
    ),
    "no_oa_bank_batch": ReadModelManifestEntry(
        key="no_oa_bank_batch",
        scope_type="no_oa_bank_batch",
        refresh_event_type="no_oa_bank_batch.read_model.refresh",
        primary_worker_instance="no-oa-bank-batch",
        auxiliary_refresh_worker_instances=(),
        query_status_contract="self_managed_freshness",
        projection_strategy="scoped_incremental",
        all_scope_semantics="fan_out_command",
        partition_key_contract="no-OA bank batch month_scope; all is fan-out only",
        scoped_incremental_target="no-OA bank batch public rows for affected month scopes",
        full_rebuild_fallback="gateway force refresh all enumerates no-OA month shards through the refresh producer",
        freshness_proof_contract="no-OA source_versions plus app_status readiness and current-effective dirty/outbox state",
        force_refresh_contract="gateway_force_refresh",
        operation_barrier_contract="app_status_registry_target",
        repository_port_contract=(
            "list_no_oa_bank_batch_rows",
            "no_oa_bank_batch_source_versions_summary",
        ),
        query_owner="NoOaBankBatchApplicationService",
        repository_owner="NoOaBankBatchReadModelRepositoryPort",
        permission_owner="no_oa_bank_batch_api_session",
        test_owner="tests/test_no_oa_bank_batch_application_service.py",
    ),
}


def read_model_manifest_by_scope_type() -> dict[str, ReadModelManifestEntry]:
    return {entry.scope_type: entry for entry in READ_MODEL_MANIFEST.values()}


def read_model_manifest_by_refresh_event_type() -> dict[str, ReadModelManifestEntry]:
    return {entry.refresh_event_type: entry for entry in READ_MODEL_MANIFEST.values()}


def is_command_only_read_model_scope(read_model_key: str, scope_key: str) -> bool:
    """Return whether a scope is a fan-out command rather than queryable state."""

    entry = READ_MODEL_MANIFEST.get(str(read_model_key or "").strip())
    normalized_scope_key = str(scope_key or "").strip()
    if entry is None or not normalized_scope_key:
        return False
    is_all_scope = normalized_scope_key == "all" or normalized_scope_key.endswith(":all")
    return is_all_scope and entry.all_scope_semantics == "fan_out_command"
