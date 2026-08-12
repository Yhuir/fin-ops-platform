from __future__ import annotations

import json
from typing import Any

from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository


def load_invoice_header_fact_repair_snapshot(
    connection: Any,
    *,
    digital_invoice_numbers: list[str],
) -> list[dict[str, Any]]:
    return connection.fetch_all(
        """
        select coalesce(legacy_mongo_id, id::text) as invoice_id,
               invoice_type, digital_invoice_no, to_char(invoice_month, 'YYYY-MM') as invoice_month,
               amount, signed_amount, tax_amount, total_with_tax, tax_rate, raw_payload
        from app.invoices
        where digital_invoice_no = any(%s::text[])
        order by digital_invoice_no, id
        """,
        (digital_invoice_numbers,),
    )


def load_import_audit_repair_snapshot(
    connection: Any,
    *,
    lifecycle_batch_id: str | None = None,
    lifecycle_file_id: str | None = None,
    etc_deleted_task_session_ids: list[str] | None = None,
    reverted_batch_ids: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    requested_reverted_batch_ids = sorted(
        {str(value or "").strip() for value in reverted_batch_ids or [] if str(value or "").strip()}
    )
    if requested_reverted_batch_ids:
        return {
            "bank_files": [],
            "bank_transactions": [],
            "bank_rows": [],
            "invoice_rows": [],
            "reverted_batch_normalization_requested": [
                {"batch_id": batch_id} for batch_id in requested_reverted_batch_ids
            ],
            "reverted_batch_normalization_targets": connection.fetch_all(
                _REVERTED_BATCH_NORMALIZATION_TARGET_SQL,
                (requested_reverted_batch_ids,),
            ),
        }
    requested_session_ids = sorted(
        {
            str(value or "").strip()
            for value in etc_deleted_task_session_ids or []
            if str(value or "").strip()
        }
    )
    if requested_session_ids:
        return {
            "bank_files": [],
            "bank_transactions": [],
            "bank_rows": [],
            "invoice_rows": [],
            "etc_session_retirement_requested": [
                {"session_id": session_id} for session_id in requested_session_ids
            ],
            "etc_session_retirement_targets": connection.fetch_all(
                _ETC_SESSION_RETIREMENT_TARGET_SQL,
                (requested_session_ids,),
            ),
        }
    snapshot = {
        "bank_files": connection.fetch_all(_BANK_FILE_SQL),
        "bank_transactions": connection.fetch_all(_BANK_TRANSACTION_SQL),
        "bank_rows": connection.fetch_all(_BANK_ROW_SQL),
        "invoice_rows": connection.fetch_all(_INVOICE_ROW_SQL),
    }
    if lifecycle_batch_id and lifecycle_file_id:
        targets = connection.fetch_all(_LIFECYCLE_TARGET_SQL, (lifecycle_batch_id, lifecycle_file_id))
        session_id = str(targets[0].get("session_id") or "").strip() if len(targets) == 1 else ""
        snapshot.update(
            {
                "lifecycle_requested": [{"batch_id": lifecycle_batch_id, "file_id": lifecycle_file_id}],
                "lifecycle_targets": targets,
                "lifecycle_jobs": connection.fetch_all(_LIFECYCLE_JOB_SQL, (session_id, lifecycle_file_id)),
                "lifecycle_row_evidence": connection.fetch_all(_LIFECYCLE_ROW_EVIDENCE_SQL, (lifecycle_batch_id,)),
                "lifecycle_row_links": connection.fetch_all(_LIFECYCLE_ROW_LINK_SQL, (lifecycle_batch_id,)),
            }
        )
    return snapshot


def load_failed_import_job_recovery_snapshot(
    connection: Any,
    *,
    import_job_id: str,
    event_id: str,
    background_job_id: str,
    session_id: str,
    file_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    normalized_file_ids = sorted({str(value or "").strip() for value in file_ids if str(value or "").strip()})
    return {
        "recovery_requested": [
            {
                "import_job_id": str(import_job_id or "").strip(),
                "event_id": str(event_id or "").strip(),
                "background_job_id": str(background_job_id or "").strip(),
                "session_id": str(session_id or "").strip(),
                "file_ids": normalized_file_ids,
            }
        ],
        "import_jobs": connection.fetch_all(_FAILED_IMPORT_JOB_SQL, (import_job_id,)),
        "events": connection.fetch_all(_FAILED_IMPORT_EVENT_SQL, (event_id,)),
        "background_jobs": connection.fetch_all(_FAILED_BACKGROUND_JOB_SQL, (background_job_id,)),
        "files": connection.fetch_all(_FAILED_IMPORT_FILE_SQL, (normalized_file_ids,)),
    }


def discover_failed_import_job_recovery_snapshot(
    connection: Any,
    *,
    import_job_id: str,
) -> dict[str, list[dict[str, Any]]]:
    import_jobs = connection.fetch_all(_FAILED_IMPORT_JOB_SQL, (import_job_id,))
    job_payload = (
        dict(import_jobs[0].get("payload") or {})
        if len(import_jobs) == 1 and isinstance(import_jobs[0].get("payload"), dict)
        else {}
    )
    event_rows = connection.fetch_all(_FAILED_IMPORT_EVENTS_FOR_JOB_SQL, (import_job_id,))
    event_id = str(event_rows[0].get("event_id") or "").strip() if len(event_rows) == 1 else ""
    background_job_id = str(job_payload.get("background_job_id") or "").strip()
    session_id = str(job_payload.get("session_id") or "").strip()
    file_ids = sorted(
        {
            str(value or "").strip()
            for value in job_payload.get("selected_file_ids") or []
            if str(value or "").strip()
        }
    )
    return {
        "recovery_requested": [
            {
                "import_job_id": str(import_job_id or "").strip(),
                "event_id": event_id,
                "background_job_id": background_job_id,
                "session_id": session_id,
                "file_ids": file_ids,
            }
        ],
        "import_jobs": import_jobs,
        "events": event_rows,
        "background_jobs": (
            connection.fetch_all(_FAILED_BACKGROUND_JOB_SQL, (background_job_id,))
            if background_job_id
            else []
        ),
        "files": connection.fetch_all(_FAILED_IMPORT_FILE_SQL, (file_ids,)) if file_ids else [],
    }


def apply_import_audit_repair(connection: Any, plan: dict[str, Any]) -> None:
    for row in list(plan.get("bank_rows") or []):
        affected = connection.execute(
            _BANK_ROW_UPSERT_SQL,
            (
                row["row_id"],
                row["batch_id"],
                row["batch_id"],
                row["batch_id"],
                row["row_no"],
                row["source_unique_key"],
                row.get("data_fingerprint"),
                row["decision"],
                row["decision_reason"],
                row.get("linked_object_id"),
                row.get("identity_kind"),
                row.get("account_no"),
                row.get("trade_time"),
                row.get("direction"),
                row.get("amount"),
                row.get("counterparty_name"),
                json.dumps({"normalized_payload": row["raw_payload"]}, ensure_ascii=False, default=str),
            ),
        )
        if affected == 0:
            raise RuntimeError(f"Import row {row['row_id']} is owned by another batch.")
    PostgresCoreRepository(connection).repair_imported_invoice_totals(
        connection,
        list(plan.get("invoice_updates") or []),
    )
    for repair in list(plan.get("lifecycle_repairs") or []):
        batch_id = str(repair["batch_id"])
        file_id = str(repair["file_id"])
        row_links = list(repair.get("row_links") or [])
        if row_links:
            affected = connection.execute(
                _LIFECYCLE_ROW_LINK_UPDATE_SQL,
                (json.dumps(row_links, ensure_ascii=False), batch_id),
            )
            if affected != len(row_links):
                raise RuntimeError(f"Import batch {batch_id} row-link precondition changed.")
        if connection.execute(_LIFECYCLE_BATCH_UPDATE_SQL, (batch_id,)) != 1:
            raise RuntimeError(f"Import batch {batch_id} lifecycle precondition changed.")
        if connection.execute(_LIFECYCLE_FILE_UPDATE_SQL, (batch_id, file_id, batch_id)) != 1:
            raise RuntimeError(f"Import file {file_id} lifecycle precondition changed.")
    for repair in list(plan.get("etc_session_retirements") or []):
        affected = connection.execute(
            _ETC_SESSION_RETIREMENT_UPDATE_SQL,
            (
                repair["after_revision"],
                repair["session_id"],
                repair["task_id"],
                repair["session_status"],
            ),
        )
        if affected != 1:
            raise RuntimeError(f"ETC import session {repair['session_id']} retirement precondition changed.")
    for repair in list(plan.get("reverted_batch_normalizations") or []):
        if connection.execute(_REVERTED_BATCH_NORMALIZATION_UPDATE_SQL, (repair["batch_id"],)) != 1:
            raise RuntimeError(
                f"Reverted import batch {repair['batch_id']} normalization precondition changed."
            )


_BANK_FILE_SQL = """
select coalesce(file.legacy_mongo_id, file.id::text) as file_id,
       coalesce(
           file.raw_payload->'normalized_payload'->>'batch_id',
           file.raw_payload->'normalized_payload'->>'preview_batch_id'
       ) as batch_id,
       file.raw_payload,
       batch.row_count, batch.success_count, batch.error_count, batch.duplicate_count,
       batch.suspected_duplicate_count, batch.updated_count
from app.import_files file
join app.import_batches batch
  on coalesce(batch.legacy_mongo_id, batch.id::text) = coalesce(
      file.raw_payload->'normalized_payload'->>'batch_id',
      file.raw_payload->'normalized_payload'->>'preview_batch_id'
  )
where file.audit_contract_revision = 'import-page-audit.v1'
  and file.raw_payload->'normalized_payload'->>'batch_type' = 'bank_transaction'
  and file.status = 'confirmed'
order by batch_id, file_id
"""


_FAILED_IMPORT_JOB_SQL = """
select id::text as import_job_id,
       tenant_id, import_type, import_session_id, source_file_id,
       idempotency_key, request_fingerprint, status, stage, priority,
       attempt_count, max_attempts, last_error, payload, result_payload,
       raw_payload, created_by, trace_id
from job.import_jobs
where id = %s
"""


_FAILED_IMPORT_EVENT_SQL = """
select id::text as event_id,
       tenant_id, event_type, aggregate_type, aggregate_id,
       scope_type, scope_key, dedupe_key, payload, attempts, status,
       schema_version, source_version, priority, trace_id, last_error,
       raw_payload
from job.outbox_events
where id = %s
"""


_FAILED_IMPORT_EVENTS_FOR_JOB_SQL = """
select id::text as event_id,
       tenant_id, event_type, aggregate_type, aggregate_id,
       scope_type, scope_key, dedupe_key, payload, attempts, status,
       schema_version, source_version, priority, trace_id, last_error,
       raw_payload
from job.outbox_events
where event_type = 'import.process.requested'
  and aggregate_type = 'import_job'
  and aggregate_id = %s
  and status = 'dead_lettered'
order by created_at, id
"""


_FAILED_BACKGROUND_JOB_SQL = """
select job_id, job_type, status, owner_id, raw_payload
from job.background_jobs
where job_id = %s
"""


_FAILED_IMPORT_FILE_SQL = """
select coalesce(file.legacy_mongo_id, file.id::text) as file_id,
       file.session_id,
       file.status as file_status,
       coalesce(
           file.raw_payload->'normalized_payload'->>'status',
           file.raw_payload->>'status'
       ) as file_payload_status,
       coalesce(
           file.raw_payload->'normalized_payload'->>'session_status',
           file.raw_payload->>'session_status'
       ) as session_status,
       coalesce(
           file.raw_payload->'normalized_payload'->>'batch_type',
           file.raw_payload->>'batch_type'
       ) as batch_type,
       coalesce(
           file.raw_payload->'normalized_payload'->>'preview_batch_id',
           file.raw_payload->>'preview_batch_id'
       ) as preview_batch_id,
       coalesce(
           file.raw_payload->'normalized_payload'->>'batch_id',
           file.raw_payload->>'batch_id'
       ) as batch_id,
       batch.status as batch_status,
       batch.row_count,
       batch.success_count,
       batch.error_count,
       batch.duplicate_count,
       batch.suspected_duplicate_count,
       batch.updated_count,
       (
           select count(*)
           from app.bank_transactions bank_transaction
           where bank_transaction.legacy_source_batch_id = coalesce(
               nullif(file.raw_payload->'normalized_payload'->>'batch_id', ''),
               nullif(file.raw_payload->>'batch_id', ''),
               file.raw_payload->'normalized_payload'->>'preview_batch_id',
               file.raw_payload->>'preview_batch_id'
           )
             and bank_transaction.status <> 'deleted'
       ) as canonical_bank_transaction_count,
       coalesce(row_audit.issue_count, 0) + coalesce(owner_audit.issue_count, 0)
           as canonical_audit_issue_count
from app.import_files file
left join app.import_batches batch
  on coalesce(batch.legacy_mongo_id, batch.id::text) = coalesce(
      nullif(file.raw_payload->'normalized_payload'->>'batch_id', ''),
      nullif(file.raw_payload->>'batch_id', ''),
      file.raw_payload->'normalized_payload'->>'preview_batch_id',
      file.raw_payload->>'preview_batch_id'
  )
left join lateral (
    select count(*) filter (
        where (
            rows.decision in ('created', 'duplicate_skipped')
            and (
                rows.linked_object_type <> 'bank_transaction'
                or bank_transaction.id is null
                or nullif(trim(rows.account_no), '') is distinct from nullif(trim(bank_transaction.account_no), '')
                or date_trunc('second', rows.trade_time) is distinct from date_trunc('second', bank_transaction.trade_time)
                or nullif(trim(rows.direction), '') is distinct from nullif(trim(bank_transaction.txn_direction), '')
                or rows.amount is distinct from bank_transaction.amount
                or nullif(trim(rows.counterparty_name), '')
                    is distinct from nullif(trim(bank_transaction.counterparty_name_raw), '')
                or not (
                    (
                        nullif(trim(rows.source_unique_key), '')
                            is not distinct from nullif(trim(bank_transaction.source_unique_key), '')
                        and nullif(trim(rows.data_fingerprint), '')
                            is not distinct from nullif(trim(bank_transaction.data_fingerprint), '')
                    )
                    or (
                        nullif(trim(rows.data_fingerprint), '') is not null
                        and rows.data_fingerprint = bank_transaction.data_fingerprint
                        and array_remove(
                            array[
                                upper(regexp_replace(coalesce(
                                    rows.raw_payload->'normalized_payload'->'normalized_row'->>'account_detail_no',
                                    rows.raw_payload->'normalized_payload'->>'account_detail_no',
                                    ''
                                ), '\\s+', '', 'g')),
                                upper(regexp_replace(coalesce(
                                    rows.raw_payload->'normalized_payload'->'normalized_row'->>'bank_serial_no',
                                    rows.raw_payload->'normalized_payload'->>'bank_serial_no',
                                    ''
                                ), '\\s+', '', 'g')),
                                upper(regexp_replace(coalesce(
                                    rows.raw_payload->'normalized_payload'->'normalized_row'->>'enterprise_serial_no',
                                    rows.raw_payload->'normalized_payload'->>'enterprise_serial_no',
                                    ''
                                ), '\\s+', '', 'g'))
                            ]::text[],
                            ''
                        ) && array_remove(
                            array[
                                upper(regexp_replace(coalesce(
                                    bank_transaction.raw_payload->'normalized_payload'->>'account_detail_no',
                                    bank_transaction.raw_payload->>'account_detail_no',
                                    ''
                                ), '\\s+', '', 'g')),
                                upper(regexp_replace(coalesce(
                                    bank_transaction.bank_serial_no,
                                    bank_transaction.raw_payload->'normalized_payload'->>'bank_serial_no',
                                    bank_transaction.raw_payload->>'bank_serial_no',
                                    ''
                                ), '\\s+', '', 'g')),
                                upper(regexp_replace(coalesce(
                                    bank_transaction.raw_payload->'normalized_payload'->>'enterprise_serial_no',
                                    bank_transaction.raw_payload->>'enterprise_serial_no',
                                    ''
                                ), '\\s+', '', 'g'))
                            ]::text[],
                            ''
                        )
                    )
                    or (
                        nullif(trim(rows.data_fingerprint), '') is null
                        and coalesce(rows.source_unique_key, '') like 'bank:%%'
                        and rows.source_unique_key = bank_transaction.data_fingerprint
                        and (
                            nullif(trim(bank_transaction.source_unique_key), '') is null
                            or bank_transaction.source_unique_key like 'bank-v2:%%'
                            or bank_transaction.source_unique_key like 'bank-v3:%%'
                        )
                    )
                )
                or (
                    rows.decision = 'created'
                    and bank_transaction.legacy_source_batch_id
                        is distinct from coalesce(batch.legacy_mongo_id, batch.id::text)
                )
            )
        )
        or (
            rows.decision not in ('created', 'duplicate_skipped')
            and (
                nullif(trim(rows.linked_object_type), '') is not null
                or nullif(trim(rows.linked_object_id), '') is not null
            )
        )
    )::bigint as issue_count
    from app.import_batch_rows rows
    left join app.bank_transactions bank_transaction
      on coalesce(bank_transaction.legacy_mongo_id, bank_transaction.id::text) = rows.linked_object_id
     and bank_transaction.status <> 'deleted'
    where rows.import_batch_id = batch.id
) row_audit on true
left join lateral (
    select count(*) filter (where owned.created_row_count <> 1)::bigint as issue_count
    from (
        select bank_transaction.id,
               count(rows.id) filter (where rows.decision = 'created')::bigint as created_row_count
        from app.bank_transactions bank_transaction
        left join app.import_batch_rows rows
          on rows.import_batch_id = batch.id
         and rows.linked_object_type = 'bank_transaction'
         and rows.linked_object_id = coalesce(bank_transaction.legacy_mongo_id, bank_transaction.id::text)
        where bank_transaction.legacy_source_batch_id = coalesce(batch.legacy_mongo_id, batch.id::text)
          and bank_transaction.status <> 'deleted'
        group by bank_transaction.id
    ) owned
) owner_audit on true
where coalesce(file.legacy_mongo_id, file.id::text) = any(%s)
order by file_id
"""

_BANK_TRANSACTION_SQL = """
select coalesce(legacy_mongo_id, id::text) as transaction_id,
       source_unique_key, data_fingerprint, legacy_source_batch_id as source_batch_id
from app.bank_transactions
where status <> 'deleted'
  and nullif(source_unique_key, '') is not null
order by transaction_id
"""

_BANK_ROW_SQL = """
with strict_batches as (
    select distinct coalesce(
        file.raw_payload->'normalized_payload'->>'batch_id',
        file.raw_payload->'normalized_payload'->>'preview_batch_id'
    ) as batch_id
    from app.import_files file
    where file.audit_contract_revision = 'import-page-audit.v1'
      and file.raw_payload->'normalized_payload'->>'batch_type' = 'bank_transaction'
      and file.status = 'confirmed'
)
select coalesce(rows.legacy_mongo_id, rows.id::text) as row_id,
       coalesce(rows.legacy_batch_id, batch.legacy_mongo_id, batch.id::text) as batch_id,
       rows.row_no, rows.source_unique_key, rows.data_fingerprint, rows.decision,
       rows.linked_object_id, rows.identity_kind, rows.account_no, rows.trade_time,
       rows.direction, rows.amount, rows.counterparty_name
from app.import_batch_rows rows
join app.import_batches batch on batch.id = rows.import_batch_id
join strict_batches strict
  on strict.batch_id = coalesce(rows.legacy_batch_id, batch.legacy_mongo_id, batch.id::text)
where rows.source_record_type = 'bank_transaction'
order by batch_id, rows.row_no, row_id
"""

_INVOICE_ROW_SQL = """
with strict_batches as (
    select distinct coalesce(
        file.raw_payload->'normalized_payload'->>'batch_id',
        file.raw_payload->'normalized_payload'->>'preview_batch_id'
    ) as batch_id
    from app.import_files file
    where file.audit_contract_revision = 'import-page-audit.v1'
      and file.raw_payload->'normalized_payload'->>'batch_type' in ('input_invoice', 'output_invoice')
      and file.status = 'confirmed'
)
select coalesce(rows.legacy_batch_id, batch.legacy_mongo_id, batch.id::text) as batch_id,
       coalesce(rows.legacy_mongo_id, rows.id::text) as row_id,
       rows.row_no, rows.source_unique_key, rows.decision, rows.linked_object_id,
       rows.raw_payload as row_raw_payload,
       coalesce(invoice.legacy_mongo_id, invoice.id::text) as invoice_id,
       invoice.legacy_source_batch_id as invoice_source_batch_id,
       to_char(invoice.invoice_date, 'YYYY-MM') as invoice_month,
       invoice.amount, invoice.signed_amount, invoice.tax_amount, invoice.total_with_tax,
       invoice.tax_rate, invoice.raw_payload as invoice_raw_payload
from app.import_batch_rows rows
join app.import_batches batch on batch.id = rows.import_batch_id
join strict_batches strict
  on strict.batch_id = coalesce(rows.legacy_batch_id, batch.legacy_mongo_id, batch.id::text)
left join app.invoices invoice
  on coalesce(invoice.legacy_mongo_id, invoice.id::text) = rows.linked_object_id
where rows.source_record_type = 'invoice'
order by batch_id, invoice_id, rows.row_no
"""

_BANK_ROW_UPSERT_SQL = """
insert into app.import_batch_rows(
    legacy_mongo_id, import_batch_id, legacy_batch_id, row_no, source_record_type,
    source_unique_key, data_fingerprint, decision, decision_reason,
    linked_object_type, linked_object_id, identity_kind, account_no, trade_time,
    direction, amount, counterparty_name, raw_payload
)
values (
    %s,
    (select id from app.import_batches where legacy_mongo_id = %s or id::text = %s limit 1),
    %s, %s, 'bank_transaction', %s, %s, %s, %s, 'bank_transaction', %s, %s, %s,
    %s::timestamptz, %s, %s, %s, %s::jsonb
)
on conflict (legacy_mongo_id) do update set
    import_batch_id = excluded.import_batch_id,
    legacy_batch_id = excluded.legacy_batch_id,
    row_no = excluded.row_no,
    source_record_type = excluded.source_record_type,
    source_unique_key = excluded.source_unique_key,
    data_fingerprint = excluded.data_fingerprint,
    decision = excluded.decision,
    decision_reason = excluded.decision_reason,
    linked_object_type = excluded.linked_object_type,
    linked_object_id = excluded.linked_object_id,
    identity_kind = excluded.identity_kind,
    account_no = excluded.account_no,
    trade_time = excluded.trade_time,
    direction = excluded.direction,
    amount = excluded.amount,
    counterparty_name = excluded.counterparty_name,
    raw_payload = excluded.raw_payload
where app.import_batch_rows.legacy_batch_id = excluded.legacy_batch_id
"""

_LIFECYCLE_TARGET_SQL = """
select coalesce(batch.legacy_mongo_id, batch.id::text) as batch_id,
       batch.batch_type, batch.status as batch_status,
       batch.row_count, batch.success_count, batch.error_count, batch.duplicate_count,
       batch.suspected_duplicate_count, batch.updated_count,
       batch.raw_payload as batch_raw_payload,
       coalesce(file.legacy_mongo_id, file.id::text) as file_id,
       file.session_id, file.status as file_status, file.raw_payload as file_raw_payload
from app.import_batches batch
cross join app.import_files file
where coalesce(batch.legacy_mongo_id, batch.id::text) = %s
  and coalesce(file.legacy_mongo_id, file.id::text) = %s
"""

_LIFECYCLE_JOB_SQL = """
select id::text as job_id, import_session_id, source_file_id, status, stage,
       attempt_count, max_attempts, last_error, payload, result_payload
from job.import_jobs
where import_type = 'file_import.confirm'
  and coalesce(import_session_id, payload->>'session_id') = %s
  and coalesce(payload->'selected_file_ids', '[]'::jsonb) ? %s
order by created_at, id
"""

_LIFECYCLE_ROW_EVIDENCE_SQL = """
with target_batch as (
    select id, coalesce(legacy_mongo_id, id::text) as batch_id
    from app.import_batches
    where coalesce(legacy_mongo_id, id::text) = %s
), target_rows as (
    select rows.*, target.batch_id
    from app.import_batch_rows rows
    join target_batch target on target.id = rows.import_batch_id
)
select count(*)::bigint as row_count,
       count(*) filter (where decision = 'created')::bigint as created_count,
       count(*) filter (where decision = 'status_updated')::bigint as status_updated_count,
       count(*) filter (where decision = 'error')::bigint as error_count,
       count(*) filter (where decision = 'duplicate_skipped')::bigint as duplicate_count,
       count(*) filter (where decision = 'suspected_duplicate')::bigint as suspected_duplicate_count
from target_rows
"""

_LIFECYCLE_ROW_LINK_SQL = """
with target_batch as (
    select id, coalesce(legacy_mongo_id, id::text) as batch_id
    from app.import_batches
    where coalesce(legacy_mongo_id, id::text) = %s
), target_rows as (
    select rows.*, target.batch_id
    from app.import_batch_rows rows
    join target_batch target on target.id = rows.import_batch_id
)
select coalesce(rows.legacy_mongo_id, rows.id::text) as row_id,
       rows.decision,
       coalesce(nullif(rows.source_unique_key, ''), nullif(rows.data_fingerprint, '')) as source_id,
       rows.linked_object_type,
       rows.linked_object_id,
       count(candidate.invoice_id)::bigint as candidate_count,
       min(candidate.invoice_id) as candidate_invoice_id,
       coalesce(bool_or(candidate.is_batch_owner), false) as candidate_is_batch_owner
from target_rows rows
left join lateral (
    select distinct coalesce(invoice.legacy_mongo_id, invoice.id::text) as invoice_id,
           (
               invoice.source_batch_id = rows.import_batch_id
               or invoice.legacy_source_batch_id = rows.batch_id
           ) as is_batch_owner
    from app.invoices invoice
    cross join lateral jsonb_array_elements(coalesce(invoice.source_links, '[]'::jsonb)) source_link
    where source_link->>'source_type' = 'manual_invoice_import'
      and source_link->>'batch_id' = rows.batch_id
      and source_link->>'source_id' = coalesce(nullif(rows.source_unique_key, ''), nullif(rows.data_fingerprint, ''))
) candidate on true
group by rows.id, rows.legacy_mongo_id, rows.decision, rows.source_unique_key,
         rows.data_fingerprint, rows.linked_object_type, rows.linked_object_id, rows.row_no
order by rows.row_no, row_id
"""

_LIFECYCLE_ROW_LINK_UPDATE_SQL = """
with repairs as (
    select *
    from jsonb_to_recordset(%s::jsonb) as repair(
        row_id text,
        decision text,
        source_id text,
        linked_object_id text,
        before jsonb
    )
), target_batch as (
    select id
    from app.import_batches
    where coalesce(legacy_mongo_id, id::text) = %s
)
update app.import_batch_rows rows
set linked_object_type = 'invoice',
    linked_object_id = repairs.linked_object_id,
    raw_payload = jsonb_set(
        jsonb_set(rows.raw_payload, '{normalized_payload,linked_object_type}', to_jsonb('invoice'::text), true),
        '{normalized_payload,linked_object_id}', to_jsonb(repairs.linked_object_id), true
    )
from repairs, target_batch
where coalesce(rows.legacy_mongo_id, rows.id::text) = repairs.row_id
  and rows.import_batch_id = target_batch.id
  and rows.decision = repairs.decision
  and coalesce(nullif(rows.source_unique_key, ''), nullif(rows.data_fingerprint, '')) = repairs.source_id
  and nullif(rows.linked_object_type, '') is null
  and nullif(rows.linked_object_id, '') is null
"""

_LIFECYCLE_BATCH_UPDATE_SQL = """
update app.import_batches
set status = 'completed',
    raw_payload = jsonb_set(raw_payload, '{normalized_payload,status}', to_jsonb('completed'::text), true),
    updated_at = now()
where coalesce(legacy_mongo_id, id::text) = %s
  and batch_type in ('input_invoice', 'output_invoice')
  and status = 'pending'
  and raw_payload->'normalized_payload'->>'status' = 'pending'
"""

_LIFECYCLE_FILE_UPDATE_SQL = """
update app.import_files
set status = 'confirmed',
    raw_payload = jsonb_set(
        jsonb_set(
            jsonb_set(raw_payload, '{normalized_payload,status}', to_jsonb('confirmed'::text), true),
            '{normalized_payload,batch_id}', to_jsonb(%s::text), true
        ),
        '{normalized_payload,session_status}', to_jsonb('confirmed'::text), true
    )
where coalesce(legacy_mongo_id, id::text) = %s
  and status = 'preview_ready'
  and raw_payload->'normalized_payload'->>'status' = 'preview_ready'
  and nullif(raw_payload->'normalized_payload'->>'batch_id', '') is null
  and raw_payload->'normalized_payload'->>'preview_batch_id' = %s
  and raw_payload->'normalized_payload'->>'session_status' = 'preview_ready'
"""

_REVERTED_BATCH_NORMALIZATION_TARGET_SQL = """
select coalesce(batch.legacy_mongo_id, batch.id::text) as batch_id,
       batch.batch_type,
       batch.status as batch_status,
       batch.raw_payload as batch_raw_payload,
       file_evidence.file_count,
       file_evidence.strict_reverted_file_count,
       file_evidence.active_or_succeeded_job_count,
       row_evidence.linked_row_count,
       invoice_evidence.canonical_invoice_count
from app.import_batches batch
cross join lateral (
    select count(distinct file.id)::bigint as file_count,
           count(distinct file.id) filter (
               where file.audit_contract_revision = 'import-page-audit.v1'
                 and file.status = 'reverted'
                 and file.raw_payload->'normalized_payload'->>'status' = 'reverted'
                 and file.raw_payload->'normalized_payload'->>'session_status' = 'reverted'
                 and nullif(file.raw_payload->'normalized_payload'->>'batch_id', '') is null
                 and file.raw_payload->'normalized_payload'->>'preview_batch_id'
                     = coalesce(batch.legacy_mongo_id, batch.id::text)
           )::bigint as strict_reverted_file_count,
           count(distinct job.id) filter (
               where job.status in ('pending', 'processing', 'succeeded')
           )::bigint as active_or_succeeded_job_count
    from app.import_files file
    left join job.import_jobs job on job.import_session_id = file.session_id
    where coalesce(
        file.raw_payload->'normalized_payload'->>'batch_id',
        file.raw_payload->'normalized_payload'->>'preview_batch_id'
    ) = coalesce(batch.legacy_mongo_id, batch.id::text)
) file_evidence
cross join lateral (
    select count(*) filter (
        where nullif(rows.linked_object_type, '') is not null
           or nullif(rows.linked_object_id, '') is not null
    )::bigint as linked_row_count
    from app.import_batch_rows rows
    where rows.import_batch_id = batch.id
) row_evidence
cross join lateral (
    select count(*)::bigint as canonical_invoice_count
    from app.invoices invoice
    where invoice.source_batch_id = batch.id
       or invoice.legacy_source_batch_id = coalesce(batch.legacy_mongo_id, batch.id::text)
       or exists (
           select 1
           from jsonb_array_elements(coalesce(invoice.source_links, '[]'::jsonb)) source_link
           where source_link->>'source_type' = 'manual_invoice_import'
             and source_link->>'batch_id' = coalesce(batch.legacy_mongo_id, batch.id::text)
       )
) invoice_evidence
where coalesce(batch.legacy_mongo_id, batch.id::text) = any(%s)
order by batch_id
"""

_REVERTED_BATCH_NORMALIZATION_UPDATE_SQL = """
update app.import_batches batch
set raw_payload = jsonb_set(
        batch.raw_payload,
        '{normalized_payload,status}',
        to_jsonb('reverted'::text),
        true
    ),
    updated_at = now()
where coalesce(batch.legacy_mongo_id, batch.id::text) = %s
  and batch.batch_type in ('input_invoice', 'output_invoice')
  and batch.status = 'reverted'
  and batch.raw_payload->'normalized_payload'->>'status' = 'pending'
"""

_ETC_SESSION_RETIREMENT_TARGET_SQL = """
select session.session_id,
       session.audit_contract_revision,
       session.status as session_status,
       session.task_id,
       task.status as task_status,
       task.raw_payload as task_raw_payload,
       count(distinct job.id) filter (
           where job.status in ('pending', 'processing')
       )::bigint as active_job_count,
       count(distinct event.id) filter (
           where event.status in ('pending', 'processing', 'publishing', 'failed', 'dead_lettered')
       )::bigint as active_outbox_count
from app.etc_import_sessions session
join app.etc_reconciliation_tasks task on task.task_id = session.task_id
left join job.import_jobs job
  on job.import_type = 'etc_invoice_import.confirm'
 and job.import_session_id = session.session_id
left join job.outbox_events event
  on event.event_type = 'import.process.requested'
 and event.aggregate_type = 'import_job'
 and event.aggregate_id = job.id::text
where session.session_id = any(%s)
group by session.session_id, session.audit_contract_revision, session.status,
         session.task_id, task.status, task.raw_payload
order by session.session_id
"""

_ETC_SESSION_RETIREMENT_UPDATE_SQL = """
update app.etc_import_sessions session
set audit_contract_revision = %s,
    updated_at = now()
where session.session_id = %s
  and session.task_id = %s
  and session.status = %s
  and session.audit_contract_revision = 'etc-import-page-audit.v1'
  and exists (
      select 1
      from app.etc_reconciliation_tasks task
      where task.task_id = session.task_id
        and task.status = 'deleted'
        and coalesce(
            task.raw_payload->'normalized_payload'->>'status',
            task.raw_payload->>'status'
        ) = 'deleted'
  )
  and not exists (
      select 1
      from job.import_jobs job
      where job.import_type = 'etc_invoice_import.confirm'
        and job.import_session_id = session.session_id
        and job.status in ('pending', 'processing')
  )
  and not exists (
      select 1
      from job.import_jobs job
      join job.outbox_events event
        on event.event_type = 'import.process.requested'
       and event.aggregate_type = 'import_job'
       and event.aggregate_id = job.id::text
      where job.import_type = 'etc_invoice_import.confirm'
        and job.import_session_id = session.session_id
        and event.status in ('pending', 'processing', 'publishing', 'failed', 'dead_lettered')
  )
"""
