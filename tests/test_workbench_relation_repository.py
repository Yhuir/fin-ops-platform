from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository


class RecordingConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.fetch_one_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.execute_calls: list[tuple[str, tuple[Any, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        return []

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, object]:
        self.fetch_one_calls.append((sql, params))
        return {"source_version": 1}

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        self.execute_calls.append((sql, params))
        return 1


def _snapshot(
    *,
    relation_mode: str = "manual_confirmed",
    row_types: list[str] | None = None,
    month_scope: str = "2026-05",
) -> dict[str, object]:
    return {
        "pair_relations": {
            "CASE-1": {
                "case_id": "CASE-1",
                "relation_mode": relation_mode,
                "status": "active",
                "version": 1,
                "month_scope": month_scope,
                "row_ids": ["bank-1", "invoice-1"],
                "row_types": list(row_types or ["bank", "invoice"]),
            }
        },
        "pair_relation_history": [],
    }


def _read_model_dirty_scope_calls(connection: RecordingConnection) -> list[tuple[Any, ...]]:
    return [
        params
        for sql, params in connection.fetch_one_calls
        if "insert into job.read_model_dirty_scopes" in " ".join(sql.lower().split())
    ]


def _read_model_outbox_calls(connection: RecordingConnection) -> list[tuple[Any, ...]]:
    return [
        params
        for sql, params in connection.execute_calls
        if "insert into job.outbox_events" in " ".join(sql.lower().split())
    ]


def _assert_no_read_model_refresh_writes(connection: RecordingConnection) -> None:
    assert _read_model_dirty_scope_calls(connection) == []
    assert _read_model_outbox_calls(connection) == []


def _assert_no_downstream_scope_inference(connection: RecordingConnection) -> None:
    sql = _executed_sql(connection)
    assert "from app.bank_transactions" not in sql
    assert "from app.invoices" not in sql
    assert "from app.oa_applications" not in sql


def _executed_sql(connection: RecordingConnection) -> str:
    return " ".join(
        "\n".join(sql for sql, _params in [*connection.fetch_all_calls, *connection.fetch_one_calls, *connection.execute_calls])
        .lower()
        .split()
    )


def test_relation_change_persists_canonical_relation_without_read_model_refresh_writes() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(_snapshot(), changed_case_ids={"CASE-1"})

    sql = _executed_sql(connection)
    assert "insert into app.workbench_pair_relations" in sql
    assert "read_model.workbench_rows" not in sql
    _assert_no_downstream_scope_inference(connection)
    _assert_no_read_model_refresh_writes(connection)


def test_no_oa_relation_change_does_not_create_no_oa_read_model_refresh() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(relation_mode="no_oa_bank_batch", row_types=["bank"]),
        changed_case_ids={"CASE-1"},
    )

    _assert_no_downstream_scope_inference(connection)
    _assert_no_read_model_refresh_writes(connection)


def test_input_expense_relation_change_does_not_infer_page_refresh_scopes() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(_snapshot(), changed_case_ids={"CASE-1"})

    _assert_no_downstream_scope_inference(connection)
    _assert_no_read_model_refresh_writes(connection)


def test_relation_change_does_not_query_bank_month_for_deleted_refresh_scope() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(month_scope="2026-01"),
        changed_case_ids={"CASE-1"},
    )

    sql = _executed_sql(connection)
    assert "from app.bank_transactions" not in sql
    assert "read_model.workbench_rows" not in sql
    _assert_no_read_model_refresh_writes(connection)


def test_relation_change_does_not_query_invoice_month_for_deleted_refresh_scope() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(month_scope="2026-02"),
        changed_case_ids={"CASE-1"},
    )

    sql = _executed_sql(connection)
    assert "from app.invoices" not in sql
    assert "read_model.workbench_rows" not in sql
    _assert_no_read_model_refresh_writes(connection)


def test_relation_refresh_does_not_enqueue_workbench_all_when_scope_is_unknown() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(month_scope=""),
        changed_case_ids={"CASE-1"},
    )

    _assert_no_downstream_scope_inference(connection)
    _assert_no_read_model_refresh_writes(connection)


def test_relation_change_does_not_query_oa_projection_for_deleted_refresh_scope() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(row_types=["bank", "oa"], month_scope="2026-04"),
        changed_case_ids={"CASE-1"},
    )

    sql = _executed_sql(connection)
    assert "from app.oa_applications" not in sql
    _assert_no_read_model_refresh_writes(connection)


def test_unresolved_invoice_month_does_not_create_broad_read_model_refresh() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(row_types=["bank", "invoice"], month_scope="2026-04"),
        changed_case_ids={"CASE-1"},
    )

    sql = _executed_sql(connection)
    assert "from app.invoices" not in sql
    _assert_no_read_model_refresh_writes(connection)


def test_cost_bearing_relation_does_not_create_cost_statistics_read_model_refresh() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(row_types=["bank", "oa"], month_scope="2026-02"),
        changed_case_ids={"CASE-1"},
    )

    sql = _executed_sql(connection)
    assert "cost_statistics.read_model.refresh" not in sql
    assert "from app.bank_transactions" not in sql
    assert "from app.oa_applications" not in sql
    _assert_no_read_model_refresh_writes(connection)


def test_relation_downstream_refresh_uses_direct_fact_gap_without_workbench_rows_fallback() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(row_types=["bank"], month_scope=""),
        changed_case_ids={"CASE-1"},
    )

    sql = _executed_sql(connection)
    assert "read_model.workbench_rows" not in sql
    _assert_no_downstream_scope_inference(connection)
    _assert_no_read_model_refresh_writes(connection)
