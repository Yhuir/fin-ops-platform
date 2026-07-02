from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository


class RecordingConnection:
    def __init__(
        self,
        *,
        invoice_types: list[str] | None = None,
        bank_directions: list[str] | None = None,
        bank_scope_keys: list[str] | None = None,
        invoice_scope_keys: list[str] | None = None,
        oa_scope_keys: list[str] | None = None,
        workbench_scope_keys: list[str] | None = None,
    ) -> None:
        self.fetch_all_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.fetch_one_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.execute_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.invoice_types = list(invoice_types or [])
        self.bank_directions = list(bank_directions or [])
        self.bank_scope_keys = list(["2026-05"] if bank_scope_keys is None else bank_scope_keys)
        self.invoice_scope_keys = list(["2026-05"] if invoice_scope_keys is None else invoice_scope_keys)
        self.oa_scope_keys = list([] if oa_scope_keys is None else oa_scope_keys)
        self.workbench_scope_keys = list([] if workbench_scope_keys is None else workbench_scope_keys)

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        normalized_sql = " ".join(sql.lower().split())
        if "select distinct invoice_type" in normalized_sql:
            return [{"invoice_type": invoice_type} for invoice_type in self.invoice_types]
        if "select distinct txn_direction" in normalized_sql:
            return [{"txn_direction": direction} for direction in self.bank_directions]
        if "select distinct to_char(txn_month, 'yyyy-mm') as scope_key from app.bank_transactions" in normalized_sql:
            return [{"scope_key": scope_key} for scope_key in self.bank_scope_keys]
        if "select distinct to_char(invoice_month, 'yyyy-mm') as scope_key from app.invoices" in normalized_sql:
            return [{"scope_key": scope_key} for scope_key in self.invoice_scope_keys]
        if "select distinct to_char(date_trunc('month', application_date)::date, 'yyyy-mm') as scope_key from app.oa_applications" in normalized_sql:
            return [{"scope_key": scope_key} for scope_key in self.oa_scope_keys]
        if "select distinct to_char(scope_month, 'yyyy-mm') as scope_key from read_model.workbench_rows" in normalized_sql:
            return [{"scope_key": scope_key} for scope_key in self.workbench_scope_keys]
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


def _json_payload(value: object) -> dict[str, object]:
    payload = getattr(value, "obj", value)
    return payload if isinstance(payload, dict) else {}


def test_relation_change_enqueues_relation_read_model_before_relevant_downstream_by_priority() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(_snapshot(), changed_case_ids={"CASE-1"})

    assert all("read_model.workbench_rows" not in sql for sql, _params in connection.fetch_all_calls)

    dirty_by_scope_type = {
        str(params[1]): params
        for sql, params in connection.fetch_one_calls
        if "insert into job.read_model_dirty_scopes" in " ".join(sql.lower().split())
    }
    outbox_by_scope_type = {
        str(params[3]): params
        for sql, params in connection.execute_calls
        if "insert into job.outbox_events" in " ".join(sql.lower().split())
    }

    assert dirty_by_scope_type["workbench_relation"][-1] == "high"
    assert dirty_by_scope_type["workbench"][-1] == "high"
    assert dirty_by_scope_type["bank_detail"][-1] == "high"
    assert dirty_by_scope_type["invoice_lifecycle"][-1] == "high"
    assert dirty_by_scope_type["input_invoice_usage"][-1] == "high"
    assert dirty_by_scope_type["output_invoice_collection"][-1] == "high"
    assert dirty_by_scope_type["search"][-1] == "high"
    assert dirty_by_scope_type["tax_offset"][-1] == "high"
    assert "cost_statistics" not in dirty_by_scope_type
    assert "oa_pending_payment" not in dirty_by_scope_type
    assert "no_oa_bank_batch" not in dirty_by_scope_type
    assert outbox_by_scope_type["workbench_relation"][-3] == "high"
    assert outbox_by_scope_type["workbench"][-3] == "high"
    assert outbox_by_scope_type["bank_detail"][-3] == "high"
    assert outbox_by_scope_type["invoice_lifecycle"][-3] == "high"
    assert outbox_by_scope_type["search"][-3] == "high"
    workbench_all_outbox_payloads = [
        _json_payload(params[8])
        for sql, params in connection.execute_calls
        if "insert into job.outbox_events" in " ".join(sql.lower().split())
        and str(params[3]) == "workbench"
        and str(params[4]) == "all"
    ]
    assert workbench_all_outbox_payloads
    assert workbench_all_outbox_payloads[-1]["aggregate_only"] is True


def test_relation_repository_can_persist_without_refresh_fanout_for_uow_boundary() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection, enqueue_refreshes=False)

    repository.save_workbench_pair_relations(_snapshot(), changed_case_ids={"CASE-1"})

    normalized_fetch_all_sql = [" ".join(sql.lower().split()) for sql, _params in connection.fetch_all_calls]
    normalized_fetch_one_sql = [" ".join(sql.lower().split()) for sql, _params in connection.fetch_one_calls]
    normalized_execute_sql = [" ".join(sql.lower().split()) for sql, _params in connection.execute_calls]

    assert not normalized_fetch_all_sql
    assert not normalized_fetch_one_sql
    assert any("insert into app.workbench_pair_relations" in sql for sql in normalized_execute_sql)
    assert not any("insert into job.outbox_events" in sql for sql in normalized_execute_sql)


def test_no_oa_relation_change_keeps_no_oa_read_model_in_downstream_scope() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(relation_mode="no_oa_bank_batch", row_types=["bank"]),
        changed_case_ids={"CASE-1"},
    )

    dirty_by_scope_type = {
        str(params[1]): params
        for sql, params in connection.fetch_one_calls
        if "insert into job.read_model_dirty_scopes" in " ".join(sql.lower().split())
    }

    assert dirty_by_scope_type["workbench_relation"][-1] == "high"
    assert dirty_by_scope_type["bank_detail"][-1] == "high"
    assert dirty_by_scope_type["cost_statistics"][-1] == "high"
    assert dirty_by_scope_type["search"][-1] == "high"
    assert dirty_by_scope_type["no_oa_bank_batch"][-1] == "high"
    assert _json_payload(dirty_by_scope_type["no_oa_bank_batch"][4])["relation_mode"] == "no_oa_bank_batch"
    no_oa_outbox_params = [
        params
        for sql, params in connection.execute_calls
        if "insert into job.outbox_events" in " ".join(sql.lower().split())
        and str(params[3]) == "no_oa_bank_batch"
    ]
    assert no_oa_outbox_params[-1][5] == (
        "no_oa_bank_batch.read_model.refresh:no_oa_bank_batch:2026-05:no_oa_bank_batch"
    )
    assert _json_payload(no_oa_outbox_params[-1][8])["relation_mode"] == "no_oa_bank_batch"
    assert "input_invoice_usage" not in dirty_by_scope_type
    assert "output_invoice_collection" not in dirty_by_scope_type
    assert "tax_offset" not in dirty_by_scope_type
    assert "oa_pending_payment" not in dirty_by_scope_type


def test_bank_flow_relation_change_enqueues_bank_flow_read_model_refresh() -> None:
    connection = RecordingConnection()
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(relation_mode="bank_flow_rule_batch", row_types=["bank"]),
        changed_case_ids={"CASE-1"},
    )

    dirty_by_scope_type = {
        str(params[1]): params
        for sql, params in connection.fetch_one_calls
        if "insert into job.read_model_dirty_scopes" in " ".join(sql.lower().split())
    }
    bank_flow_outbox_params = [
        params
        for sql, params in connection.execute_calls
        if "insert into job.outbox_events" in " ".join(sql.lower().split())
        and str(params[3]) == "bank_flow_rule_batch"
    ]

    assert "no_oa_bank_batch" not in dirty_by_scope_type
    assert dirty_by_scope_type["bank_flow_rule_batch"][-1] == "high"
    assert _json_payload(dirty_by_scope_type["bank_flow_rule_batch"][4])["relation_mode"] == "bank_flow_rule_batch"
    assert bank_flow_outbox_params[-1][5] == (
        "bank_flow_rule_batch.read_model.refresh:bank_flow_rule_batch:2026-05:bank_flow_rule_batch"
    )
    assert _json_payload(bank_flow_outbox_params[-1][8])["relation_mode"] == "bank_flow_rule_batch"
    assert dirty_by_scope_type["cost_statistics"][-1] == "high"


def test_input_expense_relation_change_skips_output_and_income_downstream_scopes() -> None:
    connection = RecordingConnection(invoice_types=["input"], bank_directions=["outflow"])
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(_snapshot(), changed_case_ids={"CASE-1"})

    dirty_params = [
        params
        for sql, params in connection.fetch_one_calls
        if "insert into job.read_model_dirty_scopes" in " ".join(sql.lower().split())
    ]
    dirty_by_scope_type = {str(params[1]): params for params in dirty_params}
    pending_scope_keys = {
        str(params[2])
        for params in dirty_params
        if str(params[1]) == "pending_invoice"
    }

    assert "input_invoice_usage" in dirty_by_scope_type
    assert "output_invoice_collection" not in dirty_by_scope_type
    assert "oa_pending_payment" not in dirty_by_scope_type
    assert pending_scope_keys == {
        "expense:all:2026-05",
        "expense:requires_invoice:2026-05",
        "expense:bank_statement_as_invoice:2026-05",
        "expense:no_invoice_required:2026-05",
    }


def test_pending_invoice_relation_refresh_uses_bank_month_not_invoice_month() -> None:
    connection = RecordingConnection(
        invoice_types=["input"],
        bank_directions=["outflow"],
        bank_scope_keys=["2026-02"],
    )
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(month_scope="2026-01"),
        changed_case_ids={"CASE-1"},
    )

    dirty_params = [
        params
        for sql, params in connection.fetch_one_calls
        if "insert into job.read_model_dirty_scopes" in " ".join(sql.lower().split())
    ]
    pending_scope_keys = {
        str(params[2])
        for params in dirty_params
        if str(params[1]) == "pending_invoice"
    }

    assert pending_scope_keys == {
        "expense:all:2026-02",
        "expense:requires_invoice:2026-02",
        "expense:bank_statement_as_invoice:2026-02",
        "expense:no_invoice_required:2026-02",
    }


def test_relation_downstream_refresh_routes_scope_keys_by_row_domain() -> None:
    connection = RecordingConnection(
        invoice_types=["input"],
        bank_directions=["outflow"],
        bank_scope_keys=["2026-02"],
        invoice_scope_keys=["2026-01"],
        workbench_scope_keys=[],
    )
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(month_scope="2026-02"),
        changed_case_ids={"CASE-1"},
    )

    dirty_params = [
        params
        for sql, params in connection.fetch_one_calls
        if "insert into job.read_model_dirty_scopes" in " ".join(sql.lower().split())
    ]
    scope_keys_by_type: dict[str, set[str]] = {}
    for params in dirty_params:
        scope_keys_by_type.setdefault(str(params[1]), set()).add(str(params[2]))

    assert scope_keys_by_type["workbench_relation"] == {"2026-01", "2026-02"}
    assert scope_keys_by_type["workbench"] == {"2026-01", "2026-02", "all"}
    assert scope_keys_by_type["bank_detail"] == {"2026-02"}
    assert scope_keys_by_type["invoice_lifecycle"] == {"2026-01"}
    assert scope_keys_by_type["input_invoice_usage"] == {"2026-01"}
    assert scope_keys_by_type["tax_offset"] == {"2026-01"}
    assert scope_keys_by_type["search"] == {"2026-01", "2026-02"}
    assert "cost_statistics" not in scope_keys_by_type
    assert scope_keys_by_type["pending_invoice"] == {
        "expense:all:2026-02",
        "expense:requires_invoice:2026-02",
        "expense:bank_statement_as_invoice:2026-02",
        "expense:no_invoice_required:2026-02",
    }
    workbench_all_outbox_payloads = [
        _json_payload(params[8])
        for sql, params in connection.execute_calls
        if "insert into job.outbox_events" in " ".join(sql.lower().split())
        and str(params[3]) == "workbench"
        and str(params[4]) == "all"
    ]
    assert workbench_all_outbox_payloads[-1]["aggregate_only"] is True
    assert workbench_all_outbox_payloads[-1]["parent_scope_keys"] == ["2026-01", "2026-02"]
    workbench_all_outbox_params = [
        params
        for sql, params in connection.execute_calls
        if "insert into job.outbox_events" in " ".join(sql.lower().split())
        and str(params[3]) == "workbench"
        and str(params[4]) == "all"
    ]
    assert workbench_all_outbox_params[-1][5] == "workbench.read_model.refresh:workbench:all:aggregate"


def test_relation_refresh_uses_full_workbench_all_only_when_scope_is_unknown() -> None:
    connection = RecordingConnection(
        invoice_types=["input"],
        bank_directions=["outflow"],
        bank_scope_keys=[],
        invoice_scope_keys=[],
        oa_scope_keys=[],
        workbench_scope_keys=[],
    )
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(month_scope=""),
        changed_case_ids={"CASE-1"},
    )

    dirty_params = [
        params
        for sql, params in connection.fetch_one_calls
        if "insert into job.read_model_dirty_scopes" in " ".join(sql.lower().split())
    ]
    scope_keys_by_type: dict[str, set[str]] = {}
    for params in dirty_params:
        scope_keys_by_type.setdefault(str(params[1]), set()).add(str(params[2]))

    assert scope_keys_by_type["workbench"] == {"all"}
    workbench_all_outbox_payloads = [
        _json_payload(params[8])
        for sql, params in connection.execute_calls
        if "insert into job.outbox_events" in " ".join(sql.lower().split())
        and str(params[3]) == "workbench"
        and str(params[4]) == "all"
    ]
    assert workbench_all_outbox_payloads
    assert "aggregate_only" not in workbench_all_outbox_payloads[-1]


def test_relation_downstream_refresh_enqueues_all_scope_when_oa_month_is_unresolved() -> None:
    connection = RecordingConnection(
        bank_scope_keys=["2026-04"],
        invoice_scope_keys=[],
        oa_scope_keys=[],
    )
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(row_types=["bank", "oa"], month_scope="2026-04"),
        changed_case_ids={"CASE-1"},
    )

    dirty_params = [
        params
        for sql, params in connection.fetch_one_calls
        if "insert into job.read_model_dirty_scopes" in " ".join(sql.lower().split())
    ]
    scope_keys_by_type: dict[str, set[str]] = {}
    for params in dirty_params:
        scope_keys_by_type.setdefault(str(params[1]), set()).add(str(params[2]))

    assert scope_keys_by_type["workbench_relation"] == {"2026-04"}
    assert scope_keys_by_type["oa_pending_payment"] == {"all"}


def test_relation_downstream_refresh_enqueues_all_scope_when_invoice_month_is_unresolved() -> None:
    connection = RecordingConnection(
        invoice_types=["input"],
        bank_directions=["outflow"],
        bank_scope_keys=["2026-04"],
        invoice_scope_keys=[],
    )
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(row_types=["bank", "invoice"], month_scope="2026-04"),
        changed_case_ids={"CASE-1"},
    )

    dirty_params = [
        params
        for sql, params in connection.fetch_one_calls
        if "insert into job.read_model_dirty_scopes" in " ".join(sql.lower().split())
    ]
    scope_keys_by_type: dict[str, set[str]] = {}
    for params in dirty_params:
        scope_keys_by_type.setdefault(str(params[1]), set()).add(str(params[2]))

    assert scope_keys_by_type["workbench_relation"] == {"2026-04"}
    assert scope_keys_by_type["input_invoice_usage"] == {"all"}
    assert scope_keys_by_type["tax_offset"] == {"all"}


def test_relation_downstream_refresh_routes_cost_statistics_by_bank_month_for_cost_bearing_relation() -> None:
    connection = RecordingConnection(
        bank_scope_keys=["2026-02"],
        oa_scope_keys=["2026-01"],
        workbench_scope_keys=[],
    )
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(row_types=["bank", "oa"], month_scope="2026-02"),
        changed_case_ids={"CASE-1"},
    )

    dirty_params = [
        params
        for sql, params in connection.fetch_one_calls
        if "insert into job.read_model_dirty_scopes" in " ".join(sql.lower().split())
    ]
    cost_scope_keys = {
        str(params[2])
        for params in dirty_params
        if str(params[1]) == "cost_statistics"
    }

    assert cost_scope_keys == {"active:2026-02", "all:2026-02"}


def test_relation_downstream_refresh_preserves_workbench_scope_fallback_for_legacy_rows() -> None:
    connection = RecordingConnection(
        invoice_types=[],
        bank_directions=["outflow"],
        bank_scope_keys=[],
        invoice_scope_keys=[],
        workbench_scope_keys=["2026-04"],
    )
    repository = PostgresWorkbenchRelationRepository(connection)

    repository.save_workbench_pair_relations(
        _snapshot(row_types=["bank"], month_scope=""),
        changed_case_ids={"CASE-1"},
    )

    dirty_params = [
        params
        for sql, params in connection.fetch_one_calls
        if "insert into job.read_model_dirty_scopes" in " ".join(sql.lower().split())
    ]
    scope_keys_by_type: dict[str, set[str]] = {}
    for params in dirty_params:
        scope_keys_by_type.setdefault(str(params[1]), set()).add(str(params[2]))

    assert scope_keys_by_type["workbench_relation"] == {"2026-04"}
    assert scope_keys_by_type["bank_detail"] == {"2026-04"}
    assert scope_keys_by_type["search"] == {"2026-04"}
    assert "cost_statistics" not in scope_keys_by_type
    assert scope_keys_by_type["pending_invoice"] == {
        "expense:all:2026-04",
        "expense:requires_invoice:2026-04",
        "expense:bank_statement_as_invoice:2026-04",
        "expense:no_invoice_required:2026-04",
    }
