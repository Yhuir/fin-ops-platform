from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from fin_ops_platform.services.postgres_repositories.common import jsonb


class PostgresBankImportWithdrawalRepository:
    """Atomic persistence boundary for withdrawing one confirmed bank import batch."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    @property
    def transaction_connection(self) -> Any:
        return self._connection

    @contextmanager
    def transaction(self) -> Iterator["PostgresBankImportWithdrawalRepository"]:
        with self._connection.transaction() as transaction:
            yield PostgresBankImportWithdrawalRepository(transaction)

    def lock_batch(self, batch_id: str) -> dict[str, Any] | None:
        row = self._connection.fetch_one(
            """
            select
              batch.id::text as batch_uuid,
              coalesce(batch.legacy_mongo_id, batch.id::text) as batch_id,
              batch.batch_type,
              batch.source_name,
              batch.imported_by,
              batch.success_count,
              batch.updated_count,
              batch.status,
              batch.imported_at,
              batch.raw_payload
            from app.import_batches batch
            where coalesce(batch.legacy_mongo_id, batch.id::text) = %s
            for update
            """,
            (batch_id,),
        )
        return dict(row) if row else None

    def created_transactions(self, batch_uuid: str, batch_id: str) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select
              bank.id::text as transaction_uuid,
              coalesce(bank.legacy_mongo_id, bank.id::text) as row_id,
              bank.txn_month::text as txn_month,
              bank.written_off_amount
            from app.import_batch_rows batch_row
            join app.bank_transactions bank
              on batch_row.linked_object_type = 'bank_transaction'
             and batch_row.linked_object_id in (bank.legacy_mongo_id, bank.id::text)
            where (batch_row.import_batch_id = %s::uuid or batch_row.legacy_batch_id = %s)
              and batch_row.decision = 'created'
              and (bank.source_batch_id = %s::uuid or bank.legacy_source_batch_id = %s)
            order by row_id
            for update of bank
            """,
            (batch_uuid, batch_id, batch_uuid, batch_id),
        ) or []
        return [dict(row) for row in rows]

    def blocking_references(
        self,
        *,
        row_ids: list[str],
    ) -> dict[str, int]:
        row = self._connection.fetch_one(
            """
            select
              (select count(*) from app.workbench_exception_cases item
               where item.status not in ('resolved', 'closed', 'cancelled', 'canceled')
                 and (item.row_ids && %s::text[] or item.candidate_ids && %s::text[]))::bigint as exception_cases,
              (select count(*) from app.no_oa_bank_batches item
               where item.status not in ('withdrawn', 'cancelled', 'canceled', 'reverted', 'deleted')
                 and item.bank_transaction_ids && %s::text[])::bigint as no_oa_batches,
              (select count(*) from app.bank_flow_rule_batches item
               where item.status not in ('withdrawn', 'cancelled', 'canceled', 'reverted', 'deleted')
                 and item.bank_transaction_ids && %s::text[])::bigint as bank_flow_rule_batches,
              (select count(*) from app.turnover_relations item
               where item.status not in ('withdrawn', 'cancelled', 'canceled', 'void', 'voided', 'deleted')
                 and item.bank_transaction_id = any(%s::text[]))::bigint as turnover_relations,
              (select count(*)
               from app.oa_pending_payment_bank_relations item
               where item.status = 'active'
                 and item.bank_transaction_ids && %s::text[])::bigint as oa_pending_relations,
              (select count(*) from app.bank_transaction_relation_claims item
               where item.status = 'active' and item.owner_type <> 'workbench_relation'
                 and item.bank_transaction_id = any(%s::text[]))::bigint as non_workbench_claims,
              (select count(*)
               from app.output_invoice_receipts item
               where item.status = 'issued'
                 and item.bank_transaction_id = any(%s::text[]))::bigint as output_invoice_receipts,
              (select count(*) from app.workbench_row_overrides item
               where item.status = 'active'
                 and item.row_id <> all(%s::text[])
                 and item.changed_row_ids && %s::text[])::bigint as dependent_overrides
            """,
            (
                row_ids,
                row_ids,
                row_ids,
                row_ids,
                row_ids,
                row_ids,
                row_ids,
                row_ids,
                row_ids,
                row_ids,
            ),
        ) or {}
        return {key: int(value or 0) for key, value in dict(row).items()}

    def cleanup_removable_state(
        self,
        *,
        transaction_uuids: list[str],
        row_ids: list[str],
        actor_id: str,
        reason: str,
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        counts["category_events"] = self._connection.execute(
            "delete from app.bank_transaction_category_events where bank_transaction_id = any(%s::uuid[])",
            (transaction_uuids,),
        )
        counts["categories"] = self._connection.execute(
            "delete from app.bank_transaction_categories where bank_transaction_id = any(%s::uuid[])",
            (transaction_uuids,),
        )
        counts["confirmations"] = self._connection.execute(
            """
            delete from app.bank_transaction_category_confirmations
            where bank_transaction_id = any(%s::uuid[])
               or legacy_transaction_id = any(%s::text[])
            """,
            (transaction_uuids, row_ids),
        )
        counts["matching_results"] = self._connection.execute(
            "delete from app.matching_results where transaction_ids && %s::text[]",
            (row_ids,),
        )
        counts["row_overrides"] = self._connection.execute(
            "delete from app.workbench_row_overrides where row_id = any(%s::text[])",
            (row_ids,),
        )
        counts["released_workbench_claims"] = self._connection.execute(
            """
            update app.bank_transaction_relation_claims
            set status = 'released', released_by = %s, released_at = now(), release_reason = %s,
                updated_at = now()
            where status = 'active'
              and owner_type = 'workbench_relation'
              and bank_transaction_id = any(%s::text[])
            """,
            (actor_id, reason, row_ids),
        )
        return counts

    def delete_transactions(
        self,
        *,
        transaction_uuids: list[str],
        actor_id: str,
        reason: str,
    ) -> int:
        self._connection.fetch_one(
            "select set_config('fin_ops.correction_reason', %s, true), set_config('fin_ops.actor_id', %s, true)",
            (reason, actor_id),
        )
        return self._connection.execute(
            "delete from app.bank_transactions where id = any(%s::uuid[])",
            (transaction_uuids,),
        )

    def mark_withdrawn(self, *, batch_uuid: str, summary: dict[str, Any]) -> None:
        summary_json = jsonb(summary)
        self._connection.execute(
            """
            update app.import_batches
            set status = 'withdrawn',
                raw_payload = jsonb_set(
                  coalesce(raw_payload, '{}'::jsonb),
                  '{normalized_payload}',
                  coalesce(raw_payload->'normalized_payload', '{}'::jsonb)
                    || jsonb_build_object('status', 'withdrawn', 'withdrawal', %s::jsonb),
                  true
                ),
                updated_at = now()
            where id = %s::uuid
            """,
            (summary_json, batch_uuid),
        )
        self._connection.execute(
            """
            update app.import_files
            set status = 'withdrawn',
                raw_payload = jsonb_set(
                  coalesce(raw_payload, '{}'::jsonb),
                  '{normalized_payload}',
                  coalesce(raw_payload->'normalized_payload', '{}'::jsonb)
                    || jsonb_build_object(
                      'status', 'withdrawn',
                      'session_status', 'withdrawn',
                      'withdrawal', %s::jsonb
                    ),
                  true
                )
            where import_batch_id = %s::uuid
               or coalesce(
                    raw_payload->'normalized_payload'->>'batch_id',
                    raw_payload->'normalized_payload'->>'preview_batch_id'
                  ) = (select coalesce(legacy_mongo_id, id::text) from app.import_batches where id = %s::uuid)
            """,
            (summary_json, batch_uuid, batch_uuid),
        )

    def append_audit_event(
        self,
        *,
        batch_id: str,
        actor_id: str,
        reason: str,
        request_id: str | None,
        summary: dict[str, Any],
    ) -> None:
        self._connection.execute(
            """
            insert into audit.events(
              event_type, object_type, object_id, actor_id, action, page_key,
              operation_location, reason, outcome, request_id, payload, raw_payload
            ) values (
              'bank_import.withdrawn', 'import_batch', %s, %s, 'withdraw_bank_import',
              'app-health-operations', 'import_history_drawer', %s, 'success', %s, %s::jsonb, '{}'::jsonb
            )
            """,
            (batch_id, actor_id, reason, request_id, jsonb(summary)),
        )

    @staticmethod
    def withdrawal_payload(batch: dict[str, Any]) -> dict[str, Any] | None:
        raw_payload = batch.get("raw_payload")
        if not isinstance(raw_payload, dict):
            return None
        normalized = raw_payload.get("normalized_payload")
        if not isinstance(normalized, dict):
            return None
        withdrawal = normalized.get("withdrawal")
        return dict(withdrawal) if isinstance(withdrawal, dict) else None
