from __future__ import annotations

import json
from typing import Any

from fin_ops_platform.services.postgres_repositories.workbench_relation import (
    PostgresWorkbenchRelationRepository,
)


def load_bank_import_dedup_repair_snapshot(
    connection: Any,
    *,
    source_sessions: list[dict[str, Any]],
    expected_target_count: int,
    expected_protected_count: int,
    expected_replay_create_count: int,
    cleanup_related_duplicates: bool = False,
    expected_category_cleanup_count: int = 0,
    expected_workbench_withdraw_count: int = 0,
    expected_workbench_transaction_id: str | None = None,
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
    target_row_ids = sorted(
        {
            str(value)
            for row in targets
            for value in (row.get("transaction_pk"), row.get("transaction_id"))
            if value
        }
    )
    workbench_snapshot = (
        PostgresWorkbenchRelationRepository(connection).load_workbench_pair_relations_for_row_ids(
            target_row_ids
        )
        if target_row_ids
        else {}
    )
    invoice_row_ids = sorted(
        {
            str(row_id)
            for relation in (workbench_snapshot.get("pair_relations") or {}).values()
            if isinstance(relation, dict)
            for row_id, row_type in zip(
                list(relation.get("row_ids") or []),
                list(relation.get("row_types") or []),
                strict=False,
            )
            if str(row_type or "").strip() == "invoice" and str(row_id or "").strip()
        }
    )
    return {
        "request": {
            "source_sessions": source_sessions,
            "expected_target_count": expected_target_count,
            "expected_protected_count": expected_protected_count,
            "expected_replay_create_count": expected_replay_create_count,
            "cleanup_related_duplicates": cleanup_related_duplicates,
            "expected_category_cleanup_count": expected_category_cleanup_count,
            "expected_workbench_withdraw_count": expected_workbench_withdraw_count,
            "expected_workbench_transaction_id": expected_workbench_transaction_id,
        },
        "files": files,
        "batches": connection.fetch_all(_BATCH_SQL, (batch_pks,)) if batch_pks else [],
        "target_transactions": targets,
        "protected_transactions": connection.fetch_all(_PROTECTED_TRANSACTION_SQL, (target_pks,)),
        "import_rows": connection.fetch_all(_IMPORT_ROW_SQL, (batch_pks,)) if batch_pks else [],
        "relation_evidence": (
            connection.fetch_all(_RELATION_EVIDENCE_SQL, (target_pks,)) if target_pks else []
        ),
        "workbench_snapshot": workbench_snapshot,
        "invoice_relation_members": (
            connection.fetch_all(
                _INVOICE_RELATION_MEMBER_SQL,
                (invoice_row_ids, invoice_row_ids),
            )
            if invoice_row_ids
            else []
        ),
    }


def apply_bank_import_dedup_repair(
    connection: Any,
    plan: dict[str, Any],
    *,
    operator_id: str,
) -> dict[str, int]:
    normalized_operator_id = str(operator_id or "").strip()
    if not normalized_operator_id:
        raise ValueError("Bank dedup repair requires an operator id.")
    connection.execute(
        "select set_config('fin_ops.correction_reason', %s, true)",
        ("Authorized bank import duplicate cleanup after relation withdrawal.",),
    )
    connection.execute(
        "select set_config('fin_ops.actor_id', %s, true)",
        (normalized_operator_id,),
    )
    category_event_delete_count = 0
    category_delete_count = 0
    for cleanup in plan.get("category_cleanup_actions") or []:
        event = dict(cleanup["event"])
        affected = connection.execute(
            _DELETE_CATEGORY_EVENT_SQL,
            (
                event["event_id"],
                cleanup["category_id"],
                cleanup["transaction_pk"],
                event["event_type"],
                event.get("actor_id"),
                event["occurred_at"],
                json.dumps(event.get("payload") or {}, ensure_ascii=False, default=str),
                json.dumps(event.get("raw_payload") or {}, ensure_ascii=False, default=str),
            ),
        )
        if affected != 1:
            raise RuntimeError(
                f"Bank category event {event['event_id']} changed after dry-run."
            )
        category_event_delete_count += affected
        affected = connection.execute(
            _DELETE_CATEGORY_SQL,
            (
                cleanup["category_id"],
                cleanup["transaction_pk"],
                cleanup.get("legacy_transaction_id"),
                cleanup["category"],
                cleanup["source"],
                cleanup.get("confidence"),
                cleanup["status"],
                cleanup["version"],
                cleanup.get("updated_by"),
                cleanup["updated_at"],
                json.dumps(cleanup.get("raw_payload") or {}, ensure_ascii=False, default=str),
            ),
        )
        if affected != 1:
            raise RuntimeError(
                f"Bank category {cleanup['category_id']} changed after dry-run."
            )
        category_delete_count += affected
    for update in plan["row_updates"]:
        affected = connection.execute(
            _UPDATE_IMPORT_ROW_SQL,
            (
                update["after_decision"],
                update["after_decision_reason"],
                update["after_linked_object_type"],
                update["after_linked_object_id"],
                json.dumps(update["after_raw_payload"], ensure_ascii=False, default=str),
                update["row_pk"],
                update["batch_pk"],
                update["before_decision"],
                update["before_decision_reason"],
                update["before_linked_object_type"],
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
    return {
        "category_event_delete_count": category_event_delete_count,
        "category_delete_count": category_delete_count,
        "import_row_update_count": len(plan["row_updates"]),
        "transaction_delete_count": len(plan["duplicate_pairs"]),
    }


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
bt.balance, bt.currency,
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
       row.row_no, row.decision, row.decision_reason,
       row.linked_object_type, row.linked_object_id, row.raw_payload
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
       coalesce((
           select jsonb_agg(
               jsonb_build_object(
                   'category_id', value.id::text,
                   'bank_transaction_id', value.bank_transaction_id::text,
                   'legacy_transaction_id', value.legacy_transaction_id,
                   'category', value.category,
                   'source', value.source,
                   'confidence', value.confidence,
                   'status', value.status,
                   'version', value.version,
                   'updated_by', value.updated_by,
                   'updated_at', value.updated_at,
                   'raw_payload', value.raw_payload
               ) order by value.id
           )
           from app.bank_transaction_categories value
           where value.bank_transaction_id = bt.id
              or value.legacy_transaction_id = any(array[bt.legacy_mongo_id, bt.id::text])
       ), '[]'::jsonb) as category_details,
       (select count(*) from app.bank_transaction_category_events value
        where value.bank_transaction_id = bt.id) as category_event_count,
       coalesce((
           select jsonb_agg(
               jsonb_build_object(
                   'event_id', value.id::text,
                   'category_id', value.category_id::text,
                   'bank_transaction_id', value.bank_transaction_id::text,
                   'event_type', value.event_type,
                   'actor_id', value.actor_id,
                   'occurred_at', value.occurred_at,
                   'payload', value.payload,
                   'raw_payload', value.raw_payload
               ) order by value.id
           )
           from app.bank_transaction_category_events value
           where value.bank_transaction_id = bt.id
       ), '[]'::jsonb) as category_event_details,
       (select count(*) from app.bank_transaction_category_confirmations value
        where value.bank_transaction_id = bt.id
           or value.legacy_transaction_id = any(array[bt.legacy_mongo_id, bt.id::text]))
           as category_confirmation_count,
       (select count(*) from app.workbench_pair_relations value
        where value.status = 'active'
          and value.row_ids && array[bt.legacy_mongo_id, bt.id::text]) as workbench_pair_count,
       (select count(*) from app.workbench_pair_relations value
        where value.status <> 'active'
          and value.row_ids && array[bt.legacy_mongo_id, bt.id::text])
          as workbench_inactive_pair_count,
       coalesce((
           select jsonb_agg(
               jsonb_build_object(
                   'relation_id', value.id::text,
                   'case_id', value.case_id,
                   'relation_mode', value.relation_mode,
                   'status', value.status,
                   'version', value.version,
                   'month_scope', value.month_scope,
                   'row_ids', value.row_ids,
                   'row_types', value.row_types,
                   'note', value.note,
                   'amount_check', value.amount_check,
                   'special_metadata', value.special_metadata,
                   'created_by', value.created_by,
                   'created_at', value.created_at,
                   'updated_at', value.updated_at
               ) order by value.case_id
           )
           from app.workbench_pair_relations value
           where value.status = 'active'
             and value.row_ids && array[bt.legacy_mongo_id, bt.id::text]
       ), '[]'::jsonb) as workbench_relation_details,
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

_INVOICE_RELATION_MEMBER_SQL = """
select invoice.id::text as invoice_pk,
       coalesce(invoice.legacy_mongo_id, invoice.id::text) as invoice_id,
       invoice.invoice_type,
       invoice.invoice_no,
       invoice.invoice_code,
       invoice.digital_invoice_no,
       invoice.invoice_date,
       invoice.counterparty_name,
       invoice.seller_name,
       invoice.seller_tax_no,
       invoice.buyer_name,
       invoice.buyer_tax_no,
       invoice.amount,
       invoice.tax_amount,
       invoice.total_with_tax,
       invoice.currency,
       invoice.status
from app.invoices invoice
where (
        invoice.id::text = any(%s::text[])
        or invoice.legacy_mongo_id = any(%s::text[])
      )
  and invoice.status <> 'deleted'
order by invoice.id
"""

_DELETE_CATEGORY_EVENT_SQL = """
delete from app.bank_transaction_category_events event
where event.id = %s::uuid
  and event.category_id = %s::uuid
  and event.bank_transaction_id = %s::uuid
  and event.event_type = %s
  and event.actor_id is not distinct from %s
  and event.occurred_at = %s::timestamptz
  and event.payload = %s::jsonb
  and event.raw_payload = %s::jsonb
"""

_DELETE_CATEGORY_SQL = """
delete from app.bank_transaction_categories category
where category.id = %s::uuid
  and category.bank_transaction_id = %s::uuid
  and category.legacy_transaction_id is not distinct from %s
  and category.category = %s
  and category.source = %s
  and category.confidence is not distinct from %s
  and category.status = %s
  and category.version = %s
  and category.updated_by is not distinct from %s
  and category.updated_at = %s::timestamptz
  and category.raw_payload = %s::jsonb
"""

_UPDATE_IMPORT_ROW_SQL = """
update app.import_batch_rows
set decision = %s,
    decision_reason = %s,
    linked_object_type = %s,
    linked_object_id = %s,
    raw_payload = %s::jsonb
where id = %s::uuid
  and import_batch_id = %s::uuid
  and decision = %s
  and decision_reason is not distinct from %s
  and linked_object_type is not distinct from %s
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
  and not exists (select 1 from app.workbench_pair_relations value where value.status = 'active' and value.row_ids && array[bt.legacy_mongo_id, bt.id::text])
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
