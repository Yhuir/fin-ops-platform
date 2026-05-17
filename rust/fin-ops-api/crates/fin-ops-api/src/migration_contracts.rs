#[cfg(test)]
mod tests {
    use std::fs;
    use std::path::PathBuf;

    fn migration_sql() -> String {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let migration_path = manifest_dir
            .join("..")
            .join("..")
            .join("migrations")
            .join("0009_p0_api_fact_sources.sql");

        fs::read_to_string(&migration_path).unwrap_or_else(|err| {
            panic!(
                "expected P0 API fact source migration at {}: {err}",
                migration_path.display()
            )
        })
    }

    #[test]
    fn p0_api_fact_source_migration_covers_required_tables() {
        let sql = migration_sql();

        for required in [
            "create table job.worker_task_acknowledgements",
            "acknowledged_at timestamptz not null default now()",
            "trace_id text not null",
            "create table app.settings_profiles",
            "create table app.project_profiles",
            "create table app.project_assignments",
            "create table app.data_reset_requests",
            "requested_by text not null",
            "outbox_event_id uuid references job.outbox_events(id)",
            "create table app.ledgers",
            "create table app.reminders",
            "create table app.reminder_runs",
            "create table app.import_preview_sessions",
            "create table app.import_fact_lineage",
            "create table app.matching_runs",
            "create table app.turnover_relation_extras",
            "create table app.etc_import_sessions",
            "create table app.etc_reconciliation_tasks",
            "create table app.etc_reconciliation_task_files",
            "create table app.etc_reconciliation_task_items",
            "create table app.etc_reconciliation_task_evidences",
            "create table app.etc_oa_drafts",
            "create table app.etc_batch_events",
            "create table app.etc_invoice_submission_events",
            "create table app.tax_certified_import_sessions",
            "create table app.export_artifacts",
            "create table staging.p0_api_fact_source_backfill_plan",
        ] {
            assert!(sql.contains(required), "missing required DDL: {required}");
        }
    }

    #[test]
    fn p0_api_fact_source_migration_preserves_audit_idempotency_and_legacy_traceability() {
        let sql = migration_sql();

        for required in [
            "references audit.events(id)",
            "idempotency_key text",
            "legacy_collection text",
            "legacy_id text",
            "created_by text not null",
            "updated_by text",
            "create unique index",
            "execute function app.set_updated_at()",
            "references staging.legacy_id_map(id)",
        ] {
            assert!(
                sql.contains(required),
                "migration is missing production guard: {required}"
            );
        }
    }
}
