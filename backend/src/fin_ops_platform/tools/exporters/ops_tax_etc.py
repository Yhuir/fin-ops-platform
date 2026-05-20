from __future__ import annotations

from fin_ops_platform.tools.exporters import ExportDefinition


OPS_TAX_ETC_EXPORTS: tuple[ExportDefinition, ...] = (
    ExportDefinition("app_settings.ndjson", "app_settings", "app_settings", identity_fields=("id", "_id")),
    ExportDefinition(
        "pending_invoice_manual_invoice_commands.ndjson",
        "pending_invoice_commands",
        "pending_invoice_manual_invoice_command",
        identity_fields=("request_id", "command_id", "id"),
    ),
    ExportDefinition("oa_sync_state.ndjson", "oa_sync_state", "oa_sync_state", identity_fields=("id", "_id")),
    ExportDefinition("manual_oa_imports.ndjson", "manual_oa_imports", "manual_oa_imports", identity_fields=("id", "_id")),
    ExportDefinition(
        "oa_attachment_invoice_cache.ndjson",
        "oa_attachment_invoice_cache",
        "oa_attachment_invoice_cache_entry",
        rebuildable=True,
        identity_fields=("id", "cache_key"),
    ),
    ExportDefinition("background_jobs.ndjson", "background_jobs", "background_job", identity_fields=("id", "job_id")),
    ExportDefinition("app_health_alerts.ndjson", "app_health_alerts", "app_health_alerts_snapshot", identity_fields=("id", "_id")),
    ExportDefinition(
        "tax_certified_import_sessions.ndjson",
        "tax_certified_import_sessions",
        "tax_certified_import_session",
        identity_fields=("id", "session_id"),
    ),
    ExportDefinition(
        "tax_certified_import_batches.ndjson",
        "tax_certified_import_batches",
        "tax_certified_import_batch",
        identity_fields=("id", "batch_id"),
    ),
    ExportDefinition(
        "tax_certified_import_records.ndjson",
        "tax_certified_import_records",
        "tax_certified_import_record",
        identity_fields=("id", "certified_unique_key", "invoice_no"),
    ),
    ExportDefinition("etc_invoices.ndjson", "etc_state", "etc_state_snapshot", identity_fields=("id", "_id")),
    ExportDefinition("etc_import_sessions.ndjson", "etc_state", "etc_import_sessions_snapshot", identity_fields=("id", "_id")),
    ExportDefinition("etc_import_batches.ndjson", "etc_state", "etc_import_batches_snapshot", identity_fields=("id", "_id")),
    ExportDefinition("etc_submission_batches.ndjson", "etc_state", "etc_submission_batches_snapshot", identity_fields=("id", "_id")),
    ExportDefinition("etc_business_batches.ndjson", "etc_state", "etc_business_batches_snapshot", identity_fields=("id", "_id")),
    ExportDefinition(
        "etc_reconciliation_tasks.ndjson",
        "etc_reconciliation_state",
        "etc_reconciliation_tasks_snapshot",
        identity_fields=("id", "task_id"),
    ),
    ExportDefinition(
        "etc_reconciliation_files.ndjson",
        "etc_reconciliation_state",
        "etc_reconciliation_files_snapshot",
        identity_fields=("id", "file_id", "stored_file_path"),
    ),
    ExportDefinition(
        "historical_etc_repair_bundles.ndjson",
        "historical_etc_repair_bundles",
        "historical_etc_repair_bundle",
        identity_fields=("id", "bundle_id"),
    ),
    ExportDefinition(
        "historical_etc_repair_parsed_seeds.ndjson",
        "historical_etc_repair_parsed_seeds",
        "historical_etc_repair_parsed_seed",
        identity_fields=("id", "bundle_id"),
    ),
    ExportDefinition(
        "historical_etc_repair_states.ndjson",
        "historical_etc_repair_states",
        "historical_etc_repair_state",
        identity_fields=("id", "bundle_id"),
    ),
    ExportDefinition("turnover_relations.ndjson", "turnover_relations", "turnover_relation", identity_fields=("id", "relation_id")),
    ExportDefinition(
        "turnover_relations_meta.ndjson",
        "turnover_relations_meta",
        "turnover_relations_snapshot",
        identity_fields=("id",),
    ),
    ExportDefinition(
        "turnover_relation_events.ndjson",
        "turnover_relation_audit_log",
        "turnover_relation_event",
        identity_fields=("id", "event_id", "relation_id"),
    ),
    ExportDefinition(
        "turnover_ledger_extras.ndjson",
        "turnover_ledger_extras",
        "turnover_ledger_extra",
        identity_fields=("id", "extra_id", "bank_transaction_id"),
    ),
)
