from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fin_ops_platform.services.postgres_repositories.common import (
    int_value,
    jsonb,
    run_in_transaction,
    text,
    text_list,
)


@dataclass(frozen=True, slots=True)
class OAPaymentStatusWritebackState:
    flow_id: str
    oa_row_ids: tuple[str, ...]
    app_owned: bool
    sync_state: str
    desired_pay_status: int
    observed_pay_status: int | None
    last_event_id: str


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

    def load_state(
        self,
        *,
        tenant_id: str,
        flow_id: str,
    ) -> OAPaymentStatusWritebackState | None:
        row = self._connection.fetch_one(
            """
            select flow_id, oa_row_ids, app_owned, sync_state, desired_pay_status,
                   observed_pay_status, last_event_id
            from app.oa_payment_status_writeback_states
            where tenant_id = %s and flow_id = %s
            """,
            (tenant_id, flow_id),
        )
        if not row:
            return None
        return OAPaymentStatusWritebackState(
            flow_id=text(row.get("flow_id")) or flow_id,
            oa_row_ids=tuple(text_list(row.get("oa_row_ids"))),
            app_owned=bool(row.get("app_owned")),
            sync_state=text(row.get("sync_state")) or "stable",
            desired_pay_status=int_value(row.get("desired_pay_status"), 0),
            observed_pay_status=(
                int_value(row.get("observed_pay_status"), 0)
                if row.get("observed_pay_status") is not None
                else None
            ),
            last_event_id=text(row.get("last_event_id")) or "",
        )

    def save_state(
        self,
        *,
        tenant_id: str,
        flow_id: str,
        oa_row_ids: list[str],
        app_owned: bool,
        sync_state: str,
        desired_pay_status: int,
        observed_pay_status: int | None,
        event_id: str,
    ) -> None:
        normalized_ids = text_list(oa_row_ids)

        def write(transaction: Any) -> None:
            transaction.execute(
                """
                insert into app.oa_payment_status_writeback_states(
                    tenant_id, flow_id, oa_row_ids, app_owned, sync_state,
                    desired_pay_status, observed_pay_status, last_event_id, raw_payload
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (tenant_id, flow_id) do update set
                    oa_row_ids = excluded.oa_row_ids,
                    app_owned = excluded.app_owned,
                    sync_state = excluded.sync_state,
                    desired_pay_status = excluded.desired_pay_status,
                    observed_pay_status = excluded.observed_pay_status,
                    last_event_id = excluded.last_event_id,
                    raw_payload = excluded.raw_payload,
                    updated_at = now()
                """,
                (
                    tenant_id,
                    flow_id,
                    normalized_ids,
                    app_owned,
                    sync_state,
                    desired_pay_status,
                    observed_pay_status,
                    event_id,
                    jsonb({
                        "oa_row_ids": normalized_ids,
                        "desired_pay_status": desired_pay_status,
                        "observed_pay_status": observed_pay_status,
                        "app_owned": app_owned,
                        "sync_state": sync_state,
                        "event_id": event_id,
                    }),
                ),
            )

        run_in_transaction(self._connection, write)
