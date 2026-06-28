from __future__ import annotations

from typing import Any


class PendingInvoiceOaIdentityRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def invalid_read_model_rows(self) -> list[dict[str, Any]]:
        return []

    def invalid_relation_rows(self) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select case_id, row_ids, row_types
            from app.workbench_pair_relations
            where status = 'active'
              and exists (
                  select 1
                  from unnest(row_ids, row_types) as relation_rows(row_id, row_type)
                  where row_type = 'oa'
                    and row_id !~ '^oa-'
              )
            order by updated_at desc, case_id
            limit 500
            """
        )
        return [dict(row) for row in list(rows or []) if isinstance(row, dict)]

    def missing_oa_relation_rows(self) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select case_id, row_ids, row_types
            from app.workbench_pair_relations
            where status = 'active'
              and row_types && array['bank']::text[]
              and row_types && array['invoice']::text[]
              and not row_types && array['oa']::text[]
              and case_id like 'candidate:%'
            order by updated_at desc, case_id
            limit 500
            """
        )
        return [dict(row) for row in list(rows or []) if isinstance(row, dict)]
