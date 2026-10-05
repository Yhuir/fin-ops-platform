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
            """select distinct on (case_id) case_id, id::text, event_type, actor_id,
                      before_payload, after_payload
               from app.workbench_pair_relation_history
               where case_id = any(%s::text[])
               order by case_id, occurred_at desc, id desc""", (case_ids,),
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
