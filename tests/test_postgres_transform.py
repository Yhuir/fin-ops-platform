from __future__ import annotations

from fin_ops_platform.postgres.migrate import run_psql
from fin_ops_platform.tools.postgres_transform import (
    JsonValue,
    StagingRecord,
    build_transaction_sql,
    build_transform_plan,
    stable_target_id,
    target_upsert_sql,
)
from postgres_test_utils import apply_test_migrations, fetch_scalar, require_postgres_test_database_url, truncate_test_database


def record(source: str, legacy: str, payload: dict[str, object]) -> StagingRecord:
    return StagingRecord(
        export_id="export-1",
        source_collection=source,
        legacy_mongo_id=legacy,
        record_type=source,
        normalized_payload=payload,
        raw_payload={"_id": legacy},
    )


def test_stable_target_id_is_deterministic_and_table_scoped() -> None:
    first = stable_target_id("invoices", "abc", "app", "invoices")
    second = stable_target_id("invoices", "abc", "app", "invoices")
    other = stable_target_id("invoices", "abc", "read_model", "search_index_rows")

    assert first == second
    assert first != other


def test_transform_plan_builds_core_rows_and_generated_search_rows() -> None:
    export_row = {
        "export_id": "export-1",
        "source_database": "fin_ops_platform_app",
        "status": "imported",
        "manifest": {"total_records": 2, "manifest_sha256": "sha"},
    }
    plan = build_transform_plan(
        export_row=export_row,
        records=[
            record("invoices", "inv-1", {"invoice_no": "F001", "amount": "12.30", "signed_amount": "12.30", "status": "pending"}),
            record(
                "bank_transactions",
                "bank-1",
                {
                    "account_no": "1001",
                    "txn_direction": "outflow",
                    "counterparty_name_raw": "Vendor",
                    "amount": "5.00",
                    "status": "pending",
                },
            ),
        ],
    )

    assert not plan.blockers
    assert plan.table_counts()["app.invoices"] == 1
    assert plan.table_counts()["app.bank_transactions"] == 1
    assert plan.table_counts()["read_model.search_index_rows"] == 2


def test_target_upsert_sql_casts_jsonb_and_text_values() -> None:
    export_row = {
        "export_id": "export-1",
        "source_database": "fin_ops_platform_app",
        "status": "imported",
        "manifest": {"total_records": 1},
    }
    plan = build_transform_plan(
        export_row=export_row,
        records=[record("app_settings", "settings", {"settings_key": "app_settings", "version": 2})],
    )

    sql = target_upsert_sql(plan.rows)

    assert "insert into app.app_settings" in sql
    assert "::jsonb" in sql
    assert "on conflict (settings_key) do update" in sql


def test_target_upsert_sql_uses_natural_conflict_targets_for_refresh_tables() -> None:
    export_row = {
        "export_id": "export-1",
        "source_database": "fin_ops_platform_app",
        "status": "imported",
        "manifest": {"total_records": 5},
    }
    plan = build_transform_plan(
        export_row=export_row,
        records=[
            record("workbench_pair_relations", "mongo-pair-1", {"case_id": "case-1", "relation_mode": "manual"}),
            record("workbench_exception_cases", "mongo-exception-1", {"case_id": "exception-1", "status": "active"}),
            record("no_oa_bank_batches", "mongo-batch-1", {"batch_id": "batch-1", "status": "draft"}),
            record("workbench_row_overrides", "mongo-row-1", {"row_id": "row-1", "row_type": "bank"}),
            record("pending_invoice_manual_invoice_commands", "mongo-command-1", {"request_id": "command-1", "status": "queued"}),
        ],
    )

    sql = target_upsert_sql(plan.rows)

    assert "insert into app.workbench_pair_relations" in sql
    assert "on conflict (case_id) do update" in sql
    assert "insert into app.workbench_exception_cases" in sql
    assert "insert into app.no_oa_bank_batches" in sql
    assert "on conflict (batch_id) do update" in sql
    assert "insert into app.workbench_row_overrides" in sql
    assert "on conflict (row_id, row_type) do update" in sql
    assert "insert into app.pending_invoice_manual_invoice_commands" in sql
    assert "on conflict (command_id) do update" in sql


def test_workbench_row_override_projection_version_defaults_when_source_is_blank_or_invalid() -> None:
    plan = build_transform_plan(
        export_row={"export_id": "export-1", "source_database": "fin_ops_platform_app", "status": "imported", "manifest": {}},
        records=[
            record(
                "workbench_row_overrides",
                "override-1",
                {"row_id": "row-1", "row_type": "bank", "projection_version": "exception_rules_v1"},
            )
        ],
    )

    rows = [row for row in plan.rows if row.target_table == "workbench_row_overrides"]

    assert rows[0].columns["projection_version"] == 1


def test_transform_maps_pending_invoice_commands_to_formal_table() -> None:
    command_payload = {
        "request_id": "cmd-1",
        "request_key": "manual-pending-invoice:bank-1:expense:digest",
        "status": "failed_recoverable",
        "status_history": ["started", "invoice_created", "failed_recoverable"],
        "invoice_id": "invoice-1",
        "relation_case_id": "case-1",
        "error": "boom",
        "last_successful_status": "invoice_created",
        "created_at": "2026-05-20T10:00:00+00:00",
        "updated_at": "2026-05-20T10:01:00+00:00",
    }

    plan = build_transform_plan(
        export_row={"export_id": "export-1", "source_database": "fin_ops_platform_app", "status": "imported", "manifest": {}},
        records=[record("pending_invoice_manual_invoice_commands", "cmd-1", command_payload)],
    )

    rows = [row for row in plan.rows if row.target_table == "pending_invoice_manual_invoice_commands"]

    assert not plan.blockers
    assert rows
    assert rows[0].target_schema == "app"
    assert rows[0].columns["command_id"] == "cmd-1"
    assert rows[0].columns["request_key"] == "manual-pending-invoice:bank-1:expense:digest"
    assert rows[0].columns["status"] == "failed_recoverable"
    assert rows[0].columns["status_history"].value == ["started", "invoice_created", "failed_recoverable"]
    assert rows[0].columns["command_payload"].value["last_successful_status"] == "invoice_created"
    assert "insert into app.pending_invoice_manual_invoice_commands" in target_upsert_sql(rows)


def test_transform_expands_workbench_pair_relation_history_events() -> None:
    plan = build_transform_plan(
        export_row={"export_id": "export-1", "source_database": "fin_ops_platform_app", "status": "imported", "manifest": {}},
        records=[
            record(
                "workbench_pair_relations_meta",
                "state",
                {
                    "pair_relation_history": [
                        {"operation_id": "op-1", "operation_type": "create", "affected_row_ids": ["row-1"]},
                        {"operation_id": "op-2", "operation_type": "withdraw", "affected_row_ids": ["row-2"]},
                    ]
                },
            )
        ],
    )

    rows = [row for row in plan.rows if row.target_table == "workbench_pair_relation_history"]

    assert len(rows) == 2
    assert {row.columns["event_type"] for row in rows} == {"create", "withdraw"}
    assert all("pair_relation_history" not in row.columns["raw_payload"].value["normalized_payload"] for row in rows)
    indexes_by_operation = {
        row.columns["raw_payload"].value["normalized_payload"]["operation_id"]: row.columns["raw_payload"].value["raw_payload"]["_stage04_child_index"]
        for row in rows
    }
    assert indexes_by_operation == {"op-1": 0, "op-2": 1}


def test_fresh_transform_updates_repaired_workbench_relation_and_replaces_history() -> None:
    database_url = require_postgres_test_database_url()
    apply_test_migrations(database_url)
    truncate_test_database(database_url)
    run_psql(
        database_url,
        sql="""
insert into app.workbench_pair_relations(case_id, relation_mode, status, raw_payload)
values ('case-1', 'repair', 'active', '{"normalized_payload":{"case_id":"case-1","relation_mode":"repair"}}'::jsonb);
insert into app.workbench_pair_relation_history(case_id, event_type, raw_payload)
values ('case-1', 'repair_event', '{"normalized_payload":{"operation_id":"repair-op","case_id":"case-1"}}'::jsonb);
insert into app.workbench_pair_relation_history(case_id, event_type, raw_payload)
values ('stale-case', 'stale_event', '{"normalized_payload":{"operation_id":"stale-op","case_id":"stale-case"}}'::jsonb);
""",
    )
    repaired_id = fetch_scalar(database_url, "select id::text from app.workbench_pair_relations where case_id = 'case-1';")
    plan = build_transform_plan(
        export_row={"export_id": "export-1", "source_database": "fin_ops_platform_app", "status": "imported", "manifest": {}},
        records=[
            record("workbench_pair_relations", "mongo-case-1", {"case_id": "case-1", "relation_mode": "fresh", "status": "active"}),
            record(
                "workbench_pair_relations_meta",
                "state",
                {
                    "pair_relation_history": [
                        {
                            "operation_id": "fresh-op",
                            "case_id": "case-1",
                            "operation_type": "fresh_event",
                            "occurred_at": "2026-05-20T10:00:00+00:00",
                        }
                    ]
                },
            ),
        ],
    )

    run_psql(database_url, sql=build_transaction_sql(plan))

    assert fetch_scalar(database_url, "select count(*) from app.workbench_pair_relations where case_id = 'case-1';") == "1"
    assert fetch_scalar(database_url, "select id::text from app.workbench_pair_relations where case_id = 'case-1';") == repaired_id
    assert fetch_scalar(database_url, "select relation_mode from app.workbench_pair_relations where case_id = 'case-1';") == "fresh"
    assert fetch_scalar(database_url, "select count(*) from app.workbench_pair_relation_history where case_id = 'case-1';") == "1"
    assert fetch_scalar(database_url, "select event_type from app.workbench_pair_relation_history where case_id = 'case-1';") == "fresh_event"
    assert fetch_scalar(database_url, "select count(*) from app.workbench_pair_relation_history where case_id = 'stale-case';") == "0"


def test_fresh_transform_replaces_full_snapshot_event_tables() -> None:
    database_url = require_postgres_test_database_url()
    apply_test_migrations(database_url)
    truncate_test_database(database_url)
    run_psql(
        database_url,
        sql="""
insert into app.bank_transaction_category_events(event_type, raw_payload)
values ('stale_category_event', '{"normalized_payload":{"event_id":"stale-category-event"}}'::jsonb);
""",
    )
    plan = build_transform_plan(
        export_row={"export_id": "export-1", "source_database": "fin_ops_platform_app", "status": "imported", "manifest": {}},
        records=[
            record(
                "bank_transaction_categories_meta",
                "state",
                {
                    "schema_version": "category-v1",
                    "categories": {},
                    "audit_log": [{"event_id": "fresh-category-event", "event_type": "fresh_category_event"}],
                },
            ),
        ],
    )

    run_psql(database_url, sql=build_transaction_sql(plan))

    assert fetch_scalar(database_url, "select count(*) from app.bank_transaction_category_events;") == "1"
    assert fetch_scalar(database_url, "select event_type from app.bank_transaction_category_events;") == "fresh_category_event"


def test_fresh_transform_updates_existing_natural_key_runtime_tables() -> None:
    database_url = require_postgres_test_database_url()
    apply_test_migrations(database_url)
    truncate_test_database(database_url)
    run_psql(
        database_url,
        sql="""
insert into app.app_settings(settings_key, settings_payload, raw_payload)
values ('app_settings', '{"version":1}'::jsonb, '{}'::jsonb);
insert into app.workbench_exception_cases(case_id, status, raw_payload)
values ('exception-1', 'repair', '{}'::jsonb);
insert into app.no_oa_bank_batches(batch_id, status, raw_payload)
values ('batch-1', 'repair', '{}'::jsonb);
insert into app.workbench_row_overrides(row_id, row_type, raw_payload)
values ('row-1', 'bank', '{}'::jsonb);
insert into app.pending_invoice_manual_invoice_commands(command_id, request_id, status, command_payload, raw_payload)
values ('command-1', 'command-1', 'repair', '{}'::jsonb, '{}'::jsonb);
""",
    )
    plan = build_transform_plan(
        export_row={"export_id": "export-1", "source_database": "fin_ops_platform_app", "status": "imported", "manifest": {}},
        records=[
            record("app_settings", "settings", {"settings_key": "app_settings", "version": 2}),
            record("workbench_exception_cases", "mongo-exception-1", {"case_id": "exception-1", "status": "fresh"}),
            record("no_oa_bank_batches", "mongo-batch-1", {"batch_id": "batch-1", "status": "fresh"}),
            record("workbench_row_overrides", "mongo-row-1", {"row_id": "row-1", "row_type": "bank", "status": "fresh"}),
            record("pending_invoice_manual_invoice_commands", "mongo-command-1", {"request_id": "command-1", "status": "fresh"}),
        ],
    )

    run_psql(database_url, sql=build_transaction_sql(plan))

    assert fetch_scalar(database_url, "select count(*) from app.app_settings where settings_key = 'app_settings';") == "1"
    assert fetch_scalar(database_url, "select settings_payload->>'version' from app.app_settings where settings_key = 'app_settings';") == "2"
    assert fetch_scalar(database_url, "select count(*) from app.workbench_exception_cases where case_id = 'exception-1';") == "1"
    assert fetch_scalar(database_url, "select status from app.workbench_exception_cases where case_id = 'exception-1';") == "fresh"
    assert fetch_scalar(database_url, "select count(*) from app.no_oa_bank_batches where batch_id = 'batch-1';") == "1"
    assert fetch_scalar(database_url, "select status from app.no_oa_bank_batches where batch_id = 'batch-1';") == "fresh"
    assert fetch_scalar(database_url, "select count(*) from app.workbench_row_overrides where row_id = 'row-1' and row_type = 'bank';") == "1"
    assert fetch_scalar(database_url, "select status from app.workbench_row_overrides where row_id = 'row-1' and row_type = 'bank';") == "fresh"
    assert fetch_scalar(database_url, "select count(*) from app.pending_invoice_manual_invoice_commands where command_id = 'command-1';") == "1"
    assert fetch_scalar(database_url, "select status from app.pending_invoice_manual_invoice_commands where command_id = 'command-1';") == "fresh"


def test_transform_preserves_empty_snapshot_envelopes_as_app_settings() -> None:
    plan = build_transform_plan(
        export_row={"export_id": "export-1", "source_database": "fin_ops_platform_app", "status": "imported", "manifest": {}},
        records=[
            record("no_oa_bank_batches_meta", "state", {"schema_version": "no-oa-v1", "batches": {}, "audit_log": []}),
            record(
                "bank_transaction_categories_meta",
                "state",
                {"schema_version": "category-v1", "categories": {}, "audit_log": [{"event_id": "cat-1"}]},
            ),
            record("turnover_relations_meta", "state", {"schema_version": "turnover-v1", "relations": [], "audit_log": []}),
        ],
    )

    settings_rows = {row.columns["settings_key"]: row for row in plan.rows if row.target_table == "app_settings"}
    category_events = [row for row in plan.rows if row.target_table == "bank_transaction_category_events"]

    assert settings_rows["state:no_oa_bank_batches"].columns["settings_payload"].value["schema_version"] == "no-oa-v1"
    assert settings_rows["state:bank_transaction_categories"].columns["settings_payload"].value["categories"] == {}
    assert settings_rows["state:turnover_relations"].columns["settings_payload"].value["relations"] == []
    assert len(category_events) == 1
    assert category_events[0].columns["raw_payload"].value["normalized_payload"]["event_id"] == "cat-1"


def test_transform_expands_etc_submission_batches_from_batches_snapshot() -> None:
    plan = build_transform_plan(
        export_row={"export_id": "export-1", "source_database": "fin_ops_platform_app", "status": "imported", "manifest": {}},
        records=[
            record(
                "etc_state:etc_submission_batches",
                "current_state",
                {
                    "batches": {
                        "etc_batch_0019": {
                            "id": "etc_batch_0019",
                            "status": "submitted_confirmed",
                            "invoice_ids": ["etc_invoice_0025", "etc_invoice_0026"],
                            "version": 3,
                        }
                    },
                    "invoices": {"etc_invoice_0025": {"id": "etc_invoice_0025"}},
                    "batch_counter": 19,
                },
            )
        ],
    )

    rows = [row for row in plan.rows if row.target_table == "etc_submission_batches"]

    assert len(rows) == 1
    assert rows[0].legacy_mongo_id == "etc_batch_0019"
    assert rows[0].columns["submission_batch_id"] == "etc_batch_0019"
    assert rows[0].columns["invoice_ids"].value == ["etc_invoice_0025", "etc_invoice_0026"]
    assert rows[0].columns["raw_payload"].value["normalized_payload"]["id"] == "etc_batch_0019"
