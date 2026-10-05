from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.common import row_payload


class PostgresOAIdentityRepairRepository:
    """Read exact historical cleanup evidence; writes remain owned by relation commands."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_evidence(self, case_ids: list[str]) -> dict[str, Any]:
        rows = self._connection.fetch_all(
            "select case_id, raw_payload from app.workbench_pair_relations "
            "where case_id = any(%s::text[]) order by case_id for update", (case_ids,),
        )
        current = {row['case_id']: row_payload(row, 'raw_payload') for row in rows}
        history = self._connection.fetch_all(
            """with cleanup as (
                   select case_id, max(occurred_at) as occurred_at
                   from app.workbench_pair_relation_history
                   where case_id = any(%s::text[])
                     and actor_id = 'system:oa_pending_payment_source_sync'
                     and event_type in ('remove_unavailable_oa_fact', 'cancel_relation_for_unavailable_oa_fact')
                   group by case_id)
               select h.case_id, h.id::text, h.event_type, h.actor_id, h.before_payload, h.after_payload
               from app.workbench_pair_relation_history h join cleanup c using(case_id)
               where h.occurred_at >= c.occurred_at
               order by h.case_id, h.occurred_at, h.id""", (case_ids,),
        )
        aliases = self._connection.fetch_all(
            """select alias_row_id, canonical_row_id from app.oa_source_aliases
               where status = 'active' and canonical_row_id in (
                   select row_id from app.oa_applications union all
                   select oa_id from app.oa_pending_payment_admissions)
               order by alias_row_id""", (),
        )
        return {'current': current, 'history': history,
                'aliases': {row['alias_row_id']: row['canonical_row_id'] for row in aliases}}
