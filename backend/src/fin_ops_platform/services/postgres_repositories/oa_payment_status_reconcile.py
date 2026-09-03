from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.common import (
    text,
    text_list,
)


class PostgresOAPaymentStatusReconcileRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def active_outflow_by_oa_row_id(
        self,
        oa_row_ids: list[str],
    ) -> dict[str, bool]:
        normalized = text_list(oa_row_ids)
        if not normalized:
            return {}
        rows = self._connection.fetch_all(
            """
            with requested as (
                select oa_row_id
                from unnest(%s::text[]) as item(oa_row_id)
            )
            select
                requested.oa_row_id,
                exists (
                    select 1
                    from app.workbench_pair_relations relation
                    where relation.status = 'active'
                      and cardinality(relation.row_ids) = cardinality(relation.row_types)
                      and exists (
                          select 1
                          from unnest(relation.row_ids, relation.row_types) member(row_id, row_type)
                          where member.row_id = requested.oa_row_id
                            and member.row_type in ('oa', 'oa_application')
                      )
                      and exists (
                          select 1
                          from unnest(relation.row_ids, relation.row_types) member(row_id, row_type)
                          join app.bank_transactions bank
                            on member.row_id in (bank.id::text, bank.legacy_mongo_id)
                           and bank.status <> 'deleted'
                           and bank.txn_direction = 'outflow'
                          where member.row_type in ('bank', 'bank_transaction')
                      )
                ) as has_active_outflow
            from requested
            order by requested.oa_row_id
            """,
            (normalized,),
        )
        return {
            text(row.get("oa_row_id")) or "": bool(row.get("has_active_outflow"))
            for row in rows
            if text(row.get("oa_row_id"))
        }

    def current_pending_oa_flow_ids(self, *, tenant_id: str) -> set[str]:
        rows = self._connection.fetch_all(
            """
            select distinct source_payload ->> 'flow_id' as flow_id
            from app.oa_pending_payment_admissions
            where tenant_id = %s
              and source_payload ->> 'flow_id' is not null
              and source_payload ->> 'flow_id' <> ''
            """,
            (tenant_id,),
        )
        return {
            flow_id
            for row in list(rows or [])
            if (flow_id := str(row.get("flow_id") or "").strip())
        }
