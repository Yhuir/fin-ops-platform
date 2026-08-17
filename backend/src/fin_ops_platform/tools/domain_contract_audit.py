from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
import json
import sys
from typing import Any, TextIO
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from fin_ops_platform.services.postgres_connection import (
    PostgresConfigurationError,
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.tools.cli_reports import postgres_configuration_missing_report


_CONTRACT_COLUMNS = {
    "invoices.invoice_date_month": "invoice_date_month",
    "invoices.source_links_array": "invoice_source_links_array",
    "invoices.raw_payload_object": "invoice_raw_payload_object",
    "bank_transactions.direction": "bank_direction",
    "bank_transactions.txn_date_month": "bank_date_month",
    "bank_transactions.bank_text_fields_array": "bank_text_fields_array",
    "bank_transactions.raw_payload_object": "bank_raw_payload_object",
    "workbench_pair_relations.version": "relation_version",
    "workbench_pair_relations.month_scope": "relation_month_scope",
    "workbench_pair_relations.row_ids_nonempty": "relation_row_ids_nonempty",
    "workbench_pair_relations.row_ids_no_blank": "relation_row_ids_no_blank",
    "workbench_pair_relations.row_types_no_blank": "relation_row_types_no_blank",
    "workbench_pair_relations.row_cardinality": "relation_row_cardinality",
    "workbench_pair_relations.amount_check_object": "relation_amount_check_object",
    "workbench_pair_relations.special_metadata_object": "relation_special_metadata_object",
    "workbench_pair_relations.source_versions_object": "relation_source_versions_object",
    "workbench_pair_relations.raw_payload_object": "relation_raw_payload_object",
    "background_jobs.affected_months": "background_affected_months",
    "background_jobs.progress_object": "background_progress_object",
    "background_jobs.result_summary_object": "background_result_summary_object",
    "background_jobs.attention_object": "background_attention_object",
    "background_jobs.raw_payload_object": "background_raw_payload_object",
    "outbox_events.attempts_nonnegative": "outbox_attempts_nonnegative",
    "outbox_events.attempt_count_mirror": "outbox_attempt_count_mirror",
    "outbox_events.event_type_nonempty": "outbox_event_type_nonempty",
    "outbox_events.tenant_id_nonempty": "outbox_tenant_id_nonempty",
    "outbox_events.payload_object": "outbox_payload_object",
    "outbox_events.raw_payload_object": "outbox_raw_payload_object",
    "outbox_events.runtime_lock_pair": "outbox_runtime_lock_pair",
    "outbox_events.processing_lock_required": "outbox_processing_lock_required",
    "outbox_events.terminal_processed_at": "outbox_terminal_processed_at",
    "outbox_events.dead_letter_timestamp": "outbox_dead_letter_timestamp",
}


_AUDIT_SQL = """
with invoice_counts as (
    select
        count(*) filter (
            where (invoice_date is null and invoice_month is not null)
               or (
                    invoice_date is not null
                    and invoice_month is distinct from date_trunc('month', invoice_date)::date
               )
        )::bigint as invoice_date_month,
        count(*) filter (
            where jsonb_typeof(source_links) is distinct from 'array'
        )::bigint as invoice_source_links_array,
        count(*) filter (
            where jsonb_typeof(raw_payload) is distinct from 'object'
        )::bigint as invoice_raw_payload_object
    from app.invoices
),
bank_counts as (
    select
        count(*) filter (
            where txn_direction is null or txn_direction not in ('inflow', 'outflow')
        )::bigint as bank_direction,
        count(*) filter (
            where (txn_date is null and txn_month is not null)
               or (
                    txn_date is not null
                    and txn_month is distinct from date_trunc('month', txn_date)::date
               )
        )::bigint as bank_date_month,
        count(*) filter (
            where jsonb_typeof(bank_text_fields) is distinct from 'array'
        )::bigint as bank_text_fields_array,
        count(*) filter (
            where jsonb_typeof(raw_payload) is distinct from 'object'
        )::bigint as bank_raw_payload_object
    from app.bank_transactions
),
relation_counts as (
    select
        count(*) filter (
            where version is null or version < 1
        )::bigint as relation_version,
        count(*) filter (
            where month_scope is not null
              and month_scope <> date_trunc('month', month_scope)::date
        )::bigint as relation_month_scope,
        count(*) filter (
            where coalesce(cardinality(row_ids), 0) = 0
        )::bigint as relation_row_ids_nonempty,
        count(*) filter (
            where exists (
                select 1
                from unnest(coalesce(row_ids, array[]::text[])) as ids(value)
                where value is null or value ~ '^[[:space:]]*$'
            )
        )::bigint as relation_row_ids_no_blank,
        count(*) filter (
            where exists (
                select 1
                from unnest(coalesce(row_types, array[]::text[])) as types(value)
                where value is null or value ~ '^[[:space:]]*$'
            )
        )::bigint as relation_row_types_no_blank,
        count(*) filter (
            where cardinality(row_ids) is distinct from cardinality(row_types)
        )::bigint as relation_row_cardinality,
        count(*) filter (
            where jsonb_typeof(amount_check) is distinct from 'object'
        )::bigint as relation_amount_check_object,
        count(*) filter (
            where jsonb_typeof(special_metadata) is distinct from 'object'
        )::bigint as relation_special_metadata_object,
        count(*) filter (
            where jsonb_typeof(source_versions) is distinct from 'object'
        )::bigint as relation_source_versions_object,
        count(*) filter (
            where jsonb_typeof(raw_payload) is distinct from 'object'
        )::bigint as relation_raw_payload_object
    from app.workbench_pair_relations
),
background_job_counts as (
    select
        count(*) filter (
            where exists (
                select 1
                from unnest(coalesce(affected_months, array[]::text[])) as months(value)
                where value is null or value !~ '^[0-9]{4}-(0[1-9]|1[0-2])$'
            )
        )::bigint as background_affected_months,
        count(*) filter (
            where jsonb_typeof(progress) is distinct from 'object'
        )::bigint as background_progress_object,
        count(*) filter (
            where jsonb_typeof(result_summary) is distinct from 'object'
        )::bigint as background_result_summary_object,
        count(*) filter (
            where jsonb_typeof(attention) is distinct from 'object'
        )::bigint as background_attention_object,
        count(*) filter (
            where jsonb_typeof(raw_payload) is distinct from 'object'
        )::bigint as background_raw_payload_object
    from job.background_jobs
),
outbox_counts as (
    select
        count(*) filter (where attempts < 0)::bigint
            as outbox_attempts_nonnegative,
        count(*) filter (where attempt_count is distinct from attempts)::bigint
            as outbox_attempt_count_mirror,
        count(*) filter (where btrim(event_type) = '')::bigint
            as outbox_event_type_nonempty,
        count(*) filter (where btrim(tenant_id) = '')::bigint
            as outbox_tenant_id_nonempty,
        count(*) filter (where jsonb_typeof(payload) is distinct from 'object')::bigint
            as outbox_payload_object,
        count(*) filter (where jsonb_typeof(raw_payload) is distinct from 'object')::bigint
            as outbox_raw_payload_object,
        count(*) filter (
            where (locked_by is null) <> (locked_at is null)
        )::bigint as outbox_runtime_lock_pair,
        count(*) filter (
            where status = 'processing'
              and (locked_by is null or locked_at is null)
        )::bigint as outbox_processing_lock_required,
        count(*) filter (
            where status in ('done', 'failed', 'dead_lettered')
              and processed_at is null
        )::bigint as outbox_terminal_processed_at,
        count(*) filter (
            where status = 'dead_lettered'
              and dead_lettered_at is null
        )::bigint as outbox_dead_letter_timestamp
    from job.outbox_events
)
select *
from invoice_counts, bank_counts, relation_counts, background_job_counts, outbox_counts
"""


def audit_domain_contracts(connection: Any) -> dict[str, Any]:
    _assert_read_only(connection)
    row = connection.fetch_one(_AUDIT_SQL)
    if row is None:
        raise RuntimeError("domain contract audit query returned no aggregate row")
    counts = _contract_counts(row)
    blocking_issue_count = sum(counts.values())
    return {
        "status": "pass" if blocking_issue_count == 0 else "issues_found",
        "read_only": True,
        "summary": {"blocking_issue_count": blocking_issue_count},
        "contracts": counts,
    }


def _assert_read_only(connection: Any) -> None:
    row = connection.fetch_one(
        "select current_setting('transaction_read_only') as transaction_read_only"
    )
    if row is None or row.get("transaction_read_only") != "on":
        raise RuntimeError("domain contract audit connection is not read-only")


def _contract_counts(row: Mapping[str, Any]) -> dict[str, int]:
    return {
        contract: int(row.get(column) or 0)
        for contract, column in _CONTRACT_COLUMNS.items()
    }


def _connection_from_env() -> PostgresConnection:
    # Migration safety must observe the primary that activation will mutate;
    # a lagging read replica can incorrectly report zero violations.
    settings = PostgresSettings.from_env()
    connection = PostgresConnection(_force_read_only(settings))
    connection.set_statement_timeout_ms(60_000)
    return connection


def _force_read_only(settings: PostgresSettings) -> PostgresSettings:
    parsed = urlsplit(settings.database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise PostgresConfigurationError("domain contract audit requires a PostgreSQL URL.")
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    options = query.get("options", "").strip()
    read_only_option = "-c default_transaction_read_only=on"
    if read_only_option not in options:
        query["options"] = f"{options} {read_only_option}".strip()
    database_url = urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query, quote_via=quote),
            parsed.fragment,
        )
    )
    return replace(settings, database_url=database_url)


def main(
    argv: Sequence[str] | None = None,
    *,
    connection: Any | None = None,
    stdout: TextIO | None = None,
) -> int:
    if argv:
        raise SystemExit("domain_contract_audit accepts no arguments")
    stdout = stdout or sys.stdout
    try:
        active_connection = connection or _connection_from_env()
    except PostgresConfigurationError as exc:
        report = postgres_configuration_missing_report(
            tool="domain_contract_audit",
            message=str(exc),
        )
        report["required_env"] = [
            "FIN_OPS_POSTGRES_DATABASE_URL",
            "DATABASE_URL",
        ]
        report["read_only"] = True
        report["summary"] = {"blocking_issue_count": 0}
        report["contracts"] = {}
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
        return 2
    report = audit_domain_contracts(active_connection)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0 if report["summary"]["blocking_issue_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
