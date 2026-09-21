from __future__ import annotations

import json
from typing import Any


def load_bank_identity_repair_rows(connection: Any, *, lock_ids: list[str] | None = None) -> list[dict[str, Any]]:
    if lock_ids:
        connection.fetch_all(
            "select id from app.bank_transactions where coalesce(legacy_mongo_id,id::text) = any(%s::text[]) "
            "order by id for update", (lock_ids,),
        )
    return connection.fetch_all("""
        select id::text, coalesce(legacy_mongo_id,id::text) as transaction_id,
               account_no, txn_direction, counterparty_name_raw, amount, trade_time, pay_receive_time,
               txn_date, bank_serial_no, source_unique_key, data_fingerprint, raw_payload, updated_at,
               raw_payload->'normalized_payload'->>'account_detail_no' as account_detail_no,
               raw_payload->'normalized_payload'->>'enterprise_serial_no' as enterprise_serial_no,
               raw_payload->'normalized_payload'->>'voucher_no' as voucher_no
        from app.bank_transactions order by id
    """)


def apply_bank_identity_repair(
    connection: Any, updates: list[dict[str, Any]], *, operator_id: str, reason: str,
) -> int:
    if not operator_id.strip() or not reason.strip():
        raise ValueError("Bank identity correction requires an operator and reason.")
    if not updates:
        return 0
    connection.execute(
        "select set_config('fin_ops.actor_id', %s, true), set_config('fin_ops.correction_reason', %s, true)",
        (operator_id, reason),
    )
    count = connection.execute("""
        update app.bank_transactions t
        set source_unique_key = delta.after_key,
            raw_payload = delta.after_payload,
            updated_at = now()
        from jsonb_to_recordset(%s::jsonb) as delta(
            id uuid, before_key text, after_key text, before_payload jsonb,
            after_payload jsonb, before_updated_at timestamptz)
        where t.id = delta.id and t.source_unique_key = delta.before_key
          and t.raw_payload = delta.before_payload and t.updated_at = delta.before_updated_at
    """, (json.dumps(updates, default=str),))
    if count != len(updates):
        raise RuntimeError("Bank identity facts changed before execution.")
    return count
