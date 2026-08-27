from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.oa_payment_status_reconcile import (
    PostgresOAPaymentStatusReconcileRepository,
)


class RecordingConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple[Any, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        return [
            {"oa_row_id": "oa-uuid", "has_active_outflow": True},
            {"oa_row_id": "oa-legacy", "has_active_outflow": False},
        ]


def test_active_outflow_query_accepts_bank_uuid_and_legacy_id() -> None:
    connection = RecordingConnection()
    repository = PostgresOAPaymentStatusReconcileRepository(connection)

    result = repository.active_outflow_by_oa_row_id(["oa-uuid", "oa-legacy"])

    assert result == {"oa-uuid": True, "oa-legacy": False}
    sql, params = connection.fetch_all_calls[0]
    normalized_sql = " ".join(sql.lower().split())
    assert "member.row_id in (bank.id::text, bank.legacy_mongo_id)" in normalized_sql
    assert "bank.txn_direction = 'outflow'" in normalized_sql
    assert params == (["oa-uuid", "oa-legacy"],)
