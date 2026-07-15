from __future__ import annotations

import json
from typing import Any

from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository


def load_import_audit_repair_snapshot(connection: Any) -> dict[str, list[dict[str, Any]]]:
    return {
        "bank_files": connection.fetch_all(_BANK_FILE_SQL),
        "bank_transactions": connection.fetch_all(_BANK_TRANSACTION_SQL),
        "bank_rows": connection.fetch_all(_BANK_ROW_SQL),
        "invoice_rows": connection.fetch_all(_INVOICE_ROW_SQL),
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
