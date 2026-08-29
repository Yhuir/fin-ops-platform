from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.common import jsonb, serialize_value


class PostgresWorkbenchRelationReceiptRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_active_relation(self, case_id: str) -> dict[str, Any] | None:
        relation = self._connection.fetch_one(
            """
            select id::text as id, case_id, version, row_ids, row_types
            from app.workbench_pair_relations
            where case_id = %s and status = 'active'
            """,
            (case_id,),
        )
        if relation is None:
            return None
        row_ids = [str(value) for value in relation.get("row_ids") or []]
        relation["bank_rows"] = self._connection.fetch_all(
            """
            select id::text as id, legacy_mongo_id, txn_direction,
                   counterparty_name_raw, normalized_counterparty_name,
                   amount, txn_date, trade_time, pay_receive_time,
                   currency, summary, remark, updated_at
            from app.bank_transactions
            where coalesce(legacy_mongo_id, id::text) = any(%s::text[])
            order by coalesce(pay_receive_time, trade_time, txn_date::timestamptz), id
            """,
            (row_ids,),
        )
        relation["invoice_rows"] = self._connection.fetch_all(
            """
            select id::text as id, legacy_mongo_id, invoice_type, invoice_no,
                   digital_invoice_no, invoice_date, buyer_name, counterparty_name,
                   total_with_tax, amount, currency, raw_payload, updated_at
            from app.invoices
            where coalesce(legacy_mongo_id, id::text) = any(%s::text[])
            order by invoice_date, invoice_no, id
            """,
            (row_ids,),
        )
        return relation

    def find_by_fingerprint(self, case_id: str, fingerprint: str) -> dict[str, Any] | None:
        return self._connection.fetch_one(
            """
            select id::text as id, storage_uri, source_fingerprint, receipt_count,
                   total_amount, snapshot, generated_at
            from app.workbench_relation_receipts
            where case_id = %s and source_fingerprint = %s
            """,
            (case_id, fingerprint),
        )

    def insert(self, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        row = self._connection.fetch_one(
            """
            insert into app.workbench_relation_receipts(
                id, relation_id, case_id, relation_version, source_fingerprint,
                file_object_id, storage_uri, receipt_count, total_amount, snapshot,
                generated_by_id, generated_by_account, generated_by_name
            ) values (
                %s::uuid, %s::uuid, %s, %s, %s,
                %s::uuid, %s, %s, %s, %s,
                %s, %s, %s
            )
            on conflict (case_id, source_fingerprint) do nothing
            returning id::text as id, storage_uri, source_fingerprint, receipt_count,
                      total_amount, snapshot, generated_at
            """,
            (
                payload["id"], payload["relation_id"], payload["case_id"],
                payload["relation_version"], payload["source_fingerprint"],
                payload["file_object_id"], payload["storage_uri"], payload["receipt_count"],
                payload["total_amount"], jsonb(serialize_value(payload["snapshot"])),
                payload["generated_by_id"], payload["generated_by_account"],
                payload["generated_by_name"],
            ),
        )
        created = row is not None
        if row is None:
            row = self.find_by_fingerprint(
                str(payload["case_id"]),
                str(payload["source_fingerprint"]),
            )
        if row is None:
            raise RuntimeError("receipt snapshot was not persisted")
        return row, created
