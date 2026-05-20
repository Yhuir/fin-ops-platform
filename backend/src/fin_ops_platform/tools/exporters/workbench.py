from __future__ import annotations

from fin_ops_platform.tools.exporters import ExportDefinition


WORKBENCH_EXPORTS: tuple[ExportDefinition, ...] = (
    ExportDefinition("matching_runs.ndjson", "matching_runs", "matching_run", identity_fields=("id", "run_id")),
    ExportDefinition("matching_results.ndjson", "matching_results", "matching_result", identity_fields=("id", "result_id")),
    ExportDefinition(
        "workbench_pair_relations.ndjson",
        "workbench_pair_relations",
        "workbench_pair_relation",
        identity_fields=("id", "relation_id", "case_id"),
    ),
    ExportDefinition(
        "workbench_pair_relation_history.ndjson",
        "workbench_pair_relations_meta",
        "workbench_pair_relation_history_snapshot",
        identity_fields=("id",),
    ),
    ExportDefinition(
        "workbench_row_overrides.ndjson",
        "workbench_row_overrides",
        "workbench_row_override",
        identity_fields=("id", "row_id", "override_id"),
    ),
    ExportDefinition(
        "workbench_exception_cases.ndjson",
        "workbench_exception_cases",
        "workbench_exception_case",
        identity_fields=("id", "case_id"),
    ),
    ExportDefinition(
        "workbench_exception_case_events.ndjson",
        "workbench_exception_cases_meta",
        "workbench_exception_case_events_snapshot",
        identity_fields=("id",),
    ),
    ExportDefinition(
        "no_oa_bank_batches.ndjson",
        "no_oa_bank_batches",
        "no_oa_bank_batch",
        identity_fields=("id", "batch_id"),
    ),
    ExportDefinition(
        "no_oa_bank_batches_meta.ndjson",
        "no_oa_bank_batches_meta",
        "no_oa_bank_batches_snapshot",
        identity_fields=("id",),
    ),
    ExportDefinition(
        "no_oa_bank_batch_events.ndjson",
        "no_oa_bank_batch_audit_log",
        "no_oa_bank_batch_event",
        identity_fields=("id", "event_id", "batch_id"),
    ),
    ExportDefinition(
        "bank_transaction_categories.ndjson",
        "bank_transaction_categories",
        "bank_transaction_category",
        identity_fields=("id", "transaction_id", "bank_transaction_id"),
    ),
    ExportDefinition(
        "bank_transaction_category_events.ndjson",
        "bank_transaction_categories_meta",
        "bank_transaction_category_events_snapshot",
        identity_fields=("id",),
    ),
    ExportDefinition(
        "workbench_matching_dirty_scopes.ndjson",
        "workbench_matching_dirty_scopes",
        "workbench_matching_dirty_scope",
        rebuildable=True,
        identity_fields=("id", "scope_key", "scope_month"),
    ),
)
