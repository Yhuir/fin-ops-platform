from __future__ import annotations

import json
from typing import Any


def load_bank_import_dedup_repair_snapshot(
    connection: Any,
    *,
    source_sessions: list[dict[str, Any]],
    expected_target_count: int,
    expected_protected_count: int,
    expected_replay_create_count: int,
) -> dict[str, Any]:
    session_ids = [str(item["session_id"]) for item in source_sessions]
    file_ids = [str(file_id) for item in source_sessions for file_id in item["file_ids"]]
    files = connection.fetch_all(_SOURCE_FILE_SQL, (session_ids, file_ids))
    batch_pks = sorted({str(row.get("batch_pk") or "") for row in files if row.get("batch_pk")})
    legacy_batch_ids = sorted(
        {str(row.get("batch_id") or "") for row in files if row.get("batch_id")}
    )
    targets = (
        connection.fetch_all(_TARGET_TRANSACTION_SQL, (batch_pks, legacy_batch_ids))
        if batch_pks or legacy_batch_ids
        else []
    )
    target_pks = [str(row["transaction_pk"]) for row in targets]
    return {
        "request": {
            "source_sessions": source_sessions,
            "expected_target_count": expected_target_count,
            "expected_protected_count": expected_protected_count,
            "expected_replay_create_count": expected_replay_create_count,
        },
        "files": files,
        "batches": connection.fetch_all(_BATCH_SQL, (batch_pks,)) if batch_pks else [],
        "target_transactions": targets,
        "protected_transactions": connection.fetch_all(_PROTECTED_TRANSACTION_SQL, (target_pks,)),
        "import_rows": connection.fetch_all(_IMPORT_ROW_SQL, (batch_pks,)) if batch_pks else [],
        "relation_evidence": (
            connection.fetch_all(_RELATION_EVIDENCE_SQL, (target_pks,)) if target_pks else []
        ),
    }


def apply_bank_import_dedup_repair(connection: Any, plan: dict[str, Any]) -> None:
    for update in plan["row_updates"]:
        affected = connection.execute(
            _UPDATE_IMPORT_ROW_SQL,
            (
                update["after_decision_reason"],
                update["after_linked_object_id"],
                json.dumps(update["after_raw_payload"], ensure_ascii=False, default=str),
                update["row_pk"],
                update["batch_pk"],
                update["before_linked_object_id"],
                json.dumps(update["before_raw_payload"], ensure_ascii=False, default=str),
            ),
        )
        if affected != 1:
            raise RuntimeError(f"Import row {update['row_pk']} changed after dry-run.")
    for update in plan["batch_updates"]:
        affected = connection.execute(
            _UPDATE_BATCH_SQL,
            (
                update["after_success_count"],
                update["after_duplicate_count"],
                json.dumps(update["after_raw_payload"], ensure_ascii=False, default=str),
                update["batch_pk"],
                update["before_success_count"],
                update["before_duplicate_count"],
                json.dumps(update["before_raw_payload"], ensure_ascii=False, default=str),
            ),
        )
        if affected != 1:
            raise RuntimeError(f"Import batch {update['batch_pk']} changed after dry-run.")
    for update in plan["file_updates"]:
        affected = connection.execute(
            _UPDATE_FILE_SQL,
            (
                json.dumps(update["after_raw_payload"], ensure_ascii=False, default=str),
                update["file_pk"],
                update["batch_id"],
                json.dumps(update["before_raw_payload"], ensure_ascii=False, default=str),
            ),
        )
        if affected != 1:
            raise RuntimeError(f"Import file {update['file_pk']} changed after dry-run.")
    for pair in plan["duplicate_pairs"]:
        affected = connection.execute(
            _DELETE_TRANSACTION_SQL,
            (
                pair["delete_transaction_pk"],
                pair["delete_batch_pk"],
                pair["delete_legacy_batch_id"],
                pair["delete_source_unique_key"],
            ),
        )
        if affected != 1:
            raise RuntimeError(
                f"Bank transaction {pair['delete_transaction_pk']} changed or gained a relation after dry-run."
            )


_SOURCE_FILE_SQL = """
select file.id::text as file_pk,
       coalesce(file.legacy_mongo_id, file.id::text) as file_id,
       file.session_id, file.status, file.stored_file_path, file.raw_payload,
       coalesce(
           object.sha256,
           file.raw_payload->'normalized_payload'->>'content_sha256',
           file.raw_payload->>'content_sha256'
       ) as content_sha256,
       batch.id::text as batch_pk,
       coalesce(batch.legacy_mongo_id, batch.id::text) as batch_id,
       batch.batch_type, batch.status as batch_status
from app.import_files file
left join app.import_batches batch
  on coalesce(batch.legacy_mongo_id, batch.id::text) = coalesce(
      nullif(file.raw_payload->'normalized_payload'->>'batch_id', ''),
      nullif(file.raw_payload->>'batch_id', ''),
      file.raw_payload->'normalized_payload'->>'preview_batch_id',
      file.raw_payload->>'preview_batch_id'
  )
left join app.file_objects object on object.id = file.file_object_id
where file.session_id = any(%s::text[])
  and coalesce(file.legacy_mongo_id, file.id::text) = any(%s::text[])
order by file.session_id, file_id
"""

_TRANSACTION_FIELDS = """
bt.id::text as transaction_pk,
coalesce(bt.legacy_mongo_id, bt.id::text) as transaction_id,
bt.source_batch_id::text as batch_pk,
bt.legacy_source_batch_id as legacy_batch_id,
bt.account_no, bt.txn_direction, bt.counterparty_name_raw,
bt.normalized_counterparty_name, bt.amount, bt.txn_date,
bt.txn_month, bt.trade_time, bt.pay_receive_time,
bt.bank_serial_no,
coalesce(bt.raw_payload->'normalized_payload'->>'account_detail_no', bt.raw_payload->>'account_detail_no')
    as account_detail_no,
coalesce(bt.raw_payload->'normalized_payload'->>'enterprise_serial_no', bt.raw_payload->>'enterprise_serial_no')
    as enterprise_serial_no,
coalesce(bt.raw_payload->'normalized_payload'->>'voucher_no', bt.raw_payload->>'voucher_no') as voucher_no,
bt.source_unique_key, bt.data_fingerprint,
bt.written_off_amount, bt.status, bt.raw_payload
"""

_TARGET_TRANSACTION_SQL = f"""
select {_TRANSACTION_FIELDS}
from app.bank_transactions bt
where (
        bt.source_batch_id::text = any(%s::text[])
        or bt.legacy_source_batch_id = any(%s::text[])
      )
  and bt.status <> 'deleted'
order by bt.id
"""

_PROTECTED_TRANSACTION_SQL = f"""
select {_TRANSACTION_FIELDS}
from app.bank_transactions bt
where bt.status <> 'deleted'
  and not (bt.id::text = any(%s::text[]))
order by bt.id
"""

_BATCH_SQL = """
select id::text as batch_pk, coalesce(legacy_mongo_id, id::text) as batch_id,
       status, success_count, duplicate_count, raw_payload
from app.import_batches
where id::text = any(%s::text[])
order by id
"""

_IMPORT_ROW_SQL = """
select row.id::text as row_pk, row.import_batch_id::text as batch_pk,
       coalesce(batch.legacy_mongo_id, batch.id::text) as batch_id,
       row.row_no, row.decision, row.linked_object_id, row.raw_payload
from app.import_batch_rows row
join app.import_batches batch on batch.id = row.import_batch_id
where row.import_batch_id::text = any(%s::text[])
order by row.import_batch_id, row.row_no, row.id
"""

_RELATION_EVIDENCE_SQL = """
select bt.id::text as transaction_pk,
       bt.written_off_amount,
       (select count(*) from app.bank_transaction_categories value
        where value.bank_transaction_id = bt.id
           or value.legacy_transaction_id = any(array[bt.legacy_mongo_id, bt.id::text]))
           as category_count,
       (select count(*) from app.bank_transaction_category_events value
        where value.bank_transaction_id = bt.id) as category_event_count,
       (select count(*) from app.bank_transaction_category_confirmations value
        where value.bank_transaction_id = bt.id
           or value.legacy_transaction_id = any(array[bt.legacy_mongo_id, bt.id::text]))
           as category_confirmation_count,
       (select count(*) from app.workbench_pair_relations value
        where value.row_ids && array[bt.legacy_mongo_id, bt.id::text]) as workbench_pair_count,
       (select count(*) from app.workbench_row_overrides value
        where value.row_id = any(array[bt.legacy_mongo_id, bt.id::text])
           or value.changed_row_ids && array[bt.legacy_mongo_id, bt.id::text])
           as workbench_override_count,
       (select count(*) from app.workbench_exception_cases value
        where value.row_ids && array[bt.legacy_mongo_id, bt.id::text]
           or value.candidate_ids && array[bt.legacy_mongo_id, bt.id::text])
           as workbench_exception_count,
       (select count(*) from app.no_oa_bank_batches value
        where value.bank_transaction_ids && array[bt.legacy_mongo_id, bt.id::text])
           as no_oa_batch_count,
       (select count(*) from app.bank_flow_rule_batches value
        where value.bank_transaction_ids && array[bt.legacy_mongo_id, bt.id::text])
           as bank_flow_batch_count,
       (select count(*) from app.matching_results value
        where value.transaction_ids && array[bt.legacy_mongo_id, bt.id::text])
           as matching_result_count,
       (select count(*) from app.turnover_relations value
        where value.bank_transaction_id = any(array[bt.legacy_mongo_id, bt.id::text]))
           as turnover_relation_count,
       (select count(*) from app.oa_pending_payment_bank_relations value
        where value.bank_transaction_ids && array[bt.legacy_mongo_id, bt.id::text])
           as oa_payment_relation_count,
       (select count(*) from app.bank_transaction_relation_claims value
        where value.bank_transaction_id = any(array[bt.legacy_mongo_id, bt.id::text]))
           as relation_claim_count,
       (select count(*) from app.output_invoice_receipts value
        where value.bank_transaction_id = any(array[bt.legacy_mongo_id, bt.id::text]))
           as output_receipt_count
from app.bank_transactions bt
where bt.id::text = any(%s::text[])
order by bt.id
"""

_UPDATE_IMPORT_ROW_SQL = """
update app.import_batch_rows
set decision = 'duplicate_skipped',
    decision_reason = %s,
    linked_object_type = 'bank_transaction',
    linked_object_id = %s,
    raw_payload = %s::jsonb
where id = %s::uuid
  and import_batch_id = %s::uuid
  and decision = 'created'
  and linked_object_id = %s
  and raw_payload = %s::jsonb
"""

_UPDATE_BATCH_SQL = """
update app.import_batches
set success_count = %s,
    duplicate_count = %s,
    raw_payload = %s::jsonb,
    updated_at = now()
where id = %s::uuid
  and status = 'completed'
  and success_count = %s
  and duplicate_count = %s
  and raw_payload = %s::jsonb
"""

_UPDATE_FILE_SQL = """
update app.import_files
set raw_payload = %s::jsonb
where id = %s::uuid
  and coalesce(
      nullif(raw_payload->'normalized_payload'->>'batch_id', ''),
      nullif(raw_payload->>'batch_id', ''),
      raw_payload->'normalized_payload'->>'preview_batch_id',
      raw_payload->>'preview_batch_id'
  ) = %s
  and status = 'confirmed'
  and raw_payload = %s::jsonb
"""

_DELETE_TRANSACTION_SQL = """
delete from app.bank_transactions bt
where bt.id = %s::uuid
  and (
      bt.source_batch_id::text = nullif(%s, '')
      or bt.legacy_source_batch_id = nullif(%s, '')
  )
  and bt.source_unique_key is not distinct from %s
  and bt.status <> 'deleted'
  and bt.written_off_amount = 0
  and not exists (
      select 1 from app.bank_transaction_categories value
      where value.bank_transaction_id = bt.id
         or value.legacy_transaction_id = any(array[bt.legacy_mongo_id, bt.id::text])
  )
  and not exists (select 1 from app.bank_transaction_category_events value where value.bank_transaction_id = bt.id)
  and not exists (
      select 1 from app.bank_transaction_category_confirmations value
      where value.bank_transaction_id = bt.id
         or value.legacy_transaction_id = any(array[bt.legacy_mongo_id, bt.id::text])
  )
  and not exists (select 1 from app.workbench_pair_relations value where value.row_ids && array[bt.legacy_mongo_id, bt.id::text])
  and not exists (select 1 from app.workbench_row_overrides value where value.row_id = any(array[bt.legacy_mongo_id, bt.id::text]) or value.changed_row_ids && array[bt.legacy_mongo_id, bt.id::text])
  and not exists (select 1 from app.workbench_exception_cases value where value.row_ids && array[bt.legacy_mongo_id, bt.id::text] or value.candidate_ids && array[bt.legacy_mongo_id, bt.id::text])
  and not exists (select 1 from app.no_oa_bank_batches value where value.bank_transaction_ids && array[bt.legacy_mongo_id, bt.id::text])
  and not exists (select 1 from app.bank_flow_rule_batches value where value.bank_transaction_ids && array[bt.legacy_mongo_id, bt.id::text])
  and not exists (select 1 from app.matching_results value where value.transaction_ids && array[bt.legacy_mongo_id, bt.id::text])
  and not exists (select 1 from app.turnover_relations value where value.bank_transaction_id = any(array[bt.legacy_mongo_id, bt.id::text]))
  and not exists (select 1 from app.oa_pending_payment_bank_relations value where value.bank_transaction_ids && array[bt.legacy_mongo_id, bt.id::text])
  and not exists (select 1 from app.bank_transaction_relation_claims value where value.bank_transaction_id = any(array[bt.legacy_mongo_id, bt.id::text]))
  and not exists (select 1 from app.output_invoice_receipts value where value.bank_transaction_id = any(array[bt.legacy_mongo_id, bt.id::text]))
"""
