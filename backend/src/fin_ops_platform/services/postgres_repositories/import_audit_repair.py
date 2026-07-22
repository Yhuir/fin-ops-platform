from __future__ import annotations

import json
from typing import Any

from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository


def load_import_audit_repair_snapshot(
    connection: Any,
    *,
    lifecycle_batch_id: str | None = None,
    lifecycle_file_id: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    snapshot = {
        "bank_files": connection.fetch_all(_BANK_FILE_SQL),
        "bank_transactions": connection.fetch_all(_BANK_TRANSACTION_SQL),
        "bank_rows": connection.fetch_all(_BANK_ROW_SQL),
        "invoice_rows": connection.fetch_all(_INVOICE_ROW_SQL),
    }
    if not lifecycle_batch_id or not lifecycle_file_id:
        return snapshot
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
         rows.data_fingerprint, rows.linked_object_type, rows.linked_object_id
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
